#unidades_model.py
from database.conexion import obtener_conexion
import pandas as pd
import streamlit as st 

def obtener_unidades(limit: int = 500, offset: int = 0):
    """
    Recupera unidades de negocio con paginación.
    """
    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"""
        SELECT id, nombre, id_ant, fecha_creacion, estatus, creador, fecha_cancela
        FROM Unidades_Negocio
        ORDER BY id DESC
        LIMIT %s OFFSET %s
    """, (int(limit), int(offset)))
    data = cursor.fetchall()
    cursor.close()
    conn.close()
    return pd.DataFrame(data)


def insertar_unidad(nombre: str, id_ant: int | None, creador: str) -> bool:
    """
    Inserta una nueva unidad de negocio.
    """
    try:
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO Unidades_Negocio (nombre, id_ant, creador, fecha_creacion, estatus)
            VALUES (%s, %s, %s, NOW(), 1)
        """, (nombre, id_ant, creador))
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Error en insertar_unidad: {e}")
        return False


def actualizar_estatus_unidad(id_unidad: int, estatus: int) -> bool:
    """
    Actualiza el estatus de una unidad de negocio (1=activo, 0=inactivo).
    """
    try:
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE Unidades_Negocio
            SET estatus = %s,
                fecha_cancela = CASE WHEN %s = 0 THEN NOW() ELSE NULL END
            WHERE id = %s
        """, (estatus, estatus, id_unidad))
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Error en actualizar_estatus_unidad: {e}")
        return False
    
def obtener_asignaciones(limit: int = 500, offset: int = 0):
    """
    Devuelve la lista de asignaciones entre usuarios y unidades activas/inactivas,
    incluyendo los nombres de usuario que dieron de alta y de baja.
    """
    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"""
        SELECT 
            uu.id,
            uu.user_id,
            u.username AS usuario,
            uu.id_unidad,
            un.nombre AS unidad,
            uu.status,
            uu.fecha_alta,
            uu.user_id_alta,
            ua.username AS creado_por,
            uu.user_id_baja,
            ub.username AS baja_por,
            uu.fecha_baja
        FROM Usuarios_Unidades uu
        JOIN usuarios u ON u.id = uu.user_id
        JOIN Unidades_Negocio un ON un.id = uu.id_unidad
        LEFT JOIN usuarios ua ON ua.id = uu.user_id_alta
        LEFT JOIN usuarios ub ON ub.id = uu.user_id_baja
        ORDER BY uu.id DESC
        LIMIT %s OFFSET %s
    """, (int(limit), int(offset)))
    data = cursor.fetchall()
    cursor.close()
    conn.close()
    return pd.DataFrame(data)


def asignar_unidad_a_usuario(user_id: int, id_unidad: int, user_id_alta: int) -> bool:
    """
    Crea una nueva asignación usuario → unidad.
    """
    try:
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO Usuarios_Unidades (user_id, id_unidad, status, fecha_alta, user_id_alta)
            VALUES (%s, %s, 1, NOW(), %s)
        """, (user_id, id_unidad, user_id_alta))
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Error en asignar_unidad_a_usuario: {e}")
        return False


def actualizar_estatus_asignacion(id_asignacion: int, status: int, user_id_baja: int | None = None) -> bool:
    """
    Cambia el estatus de una asignación (1 = activa, 0 = inactiva).
    Si se desactiva, guarda user_id_baja y fecha_baja.
    """
    try:
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE Usuarios_Unidades
            SET status = %s,
                user_id_baja = CASE WHEN %s = 0 THEN %s ELSE NULL END,
                fecha_baja = CASE WHEN %s = 0 THEN NOW() ELSE NULL END
            WHERE id = %s
        """, (status, status, user_id_baja, status, id_asignacion))
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Error en actualizar_estatus_asignacion: {e}")
        return False
    

def get_id_creador(creador):
    try:
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute("""
                        SELECT id FROM usuarios WHERE username = %s
                       """), (creador)
        data = cursor.fetchall()
        cursor.close()
        conn.close()
        return data
    except Exception as e:
        st.write(f"No se encontro el creador: {e}")
        return False

def insertar_asignacion_multiple(usernames, unidades, creador):
    creador = get_id_creador(creador)
    try:
        conn = obtener_conexion()
        cursor = conn.cursor()
        for user in usernames:
            for unidad in unidades:
                cursor.execute("""
                    INSERT INTO Usuarios_Unidades (user_id, id_unidad, status, fecha_alta, user_id_alta)
                    SELECT u.id, un.id, 1, NOW(), %s
                    FROM usuarios u, Unidades_Negocio un
                    WHERE u.username = %s AND un.nombre = %s
                    ON DUPLICATE KEY UPDATE status = 1, fecha_alta = NOW(), user_id_alta = VALUES(user_id_alta)
                """, (creador, user, unidad))
           
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        st.write(f"❌ Error en insertar_asignacion_multiple: {e}")
        st.stop()
        return False


def obtener_todas_asignaciones():
    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT uu.id, u.username AS usuario, un.nombre AS unidad, uu.status, uu.fecha_alta
        FROM Usuarios_Unidades uu
        JOIN usuarios u ON u.id = uu.user_id
        JOIN Unidades_Negocio un ON un.id = uu.id_unidad
        ORDER BY u.username DESC
    """)
    data = cursor.fetchall()
    cursor.close()
    conn.close()
    return data

def eliminar_asignaciones_db(ids_asignaciones, usuario_baja):
    usuario_baja = get_id_creador(usuario_baja)
    st.write(usuario_baja)
    if not ids_asignaciones:
        return False
    try:
        conn = obtener_conexion()
        cursor = conn.cursor()
        qmarks = ",".join(["%s"] * len(ids_asignaciones))
        cursor.execute(f"""
            UPDATE Usuarios_Unidades
            SET status = 0,
                fecha_baja = NOW(),
                user_id_baja = %s
            WHERE id IN ({qmarks})
        """, (usuario_baja, *ids_asignaciones))
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        st.write(f"❌ Error en eliminar_asignaciones_db (baja lógica): {e}")
        st.stop()
        return False