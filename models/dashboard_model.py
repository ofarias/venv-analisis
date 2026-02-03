#dashboard_model.py

import streamlit as st 
from models.db import run_query, run_query_firebird
import pandas as pd
from typing import List, Dict, Any, Union
from datetime import date


def polizas_por_tipo(eje:int, origen:str="JAVA"):
    sql = """
      SELECT concepto_sae,
             COUNT(DISTINCT CONCAT(concepto_sae,'-',periodo,'-',numero)) AS polizas,
             ROUND(SUM(COALESCE(cargo,0)),2) AS cargos,
             ROUND(SUM(COALESCE(haber,0)),2) AS abonos
      FROM test.coi_java_bridge
      WHERE eje=:eje AND origen=:origen
      GROUP BY concepto_sae
      ORDER BY COUNT(DISTINCT CONCAT(concepto_sae,'-',periodo,'-',numero)) desc 
    """
    return run_query("MYSQL_TEST", sql, {"eje": int(eje)%100, "origen": origen}).mappings().all()

def cobertura_prorrateo(eje:int, origen:str="JAVA"):
    # cuenta PÓLIZAS (no partidas): con/sin regla_id
    sql = """
      SELECT
        SUM(CASE WHEN tiene_regla=1 THEN 1 ELSE 0 END) AS polizas_con_regla,
        SUM(CASE WHEN tiene_regla=0 THEN 1 ELSE 0 END) AS polizas_sin_regla
      FROM (
        SELECT tipo, periodo, numero,
               MAX(CASE WHEN regla_id IS NOT NULL THEN 1 ELSE 0 END) AS tiene_regla
        FROM test.coi_java_bridge
        WHERE eje=:eje AND origen=:origen
        GROUP BY tipo, periodo, numero
      ) t
    """
    return run_query("MYSQL_TEST", sql, {"eje": int(eje)%100, "origen": origen}).mappings().first()

def usos_por_prorrateo(eje:int, origen:str="JAVA", limit:int=50, offset:int=0):
    # cuántas PÓLIZAS usan cada regla_id
    sql = """
      SELECT regla_id,
             MAX(regla_nombre) AS regla_nombre,
             COUNT(*) AS polizas_uso
      FROM (
        SELECT tipo, periodo, numero,
               MAX(regla_id) AS regla_id,
               MAX(regla_nombre) AS regla_nombre
        FROM test.coi_java_bridge
        WHERE eje=:eje AND origen=:origen AND regla_id IS NOT NULL
        GROUP BY tipo, periodo, numero
      ) x
      GROUP BY regla_id
      ORDER BY polizas_uso DESC, regla_id
      LIMIT :limit OFFSET :offset
    """
    return run_query("MYSQL_TEST", sql, {
        "eje": int(eje)%100, "origen": origen, "limit": int(limit), "offset": int(offset)
    }).mappings().all()

def catalogo_prorrateos_con_uso(eje:int, origen:str="JAVA", limit:int=200, offset:int=0):
    # catálogo con proveedor, concepto y estadística de uso + detalle ksae21t
    sql = """
      SELECT 
        k20.idnumpon,
        k20.dsnombre,
        k20.cdcvepro AS proveedor,
        k20.cdnrocon AS concepto_sae,
        COALESCE(u.polizas_uso, 0) AS polizas_uso,
        d.unidades,
        ROUND(COALESCE(d.suma_pct,0),2) AS suma_pct_regla
      FROM iaspel.ksae20t k20
      LEFT JOIN (
        SELECT regla_id, COUNT(DISTINCT CONCAT(tipo,'-',periodo,'-',numero)) AS polizas_uso
        FROM test.coi_java_bridge
        WHERE eje=:eje AND origen=:origen AND regla_id IS NOT NULL
        GROUP BY regla_id
      ) u ON u.regla_id = k20.idnumpon
      LEFT JOIN (
        SELECT idnumpon,
               COUNT(*) AS unidades,
               SUM(COALESCE(flporuni,0)) AS suma_pct
        FROM iaspel.ksae21t
        GROUP BY idnumpon
      ) d ON d.idnumpon = k20.idnumpon
      ORDER BY polizas_uso DESC, k20.idnumpon
      LIMIT :limit OFFSET :offset
    """
    return run_query("BIO", sql, {
        "eje": int(eje)%100, "origen": origen, "limit": int(limit), "offset": int(offset)
    }).mappings().all()

def detalle_todas_polizas(eje:int, origen:str="JAVA", limit:int=1000, offset:int=0):
    # opcional: listado detalle para tab 1 (si lo quieres bajo la tabla de tipos)
    sql = """
      SELECT tipo, periodo, numero,
             COALESCE(MAX(NULLIF(TRIM(cve_prov),'')), NULL) AS cve_prov,
             COALESCE(MAX(concepto_sae), NULL)              AS concepto_sae,
             COALESCE(MAX(regla_id), NULL)                  AS regla_id,
             COALESCE(MAX(regla_nombre), NULL)              AS regla_nombre,
             ROUND(SUM(COALESCE(cargo,0)),2) AS cargos,
             ROUND(SUM(COALESCE(haber,0)),2) AS abonos,
             ROUND(SUM(COALESCE(porcentaje,0)),2) AS suma_pct
      FROM test.coi_java_bridge
      WHERE eje=:eje AND origen=:origen
      GROUP BY tipo, periodo, numero
      ORDER BY periodo, numero
      LIMIT :limit OFFSET :offset
    """
    return run_query("MYSQL_TEST", sql, {
        "eje": int(eje)%100, "origen": origen, "limit": int(limit), "offset": int(offset)
    }).mappings().all()


def catalogo_proveedores() -> list[dict]:
    # Proveedores con al menos una ponderación en ksae20t
    sql = """
      SELECT TRIM(cdcvepro) AS proveedor, COUNT(*) AS reglas
      FROM iaspel.ksae20t
      WHERE TRIM(cdcvepro) <> ''
      GROUP BY TRIM(cdcvepro)
      ORDER BY proveedor
    """
    return run_query("BIO", sql).mappings().all()

def prorrateos_por_proveedor(proveedor: str, eje: int, origen: str = "JAVA") -> list[dict]:
    # Reglas del proveedor + uso en pólizas + resumen de detalle ksae21t
    sql = """
      SELECT 
        k20.idnumpon,
        k20.dsnombre,
        TRIM(k20.cdcvepro) AS proveedor,
        k20.cdnrocon       AS concepto_sae,
        COALESCE(u.polizas_uso, 0) AS polizas_uso,
        d.unidades,
        ROUND(COALESCE(d.suma_pct,0),2) AS suma_pct_regla
      FROM iaspel.ksae20t k20
      LEFT JOIN (
        SELECT regla_id, COUNT(DISTINCT CONCAT(tipo,'-',periodo,'-',numero)) AS polizas_uso
        FROM test.coi_java_bridge
        WHERE eje = :eje AND origen = :origen AND regla_id IS NOT NULL
        GROUP BY regla_id
      ) u ON u.regla_id = k20.idnumpon
      LEFT JOIN (
        SELECT idnumpon, COUNT(*) AS unidades, SUM(COALESCE(flporuni,0)) AS suma_pct
        FROM iaspel.ksae21t
        GROUP BY idnumpon
      ) d ON d.idnumpon = k20.idnumpon
      WHERE TRIM(k20.cdcvepro) = :prov
      ORDER BY polizas_uso DESC, k20.idnumpon
    """
    return run_query("BIO", sql, {
        "prov": (proveedor or "").strip(),
        "eje": int(eje) % 100,
        "origen": (origen or "JAVA").strip()
    }).mappings().all()

def _prov_stats_bridge(eje:int, origen:str="JAVA"):
    """
    Devuelve por proveedor:
      proveedor, polizas_totales, polizas_con_regla
    Cuenta PÓLIZAS únicas (tipo,periodo,numero).
    Compatible con MySQL < 8.0 (sin CTE).
    """
    sql = """
      SELECT pols.proveedor,
             COUNT(*) AS polizas_totales,
             SUM(pols.tiene_regla) AS polizas_con_regla
      FROM (
        SELECT tipo, periodo, numero,
               COALESCE(MAX(NULLIF(TRIM(cve_prov),'')), NULL) AS proveedor,
               MAX(CASE WHEN regla_id IS NOT NULL THEN 1 ELSE 0 END) AS tiene_regla
        FROM test.coi_java_bridge
        WHERE eje=:eje AND origen=:origen
        GROUP BY tipo, periodo, numero
      ) AS pols
      GROUP BY pols.proveedor
      ORDER BY pols.proveedor
    """
    return run_query("MYSQL_TEST", sql, {"eje": int(eje)%100, "origen": origen}).mappings().all()

def _prov_ponderaciones():
    """
    Conteo de reglas (ponderaciones) por proveedor en ksae20t.
    """
    sql = """
      SELECT TRIM(cdcvepro) AS proveedor,
             COUNT(*) AS ponderaciones
      FROM iaspel.ksae20t
      WHERE TRIM(cdcvepro) <> ''
      GROUP BY TRIM(cdcvepro)
    """
    return run_query("BIO", sql).mappings().all()

def _prov_nombres_desde_sae() -> dict:
    """
    Devuelve dict { cve_prov (CLAVE) -> nombre (NOMBRE) } desde Firebird (SAE).
    Se usa para enriquecer el resumen con nombre_proveedor a partir de cve_prov.
    """
    sql = "SELECT TRIM(CLAVE) AS CLAVE, TRIM(NOMBRE) AS NOMBRE FROM PROV01"
    try:
        rows = run_query_firebird("FIREBIRD_BIO_SAE", sql)  # retorna lista de dicts
        # normaliza a mayúsculas por seguridad (si en puente la cve_prov viene en otra caja)
        mapa = {}
        for r in rows:
            clave = (r.get("CLAVE") or "").strip()
            nombre = (r.get("NOMBRE") or "").strip()
            if clave:
                mapa[clave] = nombre
        return mapa
    except Exception:
        # si Firebird no está disponible, devolvemos vacío y el dashboard sigue funcionando
        return {}

def get_prov_nombres_desde_sae() -> dict:
    return _prov_nombres_desde_sae()

def proveedores_resumen(eje:int, origen:str="JAVA"):
    stats = { (r["proveedor"] or ""): {
                "proveedor": (r["proveedor"] or ""),
                "polizas_totales": int(r["polizas_totales"] or 0),
                "polizas_con_regla": int(r["polizas_con_regla"] or 0)
              } for r in _prov_stats_bridge(eje, origen) }

    pons = { (r["proveedor"] or ""): int(r["ponderaciones"] or 0) for r in _prov_ponderaciones() }
    nombres = _prov_nombres_desde_sae()  # <-- usa CLAVE -> NOMBRE de PROV01

    claves = set(stats.keys()) | set(pons.keys()) | set(nombres.keys())

    out = []
    for prov in sorted(claves):
        prov_key = (prov or "").strip()
        nombre = nombres.get(prov_key) if prov_key else None

        st = stats.get(prov_key, {"polizas_totales":0, "polizas_con_regla":0})
        tot = st["polizas_totales"]
        con = st["polizas_con_regla"]
        sin = max(0, tot - con)
        out.append({
            "proveedor": prov_key or None,          # esta es cve_prov
            "nombre_proveedor": nombre,             # viene de PROV01 por cve_prov
            "polizas_totales": tot,
            "polizas_con_regla": con,
            "polizas_sin_regla": sin,
            "ponderaciones": pons.get(prov_key, 0), # reglas en ksae20t para ese proveedor
            "cobertura_pct": round((con / tot * 100.0), 2) if tot else 0.0,
        })
    return out

def nombre_conceptos() -> list[dict]:
    # Proveedores con al menos una ponderación en ksae20t
    sql = """
          SELECT *
            FROM iaspel.ksae40t
            ORDER BY idnumcto
    """
    return run_query("BIO", sql).mappings().all()


def cargar_prorrateos_tabla(
        limit: int = 500,
        offset: int = 0,
        filtros: dict | None = None,
        debug: bool = False,
    ) -> pd.DataFrame:
    """
    Lee la tabla `Prorrateos` desde MYSQL_BIO e incluye:
      - unidades_cnt: cantidad de unidades (idnuevo) en DetalleProrrateos
      - suma_flporuni: suma de flporuni en DetalleProrrateos
    """
    filtros = filtros or {}
    where = []
    params: dict = {}

    # Filtros opcionales
    if filtros.get("nombre_like"):
        where.append("p.dsnombre LIKE :nombre_like")
        params["nombre_like"] = f"%{filtros['nombre_like']}%"

    if filtros.get("proveedor"):
        where.append("p.cdcvepro = :proveedor")
        params["proveedor"] = str(filtros["proveedor"]).strip()

    if filtros.get("concepto"):
        where.append("p.cdnrocon = :concepto")
        params["concepto"] = int(filtros["concepto"])

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    # 🧠 Query con agregados desde DetalleProrrateos
    sql = f"""
         SELECT 
            p.idnumpon,
            p.dsnombre,
            p.cdnrocon,
            p.cdcvepro,
            p.tmstmp,
            COALESCE(COUNT(d.idnuevo), 0) AS unidades_cnt,
            COALESCE(SUM(d.flporuni), 0) AS suma_flporuni, 
            p.estatus
        FROM Prorrateos p
        LEFT JOIN DetalleProrrateos d
            ON d.idnumpon = p.idnumpon
        {where_sql}
        GROUP BY 
            p.idnumpon, p.dsnombre, p.cdnrocon, p.cdcvepro, p.idusuari, p.tmstmp
        ORDER BY p.idnumpon DESC
        LIMIT :limit OFFSET :offset
    """
    params["limit"] = int(limit)
    params["offset"] = int(offset)

    if debug:
        st.markdown("**SQL (Prorrateos con agregados):**")
        st.code(sql, language="sql")
        st.write("Params:", params)

    df = run_query("BIO", sql, params)
    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)

    # Normalización ligera
    for c in ("idnumpon", "cdnrocon"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")

    if "tmstmp" in df.columns:
        df["tmstmp"] = pd.to_datetime(df["tmstmp"], errors="coerce")

    if "cdcvepro" in df.columns:
        df["cdcvepro"] = df["cdcvepro"].astype(str).str.strip()

    return df

def get_detalle_prorrateo(idnumpon: int) -> pd.DataFrame:
    sql = """
        select d.* , up.dsunineg as unidad
          from detalleprorrateos d 
          left join unidadesprorrateos up on up.idunineg = d.idunineg
         where idnumpon = :idnumpon
    """
    params = {"idnumpon": idnumpon}
    result = run_query("BIO", sql, params)
    if isinstance(result, pd.DataFrame):
        return result
    return pd.DataFrame(result)


def update_detalle_prorrateo_rows(cambios: list[dict]) -> int:
    
    if not cambios:
        return 0

    sql = """
        update detalleprorrateos
           set dsctacon = :dsctacon,
               idunineg = :idunineg,
               flporuni = :flporuni
         where idnumpon = :idnumpon
           and idunineg = :idunineg_orig
    """

    afectados = 0
    for row in cambios:
        params = {
            "idnumpon": row["idnumpon"],
            "idunineg": row["idunineg"],
            "idunineg_orig": row["idunineg_orig"],
            "dsctacon": row["dsctacon"],
            "flporuni": row["flporuni"],
        }
        run_query("BIO", sql, params)
        afectados += 1

    return afectados

def get_pendientes_contabilizar() -> pd.DataFrame:
    
    sql = """
        select pm.cve_prov, 
          p.nombre, 
          p.rfc,  
          pm.num_cpto, 
          cp.descr, 
          pm.no_factura, 
          pm.refer, 
          pm.fechaelab, 
          pm.fecha_apli, 
          m.descr as moneda, 
          pm.importe - fcp.IMPUESTO4 + fcp.IMPUESTO2 +fcp.IMPUESTO3 as Subtotal,
          fcp.IMPUESTO1, 
          fcp.IMPUESTO2, 
          fcp.IMPUESTO3, 
          fcp.IMPUESTO4,
          pm.importe ,
          pm.tcambio,
          pm.impmon_ext,
          pm.APP_UUID 
        from Paga_m01 pm
          left join prov01 p on p.clave = pm.cve_prov
          left join moned01 m on m.num_moned = pm.num_moned
          left join conp01 cp on cp.num_cpto = pm.num_cpto
          left join folcxp01 fcp on fcp.cve_folio = pm.cve_folio
        where (afec_coi != 'A')
            AND extract(year from fecha_apli) >= 2025
            AND pm.num_cpto != 1
    """
    result = run_query_firebird("FIREBIRD_BIO_SAE", sql, ())

    if isinstance(result, pd.DataFrame):
        df = result.copy()
    else:
        df = pd.DataFrame(result)
    # normalizamos todos los nombres de columnas a minúsculas
    df.columns = [str(c).lower() for c in df.columns]
    return pd.DataFrame(df)


def update_estatus_prorrateos(cambios: List[Dict[str, Any]]) -> int:
    """
    actualiza el campo estatus en la tabla Prorrateos (mysql).
    cada elemento de 'cambios' debe traer:
      - idnumpon (int)
      - estatus  (int)  -> 1 o 9

    regresa el número de filas procesadas.
    """
    if not cambios:
        return 0

    sql = """
        update Prorrateos
           set estatus = :estatus
         where idnumpon = :idnumpon
    """

    afectados = 0
    for row in cambios:
        # aseguramos tipos correctos
        params = {
            "idnumpon": int(row["idnumpon"]),
            "estatus": int(row["estatus"]),
        }
        # ejecuta el update en mysql (ds "BIO")
        run_query("BIO", sql, params)
        afectados += 1

    return afectados

def get_conceptos_aspel() -> pd.DataFrame:
    """
    trae los conceptos desde CONP01 (firebird/aspel) y normaliza nombres de columnas.
    """
    sql = """
        select num_cpto, descr
          from CONP01 where num_cpto >= 28
    """
    result = run_query_firebird("FIREBIRD_BIO_SAE", sql, ())

    if isinstance(result, pd.DataFrame):
        df = result.copy()
    else:
        df = pd.DataFrame(result)

    # normalizamos nombres de columnas a minúsculas
    df.columns = [str(c).lower() for c in df.columns]

    # limpieza ligera de la descripción
    if "descr" in df.columns:
        df["descr"] = df["descr"].astype(str).str.strip()

    return df

def crear_prorrateo_cabecera(
        dsnombre: str,
        cdnrocon: int,
        cdcvepro: str,
        importe: float,
        moneda: int,
        variacion: float,
        idusuari: int | None = None,
        estatus: int = 1,
    ) -> int:
    """
    inserta un nuevo prorrateo en la tabla prorrateos (mysql).

    - idnumpon: siguiente número después del MAX(idnumpon)
    """

    # 1) obtener siguiente idnumpon
    sql_max = "SELECT COALESCE(MAX(idnumpon), 0) AS max_id FROM prorrateos"
    res_max = run_query("BIO", sql_max, {})  # CursorResult

    max_id = 0
    if res_max is not None:
        # row es un Row; se puede acceder por índice o por nombre de columna
        row = res_max.first()
        if row is not None:
            try:
                # intenta por nombre
                max_id = int(row["max_id"])
            except Exception:
                # si no, por posición
                max_id = int(row[0])

    nuevo_id = max_id + 1

    # 2) insertar cabecera
    sql_ins = """
        INSERT INTO prorrateos
            (idnumpon, dsnombre, cdnrocon, cdcvepro,
             idusuari, tmstmp, estatus,
             importe, moneda, variacion)
        VALUES
            (:idnumpon, :dsnombre, :cdnrocon, :cdcvepro,
             :idusuari, NOW(), :estatus,
             :importe, :moneda, :variacion)
    """

    params: Dict[str, Any] = {
        "idnumpon": nuevo_id,
        "dsnombre": dsnombre,
        "cdnrocon": int(cdnrocon),
        "cdcvepro": cdcvepro.strip(),
        "idusuari": idusuari if idusuari is not None else 0,
        "estatus": int(estatus),
        "importe": float(importe),
        "moneda": int(moneda),
        "variacion": float(variacion),
    }

    run_query("BIO", sql_ins, params)
    # si no lanzó excepción, consideramos que se creó 1 registro
    return 1

def get_unidades_prorrateo_df() -> pd.DataFrame:
    """
    Regresa las unidades de prorrateo desde la tabla unidadesprorrateos (MySQL).
    """
    sql = """
        SELECT idunineg, cdabrevi, dsunineg
        FROM unidadesprorrateos
        ORDER BY idunineg
    """
    res = run_query("BIO", sql, {})
    # si run_query ya regresa DataFrame, puedes devolverlo directo;
    # si regresa CursorResult, adaptas según tu patrón; aquí asumo DataFrame:
    if isinstance(res, pd.DataFrame):
        return res
    return pd.DataFrame(res)

def get_cuentas_contables_coi_df() -> pd.DataFrame:
    """
    Trae catálogo de cuentas contables desde COI (Firebird).
    AJUSTA la tabla y columnas a las reales de tu BD COI.
    """
    sql = """
        SELECT
            CUENTA,
            NOMBRE, 
            CUENTA_COI,
            NIVEL, 
            RFC,
            TIPO
        FROM CUENTAS_FTC_25
        WHERE (CUENTA_COI STARTING WITH '5' OR CUENTA_COI STARTING WITH '6') AND TIPO = 'D'
        ORDER BY CUENTA 
    """
    res = run_query_firebird("FIREBIRD_BIO_COI", sql, ())
    if isinstance(res, pd.DataFrame):
        df = res.copy()
    else:
        df = pd.DataFrame(res)

    df.columns = [str(c).lower() for c in df.columns]

    # normalizamos un poco
    if "cuenta" in df.columns:
        df["cuenta"] = df["cuenta"].astype(str).str.strip()
    if "nombre" in df.columns:
        df["nombre"] = df["nombre"].astype(str).str.strip()

    return df

def insertar_detalle_prorrateo(filas: list[dict]) -> int:
    """
    inserta nuevas filas en detalleprorrateos.

    espera dicts con:
      - idnumpon
      - dsctacon
      - idunineg
      - flporuni
      - idnuevo
    tmstmp se llena con now()
    """
    if not filas:
        return 0

    sql = """
        insert into detalleprorrateos
            (idnumpon, dsctacon, idunineg, flporuni, tmstmp, idnuevo)
        values
            (:idnumpon, :dsctacon, :idunineg, :flporuni, now(), :idnuevo)
    """

    afectados = 0
    for f in filas:
        params = {
            "idnumpon": int(f["idnumpon"]),
            "dsctacon": str(f["dsctacon"]).strip(),
            "idunineg": int(f["idunineg"]),
            "flporuni": float(f["flporuni"]),
            "idnuevo": int(f.get("idnuevo", f["idunineg"])),
        }
        run_query("BIO", sql, params)
        afectados += 1

    return afectados

def get_poliza_ventas_df(fecha_apli) -> pd.DataFrame:
    """
    ventas de cuen_m01 para num_cpto = 1 en una fecha dada.
    normaliza nombres de columnas a minúsculas.
    """
    sql = """
        select f.cve_doc as factura, 
               f.cve_clpv, 
               cl.nombre, 
               f.status, 
               c.num_moned , 
               m.descr as moneda,
               c.impmon_ext as importe_moneda_ext, 
               c.tcambio,
               f.can_tot as subtotal,
               f.imp_tot1 AS ieps , 
               f.imp_tot2 AS ret_isr, 
               f.imp_tot3 AS ret_iva, 
               f.imp_tot4 as iva, 
               c.IMPORTE, 
               c.afec_coi as COI,
               cl.cuenta_contable, 
               coalesce ( (SELECT camplib3 FROM inve_clib01 i where i.cve_prod = (SELECT FIRST 1 CVE_ART FROM PAR_FACTF01 WHERE CVE_DOC = f.cve_doc)), 0)  as UNIDAD_DE_NEGOCIO,
               coalesce ( (SELECT camplib2 FROM inve_clib01 i where i.cve_prod = (SELECT FIRST 1 CVE_ART FROM PAR_FACTF01 WHERE CVE_DOC = f.cve_doc)), 'Sin Unidad')  as NOMBRE_UNIDAD_DE_NEGOCIO
        from cuen_m01 c
        left join clie01 cl on cl.clave = c.cve_clie
        left join moned01 m on m.num_moned = c.num_moned
        left join factf01 f on f.cve_doc = c.refer
        where c.num_cpto = 1 and c.fecha_apli = ?
    """

    result = run_query_firebird("FIREBIRD_BIO_SAE", sql, (fecha_apli,))

    # intentamos convertir robustamente a dataframe
    rows = []
    if result is None:
        return pd.DataFrame()

    if hasattr(result, "mappings"):
        # cursorresult sqlalchemy
        rows = list(result.mappings())
    elif isinstance(result, (list, tuple)):
        rows = []
        for r in result:
            if isinstance(r, dict):
                rows.append(r)
            else:
                # tupla sin nombres, la dejamos pasar tal cual
                rows.append(r)
    else:
        try:
            rows = list(result)
        except Exception:
            rows = []

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df.columns = [str(c).lower() for c in df.columns]
    return df

def obtener_costos_venta_por_fecha(fecha: date) -> pd.DataFrame:
    """
    devuelve el detalle de costo de venta (por artículo) para una fecha dada.
    """
    sql = """
        SELECT  pf.cve_doc,
                cl.clave,
                cl.nombre,
                f.status,
                --CASE f.num_moned
                --    WHEN 1 THEN '1150-003-001'
                --    WHEN 2 THEN '1150-003-002'
                --END AS cuenta_cliente,
                pf.cve_art,
                i.descr AS articulo,
                pf.cant,
                iif (f.status = 'C', 0, pf.cost) as cost,
                pf.cant * iif (f.status = 'C', 0, pf.cost) AS costo,
                icl.camplib3 AS depto,
                -- '1190-005-000' AS cuenta_prod_terminado,
                f.fecha_doc, 
                pf.num_alm as almacen,
                a.descr as Nombre_Almacen,
                a.cuen_cont as Cuenta_Almacen
        FROM FACTF01 f
        LEFT JOIN PAR_FACTF01 pf ON pf.cve_doc = f.cve_doc
        LEFT JOIN CLIE01 cl      ON cl.clave   = f.cve_clpv
        LEFT JOIN INVE_CLIB01 icl ON icl.cve_prod = pf.cve_art
        LEFT JOIN INVE01 i        ON i.cve_art    = pf.cve_art
        LEFT JOIN ALMACENES01 a   ON a.cve_alm    = pf.num_alm
        WHERE f.fecha_doc = ? AND pf.cost > 0
        
    """ 
    """
      and f.tip_doc_ant != 'R'
    """
    rows = run_query_firebird("FIREBIRD_BIO_SAE", sql, (fecha,))
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)

def obtener_costos_venta_por_fecha_remisiones(fecha: date) -> pd.DataFrame:
    """
    devuelve el detalle de costo de venta (por artículo) para una fecha dada de las remisiones.
    """
    sql = """
        SELECT  pf.cve_doc,
                cl.clave,
                cl.nombre,
                CASE f.num_moned
                    WHEN 1 THEN '1150-003-001'
                    WHEN 2 THEN '1150-003-002'
                END AS cuenta_cliente,
                pf.cve_art,
                i.descr AS articulo,
                pf.cant,
                pf.cost,
                pf.cant * pf.cost AS costo,
                icl.camplib3 AS depto,
                '1190-005-000' AS cuenta_prod_terminado,
                f.fecha_doc
        FROM FACTR01 f
        LEFT JOIN PAR_FACTR01 pf ON pf.cve_doc = f.cve_doc
        LEFT JOIN CLIE01 cl      ON cl.clave   = f.cve_clpv
        LEFT JOIN INVE_CLIB01 icl ON icl.cve_prod = pf.cve_art
        LEFT JOIN INVE01 i        ON i.cve_art    = pf.cve_art
        WHERE f.fecha_doc = ? AND pf.cost > 0 and f.tip_doc_sig = ''
    """
    rows = run_query_firebird("FIREBIRD_BIO_SAE", sql, (fecha,))
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)

def actualizar_concepto_prorrateo(idnumpon: int, cdnrocon: int) -> int:
    idnumpon = int(idnumpon)
    cdnrocon = int(cdnrocon)

    sql = f"""
        update prorrateos
        set cdnrocon = {cdnrocon}
        where idnumpon = {idnumpon}
    """

    res = run_query("BIO", sql)  # sin params para no caer en el tema de la lista de dicts

    # normalizamos a "filas afectadas"
    # 1) si es un CursorResult de SQLAlchemy
    rowcount = getattr(res, "rowcount", None)
    if rowcount is not None:
        return int(rowcount)

    # 2) si run_query ya devuelve un entero
    try:
        return int(res)
    except Exception:
        return 0

def get_documentos_contabilizados_df() -> pd.DataFrame:
    """
    regresa un dataframe con los documentos de PAGA_M01
    que tienen APP_STATUS = 'Contabilidad'.
    """
    sql = """
        SELECT
            CVE_PROV,
            REFER,
            NO_FACTURA,
            FECHA_APLI,
            IMPORTE,
            APP_STATUS,
            AFEC_COI,
            CVE_FOLIO,
            APP_ADA_CFD_DOC
        FROM PAGA_M01
        WHERE APP_STATUS = 'Contabilidad'
    """

    res = run_query_firebird("FIREBIRD_BIO_SAE", sql, ())

    # res puede ser lista de dicts, cursor, o cursorresult
    if not res:
        return pd.DataFrame()

    # normalizamos a lista de dicts
    if isinstance(res, list):
        rows = res
    elif hasattr(res, "mappings"):
        rows = list(res.mappings())
    else:
        try:
            rows = [dict(r) for r in res]
        except Exception:
            rows = []

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows)

def liberar_documento_contabilizado(
    row: Union[pd.Series, Dict[str, Any]]
    ) -> Dict[str, Any]:
    """
    pone AFEC_COI = '' en PAGA_M01 para el documento indicado,
    siempre y cuando esté en APP_STATUS = 'Contabilidad' y AFEC_COI = 'A'.
    """
    try:
        # normalizar fila a dict
        if isinstance(row, pd.Series):
            data = row.to_dict()
        else:
            data = dict(row)

        cve_folio = str(
            data.get("CVE_FOLIO")
            or data.get("cve_folio")
            or ""
        ).strip()

        if not cve_folio:
            return {
                "ok": False,
                "msg": "no viene CVE_FOLIO en la fila seleccionada.",
            }

        sql = """
            UPDATE PAGA_M01
               SET AFEC_COI = '', 
               APP_STATUS = 'Pendiente'
             WHERE TRIM(CVE_FOLIO) = ?
               AND APP_STATUS = 'Contabilidad'
               AND AFEC_COI = 'A'
        """

        # siguiendo el estilo que ya usaste: no nos interesa el retorno
        run_query_firebird("FIREBIRD_BIO_SAE", sql, (cve_folio,))

        return {
            "ok": True,
            "msg": f"AFEC_COI liberado (puesto en blanco) para CVE_FOLIO = {cve_folio}.",
        }

    except Exception as e:
        return {
            "ok": False,
            "msg": f"error al liberar AFEC_COI: {e}",
        }

def get_reporte_cobranza_df(fecha_corte, cliente: str | None = None, vendedor: str | None = None) -> pd.DataFrame:

    #fecha_corte_str = fecha_corte.strftime("%Y-%m-%d")

    sql = """
    with
        params as (
            select cast(? as date) as corte
            from rdb$database
        ),
        movs as (
            select
            d.refer,
            sum(d.importe * d.signo) as pagado_mn,
            sum(d.impmon_ext * d.signo) as pagado_usd,
            max(
                case
                when d.num_cpto not in (19, 20)
                and d.fecha_apli < dateadd(1 day to (select corte from params))
                then d.fecha_apli
                end
            ) as fecha_pago
            from cuen_det01 d
            where d.fecha_apli < dateadd(1 day to (select corte from params))
            group by d.refer
        )

        select
        cl.nombre, 
        cl.clasific as clasificacioncliente,
        cl.clave,
        c.refer,
        f.fecha_doc,

        case
            when (c.importe + coalesce(m.pagado_mn, 0)) > 10
            then (cast(c.fecha_apli as date) - (select corte from params)) * -1
            else 0
        end as diastranscurridos,

        case
            when (c.importe + coalesce(m.pagado_mn, 0)) > 10
            then ((cast(c.fecha_apli as date) - (select corte from params)) * -1) - cl.diascred
            else 0
        end as diasdeatraso,

        m.fecha_pago as fechapago,

        case
            when m.fecha_pago is not null
            then cast(m.fecha_pago as date) - cast(c.fecha_apli as date)
            else null
        end as diasusados,

        cl.diascred,

        case
            when m.fecha_pago is not null
            and (cl.diascred - (cast(m.fecha_pago as date) - cast(c.fecha_apli as date))) < 0
            then (cl.diascred - (cast(m.fecha_pago as date) - cast(c.fecha_apli as date))) * -1
            else 0
        end as diasdeatrasodelpago,

        case
            when c.num_moned = 1 then 0
            when c.num_moned = 2 then c.impmon_ext
            else 0
        end as subtotalusd,

        c.importe as importepesos,
        f.imp_tot3 as retencion_iva,
        f.imp_tot4 as iva,
        c.tcambio,

        coalesce(m.pagado_mn, 0) as pagado,
        coalesce(m.pagado_usd, 0) as pagado_usd,

        (c.importe + coalesce(m.pagado_mn, 0)) as saldo,
        
        case
            when c.num_moned = 1 then 0
            when c.num_moned = 2 then c.impmon_ext + coalesce(m.pagado_usd, 0)
            else 0
        end as saldo_usd,


        case
            when (c.importe + coalesce(m.pagado_mn, 0)) < 10
                and m.fecha_pago is not null
                and (cl.diascred - (cast(m.fecha_pago as date) - cast(c.fecha_apli as date))) >= 0
            then 'Pagado en Tiempo'

            when (c.importe + coalesce(m.pagado_mn, 0)) < 10
                and m.fecha_pago is not null
                and (cl.diascred - (cast(m.fecha_pago as date) - cast(c.fecha_apli as date))) < 0
            then 'Pagado con Atraso'

            when (c.importe + coalesce(m.pagado_mn, 0)) < 10
            then 'Pagado'

            when (((cast(c.fecha_apli as date) - (select corte from params)) * -1) - cl.diascred) <= 0
            then 'Vigente'

            else 'Vencido'
        end as estatusdocumento,

        v.nombre as vendedor,

        cl.cuenta_contable as cuentacontable

        from cuen_m01 c
        left join clie01 cl
        on c.cve_clie = cl.clave
        left join factf01 f
        on c.refer = f.cve_doc
        and f.fecha_doc < dateadd(1 day to (select corte from params))
        left join vend01 v
        on f.cve_vend = v.cve_vend
        left join movs m
        on m.refer = c.refer

        where
        c.tipo_mov = 'C'
        and c.fecha_apli < dateadd(1 day to (select corte from params))

        order by
        cl.nombre asc
    """

    # importante: pasar parámetro
    result = run_query_firebird("FIREBIRD_BIO_SAE", sql, (fecha_corte,))
    
    # conversión robusta
    if result is None:
        return pd.DataFrame()
    
    # caso: cursor fdb o similar
    if hasattr(result, "fetchall") and hasattr(result, "description"):
        rows = result.fetchall()
        cols = [d[0] for d in (result.description or [])]
        df = pd.DataFrame(rows, columns=cols if cols else None)
        df.columns = [str(c).lower() for c in df.columns]
        return df
    
    # caso: sqlalchemy result
    if hasattr(result, "mappings"):
        rows = list(result.mappings())
        df = pd.DataFrame(rows)
        df.columns = [str(c).lower() for c in df.columns]
        return df

    # caso: lista de dicts o tuplas
    if isinstance(result, (list, tuple)):
        if len(result) == 0:
            return pd.DataFrame()
        if isinstance(result[0], dict):
            df = pd.DataFrame(result)
            df.columns = [str(c).lower() for c in df.columns]
            return df
        df = pd.DataFrame(result)  # columnas numéricas
        df.columns = [str(c).lower() for c in df.columns]
        return df

    
    # fallback
    try:
        rows = list(result)
        df = pd.DataFrame(rows)
        df.columns = [str(c).lower() for c in df.columns]
        return df
    except Exception:
        return pd.DataFrame()
    
def get_rep_ventas_lotes_df(fecha_ini, fecha_fin) -> pd.DataFrame:
    """
    regresa dataframe del reporte de ventas por lotes.
    usa filtro por fecha_doc para no traer todo el histórico.
    """
    f1 = pd.to_datetime(fecha_ini).strftime("%Y-%m-%d")
    f2 = pd.to_datetime(fecha_fin).strftime("%Y-%m-%d")

    sql = """
    select
        f.status as estatus,
        f.cve_doc,
        f.fecha_doc,
        c.nombre,
        i.descr,
        lp.lote,
        lp.cve_art,
        el.cantidad as CantidadLote,
        p.uni_venta,
        p.prec * p.tip_cam as "Precio MN",
        case when p.tip_cam > 1 then p.prec else 0 end as "Precio USD",
        p.tip_cam as "Tipo de Cambio",
        case when p.tip_cam > 1 then 'USD' else 'MNX' end as "Moneda",
        case when p.tip_cam = 1 then p.tot_partida else 0 end as "Subtotal Documentos MN",
        case when p.tip_cam > 1 then p.tot_partida else 0 end as "Subtotal Documentos USD",
        case when p.tip_cam = 1 then p.totimp4 else 0 end as "Impuesto Documentos MN ",
        case when p.tip_cam > 1 then p.totimp4 else 0 end as "Impuesto Documentos USD",
        case when p.tip_cam = 1 then p.tot_partida + p.totimp4 else 0 end as "Total Documentos en MN",
        case when p.tip_cam > 1 then p.tot_partida + p.totimp4 else 0 end as "Total Documentos en USD",
        p.tot_partida * p.tip_cam as "SubTotal MN (Todos los documentos)",
        p.totimp4 * p.tip_cam as "Impuesto MN (Todos los documentos)",
        (p.tot_partida + p.totimp4) * p.tip_cam as "Total MN (Todos los documentos)"
    from par_factf01 p
    left join factf01 f on p.cve_doc = f.cve_doc
    left join inve01 i on i.cve_art = p.cve_art
    left join clie01 c on c.clave = f.cve_clpv
    left join enlace_ltpd01 el on el.e_ltpd = p.e_ltpd
    left join ltpd01 lp on lp.reg_ltpd = el.reg_ltpd
    where
        p.e_ltpd != 0
        and p.e_ltpd is not null
        and f.cve_doc != ''
        and f.fecha_doc >= ?
        and f.fecha_doc < dateadd(1 day to cast(? as date))
    """

    rows = run_query_firebird("FIREBIRD_BIO_SAE", sql, (f1, f2)) or []
    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df.columns = [str(c).lower() for c in df.columns]
    return df