import streamlit as st

from views.modulo_compras.tab_catalogos_unificados_view import mostrar_tab_catalogos_unificados
from views.modulo_compras.tab_solicitudes_compras_view import mostrar_tab_solicitudes_compras
from views.modulo_compras.tab_solicitudes_pendientes_view import mostrar_tab_solicitudes_pendientes


def mostrar_modulo_compras():
    st.title("módulo de compras")

    usuario = st.session_state.get("usuario") or {}
    roles = [str(r).strip().lower() for r in (usuario.get("roles", []) or [])]

    es_admin_compras = (
        "admin" in roles
        or "superadmin" in roles
        or "compras" in roles
    )

    tabs = ["Solicitudes", "Pendientes"]

    if es_admin_compras:
        tabs.insert(0, "Catálogos")

    tabs_render = st.tabs(tabs)

    i = 0

    if es_admin_compras:
        with tabs_render[i]:
            mostrar_tab_catalogos_unificados()
        i += 1

    with tabs_render[i]:
        mostrar_tab_solicitudes_compras()
    i += 1

    with tabs_render[i]:
        mostrar_tab_solicitudes_pendientes()