import streamlit as st
import pandas as pd
import io
from database.conexion import obtener_conexion
from models.usuario_model import obtener_todos_usuarios
from views.modulos_documentos.admin_tipos import get_logical_type_path

def mostrar_matriz_permisos():
    st.title("📊 Matriz de permisos por usuario")

    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)

    # Obtener usuarios
    usuarios = obtener_todos_usuarios()
    #usernames = [u for u in usuarios]
    todos_los_usuarios = [u for u in usuarios]
    usuarios_seleccionados = st.multiselect("Filtrar por usuarios", todos_los_usuarios, default=[])

    # Si no hay selección, se usan todos
    if not usuarios_seleccionados:
        usuarios_filtrados = todos_los_usuarios
    else:
        usuarios_filtrados = usuarios_seleccionados

    #filtro_usuario = st.multiselect("Filtrar por usuario", usernames, default=usernames)

    # Obtener todas las carpetas
    cursor.execute("SELECT id, nombre FROM tipos_documento")
    tipos_all = cursor.fetchall()
    tipo_id_map = {t["id"]: t["nombre"] for t in tipos_all}
    carpetas_por_id = {t["id"]: get_logical_type_path(t["id"]) for t in tipos_all}

    # Obtener permisos sobre carpetas
    cursor.execute("SELECT username, r.nombre AS tipo FROM usuarios_roles ur JOIN roles r ON ur.id_rol = r.id")
    permisos_carpeta = cursor.fetchall()
    permisos_carpeta_dict = {(p["username"], p["tipo"]): True for p in permisos_carpeta}

    # Obtener todos los documentos
    cursor.execute("SELECT d.id, d.tipo_id FROM documentos d WHERE d.estatus != 'Eliminado'")
    docs_all = cursor.fetchall()

    # Obtener permisos sobre archivos
    cursor.execute("SELECT username, documento_id FROM permisos_documento")
    permisos_archivo = cursor.fetchall()
    permisos_archivo_dict = {(p["username"], p["documento_id"]): True for p in permisos_archivo}

    # Obtener nombre de los documentos
    cursor.execute("""
        SELECT vd.documento_id, vd.nombre_archivo
        FROM versiones_documento vd
        INNER JOIN (
            SELECT documento_id, MAX(version) AS max_ver
            FROM versiones_documento
            GROUP BY documento_id
        ) v2 ON vd.documento_id = v2.documento_id AND vd.version = v2.max_ver
    """)
    nombres_docs = cursor.fetchall()
    nombre_doc_dict = {d["documento_id"]: d["nombre_archivo"] for d in nombres_docs}

    conn.close()

    # Crear tabla con columnas: Ruta Carpeta, Archivo y usuarios filtrados
    rows = []
    for doc in docs_all:
        doc_id = doc["id"]
        tipo_id = doc["tipo_id"]
        ruta = carpetas_por_id.get(tipo_id, "?")
        archivo = nombre_doc_dict.get(doc_id, f"Archivo {doc_id}")

        fila = {"Ruta Carpeta": ruta, "Archivo": archivo}

        for user in usuarios_filtrados:
            tiene_archivo = permisos_archivo_dict.get((user, doc_id), False)
            tiene_carpeta = permisos_carpeta_dict.get((user, tipo_id_map.get(tipo_id, "")), False)
            if tiene_archivo:
                fila[user] = "✅"
            elif tiene_carpeta:
                fila[user] = "🔒"
            else:
                fila[user] = ""

        rows.append(fila)

    #df_matriz = pd.DataFrame(rows)
    df_matriz = pd.DataFrame(rows)
    st.dataframe(df_matriz, use_container_width=True, height=700)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df_matriz.to_excel(writer, sheet_name="MatrizPermisos", index=False)

    st.download_button(
        label="📥 Descargar Excel",
        data=output.getvalue(),
        file_name="matriz_permisos.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
