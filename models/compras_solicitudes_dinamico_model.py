"""Captura/lectura de solicitudes de tipo DINAMICO — valores libres por
campo (ver compras_tipos_campos_dinamicos), guardados como llave/valor."""

import pandas as pd

from database.conexion import obtener_conexion


def guardar_valores_cabecera_model(id_solicitud_compra: int, valores: dict[str, str]) -> bool:
    if not valores:
        return True
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.executemany(
            """
            INSERT INTO compras_solicitudes_dinamico_cabecera_valores (id_solicitud_compra, clave_campo, valor)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE valor = VALUES(valor)
            """,
            [(int(id_solicitud_compra), clave, valor) for clave, valor in valores.items()],
        )
        conn.commit()
        return True

    except Exception:
        conn.rollback()
        return False

    finally:
        conn.close()


def obtener_valores_cabecera_model(id_solicitud_compra: int) -> dict[str, str]:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT clave_campo, valor FROM compras_solicitudes_dinamico_cabecera_valores WHERE id_solicitud_compra = %s",
            (int(id_solicitud_compra),),
        )
        return {row[0]: row[1] for row in cur.fetchall()}

    finally:
        conn.close()


def crear_renglon_detalle_model(id_solicitud_compra: int, orden: int, valores: dict[str, str]) -> int | None:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO compras_solicitudes_dinamico_detalle (id_solicitud_compra, orden) VALUES (%s, %s)",
            (int(id_solicitud_compra), int(orden)),
        )
        id_detalle = int(cur.lastrowid)
        if valores:
            cur.executemany(
                """
                INSERT INTO compras_solicitudes_dinamico_detalle_valores (id_detalle_dinamico, clave_campo, valor)
                VALUES (%s, %s, %s)
                """,
                [(id_detalle, clave, valor) for clave, valor in valores.items()],
            )
        conn.commit()
        return id_detalle

    except Exception:
        conn.rollback()
        return None

    finally:
        conn.close()


def obtener_detalle_dinamico_model(id_solicitud_compra: int) -> pd.DataFrame:
    """Una fila por renglón, una columna por clave_campo (pivotea los
    valores) — para mostrarlo como tabla en Pendientes/Autorizaciones."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT d.id_detalle_dinamico, d.orden, v.clave_campo, v.valor
            FROM compras_solicitudes_dinamico_detalle d
            LEFT JOIN compras_solicitudes_dinamico_detalle_valores v ON v.id_detalle_dinamico = d.id_detalle_dinamico
            WHERE d.id_solicitud_compra = %s
            ORDER BY d.orden, d.id_detalle_dinamico
            """,
            (int(id_solicitud_compra),),
        )
        rows = cur.fetchall() or []
        if not rows:
            return pd.DataFrame(columns=["id_detalle_dinamico", "orden"])

        por_renglon: dict[int, dict] = {}
        for r in rows:
            renglon = por_renglon.setdefault(
                r["id_detalle_dinamico"], {"id_detalle_dinamico": r["id_detalle_dinamico"], "orden": r["orden"]}
            )
            if r["clave_campo"]:
                renglon[r["clave_campo"]] = r["valor"]
        return pd.DataFrame(list(por_renglon.values()))

    finally:
        conn.close()
