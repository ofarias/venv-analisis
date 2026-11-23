import streamlit as st
import pandas as pd

from models.compras_subtipos_model import (
    obtener_subtipos_model,
    existe_subtipo_model,
    crear_subtipo_model,
    actualizar_subtipo_model,
    cambiar_estatus_subtipo_model,
    eliminar_subtipo_model,
    obtener_puestos_permitidos_subtipo_model,
    guardar_puestos_permitidos_subtipo_model,
    obtener_subtipos_activos_para_usuario_model,
)


@st.cache_data(ttl=120, show_spinner=False)
def obtener_subtipos_ctrl(id_tipo_compra: int | None = None) -> pd.DataFrame:
    return obtener_subtipos_model(id_tipo_compra)


def crear_subtipo_ctrl(id_tipo_compra: int, nombre: str, descripcion: str | None, puesto_ids: list[int] | None = None) -> tuple[bool, str]:
    nombre = str(nombre or "").strip()
    if not id_tipo_compra:
        return False, "falta el tipo de compra."
    if not nombre:
        return False, "el nombre del subtipo es obligatorio."
    if existe_subtipo_model(id_tipo_compra, nombre):
        return False, f"ya existe un subtipo llamado '{nombre}' para este tipo de compra."

    id_subtipo = crear_subtipo_model(id_tipo_compra, nombre, descripcion)
    if not id_subtipo:
        return False, "no se pudo crear el subtipo."
    guardar_puestos_permitidos_subtipo_model(id_subtipo, [int(p) for p in (puesto_ids or [])])
    obtener_subtipos_ctrl.clear()
    return True, f"subtipo '{nombre}' creado."


def actualizar_subtipo_ctrl(
    id_subtipo: int, id_tipo_compra: int, nombre: str, descripcion: str | None,
    puesto_ids: list[int] | None = None,
) -> tuple[bool, str]:
    nombre = str(nombre or "").strip()
    if not nombre:
        return False, "el nombre del subtipo es obligatorio."
    if existe_subtipo_model(id_tipo_compra, nombre, id_excluir=id_subtipo):
        return False, f"ya existe otro subtipo llamado '{nombre}' para este tipo de compra."

    ok = actualizar_subtipo_model(id_subtipo, nombre, descripcion)
    if ok:
        guardar_puestos_permitidos_subtipo_model(id_subtipo, [int(p) for p in (puesto_ids or [])])
    obtener_subtipos_ctrl.clear()
    return (True, "subtipo actualizado.") if ok else (False, "no se pudo actualizar el subtipo.")


def cambiar_estatus_subtipo_ctrl(id_subtipo: int, activo: bool) -> bool:
    ok = cambiar_estatus_subtipo_model(id_subtipo, 1 if activo else 0)
    obtener_subtipos_ctrl.clear()
    return ok


def eliminar_subtipo_ctrl(id_subtipo: int) -> tuple[bool, str]:
    ok, mensaje = eliminar_subtipo_model(id_subtipo)
    obtener_subtipos_ctrl.clear()
    return ok, mensaje


def obtener_puestos_permitidos_subtipo_ctrl(id_subtipo: int) -> list[int]:
    return obtener_puestos_permitidos_subtipo_model(id_subtipo)


def obtener_subtipos_activos_para_usuario_ctrl(id_tipo_compra: int, usuario_id: int | None) -> list[dict]:
    return obtener_subtipos_activos_para_usuario_model(id_tipo_compra, usuario_id)
