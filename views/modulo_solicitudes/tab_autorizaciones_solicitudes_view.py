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
    # nuevo (contabilidad)
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


def _consume_deeplink():
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


def _enviar_rechazo_correo(*, solicitud: dict, motivo: str, token):
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
    )


def _enviar_autorizacion_correo(*, solicitud: dict, token):
    folio = str(solicitud.get("folio") or "").strip()
    vendedor_nombre = str(solicitud.get("empleado_nombre") or "").strip()

    destinatario = _get_email_vendedor(solicitud)
    if not destinatario:
        return False, "no se encontró correo del vendedor (empleado)."

    asunto = f"solicitud de gastos autorizada {folio}".strip()

    cuerpo_html = f"""
    <div style="font-family:arial,sans-serif;font-size:14px;line-height:1.4">
      <p>tu solicitud de gastos fue autorizada.</p>
      <p>
        <b>folio:</b> {folio}<br>
        <b>vendedor:</b> {vendedor_nombre}<br>
      </p>
      <p>puedes continuar con el proceso correspondiente.</p>
    </div>
    """

    return enviar_correo(
        destinatario=destinatario,
        asunto=asunto,
        cuerpo_html=cuerpo_html,
        token=token,
    )


ESTATUS_OPTS = ["todas", "captura", "enviada", "autorizada", "rechazada", "cancelada", "cerrada", "dispersion"]


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
        # contabilidad: por defecto ver autorizadas (para dispersar)
        default_estatus_idx = 3 if is_conta else 0
        estatus = st.selectbox("estatus", options=ESTATUS_OPTS, index=default_estatus_idx, key="aut_estatus")
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

    estatus_param = "" if estatus == "todas" else estatus

    rows = listar_solicitudes_ctrl(
        folio_like=folio_like,
        estatus=estatus_param,
        anio=int(anio) if anio else None,
        empleado_id=None,
        limit=int(limit),
    ) or []

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
                    cambiar_estatus_ctrl(int(sel_id), "autorizada", int(usuario.get("id") or 0))

                    token = st.session_state.get("microsoft_token")
                    ok_mail, msg_mail = _enviar_autorizacion_correo(solicitud=s, token=token)

                    if ok_mail:
                        st.success("solicitud autorizada y correo enviado al vendedor.")
                    else:
                        st.warning(f"solicitud autorizada, pero no se pudo enviar correo: {msg_mail}")

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
                cambiar_estatus_ctrl(int(sel_id), "autorizada", int(usuario.get("id") or 0))

                token = st.session_state.get("microsoft_token")
                ok_mail, msg_mail = _enviar_autorizacion_correo(solicitud=s, token=token)

                if ok_mail:
                    st.success("solicitud autorizada y correo enviado al vendedor.")
                else:
                    st.warning(f"solicitud autorizada, pero no se pudo enviar correo: {msg_mail}")

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

            # solo guarda lo que le toca a cada rol (admin puede ambos)
            if is_admin or is_conta:
                set_dispersion_flag_ctrl(int(sel_id), "disp_gasolina", bool(gas2), uid)

            if is_admin or is_compras:
                set_dispersion_flag_ctrl(int(sel_id), "disp_prepagados", bool(pre2), uid)

            # re-lee flags desde bd para decidir estatus
            flags2 = get_dispersion_flags_ctrl(int(sel_id)) or {}
            gasf = bool(flags2.get("disp_gasolina"))
            pref = bool(flags2.get("disp_prepagados"))

            if gasf and pref:
                cambiar_estatus_ctrl(int(sel_id), "dispersion", uid)
                st.success("dispersión completada. estatus actualizado a dispersada.")
            else:
                st.success("dispersión guardada. aún falta completar el otro paso.")

            st.rerun()

    if (not puede_accion_jefe) and (not puede_accion_conta):
        if is_conta and estatus_actual != "autorizada":
            st.info("contabilidad solo puede dispersar solicitudes en estatus autorizada.")
        elif is_jefe_ventas:
            st.info("solo jefe ventas puede autorizar/rechazar solicitudes enviadas.")