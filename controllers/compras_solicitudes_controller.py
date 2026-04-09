from models.compras_solicitudes_model import (
    get_tipos_compra_activos_model,
    crear_solicitud_compra_cabecera_model,
    existe_numero_pedido_producto_model,
    crear_solicitud_producto_model,
    get_solicitudes_compra_model,
)


def obtener_tipos_compra_activos_ctrl():
    return get_tipos_compra_activos_model()


def obtener_solicitudes_compra_ctrl():
    return get_solicitudes_compra_model()


def crear_solicitud_producto_ctrl(
    id_tipo_compra,
    fecha_solicitud,
    solicitante,
    observaciones_generales,
    cliente,
    numero_pedido,
    persona_solicita,
    producto,
    cantidad,
    fecha_entrega,
    direccion_entrega,
    observaciones,
):
    solicitante = (solicitante or "").strip()
    observaciones_generales = (observaciones_generales or "").strip()
    cliente = (cliente or "").strip()
    numero_pedido = (numero_pedido or "").strip()
    persona_solicita = (persona_solicita or "").strip()
    producto = (producto or "").strip()
    cantidad = (cantidad or "").strip()
    fecha_entrega = (fecha_entrega or "").strip()
    direccion_entrega = (direccion_entrega or "").strip()
    observaciones = (observaciones or "").strip()

    if not id_tipo_compra:
        return False, "debes seleccionar el tipo de compra."

    if not fecha_solicitud:
        return False, "debes capturar la fecha de solicitud."

    if not solicitante:
        return False, "debes capturar el solicitante."

    if not cliente:
        return False, "debes capturar el cliente."

    if not numero_pedido:
        return False, "debes capturar el número de pedido."

    if not persona_solicita:
        return False, "debes capturar la persona que solicita."

    if not producto:
        return False, "debes capturar el producto."

    if not cantidad:
        return False, "debes capturar la cantidad."

    if existe_numero_pedido_producto_model(numero_pedido):
        return False, "ya existe una solicitud con ese número de pedido."

    id_solicitud_compra = crear_solicitud_compra_cabecera_model(
        id_tipo_compra=id_tipo_compra,
        fecha_solicitud=fecha_solicitud,
        solicitante=solicitante,
        observaciones_generales=observaciones_generales,
        estatus="captura",
        activo=1,
    )

    crear_solicitud_producto_model(
        id_solicitud_compra=id_solicitud_compra,
        cliente=cliente,
        numero_pedido=numero_pedido,
        persona_solicita=persona_solicita,
        producto=producto,
        cantidad=cantidad,
        fecha_entrega=fecha_entrega,
        direccion_entrega=direccion_entrega,
        observaciones=observaciones,
    )

    return True, f"solicitud creada correctamente. folio interno: {id_solicitud_compra}"