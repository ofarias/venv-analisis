from models.db import run_query_firebird, run_query
from datetime import datetime, date, timedelta

def _t_pol(eje:int) -> str:
    return f"POLIZAS{int(eje):02d}"

def _t_aux(eje:int) -> str:
    return f"AUXILIAR{int(eje):02d}"

def rows_aux_java(eje:int, origen:str="JAVA", limit:int|None=None, offset:int=0):
    """
    Lee AUXILIAR join POLIZAS para ORIGEN='JAVA'.
    Devuelve lista de dicts listos para insert en test.coi_java_bridge
    """
    p, a = _t_pol(eje), _t_aux(eje)
    pag = "" if limit is None else f" FIRST {limit} SKIP {offset} "
    sql = f"""
      SELECT {pag}
             p.EJERCICIO         AS eje,
             p.TIPO_POLI         AS tipo,
             p.PERIODO           AS periodo,
             p.NUM_POLIZ         AS numero,
             a.NUM_PART          AS partida,
             p.FECHA_POL         AS fecha,
             p.ORIGEN            AS origen,
             a.NUM_CTA           AS cuenta,
             a.NUMDEPTO          AS departamento,
             IIF(a.DEBE_HABER='D', a.MONTOMOV, 0) AS cargo,
             IIF(a.DEBE_HABER='H', a.MONTOMOV, 0) AS haber
      FROM {p} p
      JOIN {a} a
        ON a.TIPO_POLI = p.TIPO_POLI
       AND a.NUM_POLIZ = p.NUM_POLIZ
       AND a.PERIODO   = p.PERIODO
      WHERE p.ORIGEN = ?
      ORDER BY p.FECHA_POL, p.TIPO_POLI, p.NUM_POLIZ, a.NUM_PART
    """
    rows = run_query_firebird("FIREBIRD_BIO_COI", sql, (origen,))
    # Normaliza tipos y completa campos que no vienen de COI
    out = []
    for r in rows:
        def _to_date(v):
            # MySQL acepta date; si viene timestamp de FB, tomar .date()
            return v.date() if hasattr(v, "date") else v
        out.append({
            "eje": int(r["EJE"]) % 100,                       # <-- 2 dígitos
            "tipo": str(r["TIPO"]).strip(),
            "periodo": int(r["PERIODO"]),
            "numero": int(str(r["NUMERO"]).strip() or 0),     # <-- limpia y castea
            "partida": int(r.get("PARTIDA") or 0),            # <-- a entero
            "fecha": _to_date(r["FECHA"]),                    # <-- date
            "origen": str(r["ORIGEN"]).strip(),
            "cuenta": str(r["CUENTA"]).strip(),
            "departamento": int(r["DEPARTAMENTO"] or 0),
            "nombre_depto": None,
            "documento": None,
            "proveedor": None,
            "cve_prov": None,
            "cargo": float(r["CARGO"] or 0.0),
            "haber": float(r["HABER"] or 0.0),
            "porcentaje": None,
            "regla_id": None,
            "regla_nombre": None,
            "estatus": "pendiente",
            "auditado": 0,
            "audicion_fecha": None,
            "audicion_actualizacion": None,
        })
    return out

def upsert_bridge_mysql(rows:list[dict]):
    """
    Inserta/actualiza en test.coi_java_bridge usando ON DUPLICATE KEY UPDATE.
    Usa tu conexión MySQL (por ejemplo 'CTRLDOCE'). El nombre de tabla es calificado.
    """
    if not rows:
        return 0

    # Si NO agregaste 'partida' en MySQL, elimina el campo del dict:
    has_partida = "partida" in rows[0]

    cols = [
        "eje","tipo","periodo","numero"
    ] + (["partida"] if has_partida else []) + [
        "fecha","origen","cuenta","departamento","nombre_depto",
        "documento","proveedor","cve_prov","cargo","haber",
        "porcentaje","regla_id","regla_nombre","estatus",
        "auditado","audicion_fecha","audicion_actualizacion"
    ]
    placeholders = ",".join([f":{c}" for c in cols])

    sql = f"""
      INSERT INTO test.coi_java_bridge
      ({",".join(cols)})
      VALUES ({placeholders})
      ON DUPLICATE KEY UPDATE
        cuenta=VALUES(cuenta),
        departamento=VALUES(departamento),
        cargo=VALUES(cargo),
        haber=VALUES(haber),
        estatus=VALUES(estatus),
        audicion_actualizacion=VALUES(audicion_actualizacion)
    """
    # Ejecuta en lotes razonables
    batch_size = 1000
    total = 0
    for i in range(0, len(rows), batch_size):
        chunk = rows[i:i+batch_size]
        # SQLAlchemy ejecuta uno a uno si pasamos lista de dicts con text(sql)
        run_query("MYSQL_TEST", sql, chunk)  # tu run_query acepta lista de params
        total += len(chunk)
    return total

def etl_aux_java_a_bridge(eje:int, origen:str="JAVA", limit:int|None=None, offset:int=0):
    rows = rows_aux_java(eje=eje, origen=origen, limit=limit, offset=offset)
    inserted = upsert_bridge_mysql(rows)
    return {"leidos": len(rows), "upsert": inserted}

def actualizar_porcentajes(eje: int, origen: str = "JAVA", escala_100: bool = True):
    """
    Actualiza `porcentaje` por póliza en test.coi_java_bridge.
    - escala_100=True  -> guarda 0..100
      escala_100=False -> guarda 0..1
    """
    factor = 100 if escala_100 else 1

    sql = f"""
    UPDATE test.coi_java_bridge b
    JOIN (
        SELECT eje, tipo, periodo, numero,
               SUM(cargo) AS total_56
        FROM test.coi_java_bridge
        WHERE eje = :eje
          AND origen = :origen
          AND (cuenta LIKE '5%%' OR cuenta LIKE '6%%')
        GROUP BY eje, tipo, periodo, numero
    ) t
      ON  b.eje = t.eje
      AND b.tipo = t.tipo
      AND b.periodo = t.periodo
      AND b.numero = t.numero
    SET b.porcentaje = CASE
         WHEN (b.cuenta LIKE '5%%' OR b.cuenta LIKE '6%%')
              AND b.cargo > 0
              AND t.total_56 > 0
           THEN ROUND((b.cargo / t.total_56) * :factor, 4)
         ELSE 0
       END
    WHERE b.eje = :eje
      AND b.origen = :origen
    """
    # ejecuta
    run_query("MYSQL_TEST", sql, {"eje": int(eje) % 100, "origen": origen, "factor": factor})
    # opcional: devuelve filas afectadas (si tu run_query lo expone)

def actualizar_nombre_depto(eje: int, origen: str = "JAVA"):
    """
    Actualiza nombre_depto en test.coi_java_bridge
    usando DEPTOSxx de Firebird COI.
    """
    t_deptos = f"DEPTOS"
    sql_fb = f"SELECT DEPTO AS NUMDEPTO, DESCRIP AS NOMBRE FROM {t_deptos}"
    deptos = run_query_firebird("FIREBIRD_BIO_COI", sql_fb)

    if not deptos:
        return 0

    # actualizamos en mysql
    sql_mysql = """
      UPDATE test.coi_java_bridge b
      SET b.nombre_depto = :nombre
      WHERE b.eje = :eje
        AND b.origen = :origen
        AND b.departamento = :numdepto
    """

    count = 0
    for d in deptos:
        params = {
            "nombre": d["NOMBRE"].strip() if d["NOMBRE"] else None,
            "eje": int(eje) % 100,
            "origen": origen,
            "numdepto": d["NUMDEPTO"],
        }
        run_query("MYSQL_TEST", sql_mysql, params)
        count += 1
    return count

def actualizar_concepto_desde_coi(eje: int, origen: str = "JAVA") -> int:
    """
    Actualiza test.coi_java_bridge.concepto con AUXILIAR{eje}.CONCEP_PO,
    para pólizas del ORIGEN indicado. Coincidencia por (eje,tipo,periodo,numero,partida).
    """
    p = f"POLIZAS{int(eje):02d}"
    a = f"AUXILIAR{int(eje):02d}"

    # Trae (tipo, periodo, numero, partida, concepto) de COI para ORIGEN=JAVA
    sql_fb = f"""
      SELECT
        p.TIPO_POLI   AS tipo,
        p.PERIODO     AS periodo,
        p.NUM_POLIZ   AS numero,
        a.NUM_PART    AS partida,
        a.CONCEP_PO   AS concepto
        -- Si quisieras el concepto del encabezado, usa: p.CONCEP_PO AS concepto
      FROM {p} p
      JOIN {a} a
        ON a.TIPO_POLI = p.TIPO_POLI
       AND a.NUM_POLIZ = p.NUM_POLIZ
       AND a.PERIODO   = p.PERIODO
      WHERE p.ORIGEN = ?
    """
    rows = run_query_firebird("FIREBIRD_BIO_COI", sql_fb, (origen,))

    if not rows:
        return 0

    # Prepara batch de updates en MySQL
    updates = []
    for r in rows:
        updates.append({
            "eje": int(eje) % 100,  # guardamos 2 dígitos en la tabla puente
            "origen": origen,
            "tipo": str(r["TIPO"]).strip(),
            "periodo": int(r["PERIODO"]),
            "numero": int(str(r["NUMERO"]).strip() or 0),
            "partida": int(r["PARTIDA"] or 0),
            "concepto": (r["CONCEPTO"] or "").strip() or None,
        })

    sql_mysql = """
      UPDATE test.coi_java_bridge
         SET concepto = :concepto
       WHERE eje = :eje
         AND origen = :origen
         AND tipo = :tipo
         AND periodo = :periodo
         AND numero = :numero
         AND partida = :partida
    """

    # Ejecuta en lotes
    batch = 1000
    total = 0
    for i in range(0, len(updates), batch):
        chunk = updates[i:i+batch]
        run_query("MYSQL_TEST", sql_mysql, chunk)
        total += len(chunk)

    return total


def _agg_totales_bridge_por_poliza(eje:int, origen:str,
                                   impuestos_prefixes: list[str] | None = None):
    """
    Lee de test.coi_java_bridge y calcula:
      total_doc = SUM(cargo) - SUM(haber de cuentas de impuestos)
    'impuestos_prefixes' son prefijos de NUM_CTA a restar del haber.
    """
    eje2 = int(eje) % 100
    # Prefijos por defecto (ajusta si tus cuentas exactas cambian)
    if not impuestos_prefixes:
        impuestos_prefixes = [
            ##"1200001",        # IVA acreditable 16% pendiente de pago
            "215000400",      # Retención ISR RESICO (ajusta si aplica)
            "215000200",      # Retenciones ISR 10% Arrendamiento
            "215000300",      # Retenciones ISR 10% Honorarios
            "215000700",      # Retenciones IVA 10% Arrendamiento
            "215000700",      # Retenciones IVA 10% Honorarios
            "215000700",      # Retenciones IVA Autotransportistas 4%
        ]

    # Construimos condición dinámica para los impuestos
    cond_impuestos = " OR ".join([f"cuenta LIKE :pat{i}" for i in range(len(impuestos_prefixes))])
    if not cond_impuestos:
        cond_impuestos = "0"  # nunca cierto

    sql = f"""
      SELECT eje, tipo, periodo, numero,
             DATE(MIN(fecha)) AS fecha_pol,
             ROUND(
               SUM(cargo) - SUM(CASE WHEN ({cond_impuestos}) THEN haber ELSE 0 END)
             , 2) AS total_doc
      FROM test.coi_java_bridge
      WHERE eje = :eje AND origen = :origen
        AND documento IS NULL
      GROUP BY eje, tipo, periodo, numero
      ORDER BY fecha_pol, tipo, numero
    """

    params = {"eje": eje2, "origen": origen}
    for i, pfx in enumerate(impuestos_prefixes):
        params[f"pat{i}"] = f"{pfx}%"

    # devuelve rows con columnas: eje, tipo, periodo, numero, fecha_pol, total_doc
    return run_query("MYSQL_TEST", sql, params).mappings().all()

def _buscar_en_sae_por_total_y_fecha(total, fecha, tolerancia, ventana_dias):
    f_desde = fecha - timedelta(days=ventana_dias)
    f_hasta = fecha + timedelta(days=ventana_dias)

    q = """
      SELECT FIRST 1
             p.CVE_PROV, p.REFER
      FROM PAGA_M01 p
      WHERE ABS(p.IMPORTE - ?) <= ?
        AND p.FECHA_APLI BETWEEN ? AND ?
      ORDER BY ABS(p.IMPORTE - ?), p.FECHA_APLI
    """
    # Nota: 'total' se usa dos veces (WHERE y ORDER BY) → pásalo 2 veces
    params = (float(total), float(tolerancia), f_desde, f_hasta, float(total))
    r = run_query_firebird("FIREBIRD_BIO_SAE", q, params)
    return r[0] if r else None

def _nombre_proveedor_sae(cve_prov:str|int):
    """Obtiene el nombre del proveedor en Firebird-SAE (prov01)."""
    q = "SELECT FIRST 1 NOMBRE FROM PROV01 WHERE CLAVE = ?"
    r = run_query_firebird("FIREBIRD_BIO_SAE", q, (str(cve_prov).strip(),))
    return (r[0]["NOMBRE"] if r else None)

def actualizar_doc_y_proveedor_desde_sae_FB(
    eje:int,
    origen:str="JAVA",
    *, tolerancia:float=0.01,
    ventana_dias:int=3
    ) -> dict:
    """
    Para cada póliza del bridge:
      - total_cargo = SUM(cargo) (todas las cuentas)
      - match en SAE.paga_m01 por IMPORTE≈total_cargo y FECHA_APLI cercano
      - actualiza en test.coi_java_bridge: documento (REFER), cve_prov, proveedor (prov01.NOMBRE)
    """
    eje2 = int(eje) % 100
    packs = _agg_totales_bridge_por_poliza(eje, origen)
    actualizadas = 0
    sin_match = 0

    for p in packs:
        tot = float(p["total_doc"] or 0)   # <-- usamos total_doc
        fecha_pol = p["fecha_pol"]
        if not fecha_pol or tot == 0:
            sin_match += 1
            continue

        hit = _buscar_en_sae_por_total_y_fecha(tot, fecha_pol, tolerancia, ventana_dias)
        if not hit:
            sin_match += 1
            continue

        cve = str(hit["CVE_PROV"]).strip() if hit.get("CVE_PROV") is not None else None
        refer = (hit["REFER"] or "").strip() if hit.get("REFER") is not None else None
        nombre = _nombre_proveedor_sae(cve) if cve else None

        # actualiza TODAS las partidas de esa póliza en MySQL
        up = """
          UPDATE test.coi_java_bridge
             SET documento = :doc,
                 cve_prov  = :cve,
                 proveedor = :nom
           WHERE eje = :eje AND origen = :origen
             AND tipo = :tipo AND periodo = :periodo AND numero = :numero
             AND documento IS NULL
        """
        run_query("MYSQL_TEST", up, {
            "doc": refer, "cve": cve, "nom": nombre,
            "eje": eje2, "origen": origen,
            "tipo": p["tipo"], "periodo": p["periodo"], "numero": p["numero"],
        })
        actualizadas += 1

    return {"polizas_procesadas": len(packs), "actualizadas": actualizadas, "sin_match": sin_match}


def llenar_concepto_sae_desde_paga(eje:int, origen:str="JAVA",
                                   usar_cve_prov: bool = True) -> dict:
    """
    Para pólizas del bridge que ya tienen `documento` y `concepto_sae` es NULL,
    busca en FIREBIRD_BIO_SAE.PAGA_M01 el `NUM_CPTO` por `REFER` (y opcionalmente `CVE_PROV`)
    y actualiza test.coi_java_bridge.concepto_sae.

    usar_cve_prov=True hará el match por (REFER, CVE_PROV); si lo pones en False, solo por REFER.
    """
    eje2 = int(eje) % 100

    # 1) Documentos pendientes en el bridge
    q_docs = f"""
      SELECT DISTINCT TRIM(documento) AS doc,
             COALESCE(NULLIF(TRIM(cve_prov),''), NULL) AS cve
      FROM test.coi_java_bridge
      WHERE eje=:eje AND origen=:origen
        AND documento IS NOT NULL AND TRIM(documento) <> ''
        AND concepto_sae IS NULL
    """
    pend = run_query("MYSQL_TEST", q_docs, {"eje": eje2, "origen": origen}).mappings().all()
    if not pend:
        return {"pendientes": 0, "actualizadas": 0}

    actualizadas = 0

    # 2) Por cada documento, consulta NUM_CPTO en Firebird SAE
    for row in pend:
        doc = (row["doc"] or "").strip()
        cve = (row["cve"] or "").strip() if row["cve"] else None

        if usar_cve_prov and cve:
            q_fb = """
              SELECT FIRST 1 NUM_CPTO
              FROM PAGA_M01
              WHERE TRIM(REFER) = ? AND TRIM(CVE_PROV) = ?
              ORDER BY FECHA_APLI DESC
            """
            r = run_query_firebird("FIREBIRD_BIO_SAE", q_fb, (doc, cve))
        else:
            q_fb = """
              SELECT FIRST 1 NUM_CPTO
              FROM PAGA_M01
              WHERE TRIM(REFER) = ?
              ORDER BY FECHA_APLI DESC
            """
            r = run_query_firebird("FIREBIRD_BIO_SAE", q_fb, (doc,))

        if not r:
            continue

        num_cpto = r[0]["NUM_CPTO"]

        # 3) Actualiza TODAS las partidas de esa póliza con ese documento (y cve si se usa)
        if usar_cve_prov and cve:
            up = """
              UPDATE test.coi_java_bridge
                 SET concepto_sae = :cpto
               WHERE eje=:eje AND origen=:origen
                 AND TRIM(documento)=:doc AND TRIM(cve_prov)=:cve
                 AND concepto_sae IS NULL
            """
            params = {"cpto": num_cpto, "eje": eje2, "origen": origen, "doc": doc, "cve": cve}
        else:
            up = """
              UPDATE test.coi_java_bridge
                 SET concepto_sae = :cpto
               WHERE eje=:eje AND origen=:origen
                 AND TRIM(documento)=:doc
                 AND concepto_sae IS NULL
            """
            params = {"cpto": num_cpto, "eje": eje2, "origen": origen, "doc": doc}

        run_query("MYSQL_TEST", up, params)
        actualizadas += 1

    return {"pendientes": len(pend), "actualizadas": actualizadas}