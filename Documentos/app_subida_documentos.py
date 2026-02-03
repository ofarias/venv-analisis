
import streamlit as st
import mysql.connector
import os
from datetime import datetime

# === CONFIGURACIÓN ===
UPLOAD_FOLDER = "/home/ofarias/archivos_subidos"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# === CONEXIÓN A MYSQL ===
def conectar_mysql():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="genseg01",  # Cámbiala si ya la actualizaste
        database="documentos"
    )

# === TÍTULO ===
st.title("📁 Subida de Documentos - Perfil Desarrollo")

# === AUTENTICACIÓN SIMPLIFICADA ===
usuario = st.text_input("Nombre de usuario", max_chars=100)
if not usuario:
    st.warning("Por favor ingresa tu nombre de usuario.")
    st.stop()

# === CARGA DE ARCHIVO ===
archivo = st.file_uploader("Selecciona un archivo", type=["pdf", "docx", "xlsx", "png", "jpg", "csv", "txt"])

if archivo:
    ruta_archivo = os.path.join(UPLOAD_FOLDER, archivo.name)

    with open(ruta_archivo, "wb") as f:
        f.write(archivo.read())

    conn = conectar_mysql()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO archivos (nombre_archivo, tipo_archivo, tamaño, usuario) VALUES (%s, %s, %s, %s)",
        (archivo.name, archivo.type, archivo.size, usuario)
    )

    conn.commit()
    cursor.close()
    conn.close()

    st.success(f"✅ Archivo '{archivo.name}' subido y registrado exitosamente.")
