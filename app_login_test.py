import streamlit as st
import streamlit_authenticator as stauth
import yaml
import bcrypt
from yaml.loader import SafeLoader
from datetime import datetime
from pathlib import Path
import pandas as pd
import sys

st.set_page_config(layout="wide")

sys.path.append("/home/ofarias/venv-analisis/")

FILE_YAML = "/home/ofarias/venv-analisis/usuarios.yaml"
LOG_FILE = "log_usuarios.txt"

def cargar_usuarios():
    try:
        with open(FILE_YAML, "r") as file:
            return yaml.load(file, Loader=SafeLoader)
    except FileNotFoundError:
        return {"credentials": {"usernames": {}}, "cookie": {"expiry_days": 3, "key": "firma_segura", "name": "auth_cookie"}}

def guardar_usuarios(data):
    with open(FILE_YAML, "w") as file:
        yaml.dump(data, file)

def registrar_log(usuario, accion, afectado):
    with open(LOG_FILE, "a") as file:
        file.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {usuario} -> {accion}: {afectado}\n")

st.set_page_config(page_title="Sistema Integral de Usuarios", layout="wide")

# cargar configuracion
with open(FILE_YAML) as file:
    config = yaml.load(file, Loader=SafeLoader)

authenticator = stauth.Authenticate(
    credentials=config["credentials"],
    cookie_name=config["cookie"]["name"],
    key=config["cookie"]["key"],
    expiry_days=config["cookie"]["expiry_days"]
)

authenticator.login(
    location="main",
    fields={
        'Form name': 'Iniciar sesión',
        'Username': 'Usuario',
        'Password': 'Contraseña',
        'Login': 'Entrar'
    }
)

auth_status = st.session_state.get("authentication_status", None)

if auth_status:
    username = st.session_state["username"]
    user_info = config["credentials"]["usernames"][username]
    rol = user_info["role"]

    # Cerrar sesión (esto es lo que faltaba antes para que funcione correctamente)
    authenticator.logout("Cerrar sesión", "sidebar")

    st.sidebar.success(f"Bienvenido {user_info['name']} ({rol})")
    registrar_log(username, "Inicio sesión", "-")

    # definir permisos
    permisos = {
        "Admin": ["🏠 Panel General", "Documentos"],
        "Desarrollo": ["📦 Documentos Cerveza", "📈 Documentos Textil"],
        "Administracion": ["🚧 PSIMizco", "📈 Sell In Mizco",  "📦 Ventas", "📈 Ventas Sell In"]
    }

    opciones = permisos.get(rol, [])

    opcion = st.sidebar.radio("Módulos", opciones)

    registrar_log(username, "Acceso a módulo", opcion)

    st.title(opcion)

    if opcion == "🏠 Panel General":
        st.write("### 📊 Bienvenido al sistema")
        st.info("Desde aquí puedes navegar entre los módulos disponibles según tu rol.")

        total_usuarios = len(config["credentials"]["usernames"])
        total_admins = sum(1 for u in config["credentials"]["usernames"].values() if u.get("role") == "Admin")
        total_ventas = sum(1 for u in config["credentials"]["usernames"].values() if u.get("role") == "Ventas")
        total_logistica = sum(1 for u in config["credentials"]["usernames"].values() if u.get("role") == "Logistica")

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Usuarios totales", total_usuarios)
        col2.metric("Admins", total_admins)
        col3.metric("Ventas", total_ventas)
        col4.metric("Logística", total_logistica)

        st.divider()
        st.subheader("📑 Historial de actividad")

        if Path(LOG_FILE).exists():
            with open(LOG_FILE, "r") as file:
                logs = file.readlines()

            logs_data = []
            for log in logs:
                if "->" in log and ":" in log:
                    fecha, resto = log.split("] ")
                    fecha = fecha.strip("[")
                    usuario_accion, modulo = resto.split(":")
                    usuario, accion = usuario_accion.split("->")
                    logs_data.append({
                        "Fecha/Hora": fecha,
                        "Usuario": usuario.strip(),
                        "Acción": accion.strip(),
                        "Módulo": modulo.strip()
                    })

            df_logs = pd.DataFrame(logs_data)

            st.dataframe(df_logs)

            excel_buffer = pd.ExcelWriter("log_actividad.xlsx", engine="xlsxwriter")
            df_logs.to_excel(excel_buffer, index=False, sheet_name="Historial")
            excel_buffer.close()

            with open("log_actividad.xlsx", "rb") as f:
                st.download_button(
                    label="📥 Descargar historial en Excel",
                    data=f,
                    file_name="historial_de_actividad.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        else:
            st.info("No hay historial de actividad todavía.")

    elif opcion == "📦 Ventas":
        #st.success("Panel exclusivo para el rol Ventas.")
        import ventas_app.app_ventas as app_ventas
        app_ventas.ejecutar_panel_ventas()
    elif opcion == "🛒 Ventas Producto x Cliente":
        import ventas_app.app_ventas_cliente_concepto as app_ventas_cliente_concepto
        app_ventas_cliente_concepto.ejecutar_panel_ventas_cliente_concepto()        
    elif opcion == "👥 Administración de usuarios" and rol == "Admin":
        st.subheader("Usuarios registrados")
        usuarios = cargar_usuarios()
        usernames = list(usuarios["credentials"]["usernames"].keys())

        for user in usernames:
            datos = usuarios["credentials"]["usernames"][user]
            st.write(f"👤 **{user}** - {datos['name']} - Rol: {datos.get('role', 'N/A')}")

        st.divider()
        st.subheader("Agregar nuevo usuario")
        with st.form("form_usuario_nuevo"):
            username_new = st.text_input("Usuario (login)")
            nombre_new = st.text_input("Nombre completo")
            email_new = st.text_input("Email")
            password_new = st.text_input("Contraseña", type="password")
            rol_new = st.selectbox("Rol", ["Admin", "Logistica", "Ventas"])
            submit_new = st.form_submit_button("Crear usuario")

        if submit_new:
            if username_new and password_new:
                if username_new in usuarios["credentials"]["usernames"]:
                    st.error("Este usuario ya existe.")
                else:
                    hashed = bcrypt.hashpw(password_new.encode(), bcrypt.gensalt()).decode()
                    usuarios["credentials"]["usernames"][username_new] = {
                        "name": nombre_new,
                        "password": hashed,
                        "email": email_new,
                        "role": rol_new
                    }
                    guardar_usuarios(usuarios)
                    registrar_log(username, "Crear usuario", username_new)
                    st.success(f"Usuario '{username_new}' creado correctamente.")
            else:
                st.error("Usuario y contraseña son obligatorios.")

        st.divider()
        st.subheader("Editar usuario existente")
        usuario_seleccionado = st.selectbox("Selecciona un usuario para editar", [""] + usernames)

        if usuario_seleccionado:
            datos = usuarios["credentials"]["usernames"][usuario_seleccionado]
            nombre_edit = st.text_input("Nombre completo", value=datos.get("name", ""))
            email_edit = st.text_input("Email", value=datos.get("email", ""))
            rol_edit = st.selectbox("Rol", ["Admin", "Logistica", "Ventas"], index=["Admin", "Logistica", "Ventas"].index(datos.get("role", "Admin")))
            cambiar_password = st.checkbox("Cambiar contraseña")

            if cambiar_password:
                password_edit = st.text_input("Nueva contraseña", type="password")
            else:
                password_edit = None

            if st.button("Guardar cambios"):
                usuarios["credentials"]["usernames"][usuario_seleccionado]["name"] = nombre_edit
                usuarios["credentials"]["usernames"][usuario_seleccionado]["email"] = email_edit
                usuarios["credentials"]["usernames"][usuario_seleccionado]["role"] = rol_edit

                if password_edit:
                    hashed = bcrypt.hashpw(password_edit.encode(), bcrypt.gensalt()).decode()
                    usuarios["credentials"]["usernames"][usuario_seleccionado]["password"] = hashed

                guardar_usuarios(usuarios)
                registrar_log(username, "Editar usuario", usuario_seleccionado)
                st.success("Cambios guardados correctamente.")

        st.divider()
        st.subheader("Eliminar usuario")
        usuario_eliminar = st.selectbox("Selecciona un usuario para eliminar", [""] + usernames)

        if usuario_eliminar:
            if st.button("Eliminar usuario"):
                del usuarios["credentials"]["usernames"][usuario_eliminar]
                guardar_usuarios(usuarios)
                registrar_log(username, "Eliminar usuario", usuario_eliminar)
                st.success(f"Usuario '{usuario_eliminar}' eliminado correctamente.")

elif auth_status is False:
    st.error("Usuario o contraseña incorrectos.")

elif auth_status is None:
    st.info("Por favor inicia sesión.")