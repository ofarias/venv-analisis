from __future__ import annotations

import datetime as dt
import math
import re
import unicodedata
from typing import Any

import pandas as pd

# Parser de Excel para "Presupuesto Compra" — mirror del formato "standard"
# de utils/presupuesto_ventas_excel_parser.py (detector genérico de bloques
# "TURNOVER in VOLUME KG" / "TURNOVER in USD" + región MEXICO/CAM & CARIBE +
# columnas fijas por posición). También incluye parsers de formato "vendedor"
# (archivos externos con layout propio, ver _detectar_formato_compras_vendedor)
# para cuando llega un archivo de compras con un formato distinto al standard.

MESES = {
    "JAN": 1, "JANUARY": 1, "ENE": 1, "ENERO": 1,
    "FEB": 2, "FEBRUARY": 2, "FEBRERO": 2,
    "MAR": 3, "MARCH": 3, "MARZO": 3,
    "APR": 4, "APRIL": 4, "ABR": 4, "ABRIL": 4,
    "MAY": 5, "MAYO": 5,
    "JUN": 6, "JUNE": 6, "JUNIO": 6,
    "JUL": 7, "JULY": 7, "JULIO": 7,
    "AUG": 8, "AUGUST": 8, "AGO": 8, "AGOSTO": 8,
    "SEP": 9, "SEPT": 9, "SEPTEMBER": 9, "SEPTIEMBRE": 9,
    "FEBRERO": 2, "MARZO": 3,
    "OCT": 10, "OCTOBER": 10, "OCTUBRE": 10,
    "NOV": 11, "NOVEMBER": 11, "NOVIEMBRE": 11,
    "DEC": 12, "DECEMBER": 12, "DIC": 12, "DICIEMBRE": 12,
}


ESTATUS_VALIDOS = {
    "BUDGETED",
    "BUDGETEED",
    "NOT IN BGT",
}


def _txt(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and math.isnan(v):
        return ""
    return str(v).strip()


def _norm(v: Any) -> str:
    t = _txt(v).upper()
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def _sin_acentos(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))


def _float(v: Any) -> float:
    if v is None:
        return 0.0

    if isinstance(v, (int, float)):
        if isinstance(v, float) and math.isnan(v):
            return 0.0
        return float(v)

    t = _txt(v).replace(",", "")
    if not t:
        return 0.0

    try:
        return float(t)
    except Exception:
        return 0.0


def _detectar_mes(texto: Any):
    # encabezado de mes como fecha real de Excel (ej. datetime(2026,1,1) en
    # vez del texto "Jan"/"Enero") — formato "Plan Demanda BIOTECSA"
    if isinstance(texto, (dt.datetime, dt.date, pd.Timestamp)):
        return texto.month

    t = _norm(texto)

    for alias, mes in MESES.items():
        if t == alias or t.startswith(alias + " "):
            return mes

    return None


def _detectar_seccion(row_values: list[Any]) -> str | None:
    joined = " ".join(_norm(v) for v in row_values)

    if "TURNOVER" in joined and "VOLUME" in joined and "KG" in joined:
        return "KG"

    if "TURNOVER" in joined and "USD" in joined:
        return "USD"

    return None


def _detectar_region(row_values: list[Any]) -> str | None:
    joined = " ".join(_norm(v) for v in row_values)

    if "CAM" in joined and "CARIBE" in joined:
        return "CAM & Caribe"

    if "MEXICO" in joined:
        return "MEXICO"

    return None


def _es_fila_header(row_values: list[Any]) -> bool:
    joined = " ".join(_norm(v) for v in row_values)

    tiene_meses = any(
        mes in joined
        for mes in ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
    )

    tiene_producto = "PRODUCTO" in joined or "PRODUCT" in joined

    tiene_region_cam = "CAM" in joined and "CARIBE" in joined

    tiene_region_mexico = "MEXICO" in joined

    return tiene_meses and (
        tiene_producto
        or tiene_region_cam
        or tiene_region_mexico
    )


def _mapear_header(header_values: list[Any]) -> dict:
    # Columnas fijas (igual que en presupuesto de ventas):
    # col0=STATUS  col1=COMPANY  col2=PROVEEDOR/CANAL  col3=CON-xxxx  col4=Clave-B (opt)
    # col5=PRODUCTO  col6=PRECIO  col7-18=Meses Ene-Dic
    meses = []
    for idx, val in enumerate(header_values):
        mes = _detectar_mes(val)
        if mes:
            meses.append({"idx": idx, "mes": mes, "header": _txt(val)})

    return {
        "estatus":       0,
        "company":       1,
        "cliente":       2,
        "codigo_origen": 3,
        "cve_prod":      4,
        "producto":      5,
        "precio":        6,
        "meses":         meses,
    }


def _obtener(row_values: list[Any], idx: int | None):
    if idx is None:
        return None
    if idx >= len(row_values):
        return None
    return row_values[idx]


def detectar_tablas_presupuesto_compras_excel(archivo, hoja: str) -> list[dict]:
    archivo.seek(0)

    raw = pd.read_excel(
        archivo,
        sheet_name=hoja,
        header=None,
        dtype=object,
    )

    tablas = []
    seccion_actual = None
    region_actual = None

    for i in range(len(raw)):
        row_values = raw.iloc[i].tolist()

        seccion = _detectar_seccion(row_values)
        if seccion:
            seccion_actual = seccion
            region_actual = None
            continue

        region = _detectar_region(row_values)
        if region:
            region_actual = region

        if seccion_actual and region_actual and _es_fila_header(row_values):
            header_idx = i
            header_values = row_values
            cols = _mapear_header(header_values)

            if not cols.get("meses"):
                continue

            ini = header_idx + 1
            fin = ini

            while fin < len(raw):
                rv = raw.iloc[fin].tolist()

                estatus_idx = cols.get("estatus", 0)
                estatus = _norm(_obtener(rv, estatus_idx))

                producto = _txt(_obtener(rv, cols.get("producto")))

                if not producto:
                    break

                if estatus and estatus not in ESTATUS_VALIDOS:
                    break

                fin += 1

            tablas.append({
                "seccion": seccion_actual,
                "region": region_actual,
                "header_excel": header_idx + 1,
                "fila_inicio": ini + 1,
                "fila_fin": fin,
                "cols": cols,
            })

    return tablas


def normalizar_presupuesto_compras_excel_dinamico(
    archivo,
    hoja: str,
    anio: int,
) -> tuple[pd.DataFrame, list[dict]]:
    archivo.seek(0)

    raw = pd.read_excel(
        archivo,
        sheet_name=hoja,
        header=None,
        dtype=object,
    )

    tablas = detectar_tablas_presupuesto_compras_excel(archivo, hoja)

    registros = []

    for tabla in tablas:
        cols = tabla["cols"]
        meses = cols.get("meses", [])

        for excel_row_num in range(tabla["fila_inicio"], tabla["fila_fin"] + 1):
            idx = excel_row_num - 1
            if idx >= len(raw):
                continue

            rv = raw.iloc[idx].tolist()

            estatus = _txt(_obtener(rv, cols.get("estatus", 0)))
            producto = _txt(_obtener(rv, cols.get("producto")))

            if not producto:
                continue

            company = _txt(_obtener(rv, cols.get("company")))
            cliente = _txt(_obtener(rv, cols.get("cliente")))
            codigo = _txt(_obtener(rv, cols.get("codigo_origen")))
            cve_prod = _txt(_obtener(rv, cols.get("cve_prod")))
            precio = _float(_obtener(rv, cols.get("precio")))

            for m in meses:
                valor = _float(_obtener(rv, m["idx"]))

                if valor == 0:
                    continue

                seccion = tabla["seccion"]

                cantidad_kg = valor if seccion == "KG" else 0
                importe = valor if seccion == "USD" else round(valor * precio, 2)

                registros.append({
                    "fila_excel": excel_row_num,
                    "seccion": seccion,
                    "region": tabla["region"],
                    "estatus_excel": estatus or None,
                    "company": company or None,
                    "cliente_excel": cliente or None,
                    "codigo_origen": codigo or None,
                    "cve_prod": cve_prod or None,
                    "producto_excel": producto,
                    "precio": precio,
                    "anio": int(anio),
                    "mes": int(m["mes"]),
                    "cantidad_kg": cantidad_kg,
                    "importe": importe,
                    "valor": valor,
                    "comentario": None,
                })

    if not registros:
        return pd.DataFrame(registros), tablas

    df = _dedup_compras(pd.DataFrame(registros))

    return df, tablas


def _dedup_compras(df: pd.DataFrame) -> pd.DataFrame:
    """Si el Excel tiene más de una fila para la misma combinación
    (seccion, region, mes, producto, cliente, etc.), se suman para no
    violar la unique key de la tabla destino."""
    if df.empty:
        return df

    KEY = ["seccion", "region", "anio", "mes", "company",
           "cliente_excel", "codigo_origen", "producto_excel"]
    key_presentes = [c for c in KEY if c in df.columns]

    _SEN = "\x00"
    for c in key_presentes:
        df[c] = df[c].fillna(_SEN)

    agg: dict = {}
    for c in ("fila_excel", "estatus_excel", "cve_prod", "comentario", "precio"):
        if c in df.columns:
            agg[c] = "first"
    for c in ("valor", "cantidad_kg", "importe"):
        if c in df.columns:
            agg[c] = "sum"

    df = df.groupby(key_presentes).agg(agg).reset_index()

    for c in key_presentes:
        df[c] = df[c].replace(_SEN, None)

    return df


# ── formatos "vendedor" (archivos externos con layout propio) ──────────────

_LABELS_CVE_PLAN_DEMANDA = {"CODIGO BIOTECSA", "SKU"}


def _fila_header_plan_demanda(row: list[Any]) -> bool:
    """Encabezado del formato "Plan Demanda BIOTECSA" (ver _parsear_plan_demanda):
    columna de clave (CÓDIGO BIOTECSA o SKU) + PRODUCTO + al menos un mes
    (texto ES/EN o fecha real de Excel), todo en la misma fila."""
    str_set = {_sin_acentos(_norm(v)) for v in row if pd.notna(v) and _txt(v)}
    if not (str_set & _LABELS_CVE_PLAN_DEMANDA):
        return False
    if "PRODUCTO" not in str_set:
        return False
    return any(_detectar_mes(v) is not None for v in row)


def _detectar_formato_compras_vendedor(df: pd.DataFrame) -> str:
    """
    Escanea hasta 40 filas para identificar un formato de compras distinto
    al standard. Returns: 'sae_simple', 'plan_demanda' o 'standard'.
    """
    for i in range(min(len(df), 40)):
        row = df.iloc[i].tolist()
        str_set = {_sin_acentos(_norm(v)) for v in row if pd.notna(v) and _txt(v)}

        # SAE_SIMPLE: columna "CODIGO SAE" (con o sin acento) + nombres de mes
        # en la misma fila. Layout sin bloques de seccion/region ni proveedor:
        # CODIGO SAE | <nombre producto> | <precio> | Ene..Dic (KG) | totales.
        if "CODIGO SAE" in str_set:
            if any(_detectar_mes(v) for v in row):
                return "sae_simple"

        if _fila_header_plan_demanda(row):
            return "plan_demanda"

    return "standard"


def _parsear_sae_simple(df: pd.DataFrame, anio: int) -> pd.DataFrame:
    """
    Formato SAE_SIMPLE (ej. "AB BIOTECSA 2027- LEATHER con SAE.xlsx"):
    CODIGO SAE | Product Code (en realidad es el NOMBRE del producto) |
    Price <anio> | Ene..Dic (KILOGRAMOS) | Total Vol | Total Turn.
    Sin columnas de proveedor/cliente/región/estatus — a pedido del usuario
    (2026-09-14) se asume región MEXICO, sección KG y estatus "Budgeted"
    para todas las filas. Las columnas de total se ignoran, se recalculan
    (importe = kg * precio).
    """
    header_i = None
    for i in range(min(len(df), 40)):
        row = df.iloc[i].tolist()
        str_set = {_sin_acentos(_norm(v)) for v in row if pd.notna(v) and _txt(v)}
        if "CODIGO SAE" in str_set:
            header_i = i
            break

    if header_i is None:
        return pd.DataFrame()

    header = df.iloc[header_i].tolist()

    def _idx(label: str, exact: bool = True) -> int | None:
        for j, v in enumerate(header):
            t = _sin_acentos(_norm(v))
            if (t == label) if exact else (label in t):
                return j
        return None

    idx_cve = _idx("CODIGO SAE")
    idx_producto = _idx("PRODUCT CODE")
    idx_precio = _idx("PRICE", exact=False)

    month_cols: list[tuple[int, int]] = []
    for j, v in enumerate(header):
        mes = _detectar_mes(v)
        if mes:
            month_cols.append((j, mes))

    if idx_cve is None or idx_producto is None or not month_cols:
        return pd.DataFrame()

    registros: list[dict] = []
    for row_i in range(header_i + 1, len(df)):
        row = df.iloc[row_i].tolist()

        cve_prod = _txt(_obtener(row, idx_cve))
        if not cve_prod:
            # fin de la tabla: fila de totales ("Result") o en blanco
            break

        producto = _txt(_obtener(row, idx_producto)) or cve_prod
        precio = _float(_obtener(row, idx_precio)) if idx_precio is not None else 0.0

        for col_idx, mes in month_cols:
            valor = _float(_obtener(row, col_idx))
            if valor == 0:
                continue

            registros.append({
                "fila_excel": row_i + 1,
                "seccion": "KG",
                "region": "MEXICO",
                "estatus_excel": "Budgeted",
                "company": None,
                "cliente_excel": None,
                "codigo_origen": None,
                "cve_prod": cve_prod,
                "producto_excel": producto,
                "precio": precio,
                "anio": int(anio),
                "mes": int(mes),
                "cantidad_kg": valor,
                "importe": round(valor * precio, 2),
                "valor": valor,
                "comentario": None,
            })

    if not registros:
        return pd.DataFrame(registros)

    return _dedup_compras(pd.DataFrame(registros))


def _parsear_plan_demanda(df: pd.DataFrame, anio: int) -> pd.DataFrame:
    """
    Formato "Plan Demanda BIOTECSA - <línea> <proveedor> - <mes><año>.xlsx"
    (Ricardo Rodríguez, compras — 5 líneas: Animal Co-Products, Bacterias
    Envirozyme, Baking, Jugos, Textil, todas NOVO salvo Envirozyme):
    CÓDIGO BIOTECSA (o SKU) | PRODUCTO | precio (el nombre de la columna
    varía por archivo: "Precio", "PRECIO", "Precio USD <año>",
    "<año> PRICE (USD/kg)") | meses (nombre ES/EN o fecha real de Excel del
    primer día del mes) | columna(s) de total — se ignoran, se recalculan
    igual que en sae_simple.

    Sin proveedor/cliente/región/estatus en el archivo — se asume región
    MEXICO, sección KG y estatus "Budgeted" para todas las filas. No todos
    los archivos traen los 12 meses ni columna de total en USD (ej.
    "Bacterias ENVIROZYME" solo mayo-diciembre, sin total USD) — solo se
    usan los meses que sí aparecen en el encabezado. Alguna fila puede traer
    PRODUCTO sin CÓDIGO BIOTECSA (fila de referencia sin clave, ej. "Aquazym
    Ultra 1800 N" en el archivo de Textil) — esa fila se omite pero no
    corta la tabla; el fin de la tabla es la primera fila con PRODUCTO
    vacío (ahí empiezan los totales).
    """
    header_i = None
    for i in range(min(len(df), 40)):
        row = df.iloc[i].tolist()
        if _fila_header_plan_demanda(row):
            header_i = i
            break

    if header_i is None:
        return pd.DataFrame()

    header = df.iloc[header_i].tolist()

    def _idx_en(labels: set[str]) -> int | None:
        for j, v in enumerate(header):
            if _sin_acentos(_norm(v)) in labels:
                return j
        return None

    idx_cve = _idx_en(_LABELS_CVE_PLAN_DEMANDA)
    idx_producto = _idx_en({"PRODUCTO"})

    idx_precio = None
    for j, v in enumerate(header):
        t = _sin_acentos(_norm(v))
        if t.startswith("PRECIO") or "PRICE" in t:
            idx_precio = j
            break

    month_cols: list[tuple[int, int]] = []
    for j, v in enumerate(header):
        mes = _detectar_mes(v)
        if mes:
            month_cols.append((j, mes))

    if idx_cve is None or idx_producto is None or not month_cols:
        return pd.DataFrame()

    registros: list[dict] = []
    for row_i in range(header_i + 1, len(df)):
        row = df.iloc[row_i].tolist()

        producto = _txt(_obtener(row, idx_producto))
        if not producto:
            # fin de la tabla: fila en blanco antes de los totales
            break

        cve_prod = _txt(_obtener(row, idx_cve))
        if not cve_prod:
            # fila de referencia sin clave — se omite, no corta la tabla
            continue

        precio = _float(_obtener(row, idx_precio)) if idx_precio is not None else 0.0

        for col_idx, mes in month_cols:
            valor = _float(_obtener(row, col_idx))
            if valor == 0:
                continue

            registros.append({
                "fila_excel": row_i + 1,
                "seccion": "KG",
                "region": "MEXICO",
                "estatus_excel": "Budgeted",
                "company": None,
                "cliente_excel": None,
                "codigo_origen": None,
                "cve_prod": cve_prod,
                "producto_excel": producto,
                "precio": precio,
                "anio": int(anio),
                "mes": int(mes),
                "cantidad_kg": valor,
                "importe": round(valor * precio, 2),
                "valor": valor,
                "comentario": None,
            })

    if not registros:
        return pd.DataFrame(registros)

    return _dedup_compras(pd.DataFrame(registros))


_PARSERS_VENDEDOR_COMPRAS = {
    "sae_simple": _parsear_sae_simple,
    "plan_demanda": _parsear_plan_demanda,
}


def normalizar_presupuesto_compras_excel_auto(
    archivo,
    hoja: str,
    anio: int,
) -> tuple[pd.DataFrame, list[dict]]:
    """Punto de entrada único: detecta primero los formatos "vendedor"
    (ver _detectar_formato_compras_vendedor); si no coincide con ninguno,
    cae al formato "standard" (bloques TURNOVER in VOLUME KG / TURNOVER in
    USD + MEXICO / CAM & CARIBE)."""
    archivo.seek(0)
    raw = pd.read_excel(archivo, sheet_name=hoja, header=None, dtype=object)

    formato = _detectar_formato_compras_vendedor(raw)

    if formato == "standard":
        return normalizar_presupuesto_compras_excel_dinamico(archivo, hoja, anio)

    fn = _PARSERS_VENDEDOR_COMPRAS[formato]
    result = fn(raw, anio)
    return (result if result is not None else pd.DataFrame()), []
