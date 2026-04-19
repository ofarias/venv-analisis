import streamlit as st

from views.modulo_compras.tab_catalogos_compras_view import mostrar_tab_catalogos_compras
from views.modulo_compras.tab_catalogos_adicionales_view import mostrar_tab_catalogos_adicionales
from views.modulo_compras.tab_solicitudes_compras_view import mostrar_tab_solicitudes_compras
from views.modulo_compras.tab_solicitudes_pendientes_view import mostrar_tab_solicitudes_pendientes


def mostrar_modulo_compras():
    st.title("módulo de compras")

    tabs = st.tabs([
        "catálogos tipos",
        "catálogos adicionales",
        "solicitudes de compra",
        "solicitudes pendientes",
    ])

    with tabs[0]:
        mostrar_tab_catalogos_compras()

    with tabs[1]:
        mostrar_tab_catalogos_adicionales()

    with tabs[2]:
        mostrar_tab_solicitudes_compras()

    with tabs[3]:
        mostrar_tab_solicitudes_pendientes()