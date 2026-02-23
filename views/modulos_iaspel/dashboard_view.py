#dashboard_view.py
import streamlit as st
import pandas as pd
import altair as alt
from controllers.dashboard_controller import (
    get_polizas_por_tipo,
    get_cobertura,
    get_usos_prorrateo,
    get_catalogo_con_uso,
    get_detalle_polizas,
    get_proveedores_df,
    get_prorrateos_por_proveedor_df,
    get_proveedores_resumen_df,
    get_nombre_conceptos_df,
)
from views.modulos_iaspel.tab_prorrateos_config_view import mostrar_tab_prorrateos_mysql
from views.modulos_iaspel.tab_pendientes_contabilizar_view import (mostrar_tab_pendientes_contabilizar,)
from views.modulos_iaspel.tab_poliza_ventas_view import mostrar_tab_poliza_ventas
from views.modulos_iaspel.tab_poliza_costo_ventas_view import mostrar_tab_poliza_costo_venta
from views.modulos_iaspel.tab_contabilizados_view import mostrar_tab_contabilizados
from views.modulos_iaspel.tab_reporte_cobranza_view import mostrar_tab_reporte_cobranza
from views.modulos_iaspel.tab_rep_ventas_lotes_view import mostrar_tab_rep_ventas_lotes
from views.modulos_iaspel.tab_reporte_pagos_view import mostrar_tab_reporte_pagos


def pantalla_dashboard():
    st.title("Dashboard de Pólizas / Prorrateos")

    eje = 25
    origen = "JAVA"

    tabs = st.tabs(
        [
            "Póliza ventas",
            "Póliza Costo Ventas",
            "Pendientes de Contabilizar",
            "Documentos Contabilizados",
            "Tabla Prorrateos",
            "Catálogo (ksae20t/21t)",
            "Reporte de Cobranza",
            "Pronostico de Pagos",
            "Reporte ventas lotes",
            "Pólizas por Tipo",
            "Usos por Prorrateo",
            "Cobertura de Prorrateo",
            "Proveedor → Ponderaciones",
            "Proveedores (resumen)",
        ]
    )

    with tabs[0]:
        mostrar_tab_poliza_ventas()
    with tabs[1]:
        mostrar_tab_poliza_costo_venta()
    with tabs[2]:
        mostrar_tab_pendientes_contabilizar()
    with tabs[3]:
        mostrar_tab_contabilizados()
    with tabs[4]:
        mostrar_tab_prorrateos_mysql()
    with tabs[5]:
        st.subheader("Catálogo de prorrateos (y su uso)")
        lim4 = st.number_input(
            "Límite catálogo", 1, 5000, value=200, step=50, key="lim4"
        )
        cat = get_catalogo_con_uso(eje, origen, int(lim4), 0)
        if cat.empty:
            st.warning("No se encontró catálogo (ksae20t/21t).")
        else:
            st.dataframe(cat, use_container_width=True)
            chart4 = (
                alt.Chart(cat)
                .mark_bar()
                .encode(
                    x=alt.X("idnumpon:N", title="ID Regla"),
                    y=alt.Y("polizas_uso:Q", title="Pólizas que usan la regla"),
                    tooltip=[
                        "idnumpon",
                        "dsnombre",
                        "proveedor",
                        "concepto_sae",
                        "unidades",
                        "suma_pct_regla",
                        "polizas_uso",
                    ],
                )
                .properties(height=360)
            )
            st.altair_chart(chart4, use_container_width=True)
    with tabs[6]:
        mostrar_tab_reporte_cobranza()
    with tabs[7]:
        mostrar_tab_reporte_pagos()
    with tabs[8]:
        mostrar_tab_rep_ventas_lotes()
    with tabs[9]:
        c1, c2 = st.columns(2)
        eje = c1.number_input("Eje (2 dígitos)", 0, 99, value=25, step=1)
        origen = c2.text_input("Origen", "JAVA")

        st.subheader("Pólizas agrupadas por Concepto")
        df = get_polizas_por_tipo(eje, origen)
        df_con = get_nombre_conceptos_df()

        df_merged = df.merge(
            df_con,
            left_on="concepto_sae",  # columna en df
            right_on="idnumcto",  # columna en df_con
            how="left",  # o "inner" según quieras
        )

        if df.empty:
            st.warning("Sin datos.")
        else:
            st.dataframe(df_merged, use_container_width=True)
            # gráfica simple
            chart = (
                alt.Chart(df_merged)
                .mark_bar()
                .encode(
                    x=alt.X("concepto_sae:N", title="Concepto SAE"),
                    y=alt.Y("polizas:Q", title="Pólizas"),
                    tooltip=["concepto_sae", "polizas", "cargos", "abonos"],
                )
                .properties(height=320)
            )
            st.altair_chart(chart, use_container_width=True)

            with st.expander("Detalle de todas las pólizas"):
                lim = st.number_input("Límite", 1, 10000, value=1000, step=100)
                off = st.number_input("Offset", 0, 100000, value=0, step=100)
                det = get_detalle_polizas(eje, origen, int(lim), int(off))
                st.dataframe(det, use_container_width=True)

    with tabs[10]:
        st.subheader("Pólizas por prorrateo aplicado")
        lim3 = st.number_input("Top N", 1, 2000, value=50, step=10, key="lim3")
        usos = get_usos_prorrateo(eje, origen, int(lim3), 0)
        if usos.empty:
            st.info("Aún no hay pólizas con prorrateo aplicado.")
        else:
            st.dataframe(usos, use_container_width=True)
            chart3 = (
                alt.Chart(usos)
                .mark_bar()
                .encode(
                    x=alt.X("regla_nombre:N", title="Prorrateo", sort="-y"),
                    y=alt.Y("polizas_uso:Q", title="Pólizas"),
                    tooltip=["regla_id", "regla_nombre", "polizas_uso"],
                )
                .properties(height=360)
            )
            st.altair_chart(chart3, use_container_width=True)

    with tabs[11]:
        st.subheader("Cobertura (pólizas con/ sin regla aplicada)")
        dfc = get_cobertura(eje, origen)
        if dfc.empty:
            st.warning("Sin datos.")
        else:
            st.dataframe(dfc, use_container_width=True)

            # Pie chart con Altair
            pie = (
                alt.Chart(dfc)
                .mark_arc()
                .encode(
                    theta=alt.Theta(field="polizas", type="quantitative"),
                    color=alt.Color(field="estado", type="nominal"),
                    tooltip=["estado", "polizas"],
                )
                .properties(height=360, width=360)
            )

            st.altair_chart(pie, use_container_width=False)
    
    

    with tabs[12]:
        st.subheader("Ponderaciones por Proveedor")

        provs = get_proveedores_df()
        if provs.empty:
            st.warning("No hay proveedores con ponderaciones en ksae20t.")
        else:
            prov_list = provs["proveedor"].dropna().tolist()
            c1, c2 = st.columns([2, 1])
            sel_prov = c1.selectbox("Proveedor (cdcvepro)", prov_list, index=0)
            st.caption(
                f"Total de reglas de este proveedor en ksae20t: "
                f"{int(provs.loc[provs['proveedor'] == sel_prov, 'reglas'].values[0])}"
            )

            dfp = get_prorrateos_por_proveedor_df(sel_prov, eje, origen)
            if dfp.empty:
                st.info(
                    "Ese proveedor no tiene reglas o no hay uso en pólizas del puente."
                )
            else:
                total_ponderaciones = len(dfp)  # ksae20t por este proveedor
                tabla = dfp.assign(ponderaciones=total_ponderaciones)[
                    ["dsnombre", "proveedor", "polizas_uso", "ponderaciones"]
                ]
                st.dataframe(tabla, use_container_width=True)

                st.download_button(
                    "Descargar CSV",
                    data=tabla.to_csv(index=False).encode("utf-8"),
                    file_name=f"prorrateos_{sel_prov}.csv",
                    mime="text/csv",
                )

    with tabs[13]:
        st.subheader("Resumen por Proveedor")

        # Checkbox para incluir/excluir proveedores sin pólizas
        incluir_sin_polizas = st.checkbox(
            "Incluir proveedores sin pólizas", value=False
        )

        dfprov = get_proveedores_resumen_df(eje, origen)
        if dfprov.empty:
            st.info("Sin datos de proveedores para el eje/origen seleccionados.")
        else:
            # Aplica el filtro según el checkbox
            dfv = dfprov.copy()
            if not incluir_sin_polizas:
                dfv = dfv[dfv["polizas_totales"] > 0]

            # Orden útil
            if not dfv.empty:
                dfv = dfv.sort_values(
                    ["polizas_totales", "polizas_con_regla", "ponderaciones"],
                    ascending=[False, False, False],
                )

            if not dfv.empty:
                total_polizas = dfv["polizas_totales"].sum()
                total_con_regla = dfv["polizas_con_regla"].sum()

                dfv["%_polizas_totales"] = (
                    dfv["polizas_totales"] / total_polizas * 100
                )
                dfv["%_polizas_con_regla"] = (
                    dfv["polizas_con_regla"] / total_con_regla * 100
                )

                totales = {
                    "proveedor": "TOTAL",
                    "nombre_proveedor": "",
                    "polizas_totales": total_polizas,
                    "polizas_con_regla": total_con_regla,
                    "polizas_sin_regla": dfv["polizas_sin_regla"].sum(),
                    "ponderaciones": dfv["ponderaciones"].sum(),
                    "cobertura_pct": "",
                    "%_polizas_totales": 100.0,
                    "%_polizas_con_regla": 100.0,
                }
                dfv = pd.concat([dfv, pd.DataFrame([totales])], ignore_index=True)

            st.dataframe(dfv, use_container_width=True)

            st.download_button(
                "Descargar CSV",
                data=dfv.to_csv(index=False).encode("utf-8"),
                file_name=(
                    f"proveedores_resumen_e{int(eje) % 100}_"
                    f"{origen}_"
                    f"{'all' if incluir_sin_polizas else 'con_polizas'}.csv"
                ),
                mime="text/csv",
            )

            topn = st.number_input(
                "Top N para gráfica", 1, 200, value=20, step=1
            )
            chart_df = dfv.head(int(topn))
            if not chart_df.empty:
                cov = (
                    alt.Chart(chart_df)
                    .mark_bar()
                    .encode(
                        x=alt.X("proveedor:N", title="Proveedor"),
                        y=alt.Y(
                            "polizas_con_regla:Q", title="Pólizas con regla"
                        ),
                        tooltip=[
                            "proveedor",
                            "nombre_proveedor",
                            "polizas_totales",
                            "polizas_con_regla",
                            "ponderaciones",
                            "cobertura_pct",
                        ],
                    )
                    .properties(height=360)
                )
                st.altair_chart(cov, use_container_width=True)
            else:
                st.info("No hay datos para graficar con el filtro actual.")

    
    
