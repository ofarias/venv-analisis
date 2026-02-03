
from models.usuario_model import crear_usuario, obtener_usuarios
from logs.logger import registrar_log
import pandas as pd 

def procesar_creacion_usuario(username, nombre, email, password, rol):
    ok, mensaje = crear_usuario(username, nombre, email, password, rol)
    if ok:
        registrar_log("admin", "Crear usuario", username)
    return ok, mensaje


def get_usuarios(limit=500, offset=0):
    data = obtener_usuarios()
    return pd.DataFrame(data)
