from __future__ import annotations

import pandas as pd

from models.presupuesto_admin_model import (
    obtener_presupuesto_ventas_compras_model,
    obtener_roles_usuario_id_model,
    obtener_usuario_por_id_model,
    obtener_usuarios_presupuesto_model,
)


def obtener_usuarios_presupuesto_ctrl() -> pd.DataFrame:
    return obtener_usuarios_presupuesto_model()


def obtener_roles_usuario_id_ctrl(usuario_id: int) -> list[str]:
    return obtener_roles_usuario_id_model(usuario_id)


def obtener_usuario_por_id_ctrl(usuario_id: int) -> dict | None:
    return obtener_usuario_por_id_model(usuario_id)


def obtener_presupuesto_ventas_compras_ctrl(
    anio: int | None = None,
    usuario_id: int | None = None,
    cve_prod: str | None = None,
    tipo: str | None = None,
    estatus_autorizacion: str | None = None,
    limit: int = 50000,
) -> pd.DataFrame:
    return obtener_presupuesto_ventas_compras_model(
        anio=anio,
        usuario_id=usuario_id,
        cve_prod=cve_prod,
        tipo=tipo,
        estatus_autorizacion=estatus_autorizacion,
        limit=limit,
    )
