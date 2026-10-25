from models.compras_tipos_campos_model import (
    generar_clave_campo,
    obtener_campos_tipo_model,
    existe_clave_campo_model,
    crear_campo_tipo_model,
    actualizar_campo_tipo_model,
    eliminar_campo_tipo_model,
    TIPOS_DATO_VALIDOS,
)

TIPOS_DATO = sorted(TIPOS_DATO_VALIDOS)


def obtener_campos_tipo_ctrl(id_tipo_compra: int, seccion: str | None = None) -> list[dict]:
    return obtener_campos_tipo_model(int(id_tipo_compra), seccion)


def crear_campo_tipo_ctrl(
    *, id_tipo_compra: int, seccion: str, nombre_campo: str, tipo_dato: str,
    opciones: str = "", requerido: bool = False, orden: int = 0,
) -> tuple[bool, str]:
    nombre_campo = (nombre_campo or "").strip()
    if not nombre_campo:
        return False, "debes capturar el nombre del campo."
    if seccion not in ("cabecera", "detalle"):
        return False, "sección inválida."
    if tipo_dato not in TIPOS_DATO_VALIDOS:
        return False, "tipo de dato inválido."
    if tipo_dato == "seleccion" and not (opciones or "").strip():
        return False, "captura al menos una opción (una por línea) para un campo de selección."

    clave_campo = generar_clave_campo(nombre_campo)
    if existe_clave_campo_model(id_tipo_compra, clave_campo):
        return False, "ya existe un campo con un nombre muy similar en este tipo de compra."

    id_campo = crear_campo_tipo_model(
        id_tipo_compra=id_tipo_compra, seccion=seccion, nombre_campo=nombre_campo,
        clave_campo=clave_campo, tipo_dato=tipo_dato,
        opciones=(opciones or "").strip() or None, requerido=1 if requerido else 0, orden=orden,
    )
    return (True, "campo creado correctamente.") if id_campo else (False, "no se pudo crear el campo.")


def actualizar_campo_tipo_ctrl(
    *, id: int, nombre_campo: str, tipo_dato: str, opciones: str = "",
    requerido: bool = False, orden: int = 0, activo: bool = True,
) -> tuple[bool, str]:
    nombre_campo = (nombre_campo or "").strip()
    if not nombre_campo:
        return False, "debes capturar el nombre del campo."
    if tipo_dato not in TIPOS_DATO_VALIDOS:
        return False, "tipo de dato inválido."
    if tipo_dato == "seleccion" and not (opciones or "").strip():
        return False, "captura al menos una opción (una por línea) para un campo de selección."

    ok = actualizar_campo_tipo_model(
        id=id, nombre_campo=nombre_campo, tipo_dato=tipo_dato,
        opciones=(opciones or "").strip() or None, requerido=1 if requerido else 0,
        orden=orden, activo=1 if activo else 0,
    )
    return (True, "campo actualizado correctamente.") if ok else (False, "no se pudo actualizar el campo.")


def eliminar_campo_tipo_ctrl(id: int) -> tuple[bool, str]:
    ok = eliminar_campo_tipo_model(id)
    return (True, "campo eliminado correctamente.") if ok else (False, "no se pudo eliminar el campo.")
