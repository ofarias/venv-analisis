from __future__ import annotations

import streamlit as st
import pandas as pd

from controllers.solicitudes_controller import (
    listar_solicitudes_ctrl,
    get_solicitud_ctrl,
    cambiar_estatus_ctrl,
    get_detalle_ctrl,
    get_usuarios_activos_ctrl,
)

from utils.envio_correo import enviar_correo


def _get_email_vendedor(solicitud: dict) -> str | None:
    """
    intenta obtener correo del vendedor (empleado) con catálogo de usuarios activos.
    adapta llaves según tu estructura real.
    """
    empleado_id = int(solicitud.get("empleado_id") or 0)
    if not empleado_id:
        return None

    users = get_usuarios_activos_ctrl() or []
    for u in users:
        if int(u.get("id") or 0) == empleado_id:
            # intenta varias llaves típicas
            return (
                (u.get("email") or "").strip()
                or (u.get("correo") or "").strip()
                or (u.get("username") or "").strip()  # si username es email
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


ESTATUS_OPTS = ["todas", "captura", "enviada", "autorizada", "rechazada", "cancelada", "cerrada"]

def _estatus_color_html(e: str) -> str:
    e = (e or "").strip().lower()

    colors = {
        "captura": "#f4c542",
        "enviada": "#3498db",
        "autorizada": "#2ecc71",
        "rechazada": "#e74c3c",
        "cancelada": "#7f8c8d",
        "cerrada": "#8e44ad",
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
    st.subheader("autorizaciones de solicitudes (todas)")

    usuario = _get_usuario_actual()
    roles = [str(x).strip().lower() for x in (usuario.get("roles", []) or [])]

    is_admin = "admin" in roles
    is_jefe_ventas = "jefe de ventas" in roles
    is_conta = "contabilidad" in roles

    # seguridad: si no tiene rol, ni muestres nada
    if not (is_admin or is_jefe_ventas or is_conta):
        st.info("sin acceso")
        return

    # filtros rápidos
    st.caption("filtros")
    c1, c2, c3, c4 = st.columns([2, 2, 2, 2])

    with c1:
        folio_like = st.text_input("folio contiene", key="aut_folio_like")
    with c2:
        estatus = st.selectbox("estatus", options=ESTATUS_OPTS, index=0, key="aut_estatus")
    with c3:
        anio = st.number_input("año", min_value=2020, max_value=2100, value=pd.Timestamp.now().year, step=1, key="aut_anio")
    with c4:
        limit = st.number_input("límite", min_value=50, max_value=2000, value=300, step=50, key="aut_limit")

    # traer solicitudes de TODOS: empleado_id=None
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

    # vista rápida
    # muestra lo importante (ajusta columnas a tu df real)
    cols_show = [c for c in ["id","folio","estatus","empleado_nombre","clientes","ciudades","fecha_inicio","fecha_fin","created_at","fecha_creacion"] if c in df.columns]
    df_show = df[cols_show] if cols_show else df

    def _row_style(row):
        e = str(row.get("estatus") or "").strip().lower()
        bg = {
            "captura":   "#fff3cd",
            "enviada":   "#dbeafe",
            "autorizada":"#dcfce7",
            "rechazada": "#fee2e2",
            "cancelada": "#e5e7eb",
            "cerrada":   "#ede9fe",
        }.get(e, "")

        # pinta toda la fila
        return [f"background-color: {bg};" for _ in row.index]

    try:
        st.dataframe(
            df_show.style.apply(_row_style, axis=1),
            use_container_width=True,
            hide_index=True,
        )
    except Exception:
        # fallback si el Styler falla por versión
        st.dataframe(df_show, use_container_width=True, hide_index=True)

    st.divider()
    st.caption("acción sobre solicitud")

    # seleccionar id a operar
    sel_id = st.number_input("id solicitud", min_value=0, value=int(st.session_state.get("aut_selected_id") or 0), step=1, key="aut_selected_id")

    if not sel_id:
        st.info("captura un id para ver/autorizar")
        return

    s = get_solicitud_ctrl(int(sel_id))

    if not s:
        st.warning("no existe esa solicitud")
        return

    estatus_actual = str(s.get("estatus") or "").strip().lower()

    # -------------------------
    # CABECERA
    # -------------------------

    st.markdown("### cabecera")

    st.markdown(
        f"""
        <div style="line-height:1.8">
            <b>folio:</b> {s.get('folio','')}<br>
            <b>empleado:</b> {s.get('empleado_nombre','')}<br>
            <b>clientes:</b> {s.get('clientes','')}<br>
            <b>ciudades:</b> {s.get('ciudades','')}<br>
            <b>fecha inicio:</b> {s.get('fecha_inicio','')}<br>
            <b>fecha fin:</b> {s.get('fecha_fin','')}<br>
            <b>estatus:</b> {_estatus_color_html(estatus_actual)}
        </div>
        """,
        unsafe_allow_html=True
    )

    # -------------------------
    # DETALLE
    # -------------------------

    st.markdown("### detalle de gastos")

    detalle = get_detalle_ctrl(int(sel_id)) or []

    if not detalle:
        st.info("sin detalle")
    else:
        df_det = pd.DataFrame(detalle)

        # regla monto: xml o estimado
        def _monto(r):
            total_xml = float(r.get("total_xml") or 0)
            if total_xml > 0:
                return total_xml
            return float(r.get("cantidad") or 0) * float(r.get("precio_unitario") or 0)

        df_det["monto"] = df_det.apply(_monto, axis=1)

        cols_show = [
            "fecha_gasto",
            "concepto",
            "uuid",
            "descripcion",
            "cantidad",
            "precio_unitario",
            "monto",
            "proveedor",
        ]

        cols_exist = [c for c in cols_show if c in df_det.columns]

        st.dataframe(
            df_det[cols_exist],
            use_container_width=True,
            hide_index=True
        )

        st.markdown(
            f"### total solicitud: ${df_det['monto'].sum():,.2f}"
        )

    # permisos de acción (para iniciar)
    
    st.session_state.setdefault("aut_rechazando", False)
    st.session_state.setdefault("aut_rechazo_nonce", 0)  # para resetear el textarea

    is_jefe_ventas = "jefe de ventas" in roles
    estatus_actual = str(s.get("estatus") or "").strip().lower()
    puede_accion = is_jefe_ventas and estatus_actual == "enviada"

    st.divider()

    if puede_accion:
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
            # paso 1: activar modo rechazo
            if st.button("rechazar", use_container_width=True, key="aut_btn_rechazar"):
                st.session_state["aut_rechazando"] = True

        # panel de rechazo (paso 2: motivo + confirmar)
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
                        # 1) cambia estatus
                        cambiar_estatus_ctrl(int(sel_id), "rechazada", int(usuario.get("id") or 0))

                        # 2) envía correo al vendedor
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

                        # 3) limpia ui
                        st.session_state["aut_rechazando"] = False
                        st.session_state["aut_rechazo_nonce"] += 1  # reset motivo textarea
                        st.rerun()

            with c4:
                if st.button("cancelar", use_container_width=True, key="aut_btn_cancel_rechazo"):
                    st.session_state["aut_rechazando"] = False
                    st.session_state["aut_rechazo_nonce"] += 1  # reset motivo textarea
                    st.rerun()

    else:
        st.info("solo jefe ventas puede autorizar/rechazar solicitudes enviadas.")

    