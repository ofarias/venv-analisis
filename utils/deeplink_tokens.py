from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta

import streamlit as st

"""Firma/verifica los tokens usados en los links de acción por correo
(autorizar/rechazar desde el correo sin tener que entrar a buscar el
registro en la app) — mismo esquema HMAC que ya usa el módulo de
Solicitudes (views/modulo_solicitudes/tab_solicitud_gastos_view.py),
factorizado aquí para no duplicar la firma/verificación en cada módulo
nuevo que quiera links de este tipo (presupuesto de ventas/compras, etc.)."""


def get_app_link_cfg() -> tuple[str, str]:
    base_url = (st.secrets.get("APP_BASE_URL", "") or "").strip()
    secret = (st.secrets.get("APP_LINK_SECRET", "") or "").strip()

    if not base_url:
        base_url = (os.getenv("APP_BASE_URL") or "").strip()
    if not secret:
        secret = (os.getenv("APP_LINK_SECRET") or "").strip()

    return base_url.rstrip("/"), secret


def sign_payload(payload: dict, secret: str) -> str:
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).digest()
    return (
        base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")
        + "."
        + base64.urlsafe_b64encode(sig).decode("utf-8").rstrip("=")
    )


def verify_token(token: str, secret: str) -> dict | None:
    try:
        raw_b64, sig_b64 = token.split(".", 1)

        raw = base64.urlsafe_b64decode(raw_b64 + ("=" * (-len(raw_b64) % 4)))
        sig = base64.urlsafe_b64decode(sig_b64 + ("=" * (-len(sig_b64) % 4)))

        expected = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).digest()
        if not hmac.compare_digest(sig, expected):
            return None

        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


def token_exp(hours: int = 72) -> int:
    return int((datetime.utcnow() + timedelta(hours=hours)).timestamp())


def build_links_autorizacion_presupuesto(*, id_carga: int, tipo: str, nombre_rol: str) -> dict:
    """Links firmados (HMAC, expiran en 72h) para autorizar/rechazar desde el
    correo un presupuesto de ventas o compras (?pv_carga=&pv_tipo=&pv_t=&pv_action=),
    igual que en Solicitudes — apuntan a la carga+tipo completos, no a una
    línea individual, porque esa pantalla autoriza en lote."""
    base_url, secret = get_app_link_cfg()
    if not base_url or not secret:
        return {"ok": False, "error": "falta APP_BASE_URL o APP_LINK_SECRET en secrets.toml"}

    payload = {
        "pv_carga": int(id_carga),
        "pv_tipo": tipo,
        "exp": token_exp(72),
        "autoriza_rol": nombre_rol,
    }
    t = sign_payload(payload, secret)
    qs = f"pv_carga={int(id_carga)}&pv_tipo={tipo}&pv_t={t}"
    return {
        "ok": True,
        "approve": f"{base_url}/?{qs}&pv_action=approve",
        "reject": f"{base_url}/?{qs}&pv_action=reject",
    }


def build_links_autorizacion_forecast(
    *, id_version: int, tipo: str, anio: int, mes: int, nombre_rol: str,
) -> dict:
    """Links firmados (HMAC, expiran en 72h) para autorizar/rechazar desde el
    correo el forecast mensual (venta o compra) de una versión
    (?fc_v=&fc_tipo=&fc_anio=&fc_mes=&fc_t=&fc_action=) — mismo esquema que
    build_links_autorizacion_presupuesto, a nivel (id_version, tipo, anio,
    mes) en vez de (id_carga, tipo)."""
    base_url, secret = get_app_link_cfg()
    if not base_url or not secret:
        return {"ok": False, "error": "falta APP_BASE_URL o APP_LINK_SECRET en secrets.toml"}

    payload = {
        "fc_v": int(id_version),
        "fc_tipo": tipo,
        "fc_anio": int(anio),
        "fc_mes": int(mes),
        "exp": token_exp(72),
        "autoriza_rol": nombre_rol,
    }
    t = sign_payload(payload, secret)
    qs = f"fc_v={int(id_version)}&fc_tipo={tipo}&fc_anio={int(anio)}&fc_mes={int(mes)}&fc_t={t}"
    return {
        "ok": True,
        "approve": f"{base_url}/?{qs}&fc_action=approve",
        "reject": f"{base_url}/?{qs}&fc_action=reject",
    }
