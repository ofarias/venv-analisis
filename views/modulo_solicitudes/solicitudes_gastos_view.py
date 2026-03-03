# views/modulo_solicitudes/solicitudes_gastos_view.py
from __future__ import annotations

import streamlit as st

from views.modulo_solicitudes.tab_solicitud_gastos_view import mostrar_tab_solicitudes_gastos
from views.modulo_solicitudes.tab_catalogo_conceptos_view import mostrar_tab_catalogo_conceptos
from views.modulo_solicitudes.tab_usuarios_forma_pago_view import mostrar_tab_usuarios_forma_pago
from views.modulo_solicitudes.tab_autorizaciones_solicitudes_view import mostrar_tab_autorizaciones_solicitudes


def mostrar_modulo_solicitudes_gastos():
    usuario = st.session_state.get("usuario") or {}
    roles = [str(x).strip().lower() for x in (usuario.get("roles", []) or [])]

    puede_ver_aut = any(r in roles for r in ["admin", "jefe ventas", "contabilidad", "compras"])

    labels = ["solicitudes", "catálogo conceptos", "formas de pago usuario"]
    if puede_ver_aut:
        labels.append("autorizaciones")

    tabs = st.tabs(labels)

    with tabs[0]:
        mostrar_tab_solicitudes_gastos()

    with tabs[1]:
        mostrar_tab_catalogo_conceptos()

    with tabs[2]:
        mostrar_tab_usuarios_forma_pago()

    if puede_ver_aut:
        with tabs[3]:
            mostrar_tab_autorizaciones_solicitudes()