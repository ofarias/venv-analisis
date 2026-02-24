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
    paga_movimientos_con_proveedor,
)
from models.sae45_model import cargar_vista_paga_prov_cpto as _cargar_vista
from models.datoscfd_mysql_model import obtener_datoscfd_mysql_df


# ==================================================
# helpers internos para merge ada + mysql
# ==================================================
def _upper_cols(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().upper() for c in df.columns]
    return df


def _uuid_norm_series(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.upper()


def _first_existing_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    cols = {str(c).strip().upper(): c for c in df.columns}
    for name in candidates:
        key = str(name).strip().upper()
        if key in cols:
            return cols[key]
    return None


def _ensure_usocfdi(df: pd.DataFrame) -> pd.DataFrame:
    """
    asegura columna USOCFDI_ (preferida en la ui)
    mysql normalmente trae usocfdi (sin guion bajo)
    """
    df = df.copy()
    if "USOCFDI_" not in df.columns:
        c = _first_existing_col(df, ["USOCFDI", "USO_CFDI", "USO_CFDI_", "USOCFDI_"])
        if c is not None:
            df["USOCFDI_"] = df[c]
        else:
            df["USOCFDI_"] = ""
    df["USOCFDI_"] = df["USOCFDI_"].fillna("").astype(str).str.strip().str.upper()
    return df


def _ensure_tipocambio(df: pd.DataFrame) -> pd.DataFrame:
    """
    asegura TIPOCAMBIO numérico con default 1
    """
    df = df.copy()
    if "TIPOCAMBIO" not in df.columns:
        df["TIPOCAMBIO"] = 1.0
    df["TIPOCAMBIO"] = pd.to_numeric(df["TIPOCAMBIO"], errors="coerce").fillna(1.0)
    return df


def _ensure_total_mxn(df: pd.DataFrame) -> pd.DataFrame:
    """
    asegura TOTAL_MXN.
    si no existe o viene nulo, calcula TOTAL * TIPOCAMBIO
    """
    df = df.copy()

    if "TOTAL" not in df.columns and "TOTAL_MXN" not in df.columns:
        return df

    df = _ensure_tipocambio(df)

    if "TOTAL_MXN" not in df.columns:
        df["TOTAL_MXN"] = pd.NA

    tot = None
    if "TOTAL" in df.columns:
        tot = pd.to_numeric(df["TOTAL"], errors="coerce")

    mxn = pd.to_numeric(df["TOTAL_MXN"], errors="coerce")

    mask = mxn.isna()
    if tot is not None:
        df.loc[mask, "TOTAL_MXN"] = (tot[mask].fillna(0.0) * df.loc[mask, "TIPOCAMBIO"]).round(2)
    else:
        df.loc[mask, "TOTAL_MXN"] = 0.0

    return df


def unir_datoscfd_sin_duplicar_preferir_ada(df_ada: pd.DataFrame, df_mysql: pd.DataFrame) -> pd.DataFrame:
    """
    une datoscfd de ada + mysql sin duplicar por uuid.
    regla: si existe en ambos, preferir ada y completar huecos con mysql.
    agrega columna FUENTE: ADA / MYSQL / AMBOS

    nota: trabaja con columnas ya en mayúsculas.
    """
    if (df_ada is None or df_ada.empty) and (df_mysql is None or df_mysql.empty):
        return pd.DataFrame()

    df_ada = pd.DataFrame() if df_ada is None else df_ada.copy()
    df_mysql = pd.DataFrame() if df_mysql is None else df_mysql.copy()

    # normaliza uuid
    if "UUID" in df_ada.columns:
        df_ada["_UUID_NORM"] = _uuid_norm_series(df_ada["UUID"])
    else:
        df_ada["_UUID_NORM"] = ""

    if "UUID" in df_mysql.columns:
        df_mysql["_UUID_NORM"] = _uuid_norm_series(df_mysql["UUID"])
    else:
        df_mysql["_UUID_NORM"] = ""

    # quita vacíos y dupes internos
    df_ada = (
        df_ada[df_ada["_UUID_NORM"].astype(str).str.strip().ne("")]
        .drop_duplicates("_UUID_NORM", keep="first")
    )
    df_mysql = (
        df_mysql[df_mysql["_UUID_NORM"].astype(str).str.strip().ne("")]
        .drop_duplicates("_UUID_NORM", keep="first")
    )

    if df_ada.empty:
        out = df_mysql.copy()
        out["FUENTE"] = "MYSQL"
        if "UUID" not in out.columns:
            out["UUID"] = out["_UUID_NORM"]
        return out

    if df_mysql.empty:
        out = df_ada.copy()
        out["FUENTE"] = "ADA"
        if "UUID" not in out.columns:
            out["UUID"] = out["_UUID_NORM"]
        return out

    m = df_ada.merge(
        df_mysql,
        on="_UUID_NORM",
        how="outer",
        suffixes=("_ada", "_mysql"),
        indicator=True,
    )

    cols_ada = {c[:-4] for c in m.columns if c.endswith("_ada")}
    cols_mysql = {c[:-6] for c in m.columns if c.endswith("_mysql")}
    base_cols = sorted((cols_ada | cols_mysql) - {"_UUID_NORM"})

    def pick(base: str) -> pd.Series:
        c_a = f"{base}_ada"
        c_m = f"{base}_mysql"
        s_a = m[c_a] if c_a in m.columns else pd.Series([None] * len(m), index=m.index)
        s_m = m[c_m] if c_m in m.columns else pd.Series([None] * len(m), index=m.index)

        out = s_a.copy()
        try:
            mask = out.isna() | (out.astype(str).str.strip() == "")
        except Exception:
            mask = out.isna()
        out[mask] = s_m[mask]
        return out

    out = pd.DataFrame({"_UUID_NORM": m["_UUID_NORM"]})
    for c in base_cols:
        out[c] = pick(c)

    out["FUENTE"] = m["_merge"].map({"left_only": "ADA", "right_only": "MYSQL", "both": "AMBOS"})

    if "UUID" not in out.columns:
        out["UUID"] = out["_UUID_NORM"]

    return out


def preparar_docs_ada_con_mysql(
        _secrets,
        df_ada: pd.DataFrame,
        *,
        fecha_desde: str | None,
        fecha_hasta: str | None,
        limit: int | None = None,
    ) -> pd.DataFrame:
    """
    - carga mysql (DATOSCFD)
    - normaliza columnas (mayúsculas)
    - crea USOCFDI_ desde usocfdi si aplica
    - tipocambio default 1
    - une por uuid sin duplicar (preferir ada)
    - asegura total_mxn
    """
    df_ada_u = pd.DataFrame() if df_ada is None else _upper_cols(df_ada)

    # mysql
    df_mysql = pd.DataFrame()
    try:
        df_mysql = obtener_datoscfd_mysql_df(
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            limit=limit,
        )
    except Exception:
        df_mysql = pd.DataFrame()

    st.write(f"Documentos ADA: {len(df_ada_u)} | Documentos MySQL: {len(df_mysql)}")
    if df_mysql is not None and not df_mysql.empty:
        df_mysql = _upper_cols(df_mysql)
        df_mysql = _ensure_usocfdi(df_mysql)
        df_mysql = _ensure_tipocambio(df_mysql)
        df_mysql = _ensure_total_mxn(df_mysql)

    # también aseguro columnas en ada (por si ada trae null en tipocambio/usocfdi_)
    if df_ada_u is not None and not df_ada_u.empty:
        df_ada_u = _ensure_usocfdi(df_ada_u)
        df_ada_u = _ensure_tipocambio(df_ada_u)
        df_ada_u = _ensure_total_mxn(df_ada_u)

    out = unir_datoscfd_sin_duplicar_preferir_ada(df_ada_u, df_mysql)

    out = _upper_cols(out)
    out = _ensure_usocfdi(out)
    out = _ensure_tipocambio(out)
    out = _ensure_total_mxn(out)

    # debug real: cuántos quedaron como ada/mysql/ambos
    #vc = out["FUENTE"].value_counts(dropna=False) if "FUENTE" in out.columns else {}
    #st.write("fuente counts:", vc)
    #st.write(out)
    ## extra: cuántos uuid trae mysql y cuántos quedaron como mysql-only
    #if df_mysql is not None and not df_mysql.empty and "UUID" in df_mysql.columns:
    #    mysql_uuid = set(_uuid_norm_series(df_mysql["UUID"]).tolist())
    #    out_uuid = set(_uuid_norm_series(out["UUID"]).tolist()) if "UUID" in out.columns else set()
    #    st.write("uuids mysql:", len(mysql_uuid), "uuids en out:", len(out_uuid))
    #    if "FUENTE" in out.columns:
    #        st.write("mysql-only:", int((out["FUENTE"] == "MYSQL").sum()))

    return out


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


def buscar_concep_en_paga_g03(_secrets, uso_cfdi, rfc_receptor, clave_prov_sae, serie, folio, total_mxn):
    """
    wrapper seguro sobre buscar_conceptos_en_paga_g03 (la versión robusta y desconectada)
    """
    res = buscar_conceptos_en_paga_g03(
        _secrets,
        uso_cfdi,
        rfc_receptor,
        clave_prov_sae,
        serie,
        folio,
        total_mxn,
    )

    if isinstance(res, pd.DataFrame):
        return res

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
# api nueva para que el view no manipule nada
# ==================================================
@st.cache_data(ttl=60, show_spinner=False)
def cargar_documentos_con_mysql(_secrets, filtros: Dict[str, Any], page: int, page_size: int) -> pd.DataFrame:
    """
    reemplazo directo de cargar_documentos en la vista.
    - carga docs ada por filtros/paginación
    - trae mysql por rango de fechas
    - une por uuid sin duplicar (preferir ada)
    - deja usocfdi_ y tipocambio listos
    """
    offset = (page - 1) * page_size
    df_ada = buscar_documentos(_secrets, filtros, (offset, page_size))

    df_out = preparar_docs_ada_con_mysql(
        _secrets,
        df_ada,
        fecha_desde=filtros.get("fecha_desde"),
        fecha_hasta=filtros.get("fecha_hasta"),
        limit=None,
    )

    # si quieres que aquí mismo se filtre a g03 (y ya no en el view), descomenta:
    # if df_out is not None and not df_out.empty and "USOCFDI_" in df_out.columns:
    #     df_out = df_out[df_out["USOCFDI_"].astype(str).str.strip().str.upper().eq("G03")].copy()

    return df_out


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
        return (
            pd.DataFrame(columns=["CVE_PROV","NOMBRE_PROV","FACT_BASE","MASCARA","_CLUSTER","_REP_IMP","MESES","N_MESES"]),
            pd.DataFrame(columns=["CVE_PROV","NOMBRE_PROV","FACT_BASE","MASCARA","ANIO","MEDIANA_IMP","USOS","YoY_PCT"]),
        )

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
                cluster_id += 1
                current_rep = imp
            else:
                tol_abs = max(1.0, current_rep * (tol_pct/100.0))
                if abs(imp - current_rep) > tol_abs:
                    cluster_id += 1
                    current_rep = imp
            r = row.to_dict()
            r["_CLUSTER"] = cluster_id
            r["_REP_IMP"] = current_rep
            rows.append(r)
        grupos.append(pd.DataFrame(rows))
    base2 = pd.concat(grupos, ignore_index=True) if grupos else base.copy()

    repes = (
        base2.groupby(["CVE_PROV","NOMBRE_PROV","FACT_BASE","MASCARA","_CLUSTER","_REP_IMP"], as_index=False)
             .agg(
                 MESES=("MES", lambda s: sorted(set(s))),
                 N_MESES=("MES", lambda s: len(set(s))),
             )
    )
    repes = repes[repes["N_MESES"] >= int(min_meses)] \
                 .sort_values(["CVE_PROV","N_MESES","_REP_IMP"], ascending=[True, False, True])

    # mediana por año
    base2["ANIO"] = pd.to_datetime(base2["FECHA"], errors="coerce").dt.year
    anual = (
        base2.groupby(["CVE_PROV","NOMBRE_PROV","FACT_BASE","MASCARA","ANIO"], as_index=False)
             .agg(
                 MEDIANA_IMP=("IMPORTE","median"),
                 USOS=("IMPORTE","count"),
             )
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


@st.cache_data(ttl=60, show_spinner=False)
def cargar_datoscfd_mysql_df(_secrets, fecha_desde=None, fecha_hasta=None, limit=None) -> pd.DataFrame:
    # se deja por compatibilidad con tu vista actual (si aún la usa)
    return obtener_datoscfd_mysql_df(fecha_desde=fecha_desde, fecha_hasta=fecha_hasta, limit=limit)