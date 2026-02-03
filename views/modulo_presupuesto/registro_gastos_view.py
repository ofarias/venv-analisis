#registro_gastos_view.py
import streamlit as st
import pandas as pd
from controllers.presupuesto_controller import *
from views.modulo_presupuesto.tab_registrar_gastos_view import mostrar_tab_registrar_gasto
from views.modulo_presupuesto.tab_comprobantes_mes import mostrar_tab_comprobantes_mes
from views.modulo_presupuesto.tab_gastos_no_fiscales import mostrar_tab_gastos_no_fiscales
from views.modulo_presupuesto.tab_mis_gastos_no_fiscales import mostrar_tab_mis_gastos_no_fiscales
from views.modulo_presupuesto.tab_mis_gastos_fiscales import mostrar_tab_mis_gastos_fiscales

def pantalla_registro_gastos():
    st.title("💸 Registro de Gastos")
    tabs = st.tabs([
        "🔍 Registrar Gasto", 
        "📆 Comprobantes por mes", 
        "💵 Registro Gastos no Fiscales",
        "📋 Mis Gastos No Fiscales",
        "💼 Mis Gastos Fiscales",
    ])

    with tabs[0]:
        mostrar_tab_registrar_gasto()
    
    with tabs[1]:
        mostrar_tab_comprobantes_mes() 
    
    with tabs[2]:
        mostrar_tab_gastos_no_fiscales()

    with tabs[3]:
        mostrar_tab_mis_gastos_no_fiscales()

    with tabs[4]:
        mostrar_tab_mis_gastos_fiscales()