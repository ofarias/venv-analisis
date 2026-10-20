import streamlit as st
from models.compras_solicitudes_model import (
    crear_solicitud_cabecera_model,
    crear_detalle_productos_model,
    get_unidades_empaque_model,
    get_tipos_compra_activos_model,
    get_solicitudes_pendientes_usuario_model,
    get_detalle_solicitud_compra_model,
    cambiar_estatus_solicitud_compra_model,
    get_correos_roles_compras_model,
    get_cabecera_solicitud_compra_model,
    eliminar_solicitud_compra_model,
    get_departamentos_compra_model,
    get_formas_pago_compra_model,
    get_unidades_negocio_compra_model,
    crear_solicitud_estandar_cabecera_model,
    crear_solicitud_estandar_detalle_model,
    get_cabecera_solicitud_estandar_model,
    get_detalle_solicitud_estandar_model,
    crear_solicitud_mp_inventario_detalle_model,
    get_detalle_solicitud_mp_inventario_model,
    obtener_mp_solicitadas_sae_model,
)

from models.sae45_model import buscar_producto_sae

from utils.envio_correo import enviar_correo
from controllers.solicitudes_controller import get_correos_usuarios_por_rol_ctrl

def obtener_tipos_compra_activos_ctrl():
    return get_tipos_compra_activos_model()


def get_unidades_empaque_ctrl():
    return get_unidades_empaque_model()


def crear_solicitud_producto_ctrl(
    *,
    id_tipo_compra: int,
    fecha_solicitud,
    solicitante: str,
    observaciones_generales: str,
    detalle: list
):
    try:
        solicitante = (solicitante or "").strip()
        observaciones_generales = (observaciones_generales or "").strip()

        if not id_tipo_compra:
            return False, "falta el tipo de compra"

        if not fecha_solicitud:
            return False, "falta la fecha de solicitud"

        if not solicitante:
            return False, "falta el solicitante interno"

        if not detalle:
            return False, "no hay productos para guardar"

        id_solicitud = crear_solicitud_cabecera_model(
            id_tipo_compra=id_tipo_compra,
            fecha_solicitud=fecha_solicitud,
            solicitante=solicitante,
            observaciones_generales=observaciones_generales
        )

        if not id_solicitud:
            return False, "no se pudo crear la cabecera"

        ok = crear_detalle_productos_model(
            id_solicitud=id_solicitud,
            detalle=detalle
        )

        if not ok:
            return False, "error al guardar detalle"

        return True, f"solicitud creada correctamente folio #{id_solicitud}"

    except Exception as e:
        return False, f"error: {str(e)}"


def obtener_solicitudes_pendientes_usuario_ctrl(solicitante: str, ver_todas: bool = False):
    return get_solicitudes_pendientes_usuario_model(solicitante, ver_todas=ver_todas)


def obtener_detalle_solicitud_compra_ctrl(id_solicitud_compra: int):
    return get_detalle_solicitud_compra_model(id_solicitud_compra)

def obtener_cabecera_solicitud_compra_ctrl(id_solicitud_compra: int):
    return get_cabecera_solicitud_compra_model(id_solicitud_compra)


def enviar_solicitud_compra_ctrl(id_solicitud_compra: int, token=None):
    cab = get_cabecera_solicitud_compra_model(id_solicitud_compra)

    if not cab:
        return False, "no se encontró la solicitud"

    estatus_actual = str(cab.get("estatus") or "").strip().lower()
    if estatus_actual != "captura":
        return False, "solo se pueden enviar solicitudes en captura"

    ok = cambiar_estatus_solicitud_compra_model(id_solicitud_compra, "enviada")
    if not ok:
        return False, "no se pudo actualizar el estatus"

    # Materia Prima (Inventario) tiene su propio circuito de autorización
    # (SuperAdmin/forecastAdmin, ver autorizar_solicitud_compra_ctrl) — se
    # notifica a esos roles en vez de a Compras MP/Compras Admin, que son
    # quienes atienden los demás tipos de compra (sin autorización, solo
    # notificación).
    tipo_formulario = str(cab.get("tipo_formulario") or "").strip().upper()
    if tipo_formulario == "MP_INV":
        correos = list({
            *get_correos_usuarios_por_rol_ctrl("SuperAdmin"),
            *get_correos_usuarios_por_rol_ctrl("forecastAdmin"),
        })
        rol_destino = "SuperAdmin/forecastAdmin"
    else:
        correos = get_correos_roles_compras_model()
        rol_destino = "Compras MP o Compras Admin"

    if not correos:
        return True, f"solicitud enviada, pero no se encontraron correos de {rol_destino}"

    asunto = f"nueva solicitud de compra enviada #{id_solicitud_compra}"

    cuerpo_html = f"""
    <div style="font-family:arial,sans-serif;font-size:14px;line-height:1.4">
      <p>se envió una nueva solicitud de compra.</p>
      <p>
        <b>id solicitud:</b> {cab.get('id_solicitud_compra', '')}<br>
        <b>tipo:</b> {cab.get('tipo_compra', '')}<br>
        <b>fecha solicitud:</b> {cab.get('fecha_solicitud', '')}<br>
        <b>solicitante:</b> {cab.get('solicitante', '')}<br>
        <b>estatus:</b> enviada
      </p>
      <p>
        <b>observaciones generales:</b><br>
        {cab.get('observaciones_generales', '') or '-'}
      </p>
    </div>
    """

    destinatario = ", ".join(correos)
    remitente = str((st.session_state.get("usuario") or {}).get("email") or "").strip()

    ok_mail, msg_mail = enviar_correo(
        destinatario=destinatario,
        asunto=asunto,
        cuerpo_html=cuerpo_html,
        token=token,
        remitente=remitente,
    )

    if ok_mail:
        return True, "solicitud enviada y correo notificado a compras"
    return True, f"solicitud enviada, pero no se pudo mandar correo: {msg_mail}"

def eliminar_solicitud_compra_ctrl(id_solicitud_compra: int):
    cab = get_cabecera_solicitud_compra_model(id_solicitud_compra)

    if not cab:
        return False, "no se encontró la solicitud"

    estatus_actual = str(cab.get("estatus") or "").strip().lower()
    if estatus_actual != "captura":
        return False, "solo se pueden eliminar solicitudes en captura"

    ok = eliminar_solicitud_compra_model(id_solicitud_compra)
    if not ok:
        return False, "no se pudo eliminar la solicitud"

    return True, "solicitud eliminada correctamente"


def autorizar_solicitud_compra_ctrl(id_solicitud_compra: int, usuario_nombre: str):
    """Autoriza una solicitud 'enviada' — hoy solo lo usa el tipo Materia
    Prima (Inventario) (ver Compras -> Autorizaciones), SuperAdmin/
    forecastAdmin."""
    cab = get_cabecera_solicitud_compra_model(id_solicitud_compra)
    if not cab:
        return False, "no se encontró la solicitud"

    estatus_actual = str(cab.get("estatus") or "").strip().lower()
    if estatus_actual != "enviada":
        return False, "solo se pueden autorizar solicitudes enviadas"

    ok = cambiar_estatus_solicitud_compra_model(id_solicitud_compra, "autorizada")
    if not ok:
        return False, "no se pudo actualizar el estatus"

    return True, f"solicitud #{id_solicitud_compra} autorizada por {usuario_nombre}"


def rechazar_solicitud_compra_ctrl(id_solicitud_compra: int, usuario_nombre: str, motivo: str = ""):
    cab = get_cabecera_solicitud_compra_model(id_solicitud_compra)
    if not cab:
        return False, "no se encontró la solicitud"

    estatus_actual = str(cab.get("estatus") or "").strip().lower()
    if estatus_actual != "enviada":
        return False, "solo se pueden rechazar solicitudes enviadas"

    ok = cambiar_estatus_solicitud_compra_model(id_solicitud_compra, "rechazada")
    if not ok:
        return False, "no se pudo actualizar el estatus"

    return True, f"solicitud #{id_solicitud_compra} rechazada por {usuario_nombre}" + (f" — {motivo}" if motivo else "")


def obtener_mp_solicitadas_sae_ctrl(anio: int, meses: list[int]):
    return obtener_mp_solicitadas_sae_model(anio=anio, meses=meses)


def buscar_productos_sae_ctrl(q: str = "", limit: int = 50) -> list[dict]:
    return buscar_producto_sae(st.secrets, q=q, limit=limit)

def get_departamentos_compra_ctrl():
    return get_departamentos_compra_model()


def get_formas_pago_compra_ctrl():
    return get_formas_pago_compra_model()


def get_unidades_negocio_compra_ctrl():
    return get_unidades_negocio_compra_model()


def crear_solicitud_estandar_ctrl(
    *,
    id_tipo_compra: int,
    fecha_solicitud,
    solicitante: str,
    observaciones_generales: str,
    id_departamento: int,
    id_forma_pago: int,
    detalle: list,
):
    try:
        solicitante = (solicitante or "").strip()
        observaciones_generales = (observaciones_generales or "").strip()

        if not id_tipo_compra:
            return False, "falta el tipo de compra"

        if not fecha_solicitud:
            return False, "falta la fecha de solicitud"

        if not solicitante:
            return False, "falta el solicitante interno"

        if not id_departamento:
            return False, "falta el departamento"

        if not id_forma_pago:
            return False, "falta la forma de pago"

        if not detalle:
            return False, "no hay renglones para guardar"

        id_solicitud_compra = crear_solicitud_cabecera_model(
            id_tipo_compra=id_tipo_compra,
            fecha_solicitud=fecha_solicitud,
            solicitante=solicitante,
            observaciones_generales=observaciones_generales,
        )

        if not id_solicitud_compra:
            return False, "no se pudo crear la cabecera"

        id_solicitud_estandar, folio = crear_solicitud_estandar_cabecera_model(
            id_solicitud_compra=id_solicitud_compra,
            fecha_elaboracion=fecha_solicitud,
            id_departamento=id_departamento,
            id_forma_pago=id_forma_pago,
            observaciones=observaciones_generales,
        )

        if not id_solicitud_estandar:
            return False, "no se pudo crear la cabecera estándar"

        ok = crear_solicitud_estandar_detalle_model(
            id_solicitud_estandar=id_solicitud_estandar,
            detalle=detalle,
        )

        if not ok:
            return False, "error al guardar detalle estándar"

        return True, f"solicitud creada correctamente folio {folio}"

    except Exception as e:
        return False, f"error: {str(e)}"
    
def obtener_cabecera_solicitud_estandar_ctrl(id_solicitud_compra: int):
    return get_cabecera_solicitud_estandar_model(id_solicitud_compra)


def obtener_detalle_solicitud_estandar_ctrl(id_solicitud_compra: int):
    return get_detalle_solicitud_estandar_model(id_solicitud_compra)


def obtener_tipo_compra_mp_inventario_ctrl() -> dict | None:
    tipos = get_tipos_compra_activos_model() or []
    for t in tipos:
        if str(t.get("tipo_formulario") or "").strip().upper() == "MP_INV":
            return t
    return None


def crear_solicitud_mp_inventario_ctrl(
    *,
    id_tipo_compra: int,
    fecha_solicitud,
    solicitante: str,
    observaciones_generales: str,
    detalle: list,
):
    try:
        solicitante = (solicitante or "").strip()
        observaciones_generales = (observaciones_generales or "").strip()

        if not id_tipo_compra:
            return False, "falta el tipo de compra"

        if not fecha_solicitud:
            return False, "falta la fecha de solicitud"

        if not solicitante:
            return False, "falta el solicitante interno"

        if not detalle:
            return False, "no hay materias primas para guardar"

        id_solicitud_compra = crear_solicitud_cabecera_model(
            id_tipo_compra=id_tipo_compra,
            fecha_solicitud=fecha_solicitud,
            solicitante=solicitante,
            observaciones_generales=observaciones_generales,
        )

        if not id_solicitud_compra:
            return False, "no se pudo crear la cabecera"

        ok = crear_solicitud_mp_inventario_detalle_model(
            id_solicitud_compra=id_solicitud_compra,
            detalle=detalle,
        )

        if not ok:
            return False, "error al guardar el detalle de materias primas"

        return True, f"solicitud creada correctamente folio #{id_solicitud_compra}"

    except Exception as e:
        return False, f"error: {str(e)}"


def obtener_detalle_solicitud_mp_inventario_ctrl(id_solicitud_compra: int):
    return get_detalle_solicitud_mp_inventario_model(id_solicitud_compra)