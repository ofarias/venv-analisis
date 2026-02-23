# models/sae45_model.py
import fdb
import pandas as pd
from datetime import timedelta, datetime, date
from typing import Optional, Dict, Any
import streamlit as st 

def _conn_sae_from_secrets(secrets) -> fdb.Connection:
    cfg = secrets["FIREBIRD_BIO_SAE"]  # agrega este bloque en tus secrets
    return fdb.connect(
        host=cfg.get("host","localhost"),
        database=cfg["database"],
        user=cfg["user"],
        password=cfg["password"],
        port=int(cfg.get("port",3050)),
        charset=cfg.get("charset","ISO8859_1"),
    )

def _refer_variantes(serie, folio):
    serie = (serie or "").strip(); folio = (folio or "").strip()
    v = set()
    if folio: v.add(folio)
    if serie and folio:
        v.update({f"{serie}{folio}", f"{serie}-{folio}", f"{serie} {folio}", f"{serie}/{folio}"})
    return list(v)

def buscar_documento_en_sae(secrets, rfc_emisor, serie, folio, uuid, total, fecha_emision, dias_tolerancia=7) -> pd.DataFrame:
    con = _conn_sae_from_secrets(secrets)
    try:
        cur = con.cursor()
        rfc = (rfc_emisor or "").strip().upper()[:13]
        variantes = _refer_variantes(serie, folio)

        f_ini = f_fin = None
        if fecha_emision:
            dt = pd.to_datetime(fecha_emision, errors="coerce")
            if pd.notna(dt):
                dt = dt.date()
                f_ini = dt - timedelta(days=dias_tolerancia)
                f_fin = dt + timedelta(days=dias_tolerancia)

        def _fetch(sql, params):
            cur.execute(sql, params)
            cols = [d[0].strip() for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

        resultados = []

        if uuid:
            try:
                resultados += _fetch("""
                    select 'COMPC01' as tabla, c.cve_clpv, p.nombre as proveedor, p.rfc,
                           c.su_refer, c.fecha_doc as fecha, c.importe as importe, 'uuid' as match
                    from compc01 c
                    join prov01 p on p.clave = c.cve_clpv
                    where upper(p.rfc) = upper(?) and upper(c.uuid) = upper(?)
                """, (rfc, uuid))
            except Exception:
                pass
            try:
                resultados += _fetch("""
                    select 'PAGA_M01' as tabla, m.cve_prov, p.nombre as proveedor, p.rfc,
                           m.refer, m.fecha_apli as fecha, m.importe as importe, 'uuid' as match
                    from paga_m01 m
                    join prov01 p on p.clave = m.cve_prov
                    where upper(p.rfc) = upper(?) and upper(m.uuid) = upper(?)
                """, (rfc, uuid))
            except Exception:
                pass

        if variantes:
            ph = ",".join(["upper(?)"]*len(variantes))
            params = tuple([rfc] + variantes)
            resultados += _fetch(f"""
                select 'COMPC01' as tabla, c.cve_clpv, p.nombre as proveedor, p.rfc,
                       c.su_refer, c.fecha_doc as fecha, c.importe as importe, 'refer' as match
                from compc01 c
                join prov01 p on p.clave = c.cve_clpv
                where upper(p.rfc) = upper(?) and upper(c.su_refer) in ({ph})
            """, params)
            resultados += _fetch(f"""
                select 'PAGA_M01' as tabla, m.cve_prov, p.nombre as proveedor, p.rfc,
                       m.refer, m.fecha_apli as fecha, m.importe as importe, 'refer' as match
                from paga_m01 m
                join prov01 p on p.clave = m.cve_prov
                where upper(p.rfc) = upper(?) and upper(m.refer) in ({ph})
            """, params)

        df = pd.DataFrame(resultados)
        if df.empty:
            return df

        if "fecha" in df.columns and f_ini and f_fin:
            df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce").dt.date
            df = df[(df["fecha"] >= f_ini) & (df["fecha"] <= f_fin)]

        if total is not None and "importe" in df.columns:
            try:
                t = float(total)
                df["importe"] = pd.to_numeric(df["importe"], errors="coerce")
                df = df[df["importe"].sub(t).abs() <= max(1.0, t*0.01)]
            except Exception:
                pass

        return df.reset_index(drop=True)
    finally:
        con.close()

def _refer(serie: Optional[str], folio: Optional[str]) -> str:
    s = (serie or "").strip()
    f = (folio or "").strip()
    if s and f: 
        return f"{s}-{f}"
    return f or s  # si solo hay uno

def _normaliza_total_mxn(total: Any, tipocambio: Any) -> float:
    try:
        t = float(str(total).replace(",", ""))
    except Exception:
        t = 0.0
    try:
        tc = float(tipocambio) if tipocambio not in (None, "") else 1.0
        if tc <= 0: tc = 1.0
    except Exception:
        tc = 1.0
    return round(t * tc, 2)

def _proveedor_por_rfc(cur, rfc: str) -> Optional[Dict[str, Any]]:
    cur.execute("select CLAVE, NOMBRE, RFC from PROV01 where upper(RFC) = upper(?)", (rfc[:13],))
    row = cur.fetchone()
    if not row: 
        return None
    cols = [d[0].strip() for d in cur.description]
    return dict(zip(cols, row))

def _tiene_columna(cur, tabla: str, columna: str) -> bool:
    cur.execute("""
      select 1
      from rdb$relation_fields
      where rdb$relation_name = upper(?)
        and rdb$field_name = upper(?)
    """, (tabla, columna))
    return cur.fetchone() is not None

def insertar_en_sae_por_uso_cfdi(
    secrets,
    rfc_emisor: str,
    serie: Optional[str],
    folio: Optional[str],
    uuid: Optional[str],
    total: Any,
    tipocambio: Any,
    fecha_emision: Any,
    uso_cfdi: str,
) -> Dict[str, Any]:
    uso_cfdi = (uso_cfdi or "").strip().upper()
    if uso_cfdi.startswith("G01"):
        destino = "COMPC01"
    elif uso_cfdi.startswith("G03"):
        destino = "PAGA_M01"
    else:
        return {"insertado": False, "tabla": None, "refer": None,
                "msg": f"USO_CFDI '{uso_cfdi}' no soportado para inserción automática.",
                "sql": None, "params": None}

    refer = _refer(serie, folio)[:20]  # ¡asegura máx 20!
    fecha = pd.to_datetime(fecha_emision, errors="coerce")
    if pd.isna(fecha):
        fecha = pd.Timestamp.today()
    fecha_date = fecha.date()
    importe_mxn = _normaliza_total_mxn(total, tipocambio)
    rfc = (rfc_emisor or "").strip().upper()[:13]

    con = _conn_sae_from_secrets(secrets)
    cur = con.cursor()

    sql, params = None, None  # <-- para poder devolverlos
    try:
        # 0) proveedor
        prov = _proveedor_por_rfc(cur, rfc)
        if not prov:
            return {"insertado": False, "tabla": None, "refer": refer,
                    "msg": f"No existe proveedor con RFC {rfc} en PROV01.",
                    "sql": None, "params": None}
        cve_prov = prov["CLAVE"]

        # 1) duplicados
        df = buscar_documento_en_sae(
            secrets, rfc_emisor=rfc, serie=serie, folio=folio,
            uuid=uuid, total=importe_mxn, fecha_emision=fecha
        )
        if isinstance(df, pd.DataFrame) and not df.empty:
            return {"insertado": False, "tabla": None, "refer": refer,
                    "msg": "Documento ya existe en SAE (por UUID/REFER/importe/fecha).",
                    "sql": None, "params": None}

        # 2) build SQL
        tiene_uuid = _tiene_columna(cur, destino, "UUID")
        if destino == "COMPC01":
            if tiene_uuid:
                sql = """insert into COMPC01 (CVE_PROV, REFER, FECHA, IMPORTE, UUID)
                         values (?, ?, ?, ?, ?)"""
                params = (cve_prov, refer, fecha_date, importe_mxn, uuid)
            else:
                sql = """insert into COMPC01 (CVE_PROV, REFER, FECHA, IMPORTE)
                         values (?, ?, ?, ?)"""
                params = (cve_prov, refer, fecha_date, importe_mxn)
        else:
            if tiene_uuid:
                sql = """insert into PAGA_M01 (CVE_PROV, REFER, FECHA_APLI, IMPORTE, UUID)
                         values (?, ?, ?, ?, ?)"""
                params = (cve_prov, refer, fecha_date, importe_mxn, uuid)
            else:
                sql = """insert into PAGA_M01 (CVE_PROV, REFER, FECHA_APLI, IMPORTE)
                         values (?, ?, ?, ?)"""
                params = (cve_prov, refer, fecha_date, importe_mxn)

        # 3) ejecutar
        cur.execute(sql, params)
        con.commit()
        return {"insertado": True, "tabla": destino, "refer": refer,
                "msg": f"Insertado en {destino} con REFER '{refer}' y CVE_PROV '{cve_prov}'.",
                "sql": sql, "params": list(params)}
    except Exception as e:
        con.rollback()
        return {"insertado": False, "tabla": destino, "refer": refer,
                "msg": f"Error: {e}", "sql": sql, "params": list(params) if params else None}
    finally:
        try: cur.close()
        except: pass
        con.close()

def obtener_proveedores_activos(secrets) -> dict[str, str]:
    """Regresa {RFC: CLAVE} de PROV01 filtrando solo STATUS/ESTATUS != 'B'."""
    con = _conn_sae_from_secrets(secrets)
    try:
        cur = con.cursor()
        proveedores: dict[str, str] = {}

        # Intento 1: columna STATUS
        try:
            cur.execute("select CLAVE, RFC from PROV01 where RFC is not null and STATUS != 'B'")
            rows = cur.fetchall()
        except Exception:
            # Intento 2: algunas instalaciones usan ESTATUS
            cur.execute("select CLAVE, RFC from PROV01 where RFC is not null and ESTATUS != 'B'")
            rows = cur.fetchall()

        for clave, rfc in rows:
            r = (rfc or "").strip().upper()[:13]
            c = (clave or "").strip()
            if r and c:
                proveedores[r] = c

        return proveedores
    finally:
        con.close()

def _clave_prov_normalizada(clave: Optional[str]) -> str:
    """
    CVE_PROV en SAE suele ser CHAR(10) alineado a la derecha con espacios.
    Tomamos la clave (e.g. '0001') y la devolvemos como '      0001'.
    """
    c = (clave or "").strip()
    if not c:
        c = "0001"  # fallback lógico
    return c.rjust(10)  # '      0001'

def _refer_sae(serie: Optional[str], folio: Optional[str]) -> str:
    """REFER = SERIE + FOLIO (sin separador), en mayúsculas."""
    s = (serie or "").strip()
    f = (folio or "").strip()
    return (s + f).upper()

def buscar_en_paga_m01_g03(
    secrets,
    uso_cfdi: str,
    rfc_receptor: str,
    clave_prov_sae: Optional[str],
    serie: Optional[str],
    folio: Optional[str],
    total_mxn: Any,
) -> pd.DataFrame:
    """
    Busca el documento en PAGA_M01 con la combinación:
      CVE_PROV = CLAVE_PROV_SAE (o '      0001' si viene vacío),
      REFER = SERIE + FOLIO,
      NUM_CARGO = 1,
      NUM_CPTO != 1,
      IMPORTE = TOTAL_MXN (redondeado a 2 decimales).
    Solo aplica cuando USO_CFDI inicia con 'G03' y RFC_RECEPTOR == 'BIO870307QD0'.
    """
    uso = (uso_cfdi or "").strip().upper()
    rfc_rec = (rfc_receptor or "").strip().upper()

    if not (uso.startswith("G03") and rfc_rec == "BIO870307QD0"):
        # Regla no aplica: retornar df vacío
        return pd.DataFrame(columns=["TABLA","CVE_PROV","REFER","NUM_CPTO","NUM_CARGO","IMPORTE","FECHA_APLI"])

    cve = _clave_prov_normalizada(clave_prov_sae)  # usa '      0001' si no hay
    refer = _refer_sae(serie, folio)

    # normaliza importe a 2 decimales
    try:
        importe = float(str(total_mxn).replace(",", ""))
    except Exception:
        importe = 0.0
    importe = round(importe, 2)

    sql = """
    select
      'PAGA_M01' as TABLA,
      m.CVE_PROV,
      m.REFER,
      m.NUM_CPTO,
      m.NUM_CARGO,
      m.IMPORTE,
      m.FECHA_APLI
    from PAGA_M01 m
    where m.CVE_PROV = ?
      and upper(m.REFER) = upper(?)
      and m.NUM_CARGO = 1
      and m.NUM_CPTO <> 1
      and cast(m.IMPORTE as numeric(15,2)) = cast(? as numeric(15,2))
    """

    con = _conn_sae_from_secrets(secrets)
    try:
        cur = con.cursor()
        # parámetros posicionales (Firebird 2.5)
        cur.execute(sql, (cve, refer, importe))
        cols = [d[0].strip() for d in cur.description]
        rows = cur.fetchall()
        return pd.DataFrame(rows, columns=cols)
    finally:
        con.close()

# --- Normalizadores de llaves SAE ---
def _rjust10(clave: Optional[str]) -> str:
    """CVE_PROV: CHAR(10) alineado a la derecha."""
    c = (clave or "").strip()
    return c.rjust(10)[:10]

def _refer20(refer: Optional[str]) -> str:
    """REFER: VARCHAR(20) en UPPER."""
    return (refer or "").upper()[:20]

def _refer_concat20(serie: Optional[str], folio: Optional[str]) -> str:
    """REFER = SERIE + FOLIO (sin separador), máximo 20 y UPPER."""
    s = (serie or "").strip()
    f = (folio or "").strip()
    return _refer20(s + f)

# --- SNAPSHOT PAGA_M01 ---
def snapshot_paga_m01(secrets, cves: list[str], refers: list[str], f_ini=None, f_fin=None) -> pd.DataFrame:
    """
    Devuelve columnas: TABLA, CVE_PROV, REFER, NUM_CARGO, NUM_CPTO, IMPORTE, FECHA_APLI
    Filtros fijos: NUM_CARGO=1 y NUM_CPTO<>1
    Limita por IN (CVE_PROV) e IN (REFER), con longitudes correctas.
    """
    # columnas vacías consistentes
    empty_cols = ["TABLA","CVE_PROV","REFER","NUM_CARGO","NUM_CPTO","IMPORTE","FECHA_APLI"]
    if not cves or not refers:
        return pd.DataFrame(columns=empty_cols)

    cves_norm   = [_rjust10(x) for x in cves if x]
    refers_norm = [_refer20(x) for x in refers if x]

    if not cves_norm or not refers_norm:
        return pd.DataFrame(columns=empty_cols)

    ph_cve = ",".join(["?"]*len(cves_norm))
    ph_ref = ",".join(["?"]*len(refers_norm))

    sql = f"""
      select 'PAGA_M01' as TABLA, m.CVE_PROV, upper(m.REFER) as REFER,
             m.NUM_CARGO, m.NUM_CPTO, m.IMPORTE, m.FECHA_APLI
      from PAGA_M01 m
      where m.CVE_PROV in ({ph_cve})
        and upper(m.REFER) in ({ph_ref})
        and m.NUM_CARGO = 1
        and m.NUM_CPTO <> 1
    """
    params = tuple(cves_norm + refers_norm)
    if f_ini and f_fin:
        sql += " and m.FECHA_APLI between ? and ?"
        params += (f_ini, f_fin)

    con = _conn_sae_from_secrets(secrets)
    cur = con.cursor()
    try:
        cur.execute(sql, params)
        cols = [d[0].strip() for d in cur.description]
        rows = cur.fetchall()
        df = pd.DataFrame(rows, columns=cols)
        return df
    finally:
        # cerrar de forma “amable” para evitar -501 en algunos fdb
        try:
            cur.close()
        except Exception:
            pass
        try:
            con.commit()   # termina tx limpia
        except Exception:
            pass
        con.close()

# --- SNAPSHOT COMPC01 ---
def snapshot_compc01(secrets, cves: list[str], refers: list[str], f_ini=None, f_fin=None) -> pd.DataFrame:
    """
    Devuelve columnas: TABLA, CVE_PROV, REFER, IMPORTE, FECHA
    Nota: en COMPC01 la clave del proveedor es CVE_CLPV y la referencia es SU_REFER.
    """
    empty_cols = ["TABLA","CVE_PROV","REFER","IMPORTE","FECHA"]
    if not cves or not refers:
        return pd.DataFrame(columns=empty_cols)

    cves_norm   = [_rjust10(x) for x in cves if x]
    refers_norm = [_refer20(x) for x in refers if x]

    if not cves_norm or not refers_norm:
        return pd.DataFrame(columns=empty_cols)

    ph_cve = ",".join(["?"]*len(cves_norm))
    ph_ref = ",".join(["?"]*len(refers_norm))

    sql = f"""
      select 'COMPC01' as TABLA, c.CVE_CLPV as CVE_PROV, upper(c.SU_REFER) as REFER,
             c.IMPORTE, c.FECHA_DOC as FECHA
      from COMPC01 c
      where c.CVE_CLPV in ({ph_cve})
        and upper(c.SU_REFER) in ({ph_ref})
    """
    params = tuple(cves_norm + refers_norm)
    if f_ini and f_fin:
        sql += " and c.FECHA_DOC between ? and ?"
        params += (f_ini, f_fin)

    con = _conn_sae_from_secrets(secrets)
    cur = con.cursor()
    try:
        cur.execute(sql, params)
        cols = [d[0].strip() for d in cur.description]
        rows = cur.fetchall()
        df = pd.DataFrame(rows, columns=cols)
        return df
    finally:
        try:
            cur.close()
        except Exception:
            pass
        try:
            con.commit()
        except Exception:
            pass
        con.close()

def snapshot_paga_por_fecha(secrets, f_ini, f_fin) -> pd.DataFrame:
    """
    Trae TODOS los movimientos de PAGA_M01 dentro del rango [f_ini, f_fin].
    Columnas clave: CVE_PROV, REFER, NUM_CPTO, NUM_CARGO, IMPORTE, FECHA_APLI
    """
    if not f_ini or not f_fin:
        return pd.DataFrame(columns=["CVE_PROV","REFER","NUM_CPTO","NUM_CARGO","IMPORTE","FECHA_APLI"])

    cfg = secrets["FIREBIRD_BIO_SAE"]
    con = fdb.connect(
        host=cfg.get("host","localhost"),
        database=cfg["database"],
        user=cfg["user"],
        password=cfg["password"],
        port=int(cfg.get("port",3050)),
        charset=cfg.get("charset","ISO8859_1"),
    )
    cur = con.cursor()
    try:
        sql = """
            select
                m.CVE_PROV,
                upper(m.REFER) as REFER,
                m.NUM_CPTO,
                m.NUM_CARGO,
                m.IMPORTE,
                m.FECHA_APLI, 
                m.APP_UUID, 
                m.APP_ADA_CFD_DOC
            from PAGA_M01 m
            where m.FECHA_APLI between ? and ?
        """
        cur.execute(sql, (f_ini, f_fin))
        cols = [d[0].strip() for d in cur.description]
        rows = cur.fetchall()
        df = pd.DataFrame(rows, columns=cols)
        # normalizaciones mínimas y seguras
        
        if not df.empty:
            df["CVE_PROV"] = df["CVE_PROV"].astype(str).str.rjust(10).str.slice(0,10)
            df["REFER"]    = df["REFER"].astype(str).str.upper().str.slice(0,20)
        return df
    finally:
        try: cur.close()
        except: pass
        try: con.commit()
        except: pass
        con.close()


def snapshot_compc_por_fecha(secrets, f_ini, f_fin) -> pd.DataFrame:
    """
    Trae TODOS los movimientos de COMPC01 dentro del rango [f_ini, f_fin].
    Columnas clave: CVE_PROV (CVE_CLPV), REFER (SU_REFER), IMPORTE, FECHA_DOC
    """
    if not f_ini or not f_fin:
        return pd.DataFrame(columns=["CVE_PROV","REFER","IMPORTE","FECHA_DOC"])

    cfg = secrets["FIREBIRD_BIO_SAE"]
    con = fdb.connect(
        host=cfg.get("host","localhost"),
        database=cfg["database"],
        user=cfg["user"],
        password=cfg["password"],
        port=int(cfg.get("port",3050)),
        charset=cfg.get("charset","ISO8859_1"),
    )
    cur = con.cursor()
    try:
        sql = """
            select
                c.CVE_CLPV as CVE_PROV,
                upper(c.SU_REFER) as REFER,
                c.IMPORTE,
                c.FECHA_DOC
            from COMPC01 c
            where c.FECHA_DOC between ? and ?
        """
        cur.execute(sql, (f_ini, f_fin))
        cols = [d[0].strip() for d in cur.description]
        rows = cur.fetchall()
        df = pd.DataFrame(rows, columns=cols)
        # normalizaciones mínimas y seguras
        if not df.empty:
            df["CVE_PROV"] = df["CVE_PROV"].astype(str).str.rjust(10).str.slice(0,10)
            df["REFER"]    = df["REFER"].astype(str).str.upper().str.slice(0,20)
        return df
    finally:
        try: cur.close()
        except: pass
        try: con.commit()
        except: pass
        con.close()

def paga_movimientos_con_proveedor(_secrets, f_ini=None, f_fin=None) -> pd.DataFrame:
    con = _conn_sae_from_secrets(_secrets)
    try:
        cur = con.cursor()
        sql = """
          SELECT m.CVE_PROV,
                 p.NOMBRE AS NOMBRE_PROV,
                 COALESCE(m.NO_FACTURA,'') AS NO_FACTURA,
                 COALESCE(m.DOCTO,'')      AS DOCTO,
                 COALESCE(m.REFER,'')      AS REFER,
                 m.FECHA_APLI,
                 m.IMPORTE
          FROM PAGA_M01 m
          LEFT JOIN PROV01 p ON p.CLAVE = m.CVE_PROV
          WHERE m.CVE_PROV <> '0001'
        """
        params = []
        if f_ini and f_fin:
            sql += " AND m.FECHA_APLI BETWEEN ? AND ?"
            params += [f_ini, f_fin]
        cur.execute(sql, tuple(params))
        cols = [d[0].strip() for d in cur.description]
        df = pd.DataFrame(cur.fetchall(), columns=cols)
        # Normaliza tipos aquí
        df["FECHA_APLI"] = pd.to_datetime(df["FECHA_APLI"], errors="coerce")
        df["IMPORTE"] = pd.to_numeric(df["IMPORTE"], errors="coerce").fillna(0.0).round(2)
        for c in ["NO_FACTURA","DOCTO","REFER","NOMBRE_PROV"]:
            df[c] = df[c].astype(str).str.strip().str.upper()
        return df
    finally:
        con.close()


def cargar_vista_paga_prov_cpto(secrets, f_ini=None, f_fin=None) -> pd.DataFrame:
    con = _conn_sae_from_secrets(secrets)
    try:
        sql = """
            SELECT
                CVE_PROV,
                NOMBRE_PROV,
                NUM_CPTO,
                NOMBRE_CPTO,
                CTA_CONT_CPTO,
                REFER,
                CVE_FOLIO,
                DOCTO,
                IMPORTE,          -- ojo: IMPORTE (no IMPOTE)
                NUM_MONED,
                TCAMBIO,
                IMPMON_EXT,
                STATUS_MOV,
                APP_UUID,
                APP_ORIGEN,
                APP_STATUS,
                APP_ADA_CFD_DOC,
                APP_METODO,
                FECHA_APLI
            FROM V_PAGA_M01_PROV_CPTO
            WHERE 1=1 and app_origen = 'OneCore' and cve_prov != '      0001' and APP_STATUS = 'inicial'
        """
        params = []

        # agrega filtros solo si vienen; usa placeholders posicionales (?)
        if f_ini is not None:
            # convierte a date/datetime compatible con FB
            fi = pd.to_datetime(f_ini, errors="coerce")
            if pd.notna(fi):
                sql += " AND FECHA_APLI >= ?"
                params.append(fi.to_pydatetime())
        if f_fin is not None:
            ff = pd.to_datetime(f_fin, errors="coerce")
            if pd.notna(ff):
                sql += " AND FECHA_APLI <= ?"
                params.append(ff.to_pydatetime())

        sql += " ORDER BY FECHA_APLI DESC"

        df = pd.read_sql(sql, con, params=params)
        return df
    finally:
        try:
            con.close()
        except:
            pass

def _refer_sae(serie: Optional[str], folio: Optional[str]) -> str:
    """REFER = SERIE + FOLIO (sin separador), en mayúsculas."""
    s = (serie or "").strip()
    f = (folio or "").strip()
    # CORRECCIÓN: Limitar a 20 caracteres, que es la longitud típica de REFER en SAE.
    return (s + f).upper()[:20]

def buscar_conceptos_en_paga_g03(
            secrets,
            uso_cfdi: str,
            rfc_receptor: str,
            clave_prov_sae: Optional[str],
            serie: Optional[str],
            folio: Optional[str],
            total_mxn: Any,
        ) -> pd.DataFrame:
    """
    Versión robusta para Streamlit.
    Busca el documento en PAGA_M01 con la combinación:
      CVE_PROV = CLAVE_PROV_SAE, REFER = SERIE + FOLIO, NUM_CARGO = 1, NUM_CPTO != 1, IMPORTE = TOTAL_MXN.
    Solo aplica cuando USO_CFDI inicia con 'G03' y RFC_RECEPTOR == 'BIO870307QD0'.
    """
    uso = (uso_cfdi or "").strip().upper()
    rfc_rec = (rfc_receptor or "").strip().upper()

    if not (uso.startswith("G03") and rfc_rec == "BIO870307QD0"):
        return pd.DataFrame(columns=["TABLA","CVE_PROV","REFER","NUM_CPTO","NUM_CARGO","IMPORTE","FECHA_APLI"])

    cve = _clave_prov_normalizada(clave_prov_sae)
    #refer = _refer_sae(serie, folio)
    refer = _refer_concat20(serie, folio)

    try:
        importe = float(str(total_mxn).replace(",", ""))
    except Exception:
        importe = 0.0
    importe = round(importe, 2)

    sql = """
        select
        'PAGA_M01' as TABLA,
        m.CVE_PROV,
        m.REFER,
        m.NUM_CPTO,
        m.NUM_CARGO,
        m.IMPORTE,
        m.FECHA_APLI
        from PAGA_M01 m
        where m.CVE_PROV = ?
        and upper(m.REFER) = upper(?)
        and m.NUM_CARGO = 1
        and m.NUM_CPTO <> 1
        and cast(m.IMPORTE as numeric(15,2)) = cast(? as numeric(15,2))
    """

    #st.write({sql})
    con = _conn_sae_from_secrets(secrets)
    try:
        cur = con.cursor()
        cur.execute(sql, (cve, refer, importe))
        cols = [d[0].strip() for d in cur.description]
        rows = cur.fetchall() # <-- Se trae todos los datos ANTES de cerrar
        return pd.DataFrame(rows, columns=cols)
    finally:
        # Cerrar explícitamente y con manejo de excepción para evitar el -501 si ya se cerró
        try:
            con.close()
        except:
            pass # Ignorar error de cierre si ya estaba cerrada


# --- catálogo clientes (clie01) ---

def buscar_clientes_sae(secrets, q: str = "", limit: int = 500) -> list[dict]:
    """
    regresa lista de clientes activos: [{clave, nombre, rfc}]
    filtro opcional por clave/nombre/rfc
    """
    q = (q or "").strip()
    limit = int(limit or 500)
    if limit <= 0:
        limit = 50

    con = _conn_sae_from_secrets(secrets)
    try:
        cur = con.cursor()

        sql = """
            select 
                c.CLAVE,
                c.NOMBRE,
                c.RFC
            from CLIE01 c
            where c.STATUS <> 'B'
        """.format(limit=limit)

        params = []

        if q:
            # busca por clave, nombre o rfc
            sql += """
              and (
                    upper(c.CLAVE) containing upper(?)
                 or upper(c.NOMBRE) containing upper(?)
                 or upper(c.RFC)   containing upper(?)
              )
            """
            params = [q, q, q]

        sql += " order by c.NOMBRE"

        cur.execute(sql, tuple(params))
        cols = [d[0].strip() for d in cur.description]
        rows = cur.fetchall()

        out = []
        for row in rows:
            d = dict(zip(cols, row))
            out.append({
                "clave": (d.get("CLAVE") or "").strip(),
                "nombre": (d.get("NOMBRE") or "").strip(),
                "rfc": (d.get("RFC") or "").strip(),
            })
        return out
    finally:
        try:
            con.close()
        except Exception:
            pass


def get_clientes_sae_top(secrets, limit: int = 200) -> list[dict]:
    """
    lista rápida (sin filtro) para autocomplete inicial
    """
    return buscar_clientes_sae(secrets, q="", limit=limit)
