from __future__ import annotations

import math
import re
from typing import Any

import pandas as pd


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
    t = _norm(texto)

    for alias, mes in MESES.items():
        if t == alias or t.startswith(alias + " "):
            return mes

    return None


def _fila_contiene(row_values: list[Any], texto: str) -> bool:
    objetivo = _norm(texto)
    for v in row_values:
        if objetivo in _norm(v):
            return True
    return False


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
    cols = {}

    joined = " ".join(_norm(v) for v in header_values)

    es_header_cam = "CAM" in joined and "CARIBE" in joined
    es_header_mexico = "MEXICO" in joined

    for idx, val in enumerate(header_values):
        n = _norm(val)

        if not n:
            continue

        if n in {"STATUS", "ESTATUS"} or "BUDGET" in n:
            cols["estatus"] = idx

        elif "COMPANY" in n or "EMPRESA" in n:
            cols["company"] = idx

        elif "CLIENTE" in n or "CUSTOMER" in n or "COUNTRY" in n or "PAIS" in n:
            cols["cliente"] = idx

        elif "CODIGO" in n or "CÓDIGO" in n or "CODE" in n:
            cols["codigo_origen"] = idx

        elif "PRODUCTO" in n or "PRODUCT" in n:
            cols["producto"] = idx

        elif "PRECIO" in n or "PRICE" in n or "USD / KG" in n or "USD/KG" in n:
            cols["precio"] = idx

    meses = []
    for idx, val in enumerate(header_values):
        mes = _detectar_mes(val)
        if mes:
            meses.append({
                "idx": idx,
                "mes": mes,
                "header": _txt(val),
            })

    cols["meses"] = meses

    # Fallback para tablas CAM & Caribe / MEXICO donde no viene PRODUCTO como encabezado.
    # Formato observado:
    # A = estatus
    # B = company
    # C = cliente / país
    # D = código origen opcional
    # E = código SAE / producto SAE opcional
    # F = producto
    # G = precio USD/Kg
    if (es_header_cam or es_header_mexico) and meses:
        cols.setdefault("estatus", 0)
        cols.setdefault("company", 1)
        cols.setdefault("cliente", 2)
        cols.setdefault("codigo_origen", 4)
        cols.setdefault("producto", 5)
        cols.setdefault("precio", 6)

    return cols


def _obtener(row_values: list[Any], idx: int | None):
    if idx is None:
        return None
    if idx >= len(row_values):
        return None
    return row_values[idx]


def detectar_tablas_presupuesto_excel(archivo, hoja: str) -> list[dict]:
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


def normalizar_presupuesto_excel_dinamico(
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

    tablas = detectar_tablas_presupuesto_excel(archivo, hoja)

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
                    "canal": None,
                    "cliente_excel": cliente or None,
                    "codigo_origen": codigo or None,
                    "vendedor_excel": None,
                    "unidad_negocio_excel": None,
                    "linea_excel": None,
                    "producto_excel": producto,
                    "precio": precio,
                    "anio": int(anio),
                    "mes": int(m["mes"]),
                    "cantidad_kg": cantidad_kg,
                    "importe": importe,
                    "valor": valor,
                    "comentario": None,
                })

    return pd.DataFrame(registros), tablas