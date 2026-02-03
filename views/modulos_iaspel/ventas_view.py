# views/modulos_iaspel/ventas_view.py
import streamlit as st
import pandas as pd
import altair as alt
from controllers.ventas_controller import (
    cargar_ventas, kpis_ventas, ventas_mensuales,
    top_clientes, top_productos, ventas_por_vendedor
)

# subir límite de celdas estilizadas
pd.set_option("styler.render.max_elements", 1_000_000)

def pantalla_ventas():
    st.title("análisis de ventas")

    # --------- filtros ---------
    c1, c2, c3, c4 = st.columns(4)
    f1 = c1.date_input("desde", None)
    f2 = c2.date_input("hasta", None)
    cliente  = c3.text_input("cliente (CVE_CLPV)", "")
    vendedor = c4.number_input("vendedor (CVE_VEND)", min_value=0, value=0, step=1, format="%d")

    c5, c6, c7 = st.columns(3)
    moneda = c5.number_input("moneda (NUM_MONED)", min_value=0, value=0, step=1, format="%d")
    status = c6.selectbox("status", ["", "A", "B"], index=1)  # A por defecto
    btn    = c7.button("consultar")

    if not btn:
        st.info("configura filtros y pulsa **consultar**.")
        return

    # --------- carga de datos ---------
    df = cargar_ventas(
        str(f1) if f1 else None,
        str(f2) if f2 else None,
        cliente.strip() or None,
        int(vendedor) if vendedor else None,
        int(moneda) if moneda else None,
        status or None
    )

    if df.empty:
        st.warning("sin resultados")
        return

    # asegurar tipos numéricos
    num_cols = [
        "CANTIDAD","PRECIO","IMPORTE","TCAMBIO",
        "IMPORTE_MN","COSTO","COSTO_MN","UTILIDAD_MN","MARGEN_PCT"
    ]
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # margen en porcentaje real
    if "MARGEN_PCT" in df.columns:
        df["MARGEN_%"] = (df["MARGEN_PCT"] / 100.0).fillna(0)

    # --------- kpis ---------
    met = kpis_ventas(df)
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("ventas MN", f"$ {met['ventas_mn']:,.2f}")
    k2.metric("partidas", f"{met['partidas']:,d}")
    k3.metric("clientes", f"{met['clientes']:,d}")
    k4.metric("margen %", f"{met['margen_pct']:.2f}%")

    # --------- gráfica mensual ---------
    st.subheader("ventas por mes (MN)")
    mens = ventas_mensuales(df)
    st.altair_chart(
        alt.Chart(mens).mark_bar().encode(
            x=alt.X("MES:N", title="Mes"),
            y=alt.Y("IMPORTE_MN:Q", title="Ventas MN", axis=alt.Axis(format="$,.2f")),
            tooltip=[alt.Tooltip("MES:N"), alt.Tooltip("IMPORTE_MN:Q", format="$,.2f", title="Ventas MN")]
        ).properties(width="container", height=300),
        use_container_width=True
    )

    # --------- gráfica por vendedor ---------
    st.subheader("ventas por vendedor (MN)")
    por_vend = ventas_por_vendedor(df).head(20)
    st.altair_chart(
        alt.Chart(por_vend).mark_bar().encode(
            x=alt.X("IMPORTE_MN:Q", title="Ventas MN", axis=alt.Axis(format="$,.2f")),
            y=alt.Y("VENDEDOR:N", sort="-x", title="Vendedor"),
            tooltip=[alt.Tooltip("VENDEDOR:N"), alt.Tooltip("IMPORTE_MN:Q", format="$,.2f")]
        ).properties(width="container", height=420),
        use_container_width=True
    )

    # --------- detalle partidas ---------
    st.subheader("detalle de partidas")

    cols = [
        "FECHA_DOC","CVE_DOC","CVE_CLPV","CLIENTE","CVE_VEND","VENDEDOR",
        "CVE_ART","CANTIDAD","PRECIO","IMPORTE","MONEDA","TCAMBIO",
        "IMPORTE_MN","COSTO","COSTO_MN","UTILIDAD_MN","MARGEN_%"
    ]
    df_show = df[cols].copy()

    # formato de fechas
    if "FECHA_DOC" in df_show:
        df_show["FECHA_DOC"] = pd.to_datetime(df_show["FECHA_DOC"], errors="coerce").dt.strftime("%Y-%m-%d")

    fmt = {
        "CANTIDAD":    "{:,.2f}".format,
        "PRECIO":      lambda v: f"$ {v:,.2f}",
        "IMPORTE":     lambda v: f"$ {v:,.2f}",
        "TCAMBIO":     "{:,.4f}".format,
        "IMPORTE_MN":  lambda v: f"$ {v:,.2f}",
        "COSTO":       lambda v: f"$ {v:,.2f}",
        "COSTO_MN":    lambda v: f"$ {v:,.2f}",
        "UTILIDAD_MN": lambda v: f"$ {v:,.2f}",
        "MARGEN_%":    "{:.2%}".format,
    }
    right_align = list(fmt.keys())

    # toggle para mostrar todo o preview
    full = st.checkbox("mostrar toda la tabla con formato", value=False)

    if full:
        styled = (
            df_show
              .style
              .format(fmt, na_rep="")
              .set_properties(subset=right_align, **{"text-align": "right"})
        )
        st.dataframe(styled, use_container_width=True)
    else:
        df_preview = df_show.head(5000).copy()
        styled = (
            df_preview
              .style
              .format(fmt, na_rep="")
              .set_properties(subset=right_align, **{"text-align": "right"})
        )
        st.dataframe(styled, use_container_width=True)
        st.caption("mostrando solo las primeras 5000 filas con formato, usa el check para ver todo")

    # --------- top clientes ---------
    st.subheader("top clientes (MN)")
    tc = top_clientes(df, 20)
    styled_tc = (
        tc.style
          .format({"IMPORTE_MN": lambda v: f"$ {v:,.2f}"}, na_rep="")
          .set_properties(subset=["IMPORTE_MN"], **{"text-align": "right"})
    )
    st.dataframe(styled_tc, use_container_width=True)

    # --------- top productos ---------
    st.subheader("top productos (MN)")
    tp = top_productos(df, 20)
    styled_tp = (
        tp.style
          .format({
              "VENTAS_MN": lambda v: f"$ {v:,.2f}",
              "CANTIDAD": "{:,.2f}".format,
          }, na_rep="")
          .set_properties(subset=["VENTAS_MN","CANTIDAD"], **{"text-align": "right"})
    )
    st.dataframe(styled_tp, use_container_width=True)

    # --------- exportar excel ---------
    def to_excel_bytes():
        with pd.ExcelWriter("/tmp/ventas.xlsx", engine="xlsxwriter") as wr:
            df.to_excel(wr, index=False, sheet_name="partidas")
            tc.to_excel(wr, index=False, sheet_name="top_clientes")
            tp.to_excel(wr, index=False, sheet_name="top_productos")
            mens.to_excel(wr, index=False, sheet_name="mensual")
        with open("/tmp/ventas.xlsx","rb") as f:
            return f.read()

    st.download_button("descargar excel", data=to_excel_bytes(), file_name="ventas.xlsx")