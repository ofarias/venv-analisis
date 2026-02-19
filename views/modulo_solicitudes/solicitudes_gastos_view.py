# views/modulo_solicitudes/solicitudes_gastos_view.py
from __future__ import annotations

import streamlit as st

from views.modulo_solicitudes.tab_solicitud_gastos_view import mostrar_tab_solicitudes_gastos
from views.modulo_solicitudes.tab_catalogo_conceptos_view import mostrar_tab_catalogo_conceptos
from views.modulo_solicitudes.tab_usuarios_forma_pago_view import mostrar_tab_usuarios_forma_pago

def mostrar_modulo_solicitudes_gastos():
    t1, t2, t3 = st.tabs(["solicitudes", "catálogo conceptos", "Formas de Pago Usuario"])

    with t1:
        mostrar_tab_solicitudes_gastos()

    with t2:
        mostrar_tab_catalogo_conceptos()

    with t3:
        mostrar_tab_usuarios_forma_pago()