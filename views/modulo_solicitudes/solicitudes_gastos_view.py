# views/modulo_solicitudes/solicitudes_gastos_view.py
from __future__ import annotations

import streamlit as st

from views.modulo_solicitudes.tab_solicitud_gastos_view import mostrar_tab_solicitudes_gastos
from views.modulo_solicitudes.tab_catalogo_conceptos_view import mostrar_tab_catalogo_conceptos


def mostrar_modulo_solicitudes_gastos():
    t1, t2 = st.tabs(["solicitudes", "catálogo conceptos"])

    with t1:
        mostrar_tab_solicitudes_gastos()

    with t2:
        mostrar_tab_catalogo_conceptos()