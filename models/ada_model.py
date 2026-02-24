# models/ada_model.py
import fdb
import pandas as pd
from typing import Optional, Tuple, Dict, Any, List
from datetime import date

def _conn_from_secrets(secrets) -> fdb.Connection:
    cfg = secrets["FIREBIRD_BIO_ADA"]
    return fdb.connect(
        host=cfg.get("host", "localhost"),
        database=cfg["database"],
        user=cfg["user"],
        password=cfg["password"],
        port=int(cfg.get("port", 3050)),
        charset=cfg.get("charset", "ISO8859_1"),
    )

def obtener_tipos_distintos(secrets) -> List[str]:
    sql = "select distinct TIPOCOMPROBANTE from DATOSCFD where TIPOCOMPROBANTE is not null order by TIPOCOMPROBANTE"
    con = _conn_from_secrets(secrets)
    try:
        cur = con.cursor()
        cur.execute(sql)
        return [r[0] for r in cur.fetchall()]
    finally:
        con.close()

def contar_documentos(secrets, filtros):
    where, params = [], []

    if filtros.get("fecha_desde"):
        where.append("FECHA_EMISION >= cast(? as date)")
        params.append(str(filtros["fecha_desde"]))
    if filtros.get("fecha_hasta"):
        where.append("FECHA_EMISION < cast(? as date) + 1")
        params.append(str(filtros["fecha_hasta"]))
    
    if filtros.get("rfc_emisor"):
        where.append("upper(c.RFC_EMISOR) like '%' || upper(?) || '%'")
        params.append(filtros["rfc_emisor"][:13])

    # NOMBRE_EMISOR
    if filtros.get("nombre_emisor"):
        where.append("upper(c.NOMBRE_EMISOR) like '%' || upper(?) || '%'")
        params.append(filtros["nombre_emisor"][:120])

    # FOLIO
    if filtros.get("folio"):
        where.append("c.FOLIO like '%' || ? || '%'")
        params.append(filtros["folio"][:20])

    # TIPO
    if filtros.get("tipo"):
        where.append("upper(c.TIPOCOMPROBANTE) = upper(?)")
        params.append(filtros["tipo"][:20])  # por si acaso

    # RFC_RECEPTOR
    if filtros.get("rfc_receptor"):
        where.append("upper(c.RFC_RECEPTOR) like '%' || upper(?) || '%'")
        params.append(filtros["rfc_receptor"][:13])
    

    where_sql = (" where " + " and ".join(where)) if where else ""
    sql = f"select count(*) from DATOSCFD C{where_sql}"

    con = _conn_from_secrets(secrets)
    cur = con.cursor()
    cur.execute(sql, tuple(params))
    row = cur.fetchone()
    cur.close()
    con.close()
    return int(row[0]) if row else 0


def buscar_documentos(secrets, filtros, paginacion):
    where, params = [], []

    if filtros.get("fecha_desde"):
        where.append("c.FECHA_EMISION >= cast(? as date)")
        params.append(str(filtros["fecha_desde"]))
    if filtros.get("fecha_hasta"):
        where.append("c.FECHA_EMISION < cast(? as date) + 1")
        params.append(str(filtros["fecha_hasta"]))

    if filtros.get("rfc_emisor"):
        where.append("upper(c.RFC_EMISOR) like '%' || upper(?) || '%'")
        params.append(filtros["rfc_emisor"][:13])

    # NOMBRE_EMISOR
    if filtros.get("nombre_emisor"):
        where.append("upper(c.NOMBRE_EMISOR) like '%' || upper(?) || '%'")
        params.append(filtros["nombre_emisor"][:120])

    # FOLIO
    if filtros.get("folio"):
        where.append("c.FOLIO like '%' || ? || '%'")
        params.append(filtros["folio"][:20])

    # TIPO
    if filtros.get("tipo"):
        where.append("upper(c.TIPOCOMPROBANTE) = upper(?)")
        params.append(filtros["tipo"][:20])  # por si acaso

    # RFC_RECEPTOR
    if filtros.get("rfc_receptor"):
        where.append("upper(c.RFC_RECEPTOR) like '%' || upper(?) || '%'")
        params.append(filtros["rfc_receptor"][:13])
    
    where_sql = (" where " + " and ".join(where)) if where else ""
    offset, limit = paginacion

    sql = f"""
    select first {int(limit)} skip {int(offset)}
      c.ID_DOCTODIG,
      c.FECHA_EMISION,
      c.UUID,
      c.TIPOCOMPROBANTE,
      c.SERIE,
      c.FOLIO,
      c.RFC_EMISOR,
      c.NOMBRE_EMISOR,
      c.RFC_RECEPTOR,
      c.NOMBRE_RECEPTOR,
      c.MONEDA,
      c.TIPOCAMBIO,
      c.TOTAL,
      c.TOTAL * c.TIPOCAMBIO as TOTAL_MXN,
      c.ESTADO_SAT,
      c.ESTADO_CFD,
      c.FECHA_TIMBRADO,
      c.FECHA_CANCELACION, 
      c.usocfdi_ ||' - '|| c.USOCFDI as uso_cfdi,
      c.usocfdi_
    from DATOSCFD c
    {where_sql} 
    and total > 0
    order by c.FECHA_EMISION desc, c.ID_DOCTODIG desc
    """

    con = _conn_from_secrets(secrets)
    cur = con.cursor()
    cur.execute(sql, tuple(params))
    cols = [d[0].strip() for d in cur.description]
    rows = cur.fetchall()
    cur.close()
    con.close()

    import pandas as pd
    return pd.DataFrame(rows, columns=cols)


def obtener_detalle_documento(_secrets, id_docto_dig: int, uuid: str | None = None) -> dict | None:
    sql = "SELECT * FROM DATOSCFD WHERE ID_DOCTODIG = ? and UUID = ?"
    con = _conn_from_secrets(_secrets)
    try:
        cur = con.cursor()
        cur.execute(sql, (int(id_docto_dig), uuid))
        row = cur.fetchone()
        if not row:
            return None
        cols = [d[0].strip() for d in cur.description]
        return dict(zip(cols, row))
    finally:
        con.close()

def obtener_conceptos_por_documento(secrets, id_docto_dig: int):
    """
    Devuelve los conceptos (detalles de productos o servicios) asociados a un CFDI.
    Tabla: CONCEPTOS
    Relación: CONCEPTOS.ID_DOCTODIG = DATOSCFD.ID_DOCTODIG
    """
    sql = """
        SELECT
            ID_DOCTODIG,
            CLAVEPRODSERV,
            NO_IDENTIFICACION,
            CANTIDAD,
            CLAVEUNIDAD,
            UNIDAD,
            DESCRIPCION,
            VALORUNITARIO,
            DESCUENTO,
            IMPORTE,
            OBJETOIMP,
            BASE_IVA,
            IVA,
            IEPS,
            IVA_RET,
            IEPS_RET,
            ISR
        FROM CONCEPTOS
        WHERE ID_DOCTODIG = ?
        ORDER BY ID_DOCTODIG
    """

    con = _conn_from_secrets(secrets)
    try:
        cur = con.cursor()
        cur.execute(sql, (int(id_docto_dig),))
        rows = cur.fetchall()
        cols = [d[0].strip() for d in cur.description]
        df = pd.DataFrame(rows, columns=cols)
        return df
    finally:
        con.close()

def obtener_conceptos_filtrados(secrets, proveedor: str | None = None, meses: list | None = None, anio: int | None = None):
    """
    Devuelve los conceptos fiscales (CONCEPTOS + DATOSCFD)
    filtrados por proveedor (nombre o RFC), meses y año.
    Si no se pasa filtro → devuelve mes actual + anterior del año en curso.
    """
    hoy = date.today()
    mes_actual = hoy.month
    mes_anterior = 12 if mes_actual == 1 else mes_actual - 1
    anio_actual = hoy.year
    anio_anterior = hoy.year - 1 if mes_actual == 1 else hoy.year

    where, params = [], []

    if proveedor:
        proveedor = proveedor.replace("'", "").replace('"', "").strip()

    if proveedor:
        proveedor_limpio = proveedor.strip()
        where.append("upper(d.NOMBRE_EMISOR || ' ' || d.RFC_EMISOR) like '%' || upper(?) || '%'")
        params.append(proveedor_limpio)

    # Filtro por meses
    if meses and len(meses) > 0:
        placeholders = ",".join(["?"] * len(meses))
        where.append(f"extract(month from d.FECHA_EMISION) in ({placeholders})")
        params += [int(m) for m in meses]
        if anio:
            where.append("extract(year from d.FECHA_EMISION) = ?")
            params.append(int(anio))
    else:
        # por defecto: mes actual y anterior
        where.append(
            "( (extract(month from d.FECHA_EMISION) = ? and extract(year from d.FECHA_EMISION) = ?) "
            "or (extract(month from d.FECHA_EMISION) = ? and extract(year from d.FECHA_EMISION) = ?) )"
        )
        params += [mes_actual, anio_actual, mes_anterior, anio_anterior]

    where_sql = "WHERE " + " AND ".join(where) if where else ""

    sql = f"""
        SELECT
            d.FECHA_EMISION,
            d.RFC_EMISOR,
            d.NOMBRE_EMISOR || ' (' || d.RFC_EMISOR || ')' AS PROVEEDOR,
            d.SERIE,
            d.FOLIO,
            c.ID_DOCTODIG,
            c.CLAVEPRODSERV,
            c.NO_IDENTIFICACION,
            c.CANTIDAD,
            c.CLAVEUNIDAD,
            c.UNIDAD,
            c.DESCRIPCION,
            c.VALORUNITARIO,
            c.DESCUENTO,
            c.IMPORTE,
            c.OBJETOIMP,
            c.BASE_IVA,
            c.IVA,
            c.IEPS,
            c.IVA_RET,
            c.IEPS_RET,
            c.ISR
        FROM CONCEPTOS c
        JOIN DATOSCFD d ON c.ID_DOCTODIG = d.ID_DOCTODIG
        {where_sql}
        ORDER BY d.FECHA_EMISION DESC
    """

    con = _conn_from_secrets(secrets)
    try:
        cur = con.cursor()
        cur.execute(sql, tuple(params))
        rows = cur.fetchall()
        cols = [d[0].strip() for d in cur.description]
        df = pd.DataFrame(rows, columns=cols)
        return df
    except Exception as e:
        raise e
    finally:
        if 'cur' in locals():
            try:
                cur.close()
            except Exception:
                pass
        try:
            con.close()
        except Exception:
            pass

def obtener_datoscfd_por_uuid(secrets, uuid: str) -> dict | None:
    uuid = ("" if uuid is None else str(uuid)).strip().upper()
    if not uuid:
        return None

    sql = "SELECT * FROM DATOSCFD WHERE UPPER(UUID) = ? ROWS 1"
    con = _conn_from_secrets(secrets)
    try:
        cur = con.cursor()
        cur.execute(sql, (uuid,))
        row = cur.fetchone()
        if not row:
            return None
        cols = [d[0].strip() for d in cur.description]
        return dict(zip(cols, row))
    finally:
        try:
            con.close()
        except Exception:
            pass
        