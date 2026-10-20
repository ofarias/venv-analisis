import streamlit as st

from controllers.compras_solicitudes_controller import (
    obtener_solicitudes_pendientes_usuario_ctrl,
    obtener_cabecera_solicitud_compra_ctrl,
    obtener_tipo_compra_mp_inventario_ctrl,
    autorizar_solicitud_compra_ctrl,
    rechazar_solicitud_compra_ctrl,
)
from views.modulo_compras.tab_solicitudes_pendientes_view import (
    _mostrar_detalle_mp_inventario,
    _mostrar_accion_generar_sae,
)


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


def mostrar_tab_autorizaciones_compras():
    """Autorización de Solicitudes de Compra tipo Materia Prima (Inventario)
    — único tipo con circuito de autorización hoy (ver plan); los demás
    tipos (MP/STD) siguen solo con el aviso por correo de "enviar
    solicitud", sin este paso. Gate: SuperAdmin/forecastAdmin."""
    usuario = _get_usuario_actual()
    roles = usuario.get("roles", [])
    if not ("SuperAdmin" in roles or "forecastAdmin" in roles):
        st.warning("no tienes permiso para autorizar solicitudes de compra.")
        return

    st.subheader("autorizaciones — materia prima (inventario)")

    tipo_mp_inv = obtener_tipo_compra_mp_inventario_ctrl()
    if not tipo_mp_inv:
        st.error("no existe el tipo de compra 'Materia Prima (Inventario)' activo.")
        return
    nombre_tipo_mp_inv = str(tipo_mp_inv.get("nombre") or "").strip()

    df = obtener_solicitudes_pendientes_usuario_ctrl("", ver_todas=True)
    if df.empty:
        st.info("no hay solicitudes pendientes de autorizar.")
        return

    df_pend = df[
        (df["tipo_compra"].astype(str).str.strip() == nombre_tipo_mp_inv)
        & (df["estatus"].astype(str).str.strip().str.lower() == "enviada")
    ]

    st.markdown("### pendientes de autorizar")
    if df_pend.empty:
        st.info("no hay solicitudes de materia prima (inventario) enviadas a autorización.")
    else:
        st.dataframe(
            df_pend[[
                "id_solicitud_compra", "fecha_solicitud", "solicitante",
                "total_renglones", "observaciones_generales", "created_at",
            ]],
            use_container_width=True,
            hide_index=True,
        )

        st.divider()
        opciones = {
            f'{int(row["id_solicitud_compra"])} - {str(row["solicitante"] or "").strip()} '
            f'- {str(row["fecha_solicitud"] or "").strip()}': int(row["id_solicitud_compra"])
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

        st.markdown("#### detalle — necesidad de materia prima a autorizar")
        _mostrar_detalle_mp_inventario(id_solicitud)

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

    st.divider()
    st.markdown("### autorizadas — pendientes de generar en SAE")
    df_autorizadas = df[
        (df["tipo_compra"].astype(str).str.strip() == nombre_tipo_mp_inv)
        & (df["estatus"].astype(str).str.strip().str.lower() == "autorizada")
    ]
    if df_autorizadas.empty:
        st.caption("no hay solicitudes autorizadas pendientes de generar en SAE.")
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
