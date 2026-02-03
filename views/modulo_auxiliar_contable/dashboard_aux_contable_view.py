# views/dashboard_aux_contable_view.py
import streamlit as st
import calendar
from datetime import date, timedelta
import pandas as pd
import matplotlib.pyplot as plt
from models.sae_model import insertar_en_sae_por_uso, _conn_sae_from_secrets, cargar_conceptos_por_prov
from models.conta45_model import insertar_poliza_y_auxiliares 
from views.modulo_auxiliar_contable.tab_ada_insertaSAE_view import insertarSAE
from views.modulos_iaspel.tab_poliza_ventas_view import mostrar_tab_poliza_ventas
from views.modulos_iaspel.tab_poliza_costo_ventas_view import mostrar_tab_poliza_costo_venta
from controllers.ada_controller import (
    cargar_tipos,
    cargar_documentos,
    contar_documentos_cached,
    exportar_excel,
    cargar_proveedores_activos,
    cargar_paga_por_fecha,     # snapshots SAE por rango de fechas
    cargar_compc_por_fecha,    # snapshots SAE por rango de fechas
    #detectar_patrones_paga_desde_raw,
    cargar_paga_para_patrones,
    cargar_vista_paga_prov_cpto, 
    cargar_conceptos_por_documento,
    cargar_conceptos_filtrados,
    buscar_en_paga_g03,
)

# ---------------------------
# Helpers
# ---------------------------
def _default_dates():
    hoy = date.today()
    first_this = hoy.replace(day=1)
    last_prev = first_this - timedelta(days=1)
    first_prev = last_prev.replace(day=1)
    return first_prev, hoy

def _norm_rfc(x: str) -> str:
    return (str(x) if x is not None else "").strip().upper()[:13]

def _cve_match(clave: str | None) -> str:
    base = (clave or "").strip() or "0001"
    return base.rjust(10)[:10]

def _to_num_2(x):
    try:
        return round(float(str(x).replace(",", "").replace("$", "")), 2)
    except Exception:
        return 0.0

def _first_series(dframe: pd.DataFrame, candidates):
    for c in candidates:
        if c in dframe.columns:
            return dframe[c]
    return pd.Series(index=dframe.index, dtype="object")

# ---------------------------
# Vista principal
# ---------------------------
def pantalla_dashboard_aux_conta():
    st.subheader("documentos fiscales (ada)")

    tabs = st.tabs([ "Insertar en SAE", "Poliza Ventas", "Poliza Costo de Venta"])
    
    tab_insertaSAE = tabs[0]
    tab_PolizaVentas = tabs[1]
    tab_PolizaCosto = tabs[2]
    with tab_insertaSAE:
        insertarSAE()
    
    with tab_PolizaVentas:
        st.write("Poliza de Ventas ")
        mostrar_tab_poliza_ventas()

    with tab_PolizaCosto:
        st.write("Poliza de costo de Venta")
        mostrar_tab_poliza_costo_venta()
