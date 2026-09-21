# utils/sat_client.py
from __future__ import annotations

import base64
import io
import os
import zipfile
from datetime import date, datetime

from lxml import etree

from cfdiclient import (
    Fiel,
    Autenticacion,
    SolicitaDescargaRecibidos,
    VerificaSolicitudDescarga,
    DescargaMasiva,
    Validacion,
)

TIPOS_COMPROBANTE = ("I", "E", "P")

# cfdiclient trae timeout=15 por default en sus llamadas SOAP al SAT — muy
# corto: el webservice de descarga masiva del SAT es notoriamente lento y
# tira "Read timed out" con 15s en horas pico. Se sube a 60s en todas las
# llamadas (autenticación, solicitud, verificación y descarga de paquete).
_TIMEOUT_SAT = 60

# terminada según cfdiclient.VerificaSolicitudDescarga (1=Aceptada, 2=EnProceso, 3=Terminada)
_ESTADO_TERMINADA = "3"

_SECRETS_TOML_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    ".streamlit",
    "secrets.toml",
)



def _cargar_config_sat(secrets=None) -> dict:
    """
    Devuelve el dict de la sección [SAT_FIEL] de secrets.toml.
    - Desde una vista de streamlit: pasa st.secrets (secrets["SAT_FIEL"] ya viene armado).
    - Desde un script standalone (systemd): lee el toml directo por ruta absoluta,
      porque st.secrets no es confiable fuera de un proceso streamlit en este repo.
    """
    if secrets is not None:
        return dict(secrets["SAT_FIEL"])

    import toml
    data = toml.load(_SECRETS_TOML_PATH)
    return data["SAT_FIEL"]


def cargar_fiel(secrets=None) -> tuple[Fiel, str]:
    cfg = _cargar_config_sat(secrets)
    rfc = (cfg.get("rfc") or "").strip().upper()
    if not rfc:
        raise ValueError("falta 'rfc' en [SAT_FIEL] de secrets.toml")

    with open(cfg["cer_path"], "rb") as f:
        cer_der = f.read()
    with open(cfg["key_path"], "rb") as f:
        key_der = f.read()

    fiel = Fiel(cer_der, key_der, cfg["password"])
    return fiel, rfc


def solicitar_descarga(fiel: Fiel, rfc: str, fecha_desde: date, fecha_hasta: date, tipo_comprobante: str) -> dict:
    """
    Paso 1-2 del protocolo: autenticación + solicitud de descarga de recibidos.
    Devuelve dict con al menos 'id_solicitud' y 'cod_estatus'.
    """
    if tipo_comprobante not in TIPOS_COMPROBANTE:
        raise ValueError(f"tipo_comprobante inválido: {tipo_comprobante!r}")

    token = Autenticacion(fiel, timeout=_TIMEOUT_SAT).obtener_token()

    fecha_inicial = datetime.combine(fecha_desde, datetime.min.time())
    fecha_final = datetime.combine(fecha_hasta, datetime.max.time().replace(microsecond=0))

    # El SAT rechaza la solicitud de recibidos si estado_comprobante es None o
    # "Cancelado" ("No se permite la descarga de xml que se encuentren
    # cancelados" - restricción real del SAT, confirmada en pruebas: solo deja
    # pedir "Vigente" para CFDI recibidos). Los cancelados se detectan después
    # vía consultar_estado() en el verificador diario.
    solicitud = SolicitaDescargaRecibidos(fiel, timeout=_TIMEOUT_SAT).solicitar_descarga(
        token,
        rfc,
        fecha_inicial,
        fecha_final,
        rfc_receptor=rfc,
        tipo_solicitud="CFDI",
        tipo_comprobante=tipo_comprobante,
        estado_comprobante="Vigente",
    )
    return solicitud


def verificar_solicitud(fiel: Fiel, rfc: str, id_solicitud: str) -> dict:
    """Paso 3: consulta el estado de una solicitud ya hecha (no bloquea/reintenta)."""
    token = Autenticacion(fiel, timeout=_TIMEOUT_SAT).obtener_token()
    return VerificaSolicitudDescarga(fiel, timeout=_TIMEOUT_SAT).verificar_descarga(token, rfc, id_solicitud)


def _parsear_cfdi(xml_bytes: bytes) -> dict | None:
    """
    Extrae los campos que guardamos de sat_cfdi_recibidos a partir del XML del CFDI.
    Usa comodín de namespace ("{*}Tag") para que funcione igual con CFDI 3.3 y 4.0
    sin tener que detectar la versión primero.
    """
    try:
        root = etree.fromstring(xml_bytes)
    except Exception:
        return None

    def _attr(el, name, default=None):
        return el.get(name, default) if el is not None else default

    comp = root
    tfd = comp.find(".//{*}TimbreFiscalDigital")

    uuid = _attr(tfd, "UUID") or ""
    if not uuid:
        return None

    fecha_emision = _attr(comp, "Fecha")
    fecha_timbrado = _attr(tfd, "FechaTimbrado")

    emisor = comp.find("{*}Emisor")
    receptor = comp.find("{*}Receptor")

    return {
        "uuid": uuid.strip().upper(),
        "tipo_comprobante": (_attr(comp, "TipoDeComprobante") or "")[:1],
        "fecha_emision": fecha_emision,
        "fecha_timbrado": fecha_timbrado,
        "rfc_emisor": _attr(emisor, "Rfc"),
        "nombre_emisor": _attr(emisor, "Nombre"),
        "rfc_receptor": _attr(receptor, "Rfc"),
        "nombre_receptor": _attr(receptor, "Nombre"),
        "moneda": _attr(comp, "Moneda"),
        "tipo_cambio": _attr(comp, "TipoCambio") or "1",
        "subtotal": _attr(comp, "SubTotal") or "0",
        "total": _attr(comp, "Total") or "0",
        "xml": xml_bytes.decode("utf-8", errors="ignore"),
    }


def descargar_paquete(fiel: Fiel, rfc: str, id_paquete: str) -> list[dict]:
    """Paso 4: descarga un paquete ya Terminado y regresa la lista de CFDI parseados."""
    token = Autenticacion(fiel, timeout=_TIMEOUT_SAT).obtener_token()
    resultado = DescargaMasiva(fiel, timeout=_TIMEOUT_SAT).descargar_paquete(token, rfc, id_paquete)

    paquete_b64 = resultado.get("paquete_b64") or resultado.get("paquete")
    if not paquete_b64:
        return []

    zip_bytes = base64.b64decode(paquete_b64)
    cfdis = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for nombre in zf.namelist():
            if not nombre.lower().endswith(".xml"):
                continue
            xml_bytes = zf.read(nombre)
            datos = _parsear_cfdi(xml_bytes)
            if datos:
                datos["archivo_nombre"] = nombre
                datos["id_paquete_sat"] = id_paquete
                cfdis.append(datos)
    return cfdis


def consultar_estado(uuid: str, rfc_emisor: str, rfc_receptor: str, total: str) -> dict:
    """
    Consulta pública de estatus (Vigente/Cancelado) por UUID vía el webservice
    "Consulta de Estado de CFDI" del SAT. No requiere FIEL (es una consulta pública),
    por eso no recibe `fiel` ni `rfc` del solicitante.
    Devuelve dict con 'estado' ('Vigente'/'Cancelado'), 'codigo_estatus', 'es_cancelable'.
    """
    validacion = Validacion(timeout=_TIMEOUT_SAT)
    return validacion.obtener_estado(rfc_emisor, rfc_receptor, str(total), uuid)
