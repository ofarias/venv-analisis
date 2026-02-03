# controllers/ada_controller.py
from __future__ import annotations
import re
from typing import Dict, Any, Optional, Tuple
import streamlit as st
import pandas as pd
# --------- MODELOS (MVC): solo llamadas -----------
from models.ada_model import buscar_documentos, contar_documentos, obtener_tipos_distintos
from models.sae45_model import (
    buscar_documento_en_sae,
    insertar_en_sae_por_uso_cfdi,
    obtener_proveedores_activos,
    buscar_en_paga_m01_g03,
    buscar_conceptos_en_paga_g03,
    snapshot_paga_m01,
    snapshot_compc01,
    snapshot_paga_por_fecha,
    snapshot_compc_por_fecha,
    paga_movimientos_con_proveedor,  # si lo usas en tu UI
    
)
from models.sae45_model import cargar_vista_paga_prov_cpto as _cargar_vista


# ==================================================
# Wrappers cacheados (sin tocar la base de datos aquí)
# ==================================================
@st.cache_data(ttl=60, show_spinner=False)
def cargar_tipos(_secrets):
    return obtener_tipos_distintos(_secrets)

@st.cache_data(ttl=60, show_spinner=False)
def cargar_documentos(_secrets, filtros: Dict[str, Any], page: int, page_size: int) -> pd.DataFrame:
    offset = (page - 1) * page_size
    return buscar_documentos(_secrets, filtros, (offset, page_size))

@st.cache_data(ttl=60, show_spinner=False)
def contar_documentos_cached(_secrets, filtros: Dict[str, Any]) -> int:
    return contar_documentos(_secrets, filtros)

def exportar_excel(df: pd.DataFrame) -> bytes:
    import io
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="documentos")
    return output.getvalue()

@st.cache_data(ttl=30, show_spinner=False)
def verificar_en_sae(_secrets, rfc_emisor, serie, folio, uuid, total, fecha_emision):
    return buscar_documento_en_sae(_secrets, rfc_emisor, serie, folio, uuid, total, fecha_emision)

@st.cache_data(ttl=1, show_spinner=False)  # acción: ttl mínimo
def insertar_en_sae(_secrets, rfc_emisor, serie, folio, uuid, total, tipocambio, fecha_emision, uso_cfdi):
    return insertar_en_sae_por_uso_cfdi(
        _secrets, rfc_emisor, serie, folio, uuid, total, tipocambio, fecha_emision, uso_cfdi
    )

@st.cache_data(ttl=300, show_spinner=False)
def cargar_proveedores_activos(_secrets) -> dict[str, str]:
    return obtener_proveedores_activos(_secrets)

@st.cache_data(ttl=15, show_spinner=False)
def buscar_en_paga_g03(_secrets, uso_cfdi, rfc_receptor, clave_prov_sae, serie, folio, total_mxn):
    return buscar_en_paga_m01_g03(_secrets, uso_cfdi, rfc_receptor, clave_prov_sae, serie, folio, total_mxn)

#def buscar_en_paga_g03(_secrets, uso_cfdi, rfc_receptor, clave_prov_sae, serie, folio, total_mxn):
#    """
#    wrapper seguro sobre buscar_en_paga_m01_g03:
#    - no usa cache (para no guardar objetos de cursor)
#    - convierte el resultado a algo desacoplado de la conexión (dataframe o lista de dicts)
#    """
#    res = buscar_en_paga_m01_g03(
#        _secrets,
#        uso_cfdi,
#        rfc_receptor,
#        clave_prov_sae,
#        serie,
#        folio,
#        total_mxn,
#    )
#    # si el modelo ya devuelve dataframe, lo regresamos tal cual
#    if isinstance(res, pd.DataFrame):
#        return res
#    # si devuelve lista/tupla de dicts/tuplas
#    if isinstance(res, (list, tuple)):
#        # si son dicts, dataframe directo; si son tuplas, también, pero las columnas
#        # dependerán de cómo las construyas en el model
#        return pd.DataFrame(res)
#    # si es un cursor o iterador, lo forzamos a lista y lo convertimos
#    try:
#        rows = list(res)
#    except Exception:
#        # si no se puede iterar, regresamos df vacío
#        return pd.DataFrame()
#    return pd.DataFrame(rows)

def buscar_concep_en_paga_g03(_secrets, uso_cfdi, rfc_receptor, clave_prov_sae, serie, folio, total_mxn):
    """
    wrapper seguro sobre buscar_conceptos_en_paga_g03 (la versión robusta y desconectada)
    """
    # LLAMAR a la nueva función en el model
    res = buscar_conceptos_en_paga_g03(
        _secrets,
        uso_cfdi,
        rfc_receptor,
        clave_prov_sae,
        serie,
        folio,
        total_mxn,
    )

    # Dado que buscar_conceptos_en_paga_g03 ahora devuelve directamente un DataFrame
    # con los datos desconectados de la base de datos, ya no necesitamos la lógica
    # compleja de manejo de cursores en el controller.

    # 1. Si el modelo devuelve DataFrame (lo que debería hacer la nueva función), lo regresamos.
    if isinstance(res, pd.DataFrame):
        return res

    # 2. En caso contrario (por si el modelo falló y regresó None/otro), regresamos vacío.
    return pd.DataFrame()

@st.cache_data(ttl=60, show_spinner=False)
def cargar_snapshot_paga(_secrets, cves, refers, f_ini=None, f_fin=None):
    return snapshot_paga_m01(_secrets, cves, refers, f_ini, f_fin)

@st.cache_data(ttl=60, show_spinner=False)
def cargar_snapshot_compc(_secrets, cves, refers, f_ini=None, f_fin=None):
    return snapshot_compc01(_secrets, cves, refers, f_ini, f_fin)

@st.cache_data(ttl=60, show_spinner=False)
def cargar_paga_por_fecha(_secrets, f_ini, f_fin):
    return snapshot_paga_por_fecha(_secrets, f_ini, f_fin)

@st.cache_data(ttl=60, show_spinner=False)
def cargar_compc_por_fecha(_secrets, f_ini, f_fin):
    return snapshot_compc_por_fecha(_secrets, f_ini, f_fin)


# ==================================================
# Utilidades para patrones (sin DB, sólo pandas)
# ==================================================
def _series_or_empty(df: pd.DataFrame, name: str, default=""):
    """Devuelve df[name] si existe; si 'default' es str → Series llena de ese str,
       si es callable → lo evalúa y devuelve su Series."""
    if name in df.columns:
        return df[name]
    if callable(default):
        return default()
    return pd.Series([default] * len(df), index=df.index)

def _preparar_df_paga_para_patrones(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    Espera columnas (según tu model):
      CVE_PROV, NOMBRE_PROV, NO_FACTURA, DOCTO, REFER, FECHA_APLI, IMPORTE
    Devuelve columnas: CVE_PROV, NOMBRE_PROV, IMPORTE, FECHA, MES, FACT_BASE, MASCARA
    """
    if df_raw is None or df_raw.empty:
        return pd.DataFrame(columns=["CVE_PROV","NOMBRE_PROV","IMPORTE","FECHA","MES","FACT_BASE","MASCARA"])

    df = df_raw.copy()

    # normaliza clave y nombre
    df["CVE_PROV"] = df["CVE_PROV"].astype(str).str.strip().str.rjust(10).str[-10:]
    if "NOMBRE_PROV" not in df.columns:
        df["NOMBRE_PROV"] = ""

    # importe numérico
    df["IMPORTE"] = pd.to_numeric(df["IMPORTE"], errors="coerce").fillna(0.0).round(2)

    # fecha → mes
    f = pd.to_datetime(df.get("FECHA_APLI"), errors="coerce")
    df["FECHA"] = f.dt.date
    df["MES"]   = f.dt.to_period("M").astype(str)

    # FACT_BASE: prioridad NO_FACTURA → DOCTO → REFER
    s_no = _series_or_empty(df, "NO_FACTURA").fillna("").astype(str)
    s_do = _series_or_empty(df, "DOCTO").fillna("").astype(str)
    s_rf = _series_or_empty(df, "REFER").fillna("").astype(str)
    fact = s_no.where(s_no.ne(""), s_do)
    fact = fact.where(fact.ne(""), s_rf)
    df["FACT_BASE"] = fact.str.upper().str.slice(0, 40)

    # MASCARA: dígitos → 9 para detectar patrones tipo “CO3E3” → “CO9E9”
    df["MASCARA"] = df["FACT_BASE"].map(lambda x: re.sub(r"\d", "9", x or ""))

    cols = ["CVE_PROV","NOMBRE_PROV","IMPORTE","FECHA","MES","FACT_BASE","MASCARA"]
    return df[cols]

def _detectar_patrones(prep: pd.DataFrame, tol_pct: float = 2.0, min_meses: int = 6
                      ) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    repes: patrones mensuales repetidos (>= min_meses)
    anual: mediana por año y % variación YoY
    """
    if prep is None or prep.empty:
        return (pd.DataFrame(columns=["CVE_PROV","NOMBRE_PROV","FACT_BASE","MASCARA","_CLUSTER","_REP_IMP","MESES","N_MESES"]),
                pd.DataFrame(columns=["CVE_PROV","NOMBRE_PROV","FACT_BASE","MASCARA","ANIO","MEDIANA_IMP","USOS","YoY_PCT"]))

    base = prep.copy()
    # clusteriza importes por FACT_BASE dentro de proveedor, con tolerancia
    grupos = []
    for (prov, fact), g in base.groupby(["CVE_PROV","FACT_BASE"], sort=False):
        g = g.sort_values(["IMPORTE","MES"])
        cluster_id = 0
        current_rep = None
        rows = []
        for _, row in g.iterrows():
            imp = float(row["IMPORTE"])
            if current_rep is None:
                cluster_id += 1; current_rep = imp
            else:
                tol_abs = max(1.0, current_rep * (tol_pct/100.0))
                if abs(imp - current_rep) > tol_abs:
                    cluster_id += 1; current_rep = imp
            r = row.to_dict()
            r["_CLUSTER"] = cluster_id
            r["_REP_IMP"] = current_rep
            rows.append(r)
        grupos.append(pd.DataFrame(rows))
    base2 = pd.concat(grupos, ignore_index=True) if grupos else base.copy()

    repes = (
        base2.groupby(["CVE_PROV","NOMBRE_PROV","FACT_BASE","MASCARA","_CLUSTER","_REP_IMP"], as_index=False)
             .agg(MESES=("MES", lambda s: sorted(set(s))),
                  N_MESES=("MES", lambda s: len(set(s))))
    )
    repes = repes[repes["N_MESES"] >= int(min_meses)] \
                 .sort_values(["CVE_PROV","N_MESES","_REP_IMP"], ascending=[True, False, True])

    # mediana por año
    base2["ANIO"] = pd.to_datetime(base2["FECHA"], errors="coerce").dt.year
    anual = (
        base2.groupby(["CVE_PROV","NOMBRE_PROV","FACT_BASE","MASCARA","ANIO"], as_index=False)
             .agg(MEDIANA_IMP=("IMPORTE","median"),
                  USOS=("IMPORTE","count"))
             .sort_values(["CVE_PROV","FACT_BASE","ANIO"])
    )
    # variación YoY
    anual = (
        anual.groupby(["CVE_PROV","FACT_BASE"], group_keys=False)
             .apply(lambda g: g.assign(YoY_PCT=g["MEDIANA_IMP"].pct_change()*100.0))
             .reset_index(drop=True)
    )
    return repes, anual

# ---------- API para la vista ----------
@st.cache_data(ttl=120, show_spinner=False)
def cargar_paga_para_patrones(_secrets, f_ini, f_fin) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """1) trae PAGA_M01 con nombre de proveedor (ya lo hace tu model),
       2) prepara columnas para patrones,
       3) detecta patrones y año/año."""
    df_raw = paga_movimientos_con_proveedor(_secrets, f_ini=f_ini, f_fin=f_fin)
    prep = _preparar_df_paga_para_patrones(df_raw)
    repes, anual = _detectar_patrones(prep, tol_pct=2.0, min_meses=6)
    return df_raw, prep, repes, anual




@st.cache_data(ttl=60, show_spinner=False)
def cargar_vista_paga_prov_cpto(_secrets, f_ini=None, f_fin=None):
    """Interfaz cacheada hacia la vista unificada de PAGA+PROV+CONP"""
    return _cargar_vista(_secrets, f_ini, f_fin)

@st.cache_data(ttl=60, show_spinner=False)
def cargar_conceptos_por_documento(_secrets, id_docto_dig: int) -> pd.DataFrame:
    """Carga los conceptos (detalles) de un documento fiscal de ADA."""
    from models.ada_model import obtener_conceptos_por_documento
    return obtener_conceptos_por_documento(_secrets, id_docto_dig)

@st.cache_data(ttl=60, show_spinner=False)
def cargar_conceptos_filtrados(_secrets, proveedor=None, meses=None, anio=None):
    """Carga los conceptos fiscales filtrados por proveedor, meses y año."""
    from models.ada_model import obtener_conceptos_filtrados
    return obtener_conceptos_filtrados(_secrets, proveedor, meses, anio)