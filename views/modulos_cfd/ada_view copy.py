# views/ada_view.py
import streamlit as st
from datetime import date, timedelta
import pandas as pd
import matplotlib.pyplot as plt
from models.sae_model import insertar_en_sae_por_uso, _conn_sae_from_secrets
import re
from controllers.ada_controller import (
    cargar_tipos,
    cargar_documentos,
    contar_documentos_cached,
    exportar_excel,
    cargar_proveedores_activos,
    cargar_paga_por_fecha,     # snapshots SAE por rango de fechas
    cargar_compc_por_fecha,    # snapshots SAE por rango de fechas
)

# ---------------------------
# Helpers
# ---------------------------
def _default_dates():
    hoy = date.today()
    first_this = hoy.replace(day=1)
    last_prev = first_this - timedelta(days=1)
    first_prev = last_prev.replace(day=1)
    return first_prev, hoy

def _norm_rfc(x: str) -> str:
    return (str(x) if x is not None else "").strip().upper()[:13]

def _cve_match(clave: str | None) -> str:
    base = (clave or "").strip() or "0001"
    return base.rjust(10)[:10]

def _to_num_2(x):
    try:
        return round(float(str(x).replace(",", "").replace("$", "")), 2)
    except Exception:
        return 0.0

def _first_series(dframe: pd.DataFrame, candidates):
    for c in candidates:
        if c in dframe.columns:
            return dframe[c]
    return pd.Series(index=dframe.index, dtype="object")

# ---------------------------
# Vista principal
# ---------------------------
def pantalla_documentos_ada():
    st.subheader("documentos fiscales (ada)")

    # --- defaults pedidos ---
    fdef_desde, fdef_hasta = _default_dates()

    col_f1, col_f2, col_rfc, col_nom, col_folio, col_tipo, col_rfc_rec = st.columns([1,1,1,1,1,1,1])
    with col_f1:
        f_desde = st.date_input("desde", value=fdef_desde, format="YYYY-MM-DD")
    with col_f2:
        f_hasta = st.date_input("hasta", value=fdef_hasta, format="YYYY-MM-DD")
    with col_rfc:
        rfc = st.text_input("rfc emisor", value="")
    with col_nom:
        nombre = st.text_input("nombre emisor", value="")
    with col_folio:
        folio = st.text_input("folio", value="")
    with col_rfc_rec:
        rfc_rec = st.text_input("rfc receptor", value="BIO870307QD0")

    tipos = ["(todos)"]
    try:
        tipos += cargar_tipos(st.secrets)
    except Exception as e:
        st.warning(f"no se pudieron cargar tipos: {e}")
    idx_tipo = tipos.index("Ingreso") if "Ingreso" in tipos else 0
    with col_tipo:
        tipo = st.selectbox("tipo", tipos, index=idx_tipo)

    filtros = {
        "fecha_desde": str(f_desde) if f_desde else None,
        "fecha_hasta": str(f_hasta) if f_hasta else None,
        "rfc_emisor": rfc.strip() or None,
        "nombre_emisor": nombre.strip() or None,
        "folio": folio.strip() or None,
        "tipo": None if tipo == "(todos)" else tipo,
        "rfc_receptor": rfc_rec.strip() or None,
    }

    # contar
    try:
        total = contar_documentos_cached(st.secrets, filtros)
    except Exception as e:
        st.error(f"error al contar documentos: {e}")
        return
    st.caption(f"total: {total}")

    # paginación (default: Todas)
    c1, c2, c3 = st.columns([1,1,2])
    with c1:
        page_size_opt = st.selectbox("tamaño página", [200, 500, 1000, "Todas"], index=3)
    with c2:
        page = st.number_input("página", min_value=1, value=1, step=1, disabled=(page_size_opt == "Todas"))
    with c3:
        if st.button("buscar", use_container_width=True, key="btn_buscar"):
            st.cache_data.clear()

    page_size = total if page_size_opt == "Todas" else int(page_size_opt)

    # cargar ADA
    try:
        df = cargar_documentos(st.secrets, filtros, page, page_size)
    except Exception as e:
        st.error(f"error al cargar documentos: {e}")
        return

    if df.empty:
        st.info("sin resultados con los filtros actuales")
        return

    # formateo visible
    if "TOTAL" in df.columns:
        df["TOTAL"] = df["TOTAL"].map(lambda x: f"{x:,.2f}")
    if "TOTAL_MXN" in df.columns:
        df["TOTAL_MXN"] = df["TOTAL_MXN"].map(lambda x: f"{x:,.2f}")

    # RFC → CLAVE_PROV_SAE (activos) y marcado rojo
    try:
        prov_activos = cargar_proveedores_activos(st.secrets)  # {RFC: CLAVE}
    except Exception as e:
        prov_activos = {}
        st.warning(f"No se pudieron cargar proveedores activos de SAE: {e}")

    df["RFC_NORM"] = df["RFC_EMISOR"].apply(_norm_rfc) if "RFC_EMISOR" in df.columns else ""
    df["CLAVE_PROV_SAE"] = df["RFC_NORM"].map(prov_activos).fillna("")

    # llaves de comparación ADA
    df["REFER_MATCH"] = (
        df["SERIE"].fillna("").astype(str).str.strip() +
        df["FOLIO"].fillna("").astype(str).str.strip()
    ).str.upper().str.slice(0, 20)
    df["CVE_PROV_MATCH"] = df.get("CLAVE_PROV_SAE", "").apply(_cve_match)

    uso_series = _first_series(df, ["uso_cfdi", "USO_CFDI", "USOCFDI"]).fillna("").astype(str)
    df["DESTINO_SAE"] = uso_series.str.upper().map(
        lambda u: "COMPC01" if u.startswith("G01") else ("PAGA_M01" if u.startswith("G03") else "")
    )

    # valores numéricos/fecha ADA para match 2B
    df["_FECHA_ADA"] = pd.to_datetime(df["FECHA_EMISION"], errors="coerce").dt.date
    df["_IMP_MXN_NUM"] = pd.to_numeric(
        df["TOTAL_MXN"].astype(str).str.replace(",", "").str.replace("$", ""),
        errors="coerce"
    ).fillna(0.0).round(2)
    # referencias alternativas ADA
    df["_REF_ADA_1"] = df["REFER_MATCH"]
    df["_REF_ADA_2"] = df["FOLIO"].fillna("").astype(str).str.strip().str.upper()
    
    # ← NUEVO: llaves ADA para match por APP
    df["_UUID_ADA"] = df.get("UUID", "").astype(str).str.upper()
    df["_ADA_DOC"]  = df.get("ID_DOCTODIG", "").astype(str)

    # snapshots SAE por fecha (todo en rango)
    f_ini = pd.to_datetime(filtros.get("fecha_desde")).date() if filtros.get("fecha_desde") else None
    f_fin = pd.to_datetime(filtros.get("fecha_hasta")).date() if filtros.get("fecha_hasta") else None
    paga_raw = cargar_paga_por_fecha(st.secrets, f_ini, f_fin)
    compc_raw = cargar_compc_por_fecha(st.secrets, f_ini, f_fin)

    # ---------------------------
    # Normalización robusta SAE
    # Estandarizamos SIEMPRE a:
    # ['CVE_PROV','REFER','_NO_FACTURA','_DOCTO','_IMP_SAE','_FECHA_SAE','_FUENTE']
    # ---------------------------
    
    def norm_paga(dfp: pd.DataFrame) -> pd.DataFrame:

        if dfp is None or dfp.empty:
            return pd.DataFrame(columns=[
                "CVE_PROV","REFER","_NO_FACTURA","_DOCTO","_IMP_SAE","_FECHA_SAE","_FUENTE",
                "_APP_UUID","_APP_ADA_DOC"
            ])

        out = pd.DataFrame(index=dfp.index)

        out["CVE_PROV"] = dfp["CVE_PROV"].astype(str).str.rjust(10).str.slice(0,10)

        # REFER
        if "REFER" in dfp.columns:
            out["REFER"] = dfp["REFER"].astype(str).str.upper().str.slice(0,20)
        else:
            out["REFER"] = pd.Series([""]*len(dfp), index=dfp.index, dtype="object")

        # NO_FACTURA / DOCTO
        if "NO_FACTURA" in dfp.columns:
            out["_NO_FACTURA"] = dfp["NO_FACTURA"].astype(str).str.upper()
        else:
            out["_NO_FACTURA"] = pd.Series([""]*len(dfp), index=dfp.index, dtype="object")

        if "DOCTO" in dfp.columns:
            out["_DOCTO"] = dfp["DOCTO"].astype(str).str.upper()
        else:
            out["_DOCTO"] = pd.Series([""]*len(dfp), index=dfp.index, dtype="object")

        # importe / fecha
        out["_IMP_SAE"]   = pd.to_numeric(dfp["IMPORTE"], errors="coerce").fillna(0).round(2) if "IMPORTE" in dfp.columns else 0.0
        if "FECHA_APLI" in dfp.columns:
            out["_FECHA_SAE"] = pd.to_datetime(dfp["FECHA_APLI"], errors="coerce").dt.date
        elif "FECHA" in dfp.columns:
            out["_FECHA_SAE"] = pd.to_datetime(dfp["FECHA"], errors="coerce").dt.date
        else:
            out["_FECHA_SAE"] = pd.NaT

        out["_FUENTE"] = "PAGA_M01"

        # Campos de app
        if "APP_UUID" in dfp.columns:
            out["_APP_UUID"] = dfp["APP_UUID"].astype(str).str.upper()
        else:
            out["_APP_UUID"] = pd.Series([""]*len(dfp), index=dfp.index, dtype="object")

        # Acepta APP_ADA_CFD_DOC o APP_ADA_DOC
        if "APP_ADA_CFD_DOC" in dfp.columns:
            out["_APP_ADA_DOC"] = dfp["APP_ADA_CFD_DOC"].astype(str)
        elif "APP_ADA_DOC" in dfp.columns:
            out["_APP_ADA_DOC"] = dfp["APP_ADA_DOC"].astype(str)
        else:
            out["_APP_ADA_DOC"] = pd.Series([""]*len(dfp), index=dfp.index, dtype="object")

        return out


    def norm_compc(dfc: pd.DataFrame) -> pd.DataFrame:
        import pandas as pd

        if dfc is None or dfc.empty:
            return pd.DataFrame(columns=[
                "CVE_PROV","REFER","_NO_FACTURA","_DOCTO","_IMP_SAE","_FECHA_SAE","_FUENTE",
                "_APP_UUID","_APP_ADA_DOC"
            ])

        out = pd.DataFrame(index=dfc.index)
        out["CVE_PROV"] = dfc.get("CVE_PROV", dfc.get("CVE_CLPV", "")).astype(str).str.rjust(10).str.slice(0,10)

        if "REFER" in dfc.columns:
            out["REFER"] = dfc["REFER"].astype(str).str.upper().str.slice(0,20)
        elif "SU_REFER" in dfc.columns:
            out["REFER"] = dfc["SU_REFER"].astype(str).str.upper().str.slice(0,20)
        else:
            out["REFER"] = pd.Series([""]*len(dfc), index=dfc.index, dtype="object")

        out["_NO_FACTURA"] = pd.Series([""]*len(dfc), index=dfc.index, dtype="object")
        out["_DOCTO"]      = pd.Series([""]*len(dfc), index=dfc.index, dtype="object")

        out["_IMP_SAE"]   = pd.to_numeric(dfc["IMPORTE"], errors="coerce").fillna(0).round(2) if "IMPORTE" in dfc.columns else 0.0
        if "FECHA_DOC" in dfc.columns:
            out["_FECHA_SAE"] = pd.to_datetime(dfc["FECHA_DOC"], errors="coerce").dt.date
        elif "FECHA" in dfc.columns:
            out["_FECHA_SAE"] = pd.to_datetime(dfc["FECHA"], errors="coerce").dt.date
        else:
            out["_FECHA_SAE"] = pd.NaT

        out["_FUENTE"]      = "COMPC01"
        out["_APP_UUID"]    = pd.Series([""]*len(dfc), index=dfc.index, dtype="object")
        out["_APP_ADA_DOC"] = pd.Series([""]*len(dfc), index=dfc.index, dtype="object")

        return out
        
    
    paga_all = norm_paga(paga_raw)
    compc_all = norm_compc(compc_raw)
    sae_union = pd.concat([paga_all, compc_all], ignore_index=True)

    # ---------------------------
    # MATCH 1: CVE_PROV + REFER (exacto)
    # ---------------------------
    m1 = df.merge(
        sae_union[["CVE_PROV","REFER","_FUENTE"]],
        left_on=["CVE_PROV_MATCH","REFER_MATCH"],
        right_on=["CVE_PROV","REFER"],
        how="left",
        suffixes=("","_sae1"),
        indicator=False,
    )
    m1["_EN_SAE_REF"] = m1["_FUENTE"].notna()
    m1["_FUENTE_REF"] = m1["_FUENTE"]
    # limpiamos columnas de la unión para no estorbar luego
    m1.drop(columns=["CVE_PROV","REFER","_FUENTE"], inplace=True)

    # ---------------------------
    # MATCH 2A: CVE_PROV + (NO_FACTURA/DOCTO) vs (REFER_MATCH o FOLIO)
    #           (aplica valores de PAGA_M01 y también de COMPC si existieran)
    # ---------------------------
    sae_alt = sae_union.copy()
    sae_alt["_ALT_REF_SAE"] = sae_alt["_NO_FACTURA"].where(
        sae_alt["_NO_FACTURA"].ne(""), sae_alt["_DOCTO"]
    ).fillna("").astype(str).str.upper()

    # duplicamos filas ADA manteniendo el índice original
    ada_alt = pd.concat([
        m1.assign(_REF_ADA_CAND=m1["_REF_ADA_1"]),
        m1.assign(_REF_ADA_CAND=m1["_REF_ADA_2"])
    ], ignore_index=False)

    m2a = ada_alt.merge(
        sae_alt[["CVE_PROV","_ALT_REF_SAE","_FUENTE"]],
        left_on=["CVE_PROV_MATCH","_REF_ADA_CAND"],
        right_on=["CVE_PROV","_ALT_REF_SAE"],
        how="left",
    )
    m2a_group = (
        m2a.groupby(level=0)
           .agg(
               _EN_SAE_ALT=("_FUENTE", lambda s: s.notna().any()),
               _FUENTE_ALT=("_FUENTE", lambda s: s.dropna().iloc[0] if s.notna().any() else None),
           )
    )
    m1[["_EN_SAE_ALT","_FUENTE_ALT"]] = m2a_group[["_EN_SAE_ALT","_FUENTE_ALT"]]

    # ---------------------------
    # MATCH 2B: CVE_PROV + FECHA + IMPORTE (± tolerancia)
    # ---------------------------
    TOL = 0.01  # 1% o al menos 1.0
    m2b = m1.merge(
        sae_union[["CVE_PROV","_FECHA_SAE","_IMP_SAE","_FUENTE"]],
        left_on=["CVE_PROV_MATCH","_FECHA_ADA"],
        right_on=["CVE_PROV","_FECHA_SAE"],
        how="left",
    )
    diff = (m2b["_IMP_SAE"] - m2b["_IMP_MXN_NUM"]).abs()
    tol = (m2b["_IMP_MXN_NUM"] * TOL).clip(lower=1.0)
    m2b["_EN_SAE_FIMP"] = (diff <= tol) & m2b["_IMP_SAE"].notna()

    m2b_group = (
        m2b.groupby(level=0)
           .agg(
               _EN_SAE_FIMP=("_EN_SAE_FIMP", "any"),
               _FUENTE_FIMP=("_FUENTE", lambda s: s.dropna().iloc[0] if s.notna().any() else None),
           )
    )
    m1[["_EN_SAE_FIMP","_FUENTE_FIMP"]] = m2b_group[["_EN_SAE_FIMP","_FUENTE_FIMP"]]

    # ---------------------------
    # MATCH 3A: CVE_PROV + APP_UUID (PAGA_M01)  vs  ADA.UUID
    # ---------------------------
    m3a = m1.merge(
        sae_union[["CVE_PROV","_APP_UUID"]],
        left_on=["CVE_PROV_MATCH","_UUID_ADA"],
        right_on=["CVE_PROV","_APP_UUID"],
        how="left",
    )
    m3a_flag = m3a["_APP_UUID"].notna()

    # ---------------------------
    # MATCH 3B: CVE_PROV + APP_ADA_CFD_DOC (PAGA_M01)  vs  ADA.ID_DOCTODIG
    # ---------------------------
    m3b = m1.merge(
        sae_union[["CVE_PROV","_APP_ADA_DOC"]],
        left_on=["CVE_PROV_MATCH","_ADA_DOC"],
        right_on=["CVE_PROV","_APP_ADA_DOC"],
        how="left",
    )
    m3b_flag = m3b["_APP_ADA_DOC"].notna()

    # incorpora flags al master
    m1["_EN_SAE_APP_UUID"] = m3a_flag
    m1["_EN_SAE_APP_DOC"]  = m3b_flag

    # ---------------------------
    # Resultado final y columnas amigables
    # ---------------------------
    m1["EN_SAE"] = m1[["_EN_SAE_REF","_EN_SAE_ALT","_EN_SAE_FIMP", "_EN_SAE_APP_UUID", "_EN_SAE_APP_DOC"]].any(axis=1)

    # REFER_SAE
    m1["REFER_SAE"] = None
    mask_ref = m1["_EN_SAE_REF"].fillna(False)
    m1.loc[mask_ref, "REFER_SAE"] = m1.loc[mask_ref, "REFER_MATCH"]

    # NO_FACTURA_SAE desde alt-ref (si no hay REFER_SAE)
    m1["NO_FACTURA_SAE"] = None
    mask_alt = m1["REFER_SAE"].isna() & m1["_EN_SAE_ALT"].fillna(False)
    if mask_alt.any():
        # si coincidió por REF_ADA_1 o REF_ADA_2, reportamos ese valor como NO_FACTURA_SAE
        # Para simplificar, preferimos REF_ADA_1 (SERIE+FOLIO); si está vacío, REF_ADA_2 (FOLIO)
        cand1 = m1.loc[mask_alt, "_REF_ADA_1"].fillna("").astype(str)
        cand2 = m1.loc[mask_alt, "_REF_ADA_2"].fillna("").astype(str)
        m1.loc[mask_alt, "NO_FACTURA_SAE"] = cand1.where(cand1.ne(""), cand2)

    # Si solo cuadró por fecha+importe
    mask_fimp = m1["REFER_SAE"].isna() & m1["NO_FACTURA_SAE"].isna() & m1["_EN_SAE_FIMP"].fillna(False)
    m1.loc[mask_fimp, "REFER_SAE"] = "(match por fecha+importe)"

    # limpieza de columnas temporales
    m1.drop(columns=[
        "_EN_SAE_REF","_FUENTE_REF","_EN_SAE_ALT","_FUENTE_ALT","_EN_SAE_FIMP","_FUENTE_FIMP",
        "_REF_ADA_1","_REF_ADA_2","_FECHA_ADA","_IMP_MXN_NUM"
    ], inplace=True, errors="ignore")

    df_cmp = m1
    # Asegura columnas mínimas
    if "EN_SAE" not in df_cmp.columns:
        df_cmp["EN_SAE"] = False

    # Nueva columna para selección manual: marcar solo los que NO están en SAE
    df_cmp["INSERTAR"] = ~df_cmp["EN_SAE"]

    # estilo: RFC sin proveedor activo → rojo
    def _style_rfc(series: pd.Series) -> list[str]:
        styles = []
        for raw in series:
            r = _norm_rfc(raw)
            if not r or r not in prov_activos:
                styles.append("background-color:#e53935; color:white;")
            else:
                styles.append("")
        return styles


    # Gráficas (lado a lado)
    st.markdown("## gráficas")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### documentos por día")
        grafica_por_dia(df_cmp)
    with col2:
        st.markdown("#### montos por día")
        grafica_montos_por_dia(df_cmp)


    # Columnas visibles (ajusta si te falta alguna)
    visible_cols = [
        "DESTINO_SAE","FECHA_EMISION","CLAVE_PROV_SAE","RFC_EMISOR","NOMBRE_EMISOR", "SERIE","FOLIO","MONEDA",
        "TOTAL","TIPOCAMBIO","TOTAL_MXN","UUID","USOCFDI_",
        "EN_SAE","REFER_SAE","NO_FACTURA_SAE","INSERTAR", "CVE_PROV_MATCH", "ID_DOCTODIG"
    ]
    visible_cols = [c for c in visible_cols if c in df_cmp.columns]

    st.markdown("### Documentos ADA (inserción manual)")
    df_edit = st.data_editor(
        df_cmp[visible_cols].style.apply(_style_rfc, subset=["RFC_EMISOR"]),
        hide_index=True,
        use_container_width=True,
        # bloquea todo excepto la casilla INSERTAR
        disabled=[c for c in visible_cols if c != "INSERTAR"],
        key="ada_editor_insercion",
        height=min(900, 120 + 34 * len(df_cmp)),
    )

    # Tabla principal (conciliación)
    #st.markdown("### conciliación ADA ↔ SAE")
    #st.dataframe(
    #    df_cmp[visible_cols].style.apply(_style_rfc, subset=["RFC_EMISOR"]),
    #    use_container_width=True,
    #    hide_index=True,
    #    height=min(900, 120 + 34 * len(df_cmp))
    #)

    # Detectar columna de USO_CFDI disponible
    col_uso = next((c for c in ["uso_cfdi","USO_CFDI","USOCFDI"] if c in df_cmp.columns), None)
    if col_uso is None:
        # si no existe, crea una vacía para no tronar
        df_edit["USO_CFDI"] = ""
        col_uso = "USO_CFDI"

    # 2) Recupera el índice de las filas seleccionadas (ejemplo con INSERTAR)
    if "INSERTAR" in df_edit.columns:
        idx_pend = df_edit.index[df_edit["INSERTAR"] == True]
    else:
        idx_pend = []

    # 3) Reconstruye 'pend' desde el df original, con todas las columnas
    pend = df_cmp.loc[idx_pend].copy()

    # Ahora pend ya incluye columnas ocultas como CVE_PROV_MATCH
    #st.write("Pend completo:", pend.head(1).to_dict(orient="records"))


    # Botón único para insertar los seleccionados
    if st.button("Insertar seleccionados en SAE", key="btn_insertar_masivo"):
        ok = fail = 0
        # Filas marcadas y aún no existentes en SAE
        pend = df_edit[
            (df_edit.get("INSERTAR", False) == True) &
            (df_edit.get("EN_SAE", False) == False)
        ]


        #st.write("columnas en pend:", list(pend.columns))
        #st.write("muestra pend:", pend.head(1).to_dict(orient="records"))
        for _, r in pend.iterrows():
            #usocfdi = r.get("USOCFDI_")
            #clave_prov = r.get("CVE_PROV_MATCH")
            #id_docto_dig = r.get("ID_DOCTODIG")
            #st.write(usocfdi)
            #st.write(clave_prov)
            #st.write(id_docto_dig)
            #st.stop()
            res = insertar_en_sae_por_uso(
                st.secrets,
                uso_cfdi = r.get(col_uso, ""),
                rfc_emisor = r.get("RFC_EMISOR"),
                serie = r.get("SERIE"),
                folio = r.get("FOLIO"),
                fecha_emision = r.get("FECHA_EMISION"),
                total_mxn = r.get("TOTAL_MXN"),
                uuid = r.get("UUID"),
                usocfdi = r.get("USOCFDI_"), ### Nuevos campos desde aqui
                clave_prov = r.get("CVE_PROV_MATCH"),
                id_docto_dig = r.get("ID_DOCTODIG"),
                moneda = r.get("MONEDA"),
                tcambio = r.get("TIPOCAMBIO"),
                impext = r.get("TOTAL"),
            )
            ok += 1 if res.get("ok") else 0
            fail += 0 if res.get("ok") else 1
            #st.stop()
        (st.success if fail == 0 else st.warning)(
            f"Insertados: {ok} | Fallidos: {fail}"
        )

    # --- botón de refresco (siempre visible) ---
    st.divider()
    col_ref, _ = st.columns([1, 5])
    with col_ref:
        if st.button("🔄 Refrescar datos", key="btn_refrescar_despues"):
            st.cache_data.clear()  # limpia los @st.cache_data
            st.rerun()             # recarga la pantalla completa

    # columnas visibles
    #visible_cols = [
    #    "DESTINO_SAE", "CLAVE_PROV_SAE", "RFC_EMISOR", "SERIE", "FOLIO",
    #    "TOTAL_MXN", "TIPOCAMBIO", "UUID", "FECHA_EMISION",
    #    "EN_SAE", "REFER_SAE", "NO_FACTURA_SAE",
    #]
    #visible_cols = [c for c in visible_cols if c in df_cmp.columns]

    # exportar ADA base (lo que ves filtrado)
    col_a, _ = st.columns([1,3])
    with col_a:
        if st.button("exportar a excel", key="btn_exportar"):
            try:
                xlsx = exportar_excel(df)
                st.download_button(
                    "descargar documentos.xlsx",
                    data=xlsx,
                    file_name="documentos_ada.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="btn_descarga_xlsx"
                )
            except Exception as e:
                st.error(f"no se pudo exportar: {e}")

# ---------------------------
# Gráficas
# ---------------------------
def grafica_por_dia(df: pd.DataFrame):
    if "FECHA_EMISION" not in df.columns or df.empty:
        return
    df = df.copy()
    df["FECHA_EMISION"] = pd.to_datetime(df["FECHA_EMISION"], errors="coerce")
    df["DIA_NUM"] = df["FECHA_EMISION"].dt.dayofweek
    nombres = {0:"Lunes",1:"Martes",2:"Miércoles",3:"Jueves",4:"Viernes",5:"Sábado",6:"Domingo"}
    df["DIA_SEMANA"] = df["DIA_NUM"].map(nombres)
    conteo = df["DIA_SEMANA"].value_counts().reindex(nombres.values())

    fig, ax = plt.subplots(figsize=(8, 4))
    conteo.plot(kind="bar", ax=ax)
    ax.set_title("Documentos por día de la semana", fontsize=10)
    ax.set_xlabel("Día", fontsize=10)
    ax.set_ylabel("Cantidad de documentos", fontsize=10)
    ax.tick_params(axis="x", labelsize=8)
    ax.tick_params(axis="y", labelsize=8)
    for patch in ax.patches:
        altura = patch.get_height()
        if pd.notna(altura):
            ax.text(patch.get_x()+patch.get_width()/2, altura+1, f"{int(altura)}", ha="center", va="bottom", fontsize=10)
    st.pyplot(fig)

def grafica_montos_por_dia(df: pd.DataFrame):
    if df.empty or "FECHA_EMISION" not in df.columns or "TOTAL_MXN" not in df.columns:
        return
    df = df.copy()
    df["FECHA_EMISION"] = pd.to_datetime(df["FECHA_EMISION"], errors="coerce")
    nombres = {0:"Lunes",1:"Martes",2:"Miércoles",3:"Jueves",4:"Viernes",5:"Sábado",6:"Domingo"}
    df["DIA_SEMANA"] = df["FECHA_EMISION"].dt.dayofweek.map(nombres)
    if df["TOTAL_MXN"].dtype == object:
        df["TOTAL_MXN"] = df["TOTAL_MXN"].astype(str).str.replace(",", "", regex=False).str.replace("$", "", regex=False)
    df["TOTAL_MXN"] = pd.to_numeric(df["TOTAL_MXN"], errors="coerce").fillna(0.0)
    orden = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"]
    serie = df.groupby("DIA_SEMANA", dropna=False)["TOTAL_MXN"].sum().reindex(orden).fillna(0.0)

    fig, ax = plt.subplots(figsize=(9, 4.5))
    barras = ax.bar(serie.index.tolist(), serie.values)
    ax.set_title("monto total por día de la semana", fontsize=14)
    ax.set_xlabel("día", fontsize=12)
    ax.set_ylabel("monto", fontsize=12)
    ax.tick_params(axis="x", labelsize=10)
    ax.tick_params(axis="y", labelsize=10)
    for rect, val in zip(barras, serie.values):
        ax.text(rect.get_x()+rect.get_width()/2.0, rect.get_height()+(0.01*(serie.max() if serie.max() else 1)), f"{val:,.2f}", ha="center", va="bottom", fontsize=10)
    st.pyplot(fig)