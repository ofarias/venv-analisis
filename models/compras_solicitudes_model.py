import pandas as pd
from database.conexion import obtener_conexion


def get_tipos_compra_activos_model() -> pd.DataFrame:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)

        sql = """
            select
                id_tipo_compra,
                nombre,
                descripcion
            from compras_tipos
            where activo = 1
            order by nombre
        """
        cur.execute(sql)
        rows = cur.fetchall() or []

        if not rows:
            return pd.DataFrame(columns=["id_tipo_compra", "nombre", "descripcion"])

        return pd.DataFrame(rows)

    finally:
        try:
            conn.close()
        except Exception:
            pass


def crear_solicitud_compra_cabecera_model(
    id_tipo_compra: int,
    fecha_solicitud,
    solicitante: str,
    observaciones_generales: str | None,
    estatus: str = "captura",
    activo: int = 1,
) -> int:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()

        sql = """
            insert into compras_solicitudes (
                id_tipo_compra,
                fecha_solicitud,
                solicitante,
                estatus,
                observaciones_generales,
                activo
            )
            values (%s, %s, %s, %s, %s, %s)
        """
        cur.execute(
            sql,
            (
                int(id_tipo_compra),
                fecha_solicitud,
                str(solicitante).strip(),
                str(estatus).strip(),
                str(observaciones_generales).strip() if observaciones_generales else None,
                int(activo),
            )
        )
        conn.commit()
        return int(cur.lastrowid)

    finally:
        try:
            conn.close()
        except Exception:
            pass


def existe_numero_pedido_producto_model(numero_pedido: str) -> bool:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)

        sql = """
            select count(*) as total
            from compras_solicitudes_producto
            where upper(trim(numero_pedido)) = upper(trim(%s))
        """
        cur.execute(sql, (numero_pedido,))
        row = cur.fetchone() or {}

        return int(row.get("total", 0) or 0) > 0

    finally:
        try:
            conn.close()
        except Exception:
            pass


def crear_solicitud_producto_model(
    id_solicitud_compra: int,
    cliente: str,
    numero_pedido: str,
    persona_solicita: str,
    producto: str,
    cantidad: str,
    fecha_entrega: str | None,
    direccion_entrega: str | None,
    observaciones: str | None,
) -> bool:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()

        sql = """
            insert into compras_solicitudes_producto (
                id_solicitud_compra,
                cliente,
                numero_pedido,
                persona_solicita,
                producto,
                cantidad,
                fecha_entrega,
                direccion_entrega,
                observaciones
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        cur.execute(
            sql,
            (
                int(id_solicitud_compra),
                str(cliente).strip(),
                str(numero_pedido).strip(),
                str(persona_solicita).strip(),
                str(producto).strip(),
                str(cantidad).strip(),
                str(fecha_entrega).strip() if fecha_entrega else None,
                str(direccion_entrega).strip() if direccion_entrega else None,
                str(observaciones).strip() if observaciones else None,
            )
        )
        conn.commit()
        return True

    finally:
        try:
            conn.close()
        except Exception:
            pass


def get_solicitudes_compra_model() -> pd.DataFrame:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)

        sql = """
            select
                s.id_solicitud_compra,
                s.fecha_solicitud,
                t.nombre as tipo_compra,
                s.solicitante,
                s.estatus,
                p.cliente,
                p.numero_pedido,
                p.producto,
                p.cantidad,
                s.created_at
            from compras_solicitudes s
            inner join compras_tipos t
                on t.id_tipo_compra = s.id_tipo_compra
            left join compras_solicitudes_producto p
                on p.id_solicitud_compra = s.id_solicitud_compra
            where s.activo = 1
            order by s.id_solicitud_compra desc
        """
        cur.execute(sql)
        rows = cur.fetchall() or []

        if not rows:
            return pd.DataFrame(columns=[
                "id_solicitud_compra",
                "fecha_solicitud",
                "tipo_compra",
                "solicitante",
                "estatus",
                "cliente",
                "numero_pedido",
                "producto",
                "cantidad",
                "created_at",
            ])

        return pd.DataFrame(rows)

    finally:
        try:
            conn.close()
        except Exception:
            pass