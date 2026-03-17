# models/solicitudes_model.py

from __future__ import annotations
import fdb
import streamlit as st
from dataclasses import dataclass
from datetime import date, time
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from database.conexion import obtener_conexion

from models.ada_model import (
    obtener_datoscfd_por_uuid as obtener_datoscfd_por_uuid_ada,
    obtener_xml_por_uuid as obtener_xml_por_uuid_ada,
    obtener_xmls_por_uuids as obtener_xmls_por_uuids_ada,
)

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
    cur.execute(
        """
        select
          d.id, d.solicitud_id, d.renglon,
          d.fecha_gasto,
          d.concepto,
          d.descripcion,
          d.cantidad,
          d.precio_unitario,
          d.importe,
          d.impuesto1,
          d.impuesto2,
          d.impuesto3,
          d.impuesto4,
          d.subtotal,
          d.iva,
          d.ieps,
          d.ret_iva,
          d.ret_isr,
          d.total,
          d.moneda,
          d.proveedor,
          d.receptor,
          d.serie,
          d.folio,
          d.version,
          d.moneda_xml,
          d.tipo_cambio,
          d.estado_sat,
          d.forma_pago,
          d.metodo_pago,
          d.tipo_comprobante,
          d.uso_cfdi,
          d.subtotal_xml,
          d.iva_xml,
          d.total_xml,
          d.uuid,
          d.referencia,
          d.archivo_url,
          d.notas,
          d.presupuesto_id,
          d.presupuesto_detalle_id,
          d.usuario_forma_pago_id,
          d.fecha_creacion,

          coalesce(scg.fiscales, 0) as fiscales,
          coalesce(scg.prepago, 0) as prepago,

          case
            when d.uuid is not null
             and trim(d.uuid) <> ''
             and exists (
                select 1
                from DATOSCFD_PDF p
                where upper(trim(p.UUID)) = upper(trim(d.uuid))
                limit 1
             )
            then 1 else 0
          end as tiene_pdf,

          coalesce((
            select round(sum(u.porcentaje), 6)
            from solicitudes_detalle_un u
            where u.solicitud_detalle_id = d.id
          ), 0) as total_unidades

        from solicitudes_detalle d
        left join solicitud_concepto_gasto scg
          on trim(scg.concepto) = trim(d.concepto)
        where d.solicitud_id = %s
        order by d.renglon
        """,
        (solicitud_id,),
    )
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

def get_conceptos_gasto_rows(activo: int = 1):
    conn = obtener_conexion()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        select id, concepto, cuenta, prepago, fiscales
        from solicitud_concepto_gasto
        where (%s is null) or (activo = %s)
        order by concepto
        """,
        (activo, activo),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    return rows


def _is_nan(v) -> bool:
    try:
        return v != v
    except Exception:
        return False


def _none_if_nan(v):
    return None if v is None or v == "" or _is_nan(v) else v


def _next_renglon(cur, solicitud_id: int) -> int:
    cur.execute(
        """
        select coalesce(max(renglon), 0) + 1
        from solicitudes_detalle
        where solicitud_id = %s
        """,
        (solicitud_id,),
    )
    row = cur.fetchone()
    return int(row[0] if row else 1)


def get_datoscfd_by_uuid(uuid: str, secrets=None) -> dict | None:
    uuid_norm = ("" if uuid is None else str(uuid)).strip().upper()
    if not uuid_norm:
        return None

    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("select * from DATOSCFD where upper(UUID) = %s limit 1", (uuid_norm,))
        row = cur.fetchone()
        if row:
            return row
    finally:
        try:
            conn.close()
        except Exception:
            pass

    if secrets is None:
        return None

    return obtener_datoscfd_por_uuid_ada(secrets, uuid_norm)


def upsert_detalle_rows(
    *,
    solicitud_id: int,
    rows: List[Dict[str, Any]],
    creado_por: int
) -> None:

    conn = obtener_conexion()
    cur = conn.cursor()

    try:
        for r in rows:
            detalle_id = _none_if_nan(r.get("id"))

            fecha_gasto = _none_if_nan(r.get("fecha_gasto"))
            concepto = (_none_if_nan(r.get("concepto")) or "").strip()
            descripcion = (_none_if_nan(r.get("descripcion")) or "").strip() or None

            cantidad = _none_if_nan(r.get("cantidad"))
            precio_unitario = _none_if_nan(r.get("precio_unitario"))
            importe = _none_if_nan(r.get("importe"))
            impuesto1 = _none_if_nan(r.get("impuesto1"))
            impuesto2 = _none_if_nan(r.get("impuesto2"))
            impuesto3 = _none_if_nan(r.get("impuesto3"))
            impuesto4 = _none_if_nan(r.get("impuesto4"))

            subtotal = _none_if_nan(r.get("subtotal"))
            iva = _none_if_nan(r.get("iva"))
            ieps = _none_if_nan(r.get("ieps"))
            ret_iva = _none_if_nan(r.get("ret_iva"))
            ret_isr = _none_if_nan(r.get("ret_isr"))
            total = _none_if_nan(r.get("total"))

            moneda = (_none_if_nan(r.get("moneda")) or "mxn").strip().lower()
            proveedor = (_none_if_nan(r.get("proveedor")) or "").strip() or None
            receptor = (_none_if_nan(r.get("receptor")) or "").strip() or None

            serie = (_none_if_nan(r.get("serie")) or "").strip() or None
            folio = (_none_if_nan(r.get("folio")) or "").strip() or None
            version = (_none_if_nan(r.get("version")) or "").strip() or None
            moneda_xml = (_none_if_nan(r.get("moneda_xml")) or "").strip() or None
            tipo_cambio = _none_if_nan(r.get("tipo_cambio"))
            estado_sat = (_none_if_nan(r.get("estado_sat")) or "").strip() or None
            forma_pago = (_none_if_nan(r.get("forma_pago")) or "").strip() or None
            metodo_pago = (_none_if_nan(r.get("metodo_pago")) or "").strip() or None
            tipo_comprobante = (_none_if_nan(r.get("tipo_comprobante")) or "").strip() or None
            uso_cfdi = (_none_if_nan(r.get("uso_cfdi")) or "").strip() or None
            subtotal_xml = _none_if_nan(r.get("subtotal_xml"))
            iva_xml = _none_if_nan(r.get("iva_xml"))
            total_xml = _none_if_nan(r.get("total_xml"))

            uuid = (_none_if_nan(r.get("uuid")) or "").strip() or None
            referencia = (_none_if_nan(r.get("referencia")) or "").strip() or None
            archivo_url = (_none_if_nan(r.get("archivo_url")) or "").strip() or None
            notas = (_none_if_nan(r.get("notas")) or "").strip() or None

            presupuesto_id = _none_if_nan(r.get("presupuesto_id"))
            presupuesto_detalle_id = _none_if_nan(r.get("presupuesto_detalle_id"))

            usuario_forma_pago_id = _none_if_nan(r.get("usuario_forma_pago_id"))
            
            # nuevo campo rfc emisor
            rfce = (_none_if_nan(r.get("rfce")) or "").strip() or None

            if detalle_id is None:
                renglon = _next_renglon(cur, solicitud_id)
                cur.execute(
                    """
                    insert into solicitudes_detalle
                    (
                      solicitud_id, renglon,
                      fecha_gasto, concepto, descripcion,
                      cantidad, precio_unitario,
                      importe, impuesto1, impuesto2, impuesto3, impuesto4,
                      subtotal, iva, ieps, ret_iva, ret_isr, total,
                      moneda, proveedor, receptor,
                      serie, folio, version, moneda_xml, tipo_cambio, estado_sat,
                      forma_pago, metodo_pago, tipo_comprobante, uso_cfdi,
                      subtotal_xml, iva_xml, total_xml,
                      uuid, referencia, archivo_url, notas,
                      presupuesto_id, presupuesto_detalle_id,
                      usuario_forma_pago_id,
                      creado_por, 
                      rfce
                    )
                    values
                    (
                      %s, %s,
                      %s, %s, %s,
                      %s, %s,
                      %s, %s, %s, %s, %s,
                      %s, %s, %s, %s, %s, %s,
                      %s, %s, %s,
                      %s, %s, %s, %s, %s, %s,
                      %s, %s, %s, %s,
                      %s, %s, %s,
                      %s, %s, %s, %s,
                      %s, %s,
                      %s,
                      %s,
                      %s
                    )
                    """,
                    (
                        solicitud_id, renglon,
                        fecha_gasto, concepto, descripcion,
                        cantidad, precio_unitario,
                        importe, impuesto1, impuesto2, impuesto3, impuesto4,
                        subtotal, iva, ieps, ret_iva, ret_isr, total,
                        moneda, proveedor, receptor,
                        serie, folio, version, moneda_xml, tipo_cambio, estado_sat,
                        forma_pago, metodo_pago, tipo_comprobante, uso_cfdi,
                        subtotal_xml, iva_xml, total_xml,
                        uuid, referencia, archivo_url, notas,
                        presupuesto_id, presupuesto_detalle_id,
                        usuario_forma_pago_id,
                        creado_por,
                        rfce
                    ),
                )
            else:
                cur.execute(
                    """
                    update solicitudes_detalle
                    set
                      fecha_gasto = %s,
                      concepto = %s,
                      descripcion = %s,
                      cantidad = %s,
                      precio_unitario = %s,

                      importe = %s,
                      impuesto1 = %s,
                      impuesto2 = %s,
                      impuesto3 = %s,
                      impuesto4 = %s,

                      subtotal = %s,
                      iva = %s,
                      ieps = %s,
                      ret_iva = %s,
                      ret_isr = %s,
                      total = %s,

                      moneda = %s,
                      proveedor = %s,
                      receptor = %s,

                      serie = %s,
                      folio = %s,
                      version = %s,
                      moneda_xml = %s,
                      tipo_cambio = %s,
                      estado_sat = %s,
                      forma_pago = %s,
                      metodo_pago = %s,
                      tipo_comprobante = %s,
                      uso_cfdi = %s,
                      subtotal_xml = %s,
                      iva_xml = %s,
                      total_xml = %s,

                      uuid = %s,
                      referencia = %s,
                      archivo_url = %s,
                      notas = %s,

                      presupuesto_id = %s,
                      presupuesto_detalle_id = %s,
                      usuario_forma_pago_id = %s,
                      rfce = %s
                    where id = %s
                      and solicitud_id = %s
                    """,
                    (
                        fecha_gasto,
                        concepto,
                        descripcion,
                        cantidad,
                        precio_unitario,
                        importe,
                        impuesto1,
                        impuesto2,
                        impuesto3,
                        impuesto4,
                        subtotal,
                        iva,
                        ieps,
                        ret_iva,
                        ret_isr,
                        total,
                        moneda,
                        proveedor,
                        receptor,
                        serie,
                        folio,
                        version,
                        moneda_xml,
                        tipo_cambio,
                        estado_sat,
                        forma_pago,
                        metodo_pago,
                        tipo_comprobante,
                        uso_cfdi,
                        subtotal_xml,
                        iva_xml,
                        total_xml,
                        uuid,
                        referencia,
                        archivo_url,
                        notas,
                        presupuesto_id,
                        presupuesto_detalle_id,
                        usuario_forma_pago_id,
                        rfce, 
                        int(detalle_id),
                        int(solicitud_id),
                    ),
                )

        conn.commit()

    except Exception as e:
        msg = str(e).lower()
        if "duplicate" in msg and ("uk_solicitudes_detalle_uuid" in msg or "uuid" in msg):
            raise ValueError("no se puede guardar: el uuid ya fue usado en otra solicitud.") from e
        raise
    finally:
        try:
            cur.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass


def uuid_ya_usado(uuid: str, exclude_solicitud_id: int | None = None) -> dict | None:
    uuid_norm = ("" if uuid is None else str(uuid)).strip().upper()
    if not uuid_norm:
        return None

    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)

        sql = """
            select
              d.id as detalle_id,
              d.solicitud_id,
              s.folio,
              s.empleado_nombre,
              s.estatus,
              d.fecha_creacion
            from solicitudes_detalle d
            join solicitudes s on s.id = d.solicitud_id
            where upper(trim(d.uuid)) = %s
        """
        params = [uuid_norm]

        if exclude_solicitud_id is not None:
            sql += " and d.solicitud_id <> %s"
            params.append(int(exclude_solicitud_id))

        sql += " limit 1"

        cur.execute(sql, tuple(params))
        return cur.fetchone()
    finally:
        try:
            conn.close()
        except Exception:
            pass


def get_conceptos_catalogo_rows(incluir_inactivos: bool = False):
    conn = obtener_conexion()
    cur = conn.cursor(dictionary=True)

    if incluir_inactivos:
        cur.execute(
            """
            select id, concepto, cuenta, fiscales, prepago, activo, created_at, updated_at
            from solicitud_concepto_gasto
            order by id
            """
        )
    else:
        cur.execute(
            """
            select id, concepto, cuenta, fiscales, prepago, activo, created_at, updated_at
            from solicitud_concepto_gasto
            where activo = 1
            order by id
            """
        )

    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def upsert_concepto_catalogo_rows(rows: list[dict], usuario_id: int):
    if not rows:
        return

    conn = obtener_conexion()
    cur = conn.cursor()
    try:
        for r in rows:
            _id = r.get("id")
            try:
                if _id is not None and _id != "":
                    _id = int(float(_id))
                else:
                    _id = None
            except Exception:
                _id = None
            concepto = (r.get("concepto") or "").strip()
            cuenta = (r.get("cuenta") or "").strip()
            fiscales = int(r.get("fiscales") or 0)
            prepago = int(r.get("prepago") or 0)
            activo = int(r.get("activo") or 0)

            if _id is None or _id == 0:
                cur.execute(
                    """
                    insert into solicitud_concepto_gasto (concepto, cuenta, fiscales, prepago, activo, created_at, updated_at)
                    values (%s, %s, %s, %s, %s, now(), now())
                    """,
                    (concepto, cuenta, fiscales, prepago, activo),
                )
            else:
                cur.execute(
                    """
                    update solicitud_concepto_gasto
                    set concepto = %s,
                        cuenta = %s,
                        fiscales = %s,
                        prepago = %s,
                        activo = %s,
                        updated_at = now()
                    where id = %s
                    """,
                    (concepto, cuenta, fiscales, prepago, activo, int(_id)),
                )

        conn.commit()
    finally:
        try:
            cur.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass


def desactivar_conceptos_catalogo(ids: list[int], usuario_id: int):
    if not ids:
        return

    conn = obtener_conexion()
    cur = conn.cursor()
    try:
        placeholders = ",".join(["%s"] * len(ids))
        cur.execute(
            f"""
            update solicitud_concepto_gasto
            set activo = 0,
                updated_at = now()
            where id in ({placeholders})
            """,
            tuple(int(x) for x in ids),
        )
        conn.commit()
    finally:
        try:
            cur.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass


def get_formas_pago_usuario_rows(id_usuario: int) -> list[dict]:
    conn = obtener_conexion()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        select
          id,
          id_usuario,
          tipo,
          entidad_bancaria,
          moneda,
          ultimos4,
          numero_tarjeta_enmascarado,
          vigencia_inicio,
          vigencia_fin,
          activo,
          concat(
            lower(tipo),
            case when entidad_bancaria is not null and trim(entidad_bancaria) <> '' then concat(' | ', lower(entidad_bancaria)) else '' end,
            ' | ', lower(moneda),
            case
              when numero_tarjeta_enmascarado is not null and trim(numero_tarjeta_enmascarado) <> '' then concat(' | ', numero_tarjeta_enmascarado)
              when ultimos4 is not null and trim(ultimos4) <> '' then concat(' | **** ', ultimos4)
              else ''
            end
          ) as etiqueta
        from usuarios_forma_pago
        where id_usuario = %s
          and activo = 1
        order by tipo, entidad_bancaria, moneda, id desc
        """,
        (int(id_usuario),),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def _mask_tarjeta(num: str) -> tuple[str | None, str | None]:
    """
    regresa (ultimos4, enmascarado) a partir del numero (puede venir con espacios/guiones)
    """
    if not num:
        return None, None
    s = str(num).strip()
    # deja solo dígitos
    s = "".join(ch for ch in s if ch.isdigit())
    if not s:
        return None, None
    u4 = s[-4:] if len(s) >= 4 else s
    return u4, f"**** **** **** {u4}"


def upsert_formas_pago_usuario_rows(id_usuario: int, rows: list[dict], usuario_id: int) -> None:
    conn = obtener_conexion()
    cur = conn.cursor()
    try:
        for r in rows:
            _id = _none_if_nan(r.get("id"))
            tipo = (r.get("tipo") or "").strip()
            if not tipo:
                continue

            entidad_bancaria = (r.get("entidad_bancaria") or "").strip() or None
            moneda = (r.get("moneda") or "MXN").strip().upper()
            cuenta_contable = (r.get("cuenta_contable") or "").strip() or None

            ultimos4 = (r.get("ultimos4") or "").strip() or None
            numero_tarjeta_enmascarado = (r.get("numero_tarjeta_enmascarado") or "").strip() or None

            vigencia_inicio = _none_if_nan(r.get("vigencia_inicio"))
            vigencia_fin = _none_if_nan(r.get("vigencia_fin"))

            activo = 1 if int(r.get("activo") or 0) == 1 else 0

            if _id is None:
                cur.execute(
                    """
                    insert into usuarios_forma_pago
                    (id_usuario, tipo, entidad_bancaria, moneda, cuenta_contable,
                     ultimos4, numero_tarjeta_enmascarado, vigencia_inicio, vigencia_fin, activo,
                     created_at, updated_at)
                    values
                    (%s, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s,
                     now(), now())
                    """,
                    (
                        int(id_usuario), tipo, entidad_bancaria, moneda, cuenta_contable,
                        ultimos4, numero_tarjeta_enmascarado, vigencia_inicio, vigencia_fin, activo
                    ),
                )
            else:
                cur.execute(
                    """
                    update usuarios_forma_pago
                    set
                      tipo = %s,
                      entidad_bancaria = %s,
                      moneda = %s,
                      cuenta_contable = %s,
                      ultimos4 = %s,
                      numero_tarjeta_enmascarado = %s,
                      vigencia_inicio = %s,
                      vigencia_fin = %s,
                      activo = %s,
                      updated_at = now()
                    where id = %s
                      and id_usuario = %s
                    """,
                    (
                        tipo, entidad_bancaria, moneda, cuenta_contable,
                        ultimos4, numero_tarjeta_enmascarado,
                        vigencia_inicio, vigencia_fin, activo,
                        int(_id), int(id_usuario)
                    ),
                )

        conn.commit()
    finally:
        try:
            cur.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass


def desactivar_formas_pago_usuario_ids(id_usuario: int, ids: list[int], usuario_id: int) -> None:
    if not ids:
        return
    conn = obtener_conexion()
    cur = conn.cursor()
    try:
        placeholders = ",".join(["%s"] * len(ids))
        cur.execute(
            f"""
            update usuarios_forma_pago
            set activo = 0,
                updated_at = now()
            where id_usuario = %s
              and id in ({placeholders})
            """,
            tuple([int(id_usuario)] + [int(x) for x in ids]),
        )
        conn.commit()
    finally:
        try:
            cur.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

from datetime import datetime
from database.conexion import obtener_conexion

def eliminar_solicitud_model(*, solicitud_id: int, usuario_id: int) -> None:
    conn = obtener_conexion()
    cur = conn.cursor(dictionary=True)
    #st.write(f"Intentando eliminar solicitud_id={solicitud_id} por usuario_id={usuario_id} a las {datetime.now()}")
    #st.stop()
    try:
        cur.execute("select id, estatus from solicitudes where id = %s", (solicitud_id,))
        row = cur.fetchone()
        if not row:
            raise ValueError("la solicitud no existe")

        estatus = (row.get("estatus") or "").strip().lower()
        if estatus != "captura":
            raise ValueError("solo se puede eliminar si el estatus es 'captura'")

        # primero detalle (si tienes FK)
        #cur.execute("update solicitudes_detalle set activo = 0 where solicitud_id = %s", (solicitud_id,))
        cur.execute("update solicitudes set estatus = 'eliminada', actualizado_por = %s, fecha_actualizacion = now() where id = %s", (usuario_id, solicitud_id))

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        try:
            cur.close()
        except Exception:
            pass
        conn.close()

def get_dispersion_flags(solicitud_id: int) -> Dict[str, Any]:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)
        sql = """
            SELECT
              COALESCE(conta_disp_gasolina, 0) AS disp_gasolina,
              COALESCE(conta_disp_prepagados, 0) AS disp_prepagados
            FROM solicitudes
            WHERE id = %s
            LIMIT 1
        """
        cur.execute(sql, (int(solicitud_id),))
        row = cur.fetchone() or {}
        return row
    finally:
        try:
            conn.close()
        except Exception:
            pass


def set_dispersion_flag(solicitud_id: int, flag: str, value: bool, user_id: int) -> bool:
    flag = (flag or "").strip().lower()
    if flag not in ("disp_gasolina", "disp_prepagados"):
        return False

    col = "conta_disp_gasolina" if flag == "disp_gasolina" else "conta_disp_prepagados"

    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        sql = f"""
            UPDATE solicitudes
            SET {col} = %s,
                conta_disp_updated_by = %s,
                conta_disp_updated_at = NOW()
            WHERE id = %s
            LIMIT 1
        """
        cur.execute(sql, (1 if value else 0, int(user_id), int(solicitud_id)))
        conn.commit()
        return cur.rowcount > 0
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass

###### Inicia el manejo de unidades de negocio (UDN) para solicitudes ######

def get_unidades_negocio_rows() -> list[dict]:
    conn = obtener_conexion()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        select id, nombre
        from Unidades_Negocio
        where coalesce(estatus, 1) = 1
        order by nombre
        """
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def get_detalle_unidades_rows(solicitud_detalle_id: int) -> list[dict]:
    conn = obtener_conexion()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        select
            id,
            solicitud_detalle_id,
            id_unidad,
            porcentaje
        from solicitudes_detalle_un
        where solicitud_detalle_id = %s
        order by id
        """,
        (int(solicitud_detalle_id),),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def guardar_detalle_unidades_rows(
    solicitud_detalle_id: int,
    rows: list[dict],
    usuario_id: int,
) -> None:
    conn = obtener_conexion()
    cur = conn.cursor()
    try:
        cur.execute(
            "select id from solicitudes_detalle where id = %s limit 1",
            (int(solicitud_detalle_id),)
        )
        existe = cur.fetchone()
        if not existe:
            raise ValueError("el detalle indicado no existe")

        total = Decimal("0")
        unidades_vistas = set()

        cleaned: list[tuple[int, Decimal]] = []

        for r in (rows or []):
            id_unidad = r.get("id_unidad")
            porcentaje = r.get("porcentaje")

            if id_unidad in (None, "", "nan"):
                continue

            try:
                id_unidad = int(id_unidad)
            except Exception:
                raise ValueError("hay una unidad de negocio inválida")

            try:
                porcentaje_dec = Decimal(str(porcentaje or 0))
            except Exception:
                raise ValueError("hay un porcentaje inválido")

            if porcentaje_dec <= 0:
                raise ValueError("todos los porcentajes deben ser mayores a 0")

            if id_unidad in unidades_vistas:
                raise ValueError("no se permiten unidades de negocio repetidas en el mismo renglón")

            unidades_vistas.add(id_unidad)
            total += porcentaje_dec
            cleaned.append((id_unidad, porcentaje_dec))

        if not cleaned:
            raise ValueError("debes capturar al menos una unidad de negocio")

        if total.quantize(Decimal("1.000000")) != Decimal("100.000000"):
            raise ValueError("la suma de porcentajes debe ser exactamente 100")

        cur.execute(
            "delete from solicitudes_detalle_un where solicitud_detalle_id = %s",
            (int(solicitud_detalle_id),)
        )

        for id_unidad, porcentaje_dec in cleaned:
            cur.execute(
                """
                insert into solicitudes_detalle_un
                (
                    solicitud_detalle_id,
                    id_unidad,
                    porcentaje,
                    creado_por
                )
                values (%s, %s, %s, %s)
                """,
                (
                    int(solicitud_detalle_id),
                    int(id_unidad),
                    porcentaje_dec,
                    int(usuario_id),
                ),
            )

        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            cur.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        
def get_validacion_detalle_solicitud_rows(solicitud_id: int) -> list[dict]:
    conn = obtener_conexion()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(
            """
            select
                d.id,
                d.concepto,
                d.uuid,
                d.total_xml,
                d.precio_unitario,
                coalesce(scg.fiscales, 0) as fiscales,
                case
                    when d.uuid is not null and trim(d.uuid) <> '' and exists (
                        select 1
                        from DATOSCFD_PDF p
                        where upper(trim(p.UUID)) = upper(trim(d.uuid))
                        limit 1
                    ) then 1
                    else 0
                end as tiene_pdf_uuid,
                coalesce((
                    select round(sum(u.porcentaje), 6)
                    from solicitudes_detalle_un u
                    where u.solicitud_detalle_id = d.id
                ), 0) as total_unidades,
                coalesce((
                    select count(*)
                    from solicitudes_detalle_un u
                    where u.solicitud_detalle_id = d.id
                ), 0) as num_unidades
            from solicitudes_detalle d
            left join solicitud_concepto_gasto scg
              on scg.concepto collate utf8mb4_unicode_ci = d.concepto collate utf8mb4_unicode_ci
            where d.solicitud_id = %s
            order by d.renglon, d.id
            """,
            (int(solicitud_id),),
        )
        return cur.fetchall()
    finally:
        try:
            cur.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

def validar_detalle_para_comprobacion(solicitud_id: int) -> dict:
    rows = get_validacion_detalle_solicitud_rows(int(solicitud_id))
    errores = []

    for r in rows:
        detalle_id = int(r.get("id") or 0)
        concepto = (r.get("concepto") or "").strip()
        uuid = (r.get("uuid") or "").strip()
        precio_unitario = float(r.get("precio_unitario") or 0)
        fiscales = int(r.get("fiscales") or 0)
        tiene_pdf_uuid = int(r.get("tiene_pdf_uuid") or 0)
        total_unidades = float(r.get("total_unidades") or 0)
        num_unidades = int(r.get("num_unidades") or 0)

        requiere_validacion = ((fiscales == 1 and precio_unitario > 0) or bool(uuid))

        if not requiere_validacion:
            continue

        if uuid and not tiene_pdf_uuid:
            errores.append(
                f"detalle {detalle_id} ({concepto}): no tiene PDF cargado en DATOSCFD_PDF para el UUID {uuid}"
            )

        if num_unidades <= 0:
            errores.append(
                f"detalle {detalle_id} ({concepto}): no tiene unidades de negocio capturadas"
            )
        elif round(total_unidades, 6) != 100.0:
            errores.append(
                f"detalle {detalle_id} ({concepto}): las unidades suman {total_unidades} y deben sumar 100"
            )

    return {
        "ok": len(errores) == 0,
        "rows": rows,
        "errores": errores,
    }

def get_detalle_contabilidad_view(solicitud_id: int):
    conn = obtener_conexion()
    cur = conn.cursor(dictionary=True)

    cur.execute(
        """
        select *
        from vw_solicitudes_revision_contabilidad
        where solicitud_id = %s 
        and (total_xml > 0 or precio_unitario > 0) 
        order by fecha
        """,
        (int(solicitud_id),),
    )

    rows = cur.fetchall()

    cur.close()
    conn.close()

    return rows



def get_pdf_by_uuid(uuid: str):
    conn = obtener_conexion()
    cur = conn.cursor()

    cur.execute(
        """
        select ARCHIVO, NOMBRE_ARCHIVO
        from DATOSCFD_PDF
        where upper(trim(UUID)) = upper(trim(%s))
        limit 1
        """,
        (uuid,),
    )

    row = cur.fetchone()

    cur.close()
    conn.close()

    if not row:
        return None, None

    return row[0], row[1]


def get_xml_by_uuid(uuid: str) -> tuple[bytes | None, str | None]:
    uuid_norm = ("" if uuid is None else str(uuid)).strip().upper()
    if not uuid_norm:
        return None, None

    return obtener_xml_por_uuid_ada(st.secrets, uuid_norm)


def get_xmls_by_uuids(uuids: list[str]) -> dict[str, tuple[bytes, str | None]]:
    uuids_norm = [
        str(x).strip().upper()
        for x in (uuids or [])
        if str(x).strip()
    ]
    if not uuids_norm:
        return {}

    return obtener_xmls_por_uuids_ada(st.secrets, uuids_norm)