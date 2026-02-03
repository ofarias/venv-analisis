# /home/ofarias/venv-analisis/views/login_view.py

import streamlit as st
from controllers.auth_controller import handle_redirect, get_login_url
from logs.logger import registrar_log
from settings import LOGO_PATH, NOMBRE_SISTEMA
from PIL import Image
import os

def mostrar_login():
    # 1. Muestra el logo y el título (esto se queda igual)
    if os.path.exists(LOGO_PATH):
        imagen = Image.open(LOGO_PATH)
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.image(imagen, width=800)
            st.markdown(f"<h2 style='text-align: center; color: #2E86C1'>{NOMBRE_SISTEMA}</h2>", unsafe_allow_html=True)
    else:
        st.title("❌ No se encontró el logo")
        st.caption(f"Ruta buscada: {LOGO_PATH}")

    # 2. Revisa si Microsoft nos envió un código de autorización
    query_params = st.query_params
    auth_code = query_params.get("code")

    if auth_code and not st.session_state.get("usuario"):
        # Si hay un código, lo intercambiamos por los datos del usuario
        user_data_from_microsoft = handle_redirect(auth_code)
        if user_data_from_microsoft:
            # Guardamos los datos en la sesión
            st.session_state["usuario"] = {
                "username": user_data_from_microsoft.get('preferred_username'),
                "nombre": user_data_from_microsoft.get('name'),
                # Los roles debes gestionarlos tú. Microsoft no los envía por defecto.
                # Puedes asignarlos aquí basándote en el email del usuario desde tu base de datos.
                "roles": ["Usuario Autenticado"] # Ejemplo
            }
            
            # Registramos el log como lo hacías antes
            registrar_log(st.session_state["usuario"]["username"], "Inicio de sesión con Microsoft", "-")
            
            # Limpiamos la URL y recargamos la página para mostrar el estado de "logueado"
            st.query_params.clear()
            st.rerun()

    # 3. Si no hay usuario en la sesión, mostramos el botón de login
    if "usuario" not in st.session_state or st.session_state["usuario"] is None:
        st.title("🔐 Inicia sesión")
        
        # Obtenemos la URL de login desde el controlador
        login_url = get_login_url()
        
        # Mostramos el botón que redirige al usuario a la página de Microsoft
        st.link_button("Entrar con Microsoft", login_url)
        
        # Detenemos la ejecución aquí para que no se muestre el resto de la app
        st.stop()
        
    # Si llegamos aquí, significa que el usuario ya está en st.session_state["usuario"]
    # y la función termina, permitiendo que tu main.py continúe.