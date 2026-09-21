# controllers/sat_cfdi_controller.py
from __future__ import annotations

import io
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
import streamlit as st

from utils.sat_client import (
    TIPOS_COMPROBANTE,
    cargar_fiel,
    solicitar_descarga,
    verificar_solicitud,
    descargar_paquete,
    consultar_estado,
)
from models.sat_cfdi_model import (
    upsert_cfdis,
    actualizar_estado,
    uuids_vigentes_para_verificar,
    listar_cfdi,
    contar_cfdi,
    obtener_xml_por_uuid,
    registrar_sync_run,
    actualizar_sync_run,
    listar_solicitudes_pendientes,
    listar_sync_runs,
)
from models.datoscfd_model import importar_cfdi_xml_a_mysql

# códigos de EstadoSolicitud del SAT (VerificaSolicitudDescarga)
_SAT_ACEPTADA = "1"
_SAT_EN_PROCESO = "2"
_SAT_TERMINADA = "3"
_SAT_ERROR = "4"
_SAT_RECHAZADA = "5"

# CodigoEstadoSolicitud específico del SAT para "No se encontró información":
# la solicitud queda EstadoSolicitud=5 (Rechazada) pero no es un error real,
# solo no hay ningún CFDI de ese tipo_comprobante en el rango pedido.
_SAT_COD_SIN_INFO = "5004"

# El SAT a veces contesta VerificaSolicitudDescarga sin el atributo
# EstadoSolicitud (solo CodEstatus=5000 / Mensaje="Solicitud Aceptada"), y las
# fallas de red (timeout, etc.) también pueden ocurrir al verificar o al bajar
# el paquete. Antes esto se marcaba 'error' terminal desde el primer intento y
# la solicitud desaparecía de listar_solicitudes_pendientes() para siempre
# -> se perdían CFDI reales. Ahora se reintenta (cada 60s vía
# sat-cfdi-verificar-pendientes.timer) hasta este límite antes de darla por
# perdida de verdad.
_LIMITE_ESPERA_SOLICITUD = timedelta(days=5)


def _solicitud_vencida(row: dict) -> bool:
    creado_en = row.get("creado_en")
    if not creado_en:
        return False
    return datetime.utcnow() - creado_en > _LIMITE_ESPERA_SOLICITUD


def solicitar_sync(
    secrets,
    usuario: str,
    fecha_desde: date,
    fecha_hasta: date,
    tipos: tuple[str, ...] = TIPOS_COMPROBANTE,
    origen: str = "manual",
) -> list[dict]:
    """
    Dispara una solicitud de descarga por cada tipo_comprobante y la deja
    registrada en sat_sync_runs con estado_solicitud='solicitada'.
    No descarga nada todavía — eso lo hace verificar_y_completar_pendientes,
    porque la Descarga Masiva del SAT es asíncrona y puede tardar.
    """
    try:
        fiel, rfc = cargar_fiel(secrets)
    except Exception as e:
        run_id = registrar_sync_run(
            tipo="descarga", origen=origen, usuario=usuario,
            fecha_desde=fecha_desde, fecha_hasta=fecha_hasta,
            estado_solicitud="error", estado="error",
            mensaje_error=f"no se pudo cargar la FIEL: {e}",
        )
        return [{"tipo": t, "run_id": run_id, "id_solicitud": None, "ok": False, "mensaje": str(e)} for t in tipos]

    resultados = []

    for tipo in tipos:
        try:
            solicitud = solicitar_descarga(fiel, rfc, fecha_desde, fecha_hasta, tipo)
            id_solicitud = solicitud.get("id_solicitud")
            ok = bool(id_solicitud)
            run_id = registrar_sync_run(
                tipo="descarga",
                origen=origen,
                usuario=usuario,
                fecha_desde=fecha_desde,
                fecha_hasta=fecha_hasta,
                tipo_comprobante=tipo,
                id_solicitud=id_solicitud,
                estado_solicitud="solicitada" if ok else "error",
                estado="ok" if ok else "error",
                mensaje_error=None if ok else str(solicitud.get("mensaje") or solicitud),
            )
            resultados.append({
                "tipo": tipo, "run_id": run_id, "id_solicitud": id_solicitud,
                "ok": ok, "mensaje": solicitud.get("mensaje"),
            })
        except Exception as e:
            run_id = registrar_sync_run(
                tipo="descarga", origen=origen, usuario=usuario,
                fecha_desde=fecha_desde, fecha_hasta=fecha_hasta,
                tipo_comprobante=tipo, estado_solicitud="error", estado="error",
                mensaje_error=str(e),
            )
            resultados.append({"tipo": tipo, "run_id": run_id, "id_solicitud": None, "ok": False, "mensaje": str(e)})

    return resultados


def verificar_y_completar_pendientes(secrets) -> list[dict]:
    """
    Revisa todas las solicitudes de descarga que aún no están 'terminada' o 'error':
    - si el SAT ya la terminó, descarga los paquetes, los guarda en sat_cfdi_recibidos
      y marca la corrida como 'terminada'.
    - si sigue en proceso, solo actualiza el estado y la deja pendiente.
    - si el SAT la marcó como error/rechazada, la marca como 'error'.
    Es la misma función que usa el botón manual "Verificar pendientes" y el timer diario.
    """
    pendientes = listar_solicitudes_pendientes()
    if not pendientes:
        return []

    try:
        fiel, rfc = cargar_fiel(secrets)
    except Exception as e:
        resultados = []
        for row in pendientes:
            if _solicitud_vencida(row):
                actualizar_sync_run(
                    row["id"], estado_solicitud="error", estado="error",
                    mensaje_error=f"sin resolución del SAT tras {_LIMITE_ESPERA_SOLICITUD.days} días: no se pudo cargar la FIEL: {e}",
                )
                resultados.append({"run_id": row["id"], "estado": "error", "mensaje": str(e)})
            else:
                # falla local/transitoria al cargar la FIEL: se deja la
                # solicitud como está para reintentar en la próxima corrida.
                resultados.append({"run_id": row["id"], "estado": "en_proceso",
                                    "mensaje": f"no se pudo cargar la FIEL, reintento pendiente: {e}"})
        return resultados

    resultados = []

    for row in pendientes:
        run_id = row["id"]
        id_solicitud = row["id_solicitud"]
        vencida = _solicitud_vencida(row)
        try:
            verif = verificar_solicitud(fiel, rfc, id_solicitud)
            estado_cod = str(verif.get("estado_solicitud") or "")

            if estado_cod == _SAT_TERMINADA:
                nuevos_total, actualizados_total = 0, 0
                errores_datoscfd = 0
                for id_paquete in verif.get("paquetes") or []:
                    cfdis = descargar_paquete(fiel, rfc, id_paquete)
                    n, a = upsert_cfdis(cfdis)
                    nuevos_total += n
                    actualizados_total += a

                    # además de sat_cfdi_recibidos, se refleja cada CFDI en
                    # DATOSCFD + CONCEPTOS (mismas tablas que usa la carga manual
                    # de XML/PDF) para que quede unificado con el resto del sistema.
                    for c in cfdis:
                        try:
                            importar_cfdi_xml_a_mysql(c["xml"].encode("utf-8"))
                        except Exception:
                            errores_datoscfd += 1
                actualizar_sync_run(
                    run_id,
                    estado_solicitud="terminada",
                    estado="ok",
                    xml_nuevos=nuevos_total,
                    xml_actualizados=actualizados_total,
                )
                resultados.append({
                    "run_id": run_id, "estado": "terminada",
                    "nuevos": nuevos_total, "actualizados": actualizados_total,
                    "errores_datoscfd": errores_datoscfd,
                })

            elif estado_cod in (_SAT_ACEPTADA, _SAT_EN_PROCESO):
                actualizar_sync_run(run_id, estado_solicitud="en_proceso")
                resultados.append({"run_id": run_id, "estado": "en_proceso"})

            elif estado_cod in (_SAT_ERROR, _SAT_RECHAZADA):
                codigo_especifico = str(verif.get("codigo_estado_solicitud") or "")
                if codigo_especifico == _SAT_COD_SIN_INFO:
                    # Rechazada por "no se encontró información": no hubo
                    # ningún CFDI de este tipo_comprobante en el rango
                    # pedido. Es un resultado válido (0 CFDI), no un error --
                    # el 'mensaje' del SAT aquí es genérico y engañoso
                    # ("Solicitud Aceptada"), por eso hay que fijarse en
                    # codigo_estado_solicitud en vez del 'mensaje'.
                    actualizar_sync_run(run_id, estado_solicitud="terminada", estado="ok",
                                         xml_nuevos=0, xml_actualizados=0)
                    resultados.append({"run_id": run_id, "estado": "terminada", "nuevos": 0,
                                        "actualizados": 0, "mensaje": "sin CFDI en el rango"})
                else:
                    # el SAT rechazó/erroreó la solicitud explícitamente por
                    # otro motivo: no hay nada que reintentar, se marca error
                    # de una vez.
                    mensaje = verif.get("mensaje") or f"EstadoSolicitud={estado_cod}"
                    mensaje_completo = f"{mensaje} (codigo_estado_solicitud={codigo_especifico or 'desconocido'})"
                    actualizar_sync_run(run_id, estado_solicitud="error", estado="error", mensaje_error=mensaje_completo)
                    resultados.append({"run_id": run_id, "estado": "error", "mensaje": mensaje_completo})

            else:
                # respuesta sin EstadoSolicitud reconocible -- p.ej. el SAT
                # todavía no le asignó estado a la solicitud y solo repite
                # CodEstatus=5000/Mensaje="Solicitud Aceptada". Se trata como
                # "sigue en proceso" y se reintenta, en vez de darla por
                # perdida en el primer chequeo.
                mensaje = verif.get("mensaje") or f"EstadoSolicitud={estado_cod!r} no reconocido"
                if vencida:
                    actualizar_sync_run(
                        run_id, estado_solicitud="error", estado="error",
                        mensaje_error=f"sin resolución del SAT tras {_LIMITE_ESPERA_SOLICITUD.days} días: {mensaje}",
                    )
                    resultados.append({"run_id": run_id, "estado": "error", "mensaje": mensaje})
                else:
                    actualizar_sync_run(run_id, estado_solicitud="en_proceso")
                    resultados.append({"run_id": run_id, "estado": "en_proceso", "mensaje": mensaje})

        except Exception as e:
            if vencida:
                actualizar_sync_run(
                    run_id, estado_solicitud="error", estado="error",
                    mensaje_error=f"sin resolución del SAT tras {_LIMITE_ESPERA_SOLICITUD.days} días: {e}",
                )
                resultados.append({"run_id": run_id, "estado": "error", "mensaje": str(e)})
            else:
                # falla transitoria (timeout, red, etc.): se deja la
                # solicitud tal cual (sigue 'solicitada'/'en_proceso') para
                # reintentar en la próxima corrida en vez de perderla.
                resultados.append({"run_id": run_id, "estado": "en_proceso", "mensaje": f"reintento pendiente: {e}"})

    return resultados


def verificar_cancelados(usuario: str, origen: str = "manual", limite: int = 500) -> dict:
    """
    Recorre los CFDI marcados como Vigente y consulta su estatus real contra el
    SAT (webservice público, no requiere FIEL). Actualiza estado_sat cuando cambia.
    """
    pendientes = uuids_vigentes_para_verificar(limite)
    actualizados = 0
    errores = 0

    for row in pendientes:
        try:
            resultado = consultar_estado(row["uuid"], row["rfc_emisor"], row["rfc_receptor"], row["total"])
            estado = (resultado.get("estado") or "").strip()
            if estado and estado != "Vigente":
                fecha_deteccion = datetime.utcnow() if estado == "Cancelado" else None
                actualizar_estado(row["uuid"], estado, fecha_deteccion)
                actualizados += 1
        except Exception:
            errores += 1

    registrar_sync_run(
        tipo="verificacion_cancelados",
        origen=origen,
        usuario=usuario,
        estado="ok" if errores == 0 else "error",
        xml_actualizados=actualizados,
        mensaje_error=f"{errores} consultas fallaron" if errores else None,
    )

    return {"revisados": len(pendientes), "actualizados": actualizados, "errores": errores}


# ---------------------------------------------------------------------------
# lectura para la vista (cacheada)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=60, show_spinner=False)
def cargar_cfdi(filtros: dict, page: int, page_size: int) -> pd.DataFrame:
    offset = (page - 1) * page_size
    return listar_cfdi(filtros, (offset, page_size))


@st.cache_data(ttl=60, show_spinner=False)
def contar_cfdi_cached(filtros: dict) -> int:
    return contar_cfdi(filtros)


@st.cache_data(ttl=30, show_spinner=False)
def cargar_bitacora(limite: int = 30) -> pd.DataFrame:
    return listar_sync_runs(limite)


def exportar_excel(df: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="cfdi_recibidos")
    return output.getvalue()


def descargar_xml_uuid(uuid: str):
    return obtener_xml_por_uuid(uuid)
