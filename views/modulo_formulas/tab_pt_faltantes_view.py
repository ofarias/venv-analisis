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

    n_urgentes = int(df["en_presupuesto_autorizado"].sum())
    if n_urgentes:
        st.error(
            f"⚠️ {n_urgentes:,} de estos productos SÍ están en un presupuesto "
            "de ventas autorizado y no tienen fórmula — atender primero "
            "(marcados en rojo abajo)."
        )

    c1, c2, c3 = st.columns([2, 2, 1])

    with c1:
        buscar = st.text_input("buscar", key="pt_faltantes_buscar")

    with c2:
        linea = st.selectbox(
            "línea",
            ["todas"] + sorted(df["linea"].dropna().astype(str).unique().tolist()),
            key="pt_faltantes_linea",
        )

    with c3:
        solo_urgentes = st.checkbox(
            "solo en presupuesto",
            value=False,
            key="pt_faltantes_solo_urgentes",
            help="mostrar solo los que sí están en un presupuesto autorizado",
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

    if solo_urgentes:
        df_view = df_view[df_view["en_presupuesto_autorizado"]]

    df_view = df_view.sort_values(
        "en_presupuesto_autorizado", ascending=False
    ).reset_index(drop=True)

    st.caption(f"mostrando {len(df_view):,} de {len(df):,}")

    df_mostrar = df_view.rename(columns={
        "cve_sae": "clave SAE",
        "descripcion": "producto",
        "linea": "línea",
        "en_presupuesto_autorizado": "en presupuesto autorizado",
    })

    def _row_style(row):
        bg = "background-color: #f8d7da; color: #721c24;" if row["en presupuesto autorizado"] else ""
        return [bg for _ in row.index]

    st.dataframe(
        df_mostrar.style.apply(_row_style, axis=1),
        use_container_width=True,
        hide_index=True,
    )
