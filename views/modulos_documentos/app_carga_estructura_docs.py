import streamlit as st
import os
import mysql.connector
from database.conexion import obtener_conexion

def cargar_estructura():
    st.title("📂 Carga desde estructura de carpetas")

    ruta_base = st.text_input(
        "Ruta base en el servidor", 
        value="/home/ofarias/venv-analisis/Media/Upload/Desarrollo e innovacion/"
    )

    # Obtener tipos raíz
    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT id, nombre FROM tipos_documento WHERE padre_id IS NULL ORDER BY nombre"
    )
    tipos_documento = cursor.fetchall()
    conn.close()

    tipo_doc_raiz = st.selectbox(
        "Tipo de documento raíz", 
        tipos_documento, 
        format_func=lambda x: x["nombre"]
    )

    # Validar ruta
    if not os.path.isdir(ruta_base):
        st.warning("La ruta no existe en el servidor.")
        st.stop()

    # Buscar o crear subtipos
    def obtener_o_crear_subtipo(nombre, padre_id):
        conn = obtener_conexion()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id FROM tipos_documento WHERE nombre = %s AND padre_id <=> %s",
            (nombre, padre_id)
        )
        resultado = cursor.fetchone()
        if resultado:
            tipo_id = resultado['id']
        else:
            cursor.execute(
                "INSERT INTO tipos_documento (nombre, padre_id) VALUES (%s, %s)",
                (nombre, padre_id)
            )
            tipo_id = cursor.lastrowid
            conn.commit()
        conn.close()
        return tipo_id

    # Analizar estructura
    if st.button("🔍 Analizar estructura"):
        conn = obtener_conexion()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id FROM tipos_documento WHERE nombre = %s AND padre_id IS NULL",
            (tipo_doc_raiz["nombre"],)
        )
        tipo_raiz = cursor.fetchone()
        conn.close()
        if not tipo_raiz:
            st.error("No se encontró el tipo raíz.")
            st.stop()

        estructura = []
        for raiz, _, archivos in os.walk(ruta_base):
            rel = os.path.relpath(raiz, ruta_base)
            niveles = rel.split(os.sep)
            if niveles == ['.']:
                continue
            tipo_id_act = tipo_raiz['id']
            for nivel in niveles:
                tipo_id_act = obtener_o_crear_subtipo(nivel, tipo_id_act)
            for nombre_archivo in archivos:
                ruta = os.path.join(raiz, nombre_archivo)
                estructura.append({
                    "ruta": ruta,
                    "nombre": os.path.splitext(nombre_archivo)[0],
                    "extension": os.path.splitext(nombre_archivo)[1].lstrip('.'),
                    "tamanio": os.path.getsize(ruta),
                    "tipo_id": tipo_id_act
                })
        st.session_state["estructura_docs"] = estructura
        st.success(f"Se encontraron {len(estructura)} documentos.")
        st.rerun()

    # Vista previa e inserción
    if "estructura_docs" in st.session_state:
        st.subheader("📝 Vista previa de documentos")
        for doc in st.session_state["estructura_docs"]:
            st.markdown(f"- **{doc['nombre']}** ({doc['extension']}, {doc['tamanio']} bytes)")

        if st.button("✅ Insertar documentos"):
            conn = obtener_conexion()
            cursor = conn.cursor()
            # Límite de paquete MySQL
            cursor.execute("SHOW VARIABLES LIKE 'max_allowed_packet'")
            max_packet = int(cursor.fetchone()[1])
            chunk_size = max_packet - 1024

            # Filtrar pendientes y duplicados
            pendientes = []
            for doc in st.session_state["estructura_docs"]:
                try:
                    conn.ping(reconnect=True, attempts=3, delay=5)
                except:
                    conn = obtener_conexion(); cursor = conn.cursor()
                cursor.execute(
                    "SELECT COUNT(*) FROM documentos WHERE titulo = %s AND tipo_id = %s",
                    (doc['nombre'], doc['tipo_id'])
                )
                if cursor.fetchone()[0] == 0:
                    pendientes.append(doc)

            total = len(pendientes)
            mb_total = sum(d['tamanio'] for d in pendientes) / (1024*1024)
            st.info(f"A insertar: {total} archivos (~{mb_total:.2f} MB)")

            insertados = 0
            for doc in pendientes:
                # Reconectar si es necesario
                try:
                    conn.ping(reconnect=True, attempts=3, delay=5)
                except:
                    conn = obtener_conexion(); cursor = conn.cursor()

                nombre = doc['nombre']
                ext = doc['extension']
                tamaño = doc['tamanio']

                # Insertar documento
                cursor.execute(
                    "INSERT INTO documentos (titulo, descripcion, tipo_id, creado_por, fecha_creacion, estatus) "
                    "VALUES (%s, %s, %s, %s, NOW(), 'A')",
                    (nombre, nombre, doc['tipo_id'], 'admin')
                )
                doc_id = cursor.lastrowid

                # Insertar versión sin BLOB inicial
                archivo_full = f"{nombre}.{ext}"
                cursor.execute(
                    "INSERT INTO versiones_documento (documento_id, version, nombre_archivo, extension, tamaño, archivo, subido_por, fecha_subida, comentario) "
                    "VALUES (%s, 1, %s, %s, %s, %s, %s, NOW(), '')",
                    (doc_id, archivo_full, ext, tamaño, b'', 'admin')
                )
                ver_id = cursor.lastrowid

                # Subir BLOB en fragmentos
                with open(doc['ruta'], 'rb') as f:
                    while True:
                        trozo = f.read(chunk_size)
                        if not trozo:
                            break
                        cursor.execute(
                            "UPDATE versiones_documento SET archivo = CONCAT(archivo, %s) WHERE id = %s",
                            (trozo, ver_id)
                        )

                # Aplicar permisos
                for u in ['admin', 'Eduardo Peralta']:
                    cursor.execute(
                        "INSERT INTO permisos_documento (documento_id, username, puede_editar, puede_eliminar) "
                        "VALUES (%s, %s, 1, 1)",
                        (doc_id, u)
                    )
                
                conn.commit()
                insertados += 1

            conn.close()
            st.success(f"{insertados}/{total} archivos insertados correctamente.")
            del st.session_state["estructura_docs"]

if __name__ == '__main__':
    cargar_estructura()