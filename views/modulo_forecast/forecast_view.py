from __future__ import annotations

import pandas as pd
import streamlit as st

from controllers.forecast_controller import obtener_forecast_versiones_ctrl
from controllers.usuario_controller import get_usuarios
from views.modulo_forecast.tab_versiones_view import mostrar_tab_versiones
from views.modulo_forecast.tab_construccion_view import mostrar_tab_construccion
from views.modulo_forecast.tab_real_vs_forecast_view import mostrar_tab_real_vs_forecast
from views.modulo_forecast.tab_mdi_view import mostrar_tab_mdi
from views.modulo_forecast.tab_compras_view import mostrar_tab_compras
from views.modulo_forecast.tab_dashboard_view import mostrar_tab_dashboard


def _usuario_real_id() -> int:
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


def _es_superadmin() -> bool:
    usuario = st.session_state.get("usuario") or {}
    return _tiene_rol(usuario.get("roles"), "superadmin")


def _get_usuario_id() -> int:
    """Usuario "activo" para efectos de forecast (crear versión, listar
    cargas propias para vincular, autor de cada fila capturada).

    Si quien tiene la sesión es SuperAdmin y eligió un usuario en el panel
    de soporte (`_panel_soporte_seleccionar_usuario`), se actúa como ese
    usuario para poder darle asistencia sin pedirle sus credenciales —
    mismo mecanismo que `presupuesto_ventas_view.py::_get_usuario_id`.
    Cualquier otro rol siempre ve/opera lo suyo.
    """
    usuario = st.session_state.get("usuario") or {}
    soporte_id = st.session_state.get("fc_soporte_usuario_id")
    if soporte_id and _tiene_rol(usuario.get("roles"), "superadmin"):
        return int(soporte_id)
    return _usuario_real_id()


def _panel_soporte_seleccionar_usuario() -> None:
    """Solo SuperAdmin: permite elegir un usuario para ver/crear/capturar su
    forecast con fines de asistencia y soporte, sin necesitar sus
    credenciales. La elección se guarda en sesión y la usa `_get_usuario_id()`
    (también en tab_versiones_view.py y tab_construccion_view.py) mientras
    dure la sesión o hasta que se vuelva a "— mi usuario —"."""
    if not _es_superadmin():
        return

    df_usuarios = get_usuarios()
    if df_usuarios is None or df_usuarios.empty or "id" not in df_usuarios.columns:
        return

    if "estatus" in df_usuarios.columns:
        df_usuarios = df_usuarios[
            df_usuarios["estatus"].astype(str).str.strip().str.lower() != "inactivo"
        ]

    usuario_real_id = _usuario_real_id()
    col_nombre = "nombre" if "nombre" in df_usuarios.columns else "username"
    df_usuarios = df_usuarios.sort_values(col_nombre)

    opciones = {"— mi usuario —": None}
    for r in df_usuarios.to_dict(orient="records"):
        uid = int(r["id"])
        if uid == usuario_real_id:
            continue
        etiqueta = f"{r.get('nombre') or r.get('username')} ({r.get('username')})"
        opciones[etiqueta] = uid

    labels_usuarios = list(opciones.keys())
    valor_actual = st.session_state.get("fc_soporte_usuario_id")
    idx = next((i for i, l in enumerate(labels_usuarios) if opciones[l] == valor_actual), 0)

    with st.expander(
        "🛠️ soporte SuperAdmin — ver/crear/capturar forecast de otro usuario",
        expanded=valor_actual is not None,
    ):
        label = st.selectbox(
            "actuar como usuario",
            options=labels_usuarios,
            index=idx,
            key="fc_soporte_usuario_select",
            help=(
                "para dar soporte: mientras esté seleccionado, crear versión, vincular "
                "presupuesto propio y capturar el forecast muestran y guardan como si "
                "fueras esa persona. Elige '— mi usuario —' para volver a lo tuyo."
            ),
        )
        nuevo_id = opciones[label]
        if nuevo_id != st.session_state.get("fc_soporte_usuario_id"):
            st.session_state["fc_soporte_usuario_id"] = nuevo_id
            st.session_state["fc_soporte_usuario_nombre"] = label if nuevo_id else None
            st.session_state.pop("fc_id_version", None)
            st.rerun()

    if st.session_state.get("fc_soporte_usuario_id"):
        st.warning(
            f"🛠️ modo soporte activo — viendo y capturando como "
            f"**{st.session_state.get('fc_soporte_usuario_nombre')}**",
        )


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


_SECCIONES_FORECAST = [
    "📊 Dashboard",
    "📈 Construcción del Forecast",
    "📉 Real vs Forecast",
    "🗺️ MDI — Mapa de Inventario",
    "📦 Necesidades de Compra",
    "⚙️ Versiones",
]


def mostrar_modulo_forecast() -> None:
    st.subheader("Forecast — Centro de Planeación Comercial")

    _panel_soporte_seleccionar_usuario()

    # st.pills (a diferencia de st.tabs) informa cuál sección está activa, así
    # que solo se ejecuta el código de esa sección — st.tabs corre las 6 en
    # cada rerun (aunque no se vean), lo que volvía lento cualquier clic en
    # cualquier parte del módulo (ej. el AgGrid de Construcción se
    # reconstruye siempre, aunque estés viendo el MDI).
    seccion = st.pills(
        "navegación", _SECCIONES_FORECAST, default=_SECCIONES_FORECAST[0],
        key="fc_nav_sel", label_visibility="collapsed",
    ) or st.session_state.get("fc_nav_sel", _SECCIONES_FORECAST[0])

    if seccion == "⚙️ Versiones":
        mostrar_tab_versiones()
        return

    # para las demás secciones necesitamos una versión seleccionada
    version = _selector_version()

    if version is None:
        st.info("crea una versión de forecast en la sección ⚙️ Versiones para comenzar")
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

    if seccion == "📊 Dashboard":
        mostrar_tab_dashboard(id_version=id_version, anio=anio)

    elif seccion == "📈 Construcción del Forecast":
        mostrar_tab_construccion(
            id_version=id_version,
            id_carga_pv=id_carga_pv,
            anio=anio,
            metodo_default=metodo_def,
            usuario_datos_id=usuario_datos_id,
        )

    elif seccion == "📉 Real vs Forecast":
        mostrar_tab_real_vs_forecast(
            id_version=id_version, anio=anio, meses=meses_sel, usuario_datos_id=usuario_datos_id,
        )

    elif seccion == "🗺️ MDI — Mapa de Inventario":
        mostrar_tab_mdi(
            id_version=id_version, anio=anio, meses=meses_sel, usuario_datos_id=usuario_datos_id,
        )

    elif seccion == "📦 Necesidades de Compra":
        mostrar_tab_compras(
            id_version=id_version, anio=anio, meses=meses_sel, usuario_datos_id=usuario_datos_id,
        )
