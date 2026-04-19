import streamlit as st

from controllers.compras_solicitudes_controller import (
    obtener_solicitudes_pendientes_usuario_ctrl,
    obtener_detalle_solicitud_compra_ctrl,
    obtener_cabecera_solicitud_compra_ctrl,
    obtener_cabecera_solicitud_estandar_ctrl,
    obtener_detalle_solicitud_estandar_ctrl,
    enviar_solicitud_compra_ctrl,
    eliminar_solicitud_compra_ctrl,
)


def _get_usuario_actual():
    return st.session_state.get("usuario") or {}


def _get_solicitante_actual() -> str:
    usuario = _get_usuario_actual()
    return (
        str(usuario.get("nombre") or "").strip()
        or str(usuario.get("username") or "").strip()
        or str(usuario.get("email") or "").strip()
        or ""
    )


def _mostrar_detalle_materias_primas(id_solicitud: int):
    detalle = obtener_detalle_solicitud_compra_ctrl(id_solicitud)

    if detalle.empty:
        st.info("esta solicitud no tiene detalle.")
        return

    cols_det = [
        "cliente",
        "cliente_sae",
        "numero_pedido",
        "persona_solicita",
        "producto",
        "producto_sae",
        "cantidad",
        "unidad_empaque",
        "fecha_entrega",
        "direccion_entrega",
        "observaciones",
    ]
    cols_det = [c for c in cols_det if c in detalle.columns]

    st.dataframe(
        detalle[cols_det],
        use_container_width=True,
        hide_index=True,
    )

def _mostrar_detalle_estandar(id_solicitud: int):
    cab_est = obtener_cabecera_solicitud_estandar_ctrl(id_solicitud)

    if not cab_est:
        st.info("esta solicitud no tiene cabecera estándar.")
        return

    st.markdown("#### detalle del formato estándar")

    c1, c2, c3 = st.columns(3)

    with c1:
        st.text_input("folio", value=str(cab_est.get("folio") or ""), disabled=True)
        st.text_input("departamento", value=str(cab_est.get("departamento") or ""), disabled=True)

    with c2:
        st.text_input("fecha elaboración", value=str(cab_est.get("fecha_elaboracion") or ""), disabled=True)
        st.text_input("forma de pago", value=str(cab_est.get("forma_pago") or ""), disabled=True)

    with c3:
        st.text_area(
            "observaciones",
            value=str(cab_est.get("observaciones") or ""),
            disabled=True,
            height=100,
        )

    detalle = obtener_detalle_solicitud_estandar_ctrl(id_solicitud)

    if detalle.empty:
        st.info("esta solicitud no tiene detalle estándar.")
        return

    cols_det = [
        "cantidad",
        "descripcion_producto_servicio",
        "unidad_negocio_sigla",
        "porcentaje",
        "fecha_requerida",
        "proveedor",
        "precio_unitario",
        "costo_total_sin_iva",
    ]
    cols_det = [c for c in cols_det if c in detalle.columns]

    st.dataframe(
        detalle[cols_det],
        use_container_width=True,
        hide_index=True,
    )



def mostrar_tab_solicitudes_pendientes():
    st.subheader("mis solicitudes pendientes")

    solicitante_actual = _get_solicitante_actual()

    if not solicitante_actual:
        st.warning("no se pudo identificar el usuario actual.")
        return

    df = obtener_solicitudes_pendientes_usuario_ctrl(solicitante_actual)

    if df.empty:
        st.info("no tienes solicitudes pendientes.")
        return

    cols_show = [
        "id_solicitud_compra",
        "fecha_solicitud",
        "tipo_compra",
        "estatus",
        "total_renglones",
        "observaciones_generales",
        "created_at",
    ]
    cols_show = [c for c in cols_show if c in df.columns]

    st.dataframe(
        df[cols_show],
        use_container_width=True,
        hide_index=True,
    )

    st.divider()
    st.markdown("### detalle de solicitud")

    opciones = {
        f'{int(row["id_solicitud_compra"])} - {str(row["tipo_compra"] or "").strip()} - {str(row["estatus"] or "").strip()}': int(row["id_solicitud_compra"])
        for _, row in df.iterrows()
    }

    seleccion = st.selectbox(
        "selecciona una solicitud",
        options=list(opciones.keys()),
        key="scp_pendientes_sel",
    )

    id_solicitud = opciones[seleccion]

    cab = obtener_cabecera_solicitud_compra_ctrl(id_solicitud)
    estatus_actual = str(cab.get("estatus") or "").strip().lower()
    tipo_compra = str(cab.get("tipo_compra") or "").strip()

    c1, c2, c3, c4 = st.columns([2, 2, 2, 4])

    with c1:
        if st.button(
            "enviar solicitud",
            use_container_width=True,
            disabled=(estatus_actual != "captura"),
            key=f"btn_enviar_sol_compra_{id_solicitud}",
        ):
            token = st.session_state.get("microsoft_token")
            ok, mensaje = enviar_solicitud_compra_ctrl(id_solicitud, token=token)

            if ok:
                st.success(mensaje)
                st.rerun()
            else:
                st.error(mensaje)

    with c2:
        if st.button(
            "eliminar solicitud",
            use_container_width=True,
            disabled=(estatus_actual != "captura"),
            key=f"btn_eliminar_sol_compra_{id_solicitud}",
        ):
            ok, mensaje = eliminar_solicitud_compra_ctrl(id_solicitud)

            if ok:
                st.success(mensaje)
                st.rerun()
            else:
                st.error(mensaje)

    with c3:
        st.caption(f"estatus actual: {cab.get('estatus', '')}")

    st.markdown("#### cabecera general")
    g1, g2, g3 = st.columns(3)

    with g1:
        st.text_input("id solicitud", value=str(cab.get("id_solicitud_compra") or ""), disabled=True)
        st.text_input("tipo de compra", value=str(cab.get("tipo_compra") or ""), disabled=True)

    with g2:
        st.text_input("fecha solicitud", value=str(cab.get("fecha_solicitud") or ""), disabled=True)
        st.text_input("solicitante", value=str(cab.get("solicitante") or ""), disabled=True)

    with g3:
        st.text_input("estatus", value=str(cab.get("estatus") or ""), disabled=True)
        st.text_area(
            "observaciones generales",
            value=str(cab.get("observaciones_generales") or ""),
            disabled=True,
            height=90,
        )

    st.divider()

    if tipo_compra == "Materias Primas":
        st.markdown("#### detalle de materias primas")
        _mostrar_detalle_materias_primas(id_solicitud)
    else:
        _mostrar_detalle_estandar(id_solicitud)