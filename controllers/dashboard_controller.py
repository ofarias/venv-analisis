# dashboard_controller.py 

import streamlit as st
import pandas as pd
from models.conta45_model import insertar_poliza_y_auxiliares, inserta_poliza_ventas, inserta_poliza_costo_venta
import models.dashboard_model as dashboard_model
from models import conta45_model
from models.conta45_model import reset_prorrateos_cache
from models.dashboard_model import *
##(
##    polizas_por_tipo,
##    cobertura_prorrateo,
##    usos_por_prorrateo,
##    catalogo_prorrateos_con_uso,
##    detalle_todas_polizas,
##    catalogo_proveedores, 
##    prorrateos_por_proveedor,
##    proveedores_resumen, 
##    nombre_conceptos, 
##    cargar_prorrateos_tabla,
##    get_detalle_prorrateo,
##    update_detalle_prorrateo_rows,
##    get_pendientes_contabilizar,
##    update_estatus_prorrateos,
##    get_conceptos_aspel,
##    get_prov_nombres_desde_sae,
##    crear_prorrateo_cabecera,
##    get_unidades_prorrateo_df,
##    get_cuentas_contables_coi_df,
##    insertar_detalle_prorrateo,
##)

def get_polizas_por_tipo(eje:int, origen:str="JAVA") -> pd.DataFrame:
    return pd.DataFrame(polizas_por_tipo(eje, origen))

def get_cobertura(eje:int, origen:str="JAVA") -> pd.DataFrame:
    r = cobertura_prorrateo(eje, origen) or {}
    rows = [
        {"estado": "Con regla", "polizas": int(r.get("polizas_con_regla") or 0)},
        {"estado": "Sin regla", "polizas": int(r.get("polizas_sin_regla") or 0)},
    ]
    return pd.DataFrame(rows)

def get_usos_prorrateo(eje:int, origen:str="JAVA", limit:int=50, offset:int=0) -> pd.DataFrame:
    return pd.DataFrame(usos_por_prorrateo(eje, origen, limit, offset))

def get_catalogo_con_uso(eje:int, origen:str="JAVA", limit:int=200, offset:int=0) -> pd.DataFrame:
    return pd.DataFrame(catalogo_prorrateos_con_uso(eje, origen, limit, offset))

def get_detalle_polizas(eje:int, origen:str="JAVA", limit:int=1000, offset:int=0) -> pd.DataFrame:
    return pd.DataFrame(detalle_todas_polizas(eje, origen, limit, offset))

def get_proveedores_df() -> pd.DataFrame:
    return pd.DataFrame(catalogo_proveedores())

def get_prorrateos_por_proveedor_df(proveedor: str, eje: int, origen: str = "JAVA") -> pd.DataFrame:
    return pd.DataFrame(prorrateos_por_proveedor(proveedor, eje, origen))

def get_proveedores_resumen_df(eje:int, origen:str="JAVA") -> pd.DataFrame:
    return pd.DataFrame(proveedores_resumen(eje, origen))

def get_nombre_conceptos_df()->pd.DataFrame:
    return pd.DataFrame(nombre_conceptos())

def get_prorrateos_mysql_df(limit: int = 500, offset: int = 0, filtros: dict | None = None) -> pd.DataFrame:
    df = cargar_prorrateos_tabla(limit=limit, offset=offset, filtros=filtros or {})
    return df

def get_detalle_prorrateo_df(idnumpon: int) -> pd.DataFrame:
    return get_detalle_prorrateo(idnumpon)

def guardar_detalle_prorrateo(cambios: list[dict]) -> int:
    return update_detalle_prorrateo_rows(cambios)

def get_pendientes_contabilizar_df() -> pd.DataFrame:
    return get_pendientes_contabilizar()

def actualizar_estatus_prorrateos(cambios: list[dict]) -> int:
    return update_estatus_prorrateos(cambios)

def get_conceptos_aspel_df() -> pd.DataFrame:
    return get_conceptos_aspel()

def get_prov_nombres_sae_dict() -> dict:
    return get_prov_nombres_desde_sae()

def crear_prorrateo_cabecera_ctrl(
        dsnombre: str,
        cdnrocon: int,
        cdcvepro: str,
        importe: float,
        moneda: int,
        variacion: float,
        idusuari: int | None = None,
        estatus: int = 1,
    ) -> int:
    return crear_prorrateo_cabecera(
        dsnombre=dsnombre,
        cdnrocon=cdnrocon,
        cdcvepro=cdcvepro,
        importe=importe,
        moneda=moneda,
        variacion=variacion,
        idusuari=idusuari,
        estatus=estatus,
    )

def get_unidades_prorrateo_ctrl():
    return get_unidades_prorrateo_df()

def get_cuentas_contables_coi_ctrl():
    return get_cuentas_contables_coi_df()

def insertar_detalle_prorrateo_ctrl(filas: list[dict]) -> int:
    return insertar_detalle_prorrateo(filas)

def contabilizar_pendiente_en_coi(row: pd.Series, prorrateo_id: int | None = None, debug: bool = False) -> dict:
    """
    envuelve insertar_poliza_y_auxiliares usando st.secrets
    y mapea columnas minúsculas → mayúsculas para compatibilidad.
    """
    if not isinstance(row, pd.Series):
        row = pd.Series(row)

    # clon base
    row_coi = row.copy()

    # alias genérico: todas las columnas también en mayúsculas
    for col in list(row.index):
        upper = str(col).upper()
        if upper not in row_coi.index:
            row_coi[upper] = row[col]

    # alias específico: nombre → NOMBRE_PROV
    if "NOMBRE_PROV" not in row_coi.index:
        for cand in ("NOMBRE_PROV", "NOMBRE_PROVEEDOR", "NOMBRE"):
            if cand in row_coi.index:
                row_coi["NOMBRE_PROV"] = row_coi[cand]
                break

    # aquí podríamos agregar más alias específicos si hace falta
    # por ejemplo, si algún día necesitas mapear DESCR → APP_CONCEPTO, etc.

    res = insertar_poliza_y_auxiliares(row_coi, st.secrets, prorrateo_id=prorrateo_id, debug=debug)
    return res

def get_poliza_ventas_df(fecha_apli):

    return dashboard_model.get_poliza_ventas_df(fecha_apli)

def contabilizar_poliza_ventas_df(df):
    # una sola póliza con todos los documentos del día
    return inserta_poliza_ventas(df, st.secrets, debug=False)

def contabilizar_poliza_ventas_costo_df(df):
    # una sola póliza con todos los documentos del día
    return inserta_poliza_costo_venta(df, st.secrets, debug=False)

def obtener_costos_venta_por_fecha(fecha):
    return dashboard_model.obtener_costos_venta_por_fecha(fecha)

def obtener_costos_venta_por_fecha_remisiones(fecha):
    return dashboard_model.obtener_costos_venta_por_fecha_remisiones(fecha)

#def actualizar_concepto_prorrateo_ctrl(idnumpon: int, cdnrocon: int) -> int:
#    return actualizar_concepto_prorrateo(idnumpon=idnumpon, cdnrocon=cdnrocon)

def actualizar_concepto_prorrateo_ctrl(idnumpon: int, cdnrocon: int) -> int:
    afectados = actualizar_concepto_prorrateo(idnumpon=idnumpon, cdnrocon=cdnrocon)
    if afectados > 0:
        reset_prorrateos_cache()
    return afectados

def get_documentos_contabilizados_df() -> pd.DataFrame:
    return dashboard_model.get_documentos_contabilizados_df()

def get_reporte_cobranza_df(fecha_corte, cliente: str | None = None, vendedor: str | None = None) -> pd.DataFrame:
    return dashboard_model.get_reporte_cobranza_df(fecha_corte=fecha_corte, cliente=cliente, vendedor=vendedor)

def get_rep_ventas_lotes_df(fecha_ini, fecha_fin) -> pd.DataFrame:
    return dashboard_model.get_rep_ventas_lotes_df(fecha_ini=fecha_ini, fecha_fin=fecha_fin)
