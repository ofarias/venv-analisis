#presupuestos_controller.py 
from __future__ import annotations
from models.presupuesto_model import *
import pandas as pd
from typing import Optional

from models.datoscfd_model import buscar_datoscfd_mysql

def get_presupuestos(): 
    return obtener_presupuestos()

def get_unidades_activas(): 
    return obtener_unidades_activas()

def get_usuarios_activos(): 
    return obtener_usuarios_presupuestos()

def obtener_usuarios_autorizados():
    return obtener_Control_Presupuestosl()

def crear_presupuesto(data): 
    return insertar_presupuesto(data)

def get_detalle_presupuesto(id_presupuesto: int):
    return obtener_detalle_presupuesto(id_presupuesto)

#def buscar_gasto_por_uuid(uuid, folio, monto, fecha):
#    return buscar_gasto(uuid, folio, monto, fecha)

#def buscar_gasto_por_uuid(uuid, folio, monto):
#    return buscar_gasto(uuid, folio, monto)

def buscar_gasto_por_uuid(uuid, folio, monto):
    """
    busca primero en firebird (ada) vía presupuesto_model.buscar_gasto()
    y también en mysql vía datoscfd_model.buscar_datoscfd_mysql().

    retorna un dataframe unificado.
    prioridad: firebird primero; si no hay, mysql.
    si hay en ambos, concatena (sin duplicar por uuid).
    """
    uuid = (uuid or "").strip().upper()
    folio = (folio or "").strip() if folio else None
    monto = float(monto) if monto is not None and float(monto) > 0 else None

    # 1) firebird (como ya lo tenías)
    try:
        df_fb = buscar_gasto(uuid, folio, monto)  # presupuesto_model.py (firebird)
        if df_fb is None:
            df_fb = pd.DataFrame()
    except Exception:
        df_fb = pd.DataFrame()

    # 2) mysql (nuevo)
    try:
        df_my = buscar_datoscfd_mysql(uuid, folio, monto)  # datoscfd_model.py (mysql)
        if df_my is None:
            df_my = pd.DataFrame()
    except Exception:
        df_my = pd.DataFrame()

    # si solo hay uno, devolverlo
    if df_fb.empty and df_my.empty:
        return pd.DataFrame()

    # normalizar nombres de columnas a MAYÚSCULAS (tu view usa mayúsculas)
    if not df_fb.empty:
        df_fb = df_fb.copy()
        df_fb.columns = [c.upper() for c in df_fb.columns]
        df_fb["FUENTE"] = "firebird"

    if not df_my.empty:
        df_my = df_my.copy()
        df_my.columns = [c.upper() for c in df_my.columns]
        df_my["FUENTE"] = "mysql"

    # 3) asegurar columnas mínimas que tu view lee
    cols_min = [
        "ID_DOCTODIG", "UUID", "FOLIO", "SERIE", "FECHA_EMISION",
        "RFC_EMISOR", "NOMBRE_EMISOR", "RFC_RECEPTOR", "NOMBRE_RECEPTOR",
        "SUBTOTAL", "IVA", "TOTAL", "MONEDA", "TIPOCAMBIO",
        "FORMAPAGO", "METODOPAGO", "TIPOCOMPROBANTE", "USOCFDI",
        "LUGAR_EXPEDICION", "REGIMEN_FISCAL", "REGIMEN_FISCAL_RECEPTOR",
        "CONTABILIZADO", "FUENTE",
    ]

    def _ensure_cols(df: pd.DataFrame) -> pd.DataFrame:
        for c in cols_min:
            if c not in df.columns:
                df[c] = None
        return df[cols_min]

    if not df_fb.empty:
        df_fb = _ensure_cols(df_fb)
    if not df_my.empty:
        df_my = _ensure_cols(df_my)

    # 4) unir (firebird primero)
    df_all = pd.concat([df_fb, df_my], ignore_index=True)

    # 5) quitar duplicados por uuid (si existe en ambos, se queda firebird)
    # ya que firebird quedó primero en concat, keep="first" mantiene firebird
    if "UUID" in df_all.columns:
        df_all["UUID"] = df_all["UUID"].astype(str).str.upper().str.strip()
        df_all = df_all.drop_duplicates(subset=["UUID"], keep="first")

    return df_all

def get_conceptos_sae():
    return obtener_conceptos_sae()

def get_presupuestos_por_usuario_unidades(username):
    return obtener_unidades_presupuestos_por_usuario(username)

def get_presupuestos_por_usuario(username):
    return obtener_presupuestos_por_usuario(username)

def get_unidades_por_presupuesto_y_usuario(nombre_presupuesto, username):
    return obtener_unidades_por_presupuesto_y_usuario(nombre_presupuesto, username)

def get_id_detalle_presupuesto(nombre_presupuesto, unidad_nombre, username):
    return obtener_id_detalle_presupuesto(nombre_presupuesto, unidad_nombre, username)

def crear_comprobante_presupuesto(data):
    return insertar_comprobante_presupuesto(data)

def get_info_gasto_registrado(uuid):
    return obtener_info_gasto_registrado(uuid)

def get_datos_cfdi(uuid):
    return obtener_datos_cfdi(uuid)

def get_comprobantes_por_mes(username):
    return obtener_comprobantes_por_mes(username)

def get_gastos_no_fiscales_por_usuario(usuario_id: int):
   return obtener_gastos_no_fiscales_por_usuario(usuario_id)

def get_gastos_fiscales_por_usuario(username: str):
    """
    Devuelve los gastos fiscales (CFDI) del usuario autenticado.
    """
    return obtener_gastos_fiscales_por_usuario(username)
