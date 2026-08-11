import streamlit as st
import datetime
from models.documento_model import guardar_documento, obtener_tipos_documento_con_ruta, obtener_usuarios
from logs.logger import registrar_log


def mostrar_formulario_subida():
    st.subheader("➕ Subir nuevo documento")

    roles_usuario = st.session_state.get("roles", [])
    tipos = obtener_tipos_documento_con_ruta()
    # Mismo criterio de acceso que Navegar: el nombre del tipo debe estar
    # entre los roles del usuario, en cualquier nivel de la jerarquía.
    tipos_permitidos = [t for t in tipos if t["nombre"] in roles_usuario]

    if not tipos_permitidos:
        st.warning("No tienes ningún tipo de documento disponible para subir archivos.")
        return

    usuarios = obtener_usuarios()

    if "form_subida_key" not in st.session_state:
        st.session_state["form_subida_key"] = 0
    k = st.session_state["form_subida_key"]

    nombre = st.text_input("Nombre del documento", key=f"subida_nombre_{k}")
    descripcion = st.text_area("Descripción", key=f"subida_descripcion_{k}")
    # ruta_completa como llave: a diferencia del nombre solo, es única —
    # hay 7 nombres de tipo duplicados en la base (hasta 12 veces cada uno),
    # así que usar solo "nombre" hacía inalcanzables la mayoría de esos subtipos.
    tipo_dict = {t["ruta_completa"]: t["id"] for t in tipos_permitidos}
    tipo_seleccionado = st.selectbox("Tipos de documento", list(tipo_dict.keys()), key=f"subida_tipo_{k}")
    tipo = tipo_dict[tipo_seleccionado]
    archivo = st.file_uploader("Selecciona un archivo", key=f"subida_archivo_{k}")
    permisos = st.multiselect("Asignar permisos", ["Ver", "Editar", "Eliminar"], key=f"subida_permisos_{k}")
    usuarios_asignados = st.multiselect("Asignar a usuarios", [u["username"] for u in usuarios], key=f"subida_usuarios_{k}")

    if st.button("📤 Subir documento"):
        if archivo and nombre:
            contenido = archivo.read()
            extension = archivo.name.split(".")[-1]
            version = 1
            usuario = st.session_state["usuario"]["username"]
            fecha = datetime.datetime.now()

            exito = guardar_documento(nombre, descripcion, tipo, contenido, archivo.name, extension, version, usuario, fecha, permisos, usuarios_asignados)

            if exito:
                registrar_log(usuario, "Subir documento", nombre)
                st.success("✅ Documento subido correctamente")
                st.session_state["form_subida_key"] += 1
                st.rerun()
            else:
                st.error("❌ No se pudo subir el documento. Revisa los datos e intenta de nuevo.")
        else:
            st.warning("⚠️ Debes completar al menos el nombre y seleccionar un archivo")
