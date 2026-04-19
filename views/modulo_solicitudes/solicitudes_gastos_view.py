# views/modulo_solicitudes/solicitudes_gastos_view.py
from __future__ import annotations

import streamlit as st

from views.modulo_solicitudes.tab_solicitud_gastos_view import mostrar_tab_solicitudes_gastos
from views.modulo_solicitudes.tab_catalogo_conceptos_view import mostrar_tab_catalogo_conceptos
from views.modulo_solicitudes.tab_usuarios_forma_pago_view import mostrar_tab_usuarios_forma_pago
from views.modulo_solicitudes.tab_autorizaciones_solicitudes_view import mostrar_tab_autorizaciones_solicitudes
from views.modulo_solicitudes.tab_revisa_contabilidad_view import mostrar_tab_revisa_contabilidad
from views.modulo_solicitudes.tab_dashboard_solicitudes_view import mostrar_tab_dashboard_solicitudes


def mostrar_modulo_solicitudes_gastos():
    usuario = st.session_state.get("usuario") or {}
    roles = [str(x).strip().lower() for x in (usuario.get("roles", []) or [])]

    puede_ver_aut = any(r in roles for r in ["admin", "jefe de ventas", "contabilidad", "compras"])
    puede_ver_rev_conta = any(r in roles for r in ["admin", "contabilidad"])
    puede_ver_dashboard = any(r in roles for r in ["financiero", "direccion", "admin"])

    labels = ["solicitudes"]

    if puede_ver_dashboard:
        labels.append("dashboard")

    if puede_ver_aut:
        labels.append("autorizaciones")

    if puede_ver_rev_conta:
        labels.extend([
            "catálogo conceptos",
            "formas de pago usuario",
            "revisión contabilidad"
        ])

    tabs = st.tabs(labels)
    idx = 0

    with tabs[idx]:
        mostrar_tab_solicitudes_gastos()
    idx += 1

    if puede_ver_dashboard:
        with tabs[idx]:
            mostrar_tab_dashboard_solicitudes()
        idx += 1

    if puede_ver_aut:
        with tabs[idx]:
            mostrar_tab_autorizaciones_solicitudes()
        idx += 1

    if puede_ver_rev_conta:
        with tabs[idx]:
            mostrar_tab_catalogo_conceptos()
        idx += 1

        with tabs[idx]:
            mostrar_tab_usuarios_forma_pago()
        idx += 1

        with tabs[idx]:
            mostrar_tab_revisa_contabilidad()