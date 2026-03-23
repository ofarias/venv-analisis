# views/modulo_solicitudes/solicitudes_gastos_view.py
from __future__ import annotations

import streamlit as st

from views.modulo_solicitudes.tab_solicitud_gastos_view import mostrar_tab_solicitudes_gastos
from views.modulo_solicitudes.tab_catalogo_conceptos_view import mostrar_tab_catalogo_conceptos
from views.modulo_solicitudes.tab_usuarios_forma_pago_view import mostrar_tab_usuarios_forma_pago
from views.modulo_solicitudes.tab_autorizaciones_solicitudes_view import mostrar_tab_autorizaciones_solicitudes
from views.modulo_solicitudes.tab_revisa_contabilidad_view import mostrar_tab_revisa_contabilidad


def mostrar_modulo_solicitudes_gastos():
    usuario = st.session_state.get("usuario") or {}
    roles = [str(x).strip().lower() for x in (usuario.get("roles", []) or [])]

    puede_ver_aut = any(r in roles for r in ["admin", "jefe ventas", "contabilidad", "compras"])
    puede_ver_rev_conta = any(r in roles for r in ["admin", "contabilidad"])
    
    labels = ["solicitudes", "catálogo conceptos", "formas de pago usuario"]

    if puede_ver_aut:
        labels.append("autorizaciones")

    if puede_ver_rev_conta:
        labels.append("revisión contabilidad")
        
    tabs = st.tabs(labels)
    idx = 0
    with tabs[idx]:
        mostrar_tab_solicitudes_gastos()
    idx += 1
    with tabs[idx]:
        mostrar_tab_catalogo_conceptos()
    idx += 1
    with tabs[idx]:
        mostrar_tab_usuarios_forma_pago()
    idx += 1
    if puede_ver_aut:
        with tabs[idx]:
            mostrar_tab_autorizaciones_solicitudes()
        idx += 1
    if puede_ver_rev_conta:
        with tabs[idx]:
            mostrar_tab_revisa_contabilidad()