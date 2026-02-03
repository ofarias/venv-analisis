# views/modulos_iaspel/gastos_view.py
import streamlit as st
import pandas as pd
from controllers.gastos_controller import cargar_gastos, kpis, pivote_por_proveedor_mes, top_conceptos, outliers_iqr

def pantalla_gastos():
    st.title("análisis de gastos")

    c1, c2, c3, c4 = st.columns(4)
    fecha_desde = c1.date_input("desde", None)
    fecha_hasta = c2.date_input("hasta", None)
    proveedor   = c3.text_input("proveedor (cve_prov)", "")
    concepto    = c4.number_input("concepto (num_cpto)", min_value=0, value=0, step=1, format="%d")
    c5, c6, c7 = st.columns(3)
    moneda      = c5.number_input("moneda (num_moned)", min_value=0, value=0, step=1, format="%d")
    estatus     = c6.selectbox("estatus", ["", "A", "B"], index=0)
    btn         = c7.button("consultar")

    if btn:
        f1 = str(fecha_desde) if fecha_desde else None
        f2 = str(fecha_hasta) if fecha_hasta else None
        mon = int(moneda) if moneda else None
        cpto = int(concepto) if concepto else None
        prov = proveedor.strip() or None
        st.info("consultando datos...")

        df = cargar_gastos(f1, f2, prov, cpto if cpto != 0 else None, mon if mon != 0 else None, estatus or None)

        if df.empty:
            st.warning("sin resultados")
            return

        met = kpis(df)
        m1, m2, m3 = st.columns(3)
        m1.metric("gasto total mn", f"{met['gasto_total_mn']:,.2f}")
        m2.metric("movimientos", f"{met['movimientos']:,d}")
        m3.metric("proveedores", f"{met['proveedores']:,d}")

        st.subheader("detalle")

        cols = [
            "FECHA_APLI","CVE_PROV","PROVEEDOR","NUM_CPTO","CONCEPTO","REFER","NUM_CARGO",
            "MONTO","MONEDA","TCAMBIO","IMPORTE_MN","STATUS"
        ]
        df_fmt = df[cols].copy()
        df_fmt["MONTO"]    = df_fmt["MONTO"].map(lambda x: f"{x:,.2f}")
        df_fmt["TCAMBIO"]    = df_fmt["TCAMBIO"].map(lambda x: f"{x:,.4f}")
        df_fmt["IMPORTE_MN"] = df_fmt["IMPORTE_MN"].map(lambda x: f"{x:,.2f}")

        st.dataframe(df_fmt[[
            "FECHA_APLI","CVE_PROV","PROVEEDOR","NUM_CPTO","CONCEPTO","REFER","NUM_CARGO",
            "MONTO","MONEDA","TCAMBIO","IMPORTE_MN","STATUS"
        ]], use_container_width=True)

        st.subheader("pivote por proveedor y mes")
        pvt = pivote_por_proveedor_mes(df)
        st.dataframe(pvt, use_container_width=True)

        st.subheader("top conceptos")
        st.dataframe(top_conceptos(df, 20), use_container_width=True)

        st.subheader("posibles outliers por concepto (iqr)")
        df_anom = outliers_iqr(df, "NUM_CPTO")
        if not df_anom.empty:
            st.dataframe(df_anom[[
                "FECHA_APLI","CVE_PROV","PROVEEDOR","NUM_CPTO","CONCEPTO","IMPORTE_MN","UMBRAL_IQR","REFER","NUM_CARGO"
            ]].sort_values("IMPORTE_MN", ascending=False), use_container_width=True)
        else:
            st.info("sin outliers detectados")

        # exportar a excel
        def to_excel_bytes():
            with pd.ExcelWriter("/tmp/gastos.xlsx", engine="xlsxwriter") as wr:
                df.to_excel(wr, index=False, sheet_name="detalle")
                top_conceptos(df, 50).to_excel(wr, index=False, sheet_name="top_conceptos")
                pvt.to_excel(wr, sheet_name="pivote")
            with open("/tmp/gastos.xlsx", "rb") as f:
                return f.read()
        st.download_button("descargar excel", data=to_excel_bytes(), file_name="gastos.xlsx")



        st.subheader("Gasto mensual (MN)")
        # agregación mensual
        mensual = (
            df.set_index("FECHA_APLI")
            .resample("M")["IMPORTE_MN"].sum()
            .reset_index()
        )
        mensual["MES"] = mensual["FECHA_APLI"].dt.to_period("M").astype(str)

        # opción simple
        st.bar_chart(mensual.set_index("MES")["IMPORTE_MN"], use_container_width=True)

        # (opcional) versión Altair con formato de moneda
        # import altair as alt
        # st.altair_chart(
        #     alt.Chart(mensual).mark_bar().encode(
        #         x=alt.X("MES:N", title="Mes"),
        #         y=alt.Y("IMPORTE_MN:Q", title="Gasto MN", axis=alt.Axis(format="$,.2f")),
        #         tooltip=[alt.Tooltip("MES:N"), alt.Tooltip("IMPORTE_MN:Q", format="$,.2f", title="Gasto MN")]
        #     ).properties(width="container"),
        #     use_container_width=True
        # )

        st.subheader("Gasto por proveedor (MN) — Top 20")

        por_prov = (
            df.groupby(["CVE_PROV","PROVEEDOR"], as_index=False)["IMPORTE_MN"].sum()
            .sort_values("IMPORTE_MN", ascending=False)
            .head(20)
        )

        # opción simple horizontal con Altair (mejor para etiquetas)
        import altair as alt
        st.altair_chart(
            alt.Chart(por_prov).mark_bar().encode(
                x=alt.X("IMPORTE_MN:Q", title="Gasto MN", axis=alt.Axis(format="$,.2f")),
                y=alt.Y("PROVEEDOR:N", sort="-x", title="Proveedor"),
                tooltip=[
                    alt.Tooltip("CVE_PROV:N", title="Clave"),
                    alt.Tooltip("PROVEEDOR:N"),
                    alt.Tooltip("IMPORTE_MN:Q", format="$,.2f", title="Gasto MN")
                ]
            ).properties(width="container", height=450),
            use_container_width=True
        )

        # (alternativa ultra simple con st.bar_chart si no quieres Altair)
        # st.bar_chart(por_prov.set_index("PROVEEDOR")["IMPORTE_MN"], use_container_width=True)