
from datetime import date
import pandas as pd
from database.conexion import obtener_conexion
from models.db import run_query

# -------------------------
# UNIDADES DE EMPAQUE
# -------------------------
def get_unidades_empaque_model():
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)

        sql = """
            SELECT id_unidad_empaque, nombre
            FROM compras_unidades_empaque
            WHERE activo = 1
            ORDER BY nombre
        """

        cur.execute(sql)
        return cur.fetchall() or []

    finally:
        conn.close()


# -------------------------
# CABECERA
# -------------------------
def crear_solicitud_cabecera_model(
    *,
    id_tipo_compra,
    fecha_solicitud,
    solicitante,
    observaciones_generales
):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()

        sql = """
            INSERT INTO compras_solicitudes (
                id_tipo_compra,
                fecha_solicitud,
                solicitante,
                observaciones_generales
            )
            VALUES (%s, %s, %s, %s)
        """

        cur.execute(sql, (
            id_tipo_compra,
            fecha_solicitud,
            solicitante,
            observaciones_generales
        ))

        conn.commit()
        return cur.lastrowid

    except Exception:
        conn.rollback()
        return None

    finally:
        conn.close()


# -------------------------
# DETALLE MULTIPRODUCTO
# -------------------------
def crear_detalle_productos_model(*, id_solicitud, detalle: list):
    conn = obtener_conexion()
    try:
        cur = conn.cursor()

        # traer catálogo de unidades para mapear nombre → id
        cur.execute("""
            SELECT id_unidad_empaque, nombre
            FROM compras_unidades_empaque
            WHERE activo = 1
        """)
        unidades = {u[1]: u[0] for u in cur.fetchall()}

        sql = """
            INSERT INTO compras_solicitudes_producto (
                id_solicitud_compra,
                cliente,
                cliente_sae,
                numero_pedido,
                persona_solicita,
                producto,
                producto_sae,
                cantidad,
                id_unidad_empaque,
                fecha_entrega,
                direccion_entrega,
                observaciones
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        data_insert = []

        for row in detalle:

            producto = str(row.get("producto") or "").strip()

            if not producto:
                continue

            unidad_nombre = str(row.get("unidad_empaque") or "").strip()
            id_unidad = unidades.get(unidad_nombre)

            data_insert.append((
                id_solicitud,
                str(row.get("cliente") or "").strip(),
                str(row.get("cliente_sae") or "").strip(),
                str(row.get("numero_pedido") or "").strip(),
                str(row.get("persona_solicita") or "").strip(),
                str(row.get("producto") or "").strip(),
                str(row.get("producto_sae") or "").strip(),
                row.get("cantidad"),
                id_unidad,
                str(row.get("fecha_entrega") or "").strip() if row.get("fecha_entrega") else None,
                str(row.get("direccion_entrega") or "").strip(),
                str(row.get("observaciones") or "").strip(),
            ))

        if not data_insert:
            return False

        cur.executemany(sql, data_insert)

        conn.commit()
        return True

    except Exception as e:
        conn.rollback()
        print("ERROR DETALLE:", e)
        return False

    finally:
        conn.close()


def get_tipos_compra_activos_model():
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)

        sql = """
            SELECT
                id_tipo_compra,
                nombre
            FROM compras_tipos
            WHERE activo = 1
            ORDER BY nombre
        """

        cur.execute(sql)
        return cur.fetchall() or []

    finally:
        conn.close()

def get_tipos_compra_activos_model():
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)

        sql = """
            SELECT
                id_tipo_compra,
                nombre,
                descripcion,
                tipo_formulario
            FROM compras_tipos
            WHERE activo = 1
            ORDER BY nombre
        """

        cur.execute(sql)
        return cur.fetchall() or []

    finally:
        conn.close()


def get_solicitudes_pendientes_usuario_model(solicitante: str) -> pd.DataFrame:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)

        sql = """
            SELECT
                s.id_solicitud_compra,
                s.fecha_solicitud,
                t.nombre AS tipo_compra,
                s.solicitante,
                s.estatus,
                s.observaciones_generales,
                COUNT(p.id_detalle_producto) AS total_renglones,
                s.created_at,
                s.updated_at
            FROM compras_solicitudes s
            INNER JOIN compras_tipos t
                ON t.id_tipo_compra = s.id_tipo_compra
            LEFT JOIN compras_solicitudes_producto p
                ON p.id_solicitud_compra = s.id_solicitud_compra
            WHERE s.activo = 1
              AND TRIM(UPPER(s.solicitante)) = TRIM(UPPER(%s))
              AND TRIM(LOWER(s.estatus)) NOT IN ('cerrada', 'cancelada')
            GROUP BY
                s.id_solicitud_compra,
                s.fecha_solicitud,
                t.nombre,
                s.solicitante,
                s.estatus,
                s.observaciones_generales,
                s.created_at,
                s.updated_at
            ORDER BY s.id_solicitud_compra DESC
        """

        cur.execute(sql, (solicitante,))
        rows = cur.fetchall() or []

        if not rows:
            return pd.DataFrame(columns=[
                "id_solicitud_compra",
                "fecha_solicitud",
                "tipo_compra",
                "solicitante",
                "estatus",
                "observaciones_generales",
                "total_renglones",
                "created_at",
                "updated_at",
            ])

        return pd.DataFrame(rows)

    finally:
        conn.close()


def get_detalle_solicitud_compra_model(id_solicitud_compra: int) -> pd.DataFrame:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)

        sql = """
            SELECT
                p.id_detalle_producto,
                p.id_solicitud_compra,
                p.cliente,
                p.cliente_sae,
                p.numero_pedido,
                p.persona_solicita,
                p.producto,
                p.producto_sae,
                p.cantidad,
                ue.nombre AS unidad_empaque,
                p.fecha_entrega,
                p.direccion_entrega,
                p.observaciones
            FROM compras_solicitudes_producto p
            LEFT JOIN compras_unidades_empaque ue
                ON ue.id_unidad_empaque = p.id_unidad_empaque
            WHERE p.id_solicitud_compra = %s
            ORDER BY p.id_detalle_producto
        """

        cur.execute(sql, (id_solicitud_compra,))
        rows = cur.fetchall() or []

        if not rows:
            return pd.DataFrame(columns=[
                "id_detalle_producto",
                "id_solicitud_compra",
                "cliente",
                "cliente_sae",
                "numero_pedido",
                "persona_solicita",
                "producto",
                "producto_sae",
                "cantidad",
                "unidad_empaque",
                "fecha_entrega",
                "direccion_entrega",
                "observaciones",
            ])

        return pd.DataFrame(rows)

    finally:
        conn.close()
        
def cambiar_estatus_solicitud_compra_model(id_solicitud_compra: int, nuevo_estatus: str) -> bool:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()

        sql = """
            UPDATE compras_solicitudes
            SET estatus = %s
            WHERE id_solicitud_compra = %s
        """
        cur.execute(sql, (str(nuevo_estatus).strip(), int(id_solicitud_compra)))
        conn.commit()
        return cur.rowcount > 0

    except Exception:
        conn.rollback()
        return False

    finally:
        conn.close()


def get_correos_roles_compras_model() -> list[str]:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)

        sql = """
            select distinct
                u.email
            from usuarios u
            inner join usuarios_roles ur
                on ur.username = u.username
            inner join roles r
                on r.id = ur.id_rol
            where u.estatus = 'Activo'
              and r.status = 1
              and upper(trim(r.nombre)) in ('COMPRAS MP', 'COMPRAS ADMIN')
              and u.email is not null
              and trim(u.email) <> ''
        """
        cur.execute(sql)
        rows = cur.fetchall() or []

        return [
            str(r.get("email") or "").strip()
            for r in rows
            if str(r.get("email") or "").strip()
        ]

    finally:
        conn.close()


def get_cabecera_solicitud_compra_model(id_solicitud_compra: int) -> dict:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)

        sql = """
            SELECT
                s.id_solicitud_compra,
                s.fecha_solicitud,
                s.solicitante,
                s.estatus,
                s.observaciones_generales,
                t.nombre AS tipo_compra
            FROM compras_solicitudes s
            INNER JOIN compras_tipos t
                ON t.id_tipo_compra = s.id_tipo_compra
            WHERE s.id_solicitud_compra = %s
            LIMIT 1
        """
        cur.execute(sql, (int(id_solicitud_compra),))
        return cur.fetchone() or {}

    finally:
        conn.close()

def eliminar_solicitud_compra_model(id_solicitud_compra: int) -> bool:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()

        sql = """
            DELETE FROM compras_solicitudes
            WHERE id_solicitud_compra = %s
              AND TRIM(LOWER(estatus)) = 'captura'
        """
        cur.execute(sql, (int(id_solicitud_compra),))
        conn.commit()
        return cur.rowcount > 0

    except Exception:
        conn.rollback()
        return False

    finally:
        conn.close()
        
def get_departamentos_compra_model() -> list[dict]:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)

        sql = """
            SELECT
                id_departamento,
                nombre
            FROM compras_departamentos
            WHERE activo = 1
            ORDER BY nombre
        """
        cur.execute(sql)
        return cur.fetchall() or []

    finally:
        conn.close()


def get_formas_pago_compra_model() -> list[dict]:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)

        sql = """
            SELECT
                id_forma_pago,
                nombre
            FROM compras_formas_pago
            WHERE activo = 1
            ORDER BY nombre
        """
        cur.execute(sql)
        return cur.fetchall() or []

    finally:
        conn.close()


def get_unidades_negocio_compra_model() -> pd.DataFrame:
    rows = run_query("BIO", "SELECT * FROM UnidadesProrrateos", ())
    return pd.DataFrame(rows or [])


def generar_folio_solicitud_estandar_model() -> str | None:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)

        anio = date.today().year

        sql = """
            SELECT folio
            FROM compras_solicitudes_estandar
            WHERE folio LIKE %s
            ORDER BY id_solicitud_estandar DESC
            LIMIT 1
        """
        prefijo = f"SC-{anio}-%"
        cur.execute(sql, (prefijo,))
        row = cur.fetchone()

        consecutivo = 1
        if row and row.get("folio"):
            folio = str(row["folio"]).strip()
            try:
                consecutivo = int(folio.split("-")[-1]) + 1
            except Exception:
                consecutivo = 1

        return f"SC-{anio}-{consecutivo:06d}"

    finally:
        conn.close()


def crear_solicitud_estandar_cabecera_model(
    *,
    id_solicitud_compra: int,
    fecha_elaboracion,
    id_departamento: int,
    id_forma_pago: int,
    observaciones: str | None,
) -> tuple[int | None, str | None]:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()

        folio = generar_folio_solicitud_estandar_model()
        if not folio:
            return None, None

        sql = """
            INSERT INTO compras_solicitudes_estandar (
                id_solicitud_compra,
                folio,
                fecha_elaboracion,
                id_departamento,
                id_forma_pago,
                observaciones
            )
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        cur.execute(
            sql,
            (
                int(id_solicitud_compra),
                folio,
                fecha_elaboracion,
                int(id_departamento),
                int(id_forma_pago),
                str(observaciones).strip() if observaciones else None,
            )
        )
        conn.commit()
        return int(cur.lastrowid), folio

    except Exception:
        conn.rollback()
        return None, None

    finally:
        conn.close()


def crear_solicitud_estandar_detalle_model(
    *,
    id_solicitud_estandar: int,
    detalle: list[dict],
) -> bool:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()

        sql = """
            INSERT INTO compras_solicitudes_estandar_detalle (
                id_solicitud_estandar,
                cantidad,
                descripcion_producto_servicio,
                unidad_negocio_sigla,
                porcentaje,
                fecha_requerida,
                proveedor,
                precio_unitario,
                costo_total_sin_iva
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        data_insert = []

        for row in detalle:
            descripcion = str(row.get("descripcion_producto_servicio") or "").strip()
            cantidad = row.get("cantidad")

            if not descripcion:
                continue

            data_insert.append((
                int(id_solicitud_estandar),
                float(cantidad) if cantidad not in (None, "") else 0,
                descripcion,
                str(row.get("unidad_negocio_sigla") or "").strip() or None,
                float(row.get("porcentaje")) if row.get("porcentaje") not in (None, "") else None,
                row.get("fecha_requerida") or None,
                str(row.get("proveedor") or "").strip() or None,
                float(row.get("precio_unitario")) if row.get("precio_unitario") not in (None, "") else None,
                float(row.get("costo_total_sin_iva")) if row.get("costo_total_sin_iva") not in (None, "") else None,
            ))

        if not data_insert:
            return False

        cur.executemany(sql, data_insert)
        conn.commit()
        return True

    except Exception:
        conn.rollback()
        return False

    finally:
        conn.close()

def get_cabecera_solicitud_estandar_model(id_solicitud_compra: int) -> dict:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)

        sql = """
            SELECT
                se.id_solicitud_estandar,
                se.id_solicitud_compra,
                se.folio,
                se.fecha_elaboracion,
                d.nombre AS departamento,
                fp.nombre AS forma_pago,
                se.observaciones
            FROM compras_solicitudes_estandar se
            INNER JOIN compras_departamentos d
                ON d.id_departamento = se.id_departamento
            INNER JOIN compras_formas_pago fp
                ON fp.id_forma_pago = se.id_forma_pago
            WHERE se.id_solicitud_compra = %s
            LIMIT 1
        """
        cur.execute(sql, (int(id_solicitud_compra),))
        return cur.fetchone() or {}

    finally:
        conn.close()


def get_detalle_solicitud_estandar_model(id_solicitud_compra: int) -> pd.DataFrame:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)

        sql = """
            SELECT
                sed.id_detalle_estandar,
                sed.cantidad,
                sed.descripcion_producto_servicio,
                sed.unidad_negocio_sigla,
                sed.porcentaje,
                sed.fecha_requerida,
                sed.proveedor,
                sed.precio_unitario,
                sed.costo_total_sin_iva
            FROM compras_solicitudes_estandar se
            INNER JOIN compras_solicitudes_estandar_detalle sed
                ON sed.id_solicitud_estandar = se.id_solicitud_estandar
            WHERE se.id_solicitud_compra = %s
            ORDER BY sed.id_detalle_estandar
        """
        cur.execute(sql, (int(id_solicitud_compra),))
        rows = cur.fetchall() or []

        if not rows:
            return pd.DataFrame(columns=[
                "id_detalle_estandar",
                "cantidad",
                "descripcion_producto_servicio",
                "unidad_negocio_sigla",
                "porcentaje",
                "fecha_requerida",
                "proveedor",
                "precio_unitario",
                "costo_total_sin_iva",
            ])

        return pd.DataFrame(rows)

    finally:
        conn.close()

        


