"""Persistencia de qué columnas oculta cada usuario en una tabla AgGrid
(ej. presupuesto de ventas/compras), para que la preferencia sobreviva a un
refresh de la página en vez de resetear a "todas visibles" cada vez."""

from __future__ import annotations

import json

from database.conexion import obtener_conexion


def obtener_columnas_ocultas(usuario_id: int, grid_key: str) -> list[str]:
    if not usuario_id:
        return []
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT columnas_ocultas FROM ui_columnas_ocultas WHERE usuario_id=%s AND grid_key=%s",
            (usuario_id, grid_key),
        )
        row = cur.fetchone()
        cur.close()
        if not row or not row[0]:
            return []
        return json.loads(row[0])
    except Exception:
        return []
    finally:
        conn.close()


def guardar_columnas_ocultas(usuario_id: int, grid_key: str, columnas_ocultas: list[str]) -> None:
    if not usuario_id:
        return
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO ui_columnas_ocultas (usuario_id, grid_key, columnas_ocultas)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE columnas_ocultas = VALUES(columnas_ocultas)
            """,
            (usuario_id, grid_key, json.dumps(sorted(columnas_ocultas))),
        )
        conn.commit()
        cur.close()
    except Exception:
        pass
    finally:
        conn.close()
