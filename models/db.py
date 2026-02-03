import os, streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool
import firebird.driver as fb
import fdb 

def _build_url(conf: dict) -> str:
    required = ("host", "user", "password", "database")
    missing = [k for k in required if k not in conf or not conf[k]]
    if missing:
        raise ValueError(f"faltan claves en secrets para la conexión: {', '.join(missing)}")
    return f"mysql+pymysql://{conf['user']}:{conf['password']}@{conf['host']}/{conf['database']}"

def _make_engine_from_secret(secret_key: str):
    if secret_key not in st.secrets:
        raise KeyError(f"no existe la sección [{secret_key}] en .streamlit/secrets.toml")
    url = _build_url(st.secrets[secret_key])
    return create_engine(
        url,
        poolclass=QueuePool, pool_size=10, max_overflow=20,
        pool_pre_ping=True, future=True
    )

# ---------- FIREBIRD ----------
def _make_firebird_conn(secret_key: str):
    conf = st.secrets[secret_key]
    return fdb.connect(
        host=conf.get("host", "localhost"),
        port=int(conf.get("port", 3050)),
        database=conf["database"],          # ruta vista desde el servidor firebird
        user=conf.get("user", "SYSDBA"),
        password=conf.get("password", "masterkey"),
        charset=conf.get("charset", "ISO8859_1"),
    )


# registra aquí tus conexiones por alias
_engines = {
    "BIO": _make_engine_from_secret("MYSQL_BIO"), ### Prorrateos
    "CTRLDOCE": _make_engine_from_secret("MYSQL_CTRLDOCE"), ### CFDIs de los proveedores app CTRDOCE
    "MYSQL_TEST": _make_engine_from_secret("MYSQL_TEST") ### Informacion para calcular los prorrateos.(al parecer ya no es necesaria)
    # agrega más si los necesitas…
}

def run_query(db_key: str, sql: str, params: dict | None = None):
    if db_key not in _engines:
        raise ValueError(f"db '{db_key}' no configurada en _engines")
    with _engines[db_key].begin() as conn:
        return conn.execute(text(sql), params or {})
    
##  def run_query_firebird(secret_key: str, sql: str, params: tuple | None = None):
##      con = _make_firebird_conn(secret_key)
##      try:
##          cur = con.cursor()
##          cur.execute(sql, params or ())
##          if sql.strip().lower().startswith("select"):
##              cols = [c[0] for c in cur.description]
##              return [dict(zip(cols, r)) for r in cur.fetchall()]
##          con.commit()
##          return cur.rowcount
##      finally:
##          con.close()
##  
def run_query_firebird(secret_key: str, sql: str, params: tuple | None = None):
    con = _make_firebird_conn(secret_key)
    try:
        cur = con.cursor()
        cur.execute(sql, params or ())

        # si hay resultset, cur.description viene con metadata
        if cur.description is not None:
            cols = [c[0] for c in cur.description]
            rows = cur.fetchall()
            return [dict(zip(cols, r)) for r in rows]

        # si no hay resultset, es DML/DDL
        con.commit()
        return cur.rowcount
    finally:
        con.close()