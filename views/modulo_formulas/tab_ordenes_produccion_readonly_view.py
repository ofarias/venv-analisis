import pandas as pd
import streamlit as st

from controllers.formulas_readonly_controller import (
    listar_ordenes_produccion_readonly_ctrl,
    obtener_orden_produccion_readonly_ctrl,
)


def _json_to_df(value):
    if not value:
        return pd.DataFrame()
    if isinstance(value, list):
        return pd.DataFrame(value)
    if isinstance(value, dict):
        return pd.DataFrame([value])
    return pd.DataFrame({"valor": [str(value)]})


def mostrar_tab_ordenes_produccion_readonly():
    st.subheader("órdenes de producción")

    df = listar_ordenes_produccion_readonly_ctrl()

    if df.empty:
        st.info("no hay órdenes de producción registradas.")
        return

    c1, c2, c3 = st.columns(3)

    with c1:
        buscar = st.text_input("buscar orden / producto / lote")

    with c2:
        cliente = st.selectbox(
            "cliente",
            ["todos"] + sorted(df["cliente"].dropna().astype(str).unique().tolist())
        )

    with c3:
        tipo = st.selectbox(
            "tipo",
            ["todos"] + sorted(df["tipo"].dropna().astype(str).unique().tolist())
        )

    df_view = df.copy()

    if buscar:
        b = buscar.lower().strip()
        df_view = df_view[
            df_view["ord"].astype(str).str.lower().str.contains(b, na=False)
            | df_view["producto"].astype(str).str.lower().str.contains(b, na=False)
            | df_view["lote"].astype(str).str.lower().str.contains(b, na=False)
            | df_view["clave_formula"].astype(str).str.lower().str.contains(b, na=False)
        ]

    if cliente != "todos":
        df_view = df_view[df_view["cliente"].astype(str) == cliente]

    if tipo != "todos":
        df_view = df_view[df_view["tipo"].astype(str) == tipo]

    st.caption(f"órdenes encontradas: {len(df_view):,}")

    st.dataframe(df_view, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("detalle de orden")

    opciones = {
        f"{r['ord']} - {r['producto']}": r["ord"]
        for _, r in df_view.iterrows()
    }

    sel = st.selectbox("selecciona orden", [""] + list(opciones.keys()))

    if not sel:
        return

    ord_id = opciones[sel]
    orden = obtener_orden_produccion_readonly_ctrl(ord_id)

    if not orden:
        st.warning("no se encontró la orden.")
        return

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.metric("orden", orden.get("ord", ""))

    with c2:
        st.metric("lote", orden.get("lote", ""))

    with c3:
        st.metric("kg", f"{float(orden.get('kg') or 0):,.3f}")

    with c4:
        st.metric("versión", orden.get("version", ""))

    st.write(f"**producto:** {orden.get('producto', '')}")
    st.write(f"**cliente:** {orden.get('cliente', '')}")
    st.write(f"**fórmula:** {orden.get('clave_formula', '')}")

    if orden.get("observaciones"):
        st.info(orden.get("observaciones"))

    st.markdown("### materias primas")

    df_mp = _json_to_df(orden.get("materias_primas"))

    if df_mp.empty:
        st.info("sin materias primas registradas en la orden.")
    else:
        st.dataframe(df_mp, use_container_width=True, hide_index=True)