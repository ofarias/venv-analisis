from __future__ import annotations

import pandas as pd
import streamlit as st

from models.presupuesto_admin_model import (
    obtener_clientes_presupuesto_model,
    obtener_presupuesto_ventas_compras_model,
    obtener_roles_usuario_id_model,
    obtener_roles_usuarios_ids_model,
    obtener_usuario_por_id_model,
    obtener_usuarios_por_ids_model,
    obtener_usuarios_presupuesto_model,
)


@st.cache_data(ttl=300, show_spinner=False)
def obtener_usuarios_presupuesto_ctrl() -> pd.DataFrame:
    return obtener_usuarios_presupuesto_model()


@st.cache_data(ttl=300, show_spinner=False)
def obtener_clientes_presupuesto_ctrl() -> list[str]:
    return obtener_clientes_presupuesto_model()


def obtener_roles_usuario_id_ctrl(usuario_id: int) -> list[str]:
    return obtener_roles_usuario_id_model(usuario_id)


def obtener_roles_usuarios_ids_ctrl(usuario_ids: list[int]) -> dict[int, list[str]]:
    return obtener_roles_usuarios_ids_model(usuario_ids)


def obtener_usuario_por_id_ctrl(usuario_id: int) -> dict | None:
    return obtener_usuario_por_id_model(usuario_id)


def obtener_usuarios_por_ids_ctrl(usuario_ids: list[int]) -> dict[int, dict]:
    return obtener_usuarios_por_ids_model(usuario_ids)


def obtener_presupuesto_ventas_compras_ctrl(
    anio: int | None = None,
    usuario_id: int | list[int] | None = None,
    cve_prod: str | list[str] | None = None,
    tipo: str | list[str] | None = None,
    estatus_autorizacion: str | list[str] | None = None,
    cliente: str | list[str] | None = None,
    limit: int = 50000,
) -> pd.DataFrame:
    return obtener_presupuesto_ventas_compras_model(
        anio=anio,
        usuario_id=usuario_id,
        cve_prod=cve_prod,
        tipo=tipo,
        estatus_autorizacion=estatus_autorizacion,
        cliente=cliente,
        limit=limit,
    )
