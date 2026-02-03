# views/modulo_unidades/dashboard_unidades.py
import streamlit as st
from views.modulo_unidades.unidades_view import pantalla_unidades
from views.modulo_unidades.usuarios_unidades_view import pantalla_usuarios_unidades

def dashboard_unidades():
    st.title("🏢 Administración de Unidades de Negocio")

    tab1, tab2 = st.tabs(["📋 Unidades", "👥 Usuarios por Unidad"])

    with tab1:
        pantalla_unidades()

    with tab2:
        pantalla_usuarios_unidades()