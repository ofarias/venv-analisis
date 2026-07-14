from __future__ import annotations

import fdb
import pandas as pd
import streamlit as st

from typing import Optional


def _conn_sae_from_secrets(secrets) -> fdb.Connection:
    cfg = secrets["FIREBIRD_BIO_SAE"]
    return fdb.connect(
        host=cfg.get("host", "localhost"),
        database=cfg["database"],
        user=cfg["user"],
        password=cfg["password"],
        port=int(cfg.get("port", 3050)),
        charset=cfg.get("charset", "ISO8859_1"),
    )


def _df_from_cursor(cur, default_columns: list[str]) -> pd.DataFrame:
    rows = cur.fetchall() or []
    if not rows:
        return pd.DataFrame(columns=default_columns)

    cols = [d[0].strip().lower() for d in cur.description]
    return pd.DataFrame(rows, columns=cols)



def obtener_catalogo_productos_pv_model(limit: int = 10000) -> pd.DataFrame:
    con = _conn_sae_from_secrets(st.secrets)
    try:
        cur = con.cursor()
        cur.execute(
            "select first ? i.cve_art as cve_prod, i.descr "
            "from inve01 i "
            "where coalesce(i.status, 'A') <> 'B' "
            "order by i.cve_art",
            (int(limit),),
        )
        return _df_from_cursor(cur, ["cve_prod", "descr"])
    finally:
        try:
            con.close()
        except Exception:
            pass


def obtener_mapa_cve_original_sae_model() -> pd.DataFrame:
    """Mapa CVE_ORIGINAL -> CVE_PROD desde INVE_CLIB01 (SAE), usado para corregir
    claves de producto importadas de fuentes externas (p.ej. presupuesto de finanzas)."""
    con = _conn_sae_from_secrets(st.secrets)
    try:
        cur = con.cursor()
        cur.execute(
            "select cve_prod, cve_original "
            "from inve_clib01 "
            "where cve_original is not null"
        )
        return _df_from_cursor(cur, ["cve_prod", "cve_original"])
    finally:
        try:
            con.close()
        except Exception:
            pass


def obtener_clientes_sae_model(
    solo_activos: bool = True,
    clave: Optional[str] = None,
    nombre: Optional[str] = None,
    cve_vend: Optional[str] = None,
    limit: int = 5000,
) -> pd.DataFrame:
    con = _conn_sae_from_secrets(st.secrets)
    try:
        cur = con.cursor()

        sql = """
            select first ?
                c.clave,
                c.nombre,
                c.rfc,
                c.cve_vend,
                c.clasific,
                c.status,
                c.emailpred
            from clie01 c
            where 1 = 1
        """
        params: list = [int(limit)]

        if solo_activos:
            sql += " and coalesce(c.status, 'A') <> 'B'"

        if clave:
            sql += " and c.clave = ?"
            params.append(str(clave).strip())

        if nombre:
            sql += " and upper(c.nombre) containing upper(?)"
            params.append(str(nombre).strip())

        if cve_vend:
            sql += " and c.cve_vend = ?"
            params.append(str(cve_vend).strip())

        sql += " order by c.clave"

        cur.execute(sql, tuple(params))
        return _df_from_cursor(
            cur,
            [
                "clave",
                "nombre",
                "rfc",
                "cve_vend",
                "clasific",
                "status",
                "emailpred",
            ],
        )

    finally:
        try:
            con.close()
        except Exception:
            pass


def obtener_lineas_sae_model(
    solo_activas: bool = True,
    cve_lin: Optional[str] = None,
    desc_lin: Optional[str] = None,
    limit: int = 1000,
) -> pd.DataFrame:
    con = _conn_sae_from_secrets(st.secrets)
    try:
        cur = con.cursor()

        sql = """
            select first ?
                l.cve_lin,
                l.desc_lin,
                l.esungpo,
                l.status
            from clin01 l
            where 1 = 1
        """
        params: list = [int(limit)]

        if solo_activas:
            sql += " and coalesce(l.status, 'A') <> 'B'"

        if cve_lin:
            sql += " and l.cve_lin = ?"
            params.append(str(cve_lin).strip())

        if desc_lin:
            sql += " and upper(l.desc_lin) containing upper(?)"
            params.append(str(desc_lin).strip())

        sql += " order by l.cve_lin"

        cur.execute(sql, tuple(params))
        return _df_from_cursor(
            cur,
            [
                "cve_lin",
                "desc_lin",
                "esungpo",
                "status",
            ],
        )

    finally:
        try:
            con.close()
        except Exception:
            pass


def obtener_productos_sae_model(
    solo_activos: bool = True,
    cve_art: Optional[str] = None,
    descr: Optional[str] = None,
    cve_linea: Optional[str] = None,
    limit: int = 5000,
) -> pd.DataFrame:
    con = _conn_sae_from_secrets(st.secrets)
    try:
        cur = con.cursor()

        sql = """
            select first ?
                i.cve_art,
                i.descr,
                i.lin_prod,
                l.desc_lin as linea,
                i.uni_med,
                i.exist,
                i.peso,
                i.tipo_ele,
                i.status
            from inve01 i
            left join clin01 l
                on l.cve_lin = i.lin_prod
            where 1 = 1
        """
        params: list = [int(limit)]

        if solo_activos:
            sql += " and coalesce(i.status, 'A') <> 'B'"

        if cve_art:
            sql += " and i.cve_art = ?"
            params.append(str(cve_art).strip())

        if descr:
            sql += " and upper(i.descr) containing upper(?)"
            params.append(str(descr).strip())

        if cve_linea:
            sql += " and i.lin_prod = ?"
            params.append(str(cve_linea).strip())

        sql += " order by i.cve_art"

        cur.execute(sql, tuple(params))
        return _df_from_cursor(
            cur,
            [
                "cve_art",
                "descr",
                "lin_prod",
                "linea",
                "uni_med",
                "exist",
                "peso",
                "tipo_ele",
                "status",
            ],
        )

    finally:
        try:
            con.close()
        except Exception:
            pass


def obtener_vendedores_sae_model(
    solo_activos: bool = True,
    cve_vend: Optional[str] = None,
    nombre: Optional[str] = None,
    limit: int = 1000,
) -> pd.DataFrame:
    con = _conn_sae_from_secrets(st.secrets)
    try:
        cur = con.cursor()

        sql = """
            select first ?
                v.cve_vend,
                v.nombre,
                v.clasific,
                v.correoe,
                v.status
            from vend01 v
            where 1 = 1
        """
        params: list = [int(limit)]

        if solo_activos:
            sql += " and coalesce(v.status, 'A') <> 'B'"

        if cve_vend:
            sql += " and v.cve_vend = ?"
            params.append(str(cve_vend).strip())

        if nombre:
            sql += " and upper(v.nombre) containing upper(?)"
            params.append(str(nombre).strip())

        sql += " order by v.cve_vend"

        cur.execute(sql, tuple(params))
        return _df_from_cursor(
            cur,
            [
                "cve_vend",
                "nombre",
                "clasific",
                "correoe",
                "status",
            ],
        )

    finally:
        try:
            con.close()
        except Exception:
            pass


def obtener_existencias_productos_sae_model(
    cve_art: Optional[str] = None,
    cve_linea: Optional[str] = None,
    solo_activos: bool = True,
    limit: int = 10000,
) -> pd.DataFrame:
    con = _conn_sae_from_secrets(st.secrets)
    try:
        cur = con.cursor()

        sql = """
            select first ?
                i.cve_art,
                i.descr,
                i.lin_prod,
                l.desc_lin as linea,
                i.uni_med,
                coalesce(i.exist, 0) as existencia,
                coalesce(i.peso, 0) as peso,
                coalesce(i.costo_prom, 0) as costo_prom,
                coalesce(i.ult_costo, 0) as ult_costo,
                i.status
            from inve01 i
            left join clin01 l
                on l.cve_lin = i.lin_prod
            where 1 = 1
        """
        params: list = [int(limit)]

        if solo_activos:
            sql += " and coalesce(i.status, 'A') <> 'B'"

        if cve_art:
            sql += " and i.cve_art = ?"
            params.append(str(cve_art).strip())

        if cve_linea:
            sql += " and i.lin_prod = ?"
            params.append(str(cve_linea).strip())

        sql += " order by i.cve_art"

        cur.execute(sql, tuple(params))
        return _df_from_cursor(
            cur,
            [
                "cve_art",
                "descr",
                "lin_prod",
                "linea",
                "uni_med",
                "existencia",
                "peso",
                "costo_prom",
                "ult_costo",
                "status",
            ],
        )

    finally:
        try:
            con.close()
        except Exception:
            pass


def obtener_ventas_reales_sae_model(
    anio: Optional[int] = None,
    mes: Optional[int] = None,
    fecha_inicio: Optional[str] = None,
    fecha_fin: Optional[str] = None,
    cve_clie: Optional[str] = None,
    cve_vend: Optional[str] = None,
    cve_art: Optional[str] = None,
    num_alm: Optional[int] = None,
) -> pd.DataFrame:
    con = _conn_sae_from_secrets(st.secrets)
    try:
        cur = con.cursor()

        sql = """
            select
                extract(year from f.fecha_doc) as anio,
                extract(month from f.fecha_doc) as mes,
                cast(f.fecha_doc as date) as fecha,
                f.cve_doc,
                f.cve_clpv as cve_clie,
                c.nombre as cliente,
                f.cve_vend,
                v.nombre as vendedor,
                p.cve_art,
                i.descr as producto,
                i.lin_prod,
                l.desc_lin as linea,
                coalesce(p.num_alm, f.num_alma) as num_alm,
                coalesce(p.uni_venta, i.uni_med) as unidad,
                sum(coalesce(p.cant, 0)) as cantidad,
                avg(coalesce(p.prec, 0)) as precio_promedio,
                sum(coalesce(p.tot_partida, 0)) as importe
            from factf01 f
            join par_factf01 p
                on p.cve_doc = f.cve_doc
            left join clie01 c
                on c.clave = f.cve_clpv
            left join vend01 v
                on v.cve_vend = f.cve_vend
            left join inve01 i
                on i.cve_art = p.cve_art
            left join clin01 l
                on l.cve_lin = i.lin_prod
            where 1 = 1
              and coalesce(f.status, '') <> 'C'
        """
        params: list = []

        if anio is not None:
            sql += " and extract(year from f.fecha_doc) = ?"
            params.append(int(anio))

        if mes is not None:
            sql += " and extract(month from f.fecha_doc) = ?"
            params.append(int(mes))

        if fecha_inicio:
            sql += " and cast(f.fecha_doc as date) >= ?"
            params.append(fecha_inicio)

        if fecha_fin:
            sql += " and cast(f.fecha_doc as date) <= ?"
            params.append(fecha_fin)

        if cve_clie:
            sql += " and f.cve_clpv = ?"
            params.append(str(cve_clie).strip())

        if cve_vend:
            sql += " and f.cve_vend = ?"
            params.append(str(cve_vend).strip())

        if cve_art:
            sql += " and p.cve_art = ?"
            params.append(str(cve_art).strip())

        if num_alm is not None:
            sql += " and coalesce(p.num_alm, f.num_alma) = ?"
            params.append(int(num_alm))

        sql += """
            group by
                extract(year from f.fecha_doc),
                extract(month from f.fecha_doc),
                cast(f.fecha_doc as date),
                f.cve_doc,
                f.cve_clpv,
                c.nombre,
                f.cve_vend,
                v.nombre,
                p.cve_art,
                i.descr,
                i.lin_prod,
                l.desc_lin,
                coalesce(p.num_alm, f.num_alma),
                coalesce(p.uni_venta, i.uni_med)
            order by
                anio desc,
                mes desc,
                fecha desc,
                f.cve_doc desc
        """

        cur.execute(sql, tuple(params))
        return _df_from_cursor(
            cur,
            [
                "anio",
                "mes",
                "fecha",
                "cve_doc",
                "cve_clie",
                "cliente",
                "cve_vend",
                "vendedor",
                "cve_art",
                "producto",
                "lin_prod",
                "linea",
                "num_alm",
                "unidad",
                "cantidad",
                "precio_promedio",
                "importe",
            ],
        )

    finally:
        try:
            con.close()
        except Exception:
            pass


def obtener_ventas_reales_resumen_sae_model(
    anio: Optional[int] = None,
    mes: Optional[int] = None,
    fecha_inicio: Optional[str] = None,
    fecha_fin: Optional[str] = None,
    cve_clie: Optional[str] = None,
    cve_vend: Optional[str] = None,
    cve_art: Optional[str] = None,
    num_alm: Optional[int] = None,
) -> pd.DataFrame:
    con = _conn_sae_from_secrets(st.secrets)
    try:
        cur = con.cursor()

        sql = """
            select
                extract(year from f.fecha_doc) as anio,
                extract(month from f.fecha_doc) as mes,
                f.cve_clpv as cve_clie,
                c.nombre as cliente,
                f.cve_vend,
                v.nombre as vendedor,
                p.cve_art,
                i.descr as producto,
                i.lin_prod,
                l.desc_lin as linea,
                coalesce(p.num_alm, f.num_alma) as num_alm,
                sum(coalesce(p.cant, 0)) as cantidad,
                avg(coalesce(p.prec, 0)) as precio_promedio,
                sum(coalesce(p.tot_partida, 0)) as importe
            from factf01 f
            join par_factf01 p
                on p.cve_doc = f.cve_doc
            left join clie01 c
                on c.clave = f.cve_clpv
            left join vend01 v
                on v.cve_vend = f.cve_vend
            left join inve01 i
                on i.cve_art = p.cve_art
            left join clin01 l
                on l.cve_lin = i.lin_prod
            where 1 = 1
              and coalesce(f.status, '') <> 'C'
        """
        params: list = []

        if anio is not None:
            sql += " and extract(year from f.fecha_doc) = ?"
            params.append(int(anio))

        if mes is not None:
            sql += " and extract(month from f.fecha_doc) = ?"
            params.append(int(mes))

        if fecha_inicio:
            sql += " and cast(f.fecha_doc as date) >= ?"
            params.append(fecha_inicio)

        if fecha_fin:
            sql += " and cast(f.fecha_doc as date) <= ?"
            params.append(fecha_fin)

        if cve_clie:
            sql += " and f.cve_clpv = ?"
            params.append(str(cve_clie).strip())

        if cve_vend:
            sql += " and f.cve_vend = ?"
            params.append(str(cve_vend).strip())

        if cve_art:
            sql += " and p.cve_art = ?"
            params.append(str(cve_art).strip())

        if num_alm is not None:
            sql += " and coalesce(p.num_alm, f.num_alma) = ?"
            params.append(int(num_alm))

        sql += """
            group by
                extract(year from f.fecha_doc),
                extract(month from f.fecha_doc),
                f.cve_clpv,
                c.nombre,
                f.cve_vend,
                v.nombre,
                p.cve_art,
                i.descr,
                i.lin_prod,
                l.desc_lin,
                coalesce(p.num_alm, f.num_alma)
            order by
                anio desc,
                mes desc,
                cliente,
                producto
        """

        cur.execute(sql, tuple(params))
        return _df_from_cursor(
            cur,
            [
                "anio",
                "mes",
                "cve_clie",
                "cliente",
                "cve_vend",
                "vendedor",
                "cve_art",
                "producto",
                "lin_prod",
                "linea",
                "num_alm",
                "cantidad",
                "precio_promedio",
                "importe",
            ],
        )

    finally:
        try:
            con.close()
        except Exception:
            pass