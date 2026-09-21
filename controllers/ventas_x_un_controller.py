# controllers/ventas_x_un_controller.py
from __future__ import annotations

from datetime import date
from typing import Optional

import pandas as pd

from controllers.presupuesto_ventas_controller import obtener_vendedores_sae_presupuesto_ventas_ctrl
from models.ventas_x_un_model import obtener_ventas_x_un_model


def obtener_vendedores_ventas_x_un_ctrl() -> pd.DataFrame:
    return obtener_vendedores_sae_presupuesto_ventas_ctrl()


def resolver_cve_vend_por_correo_ctrl(correo: str) -> list[str]:
    """Encuentra el/los CVE_VEND de SAE (VEND01) cuyo correo (CORREOE)
    coincide con el correo del usuario logueado en la app — se usa para
    restringir al rol "ventas" a ver solo sus propias ventas, ya que los
    usuarios de esta app no tienen un cve_vend asignado directamente en la
    base de datos. Devuelve una lista (no un solo valor) porque en VEND01
    hay vendedores con más de un CVE_VEND dado de alta con el mismo correo
    (ej. "ROGELIO CURIEL" en los códigos 1 y 4) — restringir a uno solo
    dejaría fuera parte de sus ventas reales."""
    correo = (correo or "").strip().lower()
    if not correo:
        return []

    df = obtener_vendedores_sae_presupuesto_ventas_ctrl()
    if df is None or df.empty or "correoe" not in df.columns:
        return []

    match = df[df["correoe"].astype(str).str.strip().str.lower() == correo]
    return [str(v).strip() for v in match["cve_vend"].tolist()]


def obtener_ventas_x_un_ctrl(
    fecha_desde: date,
    fecha_hasta: date,
    cve_vend: Optional[str | list[str]] = None,
) -> pd.DataFrame:
    return obtener_ventas_x_un_model(
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        cve_vend=cve_vend,
    )
