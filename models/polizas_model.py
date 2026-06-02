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
            a.CONCEP_PO,
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


def obtener_xml_con_poliza_gastos(
    cliente: str,
    anio: int | None = None,
) -> pd.DataFrame:
    params = [cliente]

    filtro_anio = ""
    if anio:
        filtro_anio = " AND EXTRACT(YEAR FROM x.FECHA) = ? "
        params.append(int(anio))

    sql_xml = f"""
        SELECT
            x.UUID,
            x.CLIENTE,
            x.RFCE,
            x.FECHA,
            x.SERIE,
            x.FOLIO,
            x.SUBTOTAL,
            x.IVA,
            x.IMPORTE,
            x.MONEDA,
            x.TIPOCAMBIO,
            CASE
                WHEN COALESCE(x.TIPOCAMBIO, 0) > 0 THEN x.IMPORTE * x.TIPOCAMBIO
                ELSE x.IMPORTE
            END AS IMPORTE_MXN,
            x.TIPO,
            x.STATUS,
            x.DOCUMENTO
        FROM XML_DATA x
        WHERE COALESCE(TRIM(x.CLIENTE), '') = ?
          AND COALESCE(TRIM(x.TIPO), '') = 'I'
          {filtro_anio}
    """

    df_xml = _to_df(
        run_query_firebird(CONN_SAT, sql_xml, tuple(params))
    )

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

    df_polizas = _to_df(
        run_query_firebird(CONN_COI, sql_polizas, ())
    )

    if df_xml.empty:
        return df_xml

    if df_polizas.empty:
        df_xml["TIENE_POLIZA"] = "NO"
        return df_xml

    df_xml["UUID"] = (
        df_xml["UUID"]
        .astype(str)
        .str.upper()
        .str.strip()
    )

    df_polizas["UUID"] = (
        df_polizas["UUID"]
        .astype(str)
        .str.upper()
        .str.strip()
    )

    df = df_xml.merge(
        df_polizas,
        on="UUID",
        how="left",
    )

    df["TIENE_POLIZA"] = df["NUM_POLIZ"].apply(
        lambda x: "SI" if pd.notna(x) and str(x).strip() != "" else "NO"
    )

    return df


def obtener_detalle_xml_polizas_uuid(
    modo: str,
    cliente: str = "PCP220503B20",
    anio: int | None = None,
) -> pd.DataFrame:
    """
    Trae los XML desde la BD SAT y los cruza en pandas con POLIZAS25,
    AUXILIAR25 y CUENTAS25 desde la BD COI.

    Resultado: una fila por partida contable de la póliza relacionada al UUID.
    """

    if modo == "ventas":
        filtro_cliente = "COALESCE(TRIM(x.CLIENTE), '') <> ?"
    elif modo == "gastos":
        filtro_cliente = "COALESCE(TRIM(x.CLIENTE), '') = ?"
    else:
        return pd.DataFrame()

    params = [cliente]

    filtro_anio = ""
    if anio:
        filtro_anio = " AND EXTRACT(YEAR FROM x.FECHA) = ? "
        params.append(int(anio))

    sql_xml = f"""
        SELECT
            x.UUID,
            x.CLIENTE,
            x.RFCE,
            x.FECHA,
            x.SERIE,
            x.FOLIO,
            x.SUBTOTAL,
            x.IVA,
            x.IMPORTE,
            x.MONEDA,
            x.TIPOCAMBIO,
            CASE
                WHEN COALESCE(x.TIPOCAMBIO, 0) > 0 THEN x.IMPORTE * x.TIPOCAMBIO
                ELSE x.IMPORTE
            END AS IMPORTE_MXN,
            x.TIPO,
            x.STATUS,
            x.DOCUMENTO
        FROM XML_DATA x
        WHERE {filtro_cliente}
          AND COALESCE(TRIM(x.TIPO), '') = 'I'
          {filtro_anio}
          AND x.UUID IS NOT NULL
          AND TRIM(x.UUID) <> ''
    """

    df_xml = _to_df(
        run_query_firebird(CONN_SAT, sql_xml, tuple(params))
    )

    if df_xml.empty:
        return pd.DataFrame()

    sql_polizas_detalle = """
        SELECT
            p.UUID,
            p.TIPO_POLI,
            p.NUM_POLIZ,
            p.PERIODO,
            p.EJERCICIO,
            p.FECHA_POL,
            p.CONCEP_PO,
            a.NUM_PART,
            a.NUM_CTA,
            c.NOMBRE AS NOMBRE_CUENTA,
            a.CONCEP_PO AS CONCEPTO_PARTIDA,
            a.DEBE_HABER,
            a.MONTOMOV
        FROM POLIZAS25 p
        INNER JOIN AUXILIAR25 a
            ON  a.TIPO_POLI = p.TIPO_POLI
            AND a.NUM_POLIZ = p.NUM_POLIZ
            AND a.PERIODO = p.PERIODO
            AND a.EJERCICIO = p.EJERCICIO
        LEFT JOIN CUENTAS25 c
            ON c.NUM_CTA = a.NUM_CTA
        WHERE p.UUID IS NOT NULL
          AND TRIM(p.UUID) <> ''
        ORDER BY
            p.EJERCICIO,
            p.PERIODO,
            p.TIPO_POLI,
            p.NUM_POLIZ,
            a.NUM_PART
    """

    df_polizas = _to_df(
        run_query_firebird(CONN_COI, sql_polizas_detalle, ())
    )

    df_xml["UUID"] = (
        df_xml["UUID"]
        .astype(str)
        .str.upper()
        .str.strip()
    )

    for col in [
        "SUBTOTAL",
        "IVA",
        "IMPORTE",
        "TIPOCAMBIO",
        "IMPORTE_MXN",
    ]:
        if col in df_xml.columns:
            df_xml[col] = pd.to_numeric(
                df_xml[col],
                errors="coerce"
            ).fillna(0)

    if df_polizas.empty:
        df_xml["TIENE_POLIZA"] = "NO"
        df_xml["TOTAL_DEBE"] = 0
        df_xml["TOTAL_HABER"] = 0
        df_xml["DIF_POLIZA"] = 0
        df_xml["DIF_XML_DEBE"] = df_xml["IMPORTE_MXN"]
        df_xml["DIF_XML_HABER"] = df_xml["IMPORTE_MXN"]
        df_xml["ESTATUS_VALIDACION"] = "SIN POLIZA"
        return df_xml

    df_polizas["UUID"] = (
        df_polizas["UUID"]
        .astype(str)
        .str.upper()
        .str.strip()
    )

    df_polizas["MONTOMOV"] = pd.to_numeric(
        df_polizas["MONTOMOV"],
        errors="coerce"
    ).fillna(0)

    df_polizas["DEBE_HABER"] = (
        df_polizas["DEBE_HABER"]
        .fillna("")
        .astype(str)
        .str.upper()
        .str.strip()
    )

    df_polizas["CARGO"] = df_polizas.apply(
        lambda r: r["MONTOMOV"] if r["DEBE_HABER"] == "D" else 0,
        axis=1,
    )

    df_polizas["ABONO"] = df_polizas.apply(
        lambda r: r["MONTOMOV"] if r["DEBE_HABER"] == "H" else 0,
        axis=1,
    )

    keys_poliza = [
        "UUID",
        "TIPO_POLI",
        "NUM_POLIZ",
        "PERIODO",
        "EJERCICIO",
    ]

    df_totales = (
        df_polizas
        .groupby(keys_poliza, as_index=False)
        .agg(
            TOTAL_DEBE=("CARGO", "sum"),
            TOTAL_HABER=("ABONO", "sum"),
            PARTIDAS=("NUM_PART", "count"),
        )
    )

    df_totales["DIF_POLIZA"] = (
        df_totales["TOTAL_DEBE"] - df_totales["TOTAL_HABER"]
    )

    df_polizas = df_polizas.merge(
        df_totales,
        on=keys_poliza,
        how="left",
    )

    df = df_xml.merge(
        df_polizas,
        on="UUID",
        how="left",
    )

    df["TIENE_POLIZA"] = df["NUM_POLIZ"].apply(
        lambda x: "SI" if pd.notna(x) and str(x).strip() != "" else "NO"
    )

    for col in [
        "MONTOMOV",
        "CARGO",
        "ABONO",
        "TOTAL_DEBE",
        "TOTAL_HABER",
        "DIF_POLIZA",
    ]:
        df[col] = pd.to_numeric(
            df[col],
            errors="coerce"
        ).fillna(0)

    df["DIF_XML_DEBE"] = df["IMPORTE_MXN"] - df["TOTAL_DEBE"]
    df["DIF_XML_HABER"] = df["IMPORTE_MXN"] - df["TOTAL_HABER"]

    def _estatus(r):
        if str(r.get("TIENE_POLIZA", "NO")).strip().upper() != "SI":
            return "SIN POLIZA"

        if abs(float(r.get("DIF_POLIZA", 0))) > 1:
            return "POLIZA DESCUADRADA"

        return "POLIZA CUADRADA"

    df["ESTATUS_VALIDACION"] = df.apply(_estatus, axis=1)

    return df

def obtener_validacion_importes_uuid(
    modo: str,
    cliente: str = "PCP220503B20",
    anio: int | None = None,
) -> pd.DataFrame:
    """
    Resumen por XML/póliza.
    Regresa una fila por UUID con los montos XML vs póliza.
    """

    df_detalle = obtener_detalle_xml_polizas_uuid(
        modo=modo,
        cliente=cliente,
        anio=anio,
    )

    if df_detalle.empty:
        return pd.DataFrame()

    columnas_base = [
        "UUID",
        "CLIENTE",
        "RFCE",
        "FECHA",
        "SERIE",
        "FOLIO",
        "SUBTOTAL",
        "IVA",
        "IMPORTE",
        "MONEDA",
        "TIPOCAMBIO",
        "IMPORTE_MXN",
        "TIPO",
        "STATUS",
        "DOCUMENTO",
        "TIENE_POLIZA",
        "TIPO_POLI",
        "NUM_POLIZ",
        "PERIODO",
        "EJERCICIO",
        "FECHA_POL",
        "CONCEP_PO",
        "TOTAL_DEBE",
        "TOTAL_HABER",
        "DIF_POLIZA",
        "DIF_XML_DEBE",
        "DIF_XML_HABER",
        "ESTATUS_VALIDACION",
    ]

    columnas = [
        c for c in columnas_base
        if c in df_detalle.columns
    ]

    df_resumen = (
        df_detalle[columnas]
        .drop_duplicates()
        .reset_index(drop=True)
    )

    df_resumen = df_resumen.rename(columns={
        "NUM_POLIZ": "NUMERO_POLIZA",
        "TIPO_POLI": "TIPO_POLIZA",
        "IMPORTE_MXN": "MONTO_XML",
        "TOTAL_HABER": "MONTO_HABER",
        "TOTAL_DEBE": "MONTO_DEBE",
        "DIF_XML_HABER": "DIFERENCIA",
    })

    columnas_finales = [
        "UUID",
        "NUMERO_POLIZA",
        "TIPO_POLIZA",
        "PERIODO",
        "EJERCICIO",
        "MONTO_XML",
        "MONTO_HABER",
        "MONTO_DEBE",
        "DIFERENCIA",
        "ESTATUS_VALIDACION",
        "CLIENTE",
        "RFCE",
        "FECHA",
        "SERIE",
        "FOLIO",
        "SUBTOTAL",
        "IVA",
        "IMPORTE",
        "MONEDA",
        "TIPOCAMBIO",
        "TIENE_POLIZA",
        "FECHA_POL",
        "CONCEP_PO",
    ]

    columnas_finales = [
        c for c in columnas_finales
        if c in df_resumen.columns
    ]

    return df_resumen[columnas_finales]