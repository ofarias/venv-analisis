# models/sat_cfdi_model.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

import pandas as pd

from database.conexion import obtener_conexion


def _parse_fecha(valor):
    if not valor:
        return None
    if isinstance(valor, datetime):
        return valor
    try:
        return datetime.fromisoformat(valor)
    except ValueError:
        return None


def upsert_cfdis(cfdis: Iterable[dict]) -> tuple[int, int]:
    """
    Inserta/actualiza CFDI en sat_cfdi_recibidos (clave: uuid).
    Devuelve (nuevos, actualizados).
    """
    cfdis = list(cfdis)
    if not cfdis:
        return (0, 0)

    sql = """
        INSERT INTO sat_cfdi_recibidos
            (uuid, tipo_comprobante, fecha_emision, fecha_timbrado,
             rfc_emisor, nombre_emisor, rfc_receptor, nombre_receptor,
             moneda, tipo_cambio, subtotal, total, xml, archivo_nombre, id_paquete_sat)
        VALUES
            (%(uuid)s, %(tipo_comprobante)s, %(fecha_emision)s, %(fecha_timbrado)s,
             %(rfc_emisor)s, %(nombre_emisor)s, %(rfc_receptor)s, %(nombre_receptor)s,
             %(moneda)s, %(tipo_cambio)s, %(subtotal)s, %(total)s, %(xml)s,
             %(archivo_nombre)s, %(id_paquete_sat)s)
        ON DUPLICATE KEY UPDATE
            tipo_comprobante = VALUES(tipo_comprobante),
            fecha_emision    = VALUES(fecha_emision),
            fecha_timbrado   = VALUES(fecha_timbrado),
            rfc_emisor       = VALUES(rfc_emisor),
            nombre_emisor    = VALUES(nombre_emisor),
            rfc_receptor     = VALUES(rfc_receptor),
            nombre_receptor  = VALUES(nombre_receptor),
            moneda           = VALUES(moneda),
            tipo_cambio      = VALUES(tipo_cambio),
            subtotal         = VALUES(subtotal),
            total            = VALUES(total),
            xml              = VALUES(xml),
            archivo_nombre   = VALUES(archivo_nombre),
            id_paquete_sat   = VALUES(id_paquete_sat)
    """

    conn = obtener_conexion()
    cur = conn.cursor()
    nuevos = 0
    actualizados = 0
    try:
        for c in cfdis:
            params = {
                "uuid": c["uuid"],
                "tipo_comprobante": c.get("tipo_comprobante") or "",
                "fecha_emision": _parse_fecha(c.get("fecha_emision")),
                "fecha_timbrado": _parse_fecha(c.get("fecha_timbrado")),
                "rfc_emisor": c.get("rfc_emisor"),
                "nombre_emisor": c.get("nombre_emisor"),
                "rfc_receptor": c.get("rfc_receptor"),
                "nombre_receptor": c.get("nombre_receptor"),
                "moneda": c.get("moneda"),
                "tipo_cambio": c.get("tipo_cambio") or 1,
                "subtotal": c.get("subtotal") or 0,
                "total": c.get("total") or 0,
                "xml": c.get("xml") or "",
                "archivo_nombre": c.get("archivo_nombre"),
                "id_paquete_sat": c.get("id_paquete_sat"),
            }
            cur.execute(sql, params)
            # rowcount: 1 = insertó nuevo, 2 = actualizó existente (semántica de MySQL en ON DUPLICATE KEY UPDATE)
            if cur.rowcount == 1:
                nuevos += 1
            elif cur.rowcount == 2:
                actualizados += 1
        conn.commit()
    finally:
        cur.close()
        conn.close()

    return (nuevos, actualizados)


def actualizar_estado(uuid: str, estado: str, fecha_cancelacion: str | None = None) -> None:
    conn = obtener_conexion()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE sat_cfdi_recibidos
            SET estado_sat = %s, fecha_cancelacion = %s
            WHERE uuid = %s
            """,
            (estado, _parse_fecha(fecha_cancelacion), uuid),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def uuids_vigentes_para_verificar(limite: int = 500) -> list[dict]:
    """CFDI que hoy marcamos Vigente y que hay que re-checar contra el SAT."""
    conn = obtener_conexion()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(
            """
            SELECT uuid, rfc_emisor, rfc_receptor, total
            FROM sat_cfdi_recibidos
            WHERE estado_sat = 'Vigente'
            ORDER BY actualizado_en ASC
            LIMIT %s
            """,
            (int(limite),),
        )
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()


def listar_cfdi(filtros: dict | None = None, paginacion: tuple[int, int] | None = None) -> pd.DataFrame:
    filtros = filtros or {}
    where, params = [], []

    if filtros.get("fecha_desde"):
        where.append("fecha_emision >= %s")
        params.append(filtros["fecha_desde"])
    if filtros.get("fecha_hasta"):
        where.append("fecha_emision < DATE_ADD(%s, INTERVAL 1 DAY)")
        params.append(filtros["fecha_hasta"])
    if filtros.get("tipo_comprobante"):
        where.append("tipo_comprobante = %s")
        params.append(filtros["tipo_comprobante"])
    if filtros.get("rfc_emisor"):
        where.append("UPPER(rfc_emisor) LIKE CONCAT('%%', UPPER(%s), '%%')")
        params.append(filtros["rfc_emisor"][:13])
    if filtros.get("estado_sat"):
        where.append("estado_sat = %s")
        params.append(filtros["estado_sat"])

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    limit_sql = ""
    if paginacion:
        offset, limit = paginacion
        limit_sql = f" LIMIT {int(limit)} OFFSET {int(offset)}"

    sql = f"""
        SELECT id, uuid, tipo_comprobante, fecha_emision, fecha_timbrado,
               rfc_emisor, nombre_emisor, rfc_receptor, nombre_receptor,
               moneda, tipo_cambio, subtotal, total, estado_sat, fecha_cancelacion,
               archivo_nombre, creado_en
        FROM sat_cfdi_recibidos
        {where_sql}
        ORDER BY fecha_emision DESC, id DESC
        {limit_sql}
    """

    conn = obtener_conexion()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(sql, tuple(params))
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    return pd.DataFrame(rows) if rows else pd.DataFrame()


def contar_cfdi(filtros: dict | None = None) -> int:
    filtros = filtros or {}
    where, params = [], []

    if filtros.get("fecha_desde"):
        where.append("fecha_emision >= %s")
        params.append(filtros["fecha_desde"])
    if filtros.get("fecha_hasta"):
        where.append("fecha_emision < DATE_ADD(%s, INTERVAL 1 DAY)")
        params.append(filtros["fecha_hasta"])
    if filtros.get("tipo_comprobante"):
        where.append("tipo_comprobante = %s")
        params.append(filtros["tipo_comprobante"])
    if filtros.get("rfc_emisor"):
        where.append("UPPER(rfc_emisor) LIKE CONCAT('%%', UPPER(%s), '%%')")
        params.append(filtros["rfc_emisor"][:13])
    if filtros.get("estado_sat"):
        where.append("estado_sat = %s")
        params.append(filtros["estado_sat"])

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    sql = f"SELECT COUNT(*) AS n FROM sat_cfdi_recibidos {where_sql}"

    conn = obtener_conexion()
    cur = conn.cursor()
    try:
        cur.execute(sql, tuple(params))
        row = cur.fetchone()
        return int(row[0]) if row else 0
    finally:
        cur.close()
        conn.close()


def obtener_xml_por_uuid(uuid: str) -> tuple[bytes, str] | None:
    conn = obtener_conexion()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT xml, archivo_nombre FROM sat_cfdi_recibidos WHERE uuid = %s",
            (uuid,),
        )
        row = cur.fetchone()
        if not row:
            return None
        xml, nombre = row
        nombre = nombre or f"{uuid}.xml"
        return xml.encode("utf-8"), nombre
    finally:
        cur.close()
        conn.close()


# ---------------------------------------------------------------------------
# bitácora / seguimiento de corridas (sat_sync_runs)
# ---------------------------------------------------------------------------

def registrar_sync_run(
    tipo: str,
    origen: str,
    usuario: str | None = None,
    fecha_desde=None,
    fecha_hasta=None,
    tipo_comprobante: str | None = None,
    id_solicitud: str | None = None,
    estado_solicitud: str = "completado",
    estado: str = "ok",
    xml_nuevos: int = 0,
    xml_actualizados: int = 0,
    mensaje_error: str | None = None,
) -> int:
    conn = obtener_conexion()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO sat_sync_runs
                (tipo, origen, usuario, fecha_desde, fecha_hasta,
                 tipo_comprobante, id_solicitud, estado_solicitud,
                 estado, xml_nuevos, xml_actualizados, mensaje_error)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                tipo, origen, usuario, fecha_desde, fecha_hasta,
                tipo_comprobante, id_solicitud, estado_solicitud,
                estado, xml_nuevos, xml_actualizados, mensaje_error,
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        cur.close()
        conn.close()


def actualizar_sync_run(run_id: int, **campos: Any) -> None:
    """Actualiza columnas puntuales de una corrida (ej. tras verificar/descargar un paquete)."""
    if not campos:
        return
    sets = ", ".join(f"{k} = %s" for k in campos)
    params = list(campos.values()) + [run_id]

    conn = obtener_conexion()
    cur = conn.cursor()
    try:
        cur.execute(f"UPDATE sat_sync_runs SET {sets} WHERE id = %s", params)
        conn.commit()
    finally:
        cur.close()
        conn.close()


def listar_solicitudes_pendientes() -> list[dict]:
    """Corridas de tipo 'descarga' cuya solicitud al SAT aún no está Terminada."""
    conn = obtener_conexion()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(
            """
            SELECT id, tipo_comprobante, id_solicitud, fecha_desde, fecha_hasta, creado_en
            FROM sat_sync_runs
            WHERE tipo = 'descarga'
              AND estado_solicitud IN ('solicitada', 'en_proceso')
              AND id_solicitud IS NOT NULL
            ORDER BY creado_en ASC
            """
        )
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()


def listar_sync_runs(limite: int = 30) -> pd.DataFrame:
    conn = obtener_conexion()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(
            """
            SELECT id, tipo, tipo_comprobante, origen, usuario, fecha_desde, fecha_hasta,
                   estado_solicitud, estado, xml_nuevos, xml_actualizados, mensaje_error, creado_en
            FROM sat_sync_runs
            ORDER BY creado_en DESC
            LIMIT %s
            """,
            (int(limite),),
        )
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()
    return pd.DataFrame(rows) if rows else pd.DataFrame()
