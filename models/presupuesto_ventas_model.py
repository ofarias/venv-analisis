from __future__ import annotations

import pandas as pd
from typing import Optional

from database.conexion import obtener_conexion


def insertar_carga_presupuesto_ventas_model(
    nombre_archivo: str,
    hoja_origen: str | None,
    anio: int,
    version: str | None,
    comentarios: str | None,
    usuario_id: int,
) -> int:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()

        sql = """
            insert into presupuesto_ventas_cargas (
                nombre_archivo,
                hoja_origen,
                anio,
                version,
                comentarios,
                usuario_id
            )
            values (%s, %s, %s, %s, %s, %s)
        """
        cur.execute(
            sql,
            (
                str(nombre_archivo).strip(),
                str(hoja_origen).strip() if hoja_origen else None,
                int(anio),
                str(version).strip() if version else None,
                str(comentarios).strip() if comentarios else None,
                int(usuario_id),
            ),
        )
        conn.commit()

        return int(cur.lastrowid or 0)

    finally:
        try:
            conn.close()
        except Exception:
            pass


def actualizar_estatus_carga_presupuesto_ventas_model(
    id_carga: int,
    estatus: str,
    comentarios: str | None = None,
) -> bool:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()

        if comentarios is None:
            sql = """
                update presupuesto_ventas_cargas
                set
                    estatus = %s,
                    updated_at = current_timestamp
                where id_carga = %s
            """
            params = (
                str(estatus).strip(),
                int(id_carga),
            )
        else:
            sql = """
                update presupuesto_ventas_cargas
                set
                    estatus = %s,
                    comentarios = %s,
                    updated_at = current_timestamp
                where id_carga = %s
            """
            params = (
                str(estatus).strip(),
                str(comentarios).strip() if comentarios else None,
                int(id_carga),
            )

        cur.execute(sql, params)
        conn.commit()
        return True

    finally:
        try:
            conn.close()
        except Exception:
            pass


def obtener_cargas_presupuesto_ventas_model(
    anio: int | None = None,
    id_carga: int | None = None,
    limit: int = 100,
    usuario_id: int | None = None,
) -> pd.DataFrame:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)

        sql = """
            select
                id_carga,
                nombre_archivo,
                hoja_origen,
                anio,
                version,
                estatus,
                comentarios,
                usuario_id,
                created_at,
                updated_at
            from presupuesto_ventas_cargas
            where 1 = 1
        """
        params: list = []

        if usuario_id is not None and int(usuario_id) > 0:
            sql += " and usuario_id = %s"
            params.append(int(usuario_id))

        if id_carga is not None:
            sql += " and id_carga = %s"
            params.append(int(id_carga))

        if anio is not None:
            sql += " and anio = %s"
            params.append(int(anio))

        sql += " order by id_carga desc limit %s"
        params.append(int(limit))

        cur.execute(sql, tuple(params))
        rows = cur.fetchall() or []

        if not rows:
            return pd.DataFrame(columns=[
                "id_carga",
                "nombre_archivo",
                "hoja_origen",
                "anio",
                "version",
                "estatus",
                "comentarios",
                "usuario_id",
                "created_at",
                "updated_at",
            ])

        return pd.DataFrame(rows)

    finally:
        try:
            conn.close()
        except Exception:
            pass


def eliminar_staging_por_carga_presupuesto_ventas_model(id_carga: int) -> bool:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()

        sql = "delete from presupuesto_ventas_staging where id_carga = %s"
        cur.execute(sql, (int(id_carga),))
        conn.commit()
        return True

    finally:
        try:
            conn.close()
        except Exception:
            pass


def insertar_staging_presupuesto_ventas_model(
    id_carga: int,
    fila_excel: int,
    precio: float,
    anio: int,
    mes: int,
    cantidad_kg: float,
    importe: float,
    seccion: str | None = None,
    region: str | None = None,
    estatus_excel: str | None = None,
    company: str | None = None,
    canal: str | None = None,
    cliente_excel: str | None = None,
    codigo_origen: str | None = None,
    vendedor_excel: str | None = None,
    unidad_negocio_excel: str | None = None,
    linea_excel: str | None = None,
    producto_excel: str | None = None,
    valor: float | None = None,
    comentario: str | None = None,
    id_unidad_negocio: int | None = None,
    id_linea: int | None = None,
    id_vendedor: int | None = None,
    id_cliente: int | None = None,
    id_producto: int | None = None,
    estatus_match: str = "pendiente",
    observaciones: str | None = None,
) -> int:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()

        sql = """
            insert into presupuesto_ventas_staging (
                id_carga,
                fila_excel,
                seccion,
                region,
                estatus_excel,
                company,
                canal,
                cliente_excel,
                codigo_origen,
                vendedor_excel,
                unidad_negocio_excel,
                linea_excel,
                producto_excel,
                precio,
                anio,
                mes,
                cantidad_kg,
                importe,
                valor,
                comentario,
                id_unidad_negocio,
                id_linea,
                id_vendedor,
                id_cliente,
                id_producto,
                estatus_match,
                observaciones
            )       
            values (
                %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
        """
        cur.execute(
            sql,
            (
                int(id_carga),
                int(fila_excel),
                str(seccion).strip() if seccion else None,
                str(region).strip() if region else None,
                str(estatus_excel).strip() if estatus_excel else None,
                str(company).strip() if company else None,
                str(canal).strip() if canal else None,
                str(cliente_excel).strip() if cliente_excel else None,
                str(codigo_origen).strip() if codigo_origen else None,
                str(vendedor_excel).strip() if vendedor_excel else None,
                str(unidad_negocio_excel).strip() if unidad_negocio_excel else None,
                str(linea_excel).strip() if linea_excel else None,
                str(producto_excel).strip(),
                float(precio or 0),
                int(anio),
                int(mes),
                float(cantidad_kg or 0),
                float(importe or 0),
                float(valor or 0),
                str(comentario).strip() if comentario else None,
                int(id_unidad_negocio) if id_unidad_negocio is not None else None,
                int(id_linea) if id_linea is not None else None,
                int(id_vendedor) if id_vendedor is not None else None,
                int(id_cliente) if id_cliente is not None else None,
                int(id_producto) if id_producto is not None else None,
                str(estatus_match).strip(),
                str(observaciones).strip() if observaciones else None
            ),
        )
        conn.commit()
        return int(cur.lastrowid or 0)
    finally:
        try:
            conn.close()
        except Exception:
            pass

def actualizar_match_staging_presupuesto_ventas_model(
    id_staging: int,
    id_unidad_negocio: int | None = None,
    id_linea: int | None = None,
    id_vendedor: int | None = None,
    id_cliente: int | None = None,
    id_producto: int | None = None,
    cve_prod: str | None = None,
    cve_clie: str | None = None,
    cve_vend: str | None = None,
    cve_linea: str | None = None,
    estatus_match: str | None = None,
    observaciones: str | None = None,
) -> bool:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()

        sets: list[str] = []
        params: list = []

        if id_unidad_negocio is not None:
            sets.append("id_unidad_negocio = %s")
            params.append(int(id_unidad_negocio))

        if id_linea is not None:
            sets.append("id_linea = %s")
            params.append(int(id_linea))

        if id_vendedor is not None:
            sets.append("id_vendedor = %s")
            params.append(int(id_vendedor))

        if id_cliente is not None:
            sets.append("id_cliente = %s")
            params.append(int(id_cliente))

        if id_producto is not None:
            sets.append("id_producto = %s")
            params.append(int(id_producto))

        if cve_prod is not None:
            sets.append("cve_prod = %s")
            params.append(str(cve_prod).strip() if cve_prod else None)

        if cve_clie is not None:
            sets.append("cve_clie = %s")
            params.append(str(cve_clie).strip() if cve_clie else None)

        if cve_vend is not None:
            sets.append("cve_vend = %s")
            params.append(str(cve_vend).strip() if cve_vend else None)

        if cve_linea is not None:
            sets.append("cve_linea = %s")
            params.append(str(cve_linea).strip() if cve_linea else None)

        if estatus_match is not None:
            sets.append("estatus_match = %s")
            params.append(str(estatus_match).strip())

        if observaciones is not None:
            sets.append("observaciones = %s")
            params.append(str(observaciones).strip() if observaciones else None)

        sets.append("updated_at = current_timestamp")

        sql = f"""
            update presupuesto_ventas_staging
            set {", ".join(sets)}
            where id_staging = %s
        """
        params.append(int(id_staging))

        cur.execute(sql, tuple(params))
        conn.commit()
        return True
    finally:
        try:
            conn.close()
        except Exception:
            pass

def obtener_staging_presupuesto_ventas_model(
    id_carga: int | None = None,
    estatus_match: str | None = None,
    anio: int | None = None,
    mes: int | None = None,
    id_producto: int | None = None,
    id_cliente: int | None = None,
    id_vendedor: int | None = None,
    id_unidad_negocio: int | None = None,
    limit: int = 5000,
) -> pd.DataFrame:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)

        sql = """
            select
                id_staging,
                id_carga,
                fila_excel,
                seccion,
                region,
                estatus_excel,
                company,
                canal,
                cliente_excel,
                codigo_origen,
                vendedor_excel,
                unidad_negocio_excel,
                linea_excel,
                producto_excel,
                precio,
                anio,
                mes,
                cantidad_kg,
                importe,
                valor,
                comentario,
                id_unidad_negocio,
                id_linea,
                id_vendedor,
                id_cliente,
                id_producto,
                cve_prod,
                cve_clie,
                cve_vend,
                cve_linea,
                estatus_match,
                observaciones,
                created_at,
                updated_at
            from presupuesto_ventas_staging
            where 1 = 1
        """
        params: list = []

        if id_carga is not None:
            sql += " and id_carga = %s"
            params.append(int(id_carga))

        if estatus_match is not None and str(estatus_match).strip() != "":
            sql += " and estatus_match = %s"
            params.append(str(estatus_match).strip())

        if anio is not None:
            sql += " and anio = %s"
            params.append(int(anio))

        if mes is not None:
            sql += " and mes = %s"
            params.append(int(mes))

        if id_producto is not None:
            sql += " and id_producto = %s"
            params.append(int(id_producto))

        if id_cliente is not None:
            sql += " and id_cliente = %s"
            params.append(int(id_cliente))

        if id_vendedor is not None:
            sql += " and id_vendedor = %s"
            params.append(int(id_vendedor))

        if id_unidad_negocio is not None:
            sql += " and id_unidad_negocio = %s"
            params.append(int(id_unidad_negocio))

        sql += " order by id_staging asc limit %s"
        params.append(int(limit))

        cur.execute(sql, tuple(params))
        rows = cur.fetchall() or []

        return pd.DataFrame(rows)

    finally:
        try:
            conn.close()
        except Exception:
            pass

def actualizar_cantidad_staging_presupuesto_ventas_model(
    id_staging: int,
    cantidad_kg: float | None = None,
    importe: float | None = None,
    precio: float | None = None,
    valor: float | None = None,
) -> bool:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()

        sets: list[str] = []
        params: list = []

        if cantidad_kg is not None:
            sets.append("cantidad_kg = %s")
            params.append(float(cantidad_kg))

        if importe is not None:
            sets.append("importe = %s")
            params.append(float(importe))

        if precio is not None:
            sets.append("precio = %s")
            params.append(float(precio))

        if valor is not None:
            sets.append("valor = %s")
            params.append(float(valor))

        if not sets:
            return False

        sets.append("updated_at = current_timestamp")

        sql = f"""
            update presupuesto_ventas_staging
            set {", ".join(sets)}
            where id_staging = %s
        """
        params.append(int(id_staging))

        cur.execute(sql, tuple(params))
        conn.commit()
        return True
    finally:
        try:
            conn.close()
        except Exception:
            pass


def obtener_resumen_staging_presupuesto_ventas_model(id_carga: int) -> pd.DataFrame:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)

        sql = """
            select
                estatus_match,
                count(*) as total_registros,
                sum(coalesce(cantidad_kg, 0)) as total_kg,
                sum(coalesce(importe, 0)) as total_importe
            from presupuesto_ventas_staging
            where id_carga = %s
            group by estatus_match
            order by estatus_match
        """
        cur.execute(sql, (int(id_carga),))
        rows = cur.fetchall() or []

        if not rows:
            return pd.DataFrame(columns=[
                "estatus_match",
                "total_registros",
                "total_kg",
                "total_importe",
            ])

        return pd.DataFrame(rows)

    finally:
        try:
            conn.close()
        except Exception:
            pass


def insertar_presupuesto_desde_staging_model(
    id_carga: int,
    usuario_id: int,
    solo_estatus_match: str = "completo",
    reemplazar_existentes: bool = False,
) -> int:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()

        if reemplazar_existentes:
            sql_delete = """
                delete p
                from presupuesto_ventas p
                inner join presupuesto_ventas_staging s
                    on p.anio = s.anio
                   and p.mes = s.mes
                   and p.id_unidad_negocio = s.id_unidad_negocio
                   and ifnull(p.id_vendedor, 0) = ifnull(s.id_vendedor, 0)
                   and ifnull(p.id_cliente, 0) = ifnull(s.id_cliente, 0)
                   and p.id_producto = s.id_producto
                where s.id_carga = %s
                  and s.estatus_match = %s
                  and s.id_unidad_negocio is not null
                  and (s.cve_prod is not null or s.id_producto is not null)
            """
            cur.execute(sql_delete, (int(id_carga), str(solo_estatus_match).strip()))

        sql_insert = """
            insert into presupuesto_ventas (
                id_carga,
                seccion,
                region,
                estatus_excel,
                anio,
                mes,
                id_unidad_negocio,
                id_linea,
                id_vendedor,
                id_cliente,
                id_producto,
                cve_prod,
                cve_clie,
                cve_vend,
                cve_linea,
                cantidad_kg,
                precio,
                importe,
                valor,
                company,
                codigo_origen,
                canal,
                comentario,
                estatus,
                usuario_id
            )
            select
                s.id_carga,
                s.seccion,
                s.region,
                s.estatus_excel,
                s.anio,
                s.mes,
                s.id_unidad_negocio,
                s.id_linea,
                s.id_vendedor,
                s.id_cliente,
                s.id_producto,
                s.cve_prod,
                s.cve_clie,
                s.cve_vend,
                s.cve_linea,
                s.cantidad_kg,
                s.precio,
                s.importe,
                s.valor,
                s.company,
                s.codigo_origen,
                s.canal,
                s.comentario,
                'activo',
                %s
            from presupuesto_ventas_staging s
            where s.id_carga = %s
              and s.estatus_match = %s
              and s.id_unidad_negocio is not null
              and (s.cve_prod is not null or s.id_producto is not null)
        """
        cur.execute(
            sql_insert,
            (
                int(usuario_id),
                int(id_carga),
                str(solo_estatus_match).strip(),
            ),
        )
        conn.commit()
        return int(cur.rowcount or 0)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def obtener_presupuesto_ventas_model(
    anio: int | None = None,
    mes: int | None = None,
    id_unidad_negocio: int | None = None,
    cve_linea: str | None = None,
    cve_vend: str | None = None,
    cve_clie: str | None = None,
    cve_prod: str | None = None,
    id_carga: int | None = None,
    usuario_id: int | None = None,
    solo_autorizados: bool = False,
    estatus: str = "activo",
    limit: int = 10000,
) -> pd.DataFrame:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)

        sql = """
            select
                id_presupuesto,
                id_carga,
                seccion,
                region,
                estatus_excel,
                anio,
                mes,
                id_unidad_negocio,
                cve_linea,
                cve_vend,
                cve_clie,
                cve_prod,
                company,
                cliente_excel,
                codigo_origen,
                producto_excel,
                cantidad_kg,
                precio,
                precio_venta,
                importe,
                valor,
                canal,
                comentario,
                estatus,
                usuario_id,
                created_at,
                updated_at
            from presupuesto_ventas
            where 1 = 1
        """
        params: list = []

        if estatus:
            sql += " and estatus = %s"
            params.append(str(estatus).strip())

        if id_carga is not None:
            sql += " and id_carga = %s"
            params.append(int(id_carga))

        if anio is not None:
            sql += " and anio = %s"
            params.append(int(anio))

        if mes is not None:
            sql += " and mes = %s"
            params.append(int(mes))

        if id_unidad_negocio is not None:
            sql += " and id_unidad_negocio = %s"
            params.append(int(id_unidad_negocio))

        if cve_linea:
            sql += " and cve_linea = %s"
            params.append(str(cve_linea).strip())

        if cve_vend:
            sql += " and cve_vend = %s"
            params.append(str(cve_vend).strip())

        if cve_clie:
            sql += " and cve_clie = %s"
            params.append(str(cve_clie).strip())

        if cve_prod:
            sql += " and cve_prod = %s"
            params.append(str(cve_prod).strip())

        if usuario_id is not None:
            sql += " and usuario_id = %s"
            params.append(int(usuario_id))

        if solo_autorizados:
            sql += """
                and exists (
                    select 1 from presupuesto_ventas_lineas l
                    where l.id_carga = presupuesto_ventas.id_carga
                      and l.company <=> presupuesto_ventas.company
                      and l.cliente_excel <=> presupuesto_ventas.cliente_excel
                      and l.codigo_origen <=> presupuesto_ventas.codigo_origen
                      and l.producto_excel = presupuesto_ventas.producto_excel
                      and l.estatus = 'autorizada'
                )
            """

        sql += " order by anio desc, mes desc, id_presupuesto desc limit %s"
        params.append(int(limit))

        cur.execute(sql, tuple(params))
        rows = cur.fetchall() or []

        if not rows:
            return pd.DataFrame(columns=[
                "id_presupuesto",
                "id_carga",
                "seccion",
                "region",
                "estatus_excel",
                "anio",
                "mes",
                "id_unidad_negocio",
                "cve_linea",
                "cve_vend",
                "cve_clie",
                "cve_prod",
                "company",
                "cliente_excel",
                "codigo_origen",
                "producto_excel",
                "cantidad_kg",
                "precio",
                "precio_venta",
                "importe",
                "valor",
                "canal",
                "comentario",
                "estatus",
                "usuario_id",
                "created_at",
                "updated_at",
            ])

        return pd.DataFrame(rows)

    finally:
        try:
            conn.close()
        except Exception:
            pass


def obtener_resumen_presupuesto_ventas_model(
    anio: int | None = None,
    id_unidad_negocio: int | None = None,
    cve_vend: str | None = None,
    cve_clie: str | None = None,
    cve_prod: str | None = None,
    estatus: str = "activo",
) -> pd.DataFrame:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)

        sql = """
            select
                anio,
                mes,
                id_unidad_negocio,
                cve_linea,
                cve_vend,
                cve_clie,
                cve_prod,
                sum(coalesce(cantidad_kg, 0)) as total_kg,
                avg(coalesce(precio, 0)) as precio_promedio,
                sum(coalesce(importe, 0)) as total_importe
            from presupuesto_ventas
            where 1 = 1
        """
        params: list = []

        if estatus:
            sql += " and estatus = %s"
            params.append(str(estatus).strip())

        if anio is not None:
            sql += " and anio = %s"
            params.append(int(anio))

        if id_unidad_negocio is not None:
            sql += " and id_unidad_negocio = %s"
            params.append(int(id_unidad_negocio))

        if cve_vend:
            sql += " and cve_vend = %s"
            params.append(str(cve_vend).strip())

        if cve_clie:
            sql += " and cve_clie = %s"
            params.append(str(cve_clie).strip())

        if cve_prod:
            sql += " and cve_prod = %s"
            params.append(str(cve_prod).strip())

        sql += """
            group by
                anio,
                mes,
                id_unidad_negocio,
                cve_linea,
                cve_vend,
                cve_clie,
                cve_prod
            order by
                anio desc,
                mes desc,
                id_unidad_negocio,
                cve_vend,
                cve_clie,
                cve_prod
        """

        cur.execute(sql, tuple(params))
        rows = cur.fetchall() or []

        if not rows:
            return pd.DataFrame(columns=[
                "anio",
                "mes",
                "id_unidad_negocio",
                "cve_linea",
                "cve_vend",
                "cve_clie",
                "cve_prod",
                "total_kg",
                "precio_promedio",
                "total_importe",
            ])

        return pd.DataFrame(rows)

    finally:
        try:
            conn.close()
        except Exception:
            pass


def insertar_presupuesto_ventas_desde_df_model(
    id_carga: int,
    usuario_id: int,
    df: pd.DataFrame,
) -> int:
    if df is None or df.empty:
        return 0

    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        sql = """
            insert into presupuesto_ventas (
                id_carga, seccion, region, estatus_excel,
                company, cliente_excel, codigo_origen, cve_prod, producto_excel,
                precio, precio_venta, anio, mes, valor, cantidad_kg, importe,
                canal, comentario, estatus, usuario_id
            ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'activo',%s)
        """
        total = 0
        for _, row in df.iterrows():
            cur.execute(sql, (
                int(id_carga),
                str(row.get("seccion") or "").strip() or None,
                str(row.get("region") or "").strip() or None,
                str(row.get("estatus_excel") or "").strip() or None,
                str(row.get("company") or "").strip() or None,
                str(row.get("cliente_excel") or "").strip() or None,
                str(row.get("codigo_origen") or "").strip() or None,
                str(row.get("cve_prod") or "").strip() or None,
                str(row.get("producto_excel") or "").strip() or None,
                float(row.get("precio") or 0),
                float(row.get("precio_venta") or 0),
                int(row.get("anio") or 0),
                int(row.get("mes") or 0),
                float(row.get("valor") or 0),
                float(row.get("cantidad_kg") or 0),
                float(row.get("importe") or 0),
                str(row.get("canal") or "").strip() or None,
                str(row.get("comentario") or "").strip() or None,
                int(usuario_id),
            ))
            total += 1
        conn.commit()
        return total
    finally:
        try:
            conn.close()
        except Exception:
            pass


def insertar_presupuesto_ventas_unitario_model(
    id_carga: int,
    seccion: str,
    region: str | None,
    anio: int,
    mes: int,
    company: str | None,
    cliente_excel: str | None,
    codigo_origen: str | None,
    producto_excel: str,
    cve_prod: str | None,
    estatus_excel: str | None,
    precio: float,
    valor: float,
    cantidad_kg: float,
    importe: float,
    usuario_id: int,
) -> int:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("""
            insert into presupuesto_ventas (
                id_carga, seccion, region, estatus_excel,
                company, cliente_excel, codigo_origen, cve_prod, producto_excel,
                precio, anio, mes, valor, cantidad_kg, importe,
                estatus, usuario_id
            ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'activo',%s)
        """, (
            int(id_carga),
            str(seccion).strip() if seccion else None,
            str(region).strip() if region else None,
            str(estatus_excel).strip() if estatus_excel else None,
            str(company).strip() if company else None,
            str(cliente_excel).strip() if cliente_excel else None,
            str(codigo_origen).strip() if codigo_origen else None,
            str(cve_prod).strip() if cve_prod else None,
            str(producto_excel).strip(),
            float(precio or 0),
            int(anio),
            int(mes),
            float(valor or 0),
            float(cantidad_kg or 0),
            float(importe or 0),
            int(usuario_id),
        ))
        conn.commit()
        return int(cur.lastrowid or 0)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def actualizar_presupuesto_ventas_model(
    id_presupuesto: int,
    valor: float | None = None,
    precio: float | None = None,
    cantidad_kg: float | None = None,
    importe: float | None = None,
    cliente_excel: str | None = None,
    producto_excel: str | None = None,
    company: str | None = None,
    codigo_origen: str | None = None,
    comentario: str | None = None,
    estatus_excel: str | None = None,
) -> bool:
    sets: list[str] = []
    params: list = []

    if valor is not None:
        sets.append("valor = %s"); params.append(float(valor))
    if precio is not None:
        sets.append("precio = %s"); params.append(float(precio))
    if cantidad_kg is not None:
        sets.append("cantidad_kg = %s"); params.append(float(cantidad_kg))
    if importe is not None:
        sets.append("importe = %s"); params.append(float(importe))
    if cliente_excel is not None:
        sets.append("cliente_excel = %s"); params.append(str(cliente_excel).strip())
    if producto_excel is not None:
        sets.append("producto_excel = %s"); params.append(str(producto_excel).strip())
    if company is not None:
        sets.append("company = %s"); params.append(str(company).strip())
    if codigo_origen is not None:
        sets.append("codigo_origen = %s"); params.append(str(codigo_origen).strip())
    if comentario is not None:
        sets.append("comentario = %s"); params.append(str(comentario).strip())
    if estatus_excel is not None:
        sets.append("estatus_excel = %s"); params.append(str(estatus_excel).strip())

    if not sets:
        return False

    sets.append("updated_at = current_timestamp")
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute(
            f"update presupuesto_ventas set {', '.join(sets)} where id_presupuesto = %s",
            tuple(params + [int(id_presupuesto)]),
        )
        conn.commit()
        return True
    finally:
        try:
            conn.close()
        except Exception:
            pass


def actualizar_cve_prod_presupuesto_ventas_model(
    id_carga: int,
    producto_excel: str,
    cliente_excel: str | None,
    codigo_origen: str | None,
    company: str | None,
    cve_prod: str | None,
) -> int:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        sql = (
            "update presupuesto_ventas "
            "set cve_prod = %s, updated_at = current_timestamp "
            "where id_carga = %s and producto_excel = %s"
        )
        params: list = [str(cve_prod).strip() if cve_prod else None, int(id_carga), str(producto_excel)]
        if cliente_excel is not None:
            sql += " and cliente_excel = %s"
            params.append(str(cliente_excel))
        else:
            sql += " and cliente_excel is null"
        if codigo_origen is not None:
            sql += " and codigo_origen = %s"
            params.append(str(codigo_origen))
        else:
            sql += " and codigo_origen is null"
        if company is not None:
            sql += " and company = %s"
            params.append(str(company))
        else:
            sql += " and company is null"
        cur.execute(sql, tuple(params))
        conn.commit()
        return cur.rowcount
    finally:
        try:
            conn.close()
        except Exception:
            pass


def guardar_presupuesto_ventas_batch_model(
    inserts: list[dict],
    updates: list[dict],
    cve_prod_updates: list[dict],
    identidad_updates: list[dict] | None = None,
) -> dict:
    """Aplica inserts/updates/cve_prod_updates/identidad_updates en una sola conexión/transacción.

    inserts: dicts con las mismas llaves que insertar_presupuesto_ventas_unitario_model.
    updates: dicts con id_presupuesto + cualquiera de valor/precio/precio_venta/cantidad_kg/importe/estatus_excel.
    cve_prod_updates: dicts con id_carga/producto_excel/cliente_excel/codigo_origen/company/cve_prod/cve_linea.
    identidad_updates: dicts con id_carga + company/cliente_excel/codigo_origen/producto_excel (nuevos)
        y *_orig (los valores actuales en BD, usados para localizar las filas a renombrar).
    """
    identidad_updates = identidad_updates or []
    total_insertados = total_actualizados = total_cve_prod = total_identidad = 0

    if not inserts and not updates and not cve_prod_updates and not identidad_updates:
        return {"insertados": 0, "actualizados": 0, "cve_prod_actualizados": 0, "identidad_actualizados": 0}

    conn = obtener_conexion()
    try:
        cur = conn.cursor()

        if inserts:
            sql_insert = """
                insert into presupuesto_ventas (
                    id_carga, seccion, region, estatus_excel,
                    company, cliente_excel, codigo_origen, cve_prod, cve_linea, producto_excel,
                    precio, precio_venta, anio, mes, valor, cantidad_kg, importe,
                    estatus, usuario_id
                ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'activo',%s)
            """
            rows = [
                (
                    int(r["id_carga"]),
                    str(r.get("seccion")).strip() if r.get("seccion") else None,
                    str(r.get("region")).strip() if r.get("region") else None,
                    str(r.get("estatus_excel")).strip() if r.get("estatus_excel") else None,
                    str(r.get("company")).strip() if r.get("company") else None,
                    str(r.get("cliente_excel")).strip() if r.get("cliente_excel") else None,
                    str(r.get("codigo_origen")).strip() if r.get("codigo_origen") else None,
                    str(r.get("cve_prod")).strip() if r.get("cve_prod") else None,
                    str(r.get("cve_linea")).strip() if r.get("cve_linea") else None,
                    str(r.get("producto_excel") or "").strip(),
                    float(r.get("precio") or 0),
                    float(r.get("precio_venta") or 0),
                    int(r["anio"]),
                    int(r["mes"]),
                    float(r.get("valor") or 0),
                    float(r.get("cantidad_kg") or 0),
                    float(r.get("importe") or 0),
                    int(r["usuario_id"]),
                )
                for r in inserts
            ]
            cur.executemany(sql_insert, rows)
            total_insertados = len(rows)

        for u in updates:
            sets: list[str] = []
            params: list = []
            for campo in ("valor", "precio", "precio_venta", "cantidad_kg", "importe"):
                if u.get(campo) is not None:
                    sets.append(f"{campo} = %s")
                    params.append(float(u[campo]))
            if u.get("estatus_excel") is not None:
                sets.append("estatus_excel = %s")
                params.append(str(u["estatus_excel"]).strip())
            if not sets:
                continue
            sets.append("updated_at = current_timestamp")
            cur.execute(
                f"update presupuesto_ventas set {', '.join(sets)} where id_presupuesto = %s",
                tuple(params + [int(u["id_presupuesto"])]),
            )
            total_actualizados += 1

        for c in cve_prod_updates:
            sql = (
                "update presupuesto_ventas "
                "set cve_prod = %s, cve_linea = %s, updated_at = current_timestamp "
                "where id_carga = %s and producto_excel = %s"
            )
            params = [
                str(c["cve_prod"]).strip() if c.get("cve_prod") else None,
                str(c["cve_linea"]).strip() if c.get("cve_linea") else None,
                int(c["id_carga"]),
                str(c.get("producto_excel") or ""),
            ]
            for campo in ("cliente_excel", "codigo_origen", "company"):
                valor = c.get(campo)
                if valor is not None:
                    sql += f" and {campo} = %s"
                    params.append(str(valor))
                else:
                    sql += f" and {campo} is null"
            cur.execute(sql, tuple(params))
            total_cve_prod += 1

        for idn in identidad_updates:
            sql = (
                "update presupuesto_ventas "
                "set company = %s, cliente_excel = %s, codigo_origen = %s, producto_excel = %s, "
                "updated_at = current_timestamp "
                "where id_carga = %s and producto_excel = %s"
            )
            params = [
                str(idn["company"]).strip() if idn.get("company") else None,
                str(idn["cliente_excel"]).strip() if idn.get("cliente_excel") else None,
                str(idn["codigo_origen"]).strip() if idn.get("codigo_origen") else None,
                str(idn.get("producto_excel") or "").strip(),
                int(idn["id_carga"]),
                str(idn.get("producto_excel_orig") or ""),
            ]
            for campo, campo_orig in (
                ("cliente_excel", "cliente_excel_orig"),
                ("codigo_origen", "codigo_origen_orig"),
                ("company", "company_orig"),
            ):
                valor = idn.get(campo_orig)
                if valor is not None:
                    sql += f" and {campo} = %s"
                    params.append(str(valor))
                else:
                    sql += f" and {campo} is null"
            cur.execute(sql, tuple(params))
            total_identidad += 1

        conn.commit()
        return {
            "insertados": total_insertados,
            "actualizados": total_actualizados,
            "cve_prod_actualizados": total_cve_prod,
            "identidad_actualizados": total_identidad,
        }
    finally:
        try:
            conn.close()
        except Exception:
            pass


def eliminar_presupuesto_ventas_por_registro_model(
    id_carga: int,
    seccion: str,
    region: str | None,
    producto_excel: str,
    cliente_excel: str | None,
    codigo_origen: str | None,
    company: str | None,
) -> int:
    """Elimina TODOS los meses (todo el registro de la fila pivoteada) que
    coincidan con la combinación company/cliente/código/producto en una carga+sección+región."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        sql = (
            "delete from presupuesto_ventas "
            "where id_carga = %s and seccion = %s and producto_excel = %s"
        )
        params: list = [int(id_carga), str(seccion), str(producto_excel)]

        if region is not None:
            sql += " and region = %s"; params.append(str(region))
        else:
            sql += " and region is null"
        if cliente_excel is not None:
            sql += " and cliente_excel = %s"; params.append(str(cliente_excel))
        else:
            sql += " and cliente_excel is null"
        if codigo_origen is not None:
            sql += " and codigo_origen = %s"; params.append(str(codigo_origen))
        else:
            sql += " and codigo_origen is null"
        if company is not None:
            sql += " and company = %s"; params.append(str(company))
        else:
            sql += " and company is null"

        cur.execute(sql, tuple(params))
        conn.commit()
        return cur.rowcount
    finally:
        try:
            conn.close()
        except Exception:
            pass


def eliminar_presupuesto_ventas_por_carga_model(id_carga: int) -> bool:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("delete from presupuesto_ventas where id_carga = %s", (int(id_carga),))
        conn.commit()
        return True
    finally:
        try:
            conn.close()
        except Exception:
            pass


def eliminar_carga_presupuesto_ventas_model(id_carga: int) -> bool:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("delete from presupuesto_ventas_cargas where id_carga = %s", (int(id_carga),))
        conn.commit()
        return True
    finally:
        try:
            conn.close()
        except Exception:
            pass


def desactivar_presupuesto_ventas_por_carga_model(id_carga: int) -> bool:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()

        sql = """
            update presupuesto_ventas
            set
                estatus = 'baja',
                updated_at = current_timestamp
            where id_carga = %s
        """
        cur.execute(sql, (int(id_carga),))
        conn.commit()
        return True

    finally:
        try:
            conn.close()
        except Exception:
            pass


# ── autorización por línea ──────────────────────────────────────────────────

def upsert_presupuesto_ventas_linea_model(
    id_carga: int,
    company: str | None,
    cliente_excel: str | None,
    codigo_origen: str | None,
    producto_excel: str,
    estatus: str,
    usuario_id: int,
) -> tuple[int, str | None]:
    """Crea la línea si no existe (estatus inicial 'captura') o actualiza su
    estatus si ya existe. Devuelve (linea_id, estatus_anterior)."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            select id, estatus from presupuesto_ventas_lineas
            where id_carga = %s
              and company <=> %s and cliente_excel <=> %s
              and codigo_origen <=> %s and producto_excel = %s
            """,
            (
                int(id_carga),
                str(company).strip() if company else None,
                str(cliente_excel).strip() if cliente_excel else None,
                str(codigo_origen).strip() if codigo_origen else None,
                str(producto_excel).strip(),
            ),
        )
        existente = cur.fetchone()

        if existente:
            linea_id = int(existente["id"])
            estatus_anterior = existente["estatus"]
            cur.execute(
                """
                update presupuesto_ventas_lineas
                set estatus = %s, actualizado_por = %s, fecha_actualizacion = current_timestamp
                where id = %s
                """,
                (str(estatus), int(usuario_id), linea_id),
            )
        else:
            estatus_anterior = None
            cur.execute(
                """
                insert into presupuesto_ventas_lineas (
                    id_carga, company, cliente_excel, codigo_origen, producto_excel,
                    estatus, creado_por, actualizado_por
                ) values (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    int(id_carga),
                    str(company).strip() if company else None,
                    str(cliente_excel).strip() if cliente_excel else None,
                    str(codigo_origen).strip() if codigo_origen else None,
                    str(producto_excel).strip(),
                    str(estatus),
                    int(usuario_id),
                    int(usuario_id),
                ),
            )
            linea_id = int(cur.lastrowid or 0)

        conn.commit()
        return linea_id, estatus_anterior
    finally:
        try:
            conn.close()
        except Exception:
            pass


def insertar_presupuesto_ventas_linea_estatus_model(
    linea_id: int,
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
            insert into presupuesto_ventas_lineas_estatus (
                linea_id, estatus_anterior, estatus_nuevo,
                usuario_id, usuario_nombre, usuario_email, comentario
            ) values (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                int(linea_id),
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


def obtener_presupuesto_ventas_lineas_model(id_carga: int) -> pd.DataFrame:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            select id, id_carga, company, cliente_excel, codigo_origen, producto_excel,
                   estatus, creado_por, fecha_creacion, actualizado_por, fecha_actualizacion
            from presupuesto_ventas_lineas
            where id_carga = %s
            """,
            (int(id_carga),),
        )
        rows = cur.fetchall() or []
        if not rows:
            return pd.DataFrame(columns=[
                "id", "id_carga", "company", "cliente_excel", "codigo_origen",
                "producto_excel", "estatus", "creado_por", "fecha_creacion",
                "actualizado_por", "fecha_actualizacion",
            ])
        return pd.DataFrame(rows)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def obtener_presupuesto_ventas_lineas_pendientes_model() -> pd.DataFrame:
    """Todas las líneas en estatus 'enviada' (pendientes de autorizar), de
    todos los usuarios/cargas, con datos de la carga para mostrarlas."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            select
                l.id, l.id_carga, l.company, l.cliente_excel, l.codigo_origen,
                l.producto_excel, l.estatus, l.creado_por, l.fecha_creacion,
                l.actualizado_por, l.fecha_actualizacion,
                c.nombre_archivo, c.anio, c.version, c.comentarios,
                c.usuario_id as carga_usuario_id
            from presupuesto_ventas_lineas l
            join presupuesto_ventas_cargas c on c.id_carga = l.id_carga
            where l.estatus = 'enviada'
            order by l.fecha_actualizacion asc
            """
        )
        rows = cur.fetchall() or []
        return pd.DataFrame(rows)
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ── reporte gerencial (link compartible) ──────────────────────────────────────

def insertar_reporte_ventas_model(
    token: str,
    id_carga: int,
    anio: int,
    mes_generado: int,
    usuario_id: int,
    usuario_nombre: Optional[str],
    html_contenido: str,
) -> int:
    """Guarda un snapshot del reporte gerencial (HTML ya renderizado) para
    que el link público (?rv=<token>, sin login) lo muestre sin volver a
    calcular los datos."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            insert into presupuesto_ventas_reportes (
                token, id_carga, anio, mes_generado, usuario_id, usuario_nombre, html_contenido
            ) values (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                str(token),
                int(id_carga),
                int(anio),
                int(mes_generado),
                int(usuario_id),
                str(usuario_nombre).strip() if usuario_nombre else None,
                str(html_contenido),
            ),
        )
        conn.commit()
        return int(cur.lastrowid or 0)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def obtener_reporte_ventas_por_token_model(token: str) -> Optional[dict]:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            select id, token, id_carga, anio, mes_generado, usuario_id,
                   usuario_nombre, html_contenido, creado_en
            from presupuesto_ventas_reportes
            where token = %s
            """,
            (str(token),),
        )
        row = cur.fetchone()
        return row or None
    finally:
        try:
            conn.close()
        except Exception:
            pass