from __future__ import annotations

import math
import re
from datetime import datetime as _DT
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
    # Las columnas son fijas en todas las secciones del Excel:
    # col0=STATUS  col1=COMPANY  col2=CANAL/PAIS  col3=CON-xxxx  col4=Clave-B (opt)
    # col5=PRODUCTO  col6=PRECIO  col7=PRECIO VENTA  col8-19=Meses Ene-Dic
    # Solo los meses se detectan por etiqueta porque son los únicos que varían.
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
        "precio_venta":  7,
        "meses":         meses,
    }


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
            cve_prod = _txt(_obtener(rv, cols.get("cve_prod")))
            precio = _float(_obtener(rv, cols.get("precio")))
            precio_venta = _float(_obtener(rv, cols.get("precio_venta")))

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
                    "cve_prod": cve_prod or None,
                    "vendedor_excel": None,
                    "unidad_negocio_excel": None,
                    "linea_excel": None,
                    "producto_excel": producto,
                    "precio": precio,
                    "precio_venta": precio_venta,
                    "anio": int(anio),
                    "mes": int(m["mes"]),
                    "cantidad_kg": cantidad_kg,
                    "importe": importe,
                    "valor": valor,
                    "comentario": None,
                })

    if not registros:
        return pd.DataFrame(registros), tablas

    df = pd.DataFrame(registros)

    # Si el Excel tiene más de una fila para la misma combinación
    # (seccion, region, mes, product, cliente, etc.), las sumamos para no
    # violar la unique key de la tabla destino.
    KEY = ["seccion", "region", "anio", "mes", "company",
           "cliente_excel", "codigo_origen", "producto_excel"]
    key_presentes = [c for c in KEY if c in df.columns]

    _SEN = "\x00"
    for c in key_presentes:
        df[c] = df[c].fillna(_SEN)

    agg: dict = {}
    for c in ("fila_excel", "estatus_excel", "canal", "cve_prod",
              "vendedor_excel", "unidad_negocio_excel", "linea_excel",
              "comentario", "precio", "precio_venta"):
        if c in df.columns:
            agg[c] = "first"
    for c in ("valor", "cantidad_kg", "importe"):
        if c in df.columns:
            agg[c] = "sum"

    df = df.groupby(key_presentes).agg(agg).reset_index()

    for c in key_presentes:
        df[c] = df[c].replace(_SEN, None)

    return df, tablas


# ── Vendedor format parsers ───────────────────────────────────────────────────
# Handles: ALIMENTOS (datetime month cols), BAKING, JUICE, BREWING DP3 (Clave SAE),
# ROGELIO (CLAVE/NOMBRE DEL CLIENTE/CLAVE DEL PRODUCTO SKU/TIPO)

def _es_datetime(v: Any) -> bool:
    return isinstance(v, _DT)


def _mes_desde_datetime(v: Any) -> int | None:
    if isinstance(v, _DT):
        return v.month
    return None


def _detectar_formato_vendedor(df: pd.DataFrame) -> str:
    """
    Scan up to 40 rows to identify the vendedor format.
    Returns: 'alimentos', 'baking', 'juice', 'brewing_dp3', or 'standard'
    """
    for i in range(min(len(df), 40)):
        row = df.iloc[i].tolist()
        str_set = {_norm(v) for v in row if pd.notna(v) and _txt(v)}
        has_dt = any(_es_datetime(v) for v in row)

        # ALIMENTOS: datetime month columns + "CODIGO UNIVERSAL" or "MATERIAL" in same header row
        if has_dt:
            if any("CODIGO UNIVERSAL" in s or s in ("MATERIAL", "LOCATION DESCRIPTION")
                   for s in str_set):
                return "alimentos"

        # BREWING DP3: "CLAVE SAE" column header + month names
        if "CLAVE SAE" in str_set:
            if any(_detectar_mes(v) for v in row):
                return "brewing_dp3"

        # JUICE: "COMPANY" + "CODIGO UNIVERSAL" + "PRODUCTO" in same header row
        if ("COMPANY" in str_set
                and "CODIGO UNIVERSAL" in str_set
                and "PRODUCTO" in str_set):
            return "juice"

        # BAKING: any cell contains "CODIGO UNIVERSAL" + month name in same row
        if any("CODIGO UNIVERSAL" in s for s in str_set):
            if any(_detectar_mes(v) for v in row):
                return "baking"

        # ROGELIO: header CLAVE | NOMBRE DEL CLIENTE | CLAVE DEL PRODUCTO SKU | ... | TIPO
        if {"NOMBRE DEL CLIENTE", "CLAVE DEL PRODUCTO SKU", "TIPO"} <= str_set:
            return "rogelio"

    return "standard"


def _base_reg(
    seccion: str,
    region: str,
    anio: int,
    mes: int,
    company: str | None,
    cliente_excel: str | None,
    codigo_origen: str | None,
    cve_prod: str | None,
    producto_excel: str,
    precio: float,
    valor: float,
    estatus_excel: str | None,
    fila_excel: int,
) -> dict:
    cantidad_kg = valor if seccion == "KG" else 0.0
    importe = valor if seccion == "USD" else round(valor * precio, 2)
    return {
        "fila_excel": fila_excel,
        "seccion": seccion,
        "region": region,
        "estatus_excel": estatus_excel or None,
        "company": company or None,
        "canal": None,
        "cliente_excel": cliente_excel or None,
        "codigo_origen": codigo_origen or None,
        "cve_prod": cve_prod or None,
        "vendedor_excel": None,
        "unidad_negocio_excel": None,
        "linea_excel": None,
        "producto_excel": producto_excel,
        "precio": precio,
        "anio": int(anio),
        "mes": int(mes),
        "cantidad_kg": cantidad_kg,
        "importe": importe,
        "valor": valor,
        "comentario": None,
    }


_LABEL_ROWS = {"KG", "USD", "TOTAL", "SUBTOTAL", "CAMBIOS DP",
               "ORDEN COLOCADA", "KG BY MTH", "PRECIO USD"}


def _dedup_vendedor(registros: list[dict]) -> pd.DataFrame:
    """Aggregate duplicate key rows (same as normalizar_presupuesto_excel_dinamico)."""
    if not registros:
        return pd.DataFrame(registros)

    df = pd.DataFrame(registros)

    KEY = ["seccion", "region", "anio", "mes", "company",
           "cliente_excel", "codigo_origen", "producto_excel"]
    key_presentes = [c for c in KEY if c in df.columns]

    _SEN = "\x00"
    for c in key_presentes:
        df[c] = df[c].fillna(_SEN)

    agg: dict = {}
    for c in ("fila_excel", "estatus_excel", "canal", "cve_prod",
              "vendedor_excel", "unidad_negocio_excel", "linea_excel",
              "comentario", "precio", "precio_venta"):
        if c in df.columns:
            agg[c] = "first"
    for c in ("valor", "cantidad_kg", "importe"):
        if c in df.columns:
            agg[c] = "sum"

    df = df.groupby(key_presentes).agg(agg).reset_index()

    for c in key_presentes:
        df[c] = df[c].replace(_SEN, None)

    return df


def _parsear_alimentos(df: pd.DataFrame, anio: int) -> pd.DataFrame:
    """
    ALIMENTOS vendedor format.
    Header rows contain datetime month objects + "CODIGO UNIVERSAL"/"MATERIAL" labels.
    Data: col1=region, col2=company, col3=cve_prod(B-code), col4=product, col18=precio
    """
    # Locate all header rows: ≥6 datetime month columns + cve/material marker
    header_rows: list[tuple[int, list[tuple[int, int]]]] = []

    for i in range(len(df)):
        row = df.iloc[i].tolist()
        str_set = {_norm(v) for v in row if pd.notna(v) and _txt(v)}
        dt_cols = [(j, _mes_desde_datetime(v))
                   for j, v in enumerate(row)
                   if _mes_desde_datetime(v) is not None]

        if (len(dt_cols) >= 6
                and any("CODIGO UNIVERSAL" in s or "MATERIAL" == s for s in str_set)):
            header_rows.append((i, dt_cols))

    if not header_rows:
        return pd.DataFrame()

    registros: list[dict] = []

    for h_num, (header_i, dt_cols) in enumerate(header_rows):
        end_i = (header_rows[h_num + 1][0]
                 if h_num + 1 < len(header_rows) else len(df))

        for row_i in range(header_i + 1, end_i):
            row = df.iloc[row_i].tolist()

            # Skip rows with almost no data (separator / total lines)
            non_null = [v for v in row if pd.notna(v) and _txt(v)]
            if len(non_null) <= 2:
                continue

            cve_prod = _txt(_obtener(row, 3))
            producto = _txt(_obtener(row, 4))

            if not cve_prod or not producto:
                continue

            if _norm(cve_prod) in _LABEL_ROWS or _norm(producto) in _LABEL_ROWS:
                continue

            region_raw = _norm(_obtener(row, 1))
            if "MEXICO" in region_raw or "MÉXICO" in region_raw:
                region = "MEXICO"
            elif "CAM" in region_raw or "CARIBE" in region_raw:
                region = "CAM & Caribe"
            else:
                region = region_raw or "MEXICO"

            company = _txt(_obtener(row, 2))
            precio = _float(_obtener(row, 18)) if len(row) > 18 else 0.0

            for col_idx, mes in dt_cols:
                valor = _float(_obtener(row, col_idx))
                if valor == 0:
                    continue
                registros.append(_base_reg(
                    seccion="KG", region=region, anio=anio, mes=mes,
                    company=company, cliente_excel=None, codigo_origen=None,
                    cve_prod=cve_prod, producto_excel=producto,
                    precio=precio, valor=valor, estatus_excel=None,
                    fila_excel=row_i + 1,
                ))

    return _dedup_vendedor(registros)


def _parsear_baking(df: pd.DataFrame, anio: int) -> pd.DataFrame:
    """
    BAKING vendedor format (single table).
    Header: col2=PRODUCTO, col3=Codigo Universal, col4=Inventario(skip), col5+=month names
    Data:   col0=company(NZMX), col2=product, col3=B-code(cve_prod), col5+=monthly KG
    """
    header_i = None
    month_cols: list[tuple[int, int]] = []

    for i in range(min(len(df), 25)):
        row = df.iloc[i].tolist()
        str_set = {_norm(v) for v in row if pd.notna(v) and _txt(v)}

        if not any("CODIGO UNIVERSAL" in s for s in str_set):
            continue

        mcs = [(j, _detectar_mes(v))
               for j, v in enumerate(row)
               if _detectar_mes(v) is not None]
        if mcs:
            header_i = i
            month_cols = mcs
            break

    if header_i is None or not month_cols:
        return pd.DataFrame()

    registros: list[dict] = []

    for row_i in range(header_i + 1, len(df)):
        row = df.iloc[row_i].tolist()

        cve_prod = _txt(_obtener(row, 3))
        producto = _txt(_obtener(row, 2))

        if not cve_prod or not producto:
            continue
        if _norm(cve_prod) in _LABEL_ROWS or _norm(producto) in _LABEL_ROWS:
            continue

        company = _txt(_obtener(row, 0))

        for col_idx, mes in month_cols:
            valor = _float(_obtener(row, col_idx))
            if valor == 0:
                continue
            registros.append(_base_reg(
                seccion="KG", region="MEXICO", anio=anio, mes=mes,
                company=company or None, cliente_excel=None, codigo_origen=None,
                cve_prod=cve_prod, producto_excel=producto,
                precio=0.0, valor=valor, estatus_excel=None,
                fila_excel=row_i + 1,
            ))

    return _dedup_vendedor(registros)


def _parsear_juice(df: pd.DataFrame, anio: int) -> pd.DataFrame:
    """
    JUICE vendedor format (single table).
    Header: col2=Company, col3=CODIGO UNIVERSAL, col4=PRODUCTO, col5=PRECIO, col6+=months
    Data:   col1=estatus, col2=company, col3=cve_prod, col4=product, col5=price, col6+=monthly KG
    """
    header_i = None
    month_cols: list[tuple[int, int]] = []

    for i in range(min(len(df), 25)):
        row = df.iloc[i].tolist()
        str_set = {_norm(v) for v in row if pd.notna(v) and _txt(v)}

        if "COMPANY" not in str_set or "CODIGO UNIVERSAL" not in str_set:
            continue

        mcs = [(j, _detectar_mes(v))
               for j, v in enumerate(row)
               if _detectar_mes(v) is not None]
        if mcs:
            header_i = i
            month_cols = mcs
            break

    if header_i is None or not month_cols:
        return pd.DataFrame()

    registros: list[dict] = []

    for row_i in range(header_i + 1, len(df)):
        row = df.iloc[row_i].tolist()

        cve_prod = _txt(_obtener(row, 3))
        producto = _txt(_obtener(row, 4))

        if not cve_prod or not producto:
            continue
        if _norm(cve_prod) in _LABEL_ROWS or _norm(producto) in _LABEL_ROWS:
            continue

        # Skip totals row: col5 contains text (e.g. "Kg by MTH")
        precio_raw = _obtener(row, 5)
        if isinstance(precio_raw, str) and "KG" in precio_raw.upper():
            continue

        company = _txt(_obtener(row, 2))
        precio = _float(precio_raw)
        estatus = _txt(_obtener(row, 1))

        for col_idx, mes in month_cols:
            valor = _float(_obtener(row, col_idx))
            if valor == 0:
                continue
            registros.append(_base_reg(
                seccion="KG", region="MEXICO", anio=anio, mes=mes,
                company=company or None, cliente_excel=None, codigo_origen=None,
                cve_prod=cve_prod, producto_excel=producto,
                precio=precio, valor=valor, estatus_excel=estatus or None,
                fila_excel=row_i + 1,
            ))

    return _dedup_vendedor(registros)


def _parsear_brewing_dp3(df: pd.DataFrame, anio: int) -> pd.DataFrame:
    """
    BREWING DP3 format with 'Clave SAE' column and MEXICO + CAM sections.
    Mexico header: col1=Company, col3=Clave SAE(cve_prod), col5=PRODUCTO, col6=PRECIO, col7+=months
    CAM header:    col5='CAM & Caribe', col7+=month names; data col4=cve_prod, col5=product, col6=price
    """
    sections: list[dict] = []

    for i in range(len(df)):
        row = df.iloc[i].tolist()
        str_set = {_norm(v) for v in row if pd.notna(v) and _txt(v)}
        row_text = " ".join(str_set)

        has_sae  = "CLAVE SAE" in str_set
        has_univ = any("CODIGO UNIVERSAL" in s for s in str_set)
        has_cam  = "CAM" in row_text and "CARIBE" in row_text

        mcs = [(j, _detectar_mes(v))
               for j, v in enumerate(row)
               if _detectar_mes(v) is not None]

        if has_sae or has_univ:
            # MEXICO (or labelled-CAM) section header
            if not mcs:
                continue

            region = "CAM & Caribe" if has_cam else "MEXICO"

            cve_col = next(
                (j for j, v in enumerate(row)
                 if "CLAVE SAE" in _norm(v) or "CODIGO UNIVERSAL" in _norm(v)),
                3,
            )
            # MEXICO layout: col_cve | col_alt_code | col_product | col_price | months
            sections.append({
                "region": region,
                "header_i": i,
                "month_cols": mcs,
                "cve_col": cve_col,
                "company_col": 1,
                "cliente_col": 2,
                "prod_col": cve_col + 2,
                "price_col": cve_col + 3,
            })

        elif has_cam and mcs:
            # CAM & Caribe section header (no "Clave SAE" keyword)
            # data layout: col1=company, col2=country, col4=cve_prod, col5=product, col6=price
            sections.append({
                "region": "CAM & Caribe",
                "header_i": i,
                "month_cols": mcs,
                "cve_col": 4,
                "company_col": 1,
                "cliente_col": 2,
                "prod_col": 5,
                "price_col": 6,
            })

    if not sections:
        return pd.DataFrame()

    registros: list[dict] = []

    for s_idx, sec in enumerate(sections):
        header_i = sec["header_i"]
        end_i = (sections[s_idx + 1]["header_i"]
                 if s_idx + 1 < len(sections) else len(df))

        for row_i in range(header_i + 1, end_i):
            row = df.iloc[row_i].tolist()

            cve_prod = _txt(_obtener(row, sec["cve_col"]))
            producto = _txt(_obtener(row, sec["prod_col"]))

            if not cve_prod or not producto:
                continue

            norm_c = _norm(cve_prod)
            norm_p = _norm(producto)
            if norm_c in _LABEL_ROWS or norm_p in _LABEL_ROWS:
                continue
            # skip header-like values that leaked into data rows
            if "CLAVE SAE" in norm_c or "CODIGO UNIVERSAL" in norm_c:
                continue

            company = _txt(_obtener(row, sec["company_col"]))
            cliente = _txt(_obtener(row, sec["cliente_col"]))
            estatus = _txt(_obtener(row, 0))
            precio = _float(_obtener(row, sec["price_col"]))

            for col_idx, mes in sec["month_cols"]:
                valor = _float(_obtener(row, col_idx))
                if valor == 0:
                    continue
                registros.append(_base_reg(
                    seccion="KG", region=sec["region"], anio=anio, mes=mes,
                    company=company or None,
                    cliente_excel=cliente or None,
                    codigo_origen=cliente or None,
                    cve_prod=cve_prod, producto_excel=producto,
                    precio=precio, valor=valor,
                    estatus_excel=estatus or None,
                    fila_excel=row_i + 1,
                ))

    return _dedup_vendedor(registros)


def _parsear_rogelio(df: pd.DataFrame, anio: int) -> pd.DataFrame:
    """
    ROGELIO vendedor format.
    Encabezado (se repite: bloque normal y bloque "PROYECTOS" más abajo en la hoja):
    CLAVE | NOMBRE DEL CLIENTE | CLAVE DEL PRODUCTO SKU | PRODUCTO | AREA | VENDEDOR |
    PRECIO UNITARIO EN DÓLARES | TIPO | <12 meses, KG> | TOTAL | <bloque USD, se ignora>.
    El bloque de dólares que sigue a la derecha no se usa: el importe se calcula como
    kg * precio, igual que los demás formatos de este archivo.
    TIPO = PRESUPUESTO en el bloque normal, PROSPECTO en el bloque "PROYECTOS" — se
    guarda tal cual en estatus_excel ("Presupuesto"/"Prospecto"), no hace falta detectar
    la etiqueta de sección aparte porque cada renglón ya trae su propio TIPO.
    """
    header_rows = []
    for i in range(len(df)):
        row = df.iloc[i].tolist()
        str_set = {_norm(v) for v in row if pd.notna(v) and _txt(v)}
        if {"NOMBRE DEL CLIENTE", "CLAVE DEL PRODUCTO SKU", "TIPO"} <= str_set:
            header_rows.append(i)

    if not header_rows:
        return pd.DataFrame()

    def _idx(header_row: list[Any], label: str, exact: bool = True) -> int | None:
        for j, v in enumerate(header_row):
            txt = _norm(v)
            if (txt == label) if exact else (label in txt):
                return j
        return None

    registros: list[dict] = []

    for h_num, header_i in enumerate(header_rows):
        header = df.iloc[header_i].tolist()

        idx_clave = _idx(header, "CLAVE")
        idx_cliente = _idx(header, "NOMBRE DEL CLIENTE")
        idx_sku = _idx(header, "CLAVE DEL PRODUCTO SKU")
        idx_producto = _idx(header, "PRODUCTO")
        idx_area = _idx(header, "AREA")
        idx_vendedor = _idx(header, "VENDEDOR")
        idx_precio = _idx(header, "PRECIO UNITARIO", exact=False)
        idx_tipo = _idx(header, "TIPO")

        if idx_producto is None or idx_tipo is None:
            continue

        month_cols: list[tuple[int, int]] = []
        for j in range(idx_tipo + 1, len(header)):
            mes = _detectar_mes(header[j])
            if mes:
                month_cols.append((j, mes))
                if len(month_cols) == 12:
                    break

        if not month_cols:
            continue

        end_i = header_rows[h_num + 1] if h_num + 1 < len(header_rows) else len(df)

        for row_i in range(header_i + 1, end_i):
            row = df.iloc[row_i].tolist()

            producto = _txt(_obtener(row, idx_producto))
            if not producto:
                break

            codigo_origen = _txt(_obtener(row, idx_clave))
            cliente = _txt(_obtener(row, idx_cliente))
            cve_prod = _txt(_obtener(row, idx_sku))
            area = _txt(_obtener(row, idx_area))
            vendedor = _txt(_obtener(row, idx_vendedor))
            precio = _float(_obtener(row, idx_precio))
            tipo = _norm(_obtener(row, idx_tipo))

            estatus = "Prospecto" if tipo == "PROSPECTO" else "Presupuesto"

            for col_idx, mes in month_cols:
                valor = _float(_obtener(row, col_idx))
                if valor == 0:
                    continue

                registros.append({
                    "fila_excel": row_i + 1,
                    "seccion": "KG",
                    "region": "MEXICO",
                    "estatus_excel": estatus,
                    "company": None,
                    "canal": None,
                    "cliente_excel": cliente or None,
                    "codigo_origen": codigo_origen or None,
                    "cve_prod": cve_prod or None,
                    "vendedor_excel": vendedor or None,
                    "unidad_negocio_excel": None,
                    "linea_excel": area or None,
                    "producto_excel": producto,
                    "precio": precio,
                    "precio_venta": precio,
                    "anio": int(anio),
                    "mes": int(mes),
                    "cantidad_kg": valor,
                    "importe": round(valor * precio, 2),
                    "valor": valor,
                    "comentario": None,
                })

    return _dedup_vendedor(registros)


def normalizar_presupuesto_vendedor_excel(
    archivo,
    hoja: str,
    anio: int,
) -> tuple[pd.DataFrame, list[dict]]:
    """Entry point for vendedor formats (ALIMENTOS, BAKING, JUICE, BREWING DP3)."""
    archivo.seek(0)
    raw = pd.read_excel(archivo, sheet_name=hoja, header=None, dtype=object)

    formato = _detectar_formato_vendedor(raw)

    parsers = {
        "alimentos":   _parsear_alimentos,
        "baking":      _parsear_baking,
        "juice":       _parsear_juice,
        "brewing_dp3": _parsear_brewing_dp3,
        "rogelio":     _parsear_rogelio,
    }

    fn = parsers.get(formato)
    if fn is None:
        return pd.DataFrame(), []

    result = fn(raw, anio)
    return (result if result is not None else pd.DataFrame()), []


def normalizar_presupuesto_excel_auto(
    archivo,
    hoja: str,
    anio: int,
) -> tuple[pd.DataFrame, list[dict]]:
    """
    Auto-detect format and normalize.
    Vendedor formats are detected first; falls back to the standard parser.
    """
    archivo.seek(0)
    raw = pd.read_excel(archivo, sheet_name=hoja, header=None, dtype=object)

    formato = _detectar_formato_vendedor(raw)

    if formato == "standard":
        return normalizar_presupuesto_excel_dinamico(archivo, hoja, anio)

    parsers = {
        "alimentos":   _parsear_alimentos,
        "baking":      _parsear_baking,
        "juice":       _parsear_juice,
        "brewing_dp3": _parsear_brewing_dp3,
        "rogelio":     _parsear_rogelio,
    }

    fn = parsers[formato]
    result = fn(raw, anio)
    return (result if result is not None else pd.DataFrame()), []