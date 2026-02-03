# models/conta_model.py
from models.db import run_query_firebird

def _t_polizas(eje: int) -> str:
    return f"POLIZAS{int(eje):02d}"

def _t_aux(eje: int) -> str:
    # En tu base es AUXILIARxx (singular)
    return f"AUXILIAR{int(eje):02d}"

def obtener_opciones(eje: int):
    p = _t_polizas(eje)
    sql = f"SELECT DISTINCT TIPO_POLI AS TIPO FROM {p} ORDER BY 1"
    tipos = [r["TIPO"] for r in run_query_firebird("FIREBIRD_BIO_COI", sql)]
    periodos = list(range(1, 14))  # 1..13
    return {"tipos": tipos, "periodos": periodos}

def _filtros_where_y_params(f, alias_p="p", alias_a="a"):
    where, params = [], []

    if f.get("tipos"):
        ph = ",".join(["?"] * len(f["tipos"]))
        where.append(f"{alias_p}.TIPO_POLI IN ({ph})")
        params.extend(f["tipos"])

    if f.get("periodos"):
        ph = ",".join(["?"] * len(f["periodos"]))
        where.append(f"{alias_p}.PERIODO IN ({ph})")
        params.extend(f["periodos"])

    if f.get("cuenta_pref"):              # NUM_CTA en AUXILIAR
        where.append(f"{alias_a}.NUM_CTA STARTING WITH ?")
        params.append(f["cuenta_pref"])

    if f.get("concepto_like"):            # CONCEP_PO en AUXILIAR
        where.append(f"{alias_a}.CONCEP_PO CONTAINING ?")
        params.append(f["concepto_like"])

    if f.get("fecha_desde"):
        where.append(f"{alias_p}.FECHA_POL >= ?")
        params.append(f["fecha_desde"])

    if f.get("fecha_hasta"):
        where.append(f"{alias_p}.FECHA_POL <= ?")
        params.append(f["fecha_hasta"])

    return where, params

def obtener_polizas(eje: int, filtros: dict, limit: int | None = 300, offset: int = 0):
    p, a = _t_polizas(eje), _t_aux(eje)
    where, params = _filtros_where_y_params(filtros, "p", "a")
    where_sql = " WHERE " + " AND ".join(where) if where else ""
    pag = "" if (limit is None) else f"FIRST {limit} SKIP {offset}"

    sql = f"""
        SELECT {pag}
               p.TIPO_POLI, p.NUM_POLIZ, p.PERIODO, p.FECHA_POL, p.ORIGEN,
               SUM(IIF(a.DEBE_HABER = 'D', a.MONTOMOV, 0)) AS CARGO,
               SUM(IIF(a.DEBE_HABER = 'H', a.MONTOMOV, 0)) AS ABONO,
               COUNT(*) AS PARTIDAS
        FROM {p} p
        JOIN {a} a
          ON a.TIPO_POLI = p.TIPO_POLI
         AND a.NUM_POLIZ = p.NUM_POLIZ
         AND a.PERIODO   = p.PERIODO
        {where_sql}
        GROUP BY p.TIPO_POLI, p.NUM_POLIZ, p.PERIODO, p.FECHA_POL, p.ORIGEN
        ORDER BY p.FECHA_POL, p.TIPO_POLI, p.NUM_POLIZ
    """
    return run_query_firebird("FIREBIRD_BIO_COI", sql, tuple(params))

def contar_polizas(eje: int, filtros: dict):
    p, a = _t_polizas(eje), _t_aux(eje)
    where, params = _filtros_where_y_params(filtros, "p", "a")
    where_sql = " WHERE " + " AND ".join(where) if where else ""

    sql = f"""
        SELECT COUNT(*) AS N
        FROM (
            SELECT p.TIPO_POLI, p.NUM_POLIZ, p.PERIODO
            FROM {p} p
            JOIN {a} a
              ON a.TIPO_POLI = p.TIPO_POLI
             AND a.NUM_POLIZ = p.NUM_POLIZ
             AND a.PERIODO   = p.PERIODO
            {where_sql}
            GROUP BY p.TIPO_POLI, p.NUM_POLIZ, p.PERIODO
        ) x
    """
    r = run_query_firebird("FIREBIRD_BIO_COI", sql, tuple(params))
    return int(r[0]["N"]) if r else 0

def resumen_por_periodo(eje: int, filtros: dict):
    p, a = _t_polizas(eje), _t_aux(eje)
    where, params = _filtros_where_y_params(filtros, "p", "a")
    where_sql = " WHERE " + " AND ".join(where) if where else ""

    sql = f"""
        SELECT p.PERIODO,
               SUM(IIF(a.DEBE_HABER = 'D', a.MONTOMOV, 0)) AS CARGOS,
               SUM(IIF(a.DEBE_HABER = 'H', a.MONTOMOV, 0)) AS ABONOS
        FROM {p} p
        JOIN {a} a
          ON a.TIPO_POLI = p.TIPO_POLI
         AND a.NUM_POLIZ = p.NUM_POLIZ
         AND a.PERIODO   = p.PERIODO
        {where_sql}
        GROUP BY p.PERIODO
        ORDER BY p.PERIODO
    """
    return run_query_firebird("FIREBIRD_BIO_COI", sql, tuple(params))

def partidas_de_poliza(eje: int, tipo: str, periodo: int, num_poliz):
    """Detalle de partidas para ver el drill-down desde la grilla."""
    a = _t_aux(eje)
    sql = f"""
        SELECT NUM_PART, NUM_CTA, CONCEP_PO, DEBE_HABER, MONTOMOV, FECHA_POL
        FROM {a}
        WHERE TIPO_POLI = ? AND PERIODO = ? AND NUM_POLIZ = ?
        ORDER BY NUM_PART
    """
    return run_query_firebird("FIREBIRD_BIO_COI", sql, (tipo, periodo, num_poliz))

def resumen_por_tipo(eje: int, filtros: dict):
    p, a = _t_polizas(eje), _t_aux(eje)
    where, params = _filtros_where_y_params(filtros, "p", "a")
    where_sql = " WHERE " + " AND ".join(where) if where else ""
    sql = f"""
        SELECT p.TIPO_POLI,
               SUM(IIF(a.DEBE_HABER='D', a.MONTOMOV, 0)) AS CARGOS,
               SUM(IIF(a.DEBE_HABER='H', a.MONTOMOV, 0)) AS ABONOS
        FROM {p} p
        JOIN {a} a
          ON a.TIPO_POLI = p.TIPO_POLI
         AND a.NUM_POLIZ = p.NUM_POLIZ
         AND a.PERIODO   = p.PERIODO
        {where_sql}
        GROUP BY p.TIPO_POLI
        ORDER BY p.TIPO_POLI
    """
    return run_query_firebird("FIREBIRD_BIO_COI", sql, tuple(params))

def resumen_por_origen(eje: int, filtros: dict):
    p, a = _t_polizas(eje), _t_aux(eje)
    where, params = _filtros_where_y_params(filtros, "p", "a")
    where_sql = " WHERE " + " AND ".join(where) if where else ""
    sql = f"""
        SELECT COALESCE(p.ORIGEN, 'SIN ORIGEN') AS ORIGEN,
               SUM(IIF(a.DEBE_HABER='D', a.MONTOMOV, 0)) AS CARGOS,
               SUM(IIF(a.DEBE_HABER='H', a.MONTOMOV, 0)) AS ABONOS
        FROM {p} p
        JOIN {a} a
          ON a.TIPO_POLI = p.TIPO_POLI
         AND a.NUM_POLIZ = p.NUM_POLIZ
         AND a.PERIODO   = p.PERIODO
        {where_sql}
        GROUP BY p.ORIGEN
        ORDER BY ORIGEN
    """
    return run_query_firebird("FIREBIRD_BIO_COI", sql, tuple(params))



def resumen_conteo_por_origen(eje: int, filtros: dict):
    p, a = _t_polizas(eje), _t_aux(eje)
    where, params = _filtros_where_y_params(filtros, "p", "a")
    where_sql = " WHERE " + " AND ".join(where) if where else ""

    # Contar pólizas únicas por ORIGEN aplicando los filtros (incluye filtros que usan AUXILIAR)
    sql = f"""
        SELECT ORIGEN, COUNT(*) AS NUM_POLIZAS
        FROM (
            SELECT COALESCE(p.ORIGEN, 'SIN ORIGEN') AS ORIGEN,
                   p.TIPO_POLI, p.NUM_POLIZ, p.PERIODO
            FROM {p} p
            JOIN {a} a
              ON a.TIPO_POLI = p.TIPO_POLI
             AND a.NUM_POLIZ = p.NUM_POLIZ
             AND a.PERIODO   = p.PERIODO
            {where_sql}
            GROUP BY COALESCE(p.ORIGEN, 'SIN ORIGEN'),
                     p.TIPO_POLI, p.NUM_POLIZ, p.PERIODO
        ) x
        GROUP BY ORIGEN
        ORDER BY ORIGEN
    """
    return run_query_firebird("FIREBIRD_BIO_COI", sql, tuple(params))