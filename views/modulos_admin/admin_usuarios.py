import streamlit as st
from models.usuario_model import crear_usuario, obtener_usuarios, obtener_roles_disponibles
from logs.logger import registrar_log

from models.usuario_model import (
    obtener_usuarios,
    crear_usuario,
    actualizar_usuario,
    obtener_roles_usuario,
    actualizar_roles_usuario
)

def mostrar_admin_usuarios():
    st.subheader("👥 Crear nuevo usuario")

    #roles_disponibles = ["Admin", "Logistica", "Ventas"]

    roles_disponibles = obtener_roles_disponibles()
    #nuevo_rol = st.selectbox("Rol", roles_disponibles, index=roles_disponibles.index(datos["rol"]) if datos["rol"] in roles_disponibles else 0)
    #nuevo_rol = st.selectbox("Rol", roles_disponibles)
    with st.form("form_crear_usuario"):
        username = st.text_input("Usuario")
        nombre = st.text_input("Nombre completo")
        email = st.text_input("Correo electrónico")
        password = st.text_input("Contraseña", type="password")
        roles_seleccionados = st.multiselect("Roles", roles_disponibles)
        submitted = st.form_submit_button("Crear usuario")

    if submitted:
        if username and password and roles_seleccionados:
            success, msg = crear_usuario(username, nombre, email, password, roles_seleccionados)
            if success:
                registrar_log(st.session_state["usuario"]["username"], "Crear usuario", username)
                st.success(f"✅ {msg}")
            else:
                st.error(f"❌ {msg}")
        else:
            st.warning("⚠️ Usuario, contraseña y al menos un rol son obligatorios.")

    st.divider()
    st.subheader("📋 Usuarios existentes")

    usuarios = obtener_usuarios()
    for u in usuarios:
        roles = obtener_roles_usuario(u["username"])
        st.markdown(
           f"**{u['username']}** - {u['nombre']} - {u['email']} - {colorear_estatus(u['estatus'])}"
        )

    st.divider()
    st.subheader("✏️ Editar usuario existente")

    usuarios_dict = {u["username"]: u for u in usuarios}
    usuarios_lista = list(usuarios_dict.keys())

    usuario_seleccionado = st.selectbox("Selecciona un usuario", [""] + usuarios_lista)

    if usuario_seleccionado:
        datos = usuarios_dict[usuario_seleccionado]
        roles_actuales = obtener_roles_usuario(usuario_seleccionado)

        with st.form("form_editar_usuario"):
            nuevo_nombre = st.text_input("Nombre completo", value=datos["nombre"])
            nuevo_email = st.text_input("Correo electrónico", value=datos["email"])
            nuevos_roles = st.multiselect("Roles", roles_disponibles, default=roles_actuales)
            nuevo_estatus = st.selectbox("Estatus", ["Activo", "Suspendido", "Baja"], index=["Activo", "Suspendido", "Baja"].index(datos.get("estatus", "Activo")))
            cambiar_password = st.checkbox("¿Cambiar contraseña?")
            if cambiar_password:
                nueva_password = st.text_input("Nueva contraseña", type="password")
            else:
                nueva_password = None

            submit_edit = st.form_submit_button("Guardar cambios")

        if submit_edit:
            ok = actualizar_usuario(
                username=usuario_seleccionado,
                nombre=nuevo_nombre,
                email=nuevo_email,
                rol=nuevos_roles[0] if nuevos_roles else "SinRol",
                nueva_password=nueva_password,
                estatus=nuevo_estatus
            )

            if ok:
                actualizar_roles_usuario(usuario_seleccionado, nuevos_roles)
                # Si el usuario editado es el mismo que el que está autenticado, actualiza session_state
                if usuario_seleccionado == st.session_state["usuario"]["username"]:
                    st.session_state["roles"] = nuevos_roles
                    #st.write("🔐 Roles actuales en sesión:", st.session_state.get("roles"))
                registrar_log(st.session_state["usuario"]["username"], "Editar usuario", usuario_seleccionado)
                st.success("✅ Cambios guardados correctamente.")
                st.rerun()
            else:
                st.error("❌ Hubo un problema al guardar los cambios.")

def colorear_estatus(estatus):
    colores = {
        "Activo": "🟢",
        "Suspendido": "🟡",
        "Baja": "🔴"
    }
    return f"{colores.get(estatus, '')} {estatus}"

