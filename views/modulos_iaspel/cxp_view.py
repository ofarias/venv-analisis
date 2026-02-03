import streamlit as st
import pandas as pd
import altair as alt
from controllers.cxp_controller import (
    get_cxp_con_nombres_df,
    get_proveedores_dinamico_apli_df,
    run_etl_cxp_cruce
)

def _pie_cobertura(resumen_df: pd.DataFrame):
    if resumen_df.empty:
        st.info("Sin datos de resumen.")
        return
    row = resumen_df.iloc[0]
    data = pd.DataFrame({
        "estado": ["Con póliza", "Sin póliza"],
        "cantidad": [int(row.get("con_poliza", 0)), int(row.get("sin_poliza", 0))]
    })
    chart = alt.Chart(data).mark_arc().encode(
        theta=alt.Theta(field="cantidad", type="quantitative"),
        color=alt.Color(field="estado", type="nominal"),
        tooltip=["estado", "cantidad"]
    )
    st.altair_chart(chart, use_container_width=True)


def pantalla_cxp_vs_polizas():
    st.title("CxP SAE (sólo FECHA_APLI)")

    # Filtros de fecha
    c1, c2 = st.columns(2)
    f_desde = c1.date_input("Fecha desde (FECHA_APLI)", value=None)
    f_hasta = c2.date_input("Fecha hasta (FECHA_APLI)", value=None)
    s_desde = str(f_desde) if f_desde else None
    s_hasta = str(f_hasta) if f_hasta else None

    # Botón de ejecución
    if st.button("Cargar y cruzar"):
        if not s_desde or not s_hasta:
            st.warning("Indica fecha inicial y final.")
            return

        frames = run_etl_cxp_cruce(s_desde, s_hasta)
        detalle_df = frames["detalle_df"]
        resumen_df = frames["resumen_df"]
        ranking_df = frames["ranking_df"]

        # Tabs
        t1, t2, t3 = st.tabs(["Resumen", "Ranking proveedores", "Detalle"])

        # --- Resumen
        with t1:
            st.subheader("Cobertura (CxP vs Pólizas)")
            _pie_cobertura(resumen_df)

            if not resumen_df.empty:
                row = resumen_df.iloc[0]
                cA, cB, cC = st.columns(3)
                cA.metric("Total documentos", int(row.get("total_docs", 0)))
                cB.metric("Con póliza", int(row.get("con_poliza", 0)))
                cC.metric("Sin póliza", int(row.get("sin_poliza", 0)))

        # --- Ranking
        with t2:
            st.subheader("Proveedores con más documentos sin póliza")
            if ranking_df.empty:
                st.info("Sin datos de ranking.")
            else:
                # pequeño gráfico de barras y tabla
                chart = alt.Chart(ranking_df).mark_bar().encode(
                    x=alt.X("docs_sin_poliza:Q", title="Docs sin póliza"),
                    y=alt.Y("cve_prov:N", sort="-x", title="Proveedor"),
                    tooltip=["cve_prov", "prov_nombre", "docs_total", "docs_sin_poliza", "pct_sin_poliza"]
                ).properties(height=400)
                st.altair_chart(chart, use_container_width=True)
                ranking_df = ranking_df[["cve_prov", "prov_nombre", "docs_total", "docs_sin_poliza", "pct_sin_poliza"]]
                st.dataframe(ranking_df, use_container_width=True)

        # --- Detalle
        with t3:
            st.subheader("Detalle de documentos")
            if detalle_df.empty:
                st.info("Sin datos de detalle.")
            else:
                # filtros rápidos en el detalle
                cols = st.columns(4)
                prov_f = cols[0].text_input("Filtrar CVE_PROV (contiene)")
                ref_f  = cols[1].text_input("Filtrar REFER (contiene)")
                only_no_pol = cols[2].checkbox("Sólo sin póliza", value=False)
                origen = cols[3].selectbox("Origen en puente", ["Todos", "JAVA"], index=1)

                df_show = detalle_df.copy()
                if prov_f:
                    df_show = df_show[df_show["cve_prov"].str.contains(prov_f, case=False, na=False)]
                if ref_f:
                    df_show = df_show[df_show["refer"].str.contains(ref_f, case=False, na=False)]
                if only_no_pol:
                    df_show = df_show[df_show["tiene_poliza"] == 0]
                if origen != "Todos" and "origen" in df_show.columns:
                    df_show = df_show[df_show["origen"] == origen]

                st.dataframe(df_show, use_container_width=True)

                # Totales
                if "importe" in df_show.columns:
                    tot = pd.DataFrame([{
                        "cve_prov": "TOTAL",
                        "refer": "",
                        "importe": round(df_show["importe"].sum(), 2)
                    }])
                    st.dataframe(tot, use_container_width=True)