from datetime import date
import streamlit as st

from controllers.compras_solicitudes_controller import crear_solicitud_producto_ctrl


def _init_form_producto_state():
    if "scp_fecha_solicitud" not in st.session_state:
        st.session_state.scp_fecha_solicitud = date.today()

    if "scp_solicitante" not in st.session_state:
        st.session_state.scp_solicitante = ""

    if "scp_observaciones_generales" not in st.session_state:
        st.session_state.scp_observaciones_generales = ""

    if "scp_cliente" not in st.session_state:
        st.session_state.scp_cliente = ""

    if "scp_numero_pedido" not in st.session_state:
        st.session_state.scp_numero_pedido = ""

    if "scp_persona_solicita" not in st.session_state:
        st.session_state.scp_persona_solicita = ""

    if "scp_producto" not in st.session_state:
        st.session_state.scp_producto = ""

    if "scp_cantidad" not in st.session_state:
        st.session_state.scp_cantidad = ""

    if "scp_fecha_entrega" not in st.session_state:
        st.session_state.scp_fecha_entrega = ""

    if "scp_direccion_entrega" not in st.session_state:
        st.session_state.scp_direccion_entrega = ""

    if "scp_observaciones" not in st.session_state:
        st.session_state.scp_observaciones = ""

    if "scp_limpiar_pendiente" not in st.session_state:
        st.session_state.scp_limpiar_pendiente = False


def _solicitar_limpieza_form_producto():
    st.session_state.scp_limpiar_pendiente = True


def _aplicar_limpieza_form_producto():
    if not st.session_state.get("scp_limpiar_pendiente", False):
        return

    st.session_state.scp_fecha_solicitud = date.today()
    st.session_state.scp_solicitante = ""
    st.session_state.scp_observaciones_generales = ""
    st.session_state.scp_cliente = ""
    st.session_state.scp_numero_pedido = ""
    st.session_state.scp_persona_solicita = ""
    st.session_state.scp_producto = ""
    st.session_state.scp_cantidad = ""
    st.session_state.scp_fecha_entrega = ""
    st.session_state.scp_direccion_entrega = ""
    st.session_state.scp_observaciones = ""
    st.session_state.scp_limpiar_pendiente = False


def mostrar_formulario_compra_producto(id_tipo_compra: int):
    _init_form_producto_state()
    _aplicar_limpieza_form_producto()

    st.markdown("### formato de pedidos - producto")

    c1, c2 = st.columns([2, 1])

    with c1:
        st.text_input(
            "cliente",
            key="scp_cliente",
            placeholder="cliente"
        )

    with c2:
        st.date_input(
            "fecha",
            key="scp_fecha_solicitud",
            format="DD/MM/YYYY"
        )

    c3, c4 = st.columns(2)

    with c3:
        st.text_input(
            "número pedido",
            key="scp_numero_pedido",
            placeholder="ej. r77971"
        )

    with c4:
        st.text_input(
            "persona que solicita",
            key="scp_persona_solicita",
            placeholder="nombre"
        )

    st.text_input(
        "producto",
        key="scp_producto",
        placeholder="ej. soft g-100"
    )

    st.text_input(
        "cantidad",
        key="scp_cantidad",
        placeholder="ej. 200 kilos (10 cajas)"
    )

    st.text_input(
        "fecha de entrega",
        key="scp_fecha_entrega",
        placeholder="ej. embarcar el 07/04/2026"
    )

    st.text_area(
        "dirección de entrega",
        key="scp_direccion_entrega",
        height=120
    )

    st.text_area(
        "observaciones del pedido",
        key="scp_observaciones",
        height=100
    )

    st.text_input(
        "solicitante interno",
        key="scp_solicitante",
        placeholder="usuario o nombre del solicitante"
    )

    st.text_area(
        "observaciones generales",
        key="scp_observaciones_generales",
        height=80
    )

    a1, a2 = st.columns(2)

    with a1:
        if st.button("guardar solicitud producto", use_container_width=True):
            ok, mensaje = crear_solicitud_producto_ctrl(
                id_tipo_compra=id_tipo_compra,
                fecha_solicitud=st.session_state.scp_fecha_solicitud,
                solicitante=st.session_state.scp_solicitante,
                observaciones_generales=st.session_state.scp_observaciones_generales,
                cliente=st.session_state.scp_cliente,
                numero_pedido=st.session_state.scp_numero_pedido,
                persona_solicita=st.session_state.scp_persona_solicita,
                producto=st.session_state.scp_producto,
                cantidad=st.session_state.scp_cantidad,
                fecha_entrega=st.session_state.scp_fecha_entrega,
                direccion_entrega=st.session_state.scp_direccion_entrega,
                observaciones=st.session_state.scp_observaciones,
            )

            if ok:
                st.success(mensaje)
                _solicitar_limpieza_form_producto()
                st.rerun()
            else:
                st.error(mensaje)

    with a2:
        if st.button("limpiar formulario producto", use_container_width=True):
            _solicitar_limpieza_form_producto()
            st.rerun()
            