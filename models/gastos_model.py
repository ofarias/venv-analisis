# models/gastos_model.py
import streamlit as st 
from typing import Optional, Dict, Any
import pandas as pd
from models.db import run_query, run_query_firebird  # usa tu helper existente

def get_gastos_df(fecha_desde: Optional[str]=None,
                  fecha_hasta: Optional[str]=None,
                  proveedor: Optional[str]=None,
                  concepto: Optional[int]=None,
                  moneda: Optional[int]=None,
                  estatus: Optional[str]=None) -> pd.DataFrame:
    """
    retorna gastos desde paga_m01 con catálogos unidos
    notas:
      - estatus válidos en paga_m01: 'A', 'B'
      - usa directamente paga_m01 (paga_det01 son pagos, no el gasto)
      - campos de importe/moneda pueden variar: ajusta si tu esquema difiere
    """
    where = ["1=1"]
    params = []

    if fecha_desde:
        where.append("CAST(p.FECHA_APLI AS DATE) >= CAST(? AS DATE)")
        params.append(fecha_desde)
    if fecha_hasta:
        where.append("CAST(p.FECHA_APLI AS DATE) <= CAST(? AS DATE)")
        params.append(fecha_hasta)
    if proveedor:
        where.append("p.CVE_PROV = ?")
        params.append(proveedor)
    if concepto is not None:
        where.append("p.NUM_CPTO = ?")
        params.append(int(concepto))
    if moneda is not None:
        where.append("p.NUM_MONED = ?")
        params.append(int(moneda))
    if estatus:
        where.append("p.STATUS = ?")
        params.append(estatus)

    sql = f"""
      SELECT
        p.CVE_PROV,
        pr.NOMBRE     AS PROVEEDOR,
        p.NUM_CPTO,
        c.DESCR       AS CONCEPTO,
        p.FECHA_APLI,
        p.REFER,
        p.NUM_CARGO,
        p.IMPMON_EXT       AS MONTO,
        p.IMPORTE     AS IMPORTE,
        p.NUM_MONED,
        m.DESCR       AS MONEDA,
        p.TCAMBIO     AS TCAMBIO,
        p.STATUS
      FROM PAGA_M01 p
      LEFT JOIN PROV01  pr ON pr.CLAVE    = p.CVE_PROV
      LEFT JOIN CONP01  c  ON c.NUM_CPTO  = p.NUM_CPTO
      LEFT JOIN MONED01 m  ON m.NUM_MONED = p.NUM_MONED
      WHERE {" AND ".join(where)} 
      AND p.NUM_CPTO != 1
      ORDER BY p.NUM_CPTO
    """
    
    rows = run_query_firebird("FIREBIRD_BIO_SAE", sql, params)

    if not rows:
        return pd.DataFrame()

    if isinstance(rows[0], dict):
        df = pd.DataFrame(rows)
    else:
        cols = [
            "CVE_PROV","PROVEEDOR","NUM_CPTO","CONCEPTO","FECHA_APLI",
            "REFER","NUM_CARGO","IMPORTE","NUM_MONED","MONEDA","TCAMBIO","STATUS"
        ]
    
        df = pd.DataFrame(rows, columns=cols)

    # normalizaciones
    df["FECHA_APLI"] = pd.to_datetime(df["FECHA_APLI"], errors="coerce")
    df["IMPORTE"] = pd.to_numeric(df["IMPORTE"], errors="coerce").fillna(0.0)
    df["TCAMBIO"] = pd.to_numeric(df["TCAMBIO"], errors="coerce").fillna(1.0)
    # monto en mn: si num_moned==1 ya es mn; si no, convierte por tipo de cambio
    df["IMPORTE_MN"] = df.apply(lambda r: r["MONTO"] if int(r.get("NUM_MONED",1))==1 else r["MONTO"]*r["TCAMBIO"], axis=1)
    df["ANIO"] = df["FECHA_APLI"].dt.year
    df["MES"]  = df["FECHA_APLI"].dt.month
    df["IMPORTE_MN"] = pd.to_numeric(df["IMPORTE_MN"], errors="coerce").fillna(0.0)

    return df