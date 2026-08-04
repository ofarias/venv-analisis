import streamlit as st

from views.modulo_formulas.tab_formulas_readonly_view import mostrar_tab_formulas_readonly
from views.modulo_formulas.tab_materias_primas_readonly_view import mostrar_tab_materias_primas_readonly
from views.modulo_formulas.tab_ordenes_produccion_readonly_view import mostrar_tab_ordenes_produccion_readonly
from views.modulo_formulas.tab_pt_faltantes_view import mostrar_tab_pt_faltantes


def _roles_usuario():
    roles = st.session_state.get("roles", [])
    return [str(r).strip().lower() for r in roles]


def puede_ver_formulas():
    roles = _roles_usuario()
    return (
        "formulas" in roles
        or "administrador de formulas" in roles
    )


def mostrar_modulo_formulas():
    st.title("módulo de fórmulas")

    if not puede_ver_formulas():
        st.warning("no tienes permisos para acceder al módulo de fórmulas.")
        return

    tabs = st.tabs([
        "fórmulas",
        "materias primas",
        "órdenes de producción",
        "PT sin fórmula",
    ])

    with tabs[0]:
        mostrar_tab_formulas_readonly()

    with tabs[1]:
        mostrar_tab_materias_primas_readonly()

    with tabs[2]:
        mostrar_tab_ordenes_produccion_readonly()

    with tabs[3]:
        mostrar_tab_pt_faltantes()