import streamlit as st

from views.modulo_compras.tab_catalogos_unificados_view import mostrar_tab_catalogos_unificados
from views.modulo_compras.tab_solicitudes_compras_view import mostrar_tab_solicitudes_compras
from views.modulo_compras.tab_solicitudes_pendientes_view import mostrar_tab_solicitudes_pendientes
from views.modulo_compras.tab_demanda_forecast_view import mostrar_tab_demanda_forecast
from views.modulo_compras.tab_demanda_presupuesto_view import mostrar_tab_demanda_presupuesto
from views.modulo_compras.tab_autorizaciones_compras_view import mostrar_tab_autorizaciones_compras
from views.modulo_compras.tab_puestos_view import mostrar_tab_puestos
from views.modulo_compras.tab_flujos_compras_view import mostrar_tab_flujos_compras
from views.modulo_compras.tab_campos_dinamicos_view import mostrar_tab_campos_dinamicos
from views.modulo_compras.tab_seguimiento_compras_view import mostrar_tab_seguimiento_compras
from views.modulo_compras.tab_productos_obsoletos_view import mostrar_tab_productos_obsoletos
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

    # Navegación en dos niveles: un grupo grande por etapa del flujo
    # (Solicitar → Autorizar → Analizar/Planear → Configurar, mismo orden
    # que el proceso real) y, dentro de cada grupo, las pantallas puntuales.
    # Un grupo con una sola pantalla se muestra directo, sin una segunda
    # fila de pills innecesaria para una sola opción.
    grupos: dict[str, list[tuple[str, callable]]] = {
        "📝 Mis Solicitudes": [
            ("📝 Nueva Solicitud", mostrar_tab_solicitudes_compras),
            ("📋 Pendientes", mostrar_tab_solicitudes_pendientes),
            ("🟢 Seguimiento", mostrar_tab_seguimiento_compras),
        ],
    }

    if es_autorizador_compras:
        grupos["✅ Autorizar"] = [
            ("✅ Autorizaciones", mostrar_tab_autorizaciones_compras),
        ]

    if es_admin_compras:
        grupos["📊 Demanda y Análisis"] = [
            ("📦 Demanda (Forecast)", mostrar_tab_demanda_forecast),
            ("📦 Demanda (Presupuesto)", mostrar_tab_demanda_presupuesto),
            ("📦 Productos Obsoletos", mostrar_tab_productos_obsoletos),
        ]

    items_config: list[tuple[str, callable]] = []
    if es_admin_compras:
        items_config += [
            ("🗂️ Catálogos", mostrar_tab_catalogos_unificados),
            ("🧑‍💼 Puestos", mostrar_tab_puestos),
            ("⚙️ Flujo de Autorización de Gastos", mostrar_tab_flujos_compras),
        ]
    if es_admin_rol:
        items_config.append(("🧩 Formularios Dinámicos", mostrar_tab_campos_dinamicos))
    if items_config:
        grupos["⚙️ Configuración"] = items_config

    grupos_labels = list(grupos.keys())

    # st.pills (a diferencia de st.tabs) informa cuál sección está activa,
    # así que solo se ejecuta el código de esa sección — st.tabs corre todas
    # en cada rerun (aunque no se vean), lo que además causó el choque de
    # IDs duplicados entre Pendientes y Autorizaciones (mismo text_input
    # renderizado dos veces con el mismo valor en el mismo run). Mismo
    # criterio que ya usa el módulo Forecast (views/modulo_forecast/forecast_view.py).
    grupo_sel = st.pills(
        "grupo", grupos_labels, default=grupos_labels[0],
        key="compras_nav_grupo", label_visibility="collapsed",
    ) or st.session_state.get("compras_nav_grupo", grupos_labels[0])

    # si el grupo cambió, la sub-selección guardada ya no corresponde a
    # este grupo (puede ni existir entre sus opciones) — se limpia para
    # que la segunda fila de pills arranque en la primera opción del
    # grupo nuevo en vez de quedar "sin nada marcado".
    if st.session_state.get("_compras_nav_grupo_anterior") != grupo_sel:
        st.session_state.pop("compras_nav_item", None)
        st.session_state["_compras_nav_grupo_anterior"] = grupo_sel

    items = grupos[grupo_sel]
    if len(items) == 1:
        items[0][1]()
        return

    item_labels = [lbl for lbl, _ in items]
    item_sel = st.pills(
        "pantalla", item_labels, default=item_labels[0],
        key="compras_nav_item", label_visibility="collapsed",
    ) or st.session_state.get("compras_nav_item", item_labels[0])

    dict(items)[item_sel]()
