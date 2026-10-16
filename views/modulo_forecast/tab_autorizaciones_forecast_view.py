from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd
import streamlit as st

from controllers.forecast_controller import obtener_forecast_detalle_ctrl
from controllers.forecast_autorizacion_controller import (
    cambiar_estatus_forecast_mes_ctrl,
    obtener_forecast_mes_estatus_pendientes_ctrl,
    obtener_forecast_mes_estatus_resueltos_ctrl,
)
from controllers.presupuesto_admin_controller import (
    obtener_roles_usuarios_ids_ctrl,
    obtener_usuario_por_id_ctrl,
    obtener_usuarios_por_ids_ctrl,
)
from utils.deeplink_tokens import get_app_link_cfg, verify_token
from utils.envio_correo import enviar_correo, enviar_correo_sistema


_MESES = {1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
          7: "jul", 8: "ago", 9: "sep", 10: "oct", 11: "nov", 12: "dic"}

_ESTATUS_BADGE = {
    "enviada": "⏳ enviada",
    "autorizada": "✅ autorizada",
    "rechazada": "🔴 rechazada",
}


def _norm_roles_list(values) -> list[str]:
    if not values:
        return []
    if isinstance(values, str):
        values = [values]
    return [str(v).strip().lower() for v in values if str(v or "").strip()]


def _tiene_rol(roles: list[str], *objetivos: str) -> bool:
    roles_set = set(_norm_roles_list(roles))
    objetivos_set = set(_norm_roles_list(objetivos))
    return bool(roles_set.intersection(objetivos_set))


def _puede_autorizar() -> bool:
    usuario = st.session_state.get("usuario") or {}
    return _tiene_rol(
        usuario.get("roles"),
        "jefe de ventas", "supervisor de ventas", "gerente de ventas", "gerente ventas",
        "forecastadmin", "superadmin",
    )


def _enviar_notificacion_vendedor_forecast(
    *, destinatario: str, aprobado: bool, id_version: int, tipo: str, anio: int, mes: int,
    total: float, motivo: Optional[str], token, remitente: str,
) -> tuple[bool, str]:
    if not destinatario:
        return False, "sin correo del vendedor"
    etiqueta_tipo = "venta" if tipo == "venta" else "compra (DP)"
    mes_nombre = _MESES.get(mes, str(mes)).upper()
    verbo = "AUTORIZADO" if aprobado else "RECHAZADO"
    asunto = f"Forecast de {etiqueta_tipo} {mes_nombre} {anio} — {verbo.lower()}"
    motivo_html = f"<p><b>Motivo:</b> {motivo}</p>" if (not aprobado and motivo) else ""
    cuerpo_html = f"""
    <div style="font-family: Arial, sans-serif; font-size: 14px; color: #111;">
        <p>Tu forecast de {etiqueta_tipo} de <b>{mes_nombre} {anio}</b>
        (total: {total:,.2f}) fue
        <b style="color:{'#16a34a' if aprobado else '#dc2626'}">{verbo}</b>.</p>
        {motivo_html}
    </div>
    """
    if not token:
        return enviar_correo_sistema(destinatario=destinatario, asunto=asunto, cuerpo_html=cuerpo_html)
    return enviar_correo(
        destinatario=destinatario, asunto=asunto, cuerpo_html=cuerpo_html,
        token=token, remitente=remitente,
    )


def _total_forecast_mes(id_version: int, tipo: str, mes: int) -> tuple[pd.DataFrame, float, float]:
    """(detalle del mes, total forecast, total presupuesto de referencia)."""
    df = obtener_forecast_detalle_ctrl(id_version=id_version, seccion="KG", tipo=tipo)
    if df is None or df.empty:
        return pd.DataFrame(), 0.0, 0.0
    df_mes = df[pd.to_numeric(df["mes"], errors="coerce") == mes].copy()
    if df_mes.empty:
        return df_mes, 0.0, 0.0
    total = float(pd.to_numeric(df_mes["forecast"], errors="coerce").fillna(0.0).sum())
    presupuesto = float(pd.to_numeric(df_mes.get("presupuesto_valor"), errors="coerce").fillna(0.0).sum())
    return df_mes, total, presupuesto


def _resolver_estatus(
    *, id_version: int, tipo: str, anio: int, mes: int, estatus_nuevo: str,
    usuario_id: int, usuario_nombre: str, usuario_email: str, motivo: Optional[str],
    vendedor_email: str, total: float, token, remitente: str,
) -> None:
    cambiar_estatus_forecast_mes_ctrl(
        id_version=id_version, tipo=tipo, anio=anio, mes=mes,
        estatus_nuevo=estatus_nuevo, usuario_id=usuario_id,
        usuario_nombre=usuario_nombre, usuario_email=usuario_email,
        comentario=motivo,
    )
    _enviar_notificacion_vendedor_forecast(
        destinatario=vendedor_email, aprobado=(estatus_nuevo == "autorizada"),
        id_version=id_version, tipo=tipo, anio=anio, mes=mes, total=total,
        motivo=motivo, token=token, remitente=remitente,
    )


def mostrar_tab_autorizaciones_forecast() -> None:
    if not _puede_autorizar():
        st.info(
            "esta pestaña es para los roles Jefe de Ventas, Supervisor de Ventas, "
            "Gerente de Ventas o SuperAdmin/forecastAdmin."
        )
        return

    usuario = st.session_state.get("usuario") or {}
    tab_pend, tab_res = st.tabs(["⏳ pendientes", "📜 resueltas"])
    with tab_pend:
        sub_venta, sub_compra = st.tabs(["🟢 Venta", "🔵 Compra"])
        with sub_venta:
            _panel_pendientes(usuario, "venta")
        with sub_compra:
            _panel_pendientes(usuario, "compra")
    with tab_res:
        _panel_resueltas(usuario)


def _panel_pendientes(usuario: dict, tipo: str) -> None:
    pendientes = obtener_forecast_mes_estatus_pendientes_ctrl()
    if pendientes is None or pendientes.empty:
        st.info("no hay meses pendientes de autorización.")
        return
    pendientes = pendientes[pendientes["tipo"] == tipo].copy()
    if pendientes.empty:
        st.info(f"no hay meses de {tipo} pendientes de autorización.")
        return

    roles_viewer = set(_norm_roles_list(usuario.get("roles")))
    es_superadmin = bool(roles_viewer & {"superadmin", "forecastadmin"})
    es_gerente = bool(roles_viewer & {"gerente de ventas", "gerente ventas"})
    es_jefe = bool(roles_viewer & {"jefe de ventas", "supervisor de ventas"})

    if not es_superadmin:
        uids = [int(u) for u in pendientes["version_usuario_id"].dropna().unique()]
        roles_por_usuario = {
            uid: set(_norm_roles_list(roles))
            for uid, roles in obtener_roles_usuarios_ids_ctrl(uids).items()
        }

        def _me_corresponde(row) -> bool:
            owner_roles = roles_por_usuario.get(int(row["version_usuario_id"]), set())
            if owner_roles & {"jefe de ventas", "supervisor de ventas"}:
                return es_gerente
            return es_jefe or es_gerente

        pendientes = pendientes[pendientes.apply(_me_corresponde, axis=1)]

    if pendientes.empty:
        st.info("no hay meses pendientes de autorización para tu rol.")
        return

    pendientes = pendientes.sort_values("fecha_actualizacion")
    uids = [int(u) for u in pendientes["version_usuario_id"].dropna().unique()]
    usuarios_por_id = obtener_usuarios_por_ids_ctrl(uids)

    token = st.session_state.get("microsoft_token")
    remitente = str(usuario.get("email") or "").strip()

    for fila in pendientes.to_dict("records"):
        id_version = int(fila["id_version"])
        anio = int(fila["anio"])
        mes = int(fila["mes"])
        vendedor = usuarios_por_id.get(int(fila["version_usuario_id"]), {})
        nombre_vendedor = str(vendedor.get("nombre") or vendedor.get("email") or "usuario desconocido")
        vendedor_email = str(vendedor.get("email") or "").strip()

        with st.expander(f"{nombre_vendedor} — {_MESES[mes].upper()} {anio}"):
            df_mes, total, presupuesto = _total_forecast_mes(id_version, tipo, mes)
            c1, c2 = st.columns(2)
            c1.metric("forecast del mes (kg)", f"{total:,.2f}")
            c2.metric("presupuesto de referencia (kg)", f"{presupuesto:,.2f}")
            if not df_mes.empty:
                st.dataframe(
                    df_mes[["cve_prod", "producto_excel", "forecast"]].rename(columns={
                        "cve_prod": "cve prod", "producto_excel": "producto", "forecast": "forecast (kg)",
                    }),
                    use_container_width=True, hide_index=True,
                    height=min(56 + len(df_mes) * 35, 300),
                )
            else:
                st.info("sin detalle capturado para este mes.")

            motivo = st.text_area("motivo (solo si rechazas)", key=f"fc_aut_motivo_{tipo}_{id_version}_{mes}")
            col_ok, col_no = st.columns(2)
            with col_ok:
                if st.button("✅ autorizar", key=f"fc_aut_ok_{tipo}_{id_version}_{mes}", use_container_width=True):
                    _resolver_estatus(
                        id_version=id_version, tipo=tipo, anio=anio, mes=mes,
                        estatus_nuevo="autorizada", usuario_id=int(usuario.get("id") or 0),
                        usuario_nombre=str(usuario.get("nombre") or ""),
                        usuario_email=str(usuario.get("email") or ""),
                        motivo=None, vendedor_email=vendedor_email, total=total,
                        token=token, remitente=remitente,
                    )
                    st.success("autorizado")
                    st.rerun()
            with col_no:
                if st.button("❌ rechazar", key=f"fc_aut_no_{tipo}_{id_version}_{mes}", use_container_width=True):
                    if not motivo.strip():
                        st.warning("captura el motivo del rechazo.")
                    else:
                        _resolver_estatus(
                            id_version=id_version, tipo=tipo, anio=anio, mes=mes,
                            estatus_nuevo="rechazada", usuario_id=int(usuario.get("id") or 0),
                            usuario_nombre=str(usuario.get("nombre") or ""),
                            usuario_email=str(usuario.get("email") or ""),
                            motivo=motivo.strip(), vendedor_email=vendedor_email, total=total,
                            token=token, remitente=remitente,
                        )
                        st.success("rechazado")
                        st.rerun()


def _panel_resueltas(usuario: dict) -> None:
    usuario_id = int(usuario.get("id") or 0)
    if not usuario_id:
        st.info("no se pudo identificar tu usuario.")
        return

    resueltas = obtener_forecast_mes_estatus_resueltos_ctrl(usuario_id=usuario_id)
    if resueltas is None or resueltas.empty:
        st.info("aún no has autorizado ni rechazado ningún mes.")
        return

    resueltas = resueltas.sort_values("fecha", ascending=False).reset_index(drop=True)
    uids = [int(u) for u in resueltas["version_usuario_id"].dropna().unique()]
    usuarios_por_id = obtener_usuarios_por_ids_ctrl(uids)
    resueltas["vendedor"] = resueltas["version_usuario_id"].apply(
        lambda uid: str(usuarios_por_id.get(int(uid), {}).get("nombre") or "") if pd.notna(uid) else ""
    )
    resueltas["mes_nombre"] = resueltas["mes"].map(_MESES).str.upper()
    resueltas["estatus"] = resueltas["estatus_nuevo"].map(_ESTATUS_BADGE).fillna(resueltas["estatus_nuevo"])

    st.caption(f"{len(resueltas):,} mes(es) que autorizaste o rechazaste")
    cols = ["fecha", "vendedor", "tipo", "anio", "mes_nombre", "estatus", "comentario"]
    encabezados = {
        "fecha": "Fecha", "vendedor": "Vendedor", "tipo": "Tipo", "anio": "Año",
        "mes_nombre": "Mes", "estatus": "Estatus", "comentario": "Comentario",
    }
    df_show = resueltas[[c for c in cols if c in resueltas.columns]].rename(columns=encabezados)
    st.dataframe(df_show, use_container_width=True, hide_index=True, height=min(56 + len(df_show) * 35, 520))


def mostrar_autorizacion_forecast_link() -> None:
    """Página independiente (sin sesión/login) para el link de correo
    ?fc_v=&fc_tipo=&fc_anio=&fc_mes=&fc_action=approve|reject&fc_t= generado
    por `_enviar_notificacion_autorizador_forecast` — calco de
    `mostrar_autorizacion_presupuesto_link`."""
    st.subheader("autorización de forecast")

    qp = st.query_params
    fc_v = (qp.get("fc_v") or "").strip()
    fc_tipo = (qp.get("fc_tipo") or "").strip().lower()
    fc_anio = (qp.get("fc_anio") or "").strip()
    fc_mes = (qp.get("fc_mes") or "").strip()
    fc_action = (qp.get("fc_action") or "").strip().lower()
    fc_t = (qp.get("fc_t") or "").strip()

    if not (fc_v and fc_tipo and fc_anio and fc_mes and fc_t):
        st.error("link inválido.")
        return

    try:
        id_version, anio, mes = int(fc_v), int(fc_anio), int(fc_mes)
    except Exception:
        st.error("link inválido.")
        return

    if fc_tipo not in ("venta", "compra"):
        st.error("link inválido.")
        return

    _, secret = get_app_link_cfg()
    if not secret:
        st.error("falta APP_LINK_SECRET en secrets.toml")
        return

    payload = verify_token(fc_t, secret)
    if not payload:
        st.error("link inválido o expirado.")
        return

    exp = int(payload.get("exp") or 0)
    if exp <= 0 or int(datetime.utcnow().timestamp()) > exp:
        st.error("link expirado.")
        return

    if (
        int(payload.get("fc_v") or 0) != id_version
        or str(payload.get("fc_tipo") or "") != fc_tipo
        or int(payload.get("fc_anio") or 0) != anio
        or int(payload.get("fc_mes") or 0) != mes
    ):
        st.error("link inválido.")
        return

    if fc_action not in ("approve", "reject"):
        st.error("link inválido.")
        return

    autoriza_rol = str(payload.get("autoriza_rol") or "").strip()
    actor_nombre = autoriza_rol or "Autorización externa"

    pendientes = obtener_forecast_mes_estatus_pendientes_ctrl()
    fila = None
    if pendientes is not None and not pendientes.empty:
        m = (
            (pendientes["id_version"].astype(int) == id_version)
            & (pendientes["tipo"] == fc_tipo)
            & (pendientes["anio"].astype(int) == anio)
            & (pendientes["mes"].astype(int) == mes)
        )
        if m.any():
            fila = pendientes[m].iloc[0].to_dict()

    if fila is None:
        st.info("ya no está pendiente de autorización — puede que ya se haya resuelto.")
        return

    vendedor = obtener_usuario_por_id_ctrl(int(fila.get("version_usuario_id") or 0)) or {}
    vendedor_email = str(vendedor.get("email") or "").strip()
    _, total, _presupuesto = _total_forecast_mes(id_version, fc_tipo, mes)

    etiqueta_tipo = "venta" if fc_tipo == "venta" else "compra (DP)"
    st.info(f"forecast de {etiqueta_tipo} — {_MESES.get(mes, mes).upper()} {anio} (versión {id_version})")

    if fc_action == "approve":
        _resolver_estatus(
            id_version=id_version, tipo=fc_tipo, anio=anio, mes=mes,
            estatus_nuevo="autorizada", usuario_id=0, usuario_nombre=actor_nombre,
            usuario_email="", motivo=None, vendedor_email=vendedor_email, total=total,
            token=None, remitente="",
        )
        st.success("autorizado correctamente.")
        return

    motivo = st.text_area("motivo del rechazo", key=f"fc_link_motivo_{id_version}_{fc_tipo}_{mes}")
    if st.button("confirmar rechazo", type="primary", key=f"fc_link_btn_rechazo_{id_version}_{fc_tipo}_{mes}"):
        if not motivo.strip():
            st.warning("captura el motivo del rechazo.")
        else:
            _resolver_estatus(
                id_version=id_version, tipo=fc_tipo, anio=anio, mes=mes,
                estatus_nuevo="rechazada", usuario_id=0, usuario_nombre=actor_nombre,
                usuario_email="", motivo=motivo.strip(), vendedor_email=vendedor_email, total=total,
                token=None, remitente="",
            )
            st.success("rechazado correctamente.")
