import streamlit as st
import os
from database.conexion import obtener_conexion
from PIL import Image
import base64
import pandas as pd
import streamlit.components.v1 as components
import textwrap
import urllib.parse
from urllib.parse import quote
from streamlit_image_select import image_select # ¡Importación clave!


# --- Las funciones auxiliares permanecen igual ---
def obtener_ruta(documento_id):
    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)
    # 1) Obtenemos el tipo_id del documento
    cursor.execute("SELECT tipo_id FROM documentos WHERE id = %s", (documento_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return ""
    tipo_id = row["tipo_id"]

    # 2) Subimos por la jerarquía de tipos_documento
    segments = []
    while tipo_id:
        cursor.execute(
            "SELECT nombre, padre_id FROM tipos_documento WHERE id = %s",
            (tipo_id,)
        )
        tr = cursor.fetchone()
        if not tr:
            break
        segments.insert(0, tr["nombre"])
        tipo_id = tr["padre_id"]

    conn.close()
    return "/".join(segments)


def ruta_directorio(tipo_id):
    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)
    segments = []
    while tipo_id:
        cursor.execute(
            "SELECT nombre, padre_id FROM tipos_documento WHERE id = %s",
            (tipo_id,)
        )
        tr = cursor.fetchone()
        if not tr:
            break
        segments.insert(0, tr["nombre"])
        tipo_id = tr["padre_id"]

    conn.close()
    return "/".join(segments)


def buscar_documentos(query):
    sql = """
        SELECT d.id, d.titulo, d.descripcion, d.creado_por, d.fecha_creacion, d.estatus,
               vd.nombre_archivo, vd.tamaño, vd.extension, vd.fecha_subida, vd.archivo,
               vd.version AS version_actual, vd.comentario, vd.subido_por, vd.extension as tipo, td.nombre as tipo_nombre
        FROM documentos d
        JOIN tipos_documento td on td.id = d.tipo_id
        JOIN (
            SELECT documento_id, MAX(version) AS ultima_version
            FROM versiones_documento
            GROUP BY documento_id
        ) ult ON d.id = ult.documento_id
        JOIN versiones_documento vd 
          ON d.id = vd.documento_id AND vd.version = ult.ultima_version
        WHERE d.titulo LIKE %s OR vd.nombre_archivo LIKE %s
        ORDER BY d.fecha_creacion DESC
    """
    like = f"%%{query}%%"
    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(sql, (like, like))
    docs = cursor.fetchall()
    conn.close()
    return docs


def obtener_permisos_documento(documento_id):
    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT * FROM permisos_documento 
        WHERE documento_id = %s
    """, (documento_id,))
    perms = cursor.fetchall()
    conn.close()
    return perms


def format_size(size_in_bytes):
    if size_in_bytes is None:
        return "—"
    if size_in_bytes < 1024 * 1024:
        size_kb = size_in_bytes / 1024
        return f"{size_kb:.2f} KB"
    else:
        size_mb = size_in_bytes / (1024 * 1024)
        return f"{size_mb:.2f} MB"

def img_to_datauri(path, width=16):
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f'data:image/png;base64,{b64}'

ICON_MAP = {
    'xlsx': img_to_datauri('/home/ofarias/venv-analisis/Media/icons/xlsx.png'),
    'xls':  img_to_datauri('/home/ofarias/venv-analisis/Media/icons/xlsx.png'),
    'pdf':  img_to_datauri('/home/ofarias/venv-analisis/Media/icons/pdf.png'),
    'txt':  img_to_datauri('/home/ofarias/venv-analisis/Media/icons/txt.png'),
    'docx': img_to_datauri('/home/ofarias/venv-analisis/Media/icons/word.png'),
    'doc':  img_to_datauri('/home/ofarias/venv-analisis/Media/icons/word.png'),
    'pptx': img_to_datauri('/home/ofarias/venv-analisis/Media/icons/pptx.png'),
    'ppt':  img_to_datauri('/home/ofarias/venv-analisis/Media/icons/pptx.png'),
    'png':  img_to_datauri('/home/ofarias/venv-analisis/Media/icons/png.png'),
    'jpg':  img_to_datauri('/home/ofarias/venv-analisis/Media/icons/jpg.png'),
    'jpeg': img_to_datauri('/home/ofarias/venv-analisis/Media/icons/jpeg.png'),
}
DEFAULT_ICON_HTML = '📄'

def render_document_table(documentos, roles_usuario):
    tipo_id = st.session_state.get("tipo_id", "")
    filas = ""
    for doc in documentos:
        usuarios_doc = obtener_permisos_documento(doc['id'])
        usuarios_con_permiso = [u["username"] for u in usuarios_doc]
        ext = doc['extension'].lower()
        icon_data = ICON_MAP.get(ext)
        if icon_data:
            icon_html = f'<img src="{icon_data}" width="40" style="vertical-align:middle; margin-right:12px;">'
        else:
            icon_html = DEFAULT_ICON_HTML + "&nbsp;"

        nombre = doc['nombre_archivo']
        fecha = doc['fecha_subida']
        datos = doc['archivo']
        ext   = doc['extension'].lower()
        tamanio = format_size(doc['tamaño'])
        version = doc['version_actual']
        
        b64_file = base64.b64encode(datos).decode()
        mime = {
            'pdf': 'application/pdf',
            'png': 'image/png',
            'jpg': 'image/jpeg',
            'jpeg':'image/jpeg'
        }.get(ext, 'application/octet-stream')
        data_uri = f"data:{mime};base64,{b64_file}"

        download_attr = f'download="{(nombre)}"'
        target_attr   = 'target="_blank"' if mime.startswith('image/') or mime=='application/pdf' else ''
        ruta = obtener_ruta(doc['id'])
        autorizado = (
                    doc['tipo_nombre'] in roles_usuario or 
                    st.session_state.get("username") in usuarios_con_permiso
                    )

        if autorizado:
            link_html = (
                f'<a title="{ruta}" href="{data_uri}" {download_attr} {target_attr} '
                f'style="text-decoration:none; color:inherit;">'
                f'{icon_html}{nombre}'
                f'</a>'
            )
        else:
            link_html = (
            f'<span title="No tienes permiso para descargar Ruta:{ruta}" '
            f'style="color:gray;">🔒 {icon_html}{nombre}</span>'
        )

        fecha = (doc['fecha_subida'].strftime("%Y-%m-%d")
                 if hasattr(doc['fecha_subida'],'strftime')
                 else doc['fecha_subida'])
        mod_por = doc['subido_por']

        filas += f"""
    <tr>
    <td>{link_html}</td>
    <td>{fecha}</td>
    <td>{mod_por}</td>
    <td>{tamanio}</td>
    <td>{version}</td>
    </tr>
    """
    tabla_html = textwrap.dedent(f"""
    <style>
      .tbl-custom {{ width:100%; border-collapse:collapse; }}
      .tbl-custom th, .tbl-custom td {{
        padding:8px; text-align:left; border-bottom:1px solid #ddd;
      }}
      .tbl-custom th {{ background-color:#f2f2f2; }}
      .tbl-custom tr:hover {{ background-color:#fafafa; }}
    </style>
    <table class="tbl-custom">
      <thead>
        <tr>
          <th>Nombre</th>
          <th>Modificado</th>
          <th>Modificado por</th>
          <th>Tamaño</th>
          <th>Version</th>
        </tr>
      </thead>
      <tbody>
    {filas}
      </tbody>
    </table>
    """)
    st.markdown(tabla_html, unsafe_allow_html=True)
    params = st.query_params
    if "file_id" in params:
        try:
            fid = int(params["file_id"][0])
            permisos = obtener_permisos_documento(fid)
            with st.expander("🔑 Permisos de este documento", expanded=True):
                if permisos:
                    for p in permisos:
                        st.write(f"- Rol: **{p['rol']}**, Usuario: **{p['usuario']}**")
                else:
                    st.write("_No hay permisos registrados._")
        except:
            pass

def obtener_tipos_documento():
    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM tipos_documento ORDER BY padre_id IS NULL DESC, padre_id, nombre")
    tipos = cursor.fetchall()
    conn.close()
    return tipos

def obtener_documentos_por_tipo(tipo_id):
    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT 
            d.id, d.titulo, d.descripcion,  
            d.creado_por, d.fecha_creacion, d.estatus,
            vd.nombre_archivo, vd.tamaño, vd.extension,
            vd.fecha_subida, vd.archivo,
            vd.version AS version_actual, vd.comentario,
            vd.subido_por, vd.extension as tipo, t.nombre AS tipo_nombre 
        FROM documentos d
        JOIN tipos_documento t ON d.tipo_id = t.id
        JOIN (
            SELECT documento_id, MAX(version) AS ultima_version
            FROM versiones_documento
            GROUP BY documento_id
        ) ult ON d.id = ult.documento_id
        JOIN versiones_documento vd 
          ON d.id = vd.documento_id 
         AND vd.version = ult.ultima_version
        WHERE d.tipo_id = %s
        ORDER BY d.fecha_creacion DESC
    """, (tipo_id,))
    documentos = cursor.fetchall()
    conn.close()
    return documentos

def mostrar_breadcrumb(tipo_id, tipos):
    ruta = []
    actual = next((t for t in tipos if t["id"] == tipo_id), None)
    while actual:
        ruta.insert(0, actual)
        actual = next((t for t in tipos if t["id"] == actual["padre_id"]), None)
    
    for i, t in enumerate(ruta):
        if st.button(t["nombre"], key=f"breadcrumb_{t['id']}"):
            st.session_state["tipo_id"] = t["id"]
            st.rerun()
        if i < len(ruta) - 1:
            st.write(" > ", end="")

def mostrar_subtipos_y_documentos(tipo_id_actual, tipos, roles_usuario):
    tipo_actual = next((t for t in tipos if t["id"] == tipo_id_actual), None)
    if not tipo_actual:
        return

    mostrar_breadcrumb(tipo_id_actual, tipos)
    st.markdown(f"### 📜 Descripción del tipo:  \n{tipo_actual.get('descripcion', 'Sin descripción')}")

    subtipos = [t for t in tipos if t["padre_id"] == tipo_id_actual and t["nombre"] in roles_usuario]
    #subtipos = [t for t in tipos if t["padre_id"] == tipo_id_actual]
    if subtipos:
        st.subheader("Subtipos v2")
        ##for s in subtipos:
        ##    if st.button(f"📂 Sub- {s['nombre']}", key=f"subtipo_{s['id']}"):
        ##        st.session_state["tipo_id"] = s["id"]
        ##        st.rerun()
        for s in subtipos:
            if st.button(f"📂 Sub- {s['nombre']}", key=f"subtipo_{s['id']}"):
                st.session_state["subtipo_click"] = s["id"]
                st.rerun()

        # Después del for:
        if st.session_state.get("subtipo_click"):
            st.write('Se dio click en la subcarpeta')
            st.session_state["tipo_id"] = st.session_state["subtipo_click"]
            del st.session_state["subtipo_click"]
            st.rerun()

    documentos = obtener_documentos_por_tipo(tipo_id_actual)
    if documentos:
        ruta_dir = ruta_directorio(tipo_id_actual)
        st.markdown(
            f"<h3>📄 Documentos en :<br> <span style='color:blue'>{ruta_dir}</span></h3>",
            unsafe_allow_html=True
        )
        render_document_table(documentos, roles_usuario)
    else:
        st.info("No hay documentos para este tipo.")

def mostrar_menu_documentos():
    st.title("📁 Menú de Tipos de Documento")
    roles_usuario = st.session_state.get("roles")
    
    # Buscador de documentos
    search = st.text_input("🔍 Buscar documentos", "")
    if search:
        resultados = buscar_documentos(search)
        st.subheader(f"Resultados de búsqueda para «{search}»")
        if resultados:
            render_document_table(resultados, roles_usuario)
        else:
            st.info("No se encontraron documentos que coincidan.")
        return

    tipos = obtener_tipos_documento()
    tipos_padre = [t for t in tipos if t["padre_id"] is None and t["imagen"] is not None and t["nombre"] in roles_usuario]

    st.subheader("Tipos principales")

    # --- INICIO DEL CAMBIO ---
    # Preparamos las listas para streamlit-image-select
    image_dir = "/home/ofarias/static/tipos/"
    paths_imagenes = [os.path.join(image_dir, tipo['imagen']) for tipo in tipos_padre]
    nombres_documentos = [tipo['nombre'] for tipo in tipos_padre]
    ids_documentos = [tipo['id'] for tipo in tipos_padre]

    if not paths_imagenes:
        st.info("No hay tipos de documento principales con imágenes disponibles para tu rol.")
        return

    # Usamos image_select para crear el menú de imágenes con botones
    selected_index = image_select(
        label="Selecciona una opción:",
        images=paths_imagenes,
        captions=nombres_documentos,
        use_container_width=True,
        return_value = 'index'
    )
    
    # Manejamos la selección del usuario
    if selected_index is not None:
        selected_id = ids_documentos[selected_index]
        st.session_state["tipo_id"] = selected_id
        # st.rerun() ya no es necesario aquí porque el estado de la sesión ya se ha actualizado.

    # --- FIN DEL CAMBIO ---

    tipo_id = st.session_state.get("tipo_id")
    if tipo_id:
        tipo_seleccionado = next((t for t in tipos if t["id"] == tipo_id), None)
        # Se incluye la validación de roles en la lógica de navegación
        if tipo_seleccionado and tipo_seleccionado["nombre"] in roles_usuario:
            mostrar_subtipos_y_documentos(tipo_id, tipos, roles_usuario)
        else:
            st.error("⛔ No estás autorizado para acceder a este tipo de documento.")


# Punto de entrada de la aplicación
if __name__ == "__main__":
    
    # Configuración de estado de sesión para pruebas
    if "roles" not in st.session_state:
        st.session_state["roles"] = ["Biotecsa"] # Ejemplo: Define un rol para ver un tipo principal
        # Asegúrate de que las credenciales de la DB sean correctas para la función 'obtener_conexion'
    
    st.set_page_config(layout="wide")
    mostrar_menu_documentos()
