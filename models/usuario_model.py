import bcrypt
from database.conexion import obtener_conexion
import streamlit as st
from settings import DB_CONFIG


def obtener_usuarios():
    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, username, nombre, email, password_hash, rol, estatus, creado_en FROM usuarios")
    usuarios = cursor.fetchall()
    conn.close()
    return usuarios

def verificar_usuario(username, password):
    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM usuarios WHERE username = %s", (username,))
    user = cursor.fetchone()
    conn.close()
    if user and bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        user["roles"] = obtener_roles_usuario(username)
        if not user["roles"]:
            return None  # opcional: bloquear si no tiene roles
        return user
    return None

def crear_usuario(username, nombre, email, password, roles):
    try:
        conn = obtener_conexion()
        cursor = conn.cursor()

        # Verificar si ya existe
        cursor.execute("SELECT 1 FROM usuarios WHERE username = %s", (username,))
        if cursor.fetchone():
            return False, "El usuario ya existe."

        # Insertar usuario
        hash_pwd = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        cursor.execute("""
            INSERT INTO usuarios (username, nombre, email, password_hash, estatus)
            VALUES (%s, %s, %s, %s, 'Activo')
        """, (username, nombre, email, hash_pwd))

        # Insertar roles
        for rol in roles:
            cursor.execute("SELECT id FROM roles WHERE nombre = %s", (rol,))
            id_rol = cursor.fetchone()
            if id_rol:
                cursor.execute("INSERT INTO usuarios_roles (username, id_rol) VALUES (%s, %s)", (username, id_rol[0]))

        conn.commit()
        return True, "Usuario creado correctamente."
    except Exception as e:
        return False, f"Error: {e}"
    finally:
        conn.close()

def actualizar_usuario(username, nombre, email, rol, nueva_password=None, estatus="Activo"):
    try:
        conn = obtener_conexion()
        cursor = conn.cursor()
       
        if nueva_password:
            hashed = bcrypt.hashpw(nueva_password.encode(), bcrypt.gensalt()).decode()
            cursor.execute("""
                UPDATE usuarios
                SET nombre = %s, email = %s, password_hash = %s, estatus=%s 
                WHERE username = %s
            """, (nombre, email, hashed, estatus, username))
        else:
           cursor.execute("""
                UPDATE usuarios
                SET nombre = %s, email = %s, estatus=%s
                WHERE username = %s
            """, (nombre, email, estatus, username))

        conn.commit()
        cursor.close()
        conn.close()
        
        return True
    except Exception as e:
        st.error(f"❌ Error al actualizar usuario: {e}")
        return False
    
def obtener_usuario_por_username(username):
    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT username, estatus, email FROM usuarios WHERE username = %s", (username,))
    user = cursor.fetchone()
    conn.close()
    return user

def obtener_roles_ids(nombres_roles):
    conn = obtener_conexion()
    cursor = conn.cursor()
    format_strings = ','.join(['%s'] * len(nombres_roles))
    cursor.execute(f"SELECT id FROM roles WHERE nombre IN ({format_strings})", tuple(nombres_roles))
    ids = cursor.fetchall()
    conn.close()
    return ids

def actualizar_roles_usuario(username, nuevos_roles):
    conn = obtener_conexion()
    cursor = conn.cursor()

    # Eliminar roles existentes
    cursor.execute("DELETE FROM usuarios_roles WHERE username = %s", (username,))

    # Insertar nuevos roles
    for rol in nuevos_roles:
        cursor.execute("SELECT id FROM roles WHERE nombre = %s", (rol,))
        id_rol = cursor.fetchone()
        if id_rol:
            cursor.execute("INSERT INTO usuarios_roles (username, id_rol) VALUES (%s, %s)", (username, id_rol[0]))

    conn.commit()
    cursor.close()
    conn.close()


def obtener_roles_usuario(username):
    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT r.nombre
        FROM usuarios_roles ur
        JOIN roles r ON ur.id_rol = r.id
        WHERE ur.username = %s
    """, (username,))
    roles = [r["nombre"] for r in cursor.fetchall()]
    conn.close()
    return roles

def obtener_roles_disponibles():
    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT nombre FROM roles ORDER BY nombre")
    roles = [r["nombre"] for r in cursor.fetchall()]
    conn.close()
    return roles

def obtener_usuario_y_roles(email):
    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)

    # 1. Buscar al usuario por correo
    cursor.execute("""
        SELECT u.id, u.username, u.nombre
        FROM usuarios u
        WHERE u.email = %s AND u.estatus = 'Activo'
        LIMIT 1
    """, (email,))
    usuario = cursor.fetchone()

    if not usuario:
        conn.close()
        return None  # Usuario no autorizado

    # 2. Obtener los roles del usuario
    cursor.execute("""
        SELECT r.nombre
        FROM usuarios_roles ur
        JOIN roles r ON ur.id_rol = r.id
        WHERE ur.username = %s
    """, (usuario["username"],))
    roles = [r["nombre"] for r in cursor.fetchall()]
    st.write(usuario["username"])
    st.stop
    conn.close()

    # 3. Devolver los datos
    return {
        "id":usuario["id"],
        "username": usuario["username"],
        "nombre": usuario["nombre"],
        "roles": roles
    }


def obtener_emails_usuarios(usernames):
    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)
    formato = ",".join(["%s"] * len(usernames))
    cursor.execute(f"SELECT email FROM usuarios WHERE username IN ({formato})", tuple(usernames))
    resultados = cursor.fetchall()
    conn.close()
    return [r['email'] for r in resultados]

def obtener_todos_usuarios():
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("SELECT username FROM usuarios ORDER BY username")
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows]
