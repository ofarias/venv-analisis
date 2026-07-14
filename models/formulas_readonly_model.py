import json
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