#tab_mis_gastos_fiscales.py
import streamlit as st
import pandas as pd
from controllers.presupuesto_controller import get_gastos_fiscales_por_usuario

def mostrar_tab_mis_gastos_fiscales():
    st.subheader("💼 Mis Gastos Fiscales (CFDI)")

    user = st.session_state["usuario"]
    username = user.get("username")

    df = get_gastos_fiscales_por_usuario(username)

    if df.empty:
        st.info("No tienes gastos fiscales registrados.")
        return

    # --- filtros principales ---
    col1, col2, col3 = st.columns(3)
    with col1:
        presupuestos = ["Todos"] + sorted(df["presupuesto"].dropna().unique().tolist())
        presupuesto_sel = st.selectbox(
            "Presupuesto",
            options=presupuestos,
            index=0,
            key="mis_gastos_fiscales_presupuesto",
        )

    with col2:
        estatus_opts = sorted(df["estatus"].dropna().unique().tolist())
        estatus_sel = st.multiselect(
            "Estatus",
            options=estatus_opts,
            default=estatus_opts,
            key="mis_gastos_fiscales_estatus",
        )

    with col3:
        moneda_sel = st.radio(
            "Moneda",
            options=["MXN", "USD", "Ambas"],
            index=2,
            horizontal=True,
            key="mis_gastos_fiscales_moneda",
        )

    # --- aplica filtros ---
    df_filtrado = df.copy()
    if presupuesto_sel != "Todos":
        df_filtrado = df_filtrado[df_filtrado["presupuesto"] == presupuesto_sel]
    df_filtrado = df_filtrado[df_filtrado["estatus"].isin(estatus_sel)]

    df_filtrado["monto"] = df_filtrado.apply(
        lambda r: r["monto_mnx"] if r["monto_mnx"] else r["monto_usd"], axis=1
    )
    df_filtrado["moneda"] = df_filtrado.apply(
        lambda r: "MXN" if r["monto_mnx"] else "USD", axis=1
    )
    if moneda_sel != "Ambas":
        df_filtrado = df_filtrado[df_filtrado["moneda"] == moneda_sel]

    # --- formato monetario ---
    df_filtrado["monto"] = df_filtrado["monto"].apply(lambda x: f"${x:,.2f}")

    # --- tabla principal ---
    st.dataframe(
        df_filtrado[
            [
                "presupuesto",
                "unidad",
                "proveedor",
                "rfc_emisor",
                "documento",
                "uuid",
                "monto",
                "moneda",
                "estatus",
                "autorizador",
                "fecha_registro",
            ]
        ].sort_values("fecha_registro", ascending=False),
        use_container_width=True,
        hide_index=True,
    )

    # --- resumen ---
    with st.expander("📊 Resumen de totales"):
        resumen = (
            df_filtrado.groupby(["presupuesto", "moneda"], as_index=False)
            .agg({"monto": lambda x: pd.to_numeric(x.str.replace("[$,]", "", regex=True)).sum()})
        )
        if not resumen.empty:
            total_general = pd.DataFrame(
                {"presupuesto": ["Total general"], "moneda": [""], "monto": [resumen["monto"].sum()]}
            )
            resumen = pd.concat([resumen, total_general], ignore_index=True)
            resumen["monto"] = resumen["monto"].apply(lambda x: f"${x:,.2f}")
        st.dataframe(resumen, use_container_width=True, hide_index=True)