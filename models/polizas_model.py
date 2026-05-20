# models/polizas_model.py

import pandas as pd
from models.db import run_query_firebird

CONN_COI = "FIREBIRD_COI_PC"
CONN_SAT = "FIREBIRD_sat2app"


def _to_df(data) -> pd.DataFrame:
    if data is None:
        return pd.DataFrame()

    if isinstance(data, pd.DataFrame):
        return data

    if isinstance(data, list):
        return pd.DataFrame(data)

    return pd.DataFrame()

def obtener_xml_resumen_mes_anio(cliente: str) -> pd.DataFrame:
    sql = """
        SELECT
            EXTRACT(YEAR FROM x.FECHA) AS ANIO,
            EXTRACT(MONTH FROM x.FECHA) AS MES,
            COUNT(*) AS TOTAL_XML,
            SUM(x.IMPORTE) AS TOTAL_IMPORTE
        FROM XML_DATA x
        WHERE COALESCE(TRIM(x.CLIENTE), '') <> ?
        AND COALESCE(TRIM(x.TIPO), '') = 'I'
        GROUP BY
            EXTRACT(YEAR FROM x.FECHA),
            EXTRACT(MONTH FROM x.FECHA)
        ORDER BY
            ANIO,
            MES
    """
    return run_query_firebird(CONN_SAT, sql, (cliente,))


def obtener_xml_con_poliza(cliente: str) -> pd.DataFrame:
    sql_xml = """
        SELECT
            x.UUID,
            x.CLIENTE,
            x.FECHA,
            x.SERIE,
            x.FOLIO,
            x.SUBTOTAL,
            x.IVA,
            x.IMPORTE,
            x.TIPO,
            x.STATUS,
            x.MONEDA,
            x.TIPOCAMBIO,
            x.DOCUMENTO,
            CASE
                WHEN COALESCE(x.TIPOCAMBIO, 0) > 0 THEN x.IMPORTE * x.TIPOCAMBIO
                ELSE x.IMPORTE
            END AS IMPORTE_MXN
        FROM XML_DATA x
        WHERE COALESCE(TRIM(x.CLIENTE), '') <> ?
        AND COALESCE(TRIM(x.TIPO), '') = 'I'
        AND x.FECHA >= '2025-01-01'
    """
    df_xml = _to_df(run_query_firebird(CONN_SAT, sql_xml, (cliente,)))

    sql_polizas = """
        SELECT
            p.UUID,
            p.TIPO_POLI,
            p.NUM_POLIZ,
            p.PERIODO,
            p.EJERCICIO,
            p.FECHA_POL,
            p.CONCEP_PO
        FROM POLIZAS25 p
        WHERE p.UUID IS NOT NULL
          AND TRIM(p.UUID) <> ''
    """

    df_polizas = _to_df(run_query_firebird(CONN_COI, sql_polizas, ()))

    if df_xml.empty:
        return df_xml

    if df_polizas.empty:
        df_xml["TIENE_POLIZA"] = "NO"
        return df_xml

    df_xml["UUID"] = df_xml["UUID"].astype(str).str.upper().str.strip()
    df_polizas["UUID"] = df_polizas["UUID"].astype(str).str.upper().str.strip()

    df = df_xml.merge(
        df_polizas,
        on="UUID",
        how="left"
    )

    df["TIENE_POLIZA"] = df["NUM_POLIZ"].apply(
        lambda x: "SI" if pd.notna(x) and str(x).strip() != "" else "NO"
    )

    return df




def obtener_resumen_polizas(
    ejercicio: int,
    periodo: int,
    tipo_poliza: str | None = None,
) -> pd.DataFrame:

    params = [ejercicio, periodo]

    filtro_tipo = ""
    if tipo_poliza and tipo_poliza != "Todos":
        filtro_tipo = " AND p.TIPO_POLI = ? "
        params.append(tipo_poliza)

    sql = f"""
        SELECT
            p.TIPO_POLI,
            p.NUM_POLIZ,
            p.PERIODO,
            p.EJERCICIO,
            p.FECHA_POL,
            p.CONCEP_PO,
            SUM(CASE WHEN a.DEBE_HABER = 'D' THEN a.MONTOMOV ELSE 0 END) AS CARGOS,
            SUM(CASE WHEN a.DEBE_HABER = 'H' THEN a.MONTOMOV ELSE 0 END) AS ABONOS,
            SUM(CASE WHEN a.DEBE_HABER = 'D' THEN a.MONTOMOV ELSE 0 END)
            -
            SUM(CASE WHEN a.DEBE_HABER = 'H' THEN a.MONTOMOV ELSE 0 END) AS DIFERENCIA
        FROM POLIZAS25 p
        LEFT JOIN AUXILIAR25 a
            ON  a.TIPO_POLI = p.TIPO_POLI
            AND a.NUM_POLIZ = p.NUM_POLIZ
            AND a.PERIODO = p.PERIODO
            AND a.EJERCICIO = p.EJERCICIO
        WHERE p.EJERCICIO = ?
          AND p.PERIODO = ?
          {filtro_tipo}
        GROUP BY
            p.TIPO_POLI,
            p.NUM_POLIZ,
            p.PERIODO,
            p.EJERCICIO,
            p.FECHA_POL,
            p.CONCEP_PO
        ORDER BY
            p.TIPO_POLI,
            p.NUM_POLIZ
    """

    return run_query_firebird(CONN_COI, sql, tuple(params))


def obtener_detalle_poliza(
    ejercicio: int,
    periodo: int,
    tipo_poliza: str,
    num_poliz: str,
) -> pd.DataFrame:

    sql = """
        SELECT
            a.TIPO_POLI,
            a.NUM_POLIZ,
            a.NUM_PART,
            a.PERIODO,
            a.EJERCICIO,
            a.NUM_CTA,
            c.NOMBRE AS NOMBRE_CUENTA,
            a.CONCEPTO,
            a.DEBE_HABER,
            a.MONTOMOV
        FROM AUXILIAR25 a
        LEFT JOIN CUENTAS25 c
            ON c.NUM_CTA = a.NUM_CTA
        WHERE a.EJERCICIO = ?
          AND a.PERIODO = ?
          AND a.TIPO_POLI = ?
          AND a.NUM_POLIZ = ?
        ORDER BY
            a.NUM_PART
    """

    params = (
        ejercicio,
        periodo,
        tipo_poliza,
        num_poliz,
    )

    return run_query_firebird(CONN_COI, sql, params)