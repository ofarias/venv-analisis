import streamlit as st

from controllers.formulas_readonly_controller import listar_pt_sin_formula_ctrl


def mostrar_tab_pt_faltantes():
    st.subheader("productos PT sin fórmula")
    st.caption(
        "productos terminados (clave inicia con PT) activos en SAE que "
        "todavía no tienen una fórmula registrada en el módulo."
    )

    with st.spinner("consultando SAE…"):
        df = listar_pt_sin_formula_ctrl()

    if df is None or df.empty:
        st.success("todos los productos PT activos ya tienen fórmula.")
        return

    st.warning(f"faltan {len(df):,} productos PT por registrar en fórmulas.")

    c1, c2 = st.columns(2)

    with c1:
        buscar = st.text_input("buscar", key="pt_faltantes_buscar")

    with c2:
        linea = st.selectbox(
            "línea",
            ["todas"] + sorted(df["linea"].dropna().astype(str).unique().tolist()),
            key="pt_faltantes_linea",
        )

    df_view = df.copy()

    if buscar:
        b = buscar.lower().strip()
        df_view = df_view[
            df_view["cve_sae"].astype(str).str.lower().str.contains(b, na=False)
            | df_view["descripcion"].astype(str).str.lower().str.contains(b, na=False)
        ]

    if linea != "todas":
        df_view = df_view[df_view["linea"].astype(str) == linea]

    st.caption(f"mostrando {len(df_view):,} de {len(df):,}")

    st.dataframe(
        df_view.rename(columns={
            "cve_sae": "clave SAE",
            "descripcion": "producto",
            "linea": "línea",
        }),
        use_container_width=True,
        hide_index=True,
    )
