
from datetime import date
import pandas as pd
from database.conexion import obtener_conexion
from models.db import run_query, run_query_firebird

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


def get_solicitudes_pendientes_usuario_model(solicitante: str, ver_todas: bool = False) -> pd.DataFrame:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)

        filtro_solicitante = "" if ver_todas else "AND TRIM(UPPER(s.solicitante)) = TRIM(UPPER(%s))"

        sql = f"""
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
              {filtro_solicitante}
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

        params = () if ver_todas else (solicitante,)
        cur.execute(sql, params)
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
                s.id_tipo_compra,
                s.fecha_solicitud,
                s.solicitante,
                s.estatus,
                s.id_regla_aplicada,
                s.requiere_autorizacion,
                s.motivo_autorizacion,
                s.observaciones_generales,
                t.nombre AS tipo_compra,
                t.tipo_formulario AS tipo_formulario
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

def guardar_ruteo_solicitud_model(
    *, id_solicitud_compra: int, id_regla_aplicada: int | None,
    requiere_autorizacion: bool, motivo: str, receptor_ids: list[int],
) -> bool:
    """Guarda el resultado de evaluar las reglas de autorización al enviar
    una solicitud — fijo en el tiempo aunque la regla cambie después (ver
    controllers/compras_autorizacion_engine_controller.py)."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE compras_solicitudes
            SET id_regla_aplicada = %s, requiere_autorizacion = %s, motivo_autorizacion = %s
            WHERE id_solicitud_compra = %s
            """,
            (id_regla_aplicada, 1 if requiere_autorizacion else 0, motivo, int(id_solicitud_compra)),
        )
        cur.execute(
            "DELETE FROM compras_solicitudes_receptores WHERE id_solicitud_compra = %s",
            (int(id_solicitud_compra),),
        )
        if receptor_ids:
            cur.executemany(
                "INSERT INTO compras_solicitudes_receptores (id_solicitud_compra, usuario_id) VALUES (%s, %s)",
                [(int(id_solicitud_compra), int(uid)) for uid in receptor_ids],
            )
        conn.commit()
        return True

    except Exception:
        conn.rollback()
        return False

    finally:
        conn.close()


def obtener_receptores_asignados_model(id_solicitud_compra: int) -> list[int]:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT usuario_id FROM compras_solicitudes_receptores WHERE id_solicitud_compra = %s",
            (int(id_solicitud_compra),),
        )
        return [row[0] for row in cur.fetchall()]

    finally:
        conn.close()


def calcular_monto_autorizado_mes_mp_inv_usd_model(nombre_solicitante: str, anio: int, mes: int) -> float:
    """Suma (cantidad_kg * precio_usd), en USD, de solicitudes tipo Materia
    Prima (Inventario) ya autorizadas en el mes para ese solicitante — solo
    cuenta renglones con precio capturado (ver límite mensual en reglas de
    autorización, combinado con el de Estándar en
    controllers/compras_autorizacion_engine_controller.py)."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COALESCE(SUM(d.cantidad_kg * d.precio_usd), 0)
            FROM compras_solicitudes s
            INNER JOIN compras_solicitudes_mp_inventario_detalle d ON d.id_solicitud_compra = s.id_solicitud_compra
            WHERE s.solicitante = %s
              AND TRIM(LOWER(s.estatus)) = 'autorizada'
              AND YEAR(s.fecha_solicitud) = %s
              AND MONTH(s.fecha_solicitud) = %s
              AND d.precio_usd IS NOT NULL
            """,
            (nombre_solicitante, int(anio), int(mes)),
        )
        row = cur.fetchone()
        return float(row[0] or 0)

    finally:
        conn.close()


def usuario_tiene_solicitudes_asignadas_model(usuario_id: int) -> bool:
    """True si el usuario quedó como receptor asignado (por una regla de
    autorización) de al menos una solicitud 'enviada' (MP/Estándar) o de
    alguna LÍNEA 'enviada' de Materia Prima (Inventario, que se autoriza por
    línea, no por solicitud completa) — controla si se le muestra la
    pestaña de Autorizaciones aunque no sea SuperAdmin/forecastAdmin."""
    if not usuario_id:
        return False
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT 1
            FROM compras_solicitudes_receptores r
            INNER JOIN compras_solicitudes s ON s.id_solicitud_compra = r.id_solicitud_compra
            WHERE r.usuario_id = %s AND TRIM(LOWER(s.estatus)) = 'enviada'
            LIMIT 1
            """,
            (int(usuario_id),),
        )
        if cur.fetchone() is not None:
            return True

        cur.execute(
            """
            SELECT 1
            FROM compras_solicitudes_mp_inv_detalle_receptores r
            INNER JOIN compras_solicitudes_mp_inventario_detalle d ON d.id_detalle_mp_inv = r.id_detalle_mp_inv
            WHERE r.usuario_id = %s AND TRIM(LOWER(d.estatus_linea)) = 'enviada'
            LIMIT 1
            """,
            (int(usuario_id),),
        )
        return cur.fetchone() is not None

    finally:
        conn.close()


def obtener_lineas_mp_inventario_model(id_solicitud_compra: int) -> list[str]:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT DISTINCT linea
            FROM compras_solicitudes_mp_inventario_detalle
            WHERE id_solicitud_compra = %s AND linea IS NOT NULL AND TRIM(linea) <> ''
            """,
            (int(id_solicitud_compra),),
        )
        return [row[0] for row in cur.fetchall()]

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


# -------------------------
# DETALLE MATERIA PRIMA (INVENTARIO) — generado desde forecast o captura manual
# -------------------------
def crear_solicitud_mp_inventario_detalle_model(
    *,
    id_solicitud_compra: int,
    detalle: list[dict],
) -> bool:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()

        sql = """
            INSERT INTO compras_solicitudes_mp_inventario_detalle (
                id_solicitud_compra,
                cve_mp,
                mp_nombre,
                linea,
                cantidad_kg,
                cantidad_requerida_kg,
                precio_usd,
                existencia_mp_kg,
                anio,
                mes,
                id_version_forecast,
                observaciones
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        data_insert = []

        for row in detalle:
            cve_mp = str(row.get("cve_mp") or "").strip()
            mp_nombre = str(row.get("mp_nombre") or "").strip()
            cantidad_kg = row.get("cantidad_kg")

            if not cve_mp and not mp_nombre:
                continue

            data_insert.append((
                int(id_solicitud_compra),
                cve_mp or None,
                mp_nombre or None,
                str(row.get("linea") or "").strip() or None,
                float(cantidad_kg) if cantidad_kg not in (None, "") else 0,
                float(row["cantidad_requerida_kg"]) if row.get("cantidad_requerida_kg") not in (None, "") else None,
                float(row["precio_usd"]) if row.get("precio_usd") not in (None, "") else None,
                float(row["existencia_mp_kg"]) if row.get("existencia_mp_kg") not in (None, "") else None,
                int(row["anio"]) if row.get("anio") not in (None, "") else None,
                int(row["mes"]) if row.get("mes") not in (None, "") else None,
                int(row["id_version_forecast"]) if row.get("id_version_forecast") not in (None, "") else None,
                str(row.get("observaciones") or "").strip() or None,
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


def get_detalle_solicitud_mp_inventario_model(id_solicitud_compra: int) -> pd.DataFrame:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)

        sql = """
            SELECT
                id_detalle_mp_inv,
                cve_mp,
                mp_nombre,
                linea,
                cve_proveedor,
                proveedor_nombre,
                cantidad_kg,
                cantidad_requerida_kg,
                precio_usd,
                existencia_mp_kg,
                anio,
                mes,
                estatus_linea,
                id_regla_aplicada,
                requiere_autorizacion,
                motivo_autorizacion,
                id_version_forecast,
                observaciones,
                cve_doc_sae,
                folio_sae,
                fecha_generado_sae
            FROM compras_solicitudes_mp_inventario_detalle
            WHERE id_solicitud_compra = %s
            ORDER BY id_detalle_mp_inv
        """
        cur.execute(sql, (int(id_solicitud_compra),))
        rows = cur.fetchall() or []

        if not rows:
            return pd.DataFrame(columns=[
                "id_detalle_mp_inv",
                "cve_mp",
                "mp_nombre",
                "linea",
                "cve_proveedor",
                "proveedor_nombre",
                "cantidad_kg",
                "cantidad_requerida_kg",
                "estatus_linea",
                "id_regla_aplicada",
                "requiere_autorizacion",
                "motivo_autorizacion",
                "precio_usd",
                "existencia_mp_kg",
                "anio",
                "mes",
                "id_version_forecast",
                "observaciones",
                "cve_doc_sae",
                "folio_sae",
                "fecha_generado_sae",
            ])

        return pd.DataFrame(rows)

    finally:
        conn.close()


def obtener_detalle_mp_inventario_por_ids_model(ids_detalle: list[int]) -> pd.DataFrame:
    """Mismas columnas que get_detalle_solicitud_mp_inventario_model, pero
    por un conjunto puntual de renglones — se usa al evaluar/enviar solo las
    líneas que el usuario marcó con el checkbox en Pendientes (envío por
    línea, no por toda la solicitud)."""
    if not ids_detalle:
        return pd.DataFrame(columns=[
            "id_detalle_mp_inv", "cve_mp", "mp_nombre", "linea", "cve_proveedor",
            "proveedor_nombre", "cantidad_kg", "cantidad_requerida_kg", "precio_usd",
            "estatus_linea", "id_regla_aplicada", "requiere_autorizacion",
            "motivo_autorizacion", "id_solicitud_compra",
        ])
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)
        placeholders = ",".join(["%s"] * len(ids_detalle))
        cur.execute(
            f"""
            SELECT
                id_detalle_mp_inv, id_solicitud_compra, cve_mp, mp_nombre, linea,
                cve_proveedor, proveedor_nombre, cantidad_kg, cantidad_requerida_kg,
                precio_usd, estatus_linea, id_regla_aplicada, requiere_autorizacion,
                motivo_autorizacion
            FROM compras_solicitudes_mp_inventario_detalle
            WHERE id_detalle_mp_inv IN ({placeholders})
            """,
            tuple(int(i) for i in ids_detalle),
        )
        rows = cur.fetchall() or []
        return pd.DataFrame(rows)

    finally:
        conn.close()


def marcar_lineas_mp_inventario_model(
    *, ids_detalle: list[int], nuevo_estatus: str, id_regla_aplicada: int | None,
    requiere_autorizacion: bool, motivo: str, receptor_ids: list[int],
) -> bool:
    """Marca un conjunto de renglones (líneas) como enviados a autorizar o
    autorizados automáticamente — solo aplica sobre renglones cuya
    solicitud dueña sigue en 'captura'. Guarda también qué regla decidió y
    quién(es) quedaron como receptor(es) de ESTAS líneas en particular
    (pueden ser distintos de otras líneas de la misma solicitud, si
    pertenecen a unidades de negocio con reglas distintas)."""
    if not ids_detalle:
        return False
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        placeholders = ",".join(["%s"] * len(ids_detalle))
        cur.execute(
            f"""
            UPDATE compras_solicitudes_mp_inventario_detalle d
            INNER JOIN compras_solicitudes s ON s.id_solicitud_compra = d.id_solicitud_compra
            SET d.estatus_linea = %s, d.id_regla_aplicada = %s,
                d.requiere_autorizacion = %s, d.motivo_autorizacion = %s
            WHERE d.id_detalle_mp_inv IN ({placeholders})
              AND TRIM(LOWER(s.estatus)) = 'captura'
            """,
            (
                nuevo_estatus, id_regla_aplicada, 1 if requiere_autorizacion else 0, motivo,
                *[int(i) for i in ids_detalle],
            ),
        )
        cur.execute(
            f"DELETE FROM compras_solicitudes_mp_inv_detalle_receptores WHERE id_detalle_mp_inv IN ({placeholders})",
            tuple(int(i) for i in ids_detalle),
        )
        if receptor_ids:
            cur.executemany(
                "INSERT INTO compras_solicitudes_mp_inv_detalle_receptores (id_detalle_mp_inv, usuario_id) "
                "VALUES (%s, %s)",
                [(int(idd), int(uid)) for idd in ids_detalle for uid in receptor_ids],
            )
        conn.commit()
        return True

    except Exception:
        conn.rollback()
        return False

    finally:
        conn.close()


def cambiar_estatus_lineas_mp_inventario_model(ids_detalle: list[int], nuevo_estatus: str) -> bool:
    """Para autorizar/rechazar líneas puntuales — solo sobre renglones que
    siguen 'enviada' (evita tocar algo ya resuelto o que nunca se envió)."""
    if not ids_detalle:
        return False
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        placeholders = ",".join(["%s"] * len(ids_detalle))
        cur.execute(
            f"""
            UPDATE compras_solicitudes_mp_inventario_detalle
            SET estatus_linea = %s
            WHERE id_detalle_mp_inv IN ({placeholders})
              AND TRIM(LOWER(estatus_linea)) = 'enviada'
            """,
            (nuevo_estatus, *[int(i) for i in ids_detalle]),
        )
        conn.commit()
        return cur.rowcount > 0

    except Exception:
        conn.rollback()
        return False

    finally:
        conn.close()


def hay_lineas_pendientes_mp_inventario_model(id_solicitud_compra: int) -> bool:
    """True si a la solicitud todavía le queda algún renglón sin resolver
    (en captura o ya enviado pero sin autorizar/rechazar) — se usa para
    saber si ya se puede fijar un estatus final en la cabecera."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT 1 FROM compras_solicitudes_mp_inventario_detalle
            WHERE id_solicitud_compra = %s
              AND TRIM(LOWER(estatus_linea)) IN ('captura', 'enviada')
            LIMIT 1
            """,
            (int(id_solicitud_compra),),
        )
        return cur.fetchone() is not None

    finally:
        conn.close()


def hay_linea_autorizada_mp_inventario_model(id_solicitud_compra: int) -> bool:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT 1 FROM compras_solicitudes_mp_inventario_detalle
            WHERE id_solicitud_compra = %s AND TRIM(LOWER(estatus_linea)) = 'autorizada'
            LIMIT 1
            """,
            (int(id_solicitud_compra),),
        )
        return cur.fetchone() is not None

    finally:
        conn.close()


def hay_lineas_captura_mp_inventario_model(id_solicitud_compra: int) -> bool:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT 1 FROM compras_solicitudes_mp_inventario_detalle
            WHERE id_solicitud_compra = %s AND TRIM(LOWER(estatus_linea)) = 'captura'
            LIMIT 1
            """,
            (int(id_solicitud_compra),),
        )
        return cur.fetchone() is not None

    finally:
        conn.close()


def obtener_receptores_asignados_linea_model(id_detalle_mp_inv: int) -> list[int]:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT usuario_id FROM compras_solicitudes_mp_inv_detalle_receptores WHERE id_detalle_mp_inv = %s",
            (int(id_detalle_mp_inv),),
        )
        return [row[0] for row in cur.fetchall()]

    finally:
        conn.close()


def obtener_lineas_mp_inventario_pendientes_autorizar_model() -> pd.DataFrame:
    """Todas las líneas con estatus_linea='enviada' (pendientes de que
    alguien las autorice o rechace), con datos de la solicitud dueña — el
    filtro de "a quién le toca verlas" (SuperAdmin/forecastAdmin ven todas,
    los demás solo las suyas por receptor asignado) se aplica en Python con
    obtener_receptores_asignados_linea_model, igual criterio que para
    solicitudes completas."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT
                d.id_detalle_mp_inv, d.id_solicitud_compra, d.cve_mp, d.mp_nombre, d.linea,
                d.cantidad_kg, d.precio_usd, d.anio, d.mes, d.motivo_autorizacion,
                s.solicitante, s.fecha_solicitud
            FROM compras_solicitudes_mp_inventario_detalle d
            INNER JOIN compras_solicitudes s ON s.id_solicitud_compra = d.id_solicitud_compra
            WHERE TRIM(LOWER(d.estatus_linea)) = 'enviada'
            ORDER BY d.id_solicitud_compra, d.id_detalle_mp_inv
        """)
        rows = cur.fetchall() or []
        return pd.DataFrame(rows) if rows else pd.DataFrame(columns=[
            "id_detalle_mp_inv", "id_solicitud_compra", "cve_mp", "mp_nombre", "linea",
            "cantidad_kg", "precio_usd", "anio", "mes", "motivo_autorizacion",
            "solicitante", "fecha_solicitud",
        ])

    finally:
        conn.close()


def obtener_mp_con_solicitud_model(anio: int, meses: list[int]) -> pd.DataFrame:
    """(cve_mp, mes) que YA tienen una solicitud de compra viva (cualquier
    estatus salvo 'rechazada' — una rechazada no debe bloquear volver a
    pedirlo) — usado en Compras -> Demanda (Forecast) para avisar/evitar
    duplicar solicitudes sobre la misma necesidad, y para pintar qué ya se
    generó como Orden de Compra en SAE (cve_doc_sae no nulo)."""
    if not meses:
        return pd.DataFrame(columns=[
            "cve_mp", "mes", "id_solicitud_compra", "estatus", "folio_sae",
        ])

    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)
        placeholders = ",".join(["%s"] * len(meses))
        sql = f"""
            SELECT DISTINCT
                d.cve_mp,
                d.mes,
                s.id_solicitud_compra,
                s.estatus,
                d.folio_sae
            FROM compras_solicitudes_mp_inventario_detalle d
            INNER JOIN compras_solicitudes s
                ON s.id_solicitud_compra = d.id_solicitud_compra
            WHERE d.anio = %s
              AND d.mes IN ({placeholders})
              AND TRIM(LOWER(s.estatus)) <> 'rechazada'
        """
        cur.execute(sql, (int(anio), *[int(m) for m in meses]))
        rows = cur.fetchall() or []
        return pd.DataFrame(rows) if rows else pd.DataFrame(columns=[
            "cve_mp", "mes", "id_solicitud_compra", "estatus", "folio_sae",
        ])

    finally:
        conn.close()


def actualizar_cantidad_mp_inventario_detalle_model(id_detalle_mp_inv: int, cantidad_kg: float) -> bool:
    """Solo actualiza si la solicitud dueña del renglón sigue en 'captura' —
    una vez enviada a autorización, el detalle ya no se debe tocar."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        sql = """
            UPDATE compras_solicitudes_mp_inventario_detalle d
            INNER JOIN compras_solicitudes s ON s.id_solicitud_compra = d.id_solicitud_compra
            SET d.cantidad_kg = %s
            WHERE d.id_detalle_mp_inv = %s
              AND TRIM(LOWER(s.estatus)) = 'captura'
        """
        cur.execute(sql, (float(cantidad_kg), int(id_detalle_mp_inv)))
        conn.commit()
        return cur.rowcount > 0

    except Exception:
        conn.rollback()
        return False

    finally:
        conn.close()


def actualizar_renglon_mp_inventario_detalle_model(
    id_detalle_mp_inv: int, cantidad_kg: float, cantidad_requerida_kg: float, mes: int,
    cve_proveedor: str | None = None, proveedor_nombre: str | None = None,
    precio_usd: float | None = None,
) -> bool:
    """Como actualizar_cantidad_mp_inventario_detalle_model pero también
    fija cantidad_requerida_kg, mes, proveedor y precio USD — se usa al
    "colapsar" los renglones mensuales de una materia prima en uno solo
    (Cantidad Solicitada pasa a ser un total único por producto en
    Pendientes, no por mes)."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        sql = """
            UPDATE compras_solicitudes_mp_inventario_detalle d
            INNER JOIN compras_solicitudes s ON s.id_solicitud_compra = d.id_solicitud_compra
            SET d.cantidad_kg = %s, d.cantidad_requerida_kg = %s, d.mes = %s,
                d.cve_proveedor = %s, d.proveedor_nombre = %s, d.precio_usd = %s
            WHERE d.id_detalle_mp_inv = %s
              AND TRIM(LOWER(s.estatus)) = 'captura'
        """
        cur.execute(sql, (
            float(cantidad_kg), float(cantidad_requerida_kg), int(mes),
            cve_proveedor or None, proveedor_nombre or None,
            float(precio_usd) if precio_usd not in (None, "") else None,
            int(id_detalle_mp_inv),
        ))
        conn.commit()
        return cur.rowcount > 0

    except Exception:
        conn.rollback()
        return False

    finally:
        conn.close()


def eliminar_detalle_mp_inventario_model(id_detalle_mp_inv: int) -> bool:
    """Solo elimina si la solicitud dueña del renglón sigue en 'captura'."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        sql = """
            DELETE d FROM compras_solicitudes_mp_inventario_detalle d
            INNER JOIN compras_solicitudes s ON s.id_solicitud_compra = d.id_solicitud_compra
            WHERE d.id_detalle_mp_inv = %s
              AND TRIM(LOWER(s.estatus)) = 'captura'
        """
        cur.execute(sql, (int(id_detalle_mp_inv),))
        conn.commit()
        return cur.rowcount > 0

    except Exception:
        conn.rollback()
        return False

    finally:
        conn.close()


def listar_proveedores_mp_sae_model() -> list[dict]:
    """Proveedores de SAE (PROV01) marcados como materia prima vía su campo
    libre 9 (PROV_CLIB01.CAMPLIB9 = 'MP') — solo activos (STATUS='A'). Solo
    lectura, para el selector de proveedor de Compras -> Pendientes
    (materia prima)."""
    sql = """
        SELECT p.CLAVE, p.NOMBRE
        FROM PROV01 p
        INNER JOIN PROV_CLIB01 c ON c.CVE_PROV = p.CLAVE
        WHERE TRIM(UPPER(c.CAMPLIB9)) = 'MP'
          AND p.STATUS = 'A'
        ORDER BY p.NOMBRE
    """
    rows = run_query_firebird("FIREBIRD_BIO_SAE", sql, ())
    return [
        {"cve_prov": str(r.get("CLAVE") or "").strip(), "nombre": str(r.get("NOMBRE") or "").strip()}
        for r in (rows or [])
    ]




