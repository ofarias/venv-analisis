"""Definición de campos (cabecera/detalle) de un tipo de compra con
tipo_formulario='DINAMICO' — configurado por un Admin, sin tocar código."""

import re

from database.conexion import obtener_conexion

TIPOS_DATO_VALIDOS = {"texto", "texto_largo", "numero", "fecha", "seleccion"}


def generar_clave_campo(nombre_campo: str) -> str:
    """slug estable a partir del nombre visible — ej. "Proveedor sugerido"
    -> "proveedor_sugerido"."""
    slug = re.sub(r"[^a-z0-9]+", "_", str(nombre_campo or "").strip().lower()).strip("_")
    return slug[:50] or "campo"


def obtener_campos_tipo_model(id_tipo_compra: int, seccion: str | None = None) -> list[dict]:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)
        sql = """
            SELECT id, id_tipo_compra, seccion, nombre_campo, clave_campo,
                   tipo_dato, opciones, requerido, orden, activo
            FROM compras_tipos_campos_dinamicos
            WHERE id_tipo_compra = %s
        """
        params = [int(id_tipo_compra)]
        if seccion:
            sql += " AND seccion = %s"
            params.append(seccion)
        sql += " ORDER BY seccion, orden, id"
        cur.execute(sql, tuple(params))
        return cur.fetchall() or []

    finally:
        conn.close()


def existe_clave_campo_model(id_tipo_compra: int, clave_campo: str, id_excluir: int | None = None) -> bool:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        sql = "SELECT COUNT(*) FROM compras_tipos_campos_dinamicos WHERE id_tipo_compra = %s AND clave_campo = %s"
        params = [int(id_tipo_compra), clave_campo]
        if id_excluir is not None:
            sql += " AND id <> %s"
            params.append(int(id_excluir))
        cur.execute(sql, tuple(params))
        return int(cur.fetchone()[0]) > 0

    finally:
        conn.close()


def crear_campo_tipo_model(
    *, id_tipo_compra: int, seccion: str, nombre_campo: str, clave_campo: str,
    tipo_dato: str, opciones: str | None, requerido: int, orden: int,
) -> int | None:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO compras_tipos_campos_dinamicos (
                id_tipo_compra, seccion, nombre_campo, clave_campo, tipo_dato,
                opciones, requerido, orden, activo
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1)
            """,
            (
                int(id_tipo_compra), seccion, nombre_campo.strip(), clave_campo,
                tipo_dato, opciones, int(requerido), int(orden),
            ),
        )
        conn.commit()
        return int(cur.lastrowid)

    except Exception:
        conn.rollback()
        return None

    finally:
        conn.close()


def actualizar_campo_tipo_model(
    *, id: int, nombre_campo: str, tipo_dato: str, opciones: str | None,
    requerido: int, orden: int, activo: int,
) -> bool:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE compras_tipos_campos_dinamicos
            SET nombre_campo = %s, tipo_dato = %s, opciones = %s,
                requerido = %s, orden = %s, activo = %s
            WHERE id = %s
            """,
            (nombre_campo.strip(), tipo_dato, opciones, int(requerido), int(orden), int(activo), int(id)),
        )
        conn.commit()
        return cur.rowcount > 0

    except Exception:
        conn.rollback()
        return False

    finally:
        conn.close()


def eliminar_campo_tipo_model(id: int) -> bool:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM compras_tipos_campos_dinamicos WHERE id = %s", (int(id),))
        conn.commit()
        return cur.rowcount > 0

    except Exception:
        conn.rollback()
        return False

    finally:
        conn.close()
