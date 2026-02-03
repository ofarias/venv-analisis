import streamlit as st
import pandas as pd
from io import BytesIO
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode

from controllers.dashboard_controller import get_rep_ventas_lotes_df


def _to_excel_bytes(df: pd.DataFrame) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="rep_ventas_lotes")
    return output.getvalue()


def mostrar_tab_rep_ventas_lotes():
    st.subheader("reporte de ventas por lotes")

    c1, c2, c3 = st.columns([1.2, 1.2, 1])

    with c1:
        fecha_ini = st.date_input("fecha inicio", value=pd.to_datetime("2025-12-01").date())

    with c2:
        fecha_fin = st.date_input("fecha fin", value=pd.to_datetime("2025-12-31").date())

    with c3:
        st.caption("")
        ejecutar = st.button("consultar", use_container_width=True)

    if not ejecutar:
        st.info("selecciona fechas y presiona consultar.")
        return

    df = get_rep_ventas_lotes_df(fecha_ini=fecha_ini, fecha_fin=fecha_fin)

    if df is None or df.empty:
        st.info("no hay datos para el rango seleccionado.")
        return

    df.columns = [str(c).lower() for c in df.columns]

    st.caption(f"registros: {len(df):,}")

    gb = GridOptionsBuilder.from_dataframe(df)

    gb.configure_default_column(
        editable=False,
        groupable=True,
        filter=True,
        sortable=True,
        resizable=True,
        wrapText=False,
        autoHeight=False,
    )

    gb.configure_pagination(paginationAutoPageSize=False, paginationPageSize=25)
    gb.configure_side_bar()

    # anclar columnas clave
    for col in ["estatus", "cve_doc", "fecha_doc", "nombre", "descr", "lote", "cve_art", "moneda"]:
        if col in df.columns:
            gb.configure_column(col, pinned="left")

    # formato numérico (si existen)
    cols_num = [
        "cantidadlote",
        "precio mn",
        "precio usd",
        "tipo de cambio",
        "subtotal documentos mn",
        "subtotal documentos usd",
        "impuesto documentos mn ",
        "impuesto documentos usd",
        "total documentos en mn",
        "total documentos en usd",
        "subtotal mn (todos los documentos)",
        "impuesto mn (todos los documentos)",
        "total mn (todos los documentos)",
    ]

    for col in cols_num:
        if col in df.columns:
            gb.configure_column(col, type=["numericColumn", "numberColumnFilter"], valueFormatter="x.toLocaleString()")

    grid_options = gb.build()

    grid = AgGrid(
        df,
        gridOptions=grid_options,
        enable_enterprise_modules=True,
        update_mode=GridUpdateMode.NO_UPDATE,
        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
        fit_columns_on_grid_load=True,
        height=520,
        width="100%",
    )

    df_grid = pd.DataFrame(grid.get("data", df))

    xlsx_bytes = _to_excel_bytes(df_grid)

    st.download_button(
        label="descargar excel",
        data=xlsx_bytes,
        file_name=f"rep_ventas_lotes_{pd.to_datetime(fecha_ini).strftime('%Y%m%d')}_{pd.to_datetime(fecha_fin).strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )