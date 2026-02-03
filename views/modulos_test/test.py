import streamlit as st
import os 
from streamlit_image_select import image_select
from database.conexion import obtener_conexion

def obtener_tipos_documento():
    """
    Función para obtener tipos de documento de la base de datos.
    Filtra los registros que no tienen una imagen asociada.
    """
    try:
        conn = obtener_conexion()
        cursor = conn.cursor(dictionary=True)
        # Filtra los registros para evitar errores con valores None en 'imagen'
        cursor.execute("SELECT * FROM tipos_documento WHERE imagen IS NOT NULL ORDER BY padre_id IS NULL DESC, padre_id, nombre")
        tipos = cursor.fetchall()
        conn.close()
        return tipos
    except Exception as e:
        st.error(f"Error al conectar con la base de datos: {e}")
        return []

def codigo_test():
    """
    Función principal que renderiza la selección de imágenes.
    """
    # Obtiene los tipos de documento desde la base de datos
    tipos_documento = obtener_tipos_documento()
    
    # Verifica si hay documentos para mostrar
    if not tipos_documento:
        st.info("No se encontraron tipos de documento con una imagen asociada en la base de datos.")
        return

    # Construye las rutas completas de las imágenes
    # Usa la ruta absoluta de la carpeta de imágenes
    image_dir = "/home/ofarias/static/tipos/"
    paths_imagenes = [os.path.join(image_dir, tipo['imagen']) for tipo in tipos_documento]
    
    # Crea una lista de los nombres de los documentos para usar como leyendas
    nombres_documentos = [tipo['nombre'] for tipo in tipos_documento]

    # Muestra las imágenes como un grupo de botones seleccionables
    # 'return_value' se establece en 'index' para obtener la posición de la imagen seleccionada
    selected_index = image_select(
        label="Selecciona una opción:",
        images=paths_imagenes,
        captions=nombres_documentos,
        use_container_width=True,
        return_value='index'
    )
    
    # Maneja la selección del usuario
    if selected_index is not None:
        # Se obtiene el índice como string, por lo que se convierte a int
        selected_index_int = int(selected_index)
        selected_tipo = tipos_documento[selected_index_int]
        
        st.success(f"Has seleccionado el documento: **{selected_tipo['nombre']}**")
        st.info(f"ID del documento: {selected_tipo['id']}")
        st.info(f"Ruta de la imagen seleccionada: {paths_imagenes[selected_index_int]}")

if __name__ == "__main__":
    st.set_page_config(layout="wide")
    st.title("Aplicación de Prueba de Selección de Documentos")
    codigo_test()
