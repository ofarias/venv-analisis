
import streamlit as st
from controllers.usuario_controller import procesar_creacion_usuario

st.title("👤 Crear nuevo usuario")

with st.form("form_nuevo_usuario"):
    nombre = st.text_input("Nombre completo")
    username = st.text_input("Nombre de usuario")
    email = st.text_input("Correo electrónico")
    password = st.text_input("Contraseña", type="password")
    rol = st.selectbox("Rol", ["Admin", "Logistica", "Ventas"])
    submit = st.form_submit_button("Crear usuario")

if submit:
    if all([nombre, username, email, password]):
        ok, mensaje = procesar_creacion_usuario(username, nombre, email, password, rol)
        st.info(mensaje)  # Muestra siempre el mensaje, incluso si ok=False
        if ok:
            st.success(mensaje)
        else:
            st.error(mensaje)
    else:
        st.warning("Completa todos los campos.")
