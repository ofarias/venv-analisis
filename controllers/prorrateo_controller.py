## prorrateo_controller.py
from typing import Optional, Dict, Any, List
from models.prorrateo_model import *
from models.bridge_log_model import log_aplicacion_regla
from models.prorrateo_model import _signals_de_poliza, _suma_pct_poliza  

def sugerir_prorrateos(eje: int, tipo: str, periodo: int, numero: int,
                       tol_pct: float = 0.5, top_n: int = 3) -> List[Dict[str, Any]]:
    # normaliza tipos (streamlit number_input puede devolver float)
    eje = int(eje) % 100
    periodo = int(periodo)
    numero = int(numero)
    return candidatos_prorrateo_para_poliza(eje, tipo, periodo, numero, top_n=top_n, tol_pct=tol_pct)

def fijar_prorrateo(eje: int, tipo: str, periodo: int, numero: int,
                    idnumpon: int, nombre: str) -> Dict[str, Any]:
    eje = int(eje) % 100
    periodo = int(periodo)
    numero = int(numero)
    aplicar_prorrateo_a_poliza(eje, tipo, periodo, numero, int(idnumpon), nombre)
    return {"ok": True}

def sugerir_y_quiza_aplicar(eje: int, tipo: str, periodo: int, numero: int,
                            tol_pct: float = 0.5, umbral_auto: float = 1.0) -> Dict[str, Any]:
    """
    Calcula Top-3 candidatos. Si el mejor tiene score <= umbral_auto y
    hay brecha clara con el segundo, aplica automáticamente.
    """
    eje = int(eje) % 100
    periodo = int(periodo)
    numero = int(numero)

    cands = candidatos_prorrateo_para_poliza(eje, tipo, periodo, numero, top_n=3, tol_pct=tol_pct)
    res: Dict[str, Any] = {"candidatos": cands, "auto_aplicado": False, "elegido": None}

    if not cands:
        return res

    best = cands[0]
    # brecha con el segundo (si existe)
    brecha_ok = True
    if len(cands) >= 2:
        try:
            brecha_ok = (best["score"] + 1.0) <= cands[1]["score"]
        except Exception:
            brecha_ok = True

    if float(best.get("score", 9999)) <= float(umbral_auto) and brecha_ok:
        aplicar_prorrateo_a_poliza(eje, tipo, periodo, numero, int(best["idnumpon"]), best["nombre"])
        res["auto_aplicado"] = True
        res["elegido"] = best

    return res


def comparacion_detallada(eje:int, tipo:str, periodo:int, numero:int, idnumpon:int) -> Dict[str, Any]:
    eje = int(eje) % 100
    periodo = int(periodo)
    numero = int(numero)
    rid = int(idnumpon)
    return comparar_poliza_vs_regla(eje, tipo, periodo, numero, rid)

from typing import Dict, Any, List
from models.prorrateo_model import (
    candidatos_filtrados_por_proveedor,
    aplicar_prorrateo_a_poliza,
)

def sugerir_por_proveedor(eje:int, tipo:str, periodo:int, numero:int,
                          usar_concepto:bool=True, tol_pct:float=0.5, top_n:int=3) -> List[Dict[str,Any]]:
    eje = int(eje) % 100; periodo = int(periodo); numero = int(numero)
    return candidatos_filtrados_por_proveedor(eje, tipo, periodo, numero, usar_concepto, tol_pct, top_n)

def sugerir_y_auto_por_proveedor(eje:int, tipo:str, periodo:int, numero:int,
                                 usar_concepto:bool=True, tol_pct:float=0.5, umbral_auto:float=1.0) -> Dict[str,Any]:
    eje = int(eje) % 100; periodo = int(periodo); numero = int(numero)
    cands = candidatos_filtrados_por_proveedor(eje, tipo, periodo, numero, usar_concepto, tol_pct, top_n=3)
    res: Dict[str,Any] = {"candidatos": cands, "auto_aplicado": False, "elegido": None}
    if not cands:
        return res
    best = cands[0]
    brecha_ok = True
    if len(cands) >= 2:
        brecha_ok = (float(best["score"]) + 1.0) <= float(cands[1]["score"])
    if float(best["score"]) <= float(umbral_auto) and brecha_ok:
        aplicar_prorrateo_a_poliza(eje, tipo, periodo, numero, int(best["idnumpon"]), best["nombre"])
        res["auto_aplicado"] = True
        res["elegido"] = best
    return res

def fijar_prorrateo(eje:int, tipo:str, periodo:int, numero:int, idnumpon:int, nombre:str):
    eje2 = int(eje)%100; periodo=int(periodo); numero=int(numero)
    aplicar_prorrateo_a_poliza(eje2, tipo, periodo, numero, int(idnumpon), nombre)

    sig = _signals_de_poliza(eje2, tipo, periodo, numero)
    suma = _suma_pct_poliza(eje2, tipo, periodo, numero)
    log_aplicacion_regla(
        eje=eje2, tipo=tipo, periodo=periodo, numero=numero, origen="JAVA",
        accion="manual", regla_id=idnumpon, regla_nombre=nombre,
        proveedor=sig.get("cve_prov"), concepto=sig.get("concepto_sae"),
        score=None, gap=None, suma_pct=suma, candidatos=None, usuario="ui", nota="aplicación manual"
    )
    return {"ok": True}

def auto_aplicar_controller(
                            eje: int, tipo: str, periodo: int, numero: int,
                            usar_concepto: bool = True, tol_pct: float = 0.5,
                            umbral: float = 1.0, gap: float = 1.0, tol_suma: float = 2.0
                        ) -> dict:
    return auto_aplicar_por_poliza(eje, tipo, periodo, numero, usar_concepto, tol_pct, umbral, gap, tol_suma)

def auto_aplicar_lote_controller(
                            eje: int, origen: str = "JAVA",
                            usar_concepto: bool = True, tol_pct: float = 0.5,
                            umbral: float = 1.0, gap: float = 1.0, tol_suma: float = 2.0,
                            limit: int = 500, offset: int = 0, dry_run: bool = True
                        ) -> dict:
    return auto_aplicar_lote(eje, origen, usar_concepto, tol_pct, umbral, gap, tol_suma, limit, offset, dry_run)


def obtener_signals_poliza(eje:int, tipo:str, periodo:int, numero:int) -> Dict[str, Any]:
    eje = int(eje) % 100
    periodo = int(periodo)
    numero = int(numero)
    return _signals_de_poliza(eje, tipo.strip(), periodo, numero)

