# views/modulo_polizas/polizas.py

import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from io import BytesIO

from controllers.polizas_controller import (
    get_resumen_polizas_ctrl,
    get_detalle_poliza_ctrl,
    get_xml_con_poliza_ctrl,
)

CLIENTE_DEFAULT = "PCP220503B20"


def _fmt_money(v):
    try:
        return f"${float(v):,.2f}"
    except Exception:
        return "$0.00"


def _export_excel(df: pd.DataFrame) -> bytes:
    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="xml_polizas")

    return output.getvalue()


def _normalizar_df_xml(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()

    if "FECHA" in df.columns:
        df["FECHA"] = pd.to_datetime(df["FECHA"], errors="coerce")
        df["ANIO"] = df["FECHA"].dt.year
        df["MES"] = df["FECHA"].dt.month
        df["MES_ANIO"] = df["FECHA"].dt.to_period("M").astype(str)

    for col in [
        "SUBTOTAL",
        "IVA",
        "IMPORTE",
        "IMPORTE_MXN",
        "TIPOCAMBIO",
    ]:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col],
                errors="coerce"
            ).fillna(0)

    if "TIENE_POLIZA" in df.columns:
        df["TIENE_POLIZA"] = (
            df["TIENE_POLIZA"]
            .fillna("NO")
            .astype(str)
            .str.upper()
            .str.strip()
        )
    else:
        df["TIENE_POLIZA"] = "NO"

    return df


def mostrar_modulo_polizas():
    st.title("Módulo de Pólizas")

    tab_xml, tab_resumen, tab_detalle, tab_config = st.tabs([
        "XML vs pólizas",
        "Resumen de pólizas",
        "Detalle de póliza",
        "Configuración",
    ])

    with tab_xml:
        mostrar_tab_xml_vs_polizas()

    with tab_resumen:
        mostrar_tab_resumen_polizas()

    with tab_detalle:
        mostrar_tab_detalle_poliza()

    with tab_config:
        mostrar_tab_configuracion_polizas()


def mostrar_tab_xml_vs_polizas():
    st.subheader("XML de ventas vs pólizas")

    cliente = st.text_input(
        "RFC cliente excluido",
        value=CLIENTE_DEFAULT,
        key="polizas_xml_cliente",
    ).strip().upper()

    if st.button(
        "Consultar XML",
        type="primary",
        key="btn_consultar_xml_polizas",
    ):
        st.session_state["polizas_df_xml"] = (
            get_xml_con_poliza_ctrl(cliente)
        )

    df = st.session_state.get(
        "polizas_df_xml",
        pd.DataFrame()
    )

    df = _normalizar_df_xml(df)

    if df.empty:
        st.info(
            "Consulta los XML para revisar cuáles tienen póliza y cuáles no."
        )
        return

    total_xml = len(df)

    total_con_poliza = int(
        (df["TIENE_POLIZA"] == "SI").sum()
    )

    total_sin_poliza = int(
        (df["TIENE_POLIZA"] == "NO").sum()
    )

    importe_sin_poliza = (
        df.loc[
            df["TIENE_POLIZA"] == "NO",
            "IMPORTE_MXN"
        ].sum()
        if "IMPORTE_MXN" in df.columns
        else 0
    )

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "Total XML",
        f"{total_xml:,}"
    )

    c2.metric(
        "Con póliza",
        f"{total_con_poliza:,}"
    )

    c3.metric(
        "Sin póliza",
        f"{total_sin_poliza:,}"
    )

    c4.metric(
        "Importe sin póliza MXN",
        _fmt_money(importe_sin_poliza)
    )

    st.divider()

    st.subheader(
        "Importe XML sin póliza por mes / año"
    )

    df_importe_sin = (
        df[df["TIENE_POLIZA"] == "NO"]
        .groupby(
            "MES_ANIO",
            as_index=False
        )["IMPORTE_MXN"]
        .sum()
        .sort_values("MES_ANIO")
    )

    st.dataframe(
        df_importe_sin,
        use_container_width=True,
        hide_index=True,
        column_config={
            "IMPORTE_MXN": st.column_config.NumberColumn(
                "Importe MXN",
                format="$ %.2f"
            )
        },
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        filtro_poliza = st.selectbox(
            "Estatus póliza",
            [
                "Todos",
                "Con póliza",
                "Sin póliza",
            ],
            key="filtro_xml_poliza",
        )

    with col2:
        meses = sorted(
            df["MES_ANIO"]
            .dropna()
            .unique()
            .tolist()
        ) if "MES_ANIO" in df.columns else []

        filtro_mes = st.multiselect(
            "Mes / año",
            options=meses,
            default=meses,
            key="filtro_xml_mes_anio",
        )

    with col3:
        buscar = st.text_input(
            "Buscar UUID / serie / folio",
            key="filtro_xml_buscar",
        ).strip().upper()

    df_filtrado = df.copy()

    if filtro_poliza == "Con póliza":
        df_filtrado = df_filtrado[
            df_filtrado["TIENE_POLIZA"] == "SI"
        ]

    elif filtro_poliza == "Sin póliza":
        df_filtrado = df_filtrado[
            df_filtrado["TIENE_POLIZA"] == "NO"
        ]

    if filtro_mes and "MES_ANIO" in df_filtrado.columns:
        df_filtrado = df_filtrado[
            df_filtrado["MES_ANIO"].isin(filtro_mes)
        ]

    if buscar:
        cols_busqueda = [
            c for c in [
                "UUID",
                "SERIE",
                "FOLIO",
                "NUM_POLIZ",
            ]
            if c in df_filtrado.columns
        ]

        if cols_busqueda:
            mask = False

            for c in cols_busqueda:
                mask = (
                    mask
                    |
                    df_filtrado[c]
                    .astype(str)
                    .str.upper()
                    .str.contains(buscar, na=False)
                )

            df_filtrado = df_filtrado[mask]

    st.subheader("Gráfica por mes / año")

    if "MES_ANIO" in df_filtrado.columns:

        df_grafica = (
            df_filtrado
            .groupby(
                ["MES_ANIO", "TIENE_POLIZA"],
                as_index=False
            )
            .agg(
                XML=("UUID", "count"),
                IMPORTE_MXN=("IMPORTE_MXN", "sum"),
            )
        )

        df_pivot = (
            df_grafica
            .pivot(
                index="MES_ANIO",
                columns="TIENE_POLIZA",
                values=["XML", "IMPORTE_MXN"]
            )
            .fillna(0)
        )

        df_pivot.columns = [
            f"{valor}_{estatus}"
            for valor, estatus in df_pivot.columns
        ]

        df_pivot = df_pivot.reset_index()

        for col in [
            "XML_NO",
            "IMPORTE_MXN_NO",
            "XML_SI",
            "IMPORTE_MXN_SI",
        ]:
            if col not in df_pivot.columns:
                df_pivot[col] = 0

        df_pivot["TOTAL_XML"] = (
            df_pivot["XML_NO"]
            + df_pivot["XML_SI"]
        )

        df_pivot["TOTAL_MXN"] = (
            df_pivot["IMPORTE_MXN_NO"]
            + df_pivot["IMPORTE_MXN_SI"]
        )

        df_pivot = df_pivot.rename(columns={
            "XML_NO": "XML sin póliza",
            "IMPORTE_MXN_NO": "Valor sin póliza",
            "XML_SI": "XML con póliza",
            "IMPORTE_MXN_SI": "Valor con póliza",
            "TOTAL_XML": "Total XML",
            "TOTAL_MXN": "Total valor",
        })

        fig, ax = plt.subplots()

        ax.bar(
            df_pivot["MES_ANIO"],
            df_pivot["XML con póliza"],
            label="Con póliza",
        )

        ax.bar(
            df_pivot["MES_ANIO"],
            df_pivot["XML sin póliza"],
            bottom=df_pivot["XML con póliza"],
            label="Sin póliza",
        )

        ax.set_title(
            "XML de venta con póliza y sin póliza"
        )

        ax.set_xlabel("Mes / año")

        ax.set_ylabel(
            "Cantidad de XML"
        )

        ax.legend()

        plt.xticks(
            rotation=45,
            ha="right"
        )

        st.pyplot(fig)

        st.dataframe(
            df_pivot,
            use_container_width=True,
            hide_index=True,
            column_config={

                "XML sin póliza": st.column_config.NumberColumn(
                    format="%d"
                ),

                "XML con póliza": st.column_config.NumberColumn(
                    format="%d"
                ),

                "Total XML": st.column_config.NumberColumn(
                    format="%d"
                ),

                "Valor sin póliza": st.column_config.NumberColumn(
                    format="$ %.2f"
                ),

                "Valor con póliza": st.column_config.NumberColumn(
                    format="$ %.2f"
                ),

                "Total valor": st.column_config.NumberColumn(
                    format="$ %.2f"
                ),
            },
        )

    st.subheader("Detalle de XML")

    columnas_preferidas = [
        "TIENE_POLIZA",
        "UUID",
        "CLIENTE",
        "FECHA",
        "MES_ANIO",
        "SERIE",
        "FOLIO",
        "SUBTOTAL",
        "IVA",
        "IMPORTE",
        "MONEDA",
        "TIPOCAMBIO",
        "IMPORTE_MXN",
        "TIPO_POLI",
        "NUM_POLIZ",
        "PERIODO",
        "EJERCICIO",
        "FECHA_POL",
        "CONCEP_PO",
    ]

    columnas = [
        c for c in columnas_preferidas
        if c in df_filtrado.columns
    ]

    columnas_extra = [
        c for c in df_filtrado.columns
        if c not in columnas
    ]

    df_mostrar = df_filtrado[
        columnas + columnas_extra
    ].copy()

    st.dataframe(
        df_mostrar,
        use_container_width=True,
        hide_index=True,
        column_config={

            "FECHA": st.column_config.DateColumn(
                format="DD/MM/YYYY"
            ),

            "FECHA_POL": st.column_config.DateColumn(
                format="DD/MM/YYYY"
            ),

            "SUBTOTAL": st.column_config.NumberColumn(
                format="$ %.2f"
            ),

            "IVA": st.column_config.NumberColumn(
                format="$ %.2f"
            ),

            "IMPORTE": st.column_config.NumberColumn(
                format="$ %.2f"
            ),

            "TIPOCAMBIO": st.column_config.NumberColumn(
                format="%.4f"
            ),

            "IMPORTE_MXN": st.column_config.NumberColumn(
                format="$ %.2f"
            ),
        },
    )

    st.download_button(
        "Descargar Excel",
        data=_export_excel(df_mostrar),
        file_name="xml_vs_polizas.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="download_xml_vs_polizas",
    )


def mostrar_tab_resumen_polizas():
    st.subheader(
        "Resumen por póliza y tipo"
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        ejercicio = st.number_input(
            "Ejercicio",
            min_value=2000,
            max_value=2100,
            value=2026,
            step=1,
            key="polizas_ejercicio",
        )

    with col2:
        periodo = st.selectbox(
            "Periodo",
            options=list(range(1, 13)),
            index=0,
            key="polizas_periodo",
        )

    with col3:
        tipo_poliza = st.selectbox(
            "Tipo de póliza",
            options=[
                "Todos",
                "Ig",
                "Eg",
                "Dr",
            ],
            key="polizas_tipo",
        )

    if st.button(
        "Consultar resumen",
        type="primary",
        key="btn_consultar_resumen_polizas",
    ):
        st.session_state["polizas_df_resumen"] = (
            get_resumen_polizas_ctrl(
                ejercicio=ejercicio,
                periodo=periodo,
                tipo_poliza=tipo_poliza,
            )
        )

    df = st.session_state.get(
        "polizas_df_resumen",
        pd.DataFrame()
    )

    if df.empty:
        st.info(
            "Consulta el resumen de pólizas."
        )
        return

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
    )


def mostrar_tab_detalle_poliza():
    st.subheader(
        "Detalle de póliza"
    )

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        ejercicio = st.number_input(
            "Ejercicio detalle",
            min_value=2000,
            max_value=2100,
            value=2026,
            step=1,
            key="detalle_polizas_ejercicio",
        )

    with col2:
        periodo = st.selectbox(
            "Periodo detalle",
            options=list(range(1, 13)),
            index=0,
            key="detalle_polizas_periodo",
        )

    with col3:
        tipo_poliza = st.text_input(
            "Tipo",
            value="Ig",
            key="detalle_polizas_tipo",
        ).strip()

    with col4:
        num_poliz = st.text_input(
            "Número póliza",
            key="detalle_polizas_num",
        ).strip()

    if st.button(
        "Consultar detalle",
        type="primary",
        key="btn_consultar_detalle_poliza",
    ):
        if not tipo_poliza or not num_poliz:
            st.warning(
                "Captura tipo y número de póliza."
            )
        else:
            st.session_state["polizas_df_detalle"] = (
                get_detalle_poliza_ctrl(
                    ejercicio=ejercicio,
                    periodo=periodo,
                    tipo_poliza=tipo_poliza,
                    num_poliz=num_poliz,
                )
            )

    df = st.session_state.get(
        "polizas_df_detalle",
        pd.DataFrame()
    )

    if df.empty:
        st.info(
            "Consulta el detalle de una póliza."
        )
        return

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
    )


def mostrar_tab_configuracion_polizas():
    st.subheader(
        "Configuración del módulo"
    )

    st.info(
        "Aquí agregaremos reglas posteriormente."
    )