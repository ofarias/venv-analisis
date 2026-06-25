#database/conexion.py

import mysql.connector
import streamlit as st


def obtener_conexion():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="genseg01",
        database="documentos"
    )

def obtener_conexion_biotecsa_formulas():
    cfg = st.secrets["MYSQL_FORMULAS"]

    return mysql.connector.connect(
        host=cfg["host"],
        port=int(cfg.get("port", 3306)),
        user=cfg["user"],
        password=cfg["password"],
        database=cfg["database"],
        charset="utf8mb4",
        autocommit=True,
    )