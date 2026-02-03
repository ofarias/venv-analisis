from models.usuario_model import verificar_usuario

def autenticar_usuario(username, password):
    user = verificar_usuario(username, password)
    if user and user.get("estatus") == "Baja":
        return None
    return user