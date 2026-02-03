#presupuestos_model.py 
from database.conexion import obtener_conexion
import pandas as pd
from models.db import run_query_firebird
import streamlit as st 
import numpy as np
import fdb
#from utils.secrets import load_secrets  # o el módulo donde cargas el secrets.toml


# --- Consultas auxiliares ---

def obtener_unidades_activas():
    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, nombre FROM Unidades_Negocio WHERE estatus = 1 ORDER BY nombre;")
    data = cursor.fetchall()
    cursor.close()
    conn.close()
    return pd.DataFrame(data)

def obtener_usuarios_presupuestos():
    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT u.username, u.nombre as nombre_completo FROM usuarios u left join usuarios_roles ur on ur.username = u.username left join roles r on r.id = ur.id_rol WHERE u.estatus = 'Activo' and r.nombre = 'Usuarios_Presupuestos' ORDER BY u.nombre;")
    data = cursor.fetchall()
    cursor.close()
    conn.close()
    return pd.DataFrame(data)

def obtener_Control_Presupuestosl():
    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT u.username, u.nombre as nombre_completo FROM usuarios u left join usuarios_roles ur on ur.username = u.username left join roles r on r.id = ur.id_rol WHERE u.estatus = 'Activo' and r.nombre = 'Control_Presupuestos' ORDER BY u.nombre;")
    data = cursor.fetchall()
    cursor.close()
    conn.close()
    return pd.DataFrame(data)
# --- Inserción principal ---

def insertar_presupuesto(datos: dict):
    """
    datos = {
        'unidades': [1,2],
        'usuarios': ['maria','juan'],
        'autorizadores': ['gerente1','dir2'],
        'nombre': 'Presupuesto MZ-2025',
        'periodo': 'Mensual',
        'fecha_ini': date,
        'fecha_fin': date,
        'monto_mnx': 200000,
        'monto_usd': 0,
        'creador': 'oscar',
    }
    """
    try:
        conn = obtener_conexion()
        cur = conn.cursor()

        # Insertar cabecera
        cur.execute("""
            INSERT INTO Presupuesto (
                Nombre, Periodo, Fecha_Inicial, Fecha_Final,
                Monto_Asignado_MNX, Monto_Asignado_USD, Usuarios, Creador,
                Autorizador, Estatus, Unidad_Negocio
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'Nuevo', 1)
        """, (
            datos['nombre'],
            datos['periodo'],
            datos['fecha_ini'],
            datos['fecha_fin'],
            datos['monto_mnx'],
            datos['monto_usd'],
            ",".join(datos['usuarios']),
            datos['creador'],
            ",".join(datos['autorizadores'])
        ))

        id_pres = cur.lastrowid

        # Crear detalle por unidad y usuario
        for unidad in datos['unidades']:
            for usuario in datos['usuarios']:
                cur.execute("""
                    INSERT INTO Presupuesto_Detalle (
                        ID_Presupuesto, Unidad_Negocio, Monto_Gasto_MNX, Monto_Gasto_USD,
                        Usuario, Autorizador, Estatus
                    )
                    VALUES (%s, %s, 0, 0, %s, %s, 'Pendiente')
                """, (id_pres, unidad, usuario, ",".join(datos['autorizadores'])))

        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"[insertar_presupuesto] Error: {e}")
        return False

def obtener_presupuestos():
    conn = obtener_conexion()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT Id, Nombre, Periodo, Fecha_Inicial, Fecha_Final, Monto_Asignado_MNX,
               Monto_Asignado_USD, Estatus, Creador, Autorizador, Usuarios, Unidad_Negocio
        FROM Presupuesto
        ORDER BY Id DESC
    """)
    data = cur.fetchall()
    cur.close()
    conn.close()
    return pd.DataFrame(data)

def obtener_detalle_presupuesto(id_presupuesto: int):
    try:
        conn = obtener_conexion()
        cur = conn.cursor(dictionary=True)
        sql = """
            SELECT 
                d.ID,
                d.ID_Presupuesto,
                u.nombre AS Unidad_Negocio,
                d.Monto_Gasto_MNX,
                d.Monto_Gasto_USD,
                d.Usuario,
                d.Autorizador,
                d.Estatus
            FROM Presupuesto_Detalle d
            LEFT JOIN Unidades_Negocio u ON d.Unidad_Negocio = u.id
            WHERE d.ID_Presupuesto = %s
            ORDER BY u.nombre, d.Usuario;
        """
        cur.execute(sql, (id_presupuesto,))
        data = cur.fetchall()
        cur.close()
        conn.close()
        return pd.DataFrame(data)
    except Exception as e:
        st.write(f"[obtener_detalle_presupuesto] Error: {e}")
        return pd.DataFrame()
    

##def buscar_gasto(uuid=None, folio=None, monto=None):
##    where = []
##    params = []
##
##    if uuid:
##        where.append("UPPER(pg.APP_UUID) = ?")
##        params.append(uuid.upper())
##    if folio:
##        where.append("pg.DOCTO = ?")
##        params.append(folio)
##    if monto and monto > 0:
##        where.append("pg.TOTAL = ?")
##        params.append(monto)
##
##    sql = f"""
##        SELECT 
##            pg.APP_UUID, pg.DOCTO, pg.IMPORTE, pg.FECHA_APLI, pg.CVE_PROV, pg.TCAMBIO,
##            p.NOMBRE, c.DESCR AS CONCEPTO, m.DESCR AS MONEDA, pg.APP_ADA_CFD_DOC, pg.APP_STATUS
##        FROM PAGA_M01 pg
##        LEFT JOIN PROV01 p ON p.CLAVE = pg.CVE_PROV
##        LEFT JOIN CONP01 c ON c.NUM_CPTO = pg.NUM_CPTO
##        LEFT JOIN MONED01 m ON m.NUM_MONED = pg.NUM_MONED
##        {"WHERE " + " AND ".join(where) if where else ""}
##        ROWS 50
##    """
##    try:
##        df = run_query_firebird("FIREBIRD_BIO_SAE", sql, tuple(params))
##        return pd.DataFrame(df)
##    except Exception as e:
##        print(f"[buscar_gasto] Error: {e}")
##        return pd.DataFrame()


def buscar_gasto(uuid=None, folio=None, monto=None):
    where = []
    params = []

    if uuid:
        where.append("UPPER(d.UUID) = ?")
        params.append(uuid.upper())

    if folio:
        where.append("d.FOLIO = ?")
        params.append(folio)

    if monto is not None and float(monto) > 0:
        where.append("d.TOTAL = ?")
        params.append(float(monto))
        
    sql = f"""
        SELECT
            d.ID_DOCTODIG,
            d.UUID,
            d.FOLIO,
            d.SERIE,
            d.FECHA_EMISION,
            d.RFC_EMISOR,
            d.NOMBRE_EMISOR,
            d.RFC_RECEPTOR,
            d.NOMBRE_RECEPTOR,
            d.SUBTOTAL,
            d.IVA,
            d.TOTAL,
            d.MONEDA,
            d.TIPOCAMBIO,
            d.ESTADO_CFD,
            d.ESTADO_SAT,
            d.METODOPAGO,
            d.FORMAPAGO,
            d.TIPOCOMPROBANTE,
            d.USOCFDI,
            d.USUARIO,
            d.CONTABILIZADO,
            d.ORIGEN,
            d.FECHA_TIMBRADO,
            d.FECHA_CANCELACION
        FROM DATOSCFD d
        {"WHERE " + " AND ".join(where) if where else ""}
        ROWS 50
    """
    try:
        df = run_query_firebird("FIREBIRD_BIO_ADA", sql, tuple(params))
        return pd.DataFrame(df)
    except Exception as e:
        print(f"[buscar_gasto] Error: {e}")
        return pd.DataFrame()

def obtener_conceptos_sae():
    try:
        sql = "SELECT NUM_CPTO, DESCR FROM CONP01 WHERE STATUS = 'A' ORDER BY NUM_CPTO"
        df = run_query_firebird("FIREBIRD_BIO_SAE_4545", sql, ())
        return pd.DataFrame(df)
    except Exception as e:
        print(f"[obtener_conceptos_sae] Error: {e}")
        return pd.DataFrame()

def obtener_unidades_presupuestos_por_usuario(username: str):
    """
    Devuelve los presupuestos en los que el usuario participa (por Presupuesto_Detalle).
    """
    try:
        conn = obtener_conexion()
        cur = conn.cursor(dictionary=True)
        sql = """
            SELECT DISTINCT p.Id, p.Nombre, p.Periodo, p.Fecha_Inicial, p.Fecha_Final,
                            p.Monto_Asignado_MNX, p.Monto_Asignado_USD, p.Estatus, un.nombre as Unidad_Negocio,
                            d.id as id_detalle 
            FROM Presupuesto p
            INNER JOIN Presupuesto_Detalle d ON p.Id = d.ID_Presupuesto
            INNER JOIN Unidades_Negocio un on un.id = d.Unidad_Negocio
            WHERE d.Usuario = %s
            ORDER BY p.Fecha_Inicial DESC
        """
        cur.execute(sql, (username,))
        data = cur.fetchall()
        cur.close()
        conn.close()
        return pd.DataFrame(data)
    except Exception as e:
        print(f"[obtener_presupuestos_por_usuario] Error: {e}")
        return pd.DataFrame()


def obtener_presupuestos_por_usuario(username: str):
    """
    Devuelve los presupuestos en los que el usuario participa (por Presupuesto_Detalle).
    """
    try:
        conn = obtener_conexion()
        cur = conn.cursor(dictionary=True)
        sql = """
            SELECT DISTINCT p.Nombre 
            FROM Presupuesto p
            LEFT JOIN Presupuesto_Detalle d on d.id_presupuesto = p.id
            WHERE d.Usuario = %s
            GROUP BY p.Nombre
            ORDER BY p.Nombre DESC
        """
        cur.execute(sql, (username,))
        data = cur.fetchall()
        cur.close()
        conn.close()
        return pd.DataFrame(data)
    except Exception as e:
        print(f"[obtener_presupuestos_por_usuario] Error: {e}")
        return pd.DataFrame()

def obtener_unidades_por_usuario(username: str):
    """
    Devuelve las unidades de negocio asociadas al usuario en Presupuesto_Detalle.
    """
    try:
        conn = obtener_conexion()
        cur = conn.cursor(dictionary=True)
        sql = """
            SELECT DISTINCT u.id, u.nombre
            FROM Unidades_Negocio u
            INNER JOIN Presupuesto_Detalle d ON d.Unidad_Negocio = u.id
            WHERE d.Usuario = %s
            ORDER BY u.nombre
        """
        cur.execute(sql, (username,))
        data = cur.fetchall()
        cur.close()
        conn.close()
        return pd.DataFrame(data)
    except Exception as e:
        print(f"[obtener_unidades_por_usuario] Error: {e}")
        return pd.DataFrame()
    
def obtener_unidades_por_presupuesto_y_usuario(nombre_presupuesto: str, username: str):
    """
    Devuelve las unidades de negocio asociadas al usuario dentro del presupuesto seleccionado.
    """
    try:
        conn = obtener_conexion()
        cur = conn.cursor(dictionary=True)
        sql = """
            SELECT DISTINCT un.id, un.nombre
            FROM Presupuesto_Detalle d
            INNER JOIN Presupuesto p ON p.Id = d.ID_Presupuesto
            INNER JOIN Unidades_Negocio un ON un.id = d.Unidad_Negocio
            WHERE d.Usuario = %s AND p.Nombre = %s
            ORDER BY un.nombre;
        """
        cur.execute(sql, (username, nombre_presupuesto))
        data = cur.fetchall()
        cur.close()
        conn.close()
        return pd.DataFrame(data)
    except Exception as e:
        print(f"[obtener_unidades_por_presupuesto_y_usuario] Error: {e}")
        return pd.DataFrame()
    
def obtener_id_detalle_presupuesto(nombre_presupuesto: str, unidad_nombre: str, username: str):
    """
    Devuelve el ID del registro en Presupuesto_Detalle que corresponde
    al presupuesto, unidad y usuario indicados.
    """
    try:
        conn = obtener_conexion()
        cur = conn.cursor(dictionary=True)
        sql = """
            SELECT d.ID
            FROM Presupuesto_Detalle d
            INNER JOIN Presupuesto p ON p.Id = d.ID_Presupuesto
            INNER JOIN Unidades_Negocio u ON u.id = d.Unidad_Negocio
            WHERE p.Nombre = %s AND u.nombre = %s AND d.Usuario = %s
            LIMIT 1;
        """
        cur.execute(sql, (nombre_presupuesto, unidad_nombre, username))
        data = cur.fetchone()
        cur.close()
        conn.close()

        if data and "ID" in data:
            return data["ID"]
        else:
            return None
    except Exception as e:
        print(f"[obtener_id_detalle_presupuesto] Error: {e}")
        return None
    
def insertar_comprobante_presupuesto(data: dict):
    conn = None
    try:
        conn = obtener_conexion()
        cur = conn.cursor()

        moneda = str(data.get("moneda", "")).strip().lower()
        es_pesos = any(p in moneda for p in ["peso", "mnx", "mxn"])
        es_dolares = any(d in moneda for d in ["dolar", "dólar", "usd", "us", "dll"])

        app_ada_cfd_doc = data.get("app_ada_cfd_doc")  # puede ser none

        pct = float(data.get("porcentaje", 100.0))
        monto_original = float(data.get("monto_original", 0.0))

        if es_pesos:
            cur.execute("""
                INSERT INTO Presupuesto_Detalle_Comprobantes
                (ID_Detalle, Monto_Gasto_MNX, Autorizador, Estatus, uuid_documento, app_ada_cfd_doc, Porcentaje, Monto_Original)
                VALUES (%s,%s,%s,'Pendiente',%s,%s,%s,%s)
            """, (
                int(data["id_detalle"]),
                float(data.get("monto_mnx", 0.0)),
                str(data.get("autorizador", "")),
                str(data.get("uuid", "")),
                data.get("app_ada_cfd_doc"),
                pct,
                monto_original
            ))
        elif es_dolares:
            cur.execute("""
                INSERT INTO Presupuesto_Detalle_Comprobantes
                (ID_Detalle, Monto_Gasto_USD, Autorizador, Estatus, uuid_documento, app_ada_cfd_doc, Porcentaje, Monto_Original)
                VALUES (%s,%s,%s,'Pendiente',%s,%s,%s,%s)
            """, (
                int(data["id_detalle"]),
                float(data.get("monto_usd", 0.0)),
                str(data.get("autorizador", "")),
                str(data.get("uuid", "")),
                data.get("app_ada_cfd_doc"),
                pct,
                monto_original
            ))
        else:
            raise ValueError(f"moneda no reconocida: {data.get('moneda')}")

        # 2) sumar a presupuesto_detalle (mysql)
        if es_pesos:
            cur.execute("""
                UPDATE Presupuesto_Detalle
                SET Monto_Gasto_MNX = Monto_Gasto_MNX + %s
                WHERE ID = %s
            """, (float(data.get("monto_mnx", 0.0)), int(data["id_detalle"])))
        else:
            cur.execute("""
                UPDATE Presupuesto_Detalle
                SET Monto_Gasto_USD = Monto_Gasto_USD + %s
                WHERE ID = %s
            """, (float(data.get("monto_usd", 0.0)), int(data["id_detalle"])))

        # 3) sumar a presupuesto (mysql)
        cur.execute("SELECT ID_Presupuesto FROM Presupuesto_Detalle WHERE ID = %s", (int(data["id_detalle"]),))
        pres = cur.fetchone()
        if not pres:
            raise ValueError("no se encontró el id_presupuesto relacionado.")
        id_presupuesto = pres[0]

        if es_pesos:
            cur.execute("""
                UPDATE Presupuesto
                SET Monto_Asignado_MNX = Monto_Asignado_MNX + %s
                WHERE ID = %s
            """, (float(data.get("monto_mnx", 0.0)), id_presupuesto))
        else:
            cur.execute("""
                UPDATE Presupuesto
                SET Monto_Asignado_USD = Monto_Asignado_USD + %s
                WHERE ID = %s
            """, (float(data.get("monto_usd", 0.0)), id_presupuesto))

        conn.commit()

        # 4) marcar en ada (firebird) que ya fue contabilizado/registrado
        # ojo: en datoscfd no tienes columnas para concepto sae, así que solo marcamos contabilizado
        sql_ada = """
            UPDATE DATOSCFD
            SET CONTABILIZADO = 1
            WHERE UPPER(UUID) = ?
        """
        run_query_firebird("FIREBIRD_BIO_ADA", sql_ada, (str(data.get("uuid", "")).upper(),))

        try:
            conn = obtener_conexion()
            cur = conn.cursor()

            sql_mysql = """
                UPDATE DATOSCFD
                SET CONTABILIZADO = 1
                WHERE UPPER(UUID) = %s
            """
            cur.execute(sql_mysql, (str(data.get("uuid", "")).upper(),))
            conn.commit()

            # opcional: si quieres saber si realmente estaba en mysql
            # actualizado_mysql = cur.rowcount  # 1 si existió, 0 si no

            cur.close()
            conn.close()
        except Exception as e:
            # no rompemos el flujo si mysql datoscfd no tiene ese uuid o si falla la conexión
            st.write(f"[insertar_comprobante_presupuesto] aviso: no se pudo marcar datoscfd mysql: {e}")
        cur.close()
        conn.close()
        return True

    except Exception as e:
        st.write(f"[insertar_comprobante_presupuesto] error: {e}")
        if conn:
            conn.rollback()
        return False
    
def obtener_info_gasto_registrado(uuid: str):
    """
    Devuelve datos de unidad, usuario y estatus del comprobante si el gasto ya fue registrado.
    """
    try:
        conn = obtener_conexion()
        cur = conn.cursor(dictionary=True)
        sql = """
            SELECT 
                p.Nombre AS Presupuesto,
                u.nombre AS Unidad_Negocio,
                d.Usuario,
                c.autorizador AS Autorizador,
                c.estatus AS Estatus_Comprobante
            FROM Presupuesto_Detalle_Comprobantes c
            INNER JOIN Presupuesto_Detalle d ON c.ID_Detalle = d.ID
            INNER JOIN Presupuesto p ON d.ID_Presupuesto = p.Id
            LEFT JOIN Unidades_Negocio u ON d.Unidad_Negocio = u.id
            WHERE c.uuid_documento = %s
        """
        cur.execute(sql, (uuid,))
        data = cur.fetchall()
        cur.close()
        conn.close()
        return pd.DataFrame(data)
    except Exception as e:
        print(f"[obtener_info_gasto_registrado] Error: {e}")
        return pd.DataFrame()

def obtener_datos_cfdi(uuid: str):
    """
    Obtiene datos fiscales del CFDI desde la base ADA (tabla DATOSCFD).
    Campos: NOMBRE_EMISOR, RFC_EMISOR, FORMAPAGO, USOCFDI, LUGAR_EXPEDICION
    """
    try:
        secrets = st.secrets
        cfg = secrets["FIREBIRD_BIO_ADA"]

        conn = fdb.connect(
            host=cfg.get("host", "localhost"),
            database=cfg["database"],
            user=cfg["user"],
            password=cfg["password"],
            port=int(cfg.get("port", 3050)),
            charset=cfg.get("charset", "ISO8859_1"),
        )
        cur = conn.cursor()

        sql = """
            SELECT 
                NOMBRE_EMISOR,
                RFC_EMISOR,
                FORMAPAGO,
                USOCFDI,
                LUGAR_EXPEDICION
            FROM DATOSCFD
            WHERE UPPER(UUID) = ?
        """
        cur.execute(sql, (uuid.upper(),))
        row = cur.fetchone()

        cur.close()
        conn.close()

        if not row:
            return None

        return {
            "nombre_emisor": row[0],
            "rfc_emisor": row[1],
            "forma_pago": row[2],
            "uso_cfdi": row[3],
            "lugar_expedicion": row[4],
        }

    except Exception as e:
        st.write(f"[obtener_datos_cfdi] Error: {e}")
        return None
    
def obtener_comprobantes_por_mes(username: str):
    """
    Devuelve los comprobantes registrados ligados al usuario, agrupados por mes.
    """
    try:
        conn = obtener_conexion()
        cur = conn.cursor(dictionary=True)
        sql = """
            SELECT 
                u.nombre AS Unidad_Negocio,
                DATE_FORMAT(d.Fecha_Registro, '%Y-%m') AS Mes,
                c.uuid_documento AS UUID,
                c.Monto_Gasto_MNX,
                c.Monto_Gasto_USD,
                c.estatus AS Estatus,
                p.Nombre AS Presupuesto,
                c.autorizador,
                d.Usuario,
                Date (c.Fecha_Registro) as Fecha
            FROM Presupuesto_Detalle_Comprobantes c
            INNER JOIN Presupuesto_Detalle d ON d.ID = c.ID_Detalle
            INNER JOIN Unidades_Negocio u ON u.id = d.Unidad_Negocio
            INNER JOIN Presupuesto p ON p.Id = d.ID_Presupuesto
            ORDER BY Mes DESC, u.nombre
        """
        # WHERE d.Usuario = %s

        #cur.execute(sql, (username,))
        cur.execute(sql)
        data = cur.fetchall()
        cur.close()
        conn.close()
        df = pd.DataFrame(data)
        if df.empty:
            return df
        
        # Si no existe Fecha_Registro, calculamos mes a partir de Fecha_Inicial del presupuesto
        if "Mes" not in df.columns or df["Mes"].isnull().all():
            df["Mes"] = pd.to_datetime(df.get("Fecha_Inicial", pd.Timestamp.now())).dt.to_period("M").astype(str)
        
        return df
    except Exception as e:
        st.write(f"[obtener_comprobantes_por_mes] Error: {e}")
        return pd.DataFrame()
    
def insertar_gasto_no_fiscal(data: dict):
    
    try:
        conn = obtener_conexion()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO gastos_no_fiscales (
                usuario_id, presupuesto_id, unidad_id, proveedor, tipo, pago,
                descripcion, monto, estatus, fecha_gasto, fecha_registro
            )
            SELECT u.id, p.Id, un.id, %s, %s, %s, %s, %s, 'Nuevo', %s, NOW()
            FROM usuarios u
            JOIN Presupuesto p ON p.Nombre = %s
            JOIN Unidades_Negocio un ON un.nombre = %s
            WHERE u.id = %s
        """, (
            data["proveedor"],
            data["tipo"],
            data["pago"],
            data["descripcion"],
            data["monto"],
            data["fecha_gasto"],
            data["presupuesto"],
            data["unidad"],
            data["usuario_id"],
        ))
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        st.write(f"[insertar_gasto_no_fiscal] Error: {e}")
        return False
    
def obtener_gastos_no_fiscales_por_usuario(usuario_id: int):
    """
    Devuelve todos los gastos no fiscales registrados por el usuario.
    """
    try:
        conn = obtener_conexion()
        cur = conn.cursor(dictionary=True)
        sql = """
            SELECT 
                g.id,
                p.Nombre AS presupuesto,
                u.nombre AS unidad,
                g.proveedor,
                g.tipo,
                g.pago,
                g.descripcion,
                g.monto,
                g.estatus,
                DATE(g.fecha_gasto) AS fecha_gasto,
                DATE(g.fecha_registro) AS fecha_registro
            FROM gastos_no_fiscales g
            LEFT JOIN Presupuesto p ON g.presupuesto_id = p.Id
            LEFT JOIN Unidades_Negocio u ON g.unidad_id = u.id
            WHERE g.usuario_id = %s
            ORDER BY g.fecha_gasto DESC;
        """
        cur.execute(sql, (usuario_id,))
        data = cur.fetchall()
        cur.close()
        conn.close()
        return pd.DataFrame(data)
    except Exception as e:
        print(f"[obtener_gastos_no_fiscales_por_usuario] Error: {e}")
        return pd.DataFrame()
    
def obtener_gastos_fiscales_por_usuario(username: str):
    """
    Devuelve los comprobantes fiscales (CFDI) registrados por el usuario.
    """
    try:
        # --- 1️⃣ Obtención desde MySQL ---
        conn = obtener_conexion()
        cur = conn.cursor(dictionary=True)
        sql = """
            SELECT 
                p.Nombre AS presupuesto,
                u.nombre AS unidad,
                c.uuid_documento AS uuid,
                c.Monto_Gasto_MNX AS monto_mnx,
                c.Monto_Gasto_USD AS monto_usd,
                c.estatus,
                c.autorizador,
                DATE(c.Fecha_Registro) AS fecha_registro
            FROM Presupuesto_Detalle_Comprobantes c
            INNER JOIN Presupuesto_Detalle d ON c.ID_Detalle = d.ID
            INNER JOIN Unidades_Negocio u ON u.id = d.Unidad_Negocio
            INNER JOIN Presupuesto p ON p.Id = d.ID_Presupuesto
            WHERE d.Usuario = %s
            ORDER BY c.Fecha_Registro DESC;
        """
        cur.execute(sql, (username,))
        data = cur.fetchall()
        cur.close()
        conn.close()

        df = pd.DataFrame(data)
        if df.empty:
            return df

        # --- 2️⃣ Obtenemos campos adicionales desde Firebird ADA y SAE ---
        secrets = st.secrets
        cfg_ada = secrets["FIREBIRD_BIO_ADA"]
        #cfg_sae = secrets["FIREBIRD_BIO_SAE_4545"]

        # Conexión ADA
        conn_ada = fdb.connect(
            host=cfg_ada.get("host", "localhost"),
            database=cfg_ada["database"],
            user=cfg_ada["user"],
            password=cfg_ada["password"],
            port=int(cfg_ada.get("port", 3050)),
            charset=cfg_ada.get("charset", "ISO8859_1"),
        )
        cur_ada = conn_ada.cursor()

        # Añadimos columnas nuevas
        df["proveedor"] = ""
        df["rfc_emisor"] = ""
        df["documento"] = ""

        for i, row in df.iterrows():
            uuid = row["uuid"]

            # --- ADA: obtener emisor ---
            cur_ada.execute("""
                SELECT NOMBRE_EMISOR, RFC_EMISOR
                FROM DATOSCFD
                WHERE UPPER(UUID) = ?
            """, (uuid.upper(),))
            info_ada = cur_ada.fetchone()
            if info_ada:
                df.at[i, "proveedor"] = info_ada[0]
                df.at[i, "rfc_emisor"] = info_ada[1]

            # --- SAE: obtener REFER (documento) ---
            #sql_doc = """
            #    SELECT REFER 
            #    FROM PAGA_M01 
            #    WHERE APP_UUID = ?
            #    ROWS 1
            #"""
            #doc = run_query_firebird("FIREBIRD_BIO_SAE_4545", sql_doc, (uuid,))
            #if doc and len(doc) > 0:
            #    df.at[i, "documento"] = doc[0]["REFER"]
            # --- ada: obtener emisor + documento (folio/serie) ---
            cur_ada.execute("""
                SELECT NOMBRE_EMISOR, RFC_EMISOR, SERIE, FOLIO
                FROM DATOSCFD
                WHERE UPPER(UUID) = ?
            """, (uuid.upper(),))
            info_ada = cur_ada.fetchone()
            if info_ada:
                df.at[i, "proveedor"] = info_ada[0] or ""
                df.at[i, "rfc_emisor"] = info_ada[1] or ""
                serie = (info_ada[2] or "").strip()
                folio = (info_ada[3] or "").strip()
                df.at[i, "documento"] = f"{serie}-{folio}".strip("-")

        cur_ada.close()
        conn_ada.close()
        return df

    except Exception as e:
        print(f"[obtener_gastos_fiscales_por_usuario] Error: {e}")
        return pd.DataFrame()