from models.compras_solicitudes_dinamico_model import (
    guardar_valores_cabecera_model,
    obtener_valores_cabecera_model,
    crear_renglon_detalle_model,
    obtener_detalle_dinamico_model,
)
from models.compras_solicitudes_model import crear_solicitud_cabecera_model
from controllers.compras_tipos_campos_controller import obtener_campos_tipo_ctrl


def crear_solicitud_dinamica_ctrl(
    *, id_tipo_compra: int, fecha_solicitud, solicitante: str,
    observaciones_generales: str, valores_cabecera: dict, renglones: list[dict],
) -> tuple[bool, str]:
    solicitante = (solicitante or "").strip()
    if not solicitante:
        return False, "falta el solicitante interno."
    if not fecha_solicitud:
        return False, "falta la fecha de solicitud."

    campos_cab = obtener_campos_tipo_ctrl(id_tipo_compra, "cabecera")
    for campo in campos_cab:
        if campo["requerido"] and not str(valores_cabecera.get(campo["clave_campo"]) or "").strip():
            return False, f"falta capturar el campo obligatorio \"{campo['nombre_campo']}\"."

    campos_det = obtener_campos_tipo_ctrl(id_tipo_compra, "detalle")
    renglones_validos = [r for r in renglones if any(str(v or "").strip() for v in r.values())]
    if campos_det and not renglones_validos:
        return False, "agrega al menos un renglón de detalle."
    for r in renglones_validos:
        for campo in campos_det:
            if campo["requerido"] and not str(r.get(campo["clave_campo"]) or "").strip():
                return False, f"falta capturar el campo obligatorio \"{campo['nombre_campo']}\" en algún renglón."

    id_solicitud_compra = crear_solicitud_cabecera_model(
        id_tipo_compra=id_tipo_compra, fecha_solicitud=fecha_solicitud,
        solicitante=solicitante, observaciones_generales=observaciones_generales,
    )
    if not id_solicitud_compra:
        return False, "no se pudo crear la cabecera."

    guardar_valores_cabecera_model(
        id_solicitud_compra, {k: str(v) for k, v in valores_cabecera.items() if str(v or "").strip()}
    )
    for i, r in enumerate(renglones_validos, start=1):
        crear_renglon_detalle_model(
            id_solicitud_compra, i, {k: str(v) for k, v in r.items() if str(v or "").strip()}
        )

    return True, f"solicitud creada correctamente folio #{id_solicitud_compra}"


def obtener_valores_cabecera_ctrl(id_solicitud_compra: int) -> dict:
    return obtener_valores_cabecera_model(id_solicitud_compra)


def obtener_detalle_dinamico_ctrl(id_solicitud_compra: int):
    return obtener_detalle_dinamico_model(id_solicitud_compra)
