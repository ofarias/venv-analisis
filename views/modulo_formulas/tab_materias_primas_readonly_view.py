import streamlit as st

from controllers.formulas_readonly_controller import listar_materias_primas_readonly_ctrl


def mostrar_tab_materias_primas_readonly():
    st.subheader("materias primas")

    df = listar_materias_primas_readonly_ctrl()

    if df is None or df.empty:
        st.info("no hay materias primas registradas.")
        return

    df.columns = [str(c).lower() for c in df.columns]

    c1, c2, c3 = st.columns(3)

    with c1:
        buscar = st.text_input("buscar MP", key="mp_buscar")

    with c2:
        proveedor = st.selectbox(
            "proveedor",
            ["todos"] + sorted(df["proveedor"].dropna().astype(str).unique().tolist()),
            key="mp_proveedor",
        )

    with c3:
        activas = st.selectbox(
            "estatus MP",
            ["solo activas", "todas", "solo inactivas"],
            key="mp_activas",
        )

    df_view = df.copy()

    if buscar:
        b = buscar.lower().strip()
        df_view = df_view[
            df_view["id"].astype(str).str.lower().str.contains(b, na=False)
            | df_view["nombre"].astype(str).str.lower().str.contains(b, na=False)
        ]

    if proveedor != "todos":
        df_view = df_view[df_view["proveedor"].astype(str) == proveedor]

    if activas == "solo activas":
        df_view = df_view[df_view["activa"] == 1]
    elif activas == "solo inactivas":
        df_view = df_view[df_view["activa"] == 0]

    st.caption(f"materias primas encontradas: {len(df_view):,}")

    st.dataframe(df_view, use_container_width=True, hide_index=True)