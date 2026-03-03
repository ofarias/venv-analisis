# models/datoscfd_model.py
from __future__ import annotations

from datetime import datetime, date
from decimal import Decimal
#from turtle import st
from typing import Any, Dict, Optional, Tuple, List
import xml.etree.ElementTree as ET
import pandas as pd
from database.conexion import obtener_conexion  # ajusta al import real
import re
import streamlit as st  

uuid_re = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")

UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)

_HYPHENS = "\u2010\u2011\u2012\u2013\u2014\u2212"  # ‐-‒–—−

def _normaliza_texto_uuid(s: str) -> str:
    if not s:
        return ""
    s = str(s).strip()
    for h in _HYPHENS:
        s = s.replace(h, "-")
    s = re.sub(r"\s+", "", s)
    return s

NS = {
    "cfdi3": "http://www.sat.gob.mx/cfd/3",
    "cfdi4": "http://www.sat.gob.mx/cfd/4",
    "tfd": "http://www.sat.gob.mx/TimbreFiscalDigital",
}


def _to_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _to_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(str(v).strip())
    except Exception:
        return None


def _to_date_from_cfdi_datetime(v: Any) -> Optional[date]:
    s = _to_str(v)
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
        return dt.date()
    except Exception:
        try:
            return datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S").date()
        except Exception:
            return None


def _find_first(root: ET.Element, paths: Tuple[str, ...]) -> Optional[ET.Element]:
    for p in paths:
        el = root.find(p, NS)
        if el is not None:
            return el
    return None


def _get_root_and_version(xml_bytes: bytes) -> Tuple[ET.Element, str]:
    root = ET.fromstring(xml_bytes)
    tag = root.tag or ""
    ver = root.attrib.get("Version") or root.attrib.get("version") or ""
    if "http://www.sat.gob.mx/cfd/4" in tag:
        return root, "4.0"
    if "http://www.sat.gob.mx/cfd/3" in tag:
        return root, "3.3" if not ver else ver
    return root, ver or "desconocida"


def _sum_impuestos(root: ET.Element) -> Dict[str, float]:

    out = {
        "total_traslados": 0.0,
        "total_retenidos": 0.0,

        "iva": 0.0,          # sum traslados 002
        "ieps": 0.0,         # sum traslados 003

        "isr_ret": 0.0,      # ret 001  (lo usaremos como ISR)
        "iva_ret": 0.0,      # ret 002
        "ieps_ret": 0.0,     # ret 003 (si aplica)

        "base_16": 0.0,
        "base_8": 0.0,
        "base_0": 0.0,
        "base_exento": 0.0,

        "iva_16": 0.0,
        "iva_8": 0.0,
        "iva_0": 0.0,
    }

    def _get_ns(root):
        if root.tag.startswith("{"):
            uri = root.tag.split("}")[0].strip("{")
            return {"cfdi": uri}
        return {}

    NS = _get_ns(root)

    comp = root
    imp = comp.find("cfdi:Impuestos", NS)
    if imp is None:
        return out

    out["total_traslados"] = float(
        imp.attrib.get("TotalImpuestosTrasladados", 0)
    )

    out["total_retenidos"] = float(
        imp.attrib.get("TotalImpuestosRetenidos", 0)
    )
    

    if imp is None:
        return out

    out["total_traslados"] = _to_float(imp.attrib.get("TotalImpuestosTrasladados")) or 0.0
    out["total_retenidos"] = _to_float(imp.attrib.get("TotalImpuestosRetenidos")) or 0.0

    #st.write(f"total_traslados: {out['total_traslados']}, total_retenidos: {out['total_retenidos']}\n")
    #st.stop()

    # traslados
    #traslados = imp.findall(".//cfdi4:Traslado", NS) + imp.findall(".//cfdi3:Traslado", NS)
    traslados = imp.findall(".//cfdi:Traslado", NS)
    for t in traslados:
        impuesto = _to_str(t.attrib.get("Impuesto"))
        importe = _to_float(t.attrib.get("Importe")) or 0.0
        base = _to_float(t.attrib.get("Base")) or 0.0
        tasa = (_to_str(t.attrib.get("TasaOCuota")) or "").strip()
        tipo_factor = (_to_str(t.attrib.get("TipoFactor")) or "").strip().lower()

        if impuesto == "002":
            # IVA trasladado
            out["iva"] += importe

            # desglose por tasa
            if tipo_factor == "exento":
                out["base_exento"] += base
            else:
                if tasa.startswith("0.160"):
                    out["base_16"] += base
                    out["iva_16"] += importe
                elif tasa.startswith("0.080"):
                    out["base_8"] += base
                    out["iva_8"] += importe
                elif tasa.startswith("0.000"):
                    out["base_0"] += base
                    out["iva_0"] += importe

        elif impuesto == "003":
            # IEPS trasladado (si viene)
            out["ieps"] += importe

    # retenciones
    #retenciones = imp.findall(".//cfdi4:Retencion", NS) + imp.findall(".//cfdi3:Retencion", NS)
    retenciones = imp.findall(".//cfdi:Retencion", NS)
    for r in retenciones:
        impuesto = _to_str(r.attrib.get("Impuesto"))
        importe = _to_float(r.attrib.get("Importe")) or 0.0

        if impuesto == "001":
            out["isr_ret"] += importe
        elif impuesto == "002":
            out["iva_ret"] += importe
        elif impuesto == "003":
            out["ieps_ret"] += importe

    return out


def parse_cfdi_to_datoscfd(xml_bytes: bytes) -> Dict[str, Any]:
    root, version = _get_root_and_version(xml_bytes)

    emisor = _find_first(root, (".//cfdi4:Emisor", ".//cfdi3:Emisor"))
    receptor = _find_first(root, (".//cfdi4:Receptor", ".//cfdi3:Receptor"))
    tfd = root.find(".//tfd:TimbreFiscalDigital", NS)

    uuid = _to_str(tfd.attrib.get("UUID") if tfd is not None else None)
    if not uuid:
        raise ValueError("el xml no trae uuid en timbrefiscaldigital")

    tax = _sum_impuestos(root)

    data: Dict[str, Any] = {}
    data["uuid"] = uuid.strip().upper()

    data["fecha_emision"] = _to_date_from_cfdi_datetime(root.attrib.get("Fecha"))
    data["fecha_timbrado"] = _to_date_from_cfdi_datetime(tfd.attrib.get("FechaTimbrado") if tfd is not None else None)

    data["rfc_emisor"] = _to_str(emisor.attrib.get("Rfc") if emisor is not None else None)
    data["nombre_emisor"] = _to_str(emisor.attrib.get("Nombre") if emisor is not None else None)
    data["regimen_fiscal"] = _to_str(emisor.attrib.get("RegimenFiscal") if emisor is not None else None)

    data["rfc_receptor"] = _to_str(receptor.attrib.get("Rfc") if receptor is not None else None)
    data["nombre_receptor"] = _to_str(receptor.attrib.get("Nombre") if receptor is not None else None)

    # cambio 3: llenar usocfdi_ desde UsoCFDI del xml (además de usocfdi)
    uso = _to_str(receptor.attrib.get("UsoCFDI") if receptor is not None else None)
    data["usocfdi"] = uso
    data["usocfdi_"] = (uso or "").strip().upper()  # <- cambio 3

    data["regimen_fiscal_receptor"] = _to_str(receptor.attrib.get("RegimenFiscalReceptor") if receptor is not None else None)

    # cambio 1: si no trae Serie/Folio guardar '' (no NULL)
    data["folio"] = (_to_str(root.attrib.get("Folio")) or "")  # <- cambio 1
    data["serie"] = (_to_str(root.attrib.get("Serie")) or "")  # <- cambio 1

    data["total"] = _to_float(root.attrib.get("Total"))
    data["subtotal"] = _to_float(root.attrib.get("SubTotal"))
    data["descuento"] = _to_float(root.attrib.get("Descuento"))

    data["version"] = _to_str(root.attrib.get("Version") or root.attrib.get("version") or version)
    data["moneda"] = _to_str(root.attrib.get("Moneda"))

    # si viene null, tu UI ya lo puede default a 1, pero aquí lo dejamos como float|None
    data["tipocambio"] = _to_float(root.attrib.get("TipoCambio"))

    data["formapago"] = _to_str(root.attrib.get("FormaPago"))
    data["metodopago"] = _to_str(root.attrib.get("MetodoPago"))
    data["tipocomprobante"] = _to_str(root.attrib.get("TipoDeComprobante"))
    data["lugar_expedicion"] = _to_str(root.attrib.get("LugarExpedicion"))

    data["rfc_prov_certif"] = _to_str(tfd.attrib.get("RfcProvCertif") if tfd is not None else None)

    # cambio 2: impuestos desde cfdi:Impuestos (retenciones/traslados)
    data["total_traslados"] = float(tax["total_traslados"])
    data["total_retenidos"] = float(tax["total_retenidos"])

    data["iva"] = float(tax["iva"])                    # traslados 002 (todas tasas)
    data["iva_ret"] = float(tax["iva_ret"])            # ret 002
    data["isr"] = float(tax["isr_ret"])                # <- cambio 2 (ISR desde Retenciones 001)
    data["ieps"] = float(tax["ieps"])                  # traslados 003 (si aplica)

    # conservamos estos campos por compatibilidad con tu tabla
    data["isr_ret"] = float(tax["isr_ret"])
    data["ieps_ret"] = float(tax["ieps_ret"])

    data["total_traslados_base_iva16"] = float(tax["base_16"])
    data["total_traslados_impuesto_iva16"] = float(tax["iva_16"])
    data["total_traslados_base_iva8"] = float(tax["base_8"])
    data["total_traslados_impuesto_iva8"] = float(tax["iva_8"])
    data["total_traslado_base_iva0"] = float(tax["base_0"])
    data["total_traslados_impuesto_iva0"] = float(tax["iva_0"])
    data["total_traslado_base_iva_exento"] = float(tax["base_exento"])

    data["base_tasa_16"] = float(Decimal(str(tax["base_16"])).quantize(Decimal("0.01")))
    data["base_tasa_8"] = float(Decimal(str(tax["base_8"])).quantize(Decimal("0.01")))
    data["base_tasa_0"] = float(Decimal(str(tax["base_0"])).quantize(Decimal("0.01")))
    data["base_tasa_exento"] = float(Decimal(str(tax["base_exento"])).quantize(Decimal("0.01")))

    # IVA_TASA_16 desde traslados 002 tasa 0.16
    data["iva_tasa_16"] = float(Decimal(str(tax["iva_16"])).quantize(Decimal("0.01")))  # <- cambio 2
    data["iva_tasa_8"] = float(Decimal(str(tax["iva_8"])).quantize(Decimal("0.01")))

    data["reporte_validacioncfd"] = xml_bytes.decode("utf-8", errors="replace")

    return data

    #### NORMALIZAMOS PARA DATOSCFD


TIPO_COMPROBANTE_MAP = {
    "I": "Ingreso",
    "E": "Egreso",
    "N": "Nómina",
    "P": "Pago",
    "T": "Traslado",
}

METODO_PAGO_MAP = {
    "PUE": "Pago en una sola exhibición",
    "PPD": "Pago en parcialidades o diferido",
}

FORMA_PAGO_MAP = {
    "01": "Efectivo",
    "03": "Transferencia electrónica de fondos",
    "04": "Tarjeta de crédito",
    "05": "Monedero electrónico",
    "06": "Dinero electrónico",
    "15": "Condonación",
    "17": "Compensación",
    "28": "Tarjeta de débito",
    "29": "Tarjeta de servicios",
    "30": "Aplicación de anticipos",
    "31": "Intermediario pagos",
    "99": "Por definir",
}

def _norm_code(x: Any) -> str:
    return ("" if x is None else str(x)).strip().upper()

def normalizar_antes_upsert(data: Dict[str, Any]) -> Dict[str, Any]:
    data = dict(data or {})

    # tipocomprobante: letra -> texto
    tc = _norm_code(data.get("tipocomprobante"))
    if tc in TIPO_COMPROBANTE_MAP:
        data["tipocomprobante"] = TIPO_COMPROBANTE_MAP[tc]
    else:
        # si ya viene como "Ingreso", "Egreso", etc, se respeta
        data["tipocomprobante"] = (data.get("tipocomprobante") or "").strip()

    # metodopago: usar metodopago_ (código) para llenar metodopago (texto)
    mp_code = _norm_code(data.get("metodopago_") or data.get("metodopago"))
    if mp_code in METODO_PAGO_MAP:
        data["metodopago"] = METODO_PAGO_MAP[mp_code]
        data["metodopago_"] = mp_code
    else:
        data["metodopago"] = (data.get("metodopago") or "").strip()

    # formapago: usar formapago_ (código) para llenar formapago (texto)
    fp_code = _norm_code(data.get("formapago_") or data.get("formapago"))
    if fp_code in FORMA_PAGO_MAP:
        data["formapago"] = FORMA_PAGO_MAP[fp_code]
        data["formapago_"] = fp_code
    else:
        data["formapago"] = (data.get("formapago") or "").strip()

    return data



def upsert_datoscfd(data: Dict[str, Any]) -> Dict[str, Any]:
    conn = None
    cursor = None
    try:
        conn = obtener_conexion()
        cursor = conn.cursor()
        data = normalizar_antes_upsert(data)
        sql = """
        INSERT INTO DATOSCFD (
            UUID, RFC_EMISOR, RFC_RECEPTOR, FECHA_EMISION,
            REPORTE_VALIDACIONCFD, NOMBRE_EMISOR, NOMBRE_RECEPTOR, FOLIO, SERIE,
            TOTAL, SUBTOTAL, IVA, `VERSION`, MONEDA, TIPOCAMBIO,
            FORMAPAGO, METODOPAGO, TIPOCOMPROBANTE, USOCFDI, USOCFDI_, DESCUENTO,
            LUGAR_EXPEDICION, REGIMEN_FISCAL, TOTAL_TRASLADOS, ISR, IEPS,
            TOTAL_RETENIDOS, IVA_RET, ISR_RET, IEPS_RET, RFC_PROV_CERTIF,
            FECHA_TIMBRADO, REGIMEN_FISCAL_RECEPTOR,
            TOTAL_TRASLADOS_BASE_IVA16, TOTAL_TRASLADOS_IMPUESTO_IVA16,
            TOTAL_TRASLADOS_BASE_IVA8, TOTAL_TRASLADOS_IMPUESTO_IVA8,
            TOTAL_TRASLADO_BASE_IVA0, TOTAL_TRASLADOS_IMPUESTO_IVA0,
            TOTAL_TRASLADO_BASE_IVA_EXENTO,
            BASE_TASA_16, BASE_TASA_8, BASE_TASA_0, BASE_TASA_EXENTO,
            IVA_TASA_16, IVA_TASA_8,
            FORMAPAGO_, METODOPAGO_
        ) VALUES (
            %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s,
            %s, %s,
            %s, %s,
            %s, %s,
            %s,
            %s, %s, %s, %s,
            %s, %s,
            %s, %s 
        )
        ON DUPLICATE KEY UPDATE
            RFC_EMISOR = VALUES(RFC_EMISOR),
            RFC_RECEPTOR = VALUES(RFC_RECEPTOR),
            FECHA_EMISION = VALUES(FECHA_EMISION),
            REPORTE_VALIDACIONCFD = VALUES(REPORTE_VALIDACIONCFD),
            NOMBRE_EMISOR = VALUES(NOMBRE_EMISOR),
            NOMBRE_RECEPTOR = VALUES(NOMBRE_RECEPTOR),
            FOLIO = VALUES(FOLIO),
            SERIE = VALUES(SERIE),
            TOTAL = VALUES(TOTAL),
            SUBTOTAL = VALUES(SUBTOTAL),
            IVA = VALUES(IVA),
            `VERSION` = VALUES(`VERSION`),
            MONEDA = VALUES(MONEDA),
            TIPOCAMBIO = VALUES(TIPOCAMBIO),
            FORMAPAGO = VALUES(FORMAPAGO),
            METODOPAGO = VALUES(METODOPAGO),
            TIPOCOMPROBANTE = VALUES(TIPOCOMPROBANTE),
            USOCFDI = VALUES(USOCFDI),
            USOCFDI_ = VALUES(USOCFDI_),
            DESCUENTO = VALUES(DESCUENTO),
            LUGAR_EXPEDICION = VALUES(LUGAR_EXPEDICION),
            REGIMEN_FISCAL = VALUES(REGIMEN_FISCAL),
            TOTAL_TRASLADOS = VALUES(TOTAL_TRASLADOS),
            ISR = VALUES(ISR),
            IEPS = VALUES(IEPS),
            TOTAL_RETENIDOS = VALUES(TOTAL_RETENIDOS),
            IVA_RET = VALUES(IVA_RET),
            ISR_RET = VALUES(ISR_RET),
            IEPS_RET = VALUES(IEPS_RET),
            RFC_PROV_CERTIF = VALUES(RFC_PROV_CERTIF),
            FECHA_TIMBRADO = VALUES(FECHA_TIMBRADO),
            REGIMEN_FISCAL_RECEPTOR = VALUES(REGIMEN_FISCAL_RECEPTOR),
            TOTAL_TRASLADOS_BASE_IVA16 = VALUES(TOTAL_TRASLADOS_BASE_IVA16),
            TOTAL_TRASLADOS_IMPUESTO_IVA16 = VALUES(TOTAL_TRASLADOS_IMPUESTO_IVA16),
            TOTAL_TRASLADOS_BASE_IVA8 = VALUES(TOTAL_TRASLADOS_BASE_IVA8),
            TOTAL_TRASLADOS_IMPUESTO_IVA8 = VALUES(TOTAL_TRASLADOS_IMPUESTO_IVA8),
            TOTAL_TRASLADO_BASE_IVA0 = VALUES(TOTAL_TRASLADO_BASE_IVA0),
            TOTAL_TRASLADOS_IMPUESTO_IVA0 = VALUES(TOTAL_TRASLADOS_IMPUESTO_IVA0),
            TOTAL_TRASLADO_BASE_IVA_EXENTO = VALUES(TOTAL_TRASLADO_BASE_IVA_EXENTO),
            BASE_TASA_16 = VALUES(BASE_TASA_16),
            BASE_TASA_8 = VALUES(BASE_TASA_8),
            BASE_TASA_0 = VALUES(BASE_TASA_0),
            BASE_TASA_EXENTO = VALUES(BASE_TASA_EXENTO),
            IVA_TASA_16 = VALUES(IVA_TASA_16),
            IVA_TASA_8 = VALUES(IVA_TASA_8),
            FORMAPAGO_ = VALUES(FORMAPAGO_),
            METODOPAGO_ = VALUES(METODOPAGO_)
        """

        params = (
            data.get("uuid"),
            data.get("rfc_emisor"),
            data.get("rfc_receptor"),
            data.get("fecha_emision"),
            data.get("reporte_validacioncfd"),
            data.get("nombre_emisor"),
            data.get("nombre_receptor"),
            data.get("folio"),          # cambio 1: ya viene '' si no hay
            data.get("serie"),          # cambio 1: ya viene '' si no hay
            data.get("total"),
            data.get("subtotal"),
            data.get("iva"),            # cambio 2
            data.get("version"),
            data.get("moneda"),
            data.get("tipocambio"),
            data.get("formapago"),
            data.get("metodopago"),
            data.get("tipocomprobante"),
            data.get("usocfdi"),
            data.get("usocfdi_"),       # cambio 3
            data.get("descuento"),
            data.get("lugar_expedicion"),
            data.get("regimen_fiscal"),
            data.get("total_traslados"),
            data.get("isr"),            # cambio 2 (retenciones 001)
            data.get("ieps"),           # cambio 2
            data.get("total_retenidos"),
            data.get("iva_ret"),        # cambio 2
            data.get("isr_ret"),
            data.get("ieps_ret"),
            data.get("rfc_prov_certif"),
            data.get("fecha_timbrado"),
            data.get("regimen_fiscal_receptor"),
            data.get("total_traslados_base_iva16"),
            data.get("total_traslados_impuesto_iva16"),
            data.get("total_traslados_base_iva8"),
            data.get("total_traslados_impuesto_iva8"),
            data.get("total_traslado_base_iva0"),
            data.get("total_traslados_impuesto_iva0"),
            data.get("total_traslado_base_iva_exento"),
            data.get("base_tasa_16"),
            data.get("base_tasa_8"),
            data.get("base_tasa_0"),
            data.get("base_tasa_exento"),
            data.get("iva_tasa_16"),    # cambio 2
            data.get("iva_tasa_8"),
            data.get("formapago_"),
            data.get("metodopago_")
        )

        cursor.execute(sql, params)
        affected = cursor.rowcount
        conn.commit()

        if affected == 1:
            status = "inserted"
        elif affected == 2:
            status = "updated"
        else:
            status = "duplicated"

        return {"ok": True, "uuid": data.get("uuid"), "status": status}

    except Exception as e:
        try:
            if conn is not None:
                conn.rollback()
        except Exception:
            pass
        return {"ok": False, "uuid": data.get("uuid"), "error": str(e)}

    finally:
        try:
            if cursor is not None:
                cursor.close()
        except Exception:
            pass
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass


def importar_cfdi_xml_a_mysql(xml_bytes: bytes) -> Dict[str, Any]:
    try:
        data = parse_cfdi_to_datoscfd(xml_bytes)
        return upsert_datoscfd(data)
    except Exception as e:
        return {"ok": False, "error": str(e)}


def buscar_datoscfd_mysql(uuid: str, folio: Optional[str] = None, monto: Optional[float] = None) -> pd.DataFrame:
    uuid = (uuid or "").strip().upper()
    folio = (folio or "").strip()

    where = ["UUID = %s"]
    params: List[Any] = [uuid]

    if folio:
        where.append("FOLIO = %s")
        params.append(folio)

    if monto and float(monto) > 0:
        where.append("TOTAL BETWEEN %s AND %s")
        params.append(float(monto) - 0.01)
        params.append(float(monto) + 0.01)

    sql = f"""
        SELECT
            ID_DOCTODIG,
            UUID,
            RFC_EMISOR,
            RFC_RECEPTOR,
            FECHA_EMISION,
            NOMBRE_EMISOR,
            NOMBRE_RECEPTOR,
            FOLIO,
            SERIE,
            TOTAL,
            SUBTOTAL,
            IVA,
            VERSION,
            MONEDA,
            TIPOCAMBIO,
            FORMAPAGO,
            METODOPAGO,
            TIPOCOMPROBANTE,
            USOCFDI,
            USOCFDI_,
            LUGAR_EXPEDICION,
            REGIMEN_FISCAL,
            REGIMEN_FISCAL_RECEPTOR,
            CONTABILIZADO
        FROM DATOSCFD
        WHERE {" AND ".join(where)}
        ORDER BY ID_DOCTODIG DESC
        LIMIT 50
    """

    conn = obtener_conexion()
    try:
        df = pd.read_sql(sql, conn, params=params)
        return df
    finally:
        conn.close()


def guardar_pdf_datoscfd(
    pdf_bytes: bytes,
    nombre_archivo: str,
    usuario: str,
    uuid: Optional[str] = None,
    id_doctodig: Optional[int] = None,
    metodo_uuid: str = "sin_uuid",
    status: str = "cargado",
) -> Dict[str, Any]:
    conn = None
    cursor = None
    try:
        conn = obtener_conexion()
        cursor = conn.cursor()

        sql = """
            insert into DATOSCFD_PDF
              (uuid, id_doctodig, nombre_archivo, archivo, tamano, usuario, metodo_uuid, status)
            values
              (%s, %s, %s, %s, %s, %s, %s, %s)
        """

        u = (uuid or "").strip().upper() or None
        idd = int(id_doctodig) if id_doctodig else None

        cursor.execute(sql, (u, idd, nombre_archivo, pdf_bytes, len(pdf_bytes), usuario, metodo_uuid, status))
        conn.commit()

        return {"ok": True, "id_pdf": cursor.lastrowid, "uuid": u, "metodo_uuid": metodo_uuid, "status": status}

    except Exception as e:
        try:
            if conn:
                conn.rollback()
        except Exception:
            pass
        return {"ok": False, "error": str(e)}

    finally:
        try:
            if cursor:
                cursor.close()
        except Exception:
            pass
        try:
            if conn:
                conn.close()
        except Exception:
            pass


def extraer_uuid_desde_pdf(pdf_bytes: bytes) -> Optional[str]:
    import io
    import re

    uuid_re = re.compile(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
    )

    hyphens = "\u2010\u2011\u2012\u2013\u2014\u2212"  # ‐-‒–—−

    def _normaliza(s: str) -> str:
        if not s:
            return ""
        s = str(s)
        for h in hyphens:
            s = s.replace(h, "-")
        s = re.sub(r"\s+", "", s)
        return s

    def _buscar(s: str) -> Optional[str]:
        s2 = _normaliza(s)
        m = uuid_re.search(s2)
        return m.group(0).upper() if m else None

    try:
        try:
            from pypdf import PdfReader  # type: ignore
        except Exception:
            from PyPDF2 import PdfReader  # type: ignore

        reader = PdfReader(io.BytesIO(pdf_bytes))
        texto = ""
        for page in reader.pages[:5]:
            try:
                texto += "\n" + (page.extract_text() or "")
            except Exception:
                pass

        u = _buscar(texto)
        if u:
            return u
    except Exception:
        pass

    try:
        from pdfminer.high_level import extract_text  # type: ignore

        texto = extract_text(io.BytesIO(pdf_bytes), maxpages=5) or ""
        u = _buscar(texto)
        if u:
            return u
    except Exception:
        pass

    try:
        import pdfplumber  # type: ignore

        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            texto = ""
            for i in range(min(5, len(pdf.pages))):
                try:
                    texto += "\n" + (pdf.pages[i].extract_text() or "")
                except Exception:
                    pass
        u = _buscar(texto)
        if u:
            return u
    except Exception:
        pass

    return None