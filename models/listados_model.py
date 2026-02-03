from models.db import run_query

def listar_pendientes(eje:int, origen:str="JAVA", limit:int=500, offset:int=0):
    q = """
      SELECT tipo, periodo, numero,
             COALESCE(MAX(NULLIF(TRIM(cve_prov),'')), NULL) AS cve_prov,
             COALESCE(MAX(concepto_sae), NULL)              AS concepto_sae,
             COUNT(*) AS partidas, ROUND(SUM(porcentaje),4) AS suma_pct
      FROM test.coi_java_bridge
      WHERE eje=:eje AND origen=:origen AND regla_id IS NULL
      GROUP BY tipo, periodo, numero
      ORDER BY periodo, numero
      LIMIT :limit OFFSET :offset
    """
    return run_query("MYSQL_TEST", q, {"eje": int(eje)%100, "origen": origen, "limit": limit, "offset": offset}).mappings().all()

def listar_con_regla(eje:int, origen:str="JAVA", limit:int=500, offset:int=0):
    q = """
      SELECT b.tipo, b.periodo, b.numero,
             MAX(b.regla_id) AS regla_id, MAX(b.regla_nombre) AS regla_nombre,
             COALESCE(MAX(NULLIF(TRIM(b.cve_prov),'')), NULL) AS cve_prov,
             COALESCE(MAX(b.concepto_sae), NULL)              AS concepto_sae,
             ROUND(SUM(b.porcentaje),4) AS suma_pct,
             MAX(l.ts) AS ultimo_log
      FROM test.coi_java_bridge b
      LEFT JOIN test.coi_java_bridge_log l
             ON l.eje=b.eje AND l.tipo=b.tipo AND l.periodo=b.periodo AND l.numero=b.numero AND l.origen=b.origen
      WHERE b.eje=:eje AND b.origen=:origen AND b.regla_id IS NOT NULL
      GROUP BY b.tipo, b.periodo, b.numero
      ORDER BY b.periodo, b.numero
      LIMIT :limit OFFSET :offset
    """
    return run_query("MYSQL_TEST", q, {"eje": int(eje)%100, "origen": origen, "limit": limit, "offset": offset}).mappings().all()