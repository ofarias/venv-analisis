# controllers/ventas_controller.py
import pandas as pd
from typing import Optional, Dict, Any
from models.ventas_model import get_ventas_df

def cargar_ventas(
    fecha_desde: Optional[str],
    fecha_hasta: Optional[str],
    cliente: Optional[str],
    vendedor: Optional[int],
    moneda: Optional[int],
    status: Optional[str]
) -> pd.DataFrame:
    return get_ventas_df(fecha_desde, fecha_hasta, cliente, vendedor, moneda, status)

def kpis_ventas(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty:
        return {"ventas_mn": 0.0, "partidas": 0, "clientes": 0, "margen_pct": 0.0}
    ventas = float(df["IMPORTE_MN"].sum())
    partidas = int(len(df))
    clientes = int(df["CVE_CLPV"].nunique())
    margen_pct = float((df["UTILIDAD_MN"].sum()/ventas*100) if ventas else 0.0)
    return {"ventas_mn": ventas, "partidas": partidas, "clientes": clientes, "margen_pct": margen_pct}

def ventas_mensuales(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty: return df
    m = df.set_index("FECHA_DOC").resample("M")["IMPORTE_MN"].sum().reset_index()
    m["MES"] = m["FECHA_DOC"].dt.to_period("M").astype(str)
    return m[["MES","IMPORTE_MN"]]

def top_clientes(df: pd.DataFrame, n:int=20) -> pd.DataFrame:
    if df.empty: return df
    g = df.groupby(["CVE_CLPV","CLIENTE"], as_index=False)["IMPORTE_MN"].sum()
    return g.sort_values("IMPORTE_MN", ascending=False).head(n)

def top_productos(df: pd.DataFrame, n:int=20) -> pd.DataFrame:
    if df.empty: return df
    g = df.groupby(["CVE_ART"], as_index=False).agg(VENTAS_MN=("IMPORTE_MN","sum"), CANTIDAD=("CANTIDAD","sum"))
    return g.sort_values("VENTAS_MN", ascending=False).head(n)

def ventas_por_vendedor(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty: return df
    g = df.groupby(["CVE_VEND","VENDEDOR"], as_index=False)["IMPORTE_MN"].sum()
    return g.sort_values("IMPORTE_MN", ascending=False)