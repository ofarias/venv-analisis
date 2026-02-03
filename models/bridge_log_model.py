import json
from models.db import run_query

def log_aplicacion_regla(*, eje:int, tipo:str, periodo:int, numero:int, origen:str,
                         accion:str, regla_id:int, regla_nombre:str,
                         proveedor:str|None, concepto:int|None,
                         score:float|None, gap:float|None, suma_pct:float|None,
                         candidatos:list|None=None, usuario:str|None=None, nota:str|None=None):
    payload = {
        "eje": int(eje)%100, "tipo": tipo.strip(), "periodo": int(periodo),
        "numero": int(numero), "origen": (origen or "JAVA").strip(),
        "accion": accion, "regla_id": int(regla_id), "regla_nombre": (regla_nombre or "").strip(),
        "proveedor": (proveedor or None), "concepto_sae": (int(concepto) if concepto is not None else None),
        "score": (float(score) if score is not None else None),
        "gap": (float(gap) if gap is not None else None),
        "suma_pct": (float(suma_pct) if suma_pct is not None else None),
        "candidatos_json": json.dumps(candidatos or [], ensure_ascii=False),
        "usuario": (usuario or None), "nota": (nota or None),
    }
    sql = """
            INSERT INTO test.coi_java_bridge_log
            (ts, eje, tipo, periodo, numero, origen, accion, regla_id, regla_nombre,
            proveedor, concepto_sae, score, gap, suma_pct, candidatos_json, usuario, nota)
            VALUES (NOW(), :eje, :tipo, :periodo, :numero, :origen, :accion, :regla_id, :regla_nombre,
                    :proveedor, :concepto_sae, :score, :gap, :suma_pct, :candidatos_json, :usuario, :nota)
        """
    run_query("MYSQL_TEST", sql, payload)