import streamlit as st
from database.conexion import obtener_conexion


def obtener_roles():
    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM roles ORDER BY id")
    roles = cursor.fetchall()
    conn.close()
    return roles


def crear_rol(nombre):
    try:
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO roles (nombre) VALUES (%s)", (nombre,))
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Error al crear rol: {e}")
        return False
    finally:
        conn.close()


def actualizar_rol(id, nuevo_nombre):
    try:
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute("UPDATE roles SET nombre = %s WHERE id = %s", (nuevo_nombre, id))
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Error al actualizar rol: {e}")
        return False
    finally:
        conn.close()


def eliminar_rol(id):
    try:
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM roles WHERE id = %s", (id,))
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Error al eliminar rol: {e}")
        return False
    finally:
        conn.close()


def mostrar_admin_roles():
    st.subheader("🎭 Administración de roles")

    with st.form("form_nuevo_rol"):
        nuevo_rol = st.text_input("Nombre del nuevo rol")
        submitted = st.form_submit_button("Crear rol")

    if submitted and nuevo_rol:
        if crear_rol(nuevo_rol):
            st.success(f"✅ Rol '{nuevo_rol}' creado correctamente.")
            st.rerun()

    st.divider()
    st.markdown("### 📋 Lista de roles")

    roles = obtener_roles()
    for rol in roles:
        col1, col2, col3 = st.columns([3, 2, 1])
        with col1:
            nuevo_nombre = st.text_input(f"Nombre del rol {rol['id']}", value=rol["nombre"], key=f"nombre_{rol['id']}")
        with col2:
            if st.button("Guardar", key=f"guardar_{rol['id']}"):
                if actualizar_rol(rol["id"], nuevo_nombre):
                    st.success("✅ Rol actualizado")
                    st.rerun()
        with col3:
            if st.button("🗑️ Eliminar", key=f"eliminar_{rol['id']}"):
                if eliminar_rol(rol["id"]):
                    st.success("✅ Rol eliminado")
                    st.rerun()