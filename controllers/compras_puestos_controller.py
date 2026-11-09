import streamlit as st
import pandas as pd

from models.compras_puestos_model import (
    obtener_puestos_model,
    existe_puesto_model,
    crear_puesto_model,
    actualizar_puesto_model,
    cambiar_estatus_puesto_model,
    obtener_usuarios_de_puesto_model,
    obtener_puestos_de_usuario_model,
    asignar_usuarios_puesto_model,
    obtener_correos_de_puesto_model,
)


@st.cache_data(ttl=120, show_spinner=False)
def obtener_puestos_ctrl() -> pd.DataFrame:
    return obtener_puestos_model()


def crear_puesto_ctrl(nombre: str, descripcion: str | None) -> tuple[bool, str]:
    nombre = str(nombre or "").strip()
    if not nombre:
        return False, "el nombre del puesto es obligatorio"
    if existe_puesto_model(nombre):
        return False, f"ya existe un puesto llamado '{nombre}'"
    id_puesto = crear_puesto_model(nombre, descripcion)
    obtener_puestos_ctrl.clear()
    return (True, f"puesto '{nombre}' creado") if id_puesto else (False, "no se pudo crear el puesto")


def actualizar_puesto_ctrl(id_puesto: int, nombre: str, descripcion: str | None) -> tuple[bool, str]:
    nombre = str(nombre or "").strip()
    if not nombre:
        return False, "el nombre del puesto es obligatorio"
    if existe_puesto_model(nombre, id_excluir=id_puesto):
        return False, f"ya existe otro puesto llamado '{nombre}'"
    ok = actualizar_puesto_model(id_puesto, nombre, descripcion)
    obtener_puestos_ctrl.clear()
    return (True, "puesto actualizado") if ok else (False, "no se pudo actualizar el puesto")


def cambiar_estatus_puesto_ctrl(id_puesto: int, activo: bool) -> bool:
    ok = cambiar_estatus_puesto_model(id_puesto, 1 if activo else 0)
    obtener_puestos_ctrl.clear()
    return ok


def obtener_usuarios_de_puesto_ctrl(id_puesto: int) -> list[int]:
    return obtener_usuarios_de_puesto_model(id_puesto)


def obtener_puestos_de_usuario_ctrl(usuario_id: int) -> list[int]:
    return obtener_puestos_de_usuario_model(usuario_id)


def asignar_usuarios_puesto_ctrl(id_puesto: int, usuario_ids: list[int]) -> bool:
    ok = asignar_usuarios_puesto_model(id_puesto, usuario_ids)
    obtener_puestos_ctrl.clear()
    return ok


def obtener_correos_de_puesto_ctrl(id_puesto: int) -> list[str]:
    return obtener_correos_de_puesto_model(id_puesto)


def usuario_pertenece_a_puesto_ctrl(usuario_id: int, id_puesto: int) -> bool:
    return int(id_puesto) in obtener_puestos_de_usuario_ctrl(int(usuario_id))
