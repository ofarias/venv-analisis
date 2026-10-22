from database.conexion import obtener_conexion
from models.db import run_query_firebird


def obtener_tipo_cambio_usd_model() -> dict:
    """Tipo de cambio USD->MXN del día, directo del catálogo de monedas de
    SAE (MONED01) — ya sincronizado ahí (Banxico/DOF), no hace falta
    consultar ninguna fuente externa aparte."""
    rows = run_query_firebird(
        "FIREBIRD_BIO_SAE",
        "SELECT TCAMBIO, FULTCAMB FROM MONED01 WHERE TRIM(UPPER(CVE_MONED)) = 'USD'",
        (),
    )
    if not rows:
        return {"tipo_cambio": 1.0, "fecha": None}
    r = rows[0]
    return {"tipo_cambio": float(r.get("TCAMBIO") or 1.0), "fecha": r.get("FULTCAMB")}


def crear_regla_model(
    *,
    usuario_solicita_id: int | None,
    id_tipo_compra: int | None,
    linea: str | None,
    monto_limite_usd: float,
    monto_limite_mxn: float,
    limite_mensual_usd: float = 0,
    limite_mensual_mxn: float = 0,
    usuario_recibe_ids: list[int],
    activo: int = 1,
) -> int | None:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO compras_reglas_autorizacion (
                usuario_solicita_id, id_tipo_compra, linea,
                monto_limite_usd, monto_limite_mxn,
                limite_mensual_usd, limite_mensual_mxn, activo
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                usuario_solicita_id, id_tipo_compra, linea, monto_limite_usd, monto_limite_mxn,
                limite_mensual_usd, limite_mensual_mxn, activo,
            ),
        )
        id_regla = cur.lastrowid
        if usuario_recibe_ids:
            cur.executemany(
                "INSERT INTO compras_reglas_autorizacion_receptores (id_regla, usuario_id) VALUES (%s, %s)",
                [(id_regla, uid) for uid in usuario_recibe_ids],
            )
        conn.commit()
        return id_regla

    except Exception:
        conn.rollback()
        return None

    finally:
        conn.close()


def obtener_reglas_model() -> list[dict]:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT
                r.id_regla,
                r.usuario_solicita_id,
                us.nombre AS usuario_solicita_nombre,
                r.id_tipo_compra,
                t.nombre AS tipo_compra_nombre,
                r.linea,
                r.monto_limite_usd,
                r.monto_limite_mxn,
                r.limite_mensual_usd,
                r.limite_mensual_mxn,
                r.activo,
                r.updated_at,
                GROUP_CONCAT(ur.nombre ORDER BY ur.nombre SEPARATOR ', ') AS usuarios_recibe_nombres
            FROM compras_reglas_autorizacion r
            LEFT JOIN usuarios us ON us.id = r.usuario_solicita_id
            LEFT JOIN compras_tipos t ON t.id_tipo_compra = r.id_tipo_compra
            LEFT JOIN compras_reglas_autorizacion_receptores rec ON rec.id_regla = r.id_regla
            LEFT JOIN usuarios ur ON ur.id = rec.usuario_id
            GROUP BY r.id_regla
            ORDER BY r.id_regla DESC
        """)
        return cur.fetchall() or []

    finally:
        conn.close()


def obtener_receptores_regla_model(id_regla: int) -> list[int]:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT usuario_id FROM compras_reglas_autorizacion_receptores WHERE id_regla = %s",
            (int(id_regla),),
        )
        return [row[0] for row in cur.fetchall()]

    finally:
        conn.close()


def actualizar_regla_model(
    *,
    id_regla: int,
    usuario_solicita_id: int | None,
    id_tipo_compra: int | None,
    linea: str | None,
    monto_limite_usd: float,
    monto_limite_mxn: float,
    limite_mensual_usd: float = 0,
    limite_mensual_mxn: float = 0,
    usuario_recibe_ids: list[int],
    activo: int,
) -> bool:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE compras_reglas_autorizacion
            SET usuario_solicita_id = %s,
                id_tipo_compra = %s,
                linea = %s,
                monto_limite_usd = %s,
                monto_limite_mxn = %s,
                limite_mensual_usd = %s,
                limite_mensual_mxn = %s,
                activo = %s
            WHERE id_regla = %s
            """,
            (
                usuario_solicita_id, id_tipo_compra, linea, monto_limite_usd,
                monto_limite_mxn, limite_mensual_usd, limite_mensual_mxn,
                activo, int(id_regla),
            ),
        )
        # reemplaza la lista de receptores completa — más simple y seguro
        # que calcular un diff contra lo que ya había
        cur.execute(
            "DELETE FROM compras_reglas_autorizacion_receptores WHERE id_regla = %s",
            (int(id_regla),),
        )
        if usuario_recibe_ids:
            cur.executemany(
                "INSERT INTO compras_reglas_autorizacion_receptores (id_regla, usuario_id) VALUES (%s, %s)",
                [(int(id_regla), uid) for uid in usuario_recibe_ids],
            )
        conn.commit()
        return True

    except Exception:
        conn.rollback()
        return False

    finally:
        conn.close()


def cambiar_estatus_regla_model(id_regla: int, activo: int) -> bool:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE compras_reglas_autorizacion SET activo = %s WHERE id_regla = %s",
            (activo, int(id_regla)),
        )
        conn.commit()
        return cur.rowcount > 0

    except Exception:
        conn.rollback()
        return False

    finally:
        conn.close()


def obtener_reglas_activas_con_receptores_model() -> list[dict]:
    """Reglas activas con su lista de receptor_ids — base para resolver qué
    regla aplica a una solicitud (ver controllers/compras_autorizacion_engine_controller.py)."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT id_regla, usuario_solicita_id, id_tipo_compra, linea,
                   monto_limite_usd, monto_limite_mxn,
                   limite_mensual_usd, limite_mensual_mxn
            FROM compras_reglas_autorizacion
            WHERE activo = 1
        """)
        reglas = cur.fetchall() or []
        if not reglas:
            return []

        cur.execute("""
            SELECT id_regla, usuario_id
            FROM compras_reglas_autorizacion_receptores
            WHERE id_regla IN (%s)
        """ % ",".join(["%s"] * len(reglas)), tuple(r["id_regla"] for r in reglas))
        receptores_por_regla: dict[int, list[int]] = {}
        for row in cur.fetchall() or []:
            receptores_por_regla.setdefault(row["id_regla"], []).append(row["usuario_id"])

        for r in reglas:
            r["receptor_ids"] = receptores_por_regla.get(r["id_regla"], [])
        return reglas

    finally:
        conn.close()


def resolver_usuario_id_por_nombre_model(nombre: str) -> int | None:
    nombre = (nombre or "").strip()
    if not nombre:
        return None
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM usuarios WHERE nombre = %s LIMIT 1", (nombre,))
        row = cur.fetchone()
        return int(row[0]) if row else None

    finally:
        conn.close()


def calcular_monto_autorizado_mes_std_model(nombre_solicitante: str, anio: int, mes: int) -> float:
    """Suma el costo (MXN) de solicitudes tipo Estándar ya autorizadas en el
    mes para ese solicitante — único tipo con un monto capturado hoy (ver
    límite mensual en reglas de autorización)."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COALESCE(SUM(sed.costo_total_sin_iva), 0)
            FROM compras_solicitudes s
            INNER JOIN compras_solicitudes_estandar se ON se.id_solicitud_compra = s.id_solicitud_compra
            INNER JOIN compras_solicitudes_estandar_detalle sed ON sed.id_solicitud_estandar = se.id_solicitud_estandar
            WHERE s.solicitante = %s
              AND TRIM(LOWER(s.estatus)) = 'autorizada'
              AND YEAR(s.fecha_solicitud) = %s
              AND MONTH(s.fecha_solicitud) = %s
            """,
            (nombre_solicitante, int(anio), int(mes)),
        )
        row = cur.fetchone()
        return float(row[0] or 0)

    finally:
        conn.close()


def eliminar_regla_model(id_regla: int) -> bool:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM compras_reglas_autorizacion WHERE id_regla = %s",
            (int(id_regla),),
        )
        conn.commit()
        return cur.rowcount > 0

    except Exception:
        conn.rollback()
        return False

    finally:
        conn.close()
