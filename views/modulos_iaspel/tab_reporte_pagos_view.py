# views/modulos_iaspel/tab_reporte_pagos_view.py
from __future__ import annotations

from datetime import date
from io import BytesIO

import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode

from controllers.dashboard_controller import get_reporte_pagos_df


def _to_excel_bytes(df: pd.DataFrame) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="pagos")
    return output.getvalue()


def _build_grid(df: pd.DataFrame):
    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_default_column(
        resizable=True,
        filter=True,
        sortable=True,
        minWidth=110,
    )
    gb.configure_pagination(paginationAutoPageSize=False, paginationPageSize=50)
    gb.configure_grid_options(domLayout="normal")
    return gb.build()


def _clean_bucket(x) -> str:
    # normaliza valores tipo: "0-15", "0-15 ", "0–15", "0-15\t"
    if x is None:
        return ""
    s = str(x).strip().lower()
    s = s.replace("–", "-").replace("—", "-")
    s = " ".join(s.split())
    return s


def mostrar_tab_reporte_pagos():
    st.subheader("reporte pronóstico de pagos (sae)")

    c1, c2, c3 = st.columns([1.2, 1.2, 2.0])
    corte = c1.date_input("corte", value=date.today(), key="rp_corte")
    proveedor_like = c2.text_input("proveedor contiene", value="", key="rp_prov_like")

    buckets_default = ["0-15", "16-30", "31-60", "61-90", "90+", "vencido", "pagado"]
    buckets_sel = c3.multiselect(
        "bucket pronóstico",
        options=buckets_default,
        default=["0-15", "16-30", "31-60", "61-90", "90+", "vencido", "pagado"],
        key="rp_buckets",
    )

    c4, c5, c6 = st.columns([1.2, 1.2, 2.0])
    clasif_like = c4.text_input("clasificación contiene", value="", key="rp_clasif_like")
    solo_pendiente = c5.checkbox("solo pendiente (saldo > 10)", value=False, key="rp_solo_pend")
    moneda_sel = c6.selectbox("moneda", options=["todas", "mn", "me"], index=0, key="rp_moneda")

    # data
    try:
        df = get_reporte_pagos_df(corte=corte)
    except TypeError:
        df = get_reporte_pagos_df(corte)

    if df is None or df.empty:
        st.info("sin datos para el corte seleccionado")
        return

    # normaliza columnas
    df.columns = [str(c).strip().lower() for c in df.columns]

    # normaliza bucket para que el multiselect funcione aunque venga con espacios o guiones raros
    if "bucket_pronostico" in df.columns:
        df["bucket_pronostico"] = df["bucket_pronostico"].apply(_clean_bucket)

    # muestra un diagnóstico rápido (puedes quitarlo después)
    if "bucket_pronostico" in df.columns:
        st.caption("buckets encontrados en datos (diagnóstico)")
        st.write(sorted(df["bucket_pronostico"].dropna().unique().tolist()))

    # aplica filtros
    if proveedor_like.strip() and "nombre" in df.columns:
        df = df[df["nombre"].astype(str).str.contains(proveedor_like.strip(), case=False, na=False)]

    if clasif_like.strip() and "clasificacionproveedor" in df.columns:
        df = df[df["clasificacionproveedor"].astype(str).str.contains(clasif_like.strip(), case=False, na=False)]

    if buckets_sel and "bucket_pronostico" in df.columns:
        buckets_sel_norm = [_clean_bucket(b) for b in buckets_sel]
        df = df[df["bucket_pronostico"].isin(buckets_sel_norm)]

    if solo_pendiente and "saldo" in df.columns:
        df = df[df["saldo"].fillna(0) > 10]

    if moneda_sel != "todas":
        # primero num_moned si existe
        if "num_moned" in df.columns:
            if moneda_sel == "mn":
                df = df[df["num_moned"].fillna(1).astype(int) == 1]
            elif moneda_sel == "me":
                df = df[df["num_moned"].fillna(1).astype(int) != 1]
        # si no existe, caemos a moneda (texto)
        elif "moneda" in df.columns:
            if moneda_sel == "mn":
                df = df[df["moneda"].astype(str).str.contains("peso", case=False, na=False)]
            elif moneda_sel == "me":
                df = df[~df["moneda"].astype(str).str.contains("peso", case=False, na=False)]

    if df.empty:
        st.warning("sin filas con los filtros actuales")
        return

    # tabla detalle
    st.caption("detalle")
    grid_options = _build_grid(df)
    AgGrid(
        df,
        gridOptions=grid_options,
        update_mode=GridUpdateMode.NO_UPDATE,
        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
        fit_columns_on_grid_load=False,
        height=520,
    )

    # descarga excel
    excel_bytes = _to_excel_bytes(df)
    st.download_button(
        "descargar excel",
        data=excel_bytes,
        file_name=f"reporte_pagos_{corte.isoformat()}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="rp_down_excel",
    )