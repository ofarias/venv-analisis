from __future__ import annotations

import pandas as pd

from database.conexion import obtener_conexion


def obtener_roles_usuario_id_model(usuario_id: int) -> list[str]:
    """Roles (nombres) de un usuario dado su id — usado para rederivar, sin
    duplicar sesión, qué rol debe autorizar la línea de un tercero."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            select r.nombre
            from usuarios_roles ur
            join roles r on r.id = ur.id_rol
            join usuarios u on u.username = ur.username
            where u.id = %s
            """,
            (int(usuario_id),),
        )
        return [str(row["nombre"]) for row in (cur.fetchall() or [])]
    finally:
        try:
            conn.close()
        except Exception:
            pass


def obtener_usuario_por_id_model(usuario_id: int) -> dict | None:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "select id, nombre, email from usuarios where id = %s",
            (int(usuario_id),),
        )
        return cur.fetchone()
    finally:
        try:
            conn.close()
        except Exception:
            pass


def obtener_usuarios_presupuesto_model() -> pd.DataFrame:
    """Usuarios que tienen al menos una carga de presupuesto (venta o compra),
    para poblar el filtro de "usuario" de la pestaña ver todos."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            select distinct u.id as usuario_id, u.nombre as usuario_nombre
            from usuarios u
            where u.id in (
                select usuario_id from presupuesto_ventas_cargas where usuario_id is not null
                union
                select usuario_id from presupuesto_compras_cargas where usuario_id is not null
            )
            order by u.nombre
            """
        )
        rows = cur.fetchall() or []
        return pd.DataFrame(rows)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def obtener_presupuesto_ventas_compras_model(
    anio: int | None = None,
    usuario_id: int | None = None,
    cve_prod: str | None = None,
    tipo: str | None = None,
    estatus_autorizacion: str | None = None,
    limit: int = 50000,
) -> pd.DataFrame:
    """Unión de presupuesto_ventas y presupuesto_compras, con el usuario
    dueño de la carga y el estatus de autorización de cada línea (captura
    por defecto si no tiene registro en *_lineas), para la pestaña de
    solo-lectura "ver todos" (forecastAdmin / SuperAdmin)."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)

        sql = """
            select * from (
                select
                    'venta' as tipo,
                    p.id_presupuesto, p.id_carga, p.seccion, p.region, p.anio, p.mes,
                    p.cve_prod, p.company, p.cliente_excel, p.codigo_origen, p.producto_excel,
                    p.cantidad_kg, p.precio, p.precio_venta, p.importe, p.valor, p.estatus,
                    coalesce(l.estatus, 'captura') as estatus_autorizacion,
                    c.usuario_id, c.nombre_archivo, c.version,
                    u.nombre as usuario_nombre
                from presupuesto_ventas p
                join presupuesto_ventas_cargas c on c.id_carga = p.id_carga
                left join usuarios u on u.id = c.usuario_id
                left join presupuesto_ventas_lineas l
                    on l.id_carga = p.id_carga
                   and l.company <=> p.company
                   and l.cliente_excel <=> p.cliente_excel
                   and l.codigo_origen <=> p.codigo_origen
                   and l.producto_excel = p.producto_excel
                where p.estatus = 'activo'

                union all

                select
                    'compra' as tipo,
                    p.id_presupuesto, p.id_carga, p.seccion, p.region, p.anio, p.mes,
                    p.cve_prod, p.company, p.cliente_excel, p.codigo_origen, p.producto_excel,
                    p.cantidad_kg, p.precio, null as precio_venta, p.importe, p.valor, p.estatus,
                    coalesce(l.estatus, 'captura') as estatus_autorizacion,
                    c.usuario_id, c.nombre_archivo, c.version,
                    u.nombre as usuario_nombre
                from presupuesto_compras p
                join presupuesto_compras_cargas c on c.id_carga = p.id_carga
                left join usuarios u on u.id = c.usuario_id
                left join presupuesto_compras_lineas l
                    on l.id_carga = p.id_carga
                   and l.company <=> p.company
                   and l.cliente_excel <=> p.cliente_excel
                   and l.codigo_origen <=> p.codigo_origen
                   and l.producto_excel = p.producto_excel
                where p.estatus = 'activo'
            ) t
            where 1 = 1
        """
        params: list = []

        if anio is not None:
            sql += " and t.anio = %s"
            params.append(int(anio))

        if usuario_id is not None:
            sql += " and t.usuario_id = %s"
            params.append(int(usuario_id))

        if cve_prod:
            sql += " and t.cve_prod = %s"
            params.append(str(cve_prod).strip())

        if tipo:
            sql += " and t.tipo = %s"
            params.append(str(tipo).strip())

        if estatus_autorizacion:
            sql += " and t.estatus_autorizacion = %s"
            params.append(str(estatus_autorizacion).strip())

        sql += " order by t.anio desc, t.mes desc, t.id_presupuesto desc limit %s"
        params.append(int(limit))

        cur.execute(sql, tuple(params))
        rows = cur.fetchall() or []

        if not rows:
            return pd.DataFrame(columns=[
                "tipo", "id_presupuesto", "id_carga", "seccion", "region", "anio", "mes",
                "cve_prod", "company", "cliente_excel", "codigo_origen", "producto_excel",
                "cantidad_kg", "precio", "precio_venta", "importe", "valor", "estatus", "estatus_autorizacion",
                "usuario_id", "nombre_archivo", "version", "usuario_nombre",
            ])

        return pd.DataFrame(rows)

    finally:
        try:
            conn.close()
        except Exception:
            pass
