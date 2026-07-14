from database.conexion import obtener_conexion
from models.db import run_query, run_query_firebird

def _fetchall_dict(cursor):
    cols = [c[0] for c in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def listar_mp_model(solo_activas=True):
    conn = obtener_conexion()
    cur = conn.cursor()

    sql = """
        SELECT *
        FROM formulas_mp
        WHERE (%s = 0 OR activo = 1)
        ORDER BY nombre
    """
    cur.execute(sql, (1 if solo_activas else 0,))
    rows = _fetchall_dict(cur)

    cur.close()
    conn.close()
    return rows


def crear_mp_model(data):
    conn = obtener_conexion()
    cur = conn.cursor()

    sql = """
        INSERT INTO formulas_mp (
            clave, nombre, proveedor, unidad_enzimatica,
            actividad_especificacion, unidad_compra, aplica_coa,
            activo, creado_por
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,1,%s)
    """

    cur.execute(sql, (
        data["clave"],
        data["nombre"],
        data.get("proveedor"),
        data.get("unidad_enzimatica"),
        data.get("actividad_especificacion"),
        data.get("unidad_compra"),
        data.get("aplica_coa", 0),
        data.get("usuario_id"),
    ))

    conn.commit()
    cur.close()
    conn.close()


def actualizar_mp_model(mp_id, data):
    conn = obtener_conexion()
    cur = conn.cursor()

    sql = """
        UPDATE formulas_mp
        SET nombre=%s,
            proveedor=%s,
            unidad_enzimatica=%s,
            actividad_especificacion=%s,
            unidad_compra=%s,
            aplica_coa=%s,
            actualizado_por=%s,
            fecha_actualizacion=NOW()
        WHERE id=%s
    """

    cur.execute(sql, (
        data["nombre"],
        data.get("proveedor"),
        data.get("unidad_enzimatica"),
        data.get("actividad_especificacion"),
        data.get("unidad_compra"),
        data.get("aplica_coa", 0),
        data.get("usuario_id"),
        mp_id,
    ))

    conn.commit()
    cur.close()
    conn.close()


def cambiar_estado_mp_model(mp_id, activo, usuario_id=None):
    conn = obtener_conexion()
    cur = conn.cursor()

    sql = """
        UPDATE formulas_mp
        SET activo=%s,
            actualizado_por=%s,
            fecha_actualizacion=NOW()
        WHERE id=%s
    """

    cur.execute(sql, (1 if activo else 0, usuario_id, mp_id))

    conn.commit()
    cur.close()
    conn.close()


def listar_formulas_model(solo_activas=True):
    conn = obtener_conexion()
    cur = conn.cursor()

    sql = """
        SELECT
            f.*,
            fp.clave_formula AS clave_formula_principal,
            fp.nombre_producto AS nombre_formula_principal
        FROM formulas f
        LEFT JOIN formulas fp ON fp.id = f.formula_principal_id
        WHERE (%s = 0 OR f.activo = 1)
        ORDER BY f.nombre_producto, f.es_alterna, f.clave_formula
    """

    cur.execute(sql, (1 if solo_activas else 0,))
    rows = _fetchall_dict(cur)

    cur.close()
    conn.close()
    return rows


def get_formula_model(formula_id):
    conn = obtener_conexion()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM formulas
        WHERE id=%s
    """, (formula_id,))
    formula = _fetchall_dict(cur)

    if not formula:
        cur.close()
        conn.close()
        return None

    formula = formula[0]

    cur.execute("""
        SELECT *
        FROM formulas_versiones
        WHERE formula_id=%s
        ORDER BY version_numero DESC
    """, (formula_id,))
    versiones = _fetchall_dict(cur)

    version_actual = versiones[0] if versiones else None
    detalle = []

    if version_actual:
        cur.execute("""
            SELECT
                d.*,
                mp.clave AS mp_clave,
                mp.nombre AS mp_nombre,
                mp.proveedor,
                mp.unidad_enzimatica
            FROM formulas_detalle d
            INNER JOIN formulas_mp mp ON mp.id = d.mp_id
            WHERE d.formula_version_id=%s
            ORDER BY
                CASE d.tipo
                    WHEN 'Enzima' THEN 1
                    WHEN 'Auxiliar' THEN 2
                    WHEN 'Carrier' THEN 3
                    ELSE 9
                END,
                d.orden_adicion,
                d.id
        """, (version_actual["id"],))
        detalle = _fetchall_dict(cur)

    formula["versiones"] = versiones
    formula["version_actual_data"] = version_actual
    formula["detalle"] = detalle

    cur.close()
    conn.close()
    return formula


def crear_formula_model(data, detalle):
    conn = obtener_conexion()
    cur = conn.cursor()

    try:
        cur.execute("""
            INSERT INTO formulas (
                clave_formula, nombre_producto, segmento, version_actual,
                estado, es_alterna, formula_principal_id, motivo_alterna,
                observaciones, activo, creado_por
            )
            VALUES (%s,%s,%s,1,%s,%s,%s,%s,%s,1,%s)
        """, (
            data["clave_formula"],
            data["nombre_producto"],
            data["segmento"],
            data["estado"],
            data.get("es_alterna", 0),
            data.get("formula_principal_id"),
            data.get("motivo_alterna"),
            data.get("observaciones"),
            data["usuario_id"],
        ))

        formula_id = cur.lastrowid

        cur.execute("""
            INSERT INTO formulas_versiones (
                formula_id, version_numero, estado, observaciones, creado_por
            )
            VALUES (%s,1,%s,%s,%s)
        """, (
            formula_id,
            data["estado"],
            data.get("observaciones"),
            data["usuario_id"],
        ))

        version_id = cur.lastrowid

        for row in detalle:
            cur.execute("""
                INSERT INTO formulas_detalle (
                    formula_version_id, mp_id, tipo, orden_adicion,
                    porcentaje, actividad_objetivo, actividad_coa
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s)
            """, (
                version_id,
                row["mp_id"],
                row["tipo"],
                row.get("orden_adicion"),
                row["porcentaje"],
                row.get("actividad_objetivo"),
                row.get("actividad_coa"),
            ))

        cur.execute("""
            INSERT INTO formulas_auditoria (
                formula_id, accion, detalle, usuario_id
            )
            VALUES (%s,%s,%s,%s)
        """, (
            formula_id,
            "CREAR_FORMULA",
            f"Fórmula creada en estado {data['estado']}",
            data["usuario_id"],
        ))

        conn.commit()
        return formula_id

    except Exception:
        conn.rollback()
        raise

    finally:
        cur.close()
        conn.close()


def nueva_version_formula_model(formula_id, data, detalle):
    conn = obtener_conexion()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT version_actual
            FROM formulas
            WHERE id=%s
        """, (formula_id,))
        row = cur.fetchone()

        if not row:
            raise ValueError("No existe la fórmula.")

        nueva_version = int(row[0]) + 1

        cur.execute("""
            UPDATE formulas
            SET version_actual=%s,
                estado=%s,
                observaciones=%s,
                actualizado_por=%s,
                fecha_actualizacion=NOW()
            WHERE id=%s
        """, (
            nueva_version,
            data["estado"],
            data.get("observaciones"),
            data["usuario_id"],
            formula_id,
        ))

        cur.execute("""
            INSERT INTO formulas_versiones (
                formula_id, version_numero, estado, observaciones, creado_por
            )
            VALUES (%s,%s,%s,%s,%s)
        """, (
            formula_id,
            nueva_version,
            data["estado"],
            data.get("observaciones"),
            data["usuario_id"],
        ))

        version_id = cur.lastrowid

        for row in detalle:
            cur.execute("""
                INSERT INTO formulas_detalle (
                    formula_version_id, mp_id, tipo, orden_adicion,
                    porcentaje, actividad_objetivo, actividad_coa
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s)
            """, (
                version_id,
                row["mp_id"],
                row["tipo"],
                row.get("orden_adicion"),
                row["porcentaje"],
                row.get("actividad_objetivo"),
                row.get("actividad_coa"),
            ))

        cur.execute("""
            INSERT INTO formulas_auditoria (
                formula_id, accion, detalle, usuario_id
            )
            VALUES (%s,%s,%s,%s)
        """, (
            formula_id,
            "NUEVA_VERSION",
            f"Se creó versión {nueva_version}",
            data["usuario_id"],
        ))

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        cur.close()
        conn.close()


def cambiar_estado_formula_model(formula_id, activo, usuario_id):
    conn = obtener_conexion()
    cur = conn.cursor()

    cur.execute("""
        UPDATE formulas
        SET activo=%s,
            actualizado_por=%s,
            fecha_actualizacion=NOW()
        WHERE id=%s
    """, (1 if activo else 0, usuario_id, formula_id))

    cur.execute("""
        INSERT INTO formulas_auditoria (
            formula_id, accion, detalle, usuario_id
        )
        VALUES (%s,%s,%s,%s)
    """, (
        formula_id,
        "ACTIVAR_FORMULA" if activo else "INACTIVAR_FORMULA",
        None,
        usuario_id,
    ))

    conn.commit()
    cur.close()
    conn.close()

def listar_mp_sae_model():
    sql = """
        SELECT
            m.CVE_ART,
            i.DESCR,
            m.CVE_ALM,
            m.STATUS,
            m.CTRL_ALM,
            m.EXIST,
            m.STOCK_MIN,
            m.STOCK_MAX,
            m.COMP_X_REC,
            m.PEND_SURT
        FROM MULT01 m
        LEFT JOIN INVE01 i
            ON i.CVE_ART = m.CVE_ART
        WHERE m.CVE_ALM = 17
          -- AND UPPER(m.CVE_ART) CONTAINING 'MP'
          AND COALESCE(m.STATUS, 'A') = 'A'
        ORDER BY m.CVE_ART
    """

    return run_query_firebird(
        "FIREBIRD_BIO_SAE_4545",
        sql,
        ()
    )


def listar_pt_sae_model():
    """Existencias de producto terminado (PT) en SAE, almacén 18."""
    sql = """
        SELECT
            m.CVE_ART,
            i.DESCR,
            m.CVE_ALM,
            m.STATUS,
            m.CTRL_ALM,
            m.EXIST,
            m.STOCK_MIN,
            m.STOCK_MAX,
            m.COMP_X_REC,
            m.PEND_SURT
        FROM MULT01 m
        LEFT JOIN INVE01 i
            ON i.CVE_ART = m.CVE_ART
        WHERE m.CVE_ALM = 18
          AND COALESCE(m.STATUS, 'A') = 'A'
        ORDER BY m.CVE_ART
    """

    return run_query_firebird(
        "FIREBIRD_BIO_SAE_4545",
        sql,
        ()
    )


def sincronizar_mp_sae_a_mysql_model(usuario_id=None):
    mp_sae = listar_mp_sae_model()

    conn = obtener_conexion()
    cur = conn.cursor()

    try:
        for r in mp_sae:
            clave = str(r.get("CVE_ART") or r.get("cve_art") or "").strip()
            nombre = str(r.get("DESCR") or r.get("descr") or clave).strip()

            if not clave:
                continue

            cur.execute("""
                INSERT INTO formulas_mp (
                    clave,
                    nombre,
                    proveedor,
                    unidad_enzimatica,
                    actividad_especificacion,
                    unidad_compra,
                    aplica_coa,
                    activo,
                    creado_por
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,1,%s)
                ON DUPLICATE KEY UPDATE
                    nombre = VALUES(nombre),
                    activo = 1,
                    actualizado_por = VALUES(creado_por),
                    fecha_actualizacion = NOW()
            """, (
                clave,
                nombre,
                "SAE",
                None,
                None,
                "kg",
                0,
                usuario_id,
            ))

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        cur.close()
        conn.close()
        