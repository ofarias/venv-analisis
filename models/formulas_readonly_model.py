import json

import fdb
import streamlit as st

from database.conexion import obtener_conexion_biotecsa_formulas


def _fetchall_dict(cursor):
    cols = [c[0] for c in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def _parse_json(value):
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return value


def listar_formulas_readonly_model():
    conn = obtener_conexion_biotecsa_formulas()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            id, nombre, segmento, version, estado, fecha, nota,
            es_alterna, alterna_ref, alterna_motivo, activa,
            consumo, cve_sae, carrier, enzimas, auxiliares, empaque,
            creado_en, actualizado_en
        FROM formulas
        ORDER BY nombre, id
    """)

    rows = _fetchall_dict(cur)
    cur.close()
    conn.close()

    for row in rows:
        for c in ("carrier", "enzimas", "auxiliares", "empaque"):
            row[c] = _parse_json(row.get(c))

    return rows


def obtener_formula_readonly_model(formula_id):
    conn = obtener_conexion_biotecsa_formulas()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM formulas
        WHERE id = %s
    """, (formula_id,))

    rows = _fetchall_dict(cur)
    cur.close()
    conn.close()

    if not rows:
        return None

    row = rows[0]

    for c in ["carrier", "enzimas", "auxiliares", "empaque", "versiones"]:
        row[c] = _parse_json(row.get(c))

    return row


def listar_materias_primas_readonly_model():
    conn = obtener_conexion_biotecsa_formulas()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            id, nombre, proveedor, unidad_actividad,
            actividad_especifica, unidad_compra,
            tiene_coa, activa, creado_en, actualizado_en
        FROM materias_primas
        ORDER BY nombre
    """)

    rows = _fetchall_dict(cur)
    cur.close()
    conn.close()
    return rows


def listar_ordenes_produccion_readonly_model():
    conn = obtener_conexion_biotecsa_formulas()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            ord, lote, producto, clave_formula, version, kg,
            fecha_solicitud, fecha_fabricacion, cliente, tipo,
            pkg_tipo, contenido_neto, piezas, etiquetas,
            nbolsas, serial, consumo, bolsa, observaciones,
            operador, mezclador, numero_operacion,
            hora_inicio, hora_termino, tiempo_mezcla,
            fecha_guardado, creado_en, actualizado_en
        FROM ordenes_produccion
        ORDER BY fecha_fabricacion DESC, ord DESC
    """)

    rows = _fetchall_dict(cur)
    cur.close()
    conn.close()
    return rows


def obtener_orden_produccion_readonly_model(ord_id):
    conn = obtener_conexion_biotecsa_formulas()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM ordenes_produccion
        WHERE ord = %s
    """, (ord_id,))

    rows = _fetchall_dict(cur)
    cur.close()
    conn.close()

    if not rows:
        return None

    row = rows[0]
    row["materias_primas"] = _parse_json(row.get("materias_primas"))

    return row


def _conn_sae():
    cfg = st.secrets["FIREBIRD_BIO_SAE"]
    return fdb.connect(
        host=cfg.get("host", "localhost"),
        database=cfg["database"],
        user=cfg["user"],
        password=cfg["password"],
        port=int(cfg.get("port", 3050)),
        charset=cfg.get("charset", "ISO8859_1"),
    )


def listar_pt_sin_formula_model():
    """Productos terminados (clave inicia con PT) activos en SAE (INVE01)
    que no tienen fórmula registrada en biotecsa_formulas (por cve_sae)."""
    con = _conn_sae()
    try:
        cur = con.cursor()
        cur.execute("""
            select cve_art, descr, lin_prod
            from inve01
            where cve_art starting with 'PT'
              and coalesce(status, 'A') <> 'B'
            order by cve_art
        """)
        rows = cur.fetchall()
        cols = [d[0].strip().lower() for d in cur.description]
        productos = [dict(zip(cols, r)) for r in rows]
    finally:
        try:
            con.close()
        except Exception:
            pass

    conn = obtener_conexion_biotecsa_formulas()
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT cve_sae
        FROM formulas
        WHERE cve_sae IS NOT NULL AND cve_sae <> ''
    """)
    con_formula = {(r[0] or "").strip() for r in cur.fetchall()}
    cur.close()
    conn.close()

    return [
        {
            "cve_sae": (p["cve_art"] or "").strip(),
            "descripcion": (p["descr"] or "").strip(),
            "linea": (p["lin_prod"] or "").strip(),
        }
        for p in productos
        if (p["cve_art"] or "").strip() not in con_formula
    ]