from models.bridge_model import *

def cargar_java_a_bridge(eje:int, origen:str="JAVA", limit:int|None=None, offset:int=0):
    return etl_aux_java_a_bridge(eje=eje, origen=origen, limit=limit, offset=offset)


def calcular_porcentajes_bridge(eje: int, origen: str = "JAVA", escala_100: bool = True):
    actualizar_porcentajes(eje=eje, origen=origen, escala_100=escala_100)
    return {"ok": True}

def sync_nombre_depto(eje: int, origen: str = "JAVA"):
    return actualizar_nombre_depto(eje=eje, origen=origen)


def sync_concepto_bridge(eje: int, origen: str = "JAVA"):
    return actualizar_concepto_desde_coi(eje=eje, origen=origen)

def sync_doc_prov_desde_sae_fb(eje:int, origen:str="JAVA", tolerancia:float=0.01, ventana_dias:int=3):
    return actualizar_doc_y_proveedor_desde_sae_FB(
        eje=eje, origen=origen, tolerancia=tolerancia, ventana_dias=ventana_dias
    )

def sync_concepto_sae_desde_paga(eje:int, origen:str="JAVA", usar_cve_prov: bool = True):
    return llenar_concepto_sae_desde_paga(eje=eje, origen=origen, usar_cve_prov=usar_cve_prov)
