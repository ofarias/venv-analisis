from __future__ import annotations

import pandas as pd
from database.conexion import obtener_conexion


def upsert_forecast_mes_estatus_model(
    id_version: int,
    tipo: str,
    anio: int,
    mes: int,
    estatus: str,
    usuario_id: int,
) -> tuple[int, str | None]:
    """Crea la fila si no existe (estatus inicial implícito 'borrador' hasta
    este primer upsert) o actualiza su estatus si ya existe. Devuelve
    (mes_estatus_id, estatus_anterior) — mismo patrón que
    upsert_presupuesto_ventas_linea_model."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            select id, estatus from forecast_mes_estatus
            where id_version = %s and tipo = %s and anio = %s and mes = %s
            """,
            (int(id_version), str(tipo), int(anio), int(mes)),
        )
        existente = cur.fetchone()

        if existente:
            mes_estatus_id = int(existente["id"])
            estatus_anterior = existente["estatus"]
            cur.execute(
                """
                update forecast_mes_estatus
                set estatus = %s, actualizado_por = %s, fecha_actualizacion = current_timestamp
                where id = %s
                """,
                (str(estatus), int(usuario_id), mes_estatus_id),
            )
        else:
            estatus_anterior = None
            cur.execute(
                """
                insert into forecast_mes_estatus (
                    id_version, tipo, anio, mes, estatus, creado_por, actualizado_por
                ) values (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    int(id_version), str(tipo), int(anio), int(mes),
                    str(estatus), int(usuario_id), int(usuario_id),
                ),
            )
            mes_estatus_id = int(cur.lastrowid or 0)

        conn.commit()
        return mes_estatus_id, estatus_anterior
    finally:
        try:
            conn.close()
        except Exception:
            pass


def insertar_forecast_mes_estatus_historico_model(
    mes_estatus_id: int,
    estatus_anterior: str | None,
    estatus_nuevo: str,
    usuario_id: int | None,
    usuario_nombre: str | None,
    usuario_email: str | None,
    comentario: str | None,
) -> int:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            insert into forecast_mes_estatus_historico (
                mes_estatus_id, estatus_anterior, estatus_nuevo,
                usuario_id, usuario_nombre, usuario_email, comentario
            ) values (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                int(mes_estatus_id),
                estatus_anterior,
                str(estatus_nuevo),
                int(usuario_id) if usuario_id else None,
                str(usuario_nombre).strip() if usuario_nombre else None,
                str(usuario_email).strip() if usuario_email else None,
                str(comentario).strip() if comentario else None,
            ),
        )
        conn.commit()
        return int(cur.lastrowid or 0)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def obtener_forecast_mes_estatus_model(
    id_version: int,
    tipo: str | None = None,
    anio: int | None = None,
) -> pd.DataFrame:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)
        sql = "select * from forecast_mes_estatus where id_version = %s"
        params: list = [int(id_version)]
        if tipo:
            sql += " and tipo = %s"
            params.append(str(tipo))
        if anio:
            sql += " and anio = %s"
            params.append(int(anio))
        cur.execute(sql, tuple(params))
        rows = cur.fetchall() or []
        if not rows:
            return pd.DataFrame(columns=[
                "id", "id_version", "tipo", "anio", "mes", "estatus",
                "creado_por", "fecha_creacion", "actualizado_por", "fecha_actualizacion",
            ])
        return pd.DataFrame(rows)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def obtener_forecast_mes_estatus_pendientes_model() -> pd.DataFrame:
    """Todas las filas en estatus 'enviada' (pendientes de autorizar), de
    todos los vendedores/versiones, con datos de la versión (dueño, año,
    nombre) para mostrarlas — calco de
    obtener_presupuesto_ventas_lineas_pendientes_model."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            select
                m.id, m.id_version, m.tipo, m.anio, m.mes, m.estatus,
                m.creado_por, m.fecha_creacion, m.actualizado_por, m.fecha_actualizacion,
                v.nombre as version_nombre, v.usuario_id as version_usuario_id
            from forecast_mes_estatus m
            join forecast_versiones v on v.id_version = m.id_version
            where m.estatus = 'enviada'
            order by m.fecha_actualizacion asc
            """
        )
        rows = cur.fetchall() or []
        return pd.DataFrame(rows)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def obtener_forecast_mes_estatus_resueltos_model(usuario_id: int, limit: int = 300) -> pd.DataFrame:
    """Historial de meses que usuario_id autorizó o rechazó, con datos de la
    versión — calco de obtener_presupuesto_ventas_lineas_resueltas_model."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            select
                h.id as estatus_id, h.mes_estatus_id, h.estatus_anterior, h.estatus_nuevo,
                h.comentario, h.fecha,
                m.id_version, m.tipo, m.anio, m.mes,
                v.nombre as version_nombre, v.usuario_id as version_usuario_id
            from forecast_mes_estatus_historico h
            join forecast_mes_estatus m on m.id = h.mes_estatus_id
            join forecast_versiones v on v.id_version = m.id_version
            where h.usuario_id = %s and h.estatus_nuevo in ('autorizada', 'rechazada')
            order by h.fecha desc
            limit %s
            """,
            (int(usuario_id), int(limit)),
        )
        rows = cur.fetchall() or []
        return pd.DataFrame(rows)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def obtener_forecast_mes_estatus_autorizados_model(anio: int, tipo: str) -> pd.DataFrame:
    """Todas las filas 'autorizada' de un año/tipo dado, con el dueño de cada
    versión — insumo del consolidado cross-vendedor de Compras."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            select
                m.id_version, m.tipo, m.anio, m.mes, m.estatus,
                v.usuario_id as version_usuario_id
            from forecast_mes_estatus m
            join forecast_versiones v on v.id_version = m.id_version
            where m.anio = %s and m.tipo = %s and m.estatus = 'autorizada'
            """,
            (int(anio), str(tipo)),
        )
        rows = cur.fetchall() or []
        return pd.DataFrame(rows)
    finally:
        try:
            conn.close()
        except Exception:
            pass
