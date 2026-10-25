import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, DataReturnMode, GridOptionsBuilder, JsCode

from controllers.compras_solicitudes_controller import (
    obtener_solicitudes_pendientes_usuario_ctrl,
    obtener_cabecera_solicitud_compra_ctrl,
    obtener_tipo_compra_mp_inventario_ctrl,
    obtener_receptores_asignados_ctrl,
    autorizar_solicitud_compra_ctrl,
    rechazar_solicitud_compra_ctrl,
    obtener_lineas_mp_inventario_pendientes_autorizar_ctrl,
    autorizar_lineas_mp_inventario_ctrl,
    rechazar_lineas_mp_inventario_ctrl,
    obtener_ids_solicitudes_con_lineas_sin_generar_ctrl,
)
from views.modulo_compras.tab_solicitudes_pendientes_view import (
    _mostrar_detalle_mp_inventario,
    _mostrar_detalle_materias_primas,
    _mostrar_detalle_estandar,
    _mostrar_detalle_dinamico,
    _mostrar_accion_generar_sae,
)

_VALUE_FORMATTER_USD_JS = JsCode("""
function(params) {
    if (params.value === null || params.value === undefined || params.value === '') return '';
    return '$' + Number(params.value).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
}
""")


def _get_usuario_actual():
    return st.session_state.get("usuario") or {}


def _get_nombre_actual() -> str:
    usuario = _get_usuario_actual()
    return (
        str(usuario.get("nombre") or "").strip()
        or str(usuario.get("username") or "").strip()
        or str(usuario.get("email") or "").strip()
        or ""
    )


def _mostrar_detalle_por_tipo(id_solicitud: int, cab: dict, editable: bool = False):
    tipo_formulario = str(cab.get("tipo_formulario") or "").strip().upper()
    if tipo_formulario == "MP":
        _mostrar_detalle_materias_primas(id_solicitud)
    elif tipo_formulario == "MP_INV":
        _mostrar_detalle_mp_inventario(id_solicitud, editable=editable)
    elif tipo_formulario == "DINAMICO":
        _mostrar_detalle_dinamico(id_solicitud)
    else:
        _mostrar_detalle_estandar(id_solicitud)


def _mostrar_lineas_mp_inventario_pendientes(usuario_id, es_superadmin: bool):
    """Materia Prima (Inventario) se envía línea por línea (ver Pendientes),
    así que su cola de autorización también es por línea, no por toda la
    solicitud — una misma solicitud puede tener algunas líneas ya resueltas
    y otras todavía aquí."""
    df = obtener_lineas_mp_inventario_pendientes_autorizar_ctrl(usuario_id=usuario_id, ver_todas=es_superadmin)
    if df.empty:
        st.info("no hay líneas de materia prima (inventario) pendientes de autorizar.")
        return

    df = df.copy()
    df["costo_usd"] = (
        pd.to_numeric(df["cantidad_kg"], errors="coerce").fillna(0.0)
        * pd.to_numeric(df["precio_usd"], errors="coerce").fillna(0.0)
    ).round(2)

    df_show = df[[
        "id_solicitud_compra", "solicitante", "fecha_solicitud",
        "cve_mp", "mp_nombre", "linea", "cantidad_kg", "precio_usd", "costo_usd", "motivo_autorizacion",
        "id_detalle_mp_inv",
    ]].rename(columns={
        "id_solicitud_compra": "solicitud", "mp_nombre": "materia prima", "linea": "línea",
        "cantidad_kg": "cantidad (kg)", "precio_usd": "precio USD", "costo_usd": "costo USD",
        "motivo_autorizacion": "motivo",
    })

    gb = GridOptionsBuilder.from_dataframe(df_show)
    gb.configure_grid_options(autoSizeStrategy=None)
    gb.configure_default_column(editable=False, resizable=True, filter=True, sortable=True)
    # el checkbox se pega a la PRIMERA columna del dataframe — por eso
    # "solicitud" va primero y "id_detalle_mp_inv" (oculto, solo para
    # identificar qué se marcó) va al final, nunca al inicio.
    gb.configure_selection(selection_mode="multiple", use_checkbox=True, header_checkbox=True)
    gb.configure_column("solicitud", pinned="left", width=100)
    gb.configure_column("solicitante", pinned="left", width=150)
    gb.configure_column("id_detalle_mp_inv", hide=True)
    gb.configure_column("precio USD", valueFormatter=_VALUE_FORMATTER_USD_JS, width=110)
    gb.configure_column("costo USD", valueFormatter=_VALUE_FORMATTER_USD_JS, width=130)
    gb.configure_column("motivo", width=320, wrapText=True, autoHeight=True)

    grid_resp = AgGrid(
        df_show,
        gridOptions=gb.build(),
        data_return_mode=DataReturnMode.AS_INPUT,
        fit_columns_on_grid_load=False,
        allow_unsafe_jscode=True,
        enable_enterprise_modules=True,
        height=min(56 + len(df_show) * 35, 400),
        key="aut_mp_inv_lineas_grid",
    )

    seleccionadas = grid_resp.get("selected_rows")
    ids_marcados = (
        [int(i) for i in seleccionadas["id_detalle_mp_inv"].tolist()]
        if isinstance(seleccionadas, pd.DataFrame) else []
    )

    motivo = st.text_input("motivo (solo si vas a rechazar)", key="aut_mp_inv_lineas_motivo")
    c1, c2 = st.columns(2)
    with c1:
        if st.button(
            "✅ autorizar seleccionadas", type="primary", use_container_width=True,
            disabled=not ids_marcados, key="aut_mp_inv_lineas_btn_aprobar",
        ):
            ok, mensaje = autorizar_lineas_mp_inventario_ctrl(ids_marcados, _get_nombre_actual())
            if ok:
                st.success(mensaje)
                st.rerun()
            else:
                st.error(mensaje)
    with c2:
        if st.button(
            "❌ rechazar seleccionadas", use_container_width=True,
            disabled=not ids_marcados, key="aut_mp_inv_lineas_btn_rechazar",
        ):
            ok, mensaje = rechazar_lineas_mp_inventario_ctrl(ids_marcados, _get_nombre_actual(), motivo)
            if ok:
                st.success(mensaje)
                st.rerun()
            else:
                st.error(mensaje)


def mostrar_tab_autorizaciones_compras():
    """Autorización de Solicitudes de Compra — visible para
    SuperAdmin/forecastAdmin (ven todas, como respaldo) y para cualquier
    usuario que una regla de autorización (Compras -> Reglas de
    Autorización) haya dejado como receptor asignado. Si ninguna regla
    aplicó al enviar, se conserva el destino de siempre (SuperAdmin/
    forecastAdmin para Materia Prima (Inventario), Compras MP/Compras Admin
    por correo para los demás)."""
    usuario = _get_usuario_actual()
    roles = usuario.get("roles", [])
    usuario_id = usuario.get("id")
    es_superadmin = "SuperAdmin" in roles or "forecastAdmin" in roles

    st.subheader("autorizaciones — solicitudes de compra")

    tipo_mp_inv = obtener_tipo_compra_mp_inventario_ctrl()
    nombre_tipo_mp_inv = str((tipo_mp_inv or {}).get("nombre") or "").strip()

    st.markdown("### materia prima (inventario) — líneas pendientes de autorizar")
    _mostrar_lineas_mp_inventario_pendientes(usuario_id, es_superadmin)

    st.divider()
    st.markdown("### otras solicitudes de compra pendientes de autorizar")

    df = obtener_solicitudes_pendientes_usuario_ctrl("", ver_todas=True)
    if df.empty:
        st.info("no hay solicitudes pendientes de autorizar.")
    else:
        # Materia Prima (Inventario) se autoriza arriba, por línea — su
        # cabecera puede marcar 'enviada' sin que quede nada por revisar
        # aquí (si todas sus líneas ya se autorizaron solas).
        df_enviadas = df[
            (df["estatus"].astype(str).str.strip().str.lower() == "enviada")
            & (df["tipo_compra"].astype(str).str.strip() != nombre_tipo_mp_inv)
        ]

        if es_superadmin:
            df_pend = df_enviadas
        else:
            ids_asignados = {
                int(row["id_solicitud_compra"])
                for _, row in df_enviadas.iterrows()
                if usuario_id is not None
                and usuario_id in (obtener_receptores_asignados_ctrl(int(row["id_solicitud_compra"])) or [])
            }
            df_pend = (
                df_enviadas[df_enviadas["id_solicitud_compra"].astype(int).isin(ids_asignados)]
                if ids_asignados else df_enviadas.iloc[0:0]
            )

        if df_pend.empty:
            st.info("no hay solicitudes enviadas a autorización asignadas a ti.")
        else:
            st.dataframe(
                df_pend[[
                    "id_solicitud_compra", "tipo_compra", "fecha_solicitud", "solicitante",
                    "total_renglones", "observaciones_generales", "created_at",
                ]],
                use_container_width=True,
                hide_index=True,
            )

            st.divider()
            opciones = {
                f'{int(row["id_solicitud_compra"])} - {str(row["tipo_compra"] or "").strip()} - '
                f'{str(row["solicitante"] or "").strip()} - {str(row["fecha_solicitud"] or "").strip()}':
                int(row["id_solicitud_compra"])
                for _, row in df_pend.iterrows()
            }
            seleccion = st.selectbox(
                "selecciona una solicitud para revisar", options=list(opciones.keys()),
                key="aut_compras_sel",
            )
            id_solicitud = opciones[seleccion]

            cab = obtener_cabecera_solicitud_compra_ctrl(id_solicitud)
            st.markdown("#### cabecera")
            g1, g2, g3 = st.columns(3)
            with g1:
                st.text_input(
                    "id solicitud", value=str(cab.get("id_solicitud_compra") or ""), disabled=True,
                    key=f"aut_compras_id_{id_solicitud}",
                )
                st.text_input(
                    "solicitante", value=str(cab.get("solicitante") or ""), disabled=True,
                    key=f"aut_compras_solicitante_{id_solicitud}",
                )
            with g2:
                st.text_input(
                    "fecha solicitud", value=str(cab.get("fecha_solicitud") or ""), disabled=True,
                    key=f"aut_compras_fecha_{id_solicitud}",
                )
                st.text_input(
                    "estatus", value=str(cab.get("estatus") or ""), disabled=True,
                    key=f"aut_compras_estatus_{id_solicitud}",
                )
            with g3:
                st.text_area(
                    "observaciones generales",
                    value=str(cab.get("observaciones_generales") or ""), disabled=True, height=90,
                    key=f"aut_compras_obs_{id_solicitud}",
                )

            if cab.get("motivo_autorizacion"):
                st.caption(f"📋 {cab.get('motivo_autorizacion')}")

            st.markdown("#### detalle — a autorizar")
            _mostrar_detalle_por_tipo(id_solicitud, cab)

            st.divider()
            motivo = st.text_input(
                "motivo (solo si vas a rechazar)", key=f"aut_compras_motivo_{id_solicitud}",
            )
            c1, c2 = st.columns(2)
            with c1:
                if st.button(
                    "✅ autorizar", type="primary", use_container_width=True,
                    key=f"aut_compras_btn_aprobar_{id_solicitud}",
                ):
                    ok, mensaje = autorizar_solicitud_compra_ctrl(id_solicitud, _get_nombre_actual())
                    if ok:
                        st.success(mensaje)
                        st.rerun()
                    else:
                        st.error(mensaje)
            with c2:
                if st.button(
                    "❌ rechazar", use_container_width=True,
                    key=f"aut_compras_btn_rechazar_{id_solicitud}",
                ):
                    ok, mensaje = rechazar_solicitud_compra_ctrl(id_solicitud, _get_nombre_actual(), motivo)
                    if ok:
                        st.success(mensaje)
                        st.rerun()
                    else:
                        st.error(mensaje)

    if not es_superadmin:
        return

    st.divider()
    st.markdown("### autorizadas — pendientes de generar en SAE (materia prima/inventario)")
    # por línea, no por solicitud completa: una solicitud puede tener una
    # línea ya autorizada y lista para SAE aunque otras sigan en
    # captura/enviada — no depende del estatus de la cabecera.
    ids_con_pendientes = obtener_ids_solicitudes_con_lineas_sin_generar_ctrl()
    if not ids_con_pendientes:
        st.caption("no hay líneas autorizadas pendientes de generar en SAE.")
        return

    df_todas = obtener_solicitudes_pendientes_usuario_ctrl("", ver_todas=True)
    df_autorizadas = df_todas[
        df_todas["id_solicitud_compra"].astype(int).isin(ids_con_pendientes)
    ]
    if df_autorizadas.empty:
        st.caption("no hay líneas autorizadas pendientes de generar en SAE.")
        return

    opciones_aut = {
        f'{int(row["id_solicitud_compra"])} - {str(row["solicitante"] or "").strip()} '
        f'- {str(row["fecha_solicitud"] or "").strip()}': int(row["id_solicitud_compra"])
        for _, row in df_autorizadas.iterrows()
    }
    seleccion_aut = st.selectbox(
        "selecciona una solicitud autorizada", options=list(opciones_aut.keys()),
        key="aut_compras_sel_generada",
    )
    id_solicitud_aut = opciones_aut[seleccion_aut]
    cab_aut = obtener_cabecera_solicitud_compra_ctrl(id_solicitud_aut)
    _mostrar_detalle_mp_inventario(id_solicitud_aut)
    _mostrar_accion_generar_sae(cab_aut)
