# views/ada_view.py
import streamlit as st
import calendar
from datetime import date, timedelta
import pandas as pd
import matplotlib.pyplot as plt
from models.sae_model import insertar_en_sae_por_uso, _conn_sae_from_secrets, cargar_conceptos_por_prov
from models.conta45_model import insertar_poliza_y_auxiliares 
from views.modulo_auxiliar_contable.tab_ada_insertaSAE_view import insertarSAE
from controllers.ada_controller import (
    cargar_tipos,
    cargar_documentos,
    contar_documentos_cached,
    exportar_excel,
    cargar_proveedores_activos,
    cargar_paga_por_fecha,     # snapshots SAE por rango de fechas
    cargar_compc_por_fecha,    # snapshots SAE por rango de fechas
    #detectar_patrones_paga_desde_raw,
    cargar_paga_para_patrones,
    cargar_vista_paga_prov_cpto, 
    cargar_conceptos_por_documento,
    cargar_conceptos_filtrados,
    buscar_en_paga_g03,
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


    tab_docs, tab_conceptos, tab_patrones, tab_vista, tab_detalles, tab_insertaSAE = st.tabs(
        ["Documentos", "Conceptos por proveedor", "Patrones de facturas", "Movimientos SAE (vista unificada)", "Detalles CFDI", "Insertar en SAE"]
    )

    with tab_docs:
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
            "DESTINO_SAE","INSERTAR","FECHA_EMISION","CVE_PROV_MATCH","CLAVE_PROV_SAE","RFC_EMISOR","NOMBRE_EMISOR", "SERIE","FOLIO",
            "MONEDA","TOTAL","TIPOCAMBIO","TOTAL_MXN","USOCFDI_","UUID",
            "EN_SAE","REFER_SAE","NO_FACTURA_SAE",  "ID_DOCTODIG"
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
        pass

        # ----------------------------------------
        # 📦 Exportar facturas + conceptos a Excel
        # ----------------------------------------
        st.divider()
        st.markdown("### 📤 Exportar facturas con sus conceptos")

        if st.button("Exportar documentos y conceptos", key="btn_exportar_conceptos"):
            try:
                # 1️⃣ Traer los documentos filtrados actuales
                docs_df = df_cmp.copy()

                if docs_df.empty:
                    st.warning("No hay documentos para exportar con los filtros actuales.")
                else:
                    # 2️⃣ Traer todos los conceptos de esos documentos
                    all_conceptos = []
                    for id_doc in docs_df["ID_DOCTODIG"].unique():
                        det = cargar_conceptos_por_documento(st.secrets, int(id_doc))
                        if not det.empty:
                            det["ID_DOCTODIG"] = int(id_doc)
                            all_conceptos.append(det)

                    if not all_conceptos:
                        st.warning("Ninguno de los documentos filtrados tiene conceptos asociados.")
                    else:
                        conceptos_df = pd.concat(all_conceptos, ignore_index=True)

                        # 3️⃣ Formateo de montos
                        cols_montos = [
                            "VALORUNITARIO", "DESCUENTO", "IMPORTE",
                            "BASE_IVA", "IVA", "IEPS", "IVA_RET", "IEPS_RET", "ISR"
                        ]
                        for col in cols_montos:
                            if col in conceptos_df.columns:
                                conceptos_df[col] = pd.to_numeric(conceptos_df[col], errors="coerce").fillna(0.0)

                        # 4️⃣ Exportar a Excel (dos hojas)
                        import io
                        output = io.BytesIO()
                        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                            docs_df.to_excel(writer, sheet_name="Facturas", index=False)
                            conceptos_df.to_excel(writer, sheet_name="Conceptos", index=False)
                        xlsx_data = output.getvalue()

                        # 5️⃣ Botón de descarga
                        st.download_button(
                            label="📄 Descargar Excel combinado",
                            data=xlsx_data,
                            file_name="facturas_conceptos.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True,
                        )

            except Exception as e:
                st.error(f"Ocurrió un error al generar el Excel: {e}")


        #### Conceptos 
        # ----------------------------------------
        # 🔍 Ver detalles (conceptos) de un CFDI
        # ----------------------------------------
        st.markdown("### Detalle de conceptos del documento seleccionado")

        if not df_cmp.empty:
            lista_docs = (
                df_cmp[["ID_DOCTODIG", "UUID", "NOMBRE_EMISOR", "FOLIO"]]
                .astype(str)
                .apply(lambda x: f"{x['ID_DOCTODIG']} | {x['NOMBRE_EMISOR']} | Folio {x['FOLIO']} | {x['UUID']}", axis=1)
                .tolist()
            )

            sel_doc = st.selectbox("Selecciona un documento", options=lista_docs)

            if sel_doc:
                id_docto_dig = int(sel_doc.split("|")[0].strip())
                df_det = cargar_conceptos_por_documento(st.secrets, id_docto_dig)

                if df_det.empty:
                    st.info("No se encontraron conceptos para este documento.")
                else:
                    # formato monetario
                    cols_montos = [
                        "VALORUNITARIO", "DESCUENTO", "IMPORTE", "BASE_IVA",
                        "IVA", "IEPS", "IVA_RET", "IEPS_RET", "ISR"
                    ]
                    for col in cols_montos:
                        if col in df_det.columns:
                            df_det[col] = pd.to_numeric(df_det[col], errors="coerce").fillna(0)
                            df_det[col] = df_det[col].apply(lambda x: f"${x:,.2f}")

                    orden_cols = [
                        "CLAVEPRODSERV", "NO_IDENTIFICACION", "DESCRIPCION",
                        "CANTIDAD", "CLAVEUNIDAD", "UNIDAD",
                        "VALORUNITARIO", "DESCUENTO", "IMPORTE",
                        "OBJETOIMP", "BASE_IVA", "IVA", "IEPS",
                        "IVA_RET", "IEPS_RET", "ISR"
                    ]
                    orden_cols = [c for c in orden_cols if c in df_det.columns]

                    st.dataframe(
                        df_det[orden_cols],
                        use_container_width=True,
                        hide_index=True,
                    )

                    # total de conceptos
                    total = (
                        df_det["IMPORTE"]
                        .replace({"[$,]": ""}, regex=True)
                        .astype(float)
                        .sum()
                    )
                    st.markdown(f"**Total conceptos:** ${total:,.2f}")

                    # conceptos de sae detectados para este documento
                    st.markdown("### conceptos sae detectados para este documento")

                    # buscamos la fila original en df_cmp
                    fila_doc = df_cmp[df_cmp["ID_DOCTODIG"] == id_docto_dig]
                    if fila_doc.empty:
                        st.info("no se encontró el documento en el dataframe base.")
                    else:
                        r = fila_doc.iloc[0]

                        # columna de uso cfdi que esté disponible
                        col_uso_local = next(
                            (c for c in ["uso_cfdi", "USO_CFDI", "USOCFDI", "USOCFDI_"] if c in fila_doc.columns),
                            None,
                        )
                        uso_cfdi_val = str(r.get(col_uso_local, "") or "").strip()

                        rfc_receptor = str(r.get("RFC_RECEPTOR", "") or "").strip()
                        clave_prov = str(r.get("CVE_PROV_MATCH", "") or "").strip()
                        serie = str(r.get("SERIE", "") or "").strip()
                        folio_doc = str(r.get("FOLIO", "") or "").strip()
                        total_mxn = r.get("TOTAL_MXN", 0.0)
                        try:
                            total_mxn = float(str(total_mxn).replace(",", "").replace("$", ""))
                        except Exception:
                            total_mxn = 0.0

                        try:
                            res_cptos = buscar_en_paga_g03(
                                st.secrets,
                                uso_cfdi_val,
                                rfc_receptor,
                                clave_prov,
                                serie,
                                folio_doc,
                                total_mxn,
                            )
                        except Exception as e:
                            st.error(f"error al detectar conceptos en sae: {e}")
                            res_cptos = None

                        # normalizamos a dataframe
                        if isinstance(res_cptos, pd.DataFrame):
                            df_cptos = res_cptos.copy()
                        elif isinstance(res_cptos, (list, tuple)):
                            df_cptos = pd.DataFrame(res_cptos)
                        elif isinstance(res_cptos, dict):
                            df_cptos = pd.DataFrame([res_cptos])
                        else:
                            df_cptos = pd.DataFrame()

                        if df_cptos.empty:
                            st.info("no se encontraron conceptos de sae para este documento.")
                        else:
                            # si viene num_cpto / nombre_cpto, mostramos un resumen rápido
                            nombre_col = None
                            if "NOMBRE_CPTO" in df_cptos.columns:
                                nombre_col = "NOMBRE_CPTO"
                            elif "DESCR" in df_cptos.columns:
                                nombre_col = "DESCR"

                            if "NUM_CPTO" in df_cptos.columns:
                                num = df_cptos.iloc[0]["NUM_CPTO"]
                                desc = df_cptos.iloc[0].get(nombre_col, "")
                                st.caption(f"concepto principal sugerido: {num} - {desc}")

                            st.dataframe(
                                df_cptos,
                                use_container_width=True,
                                hide_index=True,
                            )
        

        ### Final de conceptos 


    with tab_conceptos:
        st.markdown("### Conceptos por proveedor (PAGA_M01 → CONP01 → PROV01)")

        col1, _ = st.columns([1, 4])
        with col1:
            if st.button("Refrescar conceptos", key="btn_refrescar_conceptos"):
                st.cache_data.clear()

        # Carga datos
        df_cp = cargar_conceptos_por_prov(st.secrets, f_ini, f_fin)

        if df_cp.empty:
            st.info("No hay movimientos en PAGA_M01 para el rango seleccionado.")
        else:
            df_cp["PAIR"] = (
                df_cp["NUM_CPTO"].astype(str) + " - " + df_cp["DESCR"].astype(str)
            )

            # ------- Resumen por proveedor -------
            resumen = (
                df_cp.groupby(["CVE_PROV", "NOMBRE_PROV"], as_index=False)
                    .agg(
                        N_CONCEPTOS=("NUM_CPTO", "nunique"),
                        CONCEPTOS=("PAIR", lambda s: ", ".join(sorted(set(s))))
                    )
                    .sort_values(["CVE_PROV"])
            )

            # ------- Detalle -------
            detalle = (
                df_cp[["CVE_PROV", "NOMBRE_PROV", "NUM_CPTO", "DESCR", "USOS"]]
                .sort_values(["CVE_PROV", "NUM_CPTO"])
            )




            st.markdown("## gráficas")

            col1, col2 = st.columns(2)
            with col1:
                st.markdown("#### documentos por día")
                grafica_resumen_tabla(resumen)
            with col2:
                st.markdown("#### montos por día")
                grafica_detalle_tabla(detalle)
            
            st.markdown("#### Resumen")
            st.dataframe(
                resumen,
                use_container_width=True,
                hide_index=True,
                height=min(600, 120 + 34 * len(resumen))
            )

            st.markdown("#### Detalle")
            st.dataframe(
                detalle,
                use_container_width=True,
                hide_index=True,
                height=min(800, 120 + 34 * len(detalle))
            )

    with tab_patrones:
        hoy = date.today()
        f_fin = hoy
        f_ini = (hoy.replace(day=1) - timedelta(days=365))  # simple y directo

        df_raw, prep, repes, anual = cargar_paga_para_patrones(st.secrets, f_ini, f_fin)

        # Diagnósticos rápidos
        st.caption(f"PAGA_M01 filas crudas: {len(df_raw)} | prep: {len(prep)} | repeticiones: {len(repes)}")
        if df_raw.empty:
            st.info("No hubo movimientos en PAGA_M01 para el rango seleccionado.")
        elif prep["MES"].dropna().nunique() == 0:
            st.warning("No se pudo calcular MES (revisa FECHA_APLI).")
        elif repes.empty:
            st.warning("No se detectaron patrones que cumplan el mínimo de meses. Ajusta tolerancia o min_meses.")

        # Tablas
        st.subheader("Patrones por mes (repetidos)")
        if not repes.empty:
            st.dataframe(repes, use_container_width=True, hide_index=True)
        else:
            st.dataframe(prep.head(20), use_container_width=True, hide_index=True)

        st.subheader("Mediana anual e inflación YoY (aprox)")
        if not anual.empty:
            st.dataframe(anual, use_container_width=True, hide_index=True)
    
    with tab_vista:
        st.markdown("### Vista unificada:")

        # filtros de fecha con keys únicos
        col1, col2 = st.columns(2)
        with col1:
            f_ini_vista = st.date_input("desde", value=date.today().replace(day=1),
                                        format="YYYY-MM-DD", key="vista_desde")
        with col2:
            f_fin_vista = st.date_input("hasta", value=date.today(),
                                        format="YYYY-MM-DD", key="vista_hasta")

        # botón para cargar vista
        if st.button("Cargar movimientos", key="btn_vista_unificada"):
            df_vista = cargar_vista_paga_prov_cpto(st.secrets, f_ini_vista, f_fin_vista)
            st.session_state["df_vista"] = df_vista

        df_vista = st.session_state.get("df_vista", pd.DataFrame())

        if df_vista.empty:
            st.info("No hay registros cargados o el rango de fechas no tiene movimientos.")
        else:
            # normalización de estatus
            df_vista["APP_STATUS"] = df_vista["APP_STATUS"].astype(str).str.strip().str.lower()
            df_vista["SELECCIONAR"] = df_vista["APP_STATUS"].eq("inicial")

            # orden de columnas
            orden_cols = [
                "SELECCIONAR",
                "APP_STATUS",
                "FECHA_APLI",
                "CVE_PROV",
                "NOMBRE_PROV",
                "NUM_CPTO",
                "NOMBRE_CPTO",
                "CTA_CONT_CPTO",
                "REFER",
                "DOCTO",
                "IMPMON_EXT",
                "NUM_MONED",
                "TCAMBIO",
                "IMPORTE",
                "APP_METODO",
                "APP_UUID",
                "STATUS_MOV",
                "APP_ORIGEN",
                "APP_ADA_CFD_DOC",
                "CVE_FOLIO",
            ]
            orden_cols = [c for c in orden_cols if c in df_vista.columns]
            df_vista = df_vista[orden_cols].copy()

            # Editor (como en Documentos ADA)
            st.markdown("#### Movimientos PAGA_M01 pendientes de contabilizar")
            df_edit_vista = st.data_editor(
                df_vista,
                hide_index=True,
                use_container_width=True,
                disabled=[c for c in df_vista.columns if c != "SELECCIONAR"],
                key="vista_editor_conta",
                height=min(800, 120 + 34 * len(df_vista)),
            )

            # obtener seleccionados
            pendientes = df_edit_vista[df_edit_vista["SELECCIONAR"] == True].copy()
            st.caption(f"Seleccionados: {len(pendientes)} documentos para contabilizar en COI")

            # botón para insertar en COI
            if not pendientes.empty and st.button("📘 Contabilizar en COI", key="btn_contabilizar_coi"):
                ok = fail = 0
                resultados = []
                with st.spinner("Contabilizando en COI..."):
                    for _, r in pendientes.iterrows():
                        #st.write(f"Preparando contabilización de: {r['CVE_PROV']} - {r['REFER']} ({r['IMPORTE']})")
                        #res = insertar_poliza_y_auxiliares(r, st.secrets, debug=False)
                        res = insertar_poliza_y_auxiliares(r, st.secrets, debug=False)  # primero en debug
                        #st.write(res["msg"])
                        
                        resultados.append(res)
                        ok += 1 if res.get("ok") else 0
                        fail += 0 if res.get("ok") else 1

                # mostrar resumen final
                st.success(f"Procesados: {ok} | Fallidos: {fail}")
                if resultados:
                    df_res = pd.DataFrame(resultados)
                    #st.dataframe(df_res, use_container_width=True, hide_index=True)

    with tab_detalles: 
        st.markdown("### Conceptos fiscales filtrados por proveedor y fecha")

        hoy = date.today()
        anio_actual = hoy.year
        meses_nombres = {str(i): calendar.month_name[i].capitalize() for i in range(1, 13)}

        col1, col2, col3 = st.columns([2, 2, 1])
        with col1:
            proveedor = st.text_input("Proveedor (nombre o RFC)")
        with col2:
            meses_sel = st.multiselect(
                "Mes(es) de emisión",
                options=list(meses_nombres.keys()),
                format_func=lambda x: meses_nombres[x],
                placeholder="Selecciona uno o varios meses",
            )
        with col3:
            anio_sel = st.number_input("Año", min_value=2020, max_value=anio_actual + 1, value=anio_actual, step=1)

        if st.button("🔍 Buscar conceptos", key="btn_buscar_conceptos"):
            df_conceptos = cargar_conceptos_filtrados(st.secrets, proveedor.strip() or None, meses_sel or None, anio_sel or None)
            st.session_state["df_conceptos_filtrados"] = df_conceptos

        df_conceptos = st.session_state.get("df_conceptos_filtrados", pd.DataFrame())

        if df_conceptos.empty:
            st.info("No se encontraron conceptos con los filtros aplicados.")
        else:
            # --- Formato numérico ---
            cols_montos = [
                "VALORUNITARIO", "DESCUENTO", "IMPORTE",
                "BASE_IVA", "IVA", "IEPS", "IVA_RET", "IEPS_RET", "ISR"
            ]
            for col in cols_montos:
                if col in df_conceptos.columns:
                    df_conceptos[col] = pd.to_numeric(df_conceptos[col], errors="coerce").fillna(0)
                    df_conceptos[col] = df_conceptos[col].apply(lambda x: f"${x:,.2f}")

            orden_cols = [
                "FECHA_EMISION", "PROVEEDOR", "SERIE", "FOLIO",
                "DESCRIPCION", "CANTIDAD", "UNIDAD",
                "VALORUNITARIO", "DESCUENTO", "IMPORTE",
                "BASE_IVA", "IVA", "IVA_RET", "ISR"
            ]
            orden_cols = [c for c in orden_cols if c in df_conceptos.columns]

            st.dataframe(
                df_conceptos[orden_cols],
                use_container_width=True,
                hide_index=True,
                height=min(1000, 34 * len(df_conceptos) + 120),
            )

            def to_float(series):
                return (
                    series.replace({"[$,]": ""}, regex=True)
                    .astype(float)
                    .sum()
                    if series is not None and not series.empty
                    else 0.0
                )

            total_importe = to_float(df_conceptos["IMPORTE"])
            total_iva = to_float(df_conceptos["IVA"]) if "IVA" in df_conceptos.columns else 0.0
            total_iva_ret = to_float(df_conceptos["IVA_RET"]) if "IVA_RET" in df_conceptos.columns else 0.0
            total_isr = to_float(df_conceptos["ISR"]) if "ISR" in df_conceptos.columns else 0.0

            # Mostrar resultados formateados
            st.markdown("---")
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("💰 Total general", f"${total_importe:,.2f}")
            col2.metric("🧾 Total IVA", f"${total_iva:,.2f}")
            col3.metric("↩️ Total IVA Retenido", f"${total_iva_ret:,.2f}")
            col4.metric("💸 Total ISR", f"${total_isr:,.2f}")

            # --- Exportar a Excel ---
            import io
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                df_conceptos.to_excel(writer, index=False, sheet_name="Conceptos filtrados")
            excel_data = output.getvalue()

            st.download_button(
                label="📤 Exportar a Excel",
                data=excel_data,
                file_name="conceptos_filtrados.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
    with tab_insertaSAE: 
        insertarSAE()
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