"""Motor de flujos de autorización dinámicos de Compras — reemplaza al
motor de reglas (compras_autorizacion_engine_controller.py /
compras_reglas_autorizacion_*). Por tipo de compra se define un flujo con
niveles secuenciales (N1 → N2 → N3...), cada uno ligado a un PUESTO (no un
usuario fijo ni un rol genérico); el monto de la solicitud decide cuántos
niveles de la cadena aplican — si el monto queda por debajo del primer
nivel, la solicitud se autoriza sola (0 niveles), igual que hoy una regla
por debajo de su límite. Al resolverse el último nivel aplicable, se
dispara la finalización (ver compras_requisicion_sae_controller.py)."""

import streamlit as st
import pandas as pd

from models.compras_flujos_model import (
    obtener_flujos_model,
    obtener_flujo_activo_por_tipo_model,
    obtener_niveles_de_flujo_model,
    guardar_flujo_model,
    cambiar_estatus_flujo_model,
    crear_niveles_solicitud_model,
    obtener_niveles_solicitud_model,
    obtener_nivel_pendiente_solicitud_model,
    resolver_nivel_model,
    activar_siguiente_nivel_model,
    guardar_flujo_aplicado_model,
    obtener_solicitudes_con_nivel_pendiente_model,
)
from controllers.compras_puestos_controller import (
    usuario_pertenece_a_puesto_ctrl,
    obtener_correos_de_puesto_ctrl,
)
from models.compras_solicitudes_model import (
    cambiar_estatus_solicitud_compra_model,
    get_cabecera_solicitud_compra_model,
    get_correos_roles_compras_model,
)
from utils.envio_correo import enviar_correo


@st.cache_data(ttl=60, show_spinner=False)
def obtener_flujos_ctrl() -> pd.DataFrame:
    return obtener_flujos_model()


def obtener_flujo_activo_ctrl(id_tipo_compra: int) -> dict | None:
    return obtener_flujo_activo_por_tipo_model(id_tipo_compra)


def obtener_niveles_de_flujo_ctrl(id_flujo: int) -> list[dict]:
    return obtener_niveles_de_flujo_model(id_flujo)


def validar_niveles_ctrl(niveles: list[dict]) -> tuple[bool, str]:
    """Valida que los rangos de monto sean contiguos y crecientes: el nivel
    1 empieza en 0 (o en el monto desde donde deja de auto-aprobarse), cada
    siguiente monto_desde = monto_hasta del anterior, y solo el último nivel
    puede tener monto_hasta vacío (sin tope)."""
    if not niveles:
        return False, "el flujo necesita al menos 1 nivel"
    niveles_orden = sorted(niveles, key=lambda n: int(n["orden"]))
    for idx, n in enumerate(niveles_orden, start=1):
        if int(n["orden"]) != idx:
            return False, "el orden de los niveles debe ser consecutivo (1, 2, 3...) sin huecos"
        if not n.get("id_puesto"):
            return False, f"el nivel {idx} necesita un puesto"
    for idx, n in enumerate(niveles_orden):
        hasta = n.get("monto_hasta_mxn")
        es_ultimo = idx == len(niveles_orden) - 1
        if es_ultimo and hasta not in (None, ""):
            return False, "el último nivel no debe tener 'monto hasta' (sin tope)"
        if not es_ultimo and hasta in (None, ""):
            return False, "solo el último nivel puede quedar sin 'monto hasta'"
        if not es_ultimo:
            siguiente = niveles_orden[idx + 1]
            if float(siguiente["monto_desde_mxn"]) != float(hasta):
                return False, (
                    f"el nivel {idx + 2} debe empezar exactamente donde termina el nivel {idx + 1} "
                    f"(${float(hasta):,.2f})"
                )
    return True, ""


def guardar_flujo_ctrl(
    id_tipo_compra: int, nombre: str, niveles: list[dict],
    accion_final_generar_sae: bool, accion_final_enviar_correo: bool,
    id_puesto_notificar: int | None, id_flujo: int | None = None,
) -> tuple[bool, str]:
    ok_val, msg_val = validar_niveles_ctrl(niveles)
    if not ok_val:
        return False, msg_val
    resultado = guardar_flujo_model(
        id_tipo_compra, nombre, niveles, accion_final_generar_sae,
        accion_final_enviar_correo, id_puesto_notificar, id_flujo,
    )
    obtener_flujos_ctrl.clear()
    return (True, "flujo guardado") if resultado else (False, "no se pudo guardar el flujo")


def cambiar_estatus_flujo_ctrl(id_flujo: int, activo: bool) -> bool:
    ok = cambiar_estatus_flujo_model(id_flujo, 1 if activo else 0)
    obtener_flujos_ctrl.clear()
    return ok


def resolver_niveles_aplicables_ctrl(id_tipo_compra: int, monto_mxn: float | None) -> dict:
    """{"tiene_flujo": bool, "niveles": [...]} — niveles vacío con
    tiene_flujo=True significa "auto-aprobada" (monto por debajo del primer
    nivel); tiene_flujo=False significa que ese tipo de compra no tiene
    ningún flujo configurado todavía (fallback a aviso genérico)."""
    flujo = obtener_flujo_activo_ctrl(id_tipo_compra)
    if not flujo:
        return {"tiene_flujo": False, "flujo": None, "niveles": []}

    niveles = flujo.get("niveles") or []
    if monto_mxn is None:
        # sin monto para evaluar: siempre requiere la cadena completa, igual
        # criterio conservador que el motor anterior.
        return {"tiene_flujo": True, "flujo": flujo, "niveles": niveles}

    niveles_aplicables = [n for n in niveles if float(monto_mxn) >= float(n["monto_desde_mxn"])]
    return {"tiene_flujo": True, "flujo": flujo, "niveles": niveles_aplicables}


def iniciar_flujo_solicitud_ctrl(id_solicitud_compra: int, id_tipo_compra: int, monto_mxn: float | None, token=None) -> dict:
    """Arranca el flujo de una solicitud recién enviada. Retorna
    {"requiere_autorizacion": bool, "tiene_flujo": bool, "motivo": str}."""
    resuelto = resolver_niveles_aplicables_ctrl(id_tipo_compra, monto_mxn)

    if not resuelto["tiene_flujo"]:
        return {
            "requiere_autorizacion": True, "tiene_flujo": False,
            "motivo": "no hay ningún flujo de autorización configurado para este tipo de compra",
        }

    niveles = resuelto["niveles"]
    if not niveles:
        guardar_flujo_aplicado_model(id_solicitud_compra, resuelto["flujo"]["id_flujo"])
        monto_txt = f"${float(monto_mxn):,.2f}" if monto_mxn is not None else "sin monto"
        _, msg_final = _finalizar_solicitud_ctrl(id_solicitud_compra, "", token=token)
        return {
            "requiere_autorizacion": False, "tiene_flujo": True,
            "motivo": f"{monto_txt} queda por debajo del primer nivel del flujo — se autoriza sola. {msg_final}",
        }

    ok = crear_niveles_solicitud_model(id_solicitud_compra, resuelto["flujo"]["id_flujo"], niveles)
    if ok:
        _notificar_nivel_ctrl(niveles[0]["id_puesto"], id_solicitud_compra, token=token)

    return {
        "requiere_autorizacion": True, "tiene_flujo": True,
        "motivo": f"flujo '{resuelto['flujo']['nombre']}' — {len(niveles)} nivel(es) por autorizar",
    }


def _notificar_nivel_ctrl(id_puesto: int, id_solicitud_compra: int, token=None) -> None:
    correos = obtener_correos_de_puesto_ctrl(id_puesto)
    if not correos:
        return
    cab = get_cabecera_solicitud_compra_model(id_solicitud_compra) or {}
    asunto = f"solicitud de compra #{id_solicitud_compra} pendiente de tu autorización"
    cuerpo_html = f"""
    <div style="font-family:arial,sans-serif;font-size:14px;line-height:1.4">
      <p>tienes una solicitud de compra pendiente de autorizar.</p>
      <p>
        <b>id solicitud:</b> {id_solicitud_compra}<br>
        <b>tipo:</b> {cab.get('tipo_compra', '')}<br>
        <b>solicitante:</b> {cab.get('solicitante', '')}<br>
        <b>fecha solicitud:</b> {cab.get('fecha_solicitud', '')}
      </p>
    </div>
    """
    remitente = str((st.session_state.get("usuario") or {}).get("email") or "").strip()
    try:
        enviar_correo(
            destinatario=", ".join(correos), asunto=asunto, cuerpo_html=cuerpo_html,
            token=token, remitente=remitente,
        )
    except Exception:
        pass


def obtener_niveles_solicitud_ctrl(id_solicitud_compra: int) -> list[dict]:
    return obtener_niveles_solicitud_model(id_solicitud_compra)


def nivel_pendiente_de_usuario_ctrl(id_solicitud_compra: int, usuario_id: int) -> dict | None:
    """El nivel 'pendiente' de esta solicitud, solo si el usuario pertenece
    al puesto de ese nivel — None si no hay nivel pendiente o no le toca a
    este usuario autorizarlo."""
    nivel = obtener_nivel_pendiente_solicitud_model(id_solicitud_compra)
    if not nivel:
        return None
    if not usuario_pertenece_a_puesto_ctrl(usuario_id, nivel["id_puesto"]):
        return None
    return nivel


def obtener_solicitudes_con_nivel_pendiente_ctrl(usuario_id: int | None, es_superadmin: bool) -> list[int]:
    return obtener_solicitudes_con_nivel_pendiente_model(usuario_id, ver_todas=es_superadmin)


def es_ultimo_nivel_pendiente_ctrl(id_solicitud_compra: int) -> bool:
    nivel = obtener_nivel_pendiente_solicitud_model(id_solicitud_compra)
    if not nivel:
        return False
    niveles = obtener_niveles_solicitud_model(id_solicitud_compra)
    return int(nivel["orden"]) == max(int(n["orden"]) for n in niveles)


def preview_finalizacion_sae_ctrl(id_solicitud_compra: int) -> list[dict] | None:
    """Si autorizar el nivel pendiente actual sería el ÚLTIMO del flujo Y
    ese flujo genera Requisición en SAE al finalizar, regresa la vista
    previa de lo que se insertaría (para mostrar y pedir confirmación antes
    del commit real) — None si no aplica (no es el último nivel, o el flujo
    no genera nada en SAE)."""
    if not es_ultimo_nivel_pendiente_ctrl(id_solicitud_compra):
        return None
    cab = get_cabecera_solicitud_compra_model(id_solicitud_compra) or {}
    flujo = obtener_flujo_activo_ctrl(cab.get("id_tipo_compra")) if cab.get("id_tipo_compra") else None
    if not flujo or not flujo.get("accion_final_generar_sae"):
        return None
    from controllers.compras_solicitudes_sae_controller import obtener_vista_previa_requisiciones_solicitud_ctrl
    return obtener_vista_previa_requisiciones_solicitud_ctrl(id_solicitud_compra)


def autorizar_nivel_ctrl(
    id_solicitud_compra: int, usuario_id: int, usuario_nombre: str,
    comentario: str = "", token=None,
) -> tuple[bool, str]:
    nivel = obtener_nivel_pendiente_solicitud_model(id_solicitud_compra)
    if not nivel:
        return False, "esta solicitud no tiene un nivel pendiente de autorizar"
    if not usuario_pertenece_a_puesto_ctrl(usuario_id, nivel["id_puesto"]):
        return False, "no tienes el puesto requerido para autorizar este nivel"

    resolver_nivel_model(nivel["id"], "autorizado", usuario_id, comentario or None)

    niveles = obtener_niveles_solicitud_model(id_solicitud_compra)
    siguiente_orden = int(nivel["orden"]) + 1
    siguiente = next((n for n in niveles if int(n["orden"]) == siguiente_orden), None)

    if siguiente:
        activar_siguiente_nivel_model(id_solicitud_compra, siguiente_orden)
        _notificar_nivel_ctrl(siguiente["id_puesto"], id_solicitud_compra, token=token)
        return True, f"nivel {nivel['orden']} autorizado — pasa a nivel {siguiente_orden} ({siguiente['puesto_nombre']})"

    ok_final, msg_final = _finalizar_solicitud_ctrl(id_solicitud_compra, usuario_nombre, token=token)
    return True, f"último nivel autorizado. {msg_final}"


def rechazar_nivel_ctrl(id_solicitud_compra: int, usuario_id: int, usuario_nombre: str, motivo: str = "") -> tuple[bool, str]:
    nivel = obtener_nivel_pendiente_solicitud_model(id_solicitud_compra)
    if not nivel:
        return False, "esta solicitud no tiene un nivel pendiente de autorizar"
    if not usuario_pertenece_a_puesto_ctrl(usuario_id, nivel["id_puesto"]):
        return False, "no tienes el puesto requerido para rechazar este nivel"

    resolver_nivel_model(nivel["id"], "rechazado", usuario_id, motivo or None)
    cambiar_estatus_solicitud_compra_model(id_solicitud_compra, "rechazada")
    return True, f"solicitud #{id_solicitud_compra} rechazada por {usuario_nombre} en el nivel {nivel['orden']}" + (f" — {motivo}" if motivo else "")


def _finalizar_solicitud_ctrl(id_solicitud_compra: int, usuario_nombre: str, token=None) -> tuple[bool, str]:
    from controllers.compras_solicitudes_sae_controller import generar_requisiciones_solicitud_ctrl

    cab = get_cabecera_solicitud_compra_model(id_solicitud_compra) or {}
    id_tipo_compra = cab.get("id_tipo_compra")
    flujo = obtener_flujo_activo_ctrl(id_tipo_compra) if id_tipo_compra else None

    cambiar_estatus_solicitud_compra_model(id_solicitud_compra, "finalizada")
    mensajes = []

    if flujo and flujo.get("accion_final_generar_sae"):
        ok_sae, msg_sae = generar_requisiciones_solicitud_ctrl(id_solicitud_compra)
        mensajes.append(msg_sae)

    if flujo and flujo.get("accion_final_enviar_correo"):
        correos = (
            obtener_correos_de_puesto_ctrl(flujo["id_puesto_notificar"])
            if flujo.get("id_puesto_notificar") else []
        )
        if not correos:
            correos = get_correos_roles_compras_model()
        if correos:
            asunto = f"solicitud de compra #{id_solicitud_compra} finalizada"
            cuerpo_html = f"""
            <div style="font-family:arial,sans-serif;font-size:14px;line-height:1.4">
              <p>la solicitud de compra #{id_solicitud_compra} completó todos los niveles de
              autorización y quedó finalizada.</p>
              <p><b>solicitante:</b> {cab.get('solicitante', '')}<br>
              <b>tipo:</b> {cab.get('tipo_compra', '')}</p>
            </div>
            """
            remitente = str((st.session_state.get("usuario") or {}).get("email") or "").strip()
            try:
                enviar_correo(destinatario=", ".join(correos), asunto=asunto, cuerpo_html=cuerpo_html, token=token, remitente=remitente)
                mensajes.append("correo de cierre enviado")
            except Exception:
                mensajes.append("no se pudo enviar el correo de cierre")

    return True, " — ".join(mensajes) if mensajes else "solicitud finalizada"
