#unidades_controller.py
from models.unidades_model import *

def get_unidades(limit=500, offset=0):
    return obtener_unidades(limit, offset)

def crear_unidad(nombre, id_ant, creador):
    return insertar_unidad(nombre, id_ant, creador)

def cambiar_estatus_unidad(id_unidad, estatus):
    return actualizar_estatus_unidad(id_unidad, estatus)

def get_asignaciones():
    return obtener_asignaciones()

def crear_asignacion(user_id, id_unidad, user_id_alta):
    return asignar_unidad_a_usuario(user_id, id_unidad, user_id_alta)

def cambiar_estatus_asignacion(id_asignacion, status, user_id_baja=None):
    return actualizar_estatus_asignacion(id_asignacion, status, user_id_baja)

def asignar_unidades_a_usuarios(usernames, unidades, creador):
    return insertar_asignacion_multiple(usernames, unidades, creador)

def obtener_asignaciones():
    data = obtener_todas_asignaciones()
    return pd.DataFrame(data)

def eliminar_asignaciones(ids_asignaciones: list[int], usuario_baja: str):
    return eliminar_asignaciones_db(ids_asignaciones, usuario_baja)
