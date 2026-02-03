import streamlit as st
import pandas as pd
import io
from database.conexion import obtener_conexion
from models.usuario_model import obtener_todos_usuarios
from views.modulos_documentos.admin_tipos import get_logical_type_path

def exportar_permisos():
    st.title("📤 Exportar árbol de permisos por usuario")

    usuarios = obtener_todos_usuarios()
    usuario = st.selectbox("Selecciona un usuario", usuarios)

    if not usuario:
        st.warning("Selecciona un usuario para continuar.")
        return

    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)

    # Permisos sobre carpetas (tipos)
    cursor.execute("""
        SELECT r.nombre AS tipo
        FROM usuarios_roles ur
        JOIN roles r ON ur.id_rol = r.id
        WHERE ur.username = %s
    """, (usuario,))
    carpetas_permitidas = set([r["tipo"] for r in cursor.fetchall()])

    # Obtener todas las carpetas
    cursor.execute("SELECT id, nombre FROM tipos_documento")
    tipos_all = cursor.fetchall()
    tipo_id_map = {t["id"]: t["nombre"] for t in tipos_all}

    carpetas_por_id = {t["id"]: get_logical_type_path(t["id"]) for t in tipos_all}

    # Permisos sobre archivos
    cursor.execute("""
        SELECT pd.documento_id, vd.nombre_archivo
        FROM permisos_documento pd
        JOIN versiones_documento vd ON pd.documento_id = vd.documento_id
        WHERE pd.username = %s
        AND vd.version = (
            SELECT MAX(version) FROM versiones_documento WHERE documento_id = pd.documento_id
        )
    """, (usuario,))
    archivos_con_permisos = cursor.fetchall()
    archivo_map = {}
    for row in archivos_con_permisos:
        archivo_map[row["documento_id"]] = row["nombre_archivo"]

    # Obtener todos los documentos para ver a qué tipo pertenecen
    cursor.execute("""
        SELECT d.id, d.tipo_id
        FROM documentos d
        WHERE d.estatus != 'Eliminado'
    """)
    docs_all = cursor.fetchall()
    conn.close()

    rows = []

    for doc in docs_all:
        tipo_id = doc["tipo_id"]
        tipo_nombre = tipo_id_map.get(tipo_id, "¿?")
        ruta = carpetas_por_id.get(tipo_id, "¿?")

        archivo = archivo_map.get(doc["id"])
        tiene_permiso_archivo = "Sí" if archivo else "No"
        tiene_permiso_carpeta = "Sí" if tipo_nombre in carpetas_permitidas else "No"

        rows.append({
            "Usuario": usuario,
            "Carpeta": ruta,
            "Archivo": archivo or "",
            "Permiso Carpeta": tiene_permiso_carpeta,
            "Permiso Archivo": tiene_permiso_archivo
        })

    df = pd.DataFrame(rows)

    col1, col2, col3 = st.columns([1, 1, 2])

    with col1:
        filtro_perm_carpeta = st.selectbox("Permiso Carpeta", ["Todos", "Sí", "No"])

    with col2:
        filtro_perm_archivo = st.selectbox("Permiso Archivo", ["Todos", "Sí", "No"])

    with col3:
        filtro_nombre_archivo = st.text_input("Buscar archivo")

    # Aplicar filtros
    df_filtrado = df.copy()

    if filtro_perm_carpeta != "Todos":
        df_filtrado = df_filtrado[df_filtrado["Permiso Carpeta"] == filtro_perm_carpeta]

    if filtro_perm_archivo != "Todos":
        df_filtrado = df_filtrado[df_filtrado["Permiso Archivo"] == filtro_perm_archivo]

    if filtro_nombre_archivo:
        df_filtrado = df_filtrado[df_filtrado["Archivo"].str.contains(filtro_nombre_archivo, case=False, na=False)]

    st.dataframe(df_filtrado, use_container_width=True)

    # Descargar solo lo filtrado
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df_filtrado.to_excel(writer, index=False, sheet_name="Permisos")

    st.download_button(
        label="📥 Descargar Excel",
        data=output.getvalue(),
        file_name=f"permisos_{usuario}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

