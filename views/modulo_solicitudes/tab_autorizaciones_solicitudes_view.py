from __future__ import annotations

import streamlit as st
import pandas as pd
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