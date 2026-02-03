# models/ventas_model.py
from typing import Optional, List, Any, Dict
import pandas as pd
from models.db import run_query_firebird  # mismo helper que ya usas

def get_ventas_df(
    fecha_desde: Optional[str] = None,
    fecha_hasta: Optional[str] = None,
    cliente: Optional[str] = None,     # CLAVE del cliente
    vendedor: Optional[int] = None,    # NUM_VEND
    moneda: Optional[int] = None,      # NUM_MONED
    status: Optional[str] = "A"        # 'A' activas; ajusta a tu catálogo si difiere
) -> pd.DataFrame:
    """
    Retorna partidas de factura con contexto de cliente/vendedor/moneda.
    Ajusta nombres si tu esquema difiere.
    """

    where = ["1=1"]
    params: List[Any] = []

    # FACTF01.FCH_ENTRE es frecuente; usa el campo de fecha que manejen como "fecha de la venta"
    # También puede ser FECHA_DOC; ajusta si aplica.
    if fecha_desde:
        where.append("CAST(f.FECHA_DOC AS DATE) >= CAST(? AS DATE)")
        params.append(fecha_desde)
    if fecha_hasta:
        where.append("CAST(f.FECHA_DOC AS DATE) <= CAST(? AS DATE)")
        params.append(fecha_hasta)
    if cliente:
        where.append("f.CVE_CLPV = ?")
        params.append(cliente)
    if vendedor is not None:
        where.append("f.CVE_VEND = ?")
        params.append(int(vendedor))
    if moneda is not None:
        where.append("f.NUM_MONED = ?")
        params.append(int(moneda))
    if status:
        where.append("f.STATUS = ?")
        params.append(status)

    # NOTA: campos típicos en SAE; si alguno cambia, ajusta los SELECT/JOINS.
    sql = f"""
      SELECT
        f.CVE_DOC,
        f.FECHA_DOC,
        f.CVE_CLPV,
        c.NOMBRE      AS CLIENTE,
        f.CVE_VEND,
        v.NOMBRE      AS VENDEDOR,
        f.NUM_MONED,
        m.DESCR       AS MONEDA,
        p.TIP_CAM    AS TCAMBIO,
        p.NUM_PAR,
        p.CVE_ART,
        p.CANT        AS CANTIDAD,
        p.PREC        AS PRECIO,
        p.COST        AS COSTO,
        (p.CANT * p.PREC) AS IMPORTE
      FROM PAR_FACTF01 p
      JOIN FACTF01     f ON f.CVE_DOC   = p.CVE_DOC
      LEFT JOIN CLIE01 c ON c.CLAVE     = f.CVE_CLPV
      LEFT JOIN VEND01 v ON v.CVE_VEND  = f.CVE_VEND
      LEFT JOIN MONED01 m ON m.NUM_MONED = f.NUM_MONED
      -- WHERE {" AND ".join(where)}
    """

    rows = run_query_firebird("FIREBIRD_BIO_SAE", sql, params)  # tu conexión
    if not rows:
        return pd.DataFrame()

    if isinstance(rows[0], dict):
        df = pd.DataFrame(rows)
    else:
        cols = [
            "CVE_DOC","FECHA_DOC","CVE_CLPV","CLIENTE",
            "CVE_VEND","VENDEDOR","NUM_MONED","MONEDA","TCAMBIO",
            "NUM_PAR","CVE_ART","CANTIDAD","PRECIO","COSTO","IMPORTE"
        ]
        df = pd.DataFrame(rows, columns=cols)

    # Normalizaciones
    df["FECHA_DOC"] = pd.to_datetime(df["FECHA_DOC"], errors="coerce")
    for col in ["CANTIDAD","PRECIO","COSTO","IMPORTE","TCAMBIO"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    # Importe MN (si moneda != 1, multiplica por TC)
    df["IMPORTE_MN"] = df.apply(
        lambda r: r["IMPORTE"] if int(r.get("NUM_MONED",1)) == 1 else r["IMPORTE"] * (r["TCAMBIO"] or 1.0),
        axis=1
    )
    # Margen y % margen (si COSTO existe)
    df["COSTO_MN"] = df.apply(
        lambda r: r["COSTO"]*r["CANTIDAD"] if int(r.get("NUM_MONED",1)) == 1 else (r["COSTO"]*r["CANTIDAD"])*(r["TCAMBIO"] or 1.0),
        axis=1
    )
    df["UTILIDAD_MN"] = df["IMPORTE_MN"] - df["COSTO_MN"]
    df["MARGEN_PCT"]  = df.apply(lambda r: (r["UTILIDAD_MN"]/r["IMPORTE_MN"]*100) if r["IMPORTE_MN"] else 0.0, axis=1)

    df["ANIO"] = df["FECHA_DOC"].dt.year
    df["MES"]  = df["FECHA_DOC"].dt.month
    return df