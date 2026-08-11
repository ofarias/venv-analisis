import streamlit as st
import os
from database.conexion import obtener_conexion
from settings import BASE_DIR
import base64
import html

DOCS_POR_PAGINA = 25


def _ruta_desde_tipo(cursor, tipo_id):
    """Sube por la jerarquía de tipos_documento y arma la ruta 'padre/.../nombre'."""
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
    return "/".join(segments)


def obtener_ruta(documento_id):
    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT tipo_id FROM documentos WHERE id = %s", (documento_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return ""
    ruta = _ruta_desde_tipo(cursor, row["tipo_id"])
    conn.close()
    return ruta


def ruta_directorio(tipo_id):
    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)
    ruta = _ruta_desde_tipo(cursor, tipo_id)
    conn.close()
    return ruta

def buscar_documentos(query, pagina=1, por_pagina=DOCS_POR_PAGINA):
    # Escapamos los comodines de LIKE (%, _) y el backslash, para que una
    # búsqueda literal como "50%" no se interprete como wildcard.
    query_escapada = query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    like = f"%{query_escapada}%"

    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM documentos d
        JOIN (
            SELECT documento_id, MAX(version) AS ultima_version
            FROM versiones_documento
            GROUP BY documento_id
        ) ult ON d.id = ult.documento_id
        JOIN versiones_documento vd
          ON d.id = vd.documento_id AND vd.version = ult.ultima_version
        WHERE d.titulo LIKE %s OR vd.nombre_archivo LIKE %s
    """, (like, like))
    total = cursor.fetchone()["total"]
    total_paginas = max(1, -(-total // por_pagina))
    pagina = min(max(pagina, 1), total_paginas)
    offset = (pagina - 1) * por_pagina

    cursor.execute("""
        SELECT d.id, d.titulo, d.descripcion, d.creado_por, d.fecha_creacion, d.estatus,
               vd.nombre_archivo, vd.tamaño, vd.extension, vd.fecha_subida,
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
        LIMIT %s OFFSET %s
    """, (like, like, por_pagina, offset))
    docs = cursor.fetchall()
    conn.close()
    return docs, total


def obtener_permisos_documento(documento_id):
    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT *
        FROM permisos_documento
        WHERE documento_id = %s
    """, (documento_id,))
    perms = cursor.fetchall()
    conn.close()
    return perms


def obtener_permisos_documentos(documento_ids):
    """Trae los permisos de varios documentos en una sola query, agrupados por documento_id."""
    if not documento_ids:
        return {}
    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)
    placeholders = ",".join(["%s"] * len(documento_ids))
    cursor.execute(
        f"SELECT * FROM permisos_documento WHERE documento_id IN ({placeholders})",
        tuple(documento_ids)
    )
    perms = cursor.fetchall()
    conn.close()
    permisos_por_doc = {}
    for p in perms:
        permisos_por_doc.setdefault(p["documento_id"], []).append(p)
    return permisos_por_doc


def obtener_archivo_documento(documento_id):
    """Trae el archivo (bytes) de la última versión de un documento, bajo demanda
    (solo se llama para documentos autorizados que el usuario está viendo)."""
    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT archivo, nombre_archivo, extension
        FROM versiones_documento
        WHERE documento_id = %s
        ORDER BY version DESC
        LIMIT 1
    """, (documento_id,))
    row = cursor.fetchone()
    conn.close()
    return row


def format_size(size_in_bytes):
    if size_in_bytes is None:
        return "—"
    if size_in_bytes < 1024 * 1024:  # Si es menor a 1 MB (1024 KB)
        size_kb = size_in_bytes / 1024
        return f"{size_kb:.2f} KB" # Formatear a dos decimales y añadir "KB"
    else:
        size_mb = size_in_bytes / (1024 * 1024)
        return f"{size_mb:.2f} MB" # Formatear a dos decimales y añadir "MB"

# ——— Helpers para la tabla de documentos ———
def img_to_datauri(path, width=16):
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f'data:image/png;base64,{b64}'
# Mapa de iconos
ICONS_DIR = os.path.join(BASE_DIR, "Media", "icons")
ICON_MAP = {
    'xlsx': img_to_datauri(os.path.join(ICONS_DIR, 'xlsx.png')),
    'xls':  img_to_datauri(os.path.join(ICONS_DIR, 'xlsx.png')),
    'pdf':  img_to_datauri(os.path.join(ICONS_DIR, 'pdf.png')),
    'txt':  img_to_datauri(os.path.join(ICONS_DIR, 'txt.png')),
    'docx': img_to_datauri(os.path.join(ICONS_DIR, 'word.png')),
    'doc':  img_to_datauri(os.path.join(ICONS_DIR, 'word.png')),
    'pptx': img_to_datauri(os.path.join(ICONS_DIR, 'pptx.png')),
    'ppt':  img_to_datauri(os.path.join(ICONS_DIR, 'pptx.png')),
    'png':  img_to_datauri(os.path.join(ICONS_DIR, 'png.png')),
    'jpg':  img_to_datauri(os.path.join(ICONS_DIR, 'jpg.png')),
    'jpeg': img_to_datauri(os.path.join(ICONS_DIR, 'jpeg.png')),
}
DEFAULT_ICON_HTML = '📄'

def render_document_table(documentos, roles_usuario, key_prefix="doc"):
    permisos_por_doc = obtener_permisos_documentos([doc['id'] for doc in documentos])

    encabezados = ["Nombre", "Modificado", "Modificado por", "Tamaño", "Versión", "Descargar", "Permisos"]
    anchos = [3, 1.2, 1.4, 1, 0.8, 1, 0.8]

    header_cols = st.columns(anchos)
    for col, titulo in zip(header_cols, encabezados):
        col.markdown(f"**{titulo}**")

    for doc in documentos:
        usuarios_doc = permisos_por_doc.get(doc['id'], [])
        usuarios_con_permiso = [u["username"] for u in usuarios_doc]
        ext = doc['extension'].lower()
        icon_data = ICON_MAP.get(ext)
        nombre = doc['nombre_archivo']
        nombre_html = html.escape(nombre)
        fecha = (doc['fecha_subida'].strftime("%Y-%m-%d")
                 if hasattr(doc['fecha_subida'], 'strftime')
                 else doc['fecha_subida'])
        mod_por = doc['subido_por']
        tamanio = format_size(doc['tamaño'])
        version = doc['version_actual']
        ruta = obtener_ruta(doc['id'])
        autorizado = (
                    doc['tipo_nombre'] in roles_usuario or
                    st.session_state.get("username") in usuarios_con_permiso
                    )

        cols = st.columns(anchos)
        with cols[0]:
            if icon_data:
                st.markdown(
                    f'<img src="{icon_data}" width="24" style="vertical-align:middle; margin-right:8px;">{nombre_html}',
                    unsafe_allow_html=True
                )
            else:
                st.markdown(f"{DEFAULT_ICON_HTML} {nombre_html}", unsafe_allow_html=True)
        cols[1].write(fecha)
        cols[2].write(mod_por)
        cols[3].write(tamanio)
        cols[4].write(version)

        with cols[5]:
            if autorizado:
                # El archivo solo se lee de la base de datos aquí, para el
                # documento autorizado que se está pintando — ya no se trae
                # el BLOB completo de todos los documentos al listar la carpeta.
                archivo_row = obtener_archivo_documento(doc['id'])
                if archivo_row:
                    mime = {
                        'pdf': 'application/pdf',
                        'png': 'image/png',
                        'jpg': 'image/jpeg',
                        'jpeg': 'image/jpeg'
                    }.get(ext, 'application/octet-stream')
                    st.download_button(
                        "⬇️", data=archivo_row['archivo'], file_name=nombre, mime=mime,
                        key=f"{key_prefix}_dl_{doc['id']}"
                    )
            else:
                st.markdown(
                    f'<span title="No tienes permiso para descargar. Ruta: {html.escape(ruta)}">🔒</span>',
                    unsafe_allow_html=True
                )

        with cols[6]:
            if st.button("🔑", key=f"{key_prefix}_perm_{doc['id']}"):
                st.session_state["ver_permisos_doc"] = doc['id']

    perm_doc_id = st.session_state.get("ver_permisos_doc")
    if perm_doc_id and any(doc['id'] == perm_doc_id for doc in documentos):
        permisos = obtener_permisos_documento(perm_doc_id)
        with st.expander("🔑 Permisos de este documento", expanded=True):
            if permisos:
                for p in permisos:
                    st.write(
                        f"- Usuario: **{p['username']}** — "
                        f"Editar: {'Sí' if p.get('puede_editar') else 'No'}, "
                        f"Eliminar: {'Sí' if p.get('puede_eliminar') else 'No'}"
                    )
            else:
                st.write("_No hay permisos registrados._")

def obtener_tipos_documento():
    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM tipos_documento ORDER BY padre_id IS NULL DESC, padre_id, nombre")
    tipos = cursor.fetchall()
    conn.close()
    return tipos

def obtener_documentos_por_tipo(tipo_id, pagina=1, por_pagina=DOCS_POR_PAGINA):
    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT COUNT(*) AS total FROM documentos WHERE tipo_id = %s", (tipo_id,))
    total = cursor.fetchone()["total"]
    total_paginas = max(1, -(-total // por_pagina))
    pagina = min(max(pagina, 1), total_paginas)
    offset = (pagina - 1) * por_pagina

    cursor.execute("""
        SELECT
            d.id, d.titulo, d.descripcion,
            d.creado_por, d.fecha_creacion, d.estatus,
            vd.nombre_archivo, vd.tamaño, vd.extension,
            vd.fecha_subida,
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
        LIMIT %s OFFSET %s
    """, (tipo_id, por_pagina, offset))
    documentos = cursor.fetchall()
    conn.close()
    return documentos, total


def mostrar_controles_paginacion(key, total, por_pagina):
    total_paginas = max(1, -(-total // por_pagina))
    pagina = min(max(st.session_state.get(key, 1), 1), total_paginas)
    st.session_state[key] = pagina

    col_prev, col_info, col_next = st.columns([1, 2, 1])
    with col_prev:
        if st.button("⬅️ Anterior", key=f"{key}_prev", disabled=(pagina <= 1)):
            st.session_state[key] = pagina - 1
            st.rerun()
    with col_info:
        st.markdown(
            f"<div style='text-align:center'>Página {pagina} de {total_paginas} · {total} documentos</div>",
            unsafe_allow_html=True
        )
    with col_next:
        if st.button("Siguiente ➡️", key=f"{key}_next", disabled=(pagina >= total_paginas)):
            st.session_state[key] = pagina + 1
            st.rerun()


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
            #st.write(" > ", end="")
            st.markdown(" > ", unsafe_allow_html=True)
def mostrar_subtipos_y_documentos(tipo_id_actual, tipos, roles_usuario):
    tipo_actual = next((t for t in tipos if t["id"] == tipo_id_actual), None)
    if not tipo_actual:
        return

    mostrar_breadcrumb(tipo_id_actual, tipos)
    st.markdown(f"### 📜 Descripción del tipo:  \n{tipo_actual.get('descripcion', 'Sin descripción')}")

    subtipos = [t for t in tipos if t["padre_id"] == tipo_id_actual and t["nombre"] in roles_usuario]
    if subtipos:
        st.subheader("Subtipos")
        for s in subtipos:
            if st.button(f"📂 Sub- {s['nombre']}", key=f"subtipo_{s['id']}"):
                st.session_state["tipo_id"] = s["id"]
                st.rerun()

    #### Inicio de cambios

    pagina_key = f"pagina_folder_{tipo_id_actual}"
    documentos, total = obtener_documentos_por_tipo(
        tipo_id_actual, pagina=st.session_state.get(pagina_key, 1)
    )
    if documentos:

        ruta_dir = ruta_directorio(tipo_id_actual)

        st.markdown(
        f"<h3>📄 Documentos en :<br> <span style='color:blue'>{ruta_dir}</span></h3>",
        unsafe_allow_html=True
)
        render_document_table(documentos, roles_usuario, key_prefix="folder")
        mostrar_controles_paginacion(pagina_key, total, DOCS_POR_PAGINA)

    else:
        st.info("No hay documentos para este tipo.")

def mostrar_menu_documentos():
    st.title("📁 Menú de Tipos de Documento")
    roles_usuario = st.session_state.get("roles")
    # ——— Buscador de documentos ———
    search = st.text_input("🔍 Buscar documentos", "")
    if search:
        pagina_key = f"pagina_search_{search}"
        resultados, total = buscar_documentos(search, pagina=st.session_state.get(pagina_key, 1))
        st.subheader(f"Resultados de búsqueda para «{search}» ({total})")
        if resultados:
            render_document_table(resultados, roles_usuario, key_prefix="search")
            mostrar_controles_paginacion(pagina_key, total, DOCS_POR_PAGINA)
        else:
            st.info("No se encontraron documentos que coincidan.")
        #return  # salimos para no mostrar el listado de tipos

    tipos = obtener_tipos_documento()
    tipos_padre = [t for t in tipos if t["padre_id"] is None]
    #roles_usuario = st.session_state.get("roles")

    st.subheader("Tipos principales")
    cols = st.columns(6)

#####
    # 1) Leer el param al inicio
    params = st.query_params
    if "tipo_id" in params:
        try:
            st.session_state["tipo_id"] = int(params["tipo_id"])
        except:
            pass

    cols = st.columns(6)
    for i, tipo in enumerate(tipos_padre):
        with cols[i % 6]:
            imagen_nombre = tipo.get("imagen")

            if imagen_nombre:
                ruta = os.path.join("static", "tipos", imagen_nombre)
                if os.path.exists(ruta):
                    with open(ruta, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode()
                    st.markdown(
                        f"""
                        <div style='width:200px; height:200px; display:flex; align-items:center; justify-content:center; overflow:hidden;'>
                            <img src="data:image/png;base64,{b64}" style='width:100%; height:auto; max-height:200px; object-fit:contain;'/>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
                else:
                    st.warning(f"{tipo['nombre']} (Imagen no encontrada en static/tipos)")
            else:
                st.warning(f"{tipo['nombre']} (Sin imagen asociada)")

            # Mostrar nombre (solo texto, sin botón)
            
            # Si tiene permiso, habilita el botón
            if tipo["nombre"] in roles_usuario:
                if st.button(f"{tipo['nombre']}", key=f"btn_{tipo['id']}"):
                    st.session_state["tipo_id"] = tipo["id"]
                    st.rerun()
            else: 
                st.caption(tipo["nombre"])


        ##    imagen_nombre = tipo.get("imagen")
        ##    if imagen_nombre:
        ##        ruta = os.path.join("static", "tipos", imagen_nombre)
        ##        if os.path.exists(ruta):
        ##            with open(ruta, "rb") as f:
        ##                b64 = base64.b64encode(f.read()).decode()
        ##            #st.image(f"data:image/png;base64,{b64}", width=200)
        ##            st.markdown(
        ##                f"""
        ##                <div style='width:200px; height:200px; display:flex; align-items:center; justify-content:center; overflow:hidden;'>
        ##                    <img src="data:image/png;base64,{b64}" style='width:100%; height:auto; max-height:200px; object-fit:contain;'/>
        ##                </div>
        ##                """,
        ##                unsafe_allow_html=True
        ##            )
        ##        else:
        ##            st.warning(f"{tipo['nombre']} (Imagen no encontrada en static/tipos)")
        ##    else:
        ##        # Si no tiene imagen asociada, muestra un icono genérico o nada
        ##        st.warning(f"{tipo['nombre']} (Sin imagen asociada)")

        ##    # Y justo debajo un botón invisible cuyo clic
        ##    # actualiza el session_state y recarga
        ##    if st.button(f"{tipo['nombre']}", key=f"btn_{tipo['id']}"):
        ##        st.session_state["tipo_id"] = tipo["id"]
        ##        st.rerun()

            # Y finalmente etiquetamos con el nombre
            #st.caption(tipo["nombre"])


#####

    tipo_id = st.session_state.get("tipo_id")
    if tipo_id:
        tipo_seleccionado = next((t for t in tipos if t["id"] == tipo_id), None)
        if tipo_seleccionado and tipo_seleccionado["nombre"] in roles_usuario:
            mostrar_subtipos_y_documentos(tipo_id, tipos, roles_usuario)
        else:
            st.error("⛔ No estás autorizado para acceder a este tipo de documento.")
