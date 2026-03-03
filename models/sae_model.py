# --- models/sae_model.py  ---
import streamlit as st
import fdb
import pandas as pd
from datetime import date, datetime
from typing import Optional, Dict, Any
from models.datoscfd_mysql_model import obtener_detalle_datoscfd_mysql_df

def _clean_txt(x: Any) -> str:
    if x is None:
        return ""
    try:
        if pd.isna(x):
            return ""
    except Exception:
        pass
    s = str(x).strip()
    return "" if s.lower() == "nan" else s

def _refer(serie: Any, folio: Any, uuid: Any = None) -> str:
    s = _clean_txt(serie).upper()
    f = _clean_txt(folio).upper()
    # caso 1: no hay serie pero sí folio → pad izquierda a 20
    if not s and f:
        return f[:20].rjust(20)
    # caso 2: hay serie → normal concatenación (máx 20)
    if s:
        return (s + f)[:20]
    # caso 3: no hay serie ni folio → usar solo 8 del uuid (sin guiones)
    u = _clean_txt(uuid).upper().replace("-", "")
    if u:
        return u[:8]
    # fallback: nada de nada
    return " " * 20

def _conn_sae_from_secrets(secrets) -> fdb.Connection:
    cfg = secrets["FIREBIRD_BIO_SAE"]
    return fdb.connect(
        host=cfg.get("host","localhost"),
        database=cfg["database"],
        user=cfg["user"],
        password=cfg["password"],
        port=int(cfg.get("port",3050)),
        charset=cfg.get("charset","ISO8859_1"),
    )

def _buscar_num_cpto_ideal(cur, cve_prov: str, importe: float, fecha_emision=None) -> tuple[int, str]:
    """
    Determina el NUM_CPTO correcto para una inserción en PAGA_M01.
    Devuelve (num_cpto, metodo) donde 'metodo' puede ser:
      - 'único'       → proveedor con un solo concepto
      - 'importe'     → coincidencia por importe (±3–5%)
      - 'frecuencia'  → concepto más frecuente del proveedor
      - 'default'     → no se encontró nada, usa 987
    """
    cve_prov = (cve_prov or "").rjust(10)
    if not cve_prov.strip():
        return 987, "default"

    # --- 1️⃣ proveedor con único concepto ---
    cur.execute("select distinct num_cpto from paga_m01 where cve_prov = ?", (cve_prov,))
    conceptos = [r[0] for r in cur.fetchall() if r[0] is not None]
    if len(conceptos) == 1:
        return int(conceptos[0]), "único"

    # --- 2️⃣ buscar por importe similar (±3–5%) ---
    if importe and len(conceptos) > 1:
        try:
            imp = float(importe)
            min_imp = imp * 0.95
            max_imp = imp * 0.97
            cur.execute("""
                select first 1 num_cpto
                from paga_m01
                where cve_prov = ?
                  and importe between ? and ?
                order by fechaelab desc
            """, (cve_prov, min_imp, max_imp))
            row = cur.fetchone()
            if row and row[0] is not None:
                return int(row[0]), "importe"
        except Exception:
            pass

    # --- 3️⃣ concepto más frecuente ---
    cur.execute("""
        select first 1 num_cpto
        from paga_m01
        where cve_prov = ?
        group by num_cpto
        order by count(*) desc
    """, (cve_prov,))
    row = cur.fetchone()
    if row and row[0] is not None:
        return int(row[0]), "frecuencia"

    # --- 4️⃣ fallback ---
    return 987, "default"

def _rfc(s: Any) -> str:
    return (str(s or "")).strip().upper()[:13]


def _importe_mxn(total_mxn: Any) -> float:
    try:
        return round(float(str(total_mxn).replace(",", "").replace("$", "")), 2)
    except Exception:
        return 0.0

def _fecha(fecha_emision: Any) -> date:
    dt = pd.to_datetime(fecha_emision, errors="coerce")
    return (dt if pd.notna(dt) else pd.Timestamp.today()).date()



def _proveedor_por_rfc(cur, rfc: str) -> Optional[str]:
    cur.execute("select CLAVE from PROV01 where upper(RFC)=upper(?) and status != 'B'", (rfc,))
    row = cur.fetchone()
    if row and row[0]:
        return str(row[0]).strip().rjust(10)[:10]
    # fallback a 0001 alineado a derecha
    return "0001".rjust(10)

def obtener_dias_credito_proveedor(cur, cve_prov: Any) -> int:
    """
    regresa prov01.diascred del proveedor (status != 'B')
    si no existe / nulo / error -> 0
    """
    clave = (str(cve_prov or "").strip() or "").rjust(10)[:10]

    try:
        cur.execute(
            "select first 1 coalesce(DIASCRED, 0) from PROV01 where CLAVE = ? and STATUS != 'B'",
            (clave,),
        )
        row = cur.fetchone()
        if row and row[0] is not None:
            return int(row[0])
        return 0
    except Exception:
        return 0

def _tiene_columna(cur, tabla: str, columna: str) -> bool:
    cur.execute("""
      select 1
      from rdb$relation_fields
      where rdb$relation_name = upper(?)
        and rdb$field_name = upper(?)
    """, (tabla, columna))
    return cur.fetchone() is not None

def _nuevo_Folio_Paga01(cur):
    cur.execute("SELECT COALESCE (MAX( cast(CVE_FOLIO as int)),0) + 1 as FolioNuevo FROM FOLcxP01")
    row = cur.fetchone()
    if row and row[0]:
        return str(row[0]).strip().rjust(9)[:9]
    return "0001".rjust(9)


def _debug_sql_print(sql: str, vals: list[Any]) -> None:
    
    try:
        dbg = sql
        for v in vals:
            if v is None:
                rep = "NULL"
            elif isinstance(v, (datetime, )):
                rep = f"'{v.strftime('%Y-%m-%d %H:%M:%S')}'"
            elif isinstance(v, (date, )):
                rep = f"'{v.strftime('%Y-%m-%d')}'"
            #elif isinstance(v, str):
            #    rep = f"'{v.replace(\"'\", \"''\")}'"
            else:
                rep = str(v)
            dbg = dbg.replace("?", rep, 1)
        print(dbg)
    except Exception as _:
        print(sql, vals)


    
def insertar_en_compc01(secrets, rfc_emisor, serie, folio, fecha_emision, total_mxn, uuid=None) -> Dict[str, Any]:
    con = _conn_sae_from_secrets(secrets)
    cur = con.cursor()
    try:
        rfc  = _rfc(rfc_emisor)
        cve  = _proveedor_por_rfc(cur, rfc)
        refe = _refer(serie, folio)
        fch  = _fecha(fecha_emision)
        imp  = _importe_mxn(total_mxn)

        cols = ["CVE_PROV","REFER","FECHA_DOC","IMPORTE"]
        vals = [cve,        refe,    fch,         imp]
        if _tiene_columna(cur, "COMPC01", "UUID") and uuid:
            cols.append("UUID"); vals.append(str(uuid).upper())

        sql = f"insert into COMPC01 ({', '.join(cols)}) values ({', '.join(['?']*len(cols))})"
        cur.execute(sql, tuple(vals))
        con.commit()
        return {"ok": True, "tabla": "COMPC01", "cve_prov": cve, "refer": refe, "msg": "Insertado en COMPC01"}
    except Exception as e:
        con.rollback()
        return {"ok": False, "tabla": "COMPC01", "msg": f"{e}"}
    finally:
        try: cur.close()
        except: pass
        con.close()



def insertar_en_paga_m01(secrets, rfc_emisor, serie, folio, fecha_emision, total_mxn, uuid, usocfdi, clave_prov, id_docto_dig, moneda, tcambio, impext, num_cpto_manual=None, concepto_label=None,) -> Dict[str, Any]:
    con = _conn_sae_from_secrets(secrets)
    cur = con.cursor()
    ahora = datetime.now()
    #st.write("Intenta la insercion")
    #st.write(f"Datos para inserción: rfc_emisor={rfc_emisor}, serie={serie}, folio={folio}, fecha_emision={fecha_emision}, total_mxn={total_mxn}, uuid={uuid}, usocfdi={usocfdi}, clave_prov={clave_prov}, id_docto_dig={id_docto_dig}, moneda={moneda}, tcambio={tcambio}, impext={impext}, num_cpto_manual={num_cpto_manual}, concepto_label={concepto_label}")
    if uuid:
        try:
            cur.execute(
                "select first 1 cve_folio from paga_m01 where app_uuid = ? and status = 'A'",
                (str(uuid),),
            )
            row_dup = cur.fetchone()
            if row_dup and row_dup[0]:
                folio_existente = row_dup[0]
                return {
                    "ok": False,
                    "tabla": "PAGA_M01",
                    "folio_num": folio_existente,
                    "duplicado": True,
                    "msg": f"ya existe un movimiento en PAGA_M01 con este APP_UUID (cve_folio={folio_existente})",
                }
        except Exception as e:
            # si la validación falla por alguna razón, seguimos manejando como error normal
            return {
                "ok": False,
                "tabla": "PAGA_M01",
                "duplicado": False,
                "msg": f"error al validar app_uuid en PAGA_M01: {e}",
            }
    # mapeo de monedas a su código numérico
    mapa_monedas = {
        "MXN": 1,
        "USD": 2,
        "EUR": 3,
        "CAD": 4,
        "JPY": 5,
    }
    # asigna el valor según la moneda, por defecto 3 (u otro que definas)
    moneda_int = mapa_monedas.get(moneda.upper(), 1)
    #st.write("intenta la insercion en la funcion insertar en paga_m01")
    rfc  = _rfc(rfc_emisor)
    cve  = _proveedor_por_rfc(cur, rfc)
    refe = _refer(serie, folio, uuid)
    cargo = 1
    folio = _nuevo_Folio_Paga01(cur)
    obs = 0
    factura = refe
    docto = refe
    imp  = _importe_mxn(total_mxn)
    fch  = _fecha(fecha_emision)
    venc = fch + pd.Timedelta(days=obtener_dias_credito_proveedor(cur, cve))
    coi = ''
    moned = moneda_int 
    cambio = tcambio
    ext = _importe_mxn(impext)
    elab = ahora.strftime("%Y-%m-%d %H:%M:%S")
    pol = None
    mov = 'C'
    bita = None
    signo = 1
    aut = None
    usuario = 100
    entrega = ''
    ref_sit = None
    status = 'A'
    app_org = 'OneCore'
    app_uuid = uuid 
    app_status = 'inicial'
    app_usuario = '1'
    app_fecha = ahora.strftime("%Y-%m-%d %H:%M:%S")
    # si viene un num_cpto_manual desde la vista, se respeta y se marca metodo 'manual'
    if num_cpto_manual is not None:
        try:
            cpto = int(num_cpto_manual)
        except Exception:
            cpto = int(num_cpto_manual)  # en caso de que venga como str
        metodo = "manual"
    else:
        cpto, metodo = _buscar_num_cpto_ideal(cur, cve, imp, fch)

    try:
        #st.write("Entra al Try")
        # -------------------------
        # 1) Obtener/Reservar folio para PAGA_M01 (mismo cursor/tx)
        #    Si ya tienes una función que lo toma de FOLIOSCXP01, úsala aquí
        # -------------------------
        # Ejemplo genérico: FOLIOSCXP01 guarda el consecutivo por algo tipo CVE_FOLIO='P'
        # Ajusta a tu esquema real (WHERE, campos)
        cur.execute("SELECT ULT_FOLIO FROM FOLIOSCXP01 WHERE CVE_FOLIO = 'STAND.' FOR UPDATE")
        row = cur.fetchone()
        if not row:
            raise ValueError("No existe configuración de folios en FOLIOSCXP01 para CVE_FOLIO='P'.")
        folio_num = int(row[0])               # siguiente
        cve_folio = folio_num                 # PAGA_M01.CVE_FOLIO (numérico/entero)

        # -------------------------
        # 2) INSERT en PAGA_M01
        # -------------------------
        
        cols = ["CVE_PROV","REFER", "NUM_CARGO", "NUM_CPTO", "CVE_FOLIO", "CVE_OBS", "NO_FACTURA", "DOCTO", "IMPORTE", "FECHA_APLI", "FECHA_VENC", "AFEC_COI",
                "NUM_MONED", "TCAMBIO", "IMPMON_EXT", "FECHAELAB", "CTLPOL", "TIPO_MOV", "CVE_BITA", "SIGNO", "CVE_AUT", "USUARIO", "ENTREGADA", "FECHA_ENTREGA", 
                "REF_SIST", "STATUS", "APP_ORIGEN", "APP_UUID", "APP_STATUS", "APP_USUARIO", "APP_FECHA", "APP_ADA_CFD_DOC", "APP_METODO", 
                ]
        
        vals = [cve  ,refe ,cargo ,cpto ,folio ,obs ,factura ,docto ,imp  ,fch  ,venc ,coi ,
                moned ,cambio ,ext ,elab ,pol ,mov ,bita ,signo ,aut ,usuario ,entrega , elab,
                ref_sit, status ,app_org ,app_uuid ,app_status ,app_usuario ,app_fecha, id_docto_dig, metodo
                ]

        #if _tiene_columna(cur, "PAGA_M01", "UUID") and uuid:
        #    cols.append("UUID"); vals.append(str(uuid).upper())

        sql_paga = f"insert into PAGA_M01 ({', '.join(cols)}) values ({', '.join(['?']*len(cols))})"
        #st.write(f"SQL a ejecutar en PAGA_M01: {sql_paga} con valores {vals}")

        cur.execute(sql_paga, tuple(vals))
        
        # -------------------------
        # 3) UPDATE FOLIOSCXP01 (incrementar consecutivo)
        # -------------------------
        cur.execute("UPDATE FOLIOSCXP01 SET ULT_FOLIO = ? WHERE CVE_FOLIO = 'STAND.'", (cve_folio + 1,))
        
        # -------------------------
        # 4) INSERT en FOLCXP01 (histórico de uso de folio)
        #    Ajusta las columnas exactas a tu esquema real
        # -------------------------
        # Ejemplo típico mínimo:
        from models.ada_model import obtener_detalle_documento
        # aquí consultas ADA con el UUID o el id_docto_dig
        from models.datoscfd_mysql_model import obtener_datoscfd_mysql_df

       
        detalle = obtener_detalle_documento(secrets, id_docto_dig, uuid=uuid)
        #st.write(f"Detalle desde MySQL para id_docto_dig={id_docto_dig}, uuid={uuid}: {detalle}")
        if detalle:
            imp1  = (detalle.get("IEPS") or 0) ## 003 -- IEPS -- 0
            imp2  = (detalle.get("ISR") or 0) ## ISR -- -10.6670
            imp3  = (detalle.get("IVA_RET") or 0) ## RET IVA -- -10.00
            imp4  = (detalle.get("IVA_TASA_16") or 0) ## IVA_TASA_16
        else:
            #st.write(f"No se encontró detalle en DATOSCFD para id_docto_dig={id_docto_dig} y uuid={uuid}")
            detalle = obtener_detalle_datoscfd_mysql_df(id_docto_dig=id_docto_dig, uuid=uuid)
            fila = detalle.iloc[0]   # esto ya es una Series (una fila)
            imp1 = fila.get("IEPS", 0)
            imp2 = fila.get("ISR", 0)
            imp3 = fila.get("IVA_RET", 0)
            imp4 = fila.get("IVA_TASA_16", 0)
            
        #st.write(f"Impuestos extraídos para id_docto_dig={id_docto_dig}, uuid={uuid}: IEPS={imp1}, ISR={imp2}, IVA_RET={imp3}, IVA_TASA_16={imp4}")
        #st.stop()
            
        #if detalle is None:
        #    st.warning(f"No se encontró DATOSCFD con ID_DOCTODIG={id_docto_dig}")
        #else:
            #st.json(detalle)  # para inspección   
        
        status = 'O'
        usuario = 599

        cols_fol = ["CVE_FOLIO", "IMPUESTO1", "IMPUESTO2", "IMPUESTO3", "IMPUESTO4", "REFERENCIA", "STATUS", "FECHA","FECHAELAB","USUARIO"]
        vals_fol = [folio, imp1, imp2, imp3, imp4, refe, status, fch, app_fecha, usuario]
        sql_fol = f"INSERT INTO FOLCXP01 ({', '.join(cols_fol)}) VALUES ({', '.join(['?']*len(cols_fol))})"
        debug_sql = sql_fol
        if debug_sql:
            _debug_sql_print(sql_fol, vals_fol)

        cur.execute(sql_fol, tuple(vals_fol))
        
        # -------------------------
        # 5) Commit (si todo ok)
        # -------------------------
        con.commit()
        return {
            "ok": True,
            "tabla": "PAGA_M01",
            "cve_prov": cve,
            "refer": refe,
            "folio_num": folio_num + 1,
            "msg": "Insertado en PAGA_M01 y actualizado FOLIOSCXP01/FOLCXP01"
        }
        
    except Exception as e:
        con.rollback()
        return {"ok": False, "tabla": None, "msg": f"{e}"}
    finally:
        try:
            cur.close()
        except:
            pass
        con.close()

def insertar_en_sae_por_uso(secrets, usocfdi, **kwargs) -> Dict[str, Any]:
    uso = (str(usocfdi or "").strip().upper())

    uso_norm = (uso or "").strip().upper()
    if not uso_norm.startswith("G01"):
        return insertar_en_paga_m01(
            secrets=secrets,
            rfc_emisor=kwargs.get("rfc_emisor"),
            serie=kwargs.get("serie"),
            folio=kwargs.get("folio"),
            fecha_emision=kwargs.get("fecha_emision"),
            total_mxn=kwargs.get("total_mxn"),
            uuid=kwargs.get("uuid"),
            usocfdi=uso,
            clave_prov=kwargs.get("clave_prov"),
            id_docto_dig=kwargs.get("id_docto_dig"),
            moneda=kwargs.get("moneda", 1),
            tcambio=kwargs.get("tcambio", 1.0),
            impext=kwargs.get("impext", 0.0),
            num_cpto_manual=kwargs.get("num_cpto_manual"),
            concepto_label=kwargs.get("concepto_label"),
        )
    
    return {"ok": False, "tabla": None, "msg": f"USO_CFDI '{uso}' no soportado"}


def cargar_conceptos_por_prov(_secrets, f_ini=None, f_fin=None):
    """
    Regresa un DataFrame con columnas:
      CVE_PROV, NOMBRE_PROV, NUM_CPTO, DESCR, USOS
    """
    con = _conn_sae_from_secrets(_secrets)
    try:
        cur = con.cursor()
        sql = """
            SELECT
              m.CVE_PROV,
              p.NOMBRE AS NOMBRE_PROV,
              m.NUM_CPTO,
              COALESCE(c.DESCR, '') AS DESCR,
              COUNT(*) AS USOS
            FROM PAGA_M01 m
            LEFT JOIN CONP01 c ON c.NUM_CPTO = m.NUM_CPTO
            LEFT JOIN PROV01 p ON p.CLAVE = m.CVE_PROV
            WHERE 1=1
        """
        params = []
        if f_ini and f_fin:
            sql += " AND m.FECHA_APLI BETWEEN ? AND ?"
            params.extend([f_ini, f_fin])

        sql += """
            GROUP BY m.CVE_PROV, p.NOMBRE,  m.NUM_CPTO, c.DESCR
            ORDER BY m.CVE_PROV, m.NUM_CPTO
        """
        cur.execute(sql, tuple(params))
        rows = cur.fetchall()
        cols = [d[0].strip() for d in cur.description]
        import pandas as pd
        return pd.DataFrame(rows, columns=cols)
    finally:
        con.close()


def insertar_mov_paga_m01(secrets, payload: dict) -> dict:
    """
    payload["num_cpto"]  -> NUM_CPTO seleccionado
    payload["doc"]       -> dict con todos los campos del CFDI (CVE_PROV_MATCH, TOTAL_MXN, UUID, etc.)
    """
    # aquí abres conexión a SAE usando secrets
    # extraes del payload lo que ocupes (clave proveedor, referencia, importe, fecha, etc.)
    # construyes y ejecutas el INSERT INTO PAGA_M01(...)
    # regresas algo tipo {"ok": True} o {"ok": False, "error": "..."}
    pass


def cargar_conceptos_sae(_secrets):
    """
    Regresa un DataFrame con columnas:
      CVE_PROV, NOMBRE_PROV, NUM_CPTO, DESCR, USOS
    """
    con = _conn_sae_from_secrets(_secrets)
    try:
        cur = con.cursor()
        sql = """
            SELECT
              NUM_CPTO, 
              DESCR 
            FROM CONP01 c
            WHERE TIPO = 'C' AND CON_REFER = 'N' AND STATUS = 'A' AND NUM_CPTO >= '29'
        """
        cur.execute(sql)
        rows = cur.fetchall()
        cols = [d[0].strip() for d in cur.description]
        import pandas as pd
        return pd.DataFrame(rows, columns=cols)
    finally:
        con.close()