from models.db import run_query, run_query_firebird
import datetime

ejercicio = datetime.date.today().year
ejercicio = ejercicio % 100
mes = datetime.date.today().month


def obtener_ksae10t(limit: int = 500, offset: int = 0):
    sql = """
        SELECT *
        FROM ksae10t
        ORDER BY id DESC
        LIMIT :limit OFFSET :offset
    """
    rows = run_query("BIO", sql, {"limit": limit, "offset": offset}).mappings().all()
    return [dict(r) for r in rows]

def obtener_ksae20t(limit: int = 1000, offset: int = 0):
    sql = """
        SELECT *
        FROM ksae20t
        ORDER BY idnumpon
        LIMIT :limit OFFSET :offset
    """
    rows = run_query("BIO", sql, {"limit": limit, "offset": offset}).mappings().all()
    return [dict(r) for r in rows]

def obtener_prov01():
    rows = run_query_firebird("FIREBIRD_BIO_SAE", "SELECT * FROM PROV01")
    return rows 

def polizas_coi(tipo= 'Dr', eje= ejercicio, periodo = mes,):
    tabla = f"POLIZAS{eje}"
    sql=f"""
        SELECT * FROM {tabla}
     """
    rows = run_query_firebird("FIREBIRD_BIO_COI",sql)
    return rows