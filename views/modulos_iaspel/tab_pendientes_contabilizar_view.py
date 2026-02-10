# views/modulos_iaspel/tab_pendientes_contabilizar_view.py

import streamlit as st
import pandas as pd
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode

from controllers.dashboard_controller import (
    get_pendientes_contabilizar_df,
    get_prorrateos_mysql_df,
    get_detalle_prorrateo_df,
    contabilizar_pendiente_en_coi,
)


def mostrar_tab_pendientes_contabilizar():
    ### Nuvevo tab: pendientes de contabilizar (paga_m01 vs prorrateos) ###
    if "pend_grid_refresh" not in st.session_state:
        st.session_state["pend_grid_refresh"] = 0
    ##### FIN NUEVO TAB #####

    st.subheader("pendientes de contabilizar (paga_m01 vs prorrateos)")

    # 1) pendientes desde firebird (sae) ya con columnas en minúsculas (model)
    df_pend = get_pendientes_contabilizar_df()

    if df_pend.empty:
        st.info(
            "no se encontraron registros en paga_m01 "
            "con (afec_coi <> 'A'), año(fecha_apli) >= 2025 y num_cpto <> 1."
        )
        return

    st.caption(f"registros pendientes (paga_m01): {len(df_pend)}")

    # columnas clave en pendientes
    for col in ["cve_prov", "num_cpto"]:
        if col not in df_pend.columns:
            st.error(
                f"no se encontró la columna '{col}' en el dataframe de paga_m01.\n"
                f"columnas disponibles: {list(df_pend.columns)}"
            )
            return

    # 2) prorrateos desde mysql (catálogo completo)
    df_pr = get_prorrateos_mysql_df(limit=50000, offset=0, filtros={})

    if df_pr.empty:
        st.warning("no se encontraron prorrateos en la tabla de mysql.")
        st.dataframe(df_pend, use_container_width=True, height=500)
        return

    # ⬅️ filtro: solo prorrateos con estatus != 9 (excluimos bajas)
    if "estatus" in df_pr.columns:
        df_pr = df_pr[df_pr["estatus"] != 9].copy()

    # validamos columnas clave en prorrateos
    if "cdcvepro" not in df_pr.columns:
        st.error(
            "no se encontró la columna 'cdcvepro' en el dataframe de prorrateos.\n"
            f"columnas disponibles: {list(df_pr.columns)}"
        )
        return

    if "cdnrocon" not in df_pr.columns:
        st.error(
            "no se encontró la columna 'cdnrocon' en el dataframe de prorrateos.\n"
            f"columnas disponibles: {list(df_pr.columns)}"
        )
        return

    # 3) normalizamos claves antes de comparar
    df_pend_norm = df_pend.copy()
    df_pend_norm["cve_prov_key"] = (
        df_pend_norm["cve_prov"].astype(str).str.strip().str.lower()
    )
    df_pend_norm["num_cpto_key"] = (
        df_pend_norm["num_cpto"].astype(str).str.strip().str.lower()
    )

    df_pr_norm = df_pr.copy()

    # si el nombre del prorrateo viene como 'nombre', lo renombramos
    if "nombre" in df_pr_norm.columns:
        df_pr_norm = df_pr_norm.rename(columns={"nombre": "nombre_prorrateo"})

    df_pr_norm["cdcvepro_key"] = (
        df_pr_norm["cdcvepro"].astype(str).str.strip().str.lower()
    )
    df_pr_norm["cdnrocon_key"] = (
        df_pr_norm["cdnrocon"].astype(str).str.strip().str.lower()
    )

    # aseguramos que tmstmp sea datetime si existe
    if "tmstmp" in df_pr_norm.columns:
        df_pr_norm["tmstmp"] = pd.to_datetime(
            df_pr_norm["tmstmp"], errors="coerce"
        )

    # 3.1: elegir UN solo prorrateo "sugerido" por par (cdcvepro_key, cdnrocon_key)
    sort_cols = ["cdcvepro_key", "cdnrocon_key"]
    sort_asc = [True, True]

    if "tmstmp" in df_pr_norm.columns:
        sort_cols.append("tmstmp")
        sort_asc.append(False)  # más reciente primero

    if "idnumpon" in df_pr_norm.columns:
        sort_cols.append("idnumpon")
        sort_asc.append(False)  # idnumpon más grande primero

    df_pr_sorted = df_pr_norm.sort_values(sort_cols, ascending=sort_asc)

    cols_pr = ["cdcvepro_key", "cdnrocon_key"]
    for col in ["idnumpon", "nombre_prorrateo", "tmstmp"]:
        if col in df_pr_sorted.columns:
            cols_pr.append(col)

    df_pr_best = df_pr_sorted[cols_pr].drop_duplicates(
        subset=["cdcvepro_key", "cdnrocon_key"], keep="first"
    )

    # 4) merge normalizado por las dos llaves (and)
    df_merge = df_pend_norm.merge(
        df_pr_best,
        how="left",
        left_on=["cve_prov_key", "num_cpto_key"],
        right_on=["cdcvepro_key", "cdnrocon_key"],
    )

    # indicador de si existe prorrateo (match real por ambas llaves)
    if "idnumpon" in df_merge.columns:
        df_merge["tiene_prorrateo"] = (
            df_merge["idnumpon"].notna()
            & df_merge["cdcvepro_key"].notna()
            & df_merge["cdnrocon_key"].notna()
        )
    else:
        df_merge["tiene_prorrateo"] = (
            df_merge["cdcvepro_key"].notna()
            & df_merge["cdnrocon_key"].notna()
        )

    # 4.1 inicializar / recuperar dataframe completo en session_state
    if "df_pend_full" not in st.session_state:
        df_full = df_merge.copy().reset_index(drop=True)
        # identificador estable por fila
        df_full["row_id"] = df_full.index

        # columna editable: prorrateo seleccionado (inicialmente el sugerido)
        if "idnumpon" in df_full.columns:
            df_full["idnumpon_seleccionado"] = df_full["idnumpon"]
        else:
            df_full["idnumpon_seleccionado"] = pd.NA

        st.session_state["df_pend_full"] = df_full
    else:
        df_full = st.session_state["df_pend_full"]

    # 5) resumen
    total_pend = len(df_full)
    con_prorrateo = int(df_full["tiene_prorrateo"].sum())
    sin_prorrateo = total_pend - con_prorrateo

    c1, c2, c3 = st.columns(3)
    c1.metric("pendientes totales", total_pend)
    c2.metric("con prorrateo sugerido", con_prorrateo)
    c3.metric("sin prorrateo sugerido", sin_prorrateo)

    cbtn1, cbtn2 = st.columns([1, 6])
    with cbtn1:
        if st.button("recargar pendientes", key="btn_recargar_pendientes"):
            if "df_pend_full" in st.session_state:
                del st.session_state["df_pend_full"]
            st.session_state["pend_grid_refresh"] += 1
            st.rerun()

    st.markdown("#### detalle de pendientes (con indicador de prorrateo)")

    solo_sin = st.checkbox(
        "mostrar solo pendientes sin prorrateo sugerido",
        value=False,
        key="pend_sin_prorrateo",
    )

    df_vista = df_full.copy()
    if solo_sin:
        df_vista = df_vista[df_vista["tiene_prorrateo"] == False]

    # formateo de montos para la vista (2 decimales con coma)
    cols_montos = [
        "impmon_ext",
        "importe",
        "impuesto1",
        "impuesto2",
        "impuesto3",
        "impuesto4",
        "subtotal",
        "Impmon_ext",
        "Importe",
        "Impuesto1",
        "Impuesto2",
        "Impuesto3",
        "Impuesto4",
        "Subtotal",
    ]

    df_vista_fmt = df_vista.copy()
    for col in cols_montos:
        if col in df_vista_fmt.columns:
            # guardamos qué valores no eran nulos originalmente
            mask_notnull = df_vista_fmt[col].notna()
            # convertimos a número solo los que tienen dato
            df_vista_fmt.loc[mask_notnull, col] = pd.to_numeric(
                df_vista_fmt.loc[mask_notnull, col],
                errors="coerce",
            )
            # formateamos con 2 decimales
            df_vista_fmt.loc[mask_notnull, col] = df_vista_fmt.loc[mask_notnull, col].map(
                lambda x: f"{float(x):,.2f}"
            )

    def _pick(*names):
        for n in names:
            if n in df_vista_fmt.columns:
                return n
        return None

    orden = [
        _pick("cve_prov"),
        _pick("nombre"),
        _pick("rfc"),
        _pick("num_cpto"),
        _pick("descr"),
        _pick("tiene_prorrateo"),
        _pick("idnumpon_seleccionado"),
        _pick("no_factura"),
        _pick("refer"),
        _pick("fecha_apli"),
        _pick("fechaelab"),
        _pick("moneda"),
        _pick("subtotal"),
        _pick("impuesto4"),
        _pick("ret_isr"),
        _pick("impuesto2"),
        _pick("ret_iva"),
        _pick("impuesto3"),
        _pick("ieps"),
        _pick("impuesto1"),
        _pick("importe"),
        _pick("tcambio"),
        _pick("impmon_ext"),
        _pick("app_uuid"),
        _pick("idnumpon"),
        _pick("tmstmp"),
    ]

    orden = [c for c in orden if c]
    resto = [c for c in df_vista_fmt.columns if c not in orden]
    df_vista_fmt = df_vista_fmt[orden + resto]
    # ======= FIN OPCIÓN 1 =======

    # 6) tabla con AgGrid
    # 6) tabla con AgGrid (readonly excepto selección)
    #gb = GridOptionsBuilder.from_dataframe(df_vista)
    gb = GridOptionsBuilder.from_dataframe(df_vista_fmt)

    # columnas por defecto: solo lectura
    gb.configure_default_column(editable=False, resizable=True)

    # seleccionamos una fila a la vez
    gb.configure_selection("single", use_checkbox=True)

    # ocultamos columnas técnicas / llaves internas, pero las mantenemos en datos
    for col in [
        "cve_prov_key",
        "num_cpto_key",
        "cdcvepro_key",
        "cdnrocon_key",
    ]:
        if col in df_vista.columns:
            gb.configure_column(col, hide=True, editable=False)

    if "row_id" in df_vista.columns:
        gb.configure_column("row_id", hide=True, editable=False)

    def set_width_if_exists(col, chars):
        if col in df_vista_fmt.columns:
            px = chars * 8  # aprox 8 px por carácter
            gb.configure_column(col, width=px, minWidth=px, maxWidth=px)

    # ejemplos que pediste
    set_width_if_exists("cve_prov", 10)
    set_width_if_exists("nombre", 30)      # ~30 caracteres
    set_width_if_exists("rfc", 15)         # ~18 caracteres
    set_width_if_exists("num_cpto", 5)     # ~5 caracteres
    set_width_if_exists("descr", 25)     # ~5 caracteres
    set_width_if_exists("no_factura", 15)
    set_width_if_exists("fechaelab", 20)
    set_width_if_exists("fecha_apli", 20)
    set_width_if_exists("moneda", 10)
    set_width_if_exists("subtotal", 15)
    set_width_if_exists("impuesto1", 15)
    set_width_if_exists("impuesto2", 15)
    set_width_if_exists("impuesto3", 15)
    set_width_if_exists("impuesto4", 15)
    set_width_if_exists("importe", 15)
    set_width_if_exists("impmon_ext", 15)


    # si quieres mostrar el prorrateo seleccionado en la tabla:
    if "idnumpon_seleccionado" in df_vista.columns:
        gb.configure_column(
            "idnumpon_seleccionado",
            headerName="id prorrateo seleccionado",
            editable=False,   # de momento solo lectura; luego lo podemos abrir
        )

    grid_options = gb.build()

    #grid_response = AgGrid(
    #    df_vista_fmt,
    #    gridOptions=grid_options,
    #    update_mode=GridUpdateMode.SELECTION_CHANGED,
    #    data_return_mode="AS_INPUT",
    #    fit_columns_on_grid_load=True,
    #    height=450,
    #    key="agrid_pendientes_prorrateo",
    #)
    


    grid_response = AgGrid(
        df_vista_fmt,
        gridOptions=grid_options,
        update_mode=GridUpdateMode.SELECTION_CHANGED,
        data_return_mode="AS_INPUT",
        fit_columns_on_grid_load=True,
        height=450,
        key=f"agrid_pendientes_prorrateo_{st.session_state['pend_grid_refresh']}",
    )

    seleccionados = grid_response.get("selected_rows", [])

    if isinstance(seleccionados, pd.DataFrame):
        seleccionados_list = seleccionados.to_dict("records")
    else:
        seleccionados_list = seleccionados or []


    st.download_button(
        "descargar csv (pendientes + prorrateo)",
        data=df_vista.drop(
            columns=["cve_prov_key", "num_cpto_key", "cdcvepro_key", "cdnrocon_key"],
            errors="ignore",
        ).to_csv(index=False).encode("utf-8"),
        file_name="pendientes_contabilizar_vs_prorrateos.csv",
        mime="text/csv",
        key="download_pendientes_vs_prorrateos",
    )

    st.divider()

    # 7) selección de prorrateo para el documento seleccionado
    if len(seleccionados_list) > 0:
        fila_sel = seleccionados_list[0]
        row_id = fila_sel.get("row_id", None)

        st.markdown("#### selección de prorrateo para el documento")

        # info básica del documento
        st.write(
            f"**proveedor:** {fila_sel.get('cve_prov', '')}  "
            f"**concepto:** {fila_sel.get('num_cpto', '')}  "
            f"**factura:** {fila_sel.get('no_factura', '')}  "
            f"**refer:** {fila_sel.get('refer', '')}"
        )

        # buscamos prorrateos candidatos para este proveedor + concepto
        cve_key = fila_sel.get("cve_prov_key", "")
        cpto_key = fila_sel.get("num_cpto_key", "")

        df_cand = df_pr_norm[
            (df_pr_norm["cdcvepro_key"] == cve_key)
            & (df_pr_norm["cdnrocon_key"] == cpto_key)
        ].copy()

        if df_cand.empty:
            st.info(
                "no hay prorrateos candidatos para este proveedor + concepto.\n"
                "puedes crear uno nuevo en la pestaña de configuración."
            )
            return

        # armamos opciones "idnumpon - nombre"
        opciones = []
        map_label_to_id = {}

        for _, r in df_cand.iterrows():
            idp = r.get("idnumpon", None)
            if pd.isna(idp):
                continue
            # buscamos una columna descriptiva razonable
            descr_val = ""
            if "descr" in df_cand.columns:
                descr_val = str(r.get("descr", "") or "").strip()
            elif "dsnombre" in df_cand.columns:
                descr_val = str(r.get("dsnombre", "") or "").strip()
            elif "nombre_prorrateo" in df_cand.columns:
                descr_val = str(r.get("nombre_prorrateo", "") or "").strip()

            label = f"{int(idp)} - {descr_val}"
            opciones.append(label)
            map_label_to_id[label] = int(idp)

        if not opciones:
            st.info("no hay prorrateos válidos (idnumpon) para este documento.")
            return

        # prorrateo actualmente seleccionado (si existe)
        current_sel = None
        if row_id is not None and "idnumpon_seleccionado" in df_full.columns:
            try:
                current_sel = df_full.loc[
                    df_full["row_id"] == row_id, "idnumpon_seleccionado"
                ].iloc[0]
            except Exception:
                current_sel = None

        default_index = 0
        if current_sel is not None and not pd.isna(current_sel):
            for i, label in enumerate(opciones):
                if map_label_to_id[label] == int(current_sel):
                    default_index = i
                    break

        label_choice = st.selectbox(
            "prorrateo a aplicar a este documento",
            opciones,
            index=default_index,
            key=f"sel_prorrateo_row_{row_id}",
        )

        # mostrar detalle del prorrateo seleccionado
        id_prorr_sel = map_label_to_id.get(label_choice, None)
        if id_prorr_sel is not None:
            st.markdown("##### detalle del prorrateo seleccionado")

            df_det_sel = get_detalle_prorrateo_df(int(id_prorr_sel))

            if df_det_sel.empty:
                st.info("este prorrateo no tiene detalle configurado todavía.")
            else:
                df_det_vista = df_det_sel.copy()

                if "dsctacon" in df_det_vista.columns:
                    df_det_vista = df_det_vista.rename(
                        columns={"dsctacon": "cuenta contable"}
                    )
                if "idunineg" in df_det_vista.columns:
                    df_det_vista = df_det_vista.rename(
                        columns={"idunineg": "id unidad"}
                    )
                if "flporuni" in df_det_vista.columns:
                    df_det_vista = df_det_vista.rename(
                        columns={"flporuni": "porcentaje"}
                    )

                st.dataframe(df_det_vista, use_container_width=True, height=260)

        if st.button(
            "contabilizar",
            key=f"btn_contabilizar_row_{row_id}",
            type="primary",
        ):
            nuevo_id = map_label_to_id.get(label_choice, None)
            if nuevo_id is None:
                st.error("no se pudo interpretar el prorrateo seleccionado.")
                return

            if row_id is None:
                st.error("no se pudo identificar la fila seleccionada.")
                return

            # actualizamos df_full en memoria con el prorrateo elegido
            df_full.loc[df_full["row_id"] == row_id, "idnumpon_seleccionado"] = int(
                nuevo_id
            )

            # actualizar nombre_prorrateo con el del elegido si existe
            try:
                nom_sel = df_cand.loc[
                    df_cand["idnumpon"] == nuevo_id, "nombre_prorrateo"
                ].iloc[0]
                df_full.loc[
                    df_full["row_id"] == row_id, "nombre_prorrateo"
                ] = nom_sel
            except Exception:
                pass

            st.session_state["df_pend_full"] = df_full

            # buscar la fila completa del documento para pasarla al controller
            try:
                row_doc = df_full[df_full["row_id"] == row_id].iloc[0]
            except Exception:
                st.error("no se pudo recuperar la fila del documento para contabilizar.")
                return

            # llamada al controller → model → coi
            res = contabilizar_pendiente_en_coi(row_doc, prorrateo_id=int(nuevo_id), debug=False)

            ##if res.get("ok"):
            ##    msg = res.get("msg", "documento contabilizado correctamente.")
            ##    st.success(msg)
            ##    # si quieres, mostrar info de la póliza creada
            ##    pol = res.get("poliza")
            ##    if isinstance(pol, dict):
            ##        st.write(
            ##            f"póliza: {pol.get('tipo','')}-"
            ##            f"{pol.get('num','')}/{pol.get('periodo','')}-"
            ##            f"{pol.get('ejercicio','')}"
            ##        )
            ##    # sacamos el dataframe de sesión para forzar recarga desde bd
            ##    if "df_pend_full" in st.session_state:
            ##        del st.session_state["df_pend_full"]
            ##    st.rerun()
            ##else:
            ##    st.error(res.get("msg", "hubo un error al contabilizar en coi."))
            if res.get("ok"):
                msg = res.get("msg", "documento contabilizado correctamente.")
                st.success(msg)
                pol = res.get("poliza")
                if isinstance(pol, dict):
                    st.write(
                        f"póliza: {pol.get('tipo','')}-"
                        f"{pol.get('num','')}/{pol.get('periodo','')}-"
                        f"{pol.get('ejercicio','')}"
                    )
                # limpiar selección de prorrateo de esta fila
                sel_key = f"sel_prorrateo_row_{row_id}"
                if sel_key in st.session_state:
                    del st.session_state[sel_key]
                # forzar recarga de pendientes y de la tabla (nuevo key en aggrid)
                if "df_pend_full" in st.session_state:
                    del st.session_state["df_pend_full"]
                st.session_state["pend_grid_refresh"] += 1

                st.rerun()
            else:
                st.error(res.get("msg", "hubo un error al contabilizar en coi."))