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


def obtener_roles_usuarios_ids_model(usuario_ids: list[int]) -> dict[int, list[str]]:
    """Roles de varios usuarios en una sola consulta — evita el N+1 de llamar
    obtener_roles_usuario_id_model por cada dueño de carga distinto al
    rederivar quién debe autorizar en la pestaña de autorizaciones."""
    ids = sorted({int(v) for v in usuario_ids if v is not None})
    if not ids:
        return {}
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)
        placeholders = ", ".join(["%s"] * len(ids))
        cur.execute(
            f"""
            select u.id as usuario_id, r.nombre
            from usuarios_roles ur
            join roles r on r.id = ur.id_rol
            join usuarios u on u.username = ur.username
            where u.id in ({placeholders})
            """,
            tuple(ids),
        )
        resultado: dict[int, list[str]] = {uid: [] for uid in ids}
        for row in (cur.fetchall() or []):
            resultado.setdefault(int(row["usuario_id"]), []).append(str(row["nombre"]))
        return resultado
    finally:
        try:
            conn.close()
        except Exception:
            pass


def obtener_usuarios_por_ids_model(usuario_ids: list[int]) -> dict[int, dict]:
    """Datos (id, nombre, email) de varios usuarios en una sola consulta —
    evita el N+1 de obtener_usuario_por_id_model por cada dueño de carga
    distinto en las pestañas de autorizaciones (pendientes y resueltas)."""
    ids = sorted({int(v) for v in usuario_ids if v is not None})
    if not ids:
        return {}
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)
        placeholders = ", ".join(["%s"] * len(ids))
        cur.execute(
            f"select id, nombre, email from usuarios where id in ({placeholders})",
            tuple(ids),
        )
        return {int(row["id"]): row for row in (cur.fetchall() or [])}
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


def obtener_clientes_presupuesto_model() -> list[str]:
    """Clientes (cliente_excel) que ya aparecen en presupuesto_ventas o
    presupuesto_compras, para poblar el filtro de "cliente" de la pestaña
    ver todos — no se usa el catálogo de clientes SAE porque cve_clie casi
    nunca se llena en la captura (ver migration_presupuesto_ventas_planta.sql)."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            select distinct cliente_excel from presupuesto_ventas
            where estatus = 'activo' and cliente_excel is not null and cliente_excel <> ''
            union
            select distinct cliente_excel from presupuesto_compras
            where estatus = 'activo' and cliente_excel is not null and cliente_excel <> ''
            order by cliente_excel
            """
        )
        return [str(row[0]) for row in (cur.fetchall() or [])]
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _in_clause(sql: str, params: list, columna: str, valor) -> str:
    """Agrega "and columna in (...)" (o "= %s" si es un solo valor) al SQL,
    aceptando tanto un escalar como una lista/tupla — así los filtros de la
    pestaña "ver todos" pueden ser selección múltiple sin duplicar la
    función para cada caso."""
    if valor is None:
        return sql
    if isinstance(valor, (list, tuple, set)):
        valores = [v for v in valor if v not in (None, "")]
        if not valores:
            return sql
        placeholders = ", ".join(["%s"] * len(valores))
        sql += f" and {columna} in ({placeholders})"
        params.extend(valores)
        return sql
    sql += f" and {columna} = %s"
    params.append(valor)
    return sql


def obtener_presupuesto_ventas_compras_model(
    anio: int | None = None,
    usuario_id: int | list[int] | None = None,
    cve_prod: str | list[str] | None = None,
    tipo: str | list[str] | None = None,
    estatus_autorizacion: str | list[str] | None = None,
    cliente: str | list[str] | None = None,
    limit: int = 50000,
) -> pd.DataFrame:
    """Unión de presupuesto_ventas y presupuesto_compras, con el usuario
    dueño de la carga y el estatus de autorización de cada línea (captura
    por defecto si no tiene registro en *_lineas), para la pestaña de
    solo-lectura "ver todos" (forecastAdmin / SuperAdmin).

    Solo trae las líneas de sección KG — las de sección USD son un bloque
    aparte del mismo Excel (turnover en dólares) y duplicarían las cifras
    ya calculadas a partir de KG × precio."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)

        sql = """
            select * from (
                select
                    'venta' as tipo,
                    p.id_presupuesto, p.id_carga, p.seccion, p.region, p.anio, p.mes,
                    p.cve_prod, p.company, p.cliente_excel, p.codigo_origen, p.producto_excel,
                    p.linea_uid,
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
                   and l.linea_uid = p.linea_uid
                where p.estatus = 'activo'

                union all

                select
                    'compra' as tipo,
                    p.id_presupuesto, p.id_carga, p.seccion, p.region, p.anio, p.mes,
                    p.cve_prod, p.company, p.cliente_excel, p.codigo_origen, p.producto_excel,
                    p.linea_uid,
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
                   and l.linea_uid = p.linea_uid
                where p.estatus = 'activo'
            ) t
            where t.seccion = 'KG'
        """
        params: list = []

        if anio is not None:
            sql += " and t.anio = %s"
            params.append(int(anio))

        if isinstance(usuario_id, (list, tuple, set)):
            sql = _in_clause(sql, params, "t.usuario_id", [int(v) for v in usuario_id])
        elif usuario_id is not None:
            sql = _in_clause(sql, params, "t.usuario_id", int(usuario_id))

        if isinstance(cve_prod, (list, tuple, set)):
            sql = _in_clause(sql, params, "t.cve_prod", [str(v).strip() for v in cve_prod])
        elif cve_prod:
            sql = _in_clause(sql, params, "t.cve_prod", str(cve_prod).strip())

        if isinstance(tipo, (list, tuple, set)):
            sql = _in_clause(sql, params, "t.tipo", [str(v).strip() for v in tipo])
        elif tipo:
            sql = _in_clause(sql, params, "t.tipo", str(tipo).strip())

        if isinstance(estatus_autorizacion, (list, tuple, set)):
            sql = _in_clause(sql, params, "t.estatus_autorizacion", [str(v).strip() for v in estatus_autorizacion])
        elif estatus_autorizacion:
            sql = _in_clause(sql, params, "t.estatus_autorizacion", str(estatus_autorizacion).strip())

        if isinstance(cliente, (list, tuple, set)):
            sql = _in_clause(sql, params, "t.cliente_excel", [str(v).strip() for v in cliente])
        elif cliente:
            sql = _in_clause(sql, params, "t.cliente_excel", str(cliente).strip())

        sql += " order by t.anio desc, t.mes desc, t.id_presupuesto desc limit %s"
        params.append(int(limit))

        cur.execute(sql, tuple(params))
        rows = cur.fetchall() or []

        if not rows:
            return pd.DataFrame(columns=[
                "tipo", "id_presupuesto", "id_carga", "seccion", "region", "anio", "mes",
                "cve_prod", "company", "cliente_excel", "codigo_origen", "producto_excel", "linea_uid",
                "cantidad_kg", "precio", "precio_venta", "importe", "valor", "estatus", "estatus_autorizacion",
                "usuario_id", "nombre_archivo", "version", "usuario_nombre",
            ])

        return pd.DataFrame(rows)

    finally:
        try:
            conn.close()
        except Exception:
            pass
