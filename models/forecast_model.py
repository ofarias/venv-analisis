from __future__ import annotations

from typing import Optional
import pandas as pd
from database.conexion import obtener_conexion


# ── versiones ─────────────────────────────────────────────────────────────────

def insertar_forecast_version_model(
    anio: int,
    nombre: str,
    descripcion: Optional[str],
    id_carga_pv: Optional[int],
    metodo_default: str,
    usuario_id: int,
) -> int:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO forecast_versiones
                (anio, nombre, descripcion, estatus, id_carga_pv, metodo_default, usuario_id)
            VALUES (%s, %s, %s, 'borrador', %s, %s, %s)
            """,
            (int(anio), str(nombre).strip(), descripcion or None,
             int(id_carga_pv) if id_carga_pv else None,
             str(metodo_default), int(usuario_id)),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        try:
            conn.close()
        except Exception:
            pass


def obtener_forecast_versiones_model(
    usuario_id: int,
    anio: Optional[int] = None,
    ver_todas: bool = False,
) -> pd.DataFrame:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)
        sql = """
            SELECT v.*, c.nombre_archivo, c.version as version_pv, u.nombre as propietario
            FROM forecast_versiones v
            LEFT JOIN presupuesto_ventas_cargas c ON c.id_carga = v.id_carga_pv
            LEFT JOIN usuarios u ON u.id = v.usuario_id
            WHERE 1 = 1
        """
        params: list = []
        if not ver_todas:
            sql += " AND v.usuario_id = %s"
            params.append(int(usuario_id))
        if anio:
            sql += " AND v.anio = %s"
            params.append(int(anio))
        sql += " ORDER BY v.created_at DESC"
        cur.execute(sql, tuple(params))
        rows = cur.fetchall() or []
        if not rows:
            return pd.DataFrame(columns=[
                "id_version", "anio", "nombre", "descripcion", "estatus",
                "id_carga_pv", "metodo_default", "usuario_id",
                "nombre_archivo", "version_pv", "propietario", "created_at", "updated_at",
            ])
        return pd.DataFrame(rows)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def actualizar_estatus_forecast_version_model(id_version: int, estatus: str) -> bool:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE forecast_versiones SET estatus = %s, updated_at = current_timestamp WHERE id_version = %s",
            (str(estatus), int(id_version)),
        )
        conn.commit()
        return True
    finally:
        try:
            conn.close()
        except Exception:
            pass


def eliminar_forecast_version_model(id_version: int) -> bool:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM forecast_alertas WHERE id_version = %s", (int(id_version),))
        cur.execute("DELETE FROM forecast_detalle WHERE id_version = %s", (int(id_version),))
        cur.execute("DELETE FROM forecast_versiones WHERE id_version = %s", (int(id_version),))
        conn.commit()
        return True
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ── detalle ───────────────────────────────────────────────────────────────────

def upsert_forecast_detalle_model(
    id_version: int,
    seccion: str,
    region: Optional[str],
    cve_prod: Optional[str],
    producto_excel: Optional[str],
    anio: int,
    mes: int,
    forecast: float,
    justificacion: Optional[str],
    metodo: str,
    usuario_id: int,
    venta_real_mes_ant: float = 0.0,
    venta_real_prom_3m: float = 0.0,
    presupuesto_valor: float = 0.0,
) -> int:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO forecast_detalle
                (id_version, seccion, region, cve_prod, producto_excel, anio, mes,
                 venta_real_mes_ant, venta_real_prom_3m, presupuesto_valor,
                 forecast, justificacion, metodo, usuario_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE
                forecast             = VALUES(forecast),
                justificacion        = VALUES(justificacion),
                metodo               = VALUES(metodo),
                venta_real_mes_ant   = VALUES(venta_real_mes_ant),
                venta_real_prom_3m   = VALUES(venta_real_prom_3m),
                presupuesto_valor    = VALUES(presupuesto_valor),
                usuario_id           = VALUES(usuario_id),
                updated_at           = current_timestamp
            """,
            (
                int(id_version), str(seccion), region or None,
                str(cve_prod).strip() if cve_prod else None,
                str(producto_excel).strip() if producto_excel else None,
                int(anio), int(mes),
                float(venta_real_mes_ant), float(venta_real_prom_3m), float(presupuesto_valor),
                float(forecast), justificacion or None, str(metodo), int(usuario_id),
            ),
        )
        conn.commit()
        return cur.lastrowid or cur.rowcount
    finally:
        try:
            conn.close()
        except Exception:
            pass


def obtener_forecast_detalle_model(
    id_version: int,
    seccion: Optional[str] = None,
    region: Optional[str] = None,
) -> pd.DataFrame:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)
        sql = "SELECT * FROM forecast_detalle WHERE id_version = %s"
        params: list = [int(id_version)]
        if seccion:
            sql += " AND seccion = %s"
            params.append(str(seccion))
        if region:
            sql += " AND region = %s"
            params.append(str(region))
        sql += " ORDER BY cve_prod, anio, mes"
        cur.execute(sql, tuple(params))
        rows = cur.fetchall() or []
        if not rows:
            return pd.DataFrame(columns=[
                "id_forecast", "id_version", "seccion", "region", "cve_prod",
                "producto_excel", "anio", "mes", "venta_real_mes_ant",
                "venta_real_prom_3m", "presupuesto_valor", "forecast",
                "justificacion", "metodo", "usuario_id", "created_at", "updated_at",
            ])
        return pd.DataFrame(rows)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def eliminar_forecast_detalle_por_version_model(id_version: int) -> int:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM forecast_detalle WHERE id_version = %s", (int(id_version),))
        conn.commit()
        return cur.rowcount
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ── alertas ───────────────────────────────────────────────────────────────────

def insertar_alerta_forecast_model(
    id_version: int,
    tipo: str,
    cve_prod: Optional[str],
    anio: int,
    mes: int,
    severidad: str,
    mensaje: str,
) -> None:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO forecast_alertas (id_version, tipo, cve_prod, anio, mes, severidad, mensaje)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (int(id_version), str(tipo), cve_prod or None, int(anio), int(mes), str(severidad), str(mensaje)),
        )
        conn.commit()
    finally:
        try:
            conn.close()
        except Exception:
            pass


def obtener_alertas_forecast_model(id_version: int, solo_activas: bool = True) -> pd.DataFrame:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)
        sql = "SELECT * FROM forecast_alertas WHERE id_version = %s"
        params: list = [int(id_version)]
        if solo_activas:
            sql += " AND resuelta = 0"
        sql += " ORDER BY severidad DESC, tipo, cve_prod"
        cur.execute(sql, tuple(params))
        rows = cur.fetchall() or []
        return pd.DataFrame(rows) if rows else pd.DataFrame(
            columns=["id_alerta", "id_version", "tipo", "cve_prod", "anio", "mes", "severidad", "mensaje", "resuelta"]
        )
    finally:
        try:
            conn.close()
        except Exception:
            pass


def limpiar_alertas_forecast_model(id_version: int) -> None:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM forecast_alertas WHERE id_version = %s", (int(id_version),))
        conn.commit()
    finally:
        try:
            conn.close()
        except Exception:
            pass
