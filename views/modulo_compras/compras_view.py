import streamlit as st

from views.modulo_compras.tab_catalogos_compras_view import mostrar_tab_catalogos_compras
from views.modulo_compras.tab_solicitudes_compras_view import mostrar_tab_solicitudes_compras


def mostrar_modulo_compras():
    st.title("módulo de compras")

    tabs = st.tabs([
        "catálogos",
        "solicitudes de compra",
    ])

    with tabs[0]:
        mostrar_tab_catalogos_compras()

    with tabs[1]:
        mostrar_tab_solicitudes_compras()