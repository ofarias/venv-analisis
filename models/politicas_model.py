from database.conexion import obtener_conexion
from datetime import datetime
import streamlit as st 

##def crear_politica(nombre, cargada, fecha_carga, fecha_vencimiento, descripcion, vigencia_inicial, vigencia_final, requiere_firma, aviso_email, documento_binario):
##    conn = obtener_conexion()
##    cursor = conn.cursor()
##    cursor.execute("""
##        INSERT INTO Politicas 
##        (Nombre, Cargada, Fecha_Carga, Fecha_Vencimiento, Descripcion, Estatus, Vigencia_Inicial, Vigencia_Final, Requiere_Firma, Aviso_email, Documento)
##        VALUES (%s, %s, %s, %s, %s, 'Activa', %s, %s, %s, %s, %s)
##    """, (
##        nombre, cargada, fecha_carga, fecha_vencimiento, descripcion,
##        vigencia_inicial, vigencia_final, requiere_firma, aviso_email, documento_binario
##    ))
##    politica_id = cursor.lastrowid
##    conn.commit()
##    conn.close()
##    return politica_id

def crear_politica(nombre, cargada, fecha_carga, fecha_vencimiento, descripcion, vigencia_inicial, vigencia_final, requiere_firma, aviso_email, documento_binario, nombre_archivo, extension):
    try:
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO Politicas 
            (Nombre, Descripcion, Cargada, Fecha_Carga, Fecha_Vencimiento, Vigencia_Inicial, Vigencia_Final, Requiere_Firma, Aviso_email, Documento, Nombre_archivo, Extension)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            nombre, descripcion, cargada, fecha_carga, fecha_vencimiento,
            vigencia_inicial, vigencia_final, requiere_firma, aviso_email,
            documento_binario, nombre_archivo, extension
        ))
        conn.commit()
        return cursor.lastrowid  # Devuelve el ID de la nueva política
    except Exception as e:
        print("❌ Error al insertar política:", e)
        return None
    finally:
        conn.close()


def crear_detalles_firma(politica_id, usuarios):
    conn = obtener_conexion()
    cursor = conn.cursor()
    for user in usuarios:
        cursor.execute("""
            INSERT INTO PoliticasDetalle 
            (Politica_id, Usuario_id, Estatus, Visibilidad)
            VALUES (%s, %s, 'Pendiente', TRUE)
        """, (politica_id, user))
    conn.commit()
    conn.close()

def obtener_politicas():
    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT 
            Id, Nombre, Descripcion, Fecha_Carga, Fecha_Vencimiento, 
            Estatus, Requiere_Firma, Aviso_email
        FROM Politicas
        ORDER BY Fecha_Carga DESC
    """)
    politicas = cursor.fetchall()
    conn.close()
    return politicas

def obtener_resumen_firmas():
    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT 
            p.Id,
            p.Nombre,
            COUNT(pd.Id) AS total_usuarios,
            SUM(CASE WHEN pd.Estatus = 'Firmado' THEN 1 ELSE 0 END) AS firmados,
            SUM(CASE WHEN pd.Estatus != 'Firmado' THEN 1 ELSE 0 END) AS pendientes
        FROM Politicas p
        LEFT JOIN PoliticasDetalle pd ON p.Id = pd.Politica_id
        WHERE p.Requiere_Firma = 1
        GROUP BY p.Id, p.Nombre
        ORDER BY p.Fecha_Carga DESC
    """)
    resumen = cursor.fetchall()
    conn.close()
    return resumen


def obtener_detalle_firmas(politica_id):
    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT Usuario_id, Estatus, Fecha_firma, Documento_firma, evidencia_nombre, evidencia_extension
        FROM PoliticasDetalle
        WHERE Politica_id = %s
        ORDER BY Usuario_id
    """, (politica_id,))
    detalles = cursor.fetchall()
    conn.close()
    return detalles


def obtener_politicas_pendientes_usuario(username):
    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT p.*, pd.*
        FROM PoliticasDetalle pd
        JOIN Politicas p ON pd.Politica_id = p.Id
        WHERE pd.Usuario_id = %s AND pd.Estatus = 'Pendiente' AND p.Estatus = 'Activo'
    """, (username,))
    pendientes = cursor.fetchall()
    conn.close()
    return pendientes

def guardar_evidencia_politica(politica_id, username, archivo):
    datos = archivo.read()
    fecha = datetime.now()
    estatus = 'Firmado'
    evidencia_nomnbre = archivo.name
    evidencia_extension = evidencia_nomnbre.split(".")[-1].lower()

    conn = obtener_conexion()
    cursor = conn.cursor()
    st.write(f"Busca el detalle de la politica {politica_id} con el usuario {username}")
    # Verificamos si ya existe un registro
    cursor.execute("""
        SELECT COUNT(*) FROM PoliticasDetalle
        WHERE politica_id = %s AND usuario_id = %s
    """, (politica_id, username))
    existe = cursor.fetchone()[0]

    if existe:
        st.write("Entra a actualizar")
        # Ya existe, actualizamos solo el documento
        cursor.execute("""
            UPDATE PoliticasDetalle
            SET Documento_firma = %s,
                Estatus = %s,
                Fecha_firma = %s,
                evidencia_nombre = %s,
                evidencia_extension = %s                       
            WHERE politica_id = %s AND usuario_id = %s
        """, (datos, estatus, fecha, evidencia_nomnbre, evidencia_extension, politica_id, username))
    else:
        # No existe, insertamos nuevo registro
        cursor.execute("""
            INSERT INTO PoliticasDetalle (politica_id, usuario_id, Estatus, Fecha_firma, Documento_firma, evidencia_nombre, evidencia_extension)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (politica_id, username, estatus, fecha, datos, evidencia_nomnbre, evidencia_extension ))

    conn.commit()
    conn.close()

