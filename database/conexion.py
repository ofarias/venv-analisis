#database/conexion.py

import mysql.connector
import streamlit as st

def obtener_conexion():
    cfg = st.secrets["MYSQL_DOCUMENTOS"]
    return mysql.connector.connect(
        host=cfg["host"],
        user=cfg["user"],
        password=cfg["password"],
        database=cfg["database"]
    )