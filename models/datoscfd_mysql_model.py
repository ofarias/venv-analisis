# models/datoscfd_mysql_model.py
from __future__ import annotations

from typing import Any, Iterable, Optional
import pandas as pd

from database.conexion import obtener_conexion
import streamlit as st

def _uuid_norm_series(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.upper()


def obtener_datoscfd_mysql_df(
    *,
    fecha_desde: Optional[str] = None,
    fecha_hasta: Optional[str] = None,
    limit: Optional[int] = None,
) -> pd.DataFrame:
    """
    trae DATOSCFD completo desde mysql.
    si pasas fecha_desde/fecha_hasta filtra (si existe columna FECHA_EMISION o FECHA).
    """
    conn = obtener_conexion()
    cur = conn.cursor(dictionary=True)

    where = ["1=1"]
    params: list[Any] = []

    # como no sé el nombre exacto de fecha, probamos con FECHA_EMISION primero y luego FECHA.
    # si tu columna es otra, cámbiala aquí.
    # nota: en mysql no podemos hacer "if column exists" en sql simple,
    # así que elegimos una: FECHA_EMISION (ajústala a tu esquema real).
    col_fecha = "FECHA_EMISION"  # <-- ajusta si en tu DATOSCFD se llama distinto

    if fecha_desde:
        where.append(f"{col_fecha} >= %s")
        params.append(fecha_desde)

    if fecha_hasta:
        where.append(f"{col_fecha} <= %s")
        params.append(fecha_hasta)

    sql = f"select * from DATOSCFD where {' and '.join(where)}"
    if limit is not None:
        sql += f" limit {int(limit)}"

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