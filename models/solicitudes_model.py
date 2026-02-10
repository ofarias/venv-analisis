# models/solicitudes_model.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from database.conexion import obtener_conexion


@dataclass
class SolicitudCabecera:
    id: int
    anio: int
    consecutivo: int
    folio: str
    empleado_id: int
    empleado_nombre: str
    clientes: Optional[str]
    ciudades: Optional[str]
    fecha_inicio: date
    fecha_fin: date
    hora_salida: Optional[time]
    hora_regreso: Optional[time]
    objetivo: Optional[str]
    estatus: str


def get_usuarios_activos() -> List[Dict[str, Any]]:
    conn = obtener_conexion()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        select id, username, nombre, email, rol, estatus
        from usuarios
        where estatus = 'Activo'
        order by nombre
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def _fetchone_scalar(sql: str, params: Tuple[Any, ...]) -> Any:
    conn = obtener_conexion()
    cur = conn.cursor()
    cur.execute(sql, params)
    row = cur.fetchone()
    cur.close()
    conn.close()
    return None if row is None else row[0]


def obtener_siguiente_consecutivo(anio: int) -> int:
    return int(_fetchone_scalar(
        """
        select coalesce(max(consecutivo), 0) + 1
        from solicitudes
        where anio = %s
        """,
        (anio,)
    ) or 1)


def insertar_solicitud_cabecera(
    *,
    anio: int,
    consecutivo: int,
    folio: str,
    empleado_id: int,
    empleado_nombre: str,
    clientes: Optional[str],
    ciudades: Optional[str],
    fecha_inicio: date,
    fecha_fin: date,
    hora_salida: Optional[time],
    hora_regreso: Optional[time],
    objetivo: Optional[str],
    creado_por: int,
) -> int:
    conn = obtener_conexion()
    cur = conn.cursor()
    cur.execute("""
        insert into solicitudes
        (anio, consecutivo, folio,
         empleado_id, empleado_nombre,
         clientes, ciudades,
         fecha_inicio, fecha_fin, hora_salida, hora_regreso,
         objetivo, estatus,
         creado_por)
        values
        (%s, %s, %s,
         %s, %s,
         %s, %s,
         %s, %s, %s, %s,
         %s, 'captura',
         %s)
    """, (
        anio, consecutivo, folio,
        empleado_id, empleado_nombre,
        clientes, ciudades,
        fecha_inicio, fecha_fin, hora_salida, hora_regreso,
        objetivo,
        creado_por
    ))
    solicitud_id = cur.lastrowid
    conn.commit()
    cur.close()
    conn.close()
    return int(solicitud_id)


def actualizar_solicitud_cabecera(
    *,
    solicitud_id: int,
    empleado_id: int,
    empleado_nombre: str,
    clientes: Optional[str],
    ciudades: Optional[str],
    fecha_inicio: date,
    fecha_fin: date,
    hora_salida: Optional[time],
    hora_regreso: Optional[time],
    objetivo: Optional[str],
    actualizado_por: int,
) -> None:
    conn = obtener_conexion()
    cur = conn.cursor()
    cur.execute("""
        update solicitudes
        set empleado_id = %s,
            empleado_nombre = %s,
            clientes = %s,
            ciudades = %s,
            fecha_inicio = %s,
            fecha_fin = %s,
            hora_salida = %s,
            hora_regreso = %s,
            objetivo = %s,
            actualizado_por = %s
        where id = %s
    """, (
        empleado_id,
        empleado_nombre,
        clientes,
        ciudades,
        fecha_inicio,
        fecha_fin,
        hora_salida,
        hora_regreso,
        objetivo,
        actualizado_por,
        solicitud_id
    ))
    conn.commit()
    cur.close()
    conn.close()


def actualizar_estatus_solicitud(
    *,
    solicitud_id: int,
    estatus: str,
    actualizado_por: int,
) -> None:
    conn = obtener_conexion()
    cur = conn.cursor()
    cur.execute("""
        update solicitudes
        set estatus = %s,
            actualizado_por = %s
        where id = %s
    """, (estatus, actualizado_por, solicitud_id))
    conn.commit()
    cur.close()
    conn.close()


def get_solicitudes_df(
    *,
    folio_like: str = "",
    estatus: str = "",
    anio: Optional[int] = None,
    empleado_id: Optional[int] = None,
    limit: int = 200
) -> List[Dict[str, Any]]:
    conn = obtener_conexion()
    cur = conn.cursor(dictionary=True)

    where = ["1=1"]
    params: List[Any] = []

    if folio_like.strip():
        where.append("folio like %s")
        params.append(f"%{folio_like.strip()}%")

    if estatus.strip():
        where.append("estatus = %s")
        params.append(estatus.strip())

    if anio is not None:
        where.append("anio = %s")
        params.append(int(anio))

    if empleado_id is not None:
        where.append("empleado_id = %s")
        params.append(int(empleado_id))

    sql = f"""
        select
          id, folio, anio, consecutivo,
          empleado_nombre, clientes, ciudades,
          fecha_inicio, fecha_fin, hora_salida, hora_regreso,
          estatus, fecha_creacion
        from solicitudes
        where {' and '.join(where)}
        order by id desc
        limit {int(limit)}
    """

    cur.execute(sql, tuple(params))
    rows = cur.fetchall()

    cur.close()
    conn.close()
    return rows


def get_solicitud_by_id(solicitud_id: int) -> Optional[Dict[str, Any]]:
    conn = obtener_conexion()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        select *
        from solicitudes
        where id = %s
    """, (solicitud_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row


def get_detalle_by_solicitud(solicitud_id: int) -> List[Dict[str, Any]]:
    conn = obtener_conexion()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        select
          id, solicitud_id, renglon,
          fecha_gasto, tipo_gasto, descripcion,
          cantidad, precio_unitario, subtotal,
          iva, ieps, ret_iva, ret_isr, total,
          moneda, proveedor, uuid, referencia, archivo_url, notas,
          fecha_creacion
        from solicitudes_detalle
        where solicitud_id = %s
        order by renglon
    """, (solicitud_id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def delete_detalle_ids(solicitud_id: int, detalle_ids: List[int]) -> None:
    if not detalle_ids:
        return
    conn = obtener_conexion()
    cur = conn.cursor()
    placeholders = ",".join(["%s"] * len(detalle_ids))
    params: List[Any] = [solicitud_id] + detalle_ids
    cur.execute(f"""
        delete from solicitudes_detalle
        where solicitud_id = %s
          and id in ({placeholders})
    """, tuple(params))
    conn.commit()
    cur.close()
    conn.close()


def _is_nan(v) -> bool:
    try:
        # pandas/numpy nan
        return v != v
    except Exception:
        return False


def _none_if_nan(v):
    return None if v is None or v == "" or _is_nan(v) else v


def _next_renglon(cur, solicitud_id: int) -> int:
    cur.execute("""
        select coalesce(max(renglon), 0) + 1
        from solicitudes_detalle
        where solicitud_id = %s
    """, (solicitud_id,))
    row = cur.fetchone()
    return int(row[0] if row else 1)


def upsert_detalle_rows(
    *,
    solicitud_id: int,
    rows: List[Dict[str, Any]],
    creado_por: int
) -> None:
    conn = obtener_conexion()
    cur = conn.cursor()

    for r in rows:
        detalle_id = _none_if_nan(r.get("id"))

        # normaliza nan -> None en todos los campos que puedan venir del editor
        fecha_gasto = _none_if_nan(r.get("fecha_gasto"))
        tipo_gasto = (_none_if_nan(r.get("tipo_gasto")) or "").strip()
        descripcion = (_none_if_nan(r.get("descripcion")) or "").strip() or None
        moneda = (_none_if_nan(r.get("moneda")) or "mxn").strip().lower()
        proveedor = (_none_if_nan(r.get("proveedor")) or "").strip() or None
        uuid = (_none_if_nan(r.get("uuid")) or "").strip() or None
        referencia = (_none_if_nan(r.get("referencia")) or "").strip() or None
        archivo_url = (_none_if_nan(r.get("archivo_url")) or "").strip() or None
        notas = (_none_if_nan(r.get("notas")) or "").strip() or None

        cantidad = _none_if_nan(r.get("cantidad"))
        precio_unitario = _none_if_nan(r.get("precio_unitario"))
        subtotal = _none_if_nan(r.get("subtotal"))
        iva = _none_if_nan(r.get("iva"))
        ieps = _none_if_nan(r.get("ieps"))
        ret_iva = _none_if_nan(r.get("ret_iva"))
        ret_isr = _none_if_nan(r.get("ret_isr"))
        total = _none_if_nan(r.get("total"))

        # si es nuevo, asignar renglon automático
        if detalle_id is None:
            renglon = _next_renglon(cur, solicitud_id)

            cur.execute("""
                insert into solicitudes_detalle
                (solicitud_id, renglon, fecha_gasto, tipo_gasto, descripcion,
                 cantidad, precio_unitario, subtotal,
                 iva, ieps, ret_iva, ret_isr, total,
                 moneda, proveedor, uuid, referencia, archivo_url, notas,
                 creado_por)
                values
                (%s, %s, %s, %s, %s,
                 %s, %s, %s,
                 %s, %s, %s, %s, %s,
                 %s, %s, %s, %s, %s, %s,
                 %s)
            """, (
                solicitud_id,
                renglon,
                fecha_gasto,
                tipo_gasto,
                descripcion,
                cantidad,
                precio_unitario,
                subtotal,
                iva,
                ieps,
                ret_iva,
                ret_isr,
                total,
                moneda,
                proveedor,
                uuid,
                referencia,
                archivo_url,
                notas,
                creado_por
            ))
        else:
            # update: no tocar renglon
            cur.execute("""
                update solicitudes_detalle
                set fecha_gasto = %s,
                    tipo_gasto = %s,
                    descripcion = %s,
                    cantidad = %s,
                    precio_unitario = %s,
                    subtotal = %s,
                    iva = %s,
                    ieps = %s,
                    ret_iva = %s,
                    ret_isr = %s,
                    total = %s,
                    moneda = %s,
                    proveedor = %s,
                    uuid = %s,
                    referencia = %s,
                    archivo_url = %s,
                    notas = %s
                where id = %s
                  and solicitud_id = %s
            """, (
                fecha_gasto,
                tipo_gasto,
                descripcion,
                cantidad,
                precio_unitario,
                subtotal,
                iva,
                ieps,
                ret_iva,
                ret_isr,
                total,
                moneda,
                proveedor,
                uuid,
                referencia,
                archivo_url,
                notas,
                int(detalle_id),
                int(solicitud_id)
            ))

    conn.commit()
    cur.close()
    conn.close()