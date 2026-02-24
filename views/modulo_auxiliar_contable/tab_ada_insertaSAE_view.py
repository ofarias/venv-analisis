# views/modulo_auxiliar_contable/tab_ada_insertaSAE_view.py
import streamlit as st
import calendar
from datetime import date, timedelta
import pandas as pd
import matplotlib.pyplot as plt
from models.sae_model import cargar_conceptos_por_prov, insertar_en_sae_por_uso, cargar_conceptos_sae
from controllers.ada_controller import (
    cargar_tipos,
    cargar_documentos,
    contar_documentos_cached,
    exportar_excel,
    cargar_proveedores_activos,
    cargar_paga_por_fecha,     # snapshots SAE por rango de fechas
    cargar_compc_por_fecha,    # snapshots SAE por rango de fechas
    cargar_conceptos_por_documento,
    # buscar_en_paga_g03,
    buscar_concep_en_paga_g03,
    cargar_documentos_con_mysql,
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


def insertarSAE():
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
        #df = cargar_documentos(st.secrets, filtros, page, page_size)
        df = cargar_documentos_con_mysql(st.secrets, filtros, page, page_size)
        if not df.empty:
            col_usocfdi = next((c for c in df.columns if c.lower() == "usocfdi_"), None)
            if col_usocfdi:
                df = df[df[col_usocfdi].astype(str).str.strip().str.upper() == "G03"].copy()
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

    uso_series = _first_series(df, ["uso_cfdi", "USO_CFDI", "USOCFDI", "USOCFDI_"]).fillna("").astype(str)
    
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
    
    # llaves ADA para match por APP
    df["_UUID_ADA"] = df.get("UUID", "").astype(str).str.upper()
    df["_ADA_DOC"]  = df.get("ID_DOCTODIG", "").astype(str)

    # snapshots SAE por fecha (todo en rango)
    f_ini = pd.to_datetime(filtros.get("fecha_desde")).date() if filtros.get("fecha_desde") else None
    f_fin = pd.to_datetime(filtros.get("fecha_hasta")).date() if filtros.get("fecha_hasta") else None

    paga_raw = cargar_paga_por_fecha(st.secrets, f_ini, f_fin)
    compc_raw = cargar_compc_por_fecha(st.secrets, f_ini, f_fin)
    #st.stop()

    # ---------------------------
    # Normalización robusta SAE
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

    # ----------------------------------------
    # excluir ya insertados en paga_m01 por app_uuid
    # ----------------------------------------
    uuids_en_paga = set(
        paga_all["_APP_UUID"].dropna().astype(str).str.upper().str.strip().tolist()
    )

    # opcional: si también quieres excluir los que estén en compc, descomenta:
    # uuids_en_compc = set(
    #     compc_all["_APP_UUID"].dropna().astype(str).str.upper().str.strip().tolist()
    # )
    # uuids_en_sae = uuids_en_paga.union(uuids_en_compc)
    uuids_en_sae = uuids_en_paga

    df = df.copy()
    df["_UUID_ADA"] = df.get("UUID", "").astype(str).str.upper().str.strip()

    antes = len(df)
    df = df[~df["_UUID_ADA"].isin(uuids_en_sae)].copy()
    st.caption(f"filtrados por app_uuid ya insertados en paga_m01: {antes - len(df)}")
    

    # MATCH 1: CVE_PROV + REFER
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
    m1.drop(columns=["CVE_PROV","REFER","_FUENTE"], inplace=True)

    # MATCH 2A: CVE_PROV + (NO_FACTURA/DOCTO) vs (REFER_MATCH o FOLIO)
    sae_alt = sae_union.copy()
    sae_alt["_ALT_REF_SAE"] = sae_alt["_NO_FACTURA"].where(
        sae_alt["_NO_FACTURA"].ne(""), sae_alt["_DOCTO"]
    ).fillna("").astype(str).str.upper()

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

    # MATCH 2B: CVE_PROV + FECHA + IMPORTE (± tolerancia)
    TOL = 0.01
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

    # MATCH 3A: CVE_PROV + APP_UUID vs ADA.UUID
    m3a = m1.merge(
        sae_union[["CVE_PROV","_APP_UUID"]],
        left_on=["CVE_PROV_MATCH","_UUID_ADA"],
        right_on=["CVE_PROV","_APP_UUID"],
        how="left",
    )
    m3a_flag = m3a["_APP_UUID"].notna()

    # MATCH 3B: CVE_PROV + APP_ADA_DOC vs ADA.ID_DOCTODIG
    m3b = m1.merge(
        sae_union[["CVE_PROV","_APP_ADA_DOC"]],
        left_on=["CVE_PROV_MATCH","_ADA_DOC"],
        right_on=["CVE_PROV","_APP_ADA_DOC"],
        how="left",
    )
    m3b_flag = m3b["_APP_ADA_DOC"].notna()

    m1["_EN_SAE_APP_UUID"] = m3a_flag
    m1["_EN_SAE_APP_DOC"]  = m3b_flag

    # Resultado final
    m1["EN_SAE"] = m1[["_EN_SAE_REF","_EN_SAE_ALT","_EN_SAE_FIMP", "_EN_SAE_APP_UUID", "_EN_SAE_APP_DOC"]].any(axis=1)

    m1["REFER_SAE"] = None
    mask_ref = m1["_EN_SAE_REF"].fillna(False)
    m1.loc[mask_ref, "REFER_SAE"] = m1.loc[mask_ref, "REFER_MATCH"]

    m1["NO_FACTURA_SAE"] = None
    mask_alt = m1["REFER_SAE"].isna() & m1["_EN_SAE_ALT"].fillna(False)
    if mask_alt.any():
        cand1 = m1.loc[mask_alt, "_REF_ADA_1"].fillna("").astype(str)
        cand2 = m1.loc[mask_alt, "_REF_ADA_2"].fillna("").astype(str)
        m1.loc[mask_alt, "NO_FACTURA_SAE"] = cand1.where(cand1.ne(""), cand2)

    mask_fimp = m1["REFER_SAE"].isna() & m1["NO_FACTURA_SAE"].isna() & m1["_EN_SAE_FIMP"].fillna(False)
    m1.loc[mask_fimp, "REFER_SAE"] = "(match por fecha+importe)"

    m1.drop(columns=[
        "_EN_SAE_REF","_FUENTE_REF","_EN_SAE_ALT","_FUENTE_ALT","_EN_SAE_FIMP","_FUENTE_FIMP",
        "_REF_ADA_1","_REF_ADA_2","_FECHA_ADA","_IMP_MXN_NUM"
    ], inplace=True, errors="ignore")

    df_cmp = m1
    if "EN_SAE" not in df_cmp.columns:
        df_cmp["EN_SAE"] = False

    # columna de selección (ya sin lógica de insertar)
    df_cmp["INSERTAR"] = False

    def _style_rfc(series: pd.Series) -> list[str]:
        styles = []
        for raw in series:
            r = _norm_rfc(raw)
            if not r or r not in prov_activos:
                styles.append("background-color:#e53935; color:white;")
            else:
                styles.append("")
        return styles

    # mostrar/ocultar gráficas (default: ocultas)
    st.session_state.setdefault("mostrar_graficas_ada", False)

    colg1, colg2 = st.columns([1, 6])
    with colg1:
        if st.button(
            "📈 mostrar gráficas" if not st.session_state["mostrar_graficas_ada"] else "🙈 ocultar gráficas",
            key="btn_toggle_graficas_ada",
            use_container_width=True,
        ):
            st.session_state["mostrar_graficas_ada"] = not st.session_state["mostrar_graficas_ada"]

    if st.session_state["mostrar_graficas_ada"]:
        # gráficas
        st.markdown("## gráficas")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("#### documentos por día")
            grafica_por_dia(df_cmp)
        with col2:
            st.markdown("#### montos por día")
            grafica_montos_por_dia(df_cmp)

    ### TABLA Principal 
    # asegurar tipos antes de mostrar
    if "ID_DOCTODIG" in df_cmp.columns:
        df_cmp["ID_DOCTODIG"] = pd.to_numeric(df_cmp["ID_DOCTODIG"], errors="coerce").astype("Int64") 
    
    # columnas visibles (ajusta si te falta alguna)
    visible_cols = [
        "DESTINO_SAE","INSERTAR","FECHA_EMISION","CVE_PROV_MATCH","CLAVE_PROV_SAE",
        "RFC_EMISOR","NOMBRE_EMISOR","SERIE","FOLIO",
        "MONEDA","TOTAL","TIPOCAMBIO","TOTAL_MXN","USOCFDI_","UUID",
        "EN_SAE","REFER_SAE","NO_FACTURA_SAE","ID_DOCTODIG",
    ]
    visible_cols = [c for c in visible_cols if c in df_cmp.columns]

    st.markdown("### documentos ada")

    # dejar solo INSERTAR editable, todo lo demás solo lectura
    disabled_cols = [c for c in visible_cols if c != "INSERTAR"]

    df_edit = st.data_editor(
        df_cmp[visible_cols].style.apply(_style_rfc, subset=["RFC_EMISOR"]),
        hide_index=True,
        use_container_width=True,
        disabled=disabled_cols,
        key="ada_editor_insercion",
        height=min(900, 120 + 34 * len(df_cmp)),
    )
        
    # ----------------------------------------
    # documento seleccionado via columna INSERTAR
    # ----------------------------------------
    st.divider()
    st.markdown("### detalle y concepto para el documento seleccionado")

    doc_sel = None
    if "INSERTAR" in df_edit.columns:
        mask_sel = df_edit["INSERTAR"] == True
        if mask_sel.any():
            if mask_sel.sum() > 1:
                st.info("hay varias filas marcadas; tomando la primera.")
            idx_sel = df_edit[mask_sel].index[0]
            doc_sel = df_cmp.loc[idx_sel]

    if doc_sel is None:
        st.info("marca la casilla insertar de un documento para ver su detalle.")
    else:
        # encabezado sencillo
        st.write(
            f"id_doctodig: {doc_sel.get('ID_DOCTODIG')} | "
            f"proveedor: {doc_sel.get('NOMBRE_EMISOR')} | "
            f"folio: {doc_sel.get('FOLIO')} | "
            f"uuid: {doc_sel.get('UUID')}"
        )

        # ---------------------------
        # conceptos ada del documento
        # ---------------------------
        try:
            id_docto_dig = int(doc_sel.get("ID_DOCTODIG"))
            df_det = cargar_conceptos_por_documento(st.secrets, id_docto_dig)
        except Exception as e:
            st.error(f"error al cargar conceptos de ada: {e}")
            df_det = pd.DataFrame()

        if df_det.empty:
            st.info("no se encontraron conceptos en ada para este documento.")
        else:
            cols_montos = [
                "VALORUNITARIO", "DESCUENTO", "IMPORTE", "BASE_IVA",
                "IVA", "IEPS", "IVA_RET", "IEPS_RET", "ISR"
            ]
            for col in cols_montos:
                if col in df_det.columns:
                    df_det[col] = pd.to_numeric(df_det[col], errors="coerce").fillna(0)

            orden_cols = [
                "CLAVEPRODSERV", "NO_IDENTIFICACION", "DESCRIPCION",
                "CANTIDAD", "CLAVEUNIDAD", "UNIDAD",
                "VALORUNITARIO", "DESCUENTO", "IMPORTE",
                "OBJETOIMP", "BASE_IVA", "IVA", "IEPS",
                "IVA_RET", "IEPS_RET", "ISR"
            ]
            orden_cols = [c for c in orden_cols if c in df_det.columns]

            st.markdown("#### conceptos ada")
            st.dataframe(
                df_det[orden_cols],
                use_container_width=True,
                hide_index=True,
            )
        
        # ---------------------------
        # concepto sae: sugerencia + catálogo completo
        # ---------------------------
        st.markdown("#### concepto sae")

        # 1) intentamos sugerir concepto con la lógica existente
        try:
            col_uso_local = next(
                (c for c in ["uso_cfdi","USO_CFDI","USOCFDI","USOCFDI_"] if c in df_cmp.columns),
                None,
            )
            uso_cfdi_val = str(doc_sel.get(col_uso_local, "") or "").strip()

            rfc_receptor = str(doc_sel.get("RFC_RECEPTOR", "") or "").strip()
            clave_prov   = str(doc_sel.get("CVE_PROV_MATCH", "") or "").strip()
            serie        = str(doc_sel.get("SERIE", "") or "").strip()
            folio_doc    = str(doc_sel.get("FOLIO", "") or "").strip()

            total_mxn = doc_sel.get("TOTAL_MXN", 0.0)
            try:
                total_mxn = float(str(total_mxn).replace(",", "").replace("$", ""))
            except Exception:
                total_mxn = 0.0

            res_cptos = buscar_concep_en_paga_g03(
                st.secrets,
                uso_cfdi_val,
                rfc_receptor,
                clave_prov,
                serie,
                folio_doc,
                total_mxn,
            )
        except Exception as e:
            st.error(f"error al detectar concepto en sae: {e}")
            res_cptos = None

        if isinstance(res_cptos, pd.DataFrame):
            df_cptos_sug = res_cptos.copy()
        elif isinstance(res_cptos, (list, tuple)):
            df_cptos_sug = pd.DataFrame(res_cptos)
        elif isinstance(res_cptos, dict):
            df_cptos_sug = pd.DataFrame([res_cptos])
        else:
            df_cptos_sug = pd.DataFrame()

        # num_cpto sugerido (si existe)
        num_cpto_sugerido = None
        if not df_cptos_sug.empty and "NUM_CPTO" in df_cptos_sug.columns:
            try:
                num_cpto_sugerido = int(df_cptos_sug.iloc[0]["NUM_CPTO"])
            except Exception:
                num_cpto_sugerido = None

            st.caption("sugerencias encontradas por la lógica existente")
            st.dataframe(
                df_cptos_sug,
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("no se encontró un concepto sugerido; usa el catálogo de conceptos.")

        # 2) siempre mostrar el catálogo completo de conceptos sae
        try:
            df_cat = cargar_conceptos_sae(st.secrets)
        except Exception as e:
            st.error(f"error al cargar catálogo de conceptos de sae: {e}")
            df_cat = pd.DataFrame()

        concepto_elegido = None
        num_cpto_sel = None

        if df_cat.empty:
            st.warning("no se pudo obtener el catálogo de conceptos de sae.")
        else:
            nombre_col = "NOMBRE_CPTO" if "NOMBRE_CPTO" in df_cat.columns else (
                "DESCR" if "DESCR" in df_cat.columns else None
            )

            if "NUM_CPTO" not in df_cat.columns or nombre_col is None:
                st.error("el catálogo de conceptos no tiene columnas NUM_CPTO y descripción esperadas.")
            else:
                df_cat = df_cat.copy().reset_index(drop=True)

                opciones = df_cat.apply(
                    lambda x: f"{x['NUM_CPTO']} - {x.get(nombre_col, '')}",
                    axis=1,
                ).tolist()

                # index por defecto: si hay sugerido y existe en el catálogo, lo usamos
                idx_default = 0
                if num_cpto_sugerido is not None:
                    coincidencias = df_cat.index[df_cat["NUM_CPTO"] == num_cpto_sugerido].tolist()
                    if coincidencias:
                        idx_default = coincidencias[0]

                concepto_elegido = st.selectbox(
                    "elige concepto de sae (se preselecciona el sugerido si existe):",
                    opciones,
                    index=idx_default,
                )
                num_cpto_sel = int(concepto_elegido.split("-")[0].strip())

                st.caption(f"concepto seleccionado: {concepto_elegido}")

                with st.expander("ver catálogo completo de conceptos sae"):
                    st.dataframe(
                        df_cat,
                        use_container_width=True,
                        hide_index=True,
                    )
        

        # ----------------------------------------
        # inserción en PAGA_M01 usando el concepto elegido
        # ----------------------------------------
        # asumimos que en la sección anterior ya definiste:
        #   concepto_elegido = "123 - DESCRIPCION"
        # y que doc_sel es la fila seleccionada (Series)
        
        # solo si tenemos un concepto seleccionado y un número de concepto
        if concepto_elegido and num_cpto_sel is not None:
            st.markdown("#### insertar movimiento en paga_m01")

            if st.button("insertar en paga_m01", key="btn_insertar_paga_m01"):
                # preparar parámetros igual que antes
                col_uso_local = next(
                    (c for c in ["uso_cfdi","USO_CFDI","USOCFDI","USOCFDI_"] if c in df_cmp.columns),
                    None,
                )
                uso_cfdi_val = str(doc_sel.get(col_uso_local, "") or "").strip()

                rfc_emisor = doc_sel.get("RFC_EMISOR")
                serie = doc_sel.get("SERIE")
                folio_doc = doc_sel.get("FOLIO")
                fecha_emision = doc_sel.get("FECHA_EMISION")
                total_mxn = doc_sel.get("TOTAL_MXN")
                uuid = doc_sel.get("UUID")
                clave_prov = doc_sel.get("CVE_PROV_MATCH")
                id_docto_dig = doc_sel.get("ID_DOCTODIG")
                moneda = doc_sel.get("MONEDA", "MXN")
                tcambio = doc_sel.get("TIPOCAMBIO", 1.0)
                impext = doc_sel.get("TOTAL", 0.0)

                try:
                    res = insertar_en_sae_por_uso(
                        st.secrets,
                        uso_cfdi_val,
                        rfc_emisor=rfc_emisor,
                        serie=serie,
                        folio=folio_doc,
                        fecha_emision=fecha_emision,
                        total_mxn=total_mxn,
                        uuid=uuid,
                        clave_prov=clave_prov,
                        id_docto_dig=id_docto_dig,
                        moneda=moneda,
                        tcambio=tcambio,
                        impext=impext,
                        num_cpto_manual=num_cpto_sel,
                        concepto_label=concepto_elegido,
                    )
                    if res.get("ok"):
                        st.success(f"movimiento insertado en paga_m01. folio: {res.get('folio_num')}")
                    else:
                        st.error(f"error al insertar en sae: {res.get('msg')}")
                except Exception as e:
                    st.error(f"error al llamar insertar_en_sae_por_uso: {e}")
        else:
            st.info("selecciona un concepto de sae para habilitar la inserción.")  

    # botón de refresco
    st.divider()
    col_ref, _ = st.columns([1, 5])
    with col_ref:
        if st.button("🔄 Refrescar datos", key="btn_refrescar_despues"):
            st.cache_data.clear()
            st.rerun()

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

def grafica_resumen_tabla(resumen: pd.DataFrame, top_prov: int = 10):
    """
    Barra simple: N_CONCEPTOS por proveedor usando la tabla Resumen.
    Requiere columnas: NOMBRE_PROV, N_CONCEPTOS
    """
    st.markdown("### Proveedores con más conceptos distintos (Resumen)")
    if resumen is None or resumen.empty:
        st.info("Sin datos en Resumen para graficar.")
        return
    req = {"NOMBRE_PROV", "N_CONCEPTOS"}
    if not req.issubset(resumen.columns):
        st.warning(f"Resumen no contiene columnas {sorted(req)}")
        return

    top = (resumen[["NOMBRE_PROV","N_CONCEPTOS"]]
           .sort_values("N_CONCEPTOS", ascending=False)
           .head(int(top_prov)))

    if top.empty:
        st.info("No hay datos para graficar.")
        return

    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.bar(top["NOMBRE_PROV"], top["N_CONCEPTOS"])
    ax.set_title("N.º de conceptos distintos por proveedor", fontsize=12)
    ax.set_xlabel("Proveedor", fontsize=10)
    ax.set_ylabel("Conceptos distintos", fontsize=10)
    ax.tick_params(axis="x", labelrotation=90, labelsize=9)

    for x, y in zip(top["NOMBRE_PROV"], top["N_CONCEPTOS"]):
        ax.text(x, y + max(1, top["N_CONCEPTOS"].max()*0.01), str(int(y)), ha="center", va="bottom", fontsize=9)

    st.pyplot(fig)

def grafica_detalle_tabla(detalle: pd.DataFrame, top_prov: int = 10, top_conc: int = 8):
    """
    Barra apilada: USOS por proveedor desglosado por concepto usando la tabla Detalle.
    Requiere columnas: NOMBRE_PROV, DESCR, USOS
    """
    st.markdown("### Distribución de USOS por proveedor y concepto (Detalle)")
    if detalle is None or detalle.empty:
        st.info("Sin datos en Detalle para graficar.")
        return
    req = {"NOMBRE_PROV", "DESCR", "USOS"}
    if not req.issubset(detalle.columns):
        st.warning(f"Detalle no contiene columnas {sorted(req)}")
        return

    det = detalle.copy()
    # asegurar tipos
    det["USOS"] = pd.to_numeric(det["USOS"], errors="coerce").fillna(0)

    # Top proveedores por total de USOS
    top_proveedores = (det.groupby("NOMBRE_PROV", as_index=False)["USOS"].sum()
                         .sort_values("USOS", ascending=False)
                         .head(int(top_prov)))["NOMBRE_PROV"].tolist()
    det = det[det["NOMBRE_PROV"].isin(top_proveedores)]

    if det.empty:
        st.info("No hay suficientes datos tras filtrar por top proveedores.")
        return

    # Top conceptos dentro del subconjunto
    top_conceptos = (det.groupby("DESCR", as_index=False)["USOS"].sum()
                       .sort_values("USOS", ascending=False)
                       .head(int(top_conc)))["DESCR"].tolist()
    det = det[det["DESCR"].isin(top_conceptos)]

    if det.empty:
        st.info("No hay suficientes datos tras filtrar por top conceptos.")
        return

    # pivote para apilada
    pivot = det.pivot_table(index="NOMBRE_PROV", columns="DESCR", values="USOS", aggfunc="sum", fill_value=0)
    pivot = pivot.sort_index()

    fig, ax = plt.subplots(figsize=(11, 5))
    bottom = None
    for col in pivot.columns:
        vals = pivot[col].values
        ax.bar(pivot.index, vals, bottom=bottom, label=col)
        bottom = vals if bottom is None else (bottom + vals)

    ax.set_title("USOS por proveedor y concepto", fontsize=12)
    ax.set_xlabel("Proveedor", fontsize=10)
    ax.set_ylabel("USOS", fontsize=10)
    ax.tick_params(axis="x", labelrotation=90, labelsize=9)
    ax.legend(title="Concepto", fontsize=8, title_fontsize=9, bbox_to_anchor=(1.02, 1), loc="upper left")

    st.pyplot(fig)