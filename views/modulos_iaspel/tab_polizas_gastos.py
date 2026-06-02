# views/modulos_iaspel/tab_polizas_gastos.py

import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from io import BytesIO

from controllers.polizas_controller import (
    get_xml_con_poliza_gastos_ctrl,
    get_validacion_importes_uuid_ctrl,
)

CLIENTE_GASTOS = "PCP220503B20"


def _fmt_money(v):
    try:
        return f"${float(v):,.2f}"
    except Exception:
        return "$0.00"


def _export_excel(df: pd.DataFrame) -> bytes:
    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(
            writer,
            index=False,
            sheet_name="xml_gastos"
        )

    return output.getvalue()


def _normalizar_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()

    if "FECHA" in df.columns:
        df["FECHA"] = pd.to_datetime(
            df["FECHA"],
            errors="coerce"
        )

        df["ANIO"] = df["FECHA"].dt.year
        df["MES"] = df["FECHA"].dt.month
        df["MES_ANIO"] = (
            df["FECHA"]
            .dt.to_period("M")
            .astype(str)
        )

    for col in [
        "SUBTOTAL",
        "IVA",
        "IMPORTE",
        "TIPOCAMBIO",
        "MONTO_XML",
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
    
    if "TIENE_POLIZA" not in df.columns:
        if "ESTATUS_VALIDACION" in df.columns:
            df["TIENE_POLIZA"] = df["ESTATUS_VALIDACION"].apply(
                lambda x: "NO" if str(x).strip().upper() == "SIN POLIZA" else "SI"
            )
        else:
            df["TIENE_POLIZA"] = "NO"

    return df


def mostrar_tab_polizas_gastos():
    st.subheader(
        "XML de gastos vs pólizas"
    )
    anio = st.number_input(
        "Año",
        min_value=2020,
        max_value=2100,
        value=2025,
        step=1,
        key="validacion_uuid_anio",
    )

    st.caption(
        f"Cliente gastos: {CLIENTE_GASTOS}"
    )

    if st.button(
        "Consultar gastos",
        type="primary",
        key="btn_consultar_gastos_polizas",
    ):
        st.session_state["df_polizas_gastos"] = (
            get_validacion_importes_uuid_ctrl(
                modo="gastos",
                cliente=CLIENTE_GASTOS,
                anio=anio,
            )
        )

    df = st.session_state.get(
        "df_polizas_gastos",
        pd.DataFrame()
    )

    df = _normalizar_df(df)

    if df.empty:
        st.info(
            "Consulta los XML de gastos."
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
            "MONTO_XML"
        ].sum()
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

    col1, col2, col3 = st.columns(3)

    with col1:
        filtro_poliza = st.selectbox(
            "Estatus póliza",
            [
                "Todos",
                "Con póliza",
                "Sin póliza",
            ],
            key="gastos_filtro_poliza",
        )

    with col2:
        meses = sorted(
            df["MES_ANIO"]
            .dropna()
            .unique()
            .tolist()
        )

        filtro_mes = st.multiselect(
            "Mes / año",
            options=meses,
            default=meses,
            key="gastos_filtro_mes",
        )

    with col3:
        buscar = st.text_input(
            "Buscar UUID / serie / folio",
            key="gastos_buscar",
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

    if filtro_mes:
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
                    .str.contains(
                        buscar,
                        na=False
                    )
                )

            df_filtrado = df_filtrado[mask]

    st.subheader(
        "Resumen mensual"
    )

    df_grafica = (
        df_filtrado
        .groupby(
            ["MES_ANIO", "TIENE_POLIZA"],
            as_index=False
        )
        .agg(
            XML=("UUID", "count"),
            MONTO_XML=("MONTO_XML", "sum"),
        )
    )

    df_pivot = (
        df_grafica
        .pivot(
            index="MES_ANIO",
            columns="TIENE_POLIZA",
            values=["XML", "MONTO_XML"]
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
        "MONTO_XML_NO",
        "XML_SI",
        "MONTO_XML_SI",
    ]:
        if col not in df_pivot.columns:
            df_pivot[col] = 0

    df_pivot["TOTAL_XML"] = (
        df_pivot["XML_NO"]
        + df_pivot["XML_SI"]
    )

    df_pivot["TOTAL_MXN"] = (
        df_pivot["MONTO_XML_NO"]
        + df_pivot["MONTO_XML_SI"]
    )

    df_pivot = df_pivot.rename(columns={
        "XML_NO": "XML sin póliza",
        "MONTO_XML_NO": "Valor sin póliza",
        "XML_SI": "XML con póliza",
        "MONTO_XML_SI": "Valor con póliza",
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
        "XML gastos con póliza y sin póliza"
    )

    ax.set_xlabel(
        "Mes / año"
    )

    ax.set_ylabel(
        "Cantidad XML"
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

            "XML sin póliza":
                st.column_config.NumberColumn(
                    format="%d"
                ),

            "XML con póliza":
                st.column_config.NumberColumn(
                    format="%d"
                ),

            "Total XML":
                st.column_config.NumberColumn(
                    format="%d"
                ),

            "Valor sin póliza":
                st.column_config.NumberColumn(
                    format="$ %.2f"
                ),

            "Valor con póliza":
                st.column_config.NumberColumn(
                    format="$ %.2f"
                ),

            "Total valor":
                st.column_config.NumberColumn(
                    format="$ %.2f"
                ),
        },
    )

    st.subheader(
        "Detalle XML gastos"
    )

    columnas_preferidas = [
        "TIENE_POLIZA",
        "UUID",
        "CLIENTE",
        "RFCE",
        "FECHA",
        "MES_ANIO",
        "SERIE",
        "FOLIO",
        "SUBTOTAL",
        "IVA",
        "IMPORTE",
        "MONEDA",
        "TIPOCAMBIO",
        "MONTO_XML",
        "TIPO_POLI",
        "NUM_POLIZ",
        "PERIODO",
        "EJERCICIO",
        "FECHA_POL",
        "CONCEP_PO",
        "IMPORTE_POLIZA",
        "DIFERENCIA",
        "ESTATUS_VALIDACION",
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

            "FECHA":
                st.column_config.DateColumn(
                    format="DD/MM/YYYY"
                ),

            "FECHA_POL":
                st.column_config.DateColumn(
                    format="DD/MM/YYYY"
                ),

            "SUBTOTAL":
                st.column_config.NumberColumn(
                    format="$ %.2f"
                ),

            "IVA":
                st.column_config.NumberColumn(
                    format="$ %.2f"
                ),

            "IMPORTE":
                st.column_config.NumberColumn(
                    format="$ %.2f"
                ),

            "TIPOCAMBIO":
                st.column_config.NumberColumn(
                    format="%.4f"
                ),

            "MONTO_XML":
                st.column_config.NumberColumn(
                    format="$ %.2f"
                ),
            "IMPORTE_POLIZA":
                st.column_config.NumberColumn(
                    format="$ %.2f"
                ),

            "DIFERENCIA":
                st.column_config.NumberColumn(
                    format="$ %.2f"
                ),
        },
    )

    st.download_button(
        "Descargar Excel",
        data=_export_excel(df_mostrar),
        file_name="xml_gastos_vs_polizas.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="download_gastos_excel",
    )