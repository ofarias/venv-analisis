# controllers/gastos_controller.py
import pandas as pd
from typing import Optional, Dict, Any
from models.gastos_model import get_gastos_df

def cargar_gastos(fecha_desde: Optional[str], fecha_hasta: Optional[str],
                  proveedor: Optional[str], concepto: Optional[int],
                  moneda: Optional[int], estatus: Optional[str]) -> pd.DataFrame:
    df = get_gastos_df(fecha_desde, fecha_hasta, proveedor, concepto, moneda, estatus)
    if df.empty:
        return df

    # kpis básicos
    df["abs_importe_mn"] = df["IMPORTE_MN"].abs()
    return df

def kpis(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty:
        return {"gasto_total_mn": 0.0, "movimientos": 0, "proveedores": 0}
    return {
        "gasto_total_mn": float(df["IMPORTE_MN"].sum()),
        "movimientos": int(len(df)),
        "proveedores": int(df["CVE_PROV"].nunique()),
    }

def pivote_por_proveedor_mes(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    pvt = pd.pivot_table(
        df,
        index=["CVE_PROV","PROVEEDOR"],
        columns=["ANIO","MES"],
        values="IMPORTE_MN",
        aggfunc="sum",
        fill_value=0.0,
        margins=True,
        margins_name="total"
    )
    return pvt.sort_values(("total", ""), ascending=False, axis=0, key=lambda s: s) if "total" in pvt.columns.get_level_values(0) else pvt

def top_conceptos(df: pd.DataFrame, n: int=20) -> pd.DataFrame:
    if df.empty:
        return df
    g = df.groupby(["NUM_CPTO","CONCEPTO"], as_index=False)["IMPORTE_MN"].sum()
    return g.sort_values("IMPORTE_MN", ascending=False).head(n)

def outliers_iqr(df: pd.DataFrame, agrupador: str="NUM_CPTO") -> pd.DataFrame:
    if df.empty:
        return df
    # iqr por agrupador para detectar gastos atípicos
    res = []
    for key, grp in df.groupby(agrupador):
        q1 = grp["IMPORTE_MN"].quantile(0.25)
        q3 = grp["IMPORTE_MN"].quantile(0.75)
        iqr = q3 - q1
        umbral = q3 + 1.5*iqr
        anom = grp[grp["IMPORTE_MN"] > umbral].copy()
        if not anom.empty:
            anom[agrupador] = key
            anom["UMBRAL_IQR"] = umbral
            res.append(anom)
    return pd.concat(res, ignore_index=True) if res else pd.DataFrame()