import streamlit as st
import pandas as pd
from controllers.presupuesto_controller import get_gastos_no_fiscales_por_usuario

def mostrar_tab_mis_gastos_no_fiscales():
    st.subheader("📋 Mis Gastos No Fiscales")

    user = st.session_state["usuario"]
    user_id = user.get("id")

    df = get_gastos_no_fiscales_por_usuario(user_id)

    if df.empty:
        st.info("No tienes gastos no fiscales registrados.")
        return

    # --- filtros principales ---
    col1, col2, col3 = st.columns(3)
    with col1:
        presupuestos = ["Todos"] + sorted(df["presupuesto"].dropna().unique().tolist())
        presupuesto_sel = st.selectbox("Presupuesto", options=presupuestos, index=0)

    with col2:
        estatus_sel = st.multiselect(
            "Estatus",
            options=sorted(df["estatus"].dropna().unique().tolist()),
            default=sorted(df["estatus"].dropna().unique().tolist()),
        )

    with col3:
        tipo_sel = st.multiselect(
            "Tipo de gasto",
            options=sorted(df["tipo"].dropna().unique().tolist()),
            default=sorted(df["tipo"].dropna().unique().tolist()),
        )

    # --- aplica filtros ---
    df_filtrado = df.copy()
    if presupuesto_sel != "Todos":
        df_filtrado = df_filtrado[df_filtrado["presupuesto"] == presupuesto_sel]

    df_filtrado = df_filtrado[
        df_filtrado["estatus"].isin(estatus_sel) & df_filtrado["tipo"].isin(tipo_sel)
    ]

    # --- formato de número ---
    if not df_filtrado.empty:
        df_filtrado["monto"] = df_filtrado["monto"].apply(lambda x: f"${x:,.2f}")
    
    # --- muestra tabla ---
    st.dataframe(
        df_filtrado.sort_values("fecha_gasto", ascending=False),
        use_container_width=True,
        hide_index=True,
    )

    # --- resumen de totales ---
    with st.expander("📊 Resumen de totales"):
        resumen = (
            df.query("estatus in @estatus_sel and tipo in @tipo_sel")
            .groupby(["presupuesto", "tipo"], as_index=False)["monto"]
            .sum()
            .sort_values(["presupuesto", "tipo"])
        )

        if not resumen.empty:
            total_general = pd.DataFrame(
                {
                    "presupuesto": ["Total general"],
                    "tipo": [""],
                    "monto": [resumen["monto"].sum()],
                }
            )
            resumen = pd.concat([resumen, total_general], ignore_index=True)

            # formato monetario
            resumen["monto"] = resumen["monto"].apply(lambda x: f"${x:,.2f}")

        st.dataframe(
            resumen,
            use_container_width=True,
            hide_index=True,
        )