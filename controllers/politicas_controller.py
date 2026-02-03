from models.politicas_model import crear_politica

def registrar_politica(data):
    crear_politica(**data)