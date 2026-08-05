#database/conexion.py

import mysql.connector
from mysql.connector import pooling
import streamlit as st

_pool = None


def _get_pool():
    global _pool
    if _pool is None:
        _pool = pooling.MySQLConnectionPool(
            pool_name="documentos_pool",
            pool_size=10,
            host="localhost",
            user="root",
            password="genseg01",
            database="documentos",
        )
    return _pool


def obtener_conexion():
    conn = _get_pool().get_connection()
    try:
        # las conexiones del pool pueden quedar inactivas mucho tiempo entre
        # usos (wait_timeout de mysql) y morir del lado del servidor; ping
        # con reconnect evita el error "mysql server has gone away" al
        # reusar una conexión reciclada
        conn.ping(reconnect=True, attempts=2, delay=0.2)
    except mysql.connector.Error:
        pass
    return conn

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