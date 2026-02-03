# views/modulos_iaspel/tab_poliza_ventas_view.py

import streamlit as st
import pandas as pd

from controllers.dashboard_controller import get_poliza_ventas_df, contabilizar_poliza_ventas_df


def mostrar_tab_poliza_ventas():
    st.subheader("póliza ventas")

    # filtro de fecha
    fecha = st.date_input(
        "fecha de aplicación",
        key="poliza_ventas_fecha",
    )
    df = pd.DataFrame()
    if fecha:
        df = get_poliza_ventas_df(fecha)

        if df.empty:
            st.info("no se encontraron ventas para la fecha seleccionada.")
        else:
            st.caption(f"registros encontrados: {len(df)}")
            # solo vista: formato miles y 2 decimales
            df_view = df.copy()
            num_cols = df_view.select_dtypes(include=["number"]).columns
            for c in num_cols:
                if c == "tcambio":
                    continue
                df_view[c] = df_view[c].map(lambda x: f"{x:,.2f}" if pd.notnull(x) else "")

            if "tcambio" in df_view.columns:
                df_view["tcambio"] = df_view["tcambio"].map(
                    lambda x: f"{x:,.4f}" if pd.notnull(x) else ""
                )
            st.dataframe(df_view, use_container_width=True, height=500)
        
    else:
        st.info("selecciona una fecha para consultar las ventas.")

    st.divider()
    # botón contabilizar (por ahora solo placeholder)

    if st.button("contabilizar"):
        df_cont = df.copy()
        df_cont["fecha_apli"] = fecha   # aquí agregas la columna al df que se envía
        res = contabilizar_poliza_ventas_df(df_cont)
        if res.get("ok"):
            st.success(res.get("msg", "póliza creada."))
        else:
            st.error(res.get("msg", "no se pudo crear la póliza."))