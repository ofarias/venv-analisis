import streamlit as st
from models.documento_model import obtener_todos_los_documentos, eliminar_documento, actualizar_documento

def mostrar_documentos_admin():
    st.title("📄 Administración de Documentos")

    roles = st.session_state.get("usuario", {}).get("roles", [])
    
    if "Admin" not in roles:
        st.info("Esta vista solo está disponible para administradores")
        st.error(f"Acceso denegado. Esta sección es solo para administradores. Tus roles actuales: {roles}")
        return

    documentos = obtener_todos_los_documentos()  # Esta función debe traer todos los documentos

    for doc in documentos:
        with st.expander(f"{doc['titulo']}"):
            st.write(f"Tipo: {doc['tipo_nombre']}")
            st.write(f"Fecha: {doc['fecha_creacion']}")
            st.write(f"Usuario: {doc['creado_por']}")

            editar = st.checkbox(f"Editar documento #{doc['id']}", key=f"edit_{doc['id']}")
            if editar:
                nuevo_nombre = st.text_input("Nuevo nombre", value=doc['nombre'], key=f"new_{doc['id']}")
                if st.button("Guardar cambios", key=f"save_{doc['id']}"):
                    editar_documento(doc['id'], nuevo_nombre)
                    st.success("Documento actualizado")

            if st.button("🗑️ Eliminar", key=f"delete_{doc['id']}"):
                eliminar_documento(doc['id'])
                st.warning("Documento eliminado")
                st.rerun()