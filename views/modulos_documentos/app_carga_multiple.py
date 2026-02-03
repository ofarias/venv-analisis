import streamlit as st
import os
from datetime import datetime
from database.conexion import obtener_conexion

def guardar_documento(titulo, descripcion, tipo_id, archivo, nombre_archivo, extension, tamanio, usuarios, creado_por):
    conn = obtener_conexion()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO documentos (titulo, descripcion, tipo_id, creado_por, fecha_creacion, estatus)
        VALUES (%s, %s, %s, %s, NOW(), 'Activo')
    """, (titulo, descripcion, tipo_id, creado_por))
    documento_id = cursor.lastrowid

    cursor.execute("""
        INSERT INTO versiones_documento (documento_id, version, nombre_archivo, extension, tamaño, archivo, subido_por, fecha_subida, comentario)
        VALUES (%s, 1, %s, %s, %s, %s, %s, NOW(), '')
    """, (documento_id, nombre_archivo, extension, tamanio, archivo.read(), creado_por))

    #for permiso in permisos:
    #    cursor.execute("INSERT INTO permisos_documento (documento_id, permiso) VALUES (%s, %s)", (documento_id, permiso))

    for usuario in usuarios:
        cursor.execute("INSERT INTO permisos_documento (documento_id, username, puede_editar, puede_eliminar) VALUES (%s, %s, 1, 1)", (documento_id, usuario))

    conn.commit()
    conn.close()

def cargar_multiples_documentos():
    st.title("📑 Subida múltiple de documentos")

    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT id, nombre FROM tipos_documento ORDER BY nombre")
    tipos = cursor.fetchall()

    #cursor.execute("SELECT permiso FROM catalogo_permisos ORDER BY permiso")
    #permisos = [r["permiso"] for r in cursor.fetchall()]

    cursor.execute("SELECT username FROM usuarios ORDER BY nombre")
    usuarios = [u["username"] for u in cursor.fetchall()]
    conn.close()

    tipo = st.selectbox("Tipo de documento", options=tipos, format_func=lambda x: x['nombre'])
    archivos = st.file_uploader("Selecciona los archivos", type=None, accept_multiple_files=True)
    #permisos_asignados = st.multiselect("Asignar permisos", permisos)
    usuarios_asignados = st.multiselect("Asignar a usuarios", usuarios)

    if st.button("📂 Subir documentos"):
        if not archivos:
            st.warning("Debes seleccionar al menos un archivo.")
            return

        for archivo in archivos:
            nombre = os.path.splitext(archivo.name)[0]
            extension = os.path.splitext(archivo.name)[1].lstrip('.')
            tamanio = archivo.size

            guardar_documento(
                titulo=nombre,
                descripcion=nombre,
                tipo_id=tipo['id'],
                archivo=archivo,
                nombre_archivo=archivo.name,
                extension=extension,
                tamanio=tamanio,
                #permisos=permisos_asignados,
                usuarios=usuarios_asignados,
                creado_por=st.session_state["usuario"]["username"]
            )

            st.success(f"✅ Documento '{nombre}' subido correctamente.")