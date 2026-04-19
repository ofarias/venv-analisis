from models.compras_catalogos_adicionales_model import (
    get_departamentos_model,
    existe_departamento_model,
    crear_departamento_model,
    actualizar_departamento_model,
    cambiar_estatus_departamento_model,
    get_formas_pago_model,
    existe_forma_pago_model,
    crear_forma_pago_model,
    actualizar_forma_pago_model,
    cambiar_estatus_forma_pago_model,
)


# -------------------------
# departamentos
# -------------------------
def obtener_departamentos_ctrl():
    df = get_departamentos_model()

    if not df.empty:
        df["estatus"] = df["activo"].apply(lambda x: "Activo" if int(x) == 1 else "Inactivo")

    return df


def crear_departamento_ctrl(nombre, descripcion, activo=1):
    nombre = (nombre or "").strip()
    descripcion = (descripcion or "").strip()

    if not nombre:
        return False, "debes capturar el nombre del departamento."

    if existe_departamento_model(nombre):
        return False, "ya existe un departamento con ese nombre."

    crear_departamento_model(nombre, descripcion, activo)
    return True, "departamento creado correctamente."


def actualizar_departamento_ctrl(id_departamento, nombre, descripcion, activo):
    nombre = (nombre or "").strip()
    descripcion = (descripcion or "").strip()

    if not id_departamento:
        return False, "no se recibió el id del departamento."

    if not nombre:
        return False, "debes capturar el nombre del departamento."

    if existe_departamento_model(nombre, id_excluir=id_departamento):
        return False, "ya existe otro departamento con ese nombre."

    actualizar_departamento_model(id_departamento, nombre, descripcion, activo)
    return True, "departamento actualizado correctamente."


def cambiar_estatus_departamento_ctrl(id_departamento, activo):
    if not id_departamento:
        return False, "no se recibió el id del departamento."

    cambiar_estatus_departamento_model(id_departamento, activo)
    return True, "estatus actualizado correctamente."


# -------------------------
# formas de pago
# -------------------------
def obtener_formas_pago_ctrl():
    df = get_formas_pago_model()

    if not df.empty:
        df["estatus"] = df["activo"].apply(lambda x: "Activo" if int(x) == 1 else "Inactivo")

    return df


def crear_forma_pago_ctrl(nombre, descripcion, activo=1):
    nombre = (nombre or "").strip()
    descripcion = (descripcion or "").strip()

    if not nombre:
        return False, "debes capturar el nombre de la forma de pago."

    if existe_forma_pago_model(nombre):
        return False, "ya existe una forma de pago con ese nombre."

    crear_forma_pago_model(nombre, descripcion, activo)
    return True, "forma de pago creada correctamente."


def actualizar_forma_pago_ctrl(id_forma_pago, nombre, descripcion, activo):
    nombre = (nombre or "").strip()
    descripcion = (descripcion or "").strip()

    if not id_forma_pago:
        return False, "no se recibió el id de la forma de pago."

    if not nombre:
        return False, "debes capturar el nombre de la forma de pago."

    if existe_forma_pago_model(nombre, id_excluir=id_forma_pago):
        return False, "ya existe otra forma de pago con ese nombre."

    actualizar_forma_pago_model(id_forma_pago, nombre, descripcion, activo)
    return True, "forma de pago actualizada correctamente."


def cambiar_estatus_forma_pago_ctrl(id_forma_pago, activo):
    if not id_forma_pago:
        return False, "no se recibió el id de la forma de pago."

    cambiar_estatus_forma_pago_model(id_forma_pago, activo)
    return True, "estatus actualizado correctamente."