from __future__ import annotations

import pandas as pd
import streamlit as st

from controllers.forecast_controller import obtener_forecast_versiones_ctrl
from views.modulo_forecast.tab_versiones_view import mostrar_tab_versiones
from views.modulo_forecast.tab_construccion_view import mostrar_tab_construccion
from views.modulo_forecast.tab_real_vs_forecast_view import mostrar_tab_real_vs_forecast
from views.modulo_forecast.tab_mdi_view import mostrar_tab_mdi
from views.modulo_forecast.tab_compras_view import mostrar_tab_compras
from views.modulo_forecast.tab_dashboard_view import mostrar_tab_dashboard


def _get_usuario_id() -> int:
    u = st.session_state.get("usuario") or {}
    return int(u.get("id") or u.get("id_usuario") or 0)


def _norm_roles_list(values) -> list[str]:
    if not values:
        return []
    if isinstance(values, str):
        values = [values]
    return [str(v).strip().lower() for v in values if str(v or "").strip()]


def _tiene_rol(roles: list[str], *objetivos: str) -> bool:
    roles_set = set(_norm_roles_list(roles))
    objetivos_set = set(_norm_roles_list(objetivos))
    return bool(roles_set.intersection(objetivos_set))


def _puede_ver_todos_forecast() -> bool:
    usuario = st.session_state.get("usuario") or {}
    if usuario.get("rol") == "Admin":
        return True
    return _tiene_rol(usuario.get("roles"), "admin", "superadmin", "forecastadmin")


def _selector_version() -> dict | None:
    """Selector de versión activa en el sidebar de la sección."""
    usuario_id = _get_usuario_id()
    ver_todas = _puede_ver_todos_forecast()
    df = obtener_forecast_versiones_ctrl(usuario_id=usuario_id, ver_todas=ver_todas)

    if df is None or df.empty:
        return None

    if ver_todas:
        opciones = {
            f"{r['id_version']} | {r['nombre']} [{r['anio']}] — {r['estatus']} — {r.get('propietario') or 'usuario ' + str(r['usuario_id'])}": r
            for r in df.to_dict("records")
        }
    else:
        opciones = {
            f"{r['id_version']} | {r['nombre']} [{r['anio']}] — {r['estatus']}": r
            for r in df.to_dict("records")
        }
    labels = list(opciones.keys())
    default_id = st.session_state.get("fc_id_version")
    idx = 0
    if default_id:
        for i, lbl in enumerate(labels):
            if opciones[lbl]["id_version"] == default_id:
                idx = i
                break

    sel = st.selectbox("versión de forecast", labels, index=idx, key="fc_select_version")
    version = opciones[sel]
    st.session_state["fc_id_version"] = int(version["id_version"])
    return version


def mostrar_modulo_forecast() -> None:
    st.subheader("Forecast — Centro de Planeación Comercial")

    tab_dash, tab_const, tab_rvf, tab_mdi, tab_comp, tab_ver = st.tabs([
        "📊 Dashboard",
        "📈 Construcción del Forecast",
        "📉 Real vs Forecast",
        "🗺️ MDI — Mapa de Inventario",
        "📦 Necesidades de Compra",
        "⚙️ Versiones",
    ])

    with tab_ver:
        mostrar_tab_versiones()

    # para los demás tabs necesitamos una versión seleccionada
    version = _selector_version()

    if version is None:
        for tab in (tab_dash, tab_const, tab_rvf, tab_mdi, tab_comp):
            with tab:
                st.info("crea una versión de forecast en el tab ⚙️ Versiones para comenzar")
        return

    id_version  = int(version["id_version"])
    anio        = int(version["anio"])
    id_carga_pv = version.get("id_carga_pv")
    id_carga_pv = int(id_carga_pv) if id_carga_pv is not None and not pd.isna(id_carga_pv) else None
    metodo_def  = str(version.get("metodo_default") or "manual")
    # dueño de la versión — no necesariamente quien la está viendo (un
    # forecastAdmin puede estar viendo la versión de otro usuario); todo
    # cálculo que use presupuesto propio debe basarse en este id, no en el
    # usuario de la sesión
    usuario_datos_id = int(version["usuario_id"]) if version.get("usuario_id") else _get_usuario_id()

    # meses del selector global (persiste en session_state desde tab_construccion)
    meses_sel: list[int] = st.session_state.get("fc_meses_sel", list(range(1, 13)))

    with tab_dash:
        mostrar_tab_dashboard(id_version=id_version, anio=anio)

    with tab_const:
        mostrar_tab_construccion(
            id_version=id_version,
            id_carga_pv=id_carga_pv,
            anio=anio,
            metodo_default=metodo_def,
            usuario_datos_id=usuario_datos_id,
        )

    with tab_rvf:
        mostrar_tab_real_vs_forecast(
            id_version=id_version, anio=anio, meses=meses_sel, usuario_datos_id=usuario_datos_id,
        )

    with tab_mdi:
        mostrar_tab_mdi(id_version=id_version, anio=anio, meses=meses_sel)

    with tab_comp:
        mostrar_tab_compras(id_version=id_version, anio=anio, meses=meses_sel)
