
## prorrateo_model.py
from typing import Dict, Any, List, Tuple, Optional, Iterable
from collections import defaultdict
from math import fabs
from models.db import run_query
from models.bridge_log_model import log_aplicacion_regla 
import pandas as pd

# ------------------ helpers existentes ------------------

def _vec_scale_to_100(vec: dict) -> dict:
    if not vec:
        return vec
    mx = max(vec.values())
    factor = 100.0 if mx <= 1.0 else 1.0
    return {k: round(v * factor, 4) for k, v in vec.items()}

def _score_vectors(vec_pol: dict, vec_regla: dict, tol_pct: float = 0.5) -> float:
    keys = set(vec_pol) | set(vec_regla)
    score = 0.0
    for k in keys:
        vp = vec_pol.get(k, 0.0)
        vr = vec_regla.get(k, 0.0)
        if k not in vec_pol or k not in vec_regla:
            score += 1.0      # penaliza faltantes
            continue
        d = abs(vp - vr)
        if d > tol_pct:
            score += d
    return round(score, 4)

def vector_poliza_bridge(eje:int, tipo:str, periodo:int, numero:int) -> dict:
    """
    {departamento -> porcentaje (0..100)} ya calculado en bridge.
    """
    q = """
      SELECT departamento AS unidad, ROUND(SUM(porcentaje),4) AS pct
      FROM test.coi_java_bridge
      WHERE eje=:e AND tipo=:t AND periodo=:p AND numero=:n
      GROUP BY departamento
      HAVING SUM(porcentaje) IS NOT NULL
      ORDER BY unidad
    """
    rows = run_query("MYSQL_TEST", q, {
        "e": int(eje) % 100, "t": tipo.strip(), "p": int(periodo), "n": int(numero)
    }).mappings().all()
    vec = {}
    for r in rows:
        v = float(r["pct"] or 0.0)
        try:
            u = int(r["unidad"])
        except Exception:
            u = r["unidad"]
        if v > 0:
            vec[u] = v
    return vec

def aplicar_prorrateo_a_poliza(eje: int, tipo: str, periodo: int, numero: int,
                               idnumpon: int, nombre: str) -> None:
    # trae concepto de la regla (si existe) y lo guarda
    r = run_query("BIO",
        "SELECT cdnrocon AS concepto FROM iaspel.ksae20t WHERE idnumpon=:rid",
        {"rid": int(idnumpon)}
    ).mappings().first()
    concepto = (r and r["concepto"]) or None

    up = """
      UPDATE test.coi_java_bridge
         SET regla_id=:rid, regla_nombre=:rnom,
             concepto_sae = COALESCE(:con, concepto_sae)
       WHERE eje=:e AND tipo=:t AND periodo=:p AND numero=:n
    """
    run_query("MYSQL_TEST", up, {
        "rid": int(idnumpon), "rnom": (nombre or "").strip(), "con": concepto,
        "e": int(eje) % 100, "t": tipo.strip(), "p": int(periodo), "n": int(numero)
    })

# ------------------ NUEVO: señales desde bridge ------------------

def _signals_de_poliza(eje:int, tipo:str, periodo:int, numero:int) -> dict:
    """Regresa {'cve_prov': ..., 'concepto_sae': ...} desde el bridge."""
    q = """
      SELECT
        COALESCE(MAX(NULLIF(TRIM(cve_prov),'')), NULL)   AS cve_prov,
        COALESCE(MAX(concepto_sae), NULL)                AS concepto_sae,
        COALESCE(MAX(concepto), NULL)                AS concepto,
        COALESCE(MAX(regla_nombre))                 AS regla
      FROM test.coi_java_bridge
      WHERE eje=:e AND tipo=:t AND periodo=:p AND numero=:n
    """
    r = run_query("MYSQL_TEST", q, {
        "e": int(eje) % 100, "t": tipo.strip(), "p": int(periodo), "n": int(numero)
    }).mappings().first()
    return {"cve_prov": r["cve_prov"] if r else None,
            "concepto_sae": r["concepto_sae"] if r else None, 
            "concepto": r["concepto"] if r else None,
            "regla": r["regla"] if r else None
            }

# ------------------ NUEVO: cargar solo reglas del proveedor (y concepto) ------------------

def cargar_prorrateos_filtrados(proveedor:str, concepto:int|None=None) -> dict:
    """
    Carga solo ksae20t/ksae21t del proveedor (y opcionalmente del concepto).
    Retorna dict[rid] = {'nombre','proveedor','concepto_sae','vector':{idunineg->pct 0..100}}
    """
    base = """
      SELECT
        k20.idnumpon, k20.dsnombre, k20.cdcvepro, k20.cdnrocon,
        k21.idunineg, k21.flporuni
      FROM iaspel.ksae20t k20
      JOIN iaspel.ksae21t k21 ON k21.idnumpon = k20.idnumpon
      WHERE TRIM(k20.cdcvepro) = :prov
    """
    params = {"prov": (proveedor or "").strip()}
    if concepto is not None:
        base += " AND k20.cdnrocon = :cpto"
        params["cpto"] = int(concepto)

    rows = run_query("BIO", base, params).mappings().all()
    if not rows:
        return {}
    
    by_rule = defaultdict(lambda: {"vector": defaultdict(float)})
    for r in rows:
        rid = int(r["idnumpon"])
        by_rule[rid]["nombre"] = (r["dsnombre"] or "").strip()
        by_rule[rid]["proveedor"] = (r["cdcvepro"] or "").strip() or None
        by_rule[rid]["concepto_sae"] = r["cdnrocon"]
        # unidad
        try:
            u = int(r["idunineg"])
        except Exception:
            u = str(r["idunineg"]).strip()
        by_rule[rid]["vector"][u] += float(r["flporuni"] or 0.0)

    pr = {}
    for rid, data in by_rule.items():
        pr[rid] = {
            "nombre": data["nombre"],
            "proveedor": data["proveedor"],
            "concepto_sae": data["concepto_sae"],
            "vector": _vec_scale_to_100(dict(data["vector"])),
        }
    return pr

# ------------------ NUEVO: candidatos filtrados por proveedor (y concepto) ------------------

def candidatos_filtrados_por_proveedor(eje:int, tipo:str, periodo:int, numero:int,
                                       usar_concepto:bool=True, tol_pct:float=0.5, top_n:int=3) -> list[dict]:
    sig = _signals_de_poliza(eje, tipo, periodo, numero)
    prov = sig["cve_prov"]
    cpto = sig["concepto_sae"] if usar_concepto else None
    if not prov:
        return []  # sin proveedor no filtramos

    reglas = cargar_prorrateos_filtrados(prov, cpto)
    if not reglas:
        return []

    vec_pol = vector_poliza_bridge(eje, tipo, periodo, numero)
    cands = []
    for rid, info in reglas.items():
        s = _score_vectors(vec_pol, info["vector"], tol_pct=tol_pct)
        # si además coincide concepto, bonificamos un poco
        bonus = 0.0
        if cpto is not None and info["concepto_sae"] is not None and int(cpto) == int(info["concepto_sae"]):
            bonus -= 2.0
        score = max(0.0, round(s + bonus, 4))
        cands.append({
            "idnumpon": rid,
            "nombre": info["nombre"],
            "proveedor_regla": info["proveedor"],
            "concepto_regla": info["concepto_sae"],
            "score_vector": s,
            "bonus": bonus,
            "score": score,
        })
    cands.sort(key=lambda x: (x["score"], x["score_vector"], x["idnumpon"]))
    return cands[:top_n]

def comparar_poliza_vs_regla(eje:int, tipo:str, periodo:int, numero:int, idnumpon:int):
    """
    Lado a lado por unidad: unidad, pct_poliza, pct_regla, diff, abs_diff.
    Retorna dict con 'rows', 'totales', 'nombre_regla'.
    """
    vec_p = vector_poliza_bridge(eje, tipo, periodo, numero)
    vec_r, nombre = obtener_vector_regla(idnumpon)

    keys = sorted(set(vec_p) | set(vec_r), key=lambda k: (isinstance(k, str), k))
    rows = []
    for k in keys:
        p = round(vec_p.get(k, 0.0), 4)
        r = round(vec_r.get(k, 0.0), 4)
        d = round(p - r, 4)
        rows.append({"unidad": k, "pct_poliza": p, "pct_regla": r, "diff": d, "abs_diff": abs(d)})

    tot_pol = round(sum(vec_p.values()), 4)
    tot_reg = round(sum(vec_r.values()), 4)
    tot_diff = round(tot_pol - tot_reg, 4)

    rows.sort(key=lambda x: (-x["abs_diff"], x["unidad"]))  # mayores discrepancias primero

    return {
        "rows": rows,
        "totales": {"poliza": tot_pol, "regla": tot_reg, "diff": tot_diff},
        "nombre_regla": nombre,
    }

def obtener_vector_regla(idnumpon: int) -> tuple[dict, str | None]:
    """
    Devuelve (vector, nombre) de la regla:
      vector = {idunineg -> pct (0..100)}
    """
    sql = """
      SELECT k20.dsnombre, k21.idunineg, k21.flporuni
      FROM iaspel.ksae20t k20
      JOIN iaspel.ksae21t k21 ON k21.idnumpon = k20.idnumpon
      WHERE k20.idnumpon = :rid
      ORDER BY k21.idunineg
    """
    rows = run_query("BIO", sql, {"rid": int(idnumpon)}).mappings().all()
    if not rows:
        return {}, None
    nombre = (rows[0]["dsnombre"] or "").strip()
    buckets = defaultdict(float)
    for r in rows:
        try:
            u = int(r["idunineg"])
        except Exception:
            u = str(r["idunineg"]).strip()
        buckets[u] += float(r["flporuni"] or 0.0)
    return _vec_scale_to_100(dict(buckets)), nombre


def _suma_pct_poliza(eje:int, tipo:str, periodo:int, numero:int) -> float:
    vec = vector_poliza_bridge(eje, tipo, periodo, numero)
    return round(sum(vec.values()), 4) if vec else 0.0

def polizas_pendientes(eje:int, origen:str="JAVA", limit:int=500, offset:int=0) -> List[Tuple[str,int,int,int]]:
    """
    Lista (tipo, periodo, numero, COUNT) de pólizas sin regla_id.
    """
    q = """
      SELECT tipo, periodo, numero, COUNT(*) AS n
      FROM test.coi_java_bridge
      WHERE eje=:eje AND origen=:origen AND regla_id IS NULL
      GROUP BY tipo, periodo, numero
      ORDER BY periodo, numero
      LIMIT :limit OFFSET :offset
    """
    rows = run_query("MYSQL_TEST", q, {"eje": int(eje)%100, "origen": origen, "limit": int(limit), "offset": int(offset)}).mappings().all()
    return [(r["tipo"], int(r["periodo"]), int(r["numero"]), int(r["n"])) for r in rows]


def auto_aplicar_por_poliza(
                        eje: int, tipo: str, periodo: int, numero: int,
                        usar_concepto: bool = True,
                        tol_pct: float = 0.5,
                        umbral: float = 1.0,
                        gap: float = 1.0,
                        tol_suma: float = 2.0
                    ) -> Dict[str, Any]:
    """
    Devuelve {'aplicado':bool, 'motivo':str, 'elegido':dict|None, 'candidatos':list}
    Siempre contempla proveedor y (si existe) concepto.
    """
    eje2, per, num = int(eje) % 100, int(periodo), int(numero)
    tipo = (tipo or "").strip()

    # 1) chequeo de suma de % (≈100 ± tol_suma)
    try:
        suma = _suma_pct_poliza(eje2, tipo, per, num)
    except Exception as e:
        return {"aplicado": False, "motivo": f"error suma%: {e}", "elegido": None, "candidatos": []}

    if not (100.0 - tol_suma <= suma <= 100.0 + tol_suma):
        return {"aplicado": False, "motivo": f"suma%={suma} fuera de 100±{tol_suma}", "elegido": None, "candidatos": []}

    # 2) generar candidatos (FILTRADOS por proveedor y concepto)
    cands: List[Dict[str, Any]] = []
    try:
        cands = candidatos_filtrados_por_proveedor(
            eje2, tipo, per, num,
            usar_concepto=usar_concepto,
            tol_pct=tol_pct,
            top_n=5
        )
    except Exception as e:
        return {"aplicado": False, "motivo": f"error candidatos: {e}", "elegido": None, "candidatos": []}

    if not cands:
        return {"aplicado": False, "motivo": "sin candidatos para proveedor/concepto", "elegido": None, "candidatos": []}

    sig = _signals_de_poliza(eje2, tipo, per, num)

    # 3) único candidato → aplicar
    if len(cands) == 1:
        best = cands[0]
        try:
            aplicar_prorrateo_a_poliza(eje2, tipo, per, num, int(best["idnumpon"]), best["nombre"])
            # log (opcional)
            try:
                log_aplicacion_regla(
                    eje=eje2, tipo=tipo, periodo=per, numero=num, origen="JAVA",
                    accion="auto", regla_id=best["idnumpon"], regla_nombre=best["nombre"],
                    proveedor=sig.get("cve_prov"), concepto=sig.get("concepto_sae"),
                    score=best.get("score"), gap=None, suma_pct=suma,
                    candidatos=cands, usuario="auto", nota="único candidato"
                )
            except Exception:
                pass
            return {"aplicado": True, "motivo": "único candidato", "elegido": best, "candidatos": cands}
        except Exception as e:
            return {"aplicado": False, "motivo": f"error al aplicar: {e}", "elegido": None, "candidatos": cands}

    # 4) varios → evaluar umbral y brecha
    best, second = cands[0], cands[1]
    try:
        gap_val = float(second.get("score", 9e9)) - float(best.get("score", 9e9))
    except Exception:
        gap_val = 0.0

    if float(best.get("score", 9e9)) <= float(umbral) and gap_val >= float(gap):
        try:
            aplicar_prorrateo_a_poliza(eje2, tipo, per, num, int(best["idnumpon"]), best["nombre"])
            # log (opcional)
            try:
                log_aplicacion_regla(
                    eje=eje2, tipo=tipo, periodo=per, numero=num, origen="JAVA",
                    accion="auto", regla_id=best["idnumpon"], regla_nombre=best["nombre"],
                    proveedor=sig.get("cve_prov"), concepto=sig.get("concepto_sae"),
                    score=best.get("score"), gap=gap_val, suma_pct=suma,
                    candidatos=cands, usuario="auto", nota="score<=umbral y brecha>=gap"
                )
            except Exception:
                pass
            return {"aplicado": True, "motivo": "score<=umbral y brecha>=gap", "elegido": best, "candidatos": cands}
        except Exception as e:
            return {"aplicado": False, "motivo": f"error al aplicar: {e}", "elegido": None, "candidatos": cands}

    # 5) no cumple
    return {"aplicado": False, "motivo": "no cumple umbral/brecha", "elegido": None, "candidatos": cands}

def auto_aplicar_lote(
                        eje: int, origen: str = "JAVA",
                        usar_concepto: bool = True,
                        tol_pct: float = 0.5,
                        umbral: float = 1.0,
                        gap: float = 1.0,
                        tol_suma: float = 2.0,
                        limit: int = 500, offset: int = 0,
                        dry_run: bool = False
                    ) -> Dict[str, Any]:
    pendientes = polizas_pendientes(eje, origen, limit=limit, offset=offset)
    resumen = {"procesadas": 0, "aplicadas": 0, "saltadas": 0, "detalles": []}

    for tipo, periodo, numero, _ in pendientes:
        resumen["procesadas"] += 1
        res = auto_aplicar_por_poliza(
            eje, tipo, periodo, numero,
            usar_concepto=usar_concepto,
            tol_pct=tol_pct, umbral=umbral, gap=gap, tol_suma=tol_suma
        )

        # DRY-RUN: reporta como aplicado, pero no escribe
        if res["aplicado"] and dry_run:
            res = {**res, "aplicado": False, "motivo": "DRY-RUN: se habría aplicado"}

        if res["aplicado"]:
            resumen["aplicadas"] += 1
        else:
            resumen["saltadas"] += 1

        resumen["detalles"].append({
            "tipo": tipo, "periodo": periodo, "numero": numero,
            "aplicado": res["aplicado"], "motivo": res["motivo"],
            "elegido": res["elegido"]
        })

    return resumen


""" 
    Para calcular la insercion de prorrateos en las partidas
"""

# ----------- PRORRATEOS (maestro) -----------

def cargar_prorrateos_all() -> pd.DataFrame:
    return run_query("BIO", "SELECT * FROM prorrateos")

def cargar_detalle_prorrateos_all() -> pd.DataFrame:
    return run_query("BIO", "SELECT * FROM DetalleProrrateos")

def cargar_impuestos_prorrateos_all() -> pd.DataFrame:
    return run_query("BIO", "SELECT * FROM ImpuestosProrrateos")

def cargar_unidades_prorrateos_all() -> pd.DataFrame:
    return run_query("BIO", "SELECT * FROM UnidadesProrrateos")

def _as_df(obj) -> pd.DataFrame:
    """Convierte CursorResult / list[dict] / DF en DataFrame robustamente."""
    if isinstance(obj, pd.DataFrame):
        return obj
    try:
        from sqlalchemy.engine import CursorResult
        if isinstance(obj, CursorResult):
            try:
                rows = obj.mappings().all()   # SQLAlchemy 2.x
            except Exception:
                rows = obj.fetchall()
                rows = [dict(enumerate(r)) for r in rows]
            return pd.DataFrame(rows)
    except Exception:
        pass
    try:
        return pd.DataFrame(list(obj))
    except Exception:
        return pd.DataFrame()
    

def cargar_prorrateo_completo(prorrateo_id=None) -> dict[str, pd.DataFrame]:
    """
    Si prorrateo_id es None → regresa TODAS las tablas como DataFrame.
    Si viene un id → regresa solo lo asociado a ese id (también DataFrame).
    """
    if prorrateo_id is None:
        # Estas funciones pueden devolver CursorResult; las coercionamos aquí.
        return {
            "maestro":   _as_df(cargar_prorrateos_all()),
            "detalle":   _as_df(cargar_detalle_prorrateos_all()),
            #"impuestos": _as_df(cargar_impuestos_prorrateos_all()),
            #"unidades":  _as_df(cargar_unidades_prorrateos_all()),
        }

    # ⚠️ Usa parámetros de SQLAlchemy (:id) y dicts, no %s con tuplas/listas
    sql_m = "SELECT * FROM prorrateos WHERE idnumpon = :id"
    sql_d = "SELECT * FROM DetalleProrrateos WHERE idnumpon = :id"
    #sql_i = "SELECT * FROM ImpuestosProrrateos WHERE id_prorrateo = :id"
    #sql_u = "SELECT * FROM UnidadesProrrateos  WHERE id_prorrateo = :id"

    maestro   = _as_df(run_query("BIO", sql_m, {"id": prorrateo_id}))
    detalle   = _as_df(run_query("BIO", sql_d, {"id": prorrateo_id}))
    #impuestos = _as_df(run_query("BIO", sql_i, {"id": prorrateo_id}))
    #unidades  = _as_df(run_query("BIO", sql_u, {"id": prorrateo_id}))
    
    return {"maestro": maestro, "detalle": detalle}
    #return {"maestro": maestro, "detalle": detalle, "impuestos": impuestos, "unidades": unidades}

