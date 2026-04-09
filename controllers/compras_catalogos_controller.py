from models.compras_catalogos_model import (
    get_tipos_compra_model,
    existe_tipo_compra_model,
    crear_tipo_compra_model,
    actualizar_tipo_compra_model,
    cambiar_estatus_tipo_compra_model,
)


def obtener_tipos_compra_ctrl():
    df = get_tipos_compra_model()

    if not df.empty:
        df["estatus"] = df["activo"].apply(lambda x: "Activo" if int(x) == 1 else "Inactivo")

    return df


def crear_tipo_compra_ctrl(nombre, descripcion, activo=1):
    nombre = (nombre or "").strip()
    descripcion = (descripcion or "").strip()

    if not nombre:
        return False, "Debes capturar el nombre del tipo de compra."

    if existe_tipo_compra_model(nombre):
        return False, "Ya existe un tipo de compra con ese nombre."

    crear_tipo_compra_model(nombre, descripcion, activo)
    return True, "Tipo de compra creado correctamente."


def actualizar_tipo_compra_ctrl(id_tipo_compra, nombre, descripcion, activo):
    nombre = (nombre or "").strip()
    descripcion = (descripcion or "").strip()

    if not id_tipo_compra:
        return False, "No se recibió el id del tipo de compra."

    if not nombre:
        return False, "Debes capturar el nombre del tipo de compra."

    if existe_tipo_compra_model(nombre, id_excluir=id_tipo_compra):
        return False, "Ya existe otro tipo de compra con ese nombre."

    actualizar_tipo_compra_model(id_tipo_compra, nombre, descripcion, activo)
    return True, "Tipo de compra actualizado correctamente."


def cambiar_estatus_tipo_compra_ctrl(id_tipo_compra, activo):
    if not id_tipo_compra:
        return False, "No se recibió el id del tipo de compra."

    cambiar_estatus_tipo_compra_model(id_tipo_compra, activo)
    return True, "Estatus actualizado correctamente."