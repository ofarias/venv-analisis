# views/modulos_iaspel/tab_reporte_cobranza_view.py

import streamlit as st
import pandas as pd
from io import BytesIO
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode
import matplotlib.pyplot as plt
from controllers.dashboard_controller import get_reporte_cobranza_df
from datetime import date

def _plot_barh(df_sum: pd.DataFrame, label_col: str, value_col: str, title: str):
    fig, ax = plt.subplots()
    d = df_sum.sort_values(value_col, ascending=True).copy()
    # convertir a miles
    d["_miles"] = d[value_col] / 1000.0
    ax.barh(d[label_col], d["_miles"])
    ax.set_title(f"{title} (miles de pesos)")
    ax.tick_params(axis="y", labelsize=9)
    ax.xaxis.set_major_formatter(lambda x, pos: f"{x:,.0f}")

    plt.tight_layout()
    return fig

def _plot_donut(df_sum: pd.DataFrame, label_col: str, value_col: str, title: str, donut: bool = True):
    fig, ax = plt.subplots()

    vals_miles = df_sum[value_col] / 1000.0

    ax.pie(
        vals_miles,
        startangle=90,
        autopct="%1.1f%%",
        pctdistance=0.78,
    )

    if donut:
        centre_circle = plt.Circle((0, 0), 0.55, fc="white")
        fig.gca().add_artist(centre_circle)

    ax.set_title(f"{title} (miles de pesos)")
    ax.axis("equal")

    ax.legend(
        df_sum[label_col],
        loc="center left",
        bbox_to_anchor=(1.02, 0.5),
        fontsize=9,
        title="participación",
    )

    plt.tight_layout()
    return fig

def _pie_top_n(df: pd.DataFrame, label_col: str, value_col: str, top_n: int = 10) -> pd.DataFrame:
    tmp = (
        df[[label_col, value_col]]
        .copy()
        .dropna()
    )
    tmp[value_col] = pd.to_numeric(tmp[value_col], errors="coerce").fillna(0)

    g = tmp.groupby(label_col, as_index=False)[value_col].sum()
    g = g[g[value_col] > 0].sort_values(value_col, ascending=False)

    if len(g) <= top_n:
        return g

    top = g.head(top_n).copy()
    otros_val = g.iloc[top_n:][value_col].sum()
    if otros_val > 0:
        top = pd.concat([top, pd.DataFrame([{label_col: "otros", value_col: otros_val}])], ignore_index=True)
    return top


def _to_excel_bytes(df: pd.DataFrame) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="reporte_cobranza")
    return output.getvalue()


def mostrar_tab_reporte_cobranza():
    st.subheader("reporte de cobranza")

    hoy = date.today()

    # filtros
    c1, c2, c3, c4, c5 = st.columns([1.2, 1.2, 1.2, 1.2, 1.2])

    with c1:
        # si seleccionas año, el corte se fuerza a hoy
        anio_inicio = st.selectbox(
            "año inicio",
            options=["(sin filtro)"] + list(range(hoy.year, 2009, -1)),
            index=0,
        )

    with c2:
        # corte manual solo cuando no hay año inicio
        fecha_corte = st.date_input(
            "fecha de corte",
            value=hoy if anio_inicio != "(sin filtro)" else pd.to_datetime("2025-12-31").date(),
        )

    with c3:
        filtrar_saldo_mayor_1 = st.checkbox("saldo > 1", value=True)

    with c4:
        usar_cliente = st.checkbox("filtrar por cliente", value=False)

    with c5:
        usar_vendedor = st.checkbox("filtrar por vendedor", value=False)

    # si hay año inicio, el corte real es hoy (para “desde el año a la fecha actual”)
    corte_real = hoy if anio_inicio != "(sin filtro)" else fecha_corte
    # carga base (solo depende de fecha_corte para no traer todo)
    df = get_reporte_cobranza_df(corte_real)

    if df is None or df.empty:
        st.info("no hay datos disponibles para el reporte de cobranza.")
        return

    # normaliza nombres por si acaso
    df.columns = [str(c).lower() for c in df.columns]

    # opciones de filtros (desde el df cargado)
    cliente_sel = None
    vendedor_sel = None

    df.columns = [str(c).lower() for c in df.columns]

    # normalización para filtros (evita problemas por espacios/padding)
    
    if "clave" in df.columns:
        df["clave_norm"] = df["clave"].astype(str).str.strip()

    if "vendedor" in df.columns:
        df["vendedor_norm"] = df["vendedor"].astype(str).str.strip()

    if "cuentacontable" in df.columns:
        df["cuentacontable_norm"] = df["cuentacontable"].astype(str).str.strip()

    # fecha_doc como date para filtros por año
    if "fecha_doc" in df.columns:
        df["fecha_doc_dt"] = pd.to_datetime(df["fecha_doc"], errors="coerce").dt.date
    else:
        df["fecha_doc_dt"] = pd.NaT

    colf1, colf2, colf3 = st.columns(3)

    usar_cuenta = False
    cuenta_sel = None

    if usar_cliente:
        with colf1:
            df_cli = (
                df[["clave_norm", "nombre"]]
                .dropna()
                .astype(str)
                .drop_duplicates()
                .sort_values(["nombre", "clave_norm"])
            )

            opciones_clientes = ["(todos)"] + [
                f"{r.clave_norm} - {r.nombre}"
                for r in df_cli.itertuples(index=False)
            ]

            cliente_sel = st.selectbox("cliente", opciones_clientes, index=0)

    # aplica filtros en pandas (rápido y sin volver a consultar)
    df_filtrado = df.copy()

    # filtro saldo > 1 (por defecto)
    if "saldo" in df_filtrado.columns:
        df_filtrado["saldo"] = pd.to_numeric(df_filtrado["saldo"], errors="coerce").fillna(0)
        if filtrar_saldo_mayor_1:
            df_filtrado = df_filtrado[df_filtrado["saldo"] > 1]

    # filtro por año inicio (desde 01-enero del año hasta hoy)
    if anio_inicio != "(sin filtro)":
        if "fecha_doc_dt" in df_filtrado.columns and df_filtrado["fecha_doc_dt"].notna().any():
            f_ini = date(int(anio_inicio), 1, 1)
            f_fin = hoy
            df_filtrado = df_filtrado[
                (df_filtrado["fecha_doc_dt"] >= f_ini) & (df_filtrado["fecha_doc_dt"] <= f_fin)
            ]
        else:
            st.warning("no se pudo aplicar filtro por año porque fecha_doc no está disponible o no es válida.")

    # filtro por cuenta contable
    if usar_cuenta and cuenta_sel and cuenta_sel != "(todas)" and "cuentacontable_norm" in df_filtrado.columns:
        df_filtrado = df_filtrado[df_filtrado["cuentacontable_norm"] == str(cuenta_sel).strip()]

    ######## filtros cliente/vendedor

    if usar_cliente and cliente_sel and cliente_sel != "(todos)":
        clave_sel = cliente_sel.split(" - ", 1)[0].strip()
        df_filtrado = df_filtrado[df_filtrado["clave_norm"] == clave_sel]

    if usar_vendedor:
        with colf2:
            opciones_vend = ["(todos)"] + sorted(
                df["vendedor_norm"].dropna().astype(str).unique().tolist()
            )
            vendedor_sel = st.selectbox("vendedor", opciones_vend, index=0)

    if usar_vendedor and vendedor_sel and vendedor_sel != "(todos)":
        df_filtrado = df_filtrado[df_filtrado["vendedor_norm"] == str(vendedor_sel).strip()]

    with colf3:
        if "cuentacontable_norm" in df.columns:
            usar_cuenta = st.checkbox("filtrar por cuenta contable", value=False)
        else:
            st.caption("cuenta contable: no disponible")

    if usar_cuenta and "cuentacontable_norm" in df.columns:
        with colf3:
            opciones_cta = ["(todas)"] + sorted(
                df["cuentacontable_norm"].dropna().astype(str).unique().tolist()
            )
            cuenta_sel = st.selectbox("cuenta contable", opciones_cta, index=0)

    # resumen rápido
    st.caption(f"registros: {len(df_filtrado):,}")

    ### Grafica 

    # ---------------- gráficas ----------------
    g1, g2, g3 = st.columns([1, 1, 0.8])

    with g1:
        mostrar_graf_cliente = st.checkbox("mostrar gráfica por cliente", value=True)

    with g2:
        mostrar_graf_vendedor = st.checkbox("mostrar gráfica por vendedor", value=True)

    with g3:
        top_n = st.number_input("top n", min_value=5, max_value=30, value=10, step=1)

        tipo = st.selectbox(
            "tipo de gráfica",
            ["barras (recomendado)", "dona", "pie"],
            index=0,
        )

    colg1, colg2 = st.columns(2)

    # asegura saldo numérico
    if "saldo" in df_filtrado.columns:
        df_filtrado["saldo"] = pd.to_numeric(df_filtrado["saldo"], errors="coerce").fillna(0)

    total_deuda = float(df_filtrado["saldo"].sum())
    st.metric("total de deuda (miles de pesos)", f"{total_deuda / 1000:,.0f}")

    if mostrar_graf_cliente:
        with colg1:
            st.caption("saldo por cliente (top n)")
            # etiqueta cliente: clave - nombre
            if "clave_norm" in df_filtrado.columns and "nombre" in df_filtrado.columns and "saldo" in df_filtrado.columns:
                df_filtrado["cliente_label"] = df_filtrado["clave_norm"].astype(str).str.strip() + " - " + df_filtrado["nombre"].astype(str).str.strip()
                pie_cli = _pie_top_n(df_filtrado, "cliente_label", "saldo", top_n=int(top_n))
                fig, ax = plt.subplots()
                # cliente
                pie_cli = _pie_top_n(df_filtrado, "cliente_label", "saldo", top_n=int(top_n))
                if not pie_cli.empty:
                    if tipo == "barras (recomendado)":
                        fig = _plot_barh(pie_cli, "cliente_label", "saldo", "saldo por cliente (top n)")
                    elif tipo == "dona":
                        fig = _plot_donut(pie_cli, "cliente_label", "saldo", "saldo por cliente (top n)", donut=True)
                    else:
                        fig = _plot_donut(pie_cli, "cliente_label", "saldo", "saldo por cliente (top n)", donut=False)
                    st.pyplot(fig, use_container_width=True)
                
            else:
                st.info("no se encontraron columnas necesarias para gráfica por cliente (clave/nombre/saldo).")

    if mostrar_graf_vendedor:
        with colg2:
            st.caption("saldo por vendedor (top n)")
            if "vendedor_norm" in df_filtrado.columns and "saldo" in df_filtrado.columns:
                pie_vend = _pie_top_n(df_filtrado, "vendedor_norm", "saldo", top_n=int(top_n))

                fig, ax = plt.subplots()
                #ax.pie(pie_vend["saldo"], labels=pie_vend["vendedor_norm"], autopct="%1.1f%%", startangle=90)
                #ax.axis("equal")
                #st.pyplot(fig, use_container_width=True)
                # vendedor
                pie_vend = _pie_top_n(df_filtrado, "vendedor_norm", "saldo", top_n=int(top_n))
                if not pie_vend.empty:
                    if tipo == "barras (recomendado)":
                        fig = _plot_barh(pie_vend, "vendedor_norm", "saldo", "saldo por vendedor (top n)")
                    elif tipo == "dona":
                        fig = _plot_donut(pie_vend, "vendedor_norm", "saldo", "saldo por vendedor (top n)", donut=True)
                    else:
                        fig = _plot_donut(pie_vend, "vendedor_norm", "saldo", "saldo por vendedor (top n)", donut=False)
                    st.pyplot(fig, use_container_width=True)
            else:
                st.info("no se encontraron columnas necesarias para gráfica por vendedor (vendedor/saldo).")

    ### Finaliza grafica 


    # configuración aggrid
    gb = GridOptionsBuilder.from_dataframe(df_filtrado)

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

    # filtro rápido (search)
    gb.configure_grid_options(quickFilterText="")

    # columnas clave al inicio
    for col in ["nombre", "clave", "refer", "fecha_doc", "estatusdocumento", "vendedor"]:
        if col in df_filtrado.columns:
            gb.configure_column(col, pinned="left")

    # formatos numéricos (si existen)
    cols_num = [
        "diastranscurridos", "diasdeatraso", "diasusados", "diascred", "diasdeatrasodelpago",
        "subtotalusd", "importepesos", "impuestos", "tcambio", "pagado", "pagado_usd", "saldo"
    ]
    for col in cols_num:
        if col in df_filtrado.columns:
            gb.configure_column(col, type=["numericColumn", "numberColumnFilter"], valueFormatter="x.toLocaleString()")

    grid_options = gb.build()

    grid = AgGrid(
        df_filtrado,
        gridOptions=grid_options,
        enable_enterprise_modules=True,
        update_mode=GridUpdateMode.NO_UPDATE,
        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
        fit_columns_on_grid_load=True,
        height=520,
        width="100%",
    )

    # el df que se ve (ya filtrado/ordenado en la grilla)
    df_grid = pd.DataFrame(grid.get("data", df_filtrado))

    # columnas auxiliares que NO deben ir al excel
    cols_excluir_excel = [
        "clave_norm",
        "vendedor_norm",
        "cuentacontable_norm",
        "fecha_doc_dt",
        "cliente_label",
    ]

    df_excel = df_grid.drop(
        columns=[c for c in cols_excluir_excel if c in df_grid.columns],
        errors="ignore",
    )

    # descarga excel
    xlsx_bytes = _to_excel_bytes(df_excel)

    st.download_button(
        label="descargar excel",
        data=xlsx_bytes,
        file_name=f"reporte_cobranza_{fecha_corte.strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )