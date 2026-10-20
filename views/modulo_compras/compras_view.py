import streamlit as st

from views.modulo_compras.tab_catalogos_unificados_view import mostrar_tab_catalogos_unificados
from views.modulo_compras.tab_solicitudes_compras_view import mostrar_tab_solicitudes_compras
from views.modulo_compras.tab_solicitudes_pendientes_view import mostrar_tab_solicitudes_pendientes
from views.modulo_compras.tab_demanda_forecast_view import mostrar_tab_demanda_forecast
from views.modulo_compras.tab_autorizaciones_compras_view import mostrar_tab_autorizaciones_compras


def mostrar_modulo_compras():
    st.title("módulo de compras")

    usuario = st.session_state.get("usuario") or {}
    roles = [str(r).strip().lower() for r in (usuario.get("roles", []) or [])]

    es_admin_compras = (
        "admin" in roles
        or "superadmin" in roles
        or "compras" in roles
    )
    # autoriza Solicitudes de Compra tipo Materia Prima (Inventario) — no
    # hay jerarquía de Jefe/Gerente de Compras, se decidió que solo
    # SuperAdmin/forecastAdmin autorizan (ver plan)
    es_autorizador_compras = "superadmin" in roles or "forecastadmin" in roles

    tabs = ["Solicitudes", "Pendientes"]

    if es_admin_compras:
        tabs = ["Catálogos"] + tabs + ["📦 Demanda (Forecast)"]
    if es_autorizador_compras:
        tabs = tabs + ["✅ Autorizaciones"]

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
    i += 1

    if es_admin_compras:
        with tabs_render[i]:
            mostrar_tab_demanda_forecast()
        i += 1

    if es_autorizador_compras:
        with tabs_render[i]:
            mostrar_tab_autorizaciones_compras()