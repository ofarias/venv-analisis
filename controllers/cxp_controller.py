# controllers/cxp_controller.py
import pandas as pd
from typing import Optional, Dict, Any, List
from models.cxp_model import opciones_proveedores_dinamico_por_fecha, obtener_cxp_sae_basico
from models.cxp_model import (
    obtener_cxp_sae_con_nombres,
    opciones_proveedores_por_fecha_apli,
    etl_cxp_a_mysql_y_cruzar
)

def get_cxp_basico_df(cve_prov: Optional[str], fecha_desde: Optional[str], fecha_hasta: Optional[str]) -> pd.DataFrame:
    rows = obtener_cxp_sae_basico(cve_prov=cve_prov, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta)
    return pd.DataFrame(rows)

def get_opciones_proveedores_dinamico_df(fecha_desde: Optional[str], fecha_hasta: Optional[str]) -> pd.DataFrame:
    return pd.DataFrame(opciones_proveedores_dinamico_por_fecha(fecha_desde, fecha_hasta))

def get_cxp_basico_df(cve_prov: Optional[str], fecha_desde: Optional[str], fecha_hasta: Optional[str]) -> pd.DataFrame:
    rows = obtener_cxp_sae_basico(cve_prov=cve_prov, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta)
    return pd.DataFrame(rows)

def get_cxp_con_nombres_df(cve_provs: Optional[List[str]], fecha_desde: Optional[str], fecha_hasta: Optional[str]) -> pd.DataFrame:
    rows = obtener_cxp_sae_con_nombres(cve_provs=cve_provs, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta)
    return pd.DataFrame(rows)

def get_proveedores_dinamico_apli_df(fecha_desde: Optional[str], fecha_hasta: Optional[str]) -> pd.DataFrame:
    return pd.DataFrame(opciones_proveedores_por_fecha_apli(fecha_desde, fecha_hasta))

def run_etl_cxp_cruce(fecha_desde: str, fecha_hasta: str) -> Dict[str, pd.DataFrame]:
    """
    Ejecuta el ETL FB -> MySQL y devuelve DataFrames listos para la vista:
    - resumen_df: con_poliza, sin_poliza, total
    - ranking_df: ranking por proveedor
    - detalle_df: documentos detalle con indicador tiene_poliza
    """
    res = etl_cxp_a_mysql_y_cruzar(fecha_desde, fecha_hasta)

    detalle_df = pd.DataFrame(res.get("detalle", []))
    resumen_df = pd.DataFrame(res.get("resumen", []))
    ranking_df = pd.DataFrame(res.get("ranking", []))

    # columnas en minúsculas por consistencia
    if not detalle_df.empty:
        detalle_df.columns = [c.lower() for c in detalle_df.columns]
        # normaliza tipos
        if "importe" in detalle_df.columns:
            detalle_df["importe"] = pd.to_numeric(detalle_df["importe"], errors="coerce").fillna(0)
        if "tiene_poliza" in detalle_df.columns:
            detalle_df["tiene_poliza"] = detalle_df["tiene_poliza"].astype(int)

    if not resumen_df.empty:
        resumen_df.columns = [c.lower() for c in resumen_df.columns]
        for c in ["con_poliza", "sin_poliza", "total_docs"]:
            if c in resumen_df.columns:
                resumen_df[c] = pd.to_numeric(resumen_df[c], errors="coerce").fillna(0).astype(int)

    if not ranking_df.empty:
        ranking_df.columns = [c.lower() for c in ranking_df.columns]
        for c in ["docs_total", "docs_sin_poliza", "pct_sin_poliza"]:
            if c in ranking_df.columns:
                ranking_df[c] = pd.to_numeric(ranking_df[c], errors="coerce").fillna(0)

    return {
        "detalle_df": detalle_df,
        "resumen_df": resumen_df,
        "ranking_df": ranking_df,
    }