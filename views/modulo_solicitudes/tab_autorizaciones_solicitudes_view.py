#views/modulo_solicitudes/tab_autorizaciones_solicitudes_view.py

from __future__ import annotations

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import base64
import hmac
import hashlib
import json

from controllers.solicitudes_controller import (
    listar_solicitudes_ctrl,
    get_solicitud_ctrl,
    cambiar_estatus_ctrl,
    get_detalle_ctrl,
    get_usuarios_activos_ctrl,
    get_correos_usuarios_por_rol_ctrl,
    get_dispersion_flags_ctrl,
    set_dispersion_flag_ctrl,
)
from utils.envio_correo import enviar_correo
from textwrap import dedent

def _verify_token(token: str, secret: str) -> dict | None:
    try:
        raw_b64, sig_b64 = token.split(".", 1)

        pad = "=" * (-len(raw_b64) % 4)
        raw = base64.urlsafe_b64decode(raw_b64 + pad)

        pad2 = "=" * (-len(sig_b64) % 4)
        sig = base64.urlsafe_b64decode(sig_b64 + pad2)

        expected = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).digest()
        if not hmac.compare_digest(sig, expected):
            return None

        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


def _consume_deeplink_old():
    """
    lee query params:
      ?sg_id=123&action=approve|reject&t=token
    si token es válido y no expiró:
      - set aut_selected_id
      - set aut_pending_action
    """
    qp = st.query_params
    qp_sg_id = qp.get("sg_id", None)
    qp_action = (qp.get("action", "") or "").strip().lower()
    qp_token = (qp.get("t", "") or "").strip()

    if not qp_sg_id or not qp_token:
        return

    try:
        sg_id = int(qp_sg_id)
    except Exception:
        return

    secret = str(st.secrets.get("APP_LINK_SECRET", "")).strip()
    if not secret:
        st.warning("falta APP_LINK_SECRET en secrets.toml")
        return

    payload = _verify_token(qp_token, secret)
    if not payload:
        st.warning("link inválido (token).")
        return

    # expira
    exp = int(payload.get("exp") or 0)
    if exp <= 0 or int(datetime.utcnow().timestamp()) > exp:
        st.warning("link expirado.")
        return

    # valida que el token corresponda al sg_id
    if int(payload.get("sg_id") or 0) != int(sg_id):
        st.warning("link inválido (id no coincide).")
        return

    # aplica selección + acción
    st.session_state["aut_selected_id"] = int(sg_id)

    if qp_action in ("approve", "reject"):
        st.session_state["aut_pending_action"] = qp_action

    # opcional: limpiar query params para que no se re-dispare en cada rerun
    try:
        st.query_params.clear()
    except Exception:
        pass


def _consume_deeplink():
    """
    lee query params o session_state:
      ?sg_id=123&action=approve|reject&t=token
    si token es válido y no expiró:
      - set aut_selected_id
      - set aut_pending_action
    """
    deeplink_session = st.session_state.get("deeplink_params") or {}
    qp = st.query_params

    qp_sg_id = (
        deeplink_session.get("sg_id")
        or qp.get("sg_id", None)
    )
    qp_action = (
        deeplink_session.get("action")
        or qp.get("action", "")
        or ""
    ).strip().lower()
    qp_token = (
        deeplink_session.get("t")
        or qp.get("t", "")
        or ""
    ).strip()

    if not qp_sg_id or not qp_token:
        return

    try:
        sg_id = int(qp_sg_id)
    except Exception:
        return

    secret = str(st.secrets.get("APP_LINK_SECRET", "")).strip()
    if not secret:
        st.warning("falta APP_LINK_SECRET en secrets.toml")
        return

    payload = _verify_token(qp_token, secret)
    if not payload:
        st.warning("link inválido (token).")
        st.session_state.pop("deeplink_params", None)
        return

    exp = int(payload.get("exp") or 0)
    if exp <= 0 or int(datetime.utcnow().timestamp()) > exp:
        st.warning("link expirado.")
        st.session_state.pop("deeplink_params", None)
        return

    if int(payload.get("sg_id") or 0) != int(sg_id):
        st.warning("link inválido (id no coincide).")
        st.session_state.pop("deeplink_params", None)
        return

    st.session_state["aut_selected_id"] = int(sg_id)

    if qp_action in ("approve", "reject"):
        st.session_state["aut_pending_action"] = qp_action

    st.session_state.pop("deeplink_params", None)

    try:
        st.query_params.clear()
    except Exception:
        pass
    
def _get_email_vendedor(solicitud: dict) -> str | None:
    empleado_id = int(solicitud.get("empleado_id") or 0)
    if not empleado_id:
        return None

    users = get_usuarios_activos_ctrl() or []
    for u in users:
        if int(u.get("id") or 0) == empleado_id:
            return (
                (u.get("email") or "").strip()
                or (u.get("correo") or "").strip()
                or (u.get("username") or "").strip()
                or None
            )
    return None

def _enviar_dispersion_correo(
        *,
        solicitud: dict,
        token,
        concepto_notificado: str,
        estatus_final: str,
    ) -> tuple[bool, str]:
    usuario = st.session_state.get("usuario") or {}
    remitente = str(usuario.get("email") or "").strip()

    if not remitente:
        return False, "no se encontró correo del remitente."

    destinatario = _get_email_vendedor(solicitud)
    if not destinatario:
        return False, "no se encontró correo del vendedor (empleado)."

    folio = str(solicitud.get("folio") or "").strip()
    vendedor_nombre = str(solicitud.get("empleado_nombre") or "").strip()
    concepto_notificado = str(concepto_notificado or "").strip()

    asunto = f"actualización de dispersión de solicitud {folio}".strip()

    mensaje_extra = ""
    if str(estatus_final).strip().lower() == "dispersion":
        mensaje_extra = (
            "<p>la dispersión de la solicitud quedó completada y el estatus actual es "
            "<b>dispersion</b>.</p>"
        )
    else:
        mensaje_extra = (
            "<p>la solicitud sigue pendiente de completar el resto de la dispersión.</p>"
        )

    cuerpo_html = f"""
    <div style="font-family:arial,sans-serif;font-size:14px;line-height:1.4">
      <p>se actualizó la dispersión de tu solicitud de gastos.</p>
      <p>
        <b>folio:</b> {folio}<br>
        <b>vendedor:</b> {vendedor_nombre}<br>
        <b>concepto dispersado:</b> {concepto_notificado}<br>
        <b>estatus actual:</b> {estatus_final}
      </p>
      {mensaje_extra}
    </div>
    """

    return enviar_correo(
        destinatario=destinatario,
        asunto=asunto,
        cuerpo_html=cuerpo_html,
        token=token,
        remitente=remitente,
    )

def _enviar_rechazo_correo(*, solicitud: dict, motivo: str, token):
    usuario = st.session_state.get("usuario") or {}
    remitente = str(usuario.get("email") or "").strip()
    if not remitente:
        return False, "no se encontró correo del remitente."
    folio = str(solicitud.get("folio") or "").strip()
    vendedor_nombre = str(solicitud.get("empleado_nombre") or "").strip()
    destinatario = _get_email_vendedor(solicitud)
    if not destinatario:
        return False, "no se encontró correo del vendedor (empleado)."

    asunto = f"solicitud de gastos rechazada {folio}".strip()

    cuerpo_html = f"""
    <div style="font-family:arial,sans-serif;font-size:14px;line-height:1.4">
      <p>tu solicitud de gastos fue rechazada.</p>
      <p>
        <b>folio:</b> {folio}<br>
        <b>vendedor:</b> {vendedor_nombre}<br>
      </p>

      <p><b>motivo del rechazo:</b></p>
      <div style="border:1px solid #ddd;padding:10px;border-radius:8px;background:#fafafa;white-space:pre-wrap">
        {motivo.strip()}
      </div>
    </div>
    """

    return enviar_correo(
        destinatario=destinatario,
        asunto=asunto,
        cuerpo_html=cuerpo_html,
        token=token,
        remitente=remitente,
    )

def _enviar_autorizacion_correo(*, solicitud: dict, token, estatus_final: str = "autorizada"):
    usuario = st.session_state.get("usuario") or {}
    remitente = str(usuario.get("email") or "").strip()

    if not remitente:
        return False, "no se encontró correo del remitente."

    folio = str(solicitud.get("folio") or "").strip()
    vendedor_nombre = str(solicitud.get("empleado_nombre") or "").strip()

    destinatario = _get_email_vendedor(solicitud)
    if not destinatario:
        return False, "no se encontró correo del vendedor (empleado)."

    asunto = f"solicitud de gastos autorizada {folio}".strip()

    if str(estatus_final).strip().lower() == "dispersion":
        mensaje_extra = "<p>la solicitud no requiere dispersión adicional, por lo que avanzó automáticamente al estatus <b>dispersion</b>.</p>"
    else:
        mensaje_extra = "<p>puedes continuar con el proceso correspondiente.</p>"

    cuerpo_html = f"""
    <div style="font-family:arial,sans-serif;font-size:14px;line-height:1.4">
      <p>tu solicitud de gastos fue autorizada.</p>
      <p>
        <b>folio:</b> {folio}<br>
        <b>vendedor:</b> {vendedor_nombre}<br>
        <b>estatus actual:</b> {estatus_final}
      </p>
      {mensaje_extra}
    </div>
    """

    return enviar_correo(
        destinatario=destinatario,
        asunto=asunto,
        cuerpo_html=cuerpo_html,
        token=token,
        remitente=remitente,
    )

def _correos_unicos_validos(correos: list[str]) -> list[str]:
    out = []
    seen = set()

    for c in correos or []:
        correo = str(c or "").strip()
        if not correo:
            continue

        key = correo.lower()
        if key in seen:
            continue

        seen.add(key)
        out.append(correo)

    return out


def _enviar_correo_requerimiento_dispersion(
    *,
    solicitud: dict,
    token,
    nombre_rol: str,
    tipo_requerimiento: str,
) -> tuple[bool, str]:
    usuario = st.session_state.get("usuario") or {}
    remitente = str(usuario.get("email") or "").strip()

    if not remitente:
        return False, "no se encontró correo del remitente."

    destinatarios = _correos_unicos_validos(
        get_correos_usuarios_por_rol_ctrl(nombre_rol) or []
    )

    if not destinatarios:
        return False, f"no se encontraron correos activos para el rol {nombre_rol}."

    folio = str(solicitud.get("folio") or "").strip()
    vendedor_nombre = str(solicitud.get("empleado_nombre") or "").strip()
    cliente = (
        str(solicitud.get("cliente") or "")
        or str(solicitud.get("clientes") or "")
    ).strip()

    ciudad = (
        str(solicitud.get("ciudad") or "")
        or str(solicitud.get("ciudades") or "")
    ).strip()

    asunto = f"solicitud de gastos pendiente de dispersión {folio} - {tipo_requerimiento}".strip()

    cuerpo_html = f"""
    <div style="font-family:arial,sans-serif;font-size:14px;line-height:1.4">
      <p>se autorizó una solicitud de gastos que requiere atención de <b>{nombre_rol}</b>.</p>

      <p>
        <b>folio:</b> {folio}<br>
        <b>vendedor:</b> {vendedor_nombre}<br>
        <b>cliente:</b> {cliente}<br>
        <b>ciudad:</b> {ciudad}<br>
        <b>requerimiento:</b> {tipo_requerimiento}<br>
        <b>estatus actual:</b> autorizada
      </p>

      <p>favor de ingresar al módulo de solicitudes para continuar con la dispersión correspondiente.</p>
    </div>
    """

    ok_count = 0
    errores = []

    for destinatario in destinatarios:
        ok_mail, msg_mail = enviar_correo(
            destinatario=destinatario,
            asunto=asunto,
            cuerpo_html=cuerpo_html,
            token=token,
            remitente=remitente,
        )
        if ok_mail:
            ok_count += 1
        else:
            errores.append(f"{destinatario}: {msg_mail}")

    if ok_count > 0:
        if errores:
            return True, f"correo enviado a {ok_count} destinatario(s), con algunos errores: {' | '.join(errores)}"
        return True, f"correo enviado a {ok_count} destinatario(s)."

    return False, "no se pudo enviar ningún correo. " + " | ".join(errores)

#ESTATUS_OPTS = ["todas", "captura", "enviada", "autorizada", "rechazada", "cancelada", "cerrada", "dispersion"]
ESTATUS_OPTS = ["todas", "enviada", "autorizada", "rechazada", "cerrada"]

def _estatus_color_html(e: str) -> str:
    e = (e or "").strip().lower()
    colors = {
        "captura": "#f4c542",
        "enviada": "#3498db",
        "autorizada": "#2ecc71",
        "rechazada": "#e74c3c",
        "cancelada": "#7f8c8d",
        "cerrada": "#8e44ad",
        "dispersion": "#f97316",
    }
    color = colors.get(e, "#95a5a6")

    return f"""
    <span style="
        background-color:{color};
        color:white;
        padding:4px 10px;
        border-radius:8px;
        font-size:13px;
        font-weight:600;
    ">
        {e.upper()}
    </span>
    """

def _get_usuario_actual():
    return st.session_state.get("usuario") or {}

def _norm_text(x) -> str:
    return str(x or "").strip().lower()


def _monto_detalle(r: dict) -> float:
    try:
        total_xml = float(r.get("total_xml") or 0)
    except Exception:
        total_xml = 0.0

    if total_xml > 0:
        return total_xml

    try:
        cantidad = float(r.get("cantidad") or 0)
    except Exception:
        cantidad = 0.0

    try:
        precio = float(r.get("precio_unitario") or 0)
    except Exception:
        precio = 0.0

    return round(cantidad * precio, 2)


def _analizar_requerimientos_dispersion(detalle_rows: list[dict]) -> dict:
    requiere_gasolina = False
    requiere_prepagados = False

    for r in detalle_rows or []:
        concepto = _norm_text(r.get("concepto"))
        monto = _monto_detalle(r)

        if monto <= 0:
            continue

        if concepto == "gasolina (efecticard)":
            requiere_gasolina = True
            continue

        prepago = False
        try:
            prepago = bool(PREPAGO_MAP.get(concepto, False))
        except Exception:
            prepago = False

        if prepago:
            requiere_prepagados = True

    return {
        "requiere_gasolina": requiere_gasolina,
        "requiere_prepagados": requiere_prepagados,
    }

def _get_prepago_map():
    from database.conexion import obtener_conexion

    cn = obtener_conexion()
    out = {}
    try:
        cur = cn.cursor()
        cur.execute("select concepto, prepago from solicitud_concepto_gasto")
        for concepto, prepago in cur.fetchall():
            k = (concepto or "").strip().lower()
            out[k] = bool(prepago)
    finally:
        try:
            cn.close()
        except Exception:
            pass
    return out


PREPAGO_MAP = _get_prepago_map()

def _resolver_estatus_despues_autorizacion(solicitud_id: int) -> str:
    detalle_rows = get_detalle_ctrl(int(solicitud_id)) or []
    reqs = _analizar_requerimientos_dispersion(detalle_rows)

    requiere_gasolina = bool(reqs.get("requiere_gasolina"))
    requiere_prepagados = bool(reqs.get("requiere_prepagados"))

    if requiere_gasolina or requiere_prepagados:
        return "autorizada"

    return "dispersion"

def _enviar_revision_cierre_rechazada_correo(*, solicitud: dict, motivo: str, token):
    usuario = st.session_state.get("usuario") or {}
    remitente = str(usuario.get("email") or "").strip()
    if not remitente:
        return False, "no se encontró correo del remitente."

    folio = str(solicitud.get("folio") or "").strip()
    vendedor_nombre = str(solicitud.get("empleado_nombre") or "").strip()
    destinatario = _get_email_vendedor(solicitud)
    if not destinatario:
        return False, "no se encontró correo del vendedor (empleado)."

    asunto = f"revisión de cierre rechazada {folio}".strip()

    cuerpo_html = f"""
    <div style="font-family:arial,sans-serif;font-size:14px;line-height:1.4">
      <p>la revisión de cierre de tu solicitud de gastos fue rechazada por jefe de ventas.</p>
      <p>
        <b>folio:</b> {folio}<br>
        <b>vendedor:</b> {vendedor_nombre}<br>
        <b>estatus actual:</b> dispersion
      </p>

      <p><b>comentario de rechazo:</b></p>
      <div style="border:1px solid #ddd;padding:10px;border-radius:8px;background:#fafafa;white-space:pre-wrap">
        {motivo.strip()}
      </div>
    </div>
    """

    return enviar_correo(
        destinatario=destinatario,
        asunto=asunto,
        cuerpo_html=cuerpo_html,
        token=token,
        remitente=remitente,
    )

def _enviar_revision_cierre_aprobada_correo(*, solicitud: dict, token):
    usuario = st.session_state.get("usuario") or {}
    remitente = str(usuario.get("email") or "").strip()
    if not remitente:
        return False, "no se encontró correo del remitente."

    folio = str(solicitud.get("folio") or "").strip()
    vendedor_nombre = str(solicitud.get("empleado_nombre") or "").strip()
    destinatario = _get_email_vendedor(solicitud)
    if not destinatario:
        return False, "no se encontró correo del vendedor (empleado)."

    asunto = f"revisión de cierre aprobada {folio}".strip()

    cuerpo_html = f"""
    <div style="font-family:arial,sans-serif;font-size:14px;line-height:1.4">
      <p>la revisión de cierre de tu solicitud de gastos fue aprobada por jefe de ventas.</p>
      <p>
        <b>folio:</b> {folio}<br>
        <b>vendedor:</b> {vendedor_nombre}<br>
        <b>estatus actual:</b> contabilidad
      </p>
      <p>la solicitud avanzó al área de contabilidad.</p>
    </div>
    """

    return enviar_correo(
        destinatario=destinatario,
        asunto=asunto,
        cuerpo_html=cuerpo_html,
        token=token,
        remitente=remitente,
    )

def _enviar_a_contabilidad_revision_correo(*, solicitud: dict, token):
    usuario = st.session_state.get("usuario") or {}
    remitente = str(usuario.get("email") or "").strip()

    if not remitente:
        return False, "no se encontró correo del remitente."

    destinatarios = _correos_unicos_validos(
        get_correos_usuarios_por_rol_ctrl("Contabilidad") or []
    )

    if not destinatarios:
        return False, "no se encontraron correos para contabilidad."

    folio = str(solicitud.get("folio") or "").strip()
    vendedor = str(solicitud.get("empleado_nombre") or "").strip()
    clientes = str(solicitud.get("clientes") or "").strip()
    ciudades = str(solicitud.get("ciudades") or "").strip()

    asunto = f"solicitud lista para revisión contable {folio}"

    cuerpo_html = f"""
    <div style="font-family:arial,sans-serif;font-size:14px;line-height:1.4">
      <p>una solicitud de gastos fue aprobada en su cierre y ya puede ser revisada por contabilidad.</p>

      <p>
        <b>folio:</b> {folio}<br>
        <b>vendedor:</b> {vendedor}<br>
        <b>clientes:</b> {clientes}<br>
        <b>ciudades:</b> {ciudades}<br>
        <b>estatus actual:</b> contabilidad
      </p>

      <p>favor de ingresar al módulo para iniciar la revisión contable.</p>
    </div>
    """

    ok_count = 0
    errores = []

    for dest in destinatarios:
        ok, msg = enviar_correo(
            destinatario=dest,
            asunto=asunto,
            cuerpo_html=cuerpo_html,
            token=token,
            remitente=remitente,
        )
        if ok:
            ok_count += 1
        else:
            errores.append(f"{dest}: {msg}")

    if ok_count > 0:
        return True, f"correo enviado a {ok_count} destinatario(s)"
    return False, "no se pudo enviar correo: " + " | ".join(errores)


def mostrar_tab_autorizaciones_solicitudes():
    st.subheader("autorizaciones / contabilidad")

    usuario = _get_usuario_actual()
    roles = [str(x).strip().lower() for x in (usuario.get("roles", []) or [])]

    is_admin = "admin" in roles
    is_jefe_ventas = "jefe de ventas" in roles
    is_conta = "contabilidad" in roles
    is_compras = "compras" in roles

    if not (is_admin or is_jefe_ventas or is_conta or is_compras):
        st.info("sin acceso")
        return

    if is_jefe_ventas:
        st.info("como jefe de ventas puedes autorizar o rechazar solicitudes en estatus enviada.")

    st.session_state.setdefault("aut_pending_action", "")
    _consume_deeplink()

    st.caption("filtros")
    c1, c2, c3, c4 = st.columns([2, 2, 2, 2])

    with c1:
        folio_like = st.text_input("folio contiene", key="aut_folio_like")
    with c2:
        if is_admin and is_conta and is_jefe_ventas:
            estatus_opts = ["todas", "enviada", "autorizada", "rechazada", "cerrada"]
            default_estatus = "todas"
        elif is_conta and not is_jefe_ventas:
            estatus_opts = ["autorizada", "todas"]
            default_estatus = "autorizada"
        elif is_jefe_ventas and not is_conta:
            estatus_opts = ["pendientes jefe ventas", "enviada", "cerrada", "rechazada", "todas"]
            default_estatus = "pendientes jefe ventas"
        else:
            estatus_opts = ["todas", "enviada", "autorizada", "rechazada", "cerrada"]
            default_estatus = "todas"

        default_estatus_idx = estatus_opts.index(default_estatus)

        estatus = st.selectbox(
            "estatus",
            options=estatus_opts,
            index=default_estatus_idx,
            key="aut_estatus",
        )
    with c3:
        anio = st.number_input(
            "año",
            min_value=2020,
            max_value=2100,
            value=pd.Timestamp.now().year,
            step=1,
            key="aut_anio",
        )
    with c4:
        limit = st.number_input("límite", min_value=50, max_value=2000, value=300, step=50, key="aut_limit")

    #estatus_param = "" if estatus == "todas" else estatus
    estatus_param = "" if estatus in ("todas", "pendientes jefe ventas") else estatus

    rows = listar_solicitudes_ctrl(
        folio_like=folio_like,
        estatus=estatus_param,
        anio=int(anio) if anio else None,
        empleado_id=None,
        limit=int(limit),
    ) or []
    
    if estatus == "pendientes jefe ventas":
        rows = [
            r for r in rows
            if str(r.get("estatus") or "").strip().lower() in ("enviada", "cerrada")
        ]

    df = pd.DataFrame(rows)

    if df.empty:
        st.info("sin resultados")
        return

    # contabilidad: si el usuario eligió "todas", igual puedes forzar mostrar primero autorizadas
    cols_show = [c for c in ["id", "folio", "estatus", "empleado_nombre", "clientes", "ciudades", "fecha_inicio", "fecha_fin", "created_at", "fecha_creacion"] if c in df.columns]
    df_show = df[cols_show] if cols_show else df

    def _row_style(row):
        e = str(row.get("estatus") or "").strip().lower()
        bg = {
            "captura": "#fff3cd",
            "enviada": "#dbeafe",
            "autorizada": "#dcfce7",
            "rechazada": "#fee2e2",
            "cancelada": "#e5e7eb",
            "cerrada": "#ede9fe",
            "dispersion": "#ffedd5",
        }.get(e, "")
        return [f"background-color: {bg};" for _ in row.index]

    try:
        st.dataframe(
            df_show.style.apply(_row_style, axis=1),
            use_container_width=True,
            hide_index=True,
        )
    except Exception:
        st.dataframe(df_show, use_container_width=True, hide_index=True)

    st.divider()
    st.caption("acción sobre solicitud")

    sel_id = st.number_input(
        "id solicitud",
        min_value=0,
        value=int(st.session_state.get("aut_selected_id") or 0),
        step=1,
        key="aut_selected_id",
    )

    if not sel_id:
        st.info("captura un id para ver el detalle")
        return

    s = get_solicitud_ctrl(int(sel_id))
    if not s:
        st.warning("no existe esa solicitud")
        return

    estatus_actual = str(s.get("estatus") or "").strip().lower()

    ##### utilizando el link desde el correo
    
    pending = (st.session_state.get("aut_pending_action") or "").strip().lower()

    # si viene del correo, forzamos que se muestre el panel de rechazo
    # o ejecutamos autorización con confirmación explícita
    if pending in ("approve", "reject"):
        st.info("acción solicitada desde correo. confirma para continuar.")

        # solo permitir a jefe de ventas en estatus enviada (misma regla que ya tienes)
        puede_accion_jefe = is_jefe_ventas and estatus_actual == "enviada"

        if not puede_accion_jefe:
            st.warning("no tienes permiso para autorizar/rechazar o la solicitud no está en estatus enviada.")
            st.session_state["aut_pending_action"] = ""
        else:
            cpa1, cpa2, cpa3 = st.columns([2, 2, 6])

            with cpa1:
                if st.button(
                    "confirmar autorizar",
                    use_container_width=True,
                    disabled=(pending != "approve"),
                    key="aut_btn_confirm_from_link_approve",
                ):
                    nuevo_estatus = _resolver_estatus_despues_autorizacion(int(sel_id))
                    cambiar_estatus_ctrl(int(sel_id), nuevo_estatus, int(usuario.get("id") or 0))

                    token = st.session_state.get("microsoft_token")
                    #ok_mail, msg_mail = _enviar_autorizacion_correo(solicitud=s, token=token)
                    ok_mail, msg_mail = _enviar_autorizacion_correo(
                        solicitud=s,
                        token=token,
                        estatus_final=nuevo_estatus,
                    )
                    if ok_mail:
                        st.success(f"solicitud actualizada a {nuevo_estatus} y correo enviado al vendedor.")
                    else:
                        st.warning(
                            f"solicitud actualizada a {nuevo_estatus}, pero no se pudo enviar correo: {msg_mail}"
                        )

                    st.session_state["aut_pending_action"] = ""
                    st.rerun()
            with cpa2:
                if st.button(
                    "continuar a rechazo",
                    use_container_width=True,
                    disabled=(pending != "reject"),
                    key="aut_btn_confirm_from_link_reject",
                ):
                    # abre tu panel de rechazo existente
                    st.session_state["aut_rechazando"] = True

            with cpa3:
                if st.button("cancelar acción", use_container_width=True, key="aut_btn_cancel_from_link"):
                    st.session_state["aut_pending_action"] = ""
                    st.session_state["aut_rechazando"] = False
                    st.rerun()
    #### Finaliza el link del correo

    #### css
    st.markdown("""
    <style>
    div[data-testid="stHorizontalBlock"] div[data-testid="stButton"] button[key="aut_btn_aprobar_cierre"] {
        background-color: #16a34a;
        color: white;
        border: 1px solid #16a34a;
    }
    div[data-testid="stHorizontalBlock"] div[data-testid="stButton"] button[key="aut_btn_aprobar_cierre"]:hover {
        background-color: #15803d;
        color: white;
    }

    div[data-testid="stHorizontalBlock"] div[data-testid="stButton"] button[key="aut_btn_rechazar_cierre"] {
        background-color: #dc2626;
        color: white;
        border: 1px solid #dc2626;
    }
    div[data-testid="stHorizontalBlock"] div[data-testid="stButton"] button[key="aut_btn_rechazar_cierre"]:hover {
        background-color: #b91c1c;
        color: white;
    }
    </style>
    """, unsafe_allow_html=True)

    ### finaliza csss


    # -------------------------
    # revisión final jefe ventas (cerrada -> contabilidad)
    # -------------------------
    st.session_state.setdefault("aut_revisando_cierre", False)
    st.session_state.setdefault("aut_revision_cierre_nonce", 0)

    puede_revision_cierre_jefe = is_jefe_ventas and estatus_actual == "cerrada"

    

    st.markdown("### cabecera")
    st.markdown(
        dedent(f"""
        <div style="line-height:1.8">
        <b>folio:</b> {s.get('folio','')}<br>
        <b>empleado:</b> {s.get('empleado_nombre','')}<br>
        <b>clientes:</b> {s.get('clientes','')}<br>
        <b>ciudades:</b> {s.get('ciudades','')}<br>
        <b>fecha inicio:</b> {s.get('fecha_inicio','')}<br>
        <b>fecha fin:</b> {s.get('fecha_fin','')}<br>
        <b>estatus:</b> {_estatus_color_html(estatus_actual)}
        </div>
        """),
        unsafe_allow_html=True,
    )
    
    st.markdown("### detalle de gastos")
    detalle = get_detalle_ctrl(int(sel_id)) or []
    if not detalle:
        st.info("sin detalle")
    else:
        df_det = pd.DataFrame(detalle)

        if "precio_unitario" in df_det.columns:
            df_det["precio_unitario"] = pd.to_numeric(
                df_det["precio_unitario"], errors="coerce"
            ).fillna(0.0)

            df_det = df_det[df_det["precio_unitario"] > 0].copy()

        if df_det.empty:
            st.info("sin detalle con gasto estimado mayor a 0")
        else:
            def _monto(r):
                total_xml = float(r.get("total_xml") or 0)
                if total_xml > 0:
                    return total_xml
                return float(r.get("cantidad") or 0) * float(r.get("precio_unitario") or 0)

            df_det["monto"] = df_det.apply(_monto, axis=1)

            cols_det = [
                "fecha_gasto",
                "concepto",
                "uuid",
                "descripcion",
                "cantidad",
                "precio_unitario",
                "monto",
                "proveedor",
            ]
            cols_exist = [c for c in cols_det if c in df_det.columns]
            st.dataframe(df_det[cols_exist], use_container_width=True, hide_index=True)
            st.markdown(f"### total solicitud: ${df_det['monto'].sum():,.2f}")

    st.divider()

    # -------------------------
    # acciones jefe ventas (aut/rech)
    # -------------------------
    st.session_state.setdefault("aut_rechazando", False)
    st.session_state.setdefault("aut_rechazo_nonce", 0)

    puede_accion_jefe = is_jefe_ventas and estatus_actual == "enviada"

    if puede_accion_jefe:
        c1, c2 = st.columns(2)

        with c1:
            if st.button("autorizar", use_container_width=True, key="aut_btn_aprobar"):
                detalle_rows = get_detalle_ctrl(int(sel_id)) or []
                reqs = _analizar_requerimientos_dispersion(detalle_rows)

                requiere_gasolina = bool(reqs.get("requiere_gasolina"))
                requiere_prepagados = bool(reqs.get("requiere_prepagados"))

                nuevo_estatus = "autorizada" if (requiere_gasolina or requiere_prepagados) else "dispersion"
                cambiar_estatus_ctrl(int(sel_id), nuevo_estatus, int(usuario.get("id") or 0))

                token = st.session_state.get("microsoft_token")

                mensajes_ok = []
                mensajes_warn = []

                ok_mail, msg_mail = _enviar_autorizacion_correo(
                    solicitud=s,
                    token=token,
                    estatus_final=nuevo_estatus,
                )
                if ok_mail:
                    mensajes_ok.append("correo enviado al vendedor")
                else:
                    mensajes_warn.append(f"no se pudo enviar correo al vendedor: {msg_mail}")

                if requiere_gasolina:
                    ok_conta, msg_conta = _enviar_correo_requerimiento_dispersion(
                        solicitud=s,
                        token=token,
                        nombre_rol="Contabilidad",
                        tipo_requerimiento="dispersión de gasolina",
                    )
                    if ok_conta:
                        mensajes_ok.append("correo enviado a contabilidad")
                    else:
                        mensajes_warn.append(f"no se pudo enviar correo a contabilidad: {msg_conta}")

                if requiere_prepagados:
                    ok_compras, msg_compras = _enviar_correo_requerimiento_dispersion(
                        solicitud=s,
                        token=token,
                        nombre_rol="Compras",
                        tipo_requerimiento="dispersión de prepagados",
                    )
                    if ok_compras:
                        mensajes_ok.append("correo enviado a compras")
                    else:
                        mensajes_warn.append(f"no se pudo enviar correo a compras: {msg_compras}")

                if mensajes_ok:
                    st.success(f"solicitud actualizada a {nuevo_estatus}. " + " | ".join(mensajes_ok))

                if mensajes_warn:
                    st.warning(" | ".join(mensajes_warn))

                st.rerun()

        with c2:
            if st.button("rechazar", use_container_width=True, key="aut_btn_rechazar"):
                st.session_state["aut_rechazando"] = True

        if st.session_state["aut_rechazando"]:
            st.markdown("#### rechazo")
            motivo_key = f"aut_motivo_rechazo_{st.session_state['aut_rechazo_nonce']}"
            motivo = st.text_area(
                "motivo del rechazo",
                key=motivo_key,
                height=120,
                placeholder="describe el motivo…",
            )
            c3, c4 = st.columns(2)

            with c3:
                if st.button("confirmar rechazo", use_container_width=True, key="aut_btn_confirm_rechazo"):
                    if not (motivo or "").strip():
                        st.warning("captura el motivo del rechazo.")
                    else:
                        cambiar_estatus_ctrl(int(sel_id), "rechazada", int(usuario.get("id") or 0))

                        token = st.session_state.get("microsoft_token")
                        ok_mail, msg_mail = _enviar_rechazo_correo(
                            solicitud=s,
                            motivo=motivo,
                            token=token,
                        )


                        if ok_mail:
                            st.success("solicitud rechazada y correo enviado al vendedor.")
                        else:
                            st.warning(f"solicitud rechazada, pero no se pudo enviar correo: {msg_mail}")

                        st.session_state["aut_rechazando"] = False
                        st.session_state["aut_rechazo_nonce"] += 1
                        st.rerun()

            with c4:
                if st.button("cancelar", use_container_width=True, key="aut_btn_cancel_rechazo"):
                    st.session_state["aut_rechazando"] = False
                    st.session_state["aut_rechazo_nonce"] += 1
                    st.rerun()

    # -------------------------
    # acciones contabilidad (dispersión)
    # -------------------------
    puede_accion_conta = is_conta and estatus_actual == "autorizada"
    puede_dispersion = (is_conta or is_compras) and estatus_actual == "autorizada"

    # -------------------------
    # DISPERSIÓN (contabilidad/compras)
    # -------------------------
    if puede_dispersion:
        st.subheader("dispersión")

        # trae flags actuales (necesitas estos ctrl/model abajo)
        flags = get_dispersion_flags_ctrl(int(sel_id)) or {}
        gas_ok = bool(flags.get("disp_gasolina"))
        pre_ok = bool(flags.get("disp_prepagados"))
        reqs = _analizar_requerimientos_dispersion(detalle)
        requiere_gasolina = bool(reqs.get("requiere_gasolina"))
        requiere_prepagados = bool(reqs.get("requiere_prepagados"))

        st.caption(
            f"requiere gasolina: {'sí' if requiere_gasolina else 'no'} | "
            f"requiere otros prepagados: {'sí' if requiere_prepagados else 'no'}"
        )

        c1, c2 = st.columns(2)

        # antes de los checkbox (después de flags/gas_ok/pre_ok)
        key_gas = f"disp_chk_gasolina_{int(sel_id)}"
        key_pre = f"disp_chk_prepagados_{int(sel_id)}"

        with c1:
            gas2 = st.checkbox(
                "dispersión gasolina",
                value=gas_ok,
                disabled=(not (is_admin or is_conta)),
                key=key_gas,
            )

        with c2:
            pre2 = st.checkbox(
                "dispersión prepagados",
                value=pre_ok,
                disabled=(not (is_admin or is_compras)),
                key=key_pre,
            )

        if st.button("guardar dispersión", use_container_width=True, key=f"btn_guardar_disp_{int(sel_id)}"):
            uid = int(usuario.get("id") or 0)
            token = st.session_state.get("microsoft_token")

            concepto_notificado = None

            # solo guarda lo que le toca a cada rol (admin puede ambos)
            if is_admin or is_conta:
                flags_prev = get_dispersion_flags_ctrl(int(sel_id)) or {}
                gas_prev = bool(flags_prev.get("disp_gasolina"))

                set_dispersion_flag_ctrl(int(sel_id), "disp_gasolina", bool(gas2), uid)

                if requiere_gasolina and (not gas_prev) and bool(gas2):
                    concepto_notificado = "gasolina (efecticard)"

            if is_admin or is_compras:
                flags_prev = get_dispersion_flags_ctrl(int(sel_id)) or {}
                pre_prev = bool(flags_prev.get("disp_prepagados"))

                set_dispersion_flag_ctrl(int(sel_id), "disp_prepagados", bool(pre2), uid)

                if requiere_prepagados and (not pre_prev) and bool(pre2):
                    concepto_notificado = "prepagados"

            # re-lee flags desde bd para decidir estatus
            flags2 = get_dispersion_flags_ctrl(int(sel_id)) or {}
            gasf = bool(flags2.get("disp_gasolina"))
            pref = bool(flags2.get("disp_prepagados"))

            ok_gasolina = (not requiere_gasolina) or gasf
            ok_prepagados = (not requiere_prepagados) or pref

            estatus_final = "autorizada"
            if ok_gasolina and ok_prepagados:
                cambiar_estatus_ctrl(int(sel_id), "dispersion", uid)
                estatus_final = "dispersion"

            ok_mail = None
            msg_mail = None

            if concepto_notificado:
                ok_mail, msg_mail = _enviar_dispersion_correo(
                    solicitud=s,
                    token=token,
                    concepto_notificado=concepto_notificado,
                    estatus_final=estatus_final,
                )

            if estatus_final == "dispersion":
                if concepto_notificado:
                    if ok_mail:
                        st.success(
                            f"dispersión de {concepto_notificado} guardada. "
                            "estatus actualizado a dispersion y correo enviado al solicitante."
                        )
                    else:
                        st.warning(
                            f"dispersión de {concepto_notificado} guardada. "
                            f"estatus actualizado a dispersion, pero no se pudo enviar correo: {msg_mail}"
                        )
                else:
                    st.success("dispersión completada. estatus actualizado a dispersion.")
            else:
                faltantes = []
                if requiere_gasolina and not gasf:
                    faltantes.append("gasolina")
                if requiere_prepagados and not pref:
                    faltantes.append("prepagados")

                if concepto_notificado:
                    if ok_mail:
                        st.success(
                            f"dispersión de {concepto_notificado} guardada y correo enviado al solicitante. "
                            + (
                                "aún falta completar: " + ", ".join(faltantes)
                                if faltantes else
                                "la dispersión fue guardada."
                            )
                        )
                    else:
                        st.warning(
                            f"dispersión de {concepto_notificado} guardada, pero no se pudo enviar correo: {msg_mail}. "
                            + (
                                "aún falta completar: " + ", ".join(faltantes)
                                if faltantes else
                                "la dispersión fue guardada."
                            )
                        )
                else:
                    if faltantes:
                        st.success(
                            "dispersión guardada. aún falta completar: "
                            + ", ".join(faltantes)
                        )
                    else:
                        st.success("dispersión guardada.")

            st.rerun()

    if puede_revision_cierre_jefe:
        st.markdown("### revisión de cierre por jefe de ventas")

        c5, c6 = st.columns(2)

        with c5:
            if st.button("✅ aprobar cierre", use_container_width=True, key="aut_btn_aprobar_cierre", type="secondary",):
                cambiar_estatus_ctrl(int(sel_id), "contabilidad", int(usuario.get("id") or 0))

                token = st.session_state.get("microsoft_token")

                mensajes_ok = []
                mensajes_warn = []

                # correo al solicitante
                ok_mail, msg_mail = _enviar_revision_cierre_aprobada_correo(
                    solicitud=s,
                    token=token,
                )

                if ok_mail:
                    mensajes_ok.append("correo enviado al solicitante")
                else:
                    mensajes_warn.append(f"no se pudo enviar correo al solicitante: {msg_mail}")

                # 👇 NUEVO: correo a contabilidad
                ok_conta, msg_conta = _enviar_a_contabilidad_revision_correo(
                    solicitud=s,
                    token=token,
                )

                if ok_conta:
                    mensajes_ok.append("correo enviado a contabilidad")
                else:
                    mensajes_warn.append(f"no se pudo enviar correo a contabilidad: {msg_conta}")

                if mensajes_ok:
                    st.success("cierre aprobado. " + " | ".join(mensajes_ok))

                if mensajes_warn:
                    st.warning(" | ".join(mensajes_warn))

                st.rerun()

        with c6:
            if st.button("🛑 rechazar cierre", use_container_width=True, key="aut_btn_rechazar_cierre", type="primary"):
                st.session_state["aut_revisando_cierre"] = True

        if st.session_state["aut_revisando_cierre"]:
            comentario_key = f"aut_comentario_cierre_{st.session_state['aut_revision_cierre_nonce']}"
            comentario = st.text_area(
                "comentario de rechazo de cierre",
                key=comentario_key,
                height=120,
                placeholder="describe qué debe corregirse…",
            )

            c7, c8 = st.columns(2)

            with c7:
                if st.button("confirmar rechazo de cierre", use_container_width=True, key="aut_btn_confirm_rechazo_cierre"):
                    if not (comentario or "").strip():
                        st.warning("captura el comentario del rechazo.")
                    else:
                        cambiar_estatus_ctrl(int(sel_id), "dispersion", int(usuario.get("id") or 0))

                        token = st.session_state.get("microsoft_token")
                        ok_mail, msg_mail = _enviar_revision_cierre_rechazada_correo(
                            solicitud=s,
                            motivo=comentario,
                            token=token,
                        )

                        if ok_mail:
                            st.success("cierre rechazado y correo enviado al solicitante.")
                        else:
                            st.warning(f"cierre rechazado, pero no se pudo enviar correo: {msg_mail}")

                        st.session_state["aut_revisando_cierre"] = False
                        st.session_state["aut_revision_cierre_nonce"] += 1
                        st.rerun()

            with c8:
                if st.button("cancelar rechazo de cierre", use_container_width=True, key="aut_btn_cancel_rechazo_cierre"):
                    st.session_state["aut_revisando_cierre"] = False
                    st.session_state["aut_revision_cierre_nonce"] += 1
                    st.rerun()

    if (not puede_accion_jefe) and (not puede_revision_cierre_jefe) and (not puede_accion_conta):
        if is_conta and estatus_actual != "autorizada":
            st.info("contabilidad solo puede dispersar solicitudes en estatus autorizada.")
        elif is_jefe_ventas:
            st.info("jefe de ventas solo puede autorizar solicitudes enviadas o revisar solicitudes cerradas.")