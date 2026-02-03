import streamlit as st
import datetime
from models.documento_model import guardar_documento, obtener_tipos_documento, obtener_usuarios
from logs.logger import registrar_log


def mostrar_formulario_subida():
    st.subheader("➕ Subir nuevo documento")

    tipos = obtener_tipos_documento()
    usuarios = obtener_usuarios()

    nombre = st.text_input("Nombre del documento")
    descripcion = st.text_area("Descripción")
    tipo_dict = {t["nombre"]: t["id"] for t in tipos}
    tipo_nombre = st.selectbox("Tipos de documento", list(tipo_dict.keys()))
    tipo = tipo_dict[tipo_nombre]
    archivo = st.file_uploader("Selecciona un archivo")
    permisos = st.multiselect("Asignar permisos", ["Ver", "Editar", "Eliminar"])
    usuarios_asignados = st.multiselect("Asignar a usuarios", [u["username"] for u in usuarios])

    if st.button("📤 Subir documento"):
        if archivo and nombre:
            contenido = archivo.read()
            extension = archivo.name.split(".")[-1]
            version = 1
            usuario = st.session_state["usuario"]["username"]
            fecha = datetime.datetime.now()

            guardar_documento(nombre, descripcion, tipo, contenido, archivo.name, extension, version, usuario, fecha, permisos, usuarios_asignados)
            registrar_log(usuario, "Subir documento", nombre)

            st.success("✅ Documento subido correctamente")
            #st.rerun()
        else:
            st.warning("⚠️ Debes completar al menos el nombre y seleccionar un archivo")
