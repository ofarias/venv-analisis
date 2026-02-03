#tab_poliza_costo_ventas_view.py

import streamlit as st
import pandas as pd
from datetime import date
from controllers.dashboard_controller import obtener_costos_venta_por_fecha, contabilizar_poliza_ventas_costo_df, obtener_costos_venta_por_fecha_remisiones


def mostrar_tab_poliza_costo_venta():
    st.subheader("Póliza de costo de venta")

    fecha = st.date_input("Fecha de la póliza", value=date.today())
    
    df_costos = obtener_costos_venta_por_fecha(fecha)

    df_costos_remisiones = obtener_costos_venta_por_fecha_remisiones(fecha)

    df_unido = pd.concat([df_costos, df_costos_remisiones], ignore_index=True)

    df_view = df_unido.copy()
    df_view = df_view.rename(columns={"DEPTO": "Unidad de negocio"})

    num_cols = df_view.select_dtypes(include=["number"]).columns

    # 1) todos a 2 decimales excepto tcambio
    for c in num_cols:
        if c == "tcambio":
            continue
        df_view[c] = df_view[c].map(lambda x: f"{x:,.2f}" if pd.notnull(x) else "")

    # 2) tcambio a 4 decimales (si existe)
    if "tcambio" in df_view.columns:
        df_view["tcambio"] = df_view["tcambio"].map(lambda x: f"{x:,.4f}" if pd.notnull(x) else "")

    st.dataframe(df_view, use_container_width=True, height=500)

    if st.button("Generar póliza de costo de venta"):
        
        if df_unido.empty:
            st.warning("No hay costos de venta para esa fecha.")
            return

        res = contabilizar_poliza_ventas_costo_df(df_unido)
        if res.get("ok"):
            st.success(res["msg"])
        else:
            st.error(res["msg"])