from models.usuario_model import obtener_usuario_y_roles
import os
import streamlit as st
from controllers.auth_controller import handle_redirect, get_login_url
from logs.logger import registrar_log
from settings import LOGO_PATH, NOMBRE_SISTEMA
from PIL import Image
from models.politicas_model import obtener_politicas_pendientes_usuario

def mostrar_login():
    
    # Logo y título igual que antes
    if os.path.exists(LOGO_PATH):
        imagen = Image.open(LOGO_PATH)
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.image(imagen, width=800)
            st.markdown(f"<h2 style='text-align: center; color: #2E86C1'>{NOMBRE_SISTEMA}</h2>", unsafe_allow_html=True)
    else:
        st.title("❌ No se encontró el logo")
        st.caption(f"Ruta buscada: {LOGO_PATH}")    

    # --- Paso 1: detectar si se recibió código de Microsoft ---
    query_params = st.query_params
    auth_code = query_params.get("code")
    
    if auth_code and not st.session_state.get("usuario"):
        user_data_from_microsoft = handle_redirect(auth_code)
        ## st.write("Datos Microsoft:", user_data_from_microsoft)
        if user_data_from_microsoft:
            username = user_data_from_microsoft.get('preferred_username')
            nombre = user_data_from_microsoft.get('name')
            access_token = user_data_from_microsoft.get('access_token')  # <-- ⬅️ extrae el token
            st.warning(f"Correo recibido desde Microsoft: {username}")
            usuario_db = obtener_usuario_y_roles(username)
            
            if usuario_db:
                # Si está registrado en tu BD
                st.session_state["usuario"] = {
                    "id": usuario_db["id"],
                    "username": usuario_db["username"],
                    "nombre": usuario_db["nombre"],
                    "roles": usuario_db["roles"] or [] 
                }
                #st.session_state["roles"] = st.session_state["usuario"]["roles"]
                st.session_state["roles"] = usuario_db["roles"] or []
                st.session_state["username"] = usuario_db["username"]
                # 🔐 Guarda también el token de Microsoft
                st.session_state["microsoft_token"] = access_token
                
                ### Para Conrtrol de politicas 
                username = usuario_db["username"]
                pendientes = obtener_politicas_pendientes_usuario(username)

                st.session_state["avisos_politicas"] = pendientes  # guardar para mostrar al cargar

                registrar_log(usuario_db["username"], "Inicio de sesión con Microsoft", "-")
                st.query_params.clear()
                st.rerun()
            else:
                st.error(f"⛔ El usuario {username} no está registrado o está inactivo.")
                st.stop()
        else:
            st.error("❌ No se pudo autenticar con Microsoft.")
            st.stop()

    # --- Paso 2: si no está autenticado, muestra botón de inicio ---
    # --- Hay que arreglarlo para que no lo abra en 2 pestañas del navegador ---
    if "usuario" not in st.session_state or st.session_state["usuario"] is None:
        st.title("🔐 Inicia sesión en test")
        login_url = get_login_url()
        st.link_button("Entrar con Microsoft", login_url)
        st.stop()
    else:
        st.rerun()

    # Aquí continúa la app si ya está autenticado