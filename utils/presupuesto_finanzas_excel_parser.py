from __future__ import annotations

import math
from typing import Any

import pandas as pd


_COLUMNAS_ESPERADAS = {
    "CODIGO": "codigo",
    "FILAS": "fila_excel",
    "MESES": "mes",
    "CLAVE": "clave_cliente",
    "NOMBRE DEL CLIENTE": "nombre_cliente",
    "CLAVE DEL PRODUCTO SKU": "clave_producto_sku",
    "PRODUCTO": "producto",
    "AREA": "area",
    "VENDEDOR": "vendedor",
    "PRECIO UNITARIO EN DÓLARES": "precio_unitario_dolares",
    "TIPO": "tipo",
    "VOLUMEN": "volumen",
    "PU": "pu",
    "DÓLARES": "dolares",
}


def _txt(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and math.isnan(v):
        return ""
    return str(v).strip()


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


def _int(v: Any) -> int:
    return int(round(_float(v)))


def obtener_hojas_presupuesto_finanzas(archivo) -> list[str]:
    """Devuelve los nombres de hoja de un archivo Excel subido (file-like)."""
    try:
        archivo.seek(0)
    except Exception:
        pass
    xls = pd.ExcelFile(archivo)
    return xls.sheet_names


def parsear_excel_presupuesto_finanzas(
    archivo,
    hoja: str = "BD",
    anio: int | None = None,
) -> pd.DataFrame:
    """
    Lee la hoja "BD" del archivo de presupuesto de finanzas y regresa un
    DataFrame normalizado listo para insertarse en la tabla `presupuesto_finanzas`.

    La hoja trae una fila en blanco arriba de los encabezados, por eso se lee
    con header=1 (segunda fila del Excel).
    """
    try:
        archivo.seek(0)
    except Exception:
        pass

    df_raw = pd.read_excel(archivo, sheet_name=hoja, header=1)
    df_raw.columns = [str(c).strip() for c in df_raw.columns]

    faltantes = [c for c in _COLUMNAS_ESPERADAS if c not in df_raw.columns]
    if faltantes:
        raise ValueError(
            f"la hoja '{hoja}' no tiene las columnas esperadas: {', '.join(faltantes)}"
        )

    filas: list[dict] = []
    for _, r in df_raw.iterrows():
        producto = _txt(r.get("PRODUCTO"))
        nombre_cliente = _txt(r.get("NOMBRE DEL CLIENTE"))
        if not producto and not nombre_cliente:
            continue  # fila vacía / de relleno

        filas.append({
            "codigo": _int(r.get("CODIGO")),
            "fila_excel": _int(r.get("FILAS")),
            "mes": _int(r.get("MESES")),
            "anio": int(anio) if anio else None,
            "clave_cliente": _txt(r.get("CLAVE")),
            "nombre_cliente": nombre_cliente,
            "clave_producto_sku": _txt(r.get("CLAVE DEL PRODUCTO SKU")),
            "producto": producto,
            "area": _txt(r.get("AREA")),
            "vendedor": _txt(r.get("VENDEDOR")),
            "precio_unitario_dolares": _float(r.get("PRECIO UNITARIO EN DÓLARES")),
            "tipo": _txt(r.get("TIPO")).upper(),
            "volumen": _float(r.get("VOLUMEN")),
            "pu": _float(r.get("PU")),
            "dolares": _float(r.get("DÓLARES")),
        })

    return pd.DataFrame(filas)
