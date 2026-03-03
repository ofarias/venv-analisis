# models/datoscfd_mysql_model.py
from __future__ import annotations

from typing import Any, Iterable, Optional
import pandas as pd

from database.conexion import obtener_conexion
import streamlit as st

def _uuid_norm_series(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.upper()


def obtener_datoscfd_mysql_df(
        filtros: dict | None = None,
    ) -> pd.DataFrame:

    filtros = filtros or {}

    conn = obtener_conexion()
    cur = conn.cursor(dictionary=True)

    where = []
    params = []

    # FECHA_DESDE
    if filtros.get("fecha_desde"):
        where.append("FECHA_EMISION >= %s")
        params.append(filtros["fecha_desde"])

    # FECHA_HASTA (mismo comportamiento que firebird)
    if filtros.get("fecha_hasta"):
        where.append("FECHA_EMISION < DATE_ADD(%s, INTERVAL 1 DAY)")
        params.append(filtros["fecha_hasta"])

    # RFC_EMISOR
    if filtros.get("rfc_emisor"):
        where.append("UPPER(RFC_EMISOR) LIKE CONCAT('%%', UPPER(%s), '%%')")
        params.append(filtros["rfc_emisor"][:13])

    # NOMBRE_EMISOR
    if filtros.get("nombre_emisor"):
        where.append("UPPER(NOMBRE_EMISOR) LIKE CONCAT('%%', UPPER(%s), '%%')")
        params.append(filtros["nombre_emisor"][:120])

    # FOLIO
    if filtros.get("folio"):
        where.append("FOLIO LIKE CONCAT('%%', %s, '%%')")
        params.append(filtros["folio"][:20])

    # TIPO
    if filtros.get("tipo"):
        where.append("UPPER(TIPOCOMPROBANTE) = UPPER(%s)")
        params.append(filtros["tipo"][:20])

    # RFC_RECEPTOR
    if filtros.get("rfc_receptor"):
        where.append("UPPER(RFC_RECEPTOR) LIKE CONCAT('%%', UPPER(%s), '%%')")
        params.append(filtros["rfc_receptor"][:13])

    # TOTAL > 0
    where.append("TOTAL > 0")

    where_sql = ""
    if where:
        where_sql = "WHERE " + " AND ".join(where)

    sql = f"""
        SELECT
            ID_DOCTODIG,
            FECHA_EMISION,
            UUID,
            TIPOCOMPROBANTE,
            SERIE,
            FOLIO,
            RFC_EMISOR,
            NOMBRE_EMISOR,
            RFC_RECEPTOR,
            NOMBRE_RECEPTOR,
            MONEDA,
            TIPOCAMBIO,
            TOTAL,
            TOTAL * TIPOCAMBIO AS TOTAL_MXN,
            ESTADO_SAT,
            ESTADO_CFD,
            FECHA_TIMBRADO,
            FECHA_CANCELACION,
            CONCAT(usocfdi_, ' - ', USOCFDI) AS uso_cfdi,
            usocfdi_,
            CONCAT(metodopago_, ' - ', METODOPAGO) AS metodo_pago,
            CONCAT(formapago_, ' - ', FORMAPAGO) AS forma_pago
        FROM DATOSCFD
        {where_sql}
        ORDER BY FECHA_EMISION DESC, ID_DOCTODIG DESC
    """

    cur.execute(sql, tuple(params))
    rows = cur.fetchall()

    cur.close()
    conn.close()

    df = pd.DataFrame(rows) if rows else pd.DataFrame()

    if not df.empty and "UUID" in df.columns:
        df["_UUID_NORM"] = df["UUID"].astype(str).str.strip().str.upper()
    else:
        df["_UUID_NORM"] = ""

    return df


def obtener_detalle_datoscfd_mysql_df(
    id_docto_dig:int,
    uuid: Optional[str] = None,
    ) -> pd.DataFrame:
    """
    trae DATOSCFD completo desde mysql.
    si pasas fecha_desde/fecha_hasta filtra (si existe columna FECHA_EMISION o FECHA).
    """
    #st.write(f"obtener_detalle_datoscfd_mysql_df llamado con id_docto_dig={id_docto_dig}, uuid={uuid}")
    id_docto_dig = int(id_docto_dig)
    conn = obtener_conexion()
    cur = conn.cursor(dictionary=True)
    params: list[Any] = []
    sql = f"select * from DATOSCFD where id_doctodig = %s and uuid = %s"
    params.append(id_docto_dig)
    params.append(uuid)
    #st.write(f"Ejecutando SQL: {sql} con params {params}")

    cur.execute(sql, tuple(params))
    rows = cur.fetchall()

    cur.close()
    conn.close()

    df = pd.DataFrame(rows) if rows else pd.DataFrame()
    #st.write(f"Datos CFD desde MySQL: {df} registros obtenidos.")
    #st.write(df)

    if not df.empty and "UUID" in df.columns:
        df["_UUID_NORM"] = _uuid_norm_series(df["UUID"])
    else:
        df["_UUID_NORM"] = ""

    return df