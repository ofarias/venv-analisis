# views/modulos_iaspel/tab_contabilizados_view.py

import streamlit as st
import pandas as pd
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode

from controllers.dashboard_controller import (
    get_documentos_contabilizados_df,   
    liberar_documento_contabilizado,    
)

def mostrar_tab_contabilizados():
    """
    pestaña para manejar documentos ya contabilizados (APP_STATUS = 'Contabilidad')
    y permitir cambiar AFEC_COI de 'A' a '' en PAGA_M01.
    """
    st.subheader("documentos contabilizados (prorrateos)")

    # 1) traemos los documentos contabilizados desde el controller
    df = get_documentos_contabilizados_df()

    if df is None or len(df) == 0:
        st.info("no se encontraron documentos con APP_STATUS = 'Contabilidad'.")
        return

    st.caption(f"documentos contabilizados encontrados: {len(df)}")

    df_vista = df.copy()

    # 2) formateo de montos si existen
    cols_montos = [
        "IMPORTE", "importe",
        "IMPUESTO1", "IMPUESTO2", "IMPUESTO3", "IMPUESTO4",
        "SUBTOTAL", "subtotal",
    ]
    for col in cols_montos:
        if col in df_vista.columns:
            mask_notnull = df_vista[col].notna()
            df_vista.loc[mask_notnull, col] = pd.to_numeric(
                df_vista.loc[mask_notnull, col],
                errors="coerce",
            )
            df_vista.loc[mask_notnull, col] = df_vista.loc[mask_notnull, col].map(
                lambda x: f"{float(x):,.2f}"
            )

    # 3) identificador estable de fila
    if "row_id" not in df_vista.columns:
        df_vista = df_vista.reset_index(drop=True)
        df_vista["row_id"] = df_vista.index

    # 4) grid con selección de UNA fila
    gb = GridOptionsBuilder.from_dataframe(df_vista)
    gb.configure_default_column(editable=False, resizable=True)
    gb.configure_selection("single", use_checkbox=True)

    # oculta columnas técnicas si las hay
    for col in ["row_id"]:
        if col in df_vista.columns:
            gb.configure_column(col, hide=True, editable=False)

    # ajustar anchos típicos
    def set_width_if_exists(col, chars):
        if col in df_vista.columns:
            px = chars * 8
            gb.configure_column(col, width=px, minWidth=px, maxWidth=px)

    set_width_if_exists("CVE_PROV", 10)
    set_width_if_exists("REFER", 15)
    set_width_if_exists("NO_FACTURA", 15)
    set_width_if_exists("FECHA_APLI", 20)
    set_width_if_exists("IMPORTE", 15)
    set_width_if_exists("APP_STATUS", 15)
    set_width_if_exists("AFEC_COI", 10)

    grid_options = gb.build()

    grid_response = AgGrid(
        df_vista,
        gridOptions=grid_options,
        update_mode=GridUpdateMode.SELECTION_CHANGED,
        data_return_mode="AS_INPUT",
        fit_columns_on_grid_load=True,
        height=450,
        key="agrid_contabilizados",
    )

    seleccionados = grid_response.get("selected_rows", [])

    if isinstance(seleccionados, pd.DataFrame):
        seleccionados_list = seleccionados.to_dict("records")
    else:
        seleccionados_list = seleccionados or []

    # 5) export a csv
    st.download_button(
        "descargar csv (documentos contabilizados)",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name="documentos_contabilizados.csv",
        mime="text/csv",
        key="download_contabilizados",
    )

    st.divider()

    # 6) si hay algo seleccionado, mostramos datos y el botón para cambiar AFEC_COI
    if len(seleccionados_list) == 0:
        st.info("selecciona un documento para liberar AFEC_COI.")
        return

    fila_sel = seleccionados_list[0]

    st.markdown("#### documento seleccionado")

    cve_prov = fila_sel.get("CVE_PROV") or fila_sel.get("cve_prov", "")
    refer = fila_sel.get("REFER") or fila_sel.get("refer", "")
    no_factura = fila_sel.get("NO_FACTURA") or fila_sel.get("no_factura", "")
    app_status = fila_sel.get("APP_STATUS") or fila_sel.get("app_status", "")
    afec_coi = fila_sel.get("AFEC_COI") or fila_sel.get("afec_coi", "")

    st.write(
        f"**proveedor:** {cve_prov}  "
        f"**refer:** {refer}  "
        f"**factura:** {no_factura}  "
        f"**APP_STATUS:** {app_status}  "
        f"**AFEC_COI actual:** '{afec_coi}'"
    )

    st.warning(
        "al confirmar se actualizará AFEC_COI de 'A' a '' en PAGA_M01 "
        "para este documento."
    )

    if st.button(
        "liberar AFEC_COI (poner en blanco)",
        type="primary",
        key="btn_liberar_afec_coi",
    ):
        # pasamos TODA la fila seleccionada al controller, como en el tab de pendientes
        res = liberar_documento_contabilizado(fila_sel)

        if isinstance(res, dict) and res.get("ok"):
            msg = res.get("msg", "se actualizó AFEC_COI correctamente.")
            st.success(msg)
            st.rerun()
        else:
            msg = ""
            if isinstance(res, dict):
                msg = res.get("msg", "")
            if not msg:
                msg = "hubo un error al intentar actualizar AFEC_COI."
            st.error(msg)