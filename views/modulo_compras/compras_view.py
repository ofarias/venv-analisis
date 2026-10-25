import streamlit as st

from views.modulo_compras.tab_catalogos_unificados_view import mostrar_tab_catalogos_unificados
from views.modulo_compras.tab_solicitudes_compras_view import mostrar_tab_solicitudes_compras
from views.modulo_compras.tab_solicitudes_pendientes_view import mostrar_tab_solicitudes_pendientes
from views.modulo_compras.tab_demanda_forecast_view import mostrar_tab_demanda_forecast
from views.modulo_compras.tab_autorizaciones_compras_view import mostrar_tab_autorizaciones_compras
from views.modulo_compras.tab_reglas_autorizacion_view import mostrar_tab_reglas_autorizacion
from views.modulo_compras.tab_campos_dinamicos_view import mostrar_tab_campos_dinamicos
from controllers.compras_solicitudes_controller import usuario_tiene_solicitudes_asignadas_ctrl


def mostrar_modulo_compras():
    st.title("módulo de compras")

    usuario = st.session_state.get("usuario") or {}
    roles = [str(r).strip().lower() for r in (usuario.get("roles", []) or [])]

    es_admin_compras = (
        "admin" in roles
        or "superadmin" in roles
        or "compras" in roles
    )
    # formularios dinámicos: solo rol Admin, como se pidió explícitamente
    # (es_admin_compras es más amplio — también admite "compras"/"superadmin"
    # — y aquí no aplica).
    es_admin_rol = "admin" in roles
    # SuperAdmin/forecastAdmin siempre autorizan (respaldo); además, si una
    # regla de autorización (Compras -> Reglas de Autorización) dejó a este
    # usuario como receptor asignado de alguna solicitud enviada, también ve
    # la pestaña aunque no tenga esos roles.
    es_autorizador_compras = (
        "superadmin" in roles or "forecastadmin" in roles
        or usuario_tiene_solicitudes_asignadas_ctrl(usuario.get("id"))
    )

    secciones = []
    if es_admin_compras:
        secciones.append("Catálogos")
    secciones += ["Solicitudes", "Pendientes"]
    if es_admin_compras:
        secciones.append("📦 Demanda (Forecast)")
    if es_autorizador_compras:
        secciones.append("✅ Autorizaciones")
    if es_admin_compras:
        secciones.append("⚙️ Reglas de Autorización")
    if es_admin_rol:
        secciones.append("🧩 Formularios Dinámicos")

    # st.pills (a diferencia de st.tabs) informa cuál sección está activa,
    # así que solo se ejecuta el código de esa sección — st.tabs corre todas
    # en cada rerun (aunque no se vean), lo que además causó el choque de
    # IDs duplicados entre Pendientes y Autorizaciones (mismo text_input
    # renderizado dos veces con el mismo valor en el mismo run). Mismo
    # criterio que ya usa el módulo Forecast (views/modulo_forecast/forecast_view.py).
    seccion = st.pills(
        "navegación", secciones, default=secciones[0],
        key="compras_nav_sel", label_visibility="collapsed",
    ) or st.session_state.get("compras_nav_sel", secciones[0])

    if seccion == "Catálogos":
        mostrar_tab_catalogos_unificados()
    elif seccion == "Solicitudes":
        mostrar_tab_solicitudes_compras()
    elif seccion == "Pendientes":
        mostrar_tab_solicitudes_pendientes()
    elif seccion == "📦 Demanda (Forecast)":
        mostrar_tab_demanda_forecast()
    elif seccion == "✅ Autorizaciones":
        mostrar_tab_autorizaciones_compras()
    elif seccion == "⚙️ Reglas de Autorización":
        mostrar_tab_reglas_autorizacion()
    elif seccion == "🧩 Formularios Dinámicos":
        mostrar_tab_campos_dinamicos()
