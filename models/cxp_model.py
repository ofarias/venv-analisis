# models/cxp_model.py
from typing import Optional, List, Dict, Any
from models.db import run_query_firebird, run_query
import streamlit as st


def _leer_cxp(campo_fecha: Optional[str], cve_prov: Optional[str], f_desde: Optional[str], f_hasta: Optional[str]) -> List[Dict[str, Any]]:
    where, params = [], []
    if cve_prov:
        where.append("TRIM(CVE_PROV) = ?")
        params.append(cve_prov.strip())
    if campo_fecha:
        if f_desde:
            where.append(f"{campo_fecha} >= ?")
            params.append(f_desde)
        if f_hasta:
            where.append(f"{campo_fecha} <= ?")
            params.append(f_hasta)
    
    #where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    where_sql = (" AND ".join(where)) if where else ""
    sql = f"""
        SELECT
            TRIM(CVE_PROV)   AS "cve_prov",
            TRIM(REFER)      AS "refer",
            NUM_CPTO         AS "num_cpto",
            NUM_CARGO        AS "num_cargo",
            TRIM(CVE_FOLIO)  AS "cve_folio",
            TRIM(NO_FACTURA) AS "no_factura",
            TRIM(DOCTO)      AS "docto",
            IMPORTE          AS "importe"
            {', ' + campo_fecha + ' AS fecha_apli' if campo_fecha else ', NULL AS fecha_apli'}
        FROM PAGA_M01 
        {where_sql}
    """
    return run_query_firebird("FIREBIRD_BIO_SAE", sql, tuple(params))

def obtener_cxp_sae_basico(cve_prov: Optional[str] = None, fecha_desde: Optional[str] = None, fecha_hasta: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Lee PAGA_M01 con filtros sencillos.
    Intenta FECHA_APLI -> FECHAELAB -> FECHA -> sin fecha.
    """
    for campo in ("FECHA_APLI", "FECHAELAB", "FECHA", None):
        try:
            return _leer_cxp(campo, cve_prov, fecha_desde, fecha_hasta)
        except Exception:
            continue
    return []  # si todo falló

def _distinct_provs_pagam01_por_fecha(campo_fecha: Optional[str],
                                      f_desde: Optional[str],
                                      f_hasta: Optional[str]) -> List[str]:
    where, params = [], []
    if campo_fecha:
        if f_desde:
            where.append(f"{campo_fecha} >= ?")
            params.append(f_desde)
        if f_hasta:
            where.append(f"{campo_fecha} <= ?")
            params.append(f_hasta)
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    sql = f"""SELECT DISTINCT TRIM(CVE_PROV) AS "cve" FROM PAGA_M01 {where_sql}"""
    rows = run_query_firebird("FIREBIRD_BIO_SAE", sql, tuple(params)) or []
    return [ (r.get("cve") or "").strip() for r in rows if (r.get("cve") or "").strip() ]

def _nombres_proveedores(claves: List[str]) -> List[Dict[str,str]]:
    if not claves:
        return []
    placeholders = ",".join(["?"]*len(claves))
    sql = f"""
      SELECT TRIM(CLAVE) AS "cve_prov", TRIM(NOMBRE) AS "nombre"
      FROM PROV01
      WHERE TRIM(CLAVE) IN ({placeholders})
    """
    rows = run_query_firebird("FIREBIRD_BIO_SAE", sql, tuple(claves)) or []
    mapa = { (r.get("cve_prov") or "").strip(): (r.get("nombre") or "").strip() for r in rows }
    out = []
    for cve in sorted(set(claves)):
        nom = mapa.get(cve, "")
        out.append({"cve_prov": cve, "nombre": nom, "label": f"{cve} - {nom}" if nom else cve})
    return out

def opciones_proveedores_dinamico_por_fecha(fecha_desde: Optional[str],
                                            fecha_hasta: Optional[str]) -> List[Dict[str,str]]:
    """Trae proveedores que tienen CxP en el rango; si no hay, devuelve TODOS de PROV01."""
    # intenta FECHA_APLI -> FECHAELAB -> FECHA -> sin fecha
    for campo in ("FECHA_APLI", "FECHAELAB", "FECHA", None):
        try:
            claves = _distinct_provs_pagam01_por_fecha(campo, fecha_desde, fecha_hasta)
            if claves:
                return _nombres_proveedores(claves)
        except Exception:
            continue
    # fallback: todos los proveedores
    sql_all = f"""SELECT TRIM(CLAVE) AS "cve_prov", TRIM(NOMBRE) AS "nombre" FROM PROV01"""
    rows = run_query_firebird("FIREBIRD_BIO_SAE", sql_all) or []
    out = [{"cve_prov": (r.get("cve_prov") or "").strip(),
            "nombre": (r.get("nombre") or "").strip()}
           for r in rows if (r.get("cve_prov") or "").strip()]
    for r in out:
        r["label"] = f"{r['cve_prov']} - {r['nombre']}" if r["nombre"] else r["cve_prov"]
    out.sort(key=lambda x: x["cve_prov"])
    return out


def obtener_cxp_sae_con_nombres(
    cve_provs: Optional[List[str]] = None,
    fecha_desde: Optional[str] = None,
    fecha_hasta: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Lee PAGA_M01 filtrando SOLO por FECHA_APLI.
    Agrega: nombre de proveedor (PROV01.NOMBRE) y nombre de concepto (CONP01.DESCR).
    """
    where, params = [], []

    # proveedores (lista opcional)
    if cve_provs:
        cves = [str(x).strip() for x in cve_provs if str(x).strip()]
        if cves:
            where.append(f"TRIM(p.CVE_PROV) IN ({','.join(['?']*len(cves))})")
            params.extend(cves)

    # fechas: SOLO FECHA_APLI
    if fecha_desde:
        where.append("p.FECHA_APLI >= ?")
        params.append(fecha_desde)
    if fecha_hasta:
        where.append("p.FECHA_APLI <= ?")
        params.append(fecha_hasta)

    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    sql = f"""
        SELECT
            TRIM(p.CVE_PROV)          AS "cve_prov,
            TRIM(pr.NOMBRE)           AS "prov_nombre,
            TRIM(p.REFER)             AS "refer",
            p.NUM_CPTO                AS "num_cpto",
            TRIM(c.DESCR)             AS "concepto_nombre",
            p.NUM_CARGO               AS "num_cargo",
            TRIM(p.CVE_FOLIO)         AS "cve_folio",
            TRIM(p.NO_FACTURA)        AS "no_factura",
            TRIM(p.DOCTO)             AS "docto",
            p.IMPORTE                 AS "importe",
            p.FECHA_APLI              AS "fecha_apli"
        FROM PAGA_M01 p
        LEFT JOIN PROV01 pr
               ON TRIM(pr.CLAVE) = TRIM(p.CVE_PROV)
        LEFT JOIN CONP01 c
               ON c.NUM_CPTO = p.NUM_CPTO
        {where_sql}
    """
    return run_query_firebird("FIREBIRD_BIO_SAE", sql, tuple(params))

def opciones_proveedores_por_fecha_apli(fecha_desde: Optional[str], fecha_hasta: Optional[str]) -> List[Dict[str, str]]:
    """
    Devuelve los proveedores que tienen CxP en PAGA_M01 dentro del rango de FECHA_APLI.
    Compara por fecha con CAST a DATE para evitar problemas de TIMESTAMP.
    Si no hay resultados, hace fallback a TODOS los proveedores de PROV01.
    """

    ##sql = """
    ##    SELECT FIRST 20 p.CVE_PROV, p.FECHA_APLI
    ##    FROM PAGA_M01 p
    ##    ORDER BY p.FECHA_APLI DESC
    ##"""
    ##rows = run_query_firebird("FIREBIRD_BIO_SAE", sql)
    ##st.dataframe(rows)

    where, params = [], []


    # comparaciones robustas contra DATE
    if fecha_desde:
        where.append("CAST(p.FECHA_APLI AS DATE) >= CAST(? AS DATE)")
        params.append(fecha_desde)  # sigue siendo 'YYYY-MM-DD'
    if fecha_hasta:
        where.append("CAST(p.FECHA_APLI AS DATE) <= CAST(? AS DATE)")
        params.append(fecha_hasta)

    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    sql = f"""
        SELECT DISTINCT TRIM(p.CVE_PROV) AS "cve", TRIM(pr.NOMBRE) AS "nombre"
        FROM PAGA_M01 p
        LEFT JOIN PROV01 pr ON TRIM(pr.CLAVE) = TRIM(p.CVE_PROV)
        {where_sql}
        ORDER BY TRIM(p.CVE_PROV)
    """
    rows = run_query_firebird("FIREBIRD_BIO_SAE", sql, tuple(params)) or []
    
    out = []
    for r in rows:

        cve = (r.get("cve") or "").strip()
        nom = (r.get("nombre") or "").strip()
        if cve:
            out.append({
                "cve_prov": cve,
                "nombre": nom,
                "label": f"{cve} - {nom}" if nom else cve
            })
    
    if out:
        return out

    # Fallback: todos los proveedores si el rango no arrojó CxP
    sql_all = f"""
            SELECT TRIM(CLAVE) AS "cve_prov", 
                    TRIM(NOMBRE) AS "nombre" 
            FROM PROV01 ORDER BY TRIM(CLAVE)
            """
    rows = run_query_firebird("FIREBIRD_BIO_SAE", sql_all) or []
    out = []
    for r in rows:
        cve = (r.get("cve_prov") or "").strip()
        nom = (r.get("nombre") or "").strip()
        if cve:
            out.append({"cve_prov": cve, "nombre": nom, "label": f"{cve} - {nom}" if nom else cve})
    return out

def etl_cxp_a_mysql_y_cruzar(fecha_desde: str, fecha_hasta: str) -> dict:
    # 1) extrae desde FB
    q_fb = """
        SELECT TRIM(p.CVE_PROV) AS   "cve_prov",
               TRIM(pr.NOMBRE)  AS   "prov_nombre",
               TRIM(p.REFER)    AS   "refer",
               p.NUM_CPTO       AS   "num_cpto",
               TRIM(c.DESCR)    AS   "concepto_nombre",
               p.NUM_CARGO      AS   "num_cargo",
               TRIM(p.CVE_FOLIO) AS  "cve_folio",
               TRIM(p.NO_FACTURA) AS "no_factura",
               TRIM(p.DOCTO)    AS "docto",
               p.IMPORTE        AS "importe",
               CAST(p.FECHA_APLI AS DATE) AS "fecha_apli"
        FROM PAGA_M01 p
        LEFT JOIN PROV01 pr ON TRIM(pr.CLAVE)=TRIM(p.CVE_PROV)
        LEFT JOIN CONP01 c  ON c.NUM_CPTO=p.NUM_CPTO
        WHERE CAST(p.FECHA_APLI AS DATE) BETWEEN ? AND ?
    """
    rows = run_query_firebird("FIREBIRD_BIO_SAE", q_fb, (fecha_desde, fecha_hasta))

    if not rows:
        return {"insertados": 0, "detalle": [], "resumen": [], "ranking": []}

    # 2) upsert a MySQL (chunked)
    ins = """
      INSERT INTO test.cxp_staging
        (cve_prov, prov_nombre, refer, num_cpto, concepto_nombre,
         num_cargo, cve_folio, no_factura, docto, importe, fecha_apli)
      VALUES
        (:cve_prov, :prov_nombre, :refer, :num_cpto, :concepto_nombre,
         :num_cargo, :cve_folio, :no_factura, :docto, :importe, :fecha_apli)
      ON DUPLICATE KEY UPDATE
        prov_nombre=VALUES(prov_nombre),
        num_cpto=VALUES(num_cpto),
        concepto_nombre=VALUES(concepto_nombre),
        num_cargo=VALUES(num_cargo),
        cve_folio=VALUES(cve_folio),
        no_factura=VALUES(no_factura),
        docto=VALUES(docto),
        importe=VALUES(importe)
    """
    BATCH = 1000
    total = 0
    for i in range(0, len(rows), BATCH):
        chunk = rows[i:i+BATCH]
        run_query("MYSQL_TEST", ins, chunk)
        total += len(chunk)

    # 3) consultas de cruce
    detalle = run_query("MYSQL_TEST", """
        SELECT s.*, b.eje,b.tipo,b.periodo,b.numero,b.origen,b.regla_id,
               CASE WHEN b.documento IS NULL THEN 0 ELSE 1 END AS tiene_poliza
        FROM test.cxp_staging s
        LEFT JOIN test.coi_java_bridge b
          ON b.origen='JAVA'
         AND TRIM(b.cve_prov)=TRIM(s.cve_prov)
         AND TRIM(b.documento)=TRIM(s.refer)
        ORDER BY s.fecha_apli, s.cve_prov, s.refer
    """).mappings().all()

    resumen = run_query("MYSQL_TEST", """
        SELECT
          SUM(CASE WHEN b.documento IS NULL THEN 1 ELSE 0 END) AS sin_poliza,
          SUM(CASE WHEN b.documento IS NULL THEN 0 ELSE 1 END) AS con_poliza,
          COUNT(*) AS total_docs
        FROM test.cxp_staging s
        LEFT JOIN test.coi_java_bridge b
          ON b.origen='JAVA'
         AND TRIM(b.cve_prov)=TRIM(s.cve_prov)
         AND TRIM(b.documento)=TRIM(s.refer)
    """).mappings().all()

    ranking = run_query("MYSQL_TEST", """
        SELECT
          s.cve_prov, MAX(s.prov_nombre) AS prov_nombre,
          COUNT(*) AS docs_total,
          SUM(CASE WHEN b.documento IS NULL THEN 1 ELSE 0 END) AS docs_sin_poliza,
          ROUND(100*SUM(CASE WHEN b.documento IS NULL THEN 1 ELSE 0 END)/COUNT(*),2) AS pct_sin_poliza
        FROM test.cxp_staging s
        LEFT JOIN test.coi_java_bridge b
          ON b.origen='JAVA'
         AND TRIM(b.cve_prov)=TRIM(s.cve_prov)
         AND TRIM(b.documento)=TRIM(s.refer)
        GROUP BY s.cve_prov
        ORDER BY docs_sin_poliza DESC, s.cve_prov
    """).mappings().all()

    return {"insertados": total, "detalle": detalle, "resumen": resumen, "ranking": ranking}