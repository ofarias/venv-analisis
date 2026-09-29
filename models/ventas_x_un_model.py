# models/ventas_x_un_model.py
"""Reporte "Ventas por Unidad de Negocio" — migrado del PHP legado
(index.php?action=vxun, pegaso.controller.php::RepVentasUN,
pegaso.model.php::RVCU/TotalRV/un). Mismas tablas de SAE (FACTF01,
PAR_FACTF01, CLIE01, INVE01, CLIN01) que ya consulta el resto de esta app
por Firebird, pero en una sola consulta para todas las unidades de negocio
en vez de un query por unidad en un loop — el agrupamiento y los subtotales
por unidad/cliente/factura se resuelven en la vista con AgGrid en vez de
las filas literales "Total documento"/"Total por cliente" del PHP."""
from __future__ import annotations

from datetime import date
from typing import Optional

import fdb
import pandas as pd
import streamlit as st


def _conn_sae() -> fdb.Connection:
    cfg = st.secrets["FIREBIRD_BIO_SAE"]
    return fdb.connect(
        host=cfg.get("host", "localhost"),
        database=cfg["database"],
        user=cfg["user"],
        password=cfg["password"],
        port=int(cfg.get("port", 3050)),
        charset=cfg.get("charset", "ISO8859_1"),
    )


def _df_from_cursor(cur) -> pd.DataFrame:
    rows = cur.fetchall() or []
    cols = [d[0].strip().lower() for d in cur.description]
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows, columns=cols)


def obtener_ventas_x_un_model(
    fecha_desde: date,
    fecha_hasta: date,
    cve_vend: Optional[str | list[str]] = None,
) -> pd.DataFrame:
    """Detalle de partidas facturadas (activas, status != 'C') entre
    fecha_desde y fecha_hasta (sobre FECHA_DOC), con la Unidad de Negocio
    de cada partida (INVE01.LIN_PROD / CLIN01.DESC_LIN) y el cliente/
    factura a los que pertenece — para agrupar y sumar en la vista."""
    con = _conn_sae()
    try:
        cur = con.cursor()
        sql = """
            select
                a.fecha_doc as fecha_factura,
                a.fechaelab as elaborada_el,
                a.cve_doc as factura,
                a.doc_ant as remision,
                a.status as estado,
                a.cve_vend as cve_vend,
                a.cve_clpv as clave_cliente,
                b.nombre as nombre_cliente,
                c.cve_art as clave_articulo,
                d.descr as producto,
                d.lin_prod as un,
                coalesce(l.desc_lin, d.lin_prod) as un_desc,
                f.lote as lote,
                iif(e.cantidad is null, c.cant, e.cantidad) as cantidad,
                c.prec as precio_mn,
                a.num_moned as moneda,
                a.tipcamb as tc,
                ((iif(e.cantidad is null, c.cant, e.cantidad) * c.prec) / nullif(a.tipcamb, 0)) as precio_usd,
                (c.tot_partida * (iif(e.cantidad is null, c.cant, e.cantidad) / c.cant)) as subtotal,
                (c.totimp4 * (iif(e.cantidad is null, c.cant, e.cantidad) / c.cant)) as iva,
                ((c.tot_partida * (iif(e.cantidad is null, c.cant, e.cantidad) / c.cant))
                    + (c.totimp4 * (iif(e.cantidad is null, c.cant, e.cantidad) / c.cant))) as total,
                f.pedimento as pedimento,
                c.num_par as partida
            from factf01 a
            left join clie01 b on a.cve_clpv = b.clave
            left join par_factf01 c on a.cve_doc = c.cve_doc
            left join inve01 d on c.cve_art = d.cve_art
            left join clin01 l on l.cve_lin = d.lin_prod
            left join enlace_ltpd01 e on e.e_ltpd = c.e_ltpd
            left join ltpd01 f on e.reg_ltpd = f.reg_ltpd
            where cast(a.fecha_doc as date) between ? and ?
              and coalesce(a.status, '') <> 'C'
        """
        params: list = [fecha_desde, fecha_hasta]

        if cve_vend:
            # CVE_VEND es CHAR de ancho fijo en SAE (viene con espacios a la
            # izquierda, ej. '    1') — hay que comparar con TRIM() o nunca
            # va a hacer match contra el valor ya limpio que se le pasa aquí
            lista = [cve_vend] if isinstance(cve_vend, str) else list(cve_vend)
            lista = [str(v).strip() for v in lista if str(v or "").strip()]
            if lista:
                placeholders = ", ".join(["?"] * len(lista))
                sql += f" and trim(a.cve_vend) in ({placeholders})"
                params.extend(lista)

        sql += " order by b.clave, a.cve_doc desc, d.lin_prod"

        cur.execute(sql, tuple(params))
        return _df_from_cursor(cur)
    finally:
        try:
            con.close()
        except Exception:
            pass
