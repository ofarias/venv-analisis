import streamlit as st

from views.modulo_formulas.tab_formulas_view import mostrar_tab_formulas
from views.modulo_formulas.tab_catalogo_mp_view import mostrar_tab_catalogo_mp
from views.modulo_formulas.tab_calculadora_coa_view import mostrar_tab_calculadora_coa


def _roles_usuario():
    roles = st.session_state.get("roles", [])
    return [str(r).strip().lower() for r in roles]

def puede_ver_formulas():
    roles = _roles_usuario()
    return "formulas" in roles or "administrador de formulas" in roles

def puede_administrar_formulas():
    roles = _roles_usuario()   
    return "administrador de formulas" in roles

def mostrar_modulo_formulas():
    st.title("módulo de fórmulas")

    if not puede_ver_formulas():
        st.warning("no tienes permisos para acceder al módulo de fórmulas.")
        return

    tabs = st.tabs([
        "fórmulas",
        "catálogo MP",
        "calculadora CoA",
    ])

    es_admin = puede_administrar_formulas()

    with tabs[0]:
        mostrar_tab_formulas(es_admin=es_admin)

    with tabs[1]:
        mostrar_tab_catalogo_mp(es_admin=es_admin)

    with tabs[2]:
        mostrar_tab_calculadora_coa()
