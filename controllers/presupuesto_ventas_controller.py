from __future__ import annotations

import math
import re
from typing import Any, Optional

import pandas as pd

import streamlit as st

from models.presupuesto_ventas_model import (
    actualizar_cantidad_staging_presupuesto_ventas_model,
    actualizar_cve_prod_presupuesto_ventas_model,
    actualizar_estatus_carga_presupuesto_ventas_model,
    actualizar_match_staging_presupuesto_ventas_model,
    actualizar_presupuesto_ventas_model,
    eliminar_carga_presupuesto_ventas_model,
    eliminar_presupuesto_ventas_por_carga_model,
    eliminar_presupuesto_ventas_por_registro_model,
    eliminar_staging_por_carga_presupuesto_ventas_model,
    guardar_presupuesto_ventas_batch_model,
    insertar_carga_presupuesto_ventas_model,
    insertar_presupuesto_desde_staging_model,
    insertar_presupuesto_ventas_desde_df_model,
    insertar_presupuesto_ventas_unitario_model,
    insertar_presupuesto_ventas_linea_estatus_model,
    insertar_staging_presupuesto_ventas_model,
    obtener_cargas_presupuesto_ventas_model,
    obtener_presupuesto_ventas_lineas_model,
    obtener_presupuesto_ventas_lineas_pendientes_model,
    obtener_presupuesto_ventas_model,
    obtener_resumen_presupuesto_ventas_model,
    obtener_resumen_staging_presupuesto_ventas_model,
    obtener_staging_presupuesto_ventas_model,
    upsert_presupuesto_ventas_linea_model,
)
from models.presupuesto_ventas_sae_model import (
    obtener_catalogo_productos_pv_model,
    obtener_clientes_sae_model,
    obtener_existencias_productos_sae_model,
    obtener_lineas_sae_model,
    obtener_ordenes_compra_pendientes_sae_model,
    obtener_productos_sae_model,
    obtener_ultimo_precio_venta_sae_model,
    obtener_vendedores_sae_model,
)
from controllers.solicitudes_controller import buscar_clientes_sae_ctrl

from utils.presupuesto_ventas_excel_parser import (
    detectar_tablas_presupuesto_excel,
    normalizar_presupuesto_excel_auto,
    normalizar_presupuesto_excel_dinamico,
)

MESES_MAP = {
    "jan": 1,
    "january": 1,
    "ene": 1,
    "enero": 1,
    "feb": 2,
    "february": 2,
    "febrero": 2,
    "mar": 3,
    "march": 3,
    "marzo": 3,
    "apr": 4,
    "april": 4,
    "abr": 4,
    "abril": 4,
    "may": 5,
    "mayo": 5,
    "jun": 6,
    "june": 6,
    "junio": 6,
    "jul": 7,
    "july": 7,
    "julio": 7,
    "aug": 8,
    "august": 8,
    "ago": 8,
    "agosto": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "septiembre": 9,
    "oct": 10,
    "october": 10,
    "octubre": 10,
    "nov": 11,
    "november": 11,
    "noviembre": 11,
    "dec": 12,
    "december": 12,
    "dic": 12,
    "diciembre": 12,
}


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value).strip()


def _clean_upper(value: Any) -> str:
    return _clean_text(value).upper()


def _safe_float(value: Any) -> float:
    if value is None:
        return 0.0

    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return 0.0
        return float(value)

    text = _clean_text(value)
    if not text:
        return 0.0

    text = text.replace(",", "")
    try:
        return float(text)
    except Exception:
        return 0.0


def _normalize_col_name(col: Any) -> str:
    text = _clean_upper(col)
    text = re.sub(r"\s+", " ", text)
    return text


def _es_columna_mes(col_name: str) -> tuple[bool, Optional[int], Optional[int]]:
    c = _clean_text(col_name)
    c_upper = c.upper()

    m = re.match(r"^\s*(\d{4})[\.\-_\/](\d{1,2})\s*$", c_upper)
    if m:
        anio = int(m.group(1))
        mes = int(m.group(2))
        if 1 <= mes <= 12:
            return True, anio, mes

    c_norm = re.sub(r"\s+", " ", c.strip().lower())

    for alias, mes in MESES_MAP.items():
        alias_norm = alias.lower().strip()

        if c_norm == alias_norm:
            return True, None, mes

        if c_norm.startswith(alias_norm + " "):
            return True, None, mes

        if re.match(rf"^{re.escape(alias_norm)}[^a-z0-9]?", c_norm):
            return True, None, mes

    return False, None, None

def _buscar_columna(df: pd.DataFrame, aliases: list[str]) -> Optional[str]:
    normalizadas = {_normalize_col_name(c): c for c in df.columns}

    for alias in aliases:
        key = _normalize_col_name(alias)
        if key in normalizadas:
            return normalizadas[key]

    for norm_name, original in normalizadas.items():
        for alias in aliases:
            if _normalize_col_name(alias) in norm_name:
                return original

    return None


def _detectar_columnas_base(df: pd.DataFrame) -> dict[str, Optional[str]]:
    return {
        "company": _buscar_columna(df, ["company", "empresa"]),
        "canal": _buscar_columna(df, ["canal", "channel"]),
        "cliente": _buscar_columna(df, ["cliente", "customer", "client"]),
        "vendedor": _buscar_columna(df, ["vendedor", "sales rep", "salesperson", "seller"]),
        "unidad_negocio": _buscar_columna(df, ["unidad negocio", "unidad de negocio", "business unit"]),
        "linea": _buscar_columna(df, ["linea", "línea", "line"]),
        "producto": _buscar_columna(df, ["producto", "product", "sku", "item"]),
        "precio": _buscar_columna(df, ["precio", "price", "usd/kg", "price usd/kg", "precio usd/kg"]),
        "comentario": _buscar_columna(df, ["comentario", "comments", "comment", "notas", "notes"]),
    }


def _detectar_columnas_mes(df: pd.DataFrame, anio_default: Optional[int] = None) -> list[dict]:
    cols_mes: list[dict] = []

    for col in df.columns:
        es_mes, anio_detectado, mes = _es_columna_mes(str(col))
        if es_mes and mes:
            cols_mes.append(
                {
                    "columna": col,
                    "anio": anio_detectado if anio_detectado is not None else anio_default,
                    "mes": mes,
                }
            )

    cols_mes.sort(key=lambda x: ((x["anio"] or 0), x["mes"]))
    return cols_mes


def _valor(row: pd.Series, col: Optional[str]) -> Any:
    if not col:
        return None
    return row.get(col)


def _df_to_lookup(df: pd.DataFrame, key_col: str) -> dict[str, dict]:
    if df is None or df.empty or key_col not in df.columns:
        return {}

    rows = df.to_dict(orient="records")
    out: dict[str, dict] = {}
    for r in rows:
        key = _clean_upper(r.get(key_col))
        if key:
            out[key] = r
    return out


def leer_excel_presupuesto_ventas_ctrl(
    archivo,
    hoja: Optional[str] = None,
    header: int = 0,
) -> tuple[pd.DataFrame, str]:
    xls = pd.ExcelFile(archivo)

    hoja_final = hoja or (xls.sheet_names[0] if xls.sheet_names else "")
    if not hoja_final:
        raise ValueError("No se encontró ninguna hoja en el archivo Excel.")

    df = pd.read_excel(archivo, sheet_name=hoja_final, header=header)
    df.columns = [str(c).strip() for c in df.columns]
    return df, hoja_final


def obtener_preview_presupuesto_ventas_ctrl(
    archivo,
    hoja: Optional[str] = None,
    header: int = 0,
    limit: int = 50,
) -> dict:
    df, hoja_final = leer_excel_presupuesto_ventas_ctrl(
        archivo=archivo,
        hoja=hoja,
        header=header,
    )

    return {
        "hoja": hoja_final,
        "columnas": list(df.columns),
        "columnas_base": _detectar_columnas_base(df),
        "columnas_mes": _detectar_columnas_mes(df),
        "preview": df.head(limit).copy(),
        "total_filas": len(df),
    }


def normalizar_presupuesto_ventas_ctrl(
    df: pd.DataFrame,
    anio_default: int,
) -> list[dict]:
    columnas_base = _detectar_columnas_base(df)
    columnas_mes = _detectar_columnas_mes(df, anio_default=anio_default)

    col_producto = columnas_base.get("producto")
    col_precio = columnas_base.get("precio")

    if not col_producto:
        raise ValueError("No se encontró la columna de producto en el Excel.")

    if not columnas_mes:
        raise ValueError("No se detectaron columnas de meses en el Excel.")

    registros: list[dict] = []

    for idx, row in df.iterrows():
        producto_excel = _clean_text(_valor(row, col_producto))
        if not producto_excel:
            continue

        precio = _safe_float(_valor(row, col_precio))

        company = _clean_text(_valor(row, columnas_base.get("company")))
        canal = _clean_text(_valor(row, columnas_base.get("canal")))
        cliente_excel = _clean_text(_valor(row, columnas_base.get("cliente")))
        vendedor_excel = _clean_text(_valor(row, columnas_base.get("vendedor")))
        unidad_negocio_excel = _clean_text(_valor(row, columnas_base.get("unidad_negocio")))
        linea_excel = _clean_text(_valor(row, columnas_base.get("linea")))
        comentario = _clean_text(_valor(row, columnas_base.get("comentario")))

        for info_mes in columnas_mes:
            columna_mes = info_mes["columna"]
            anio = info_mes["anio"] if info_mes["anio"] is not None else anio_default
            mes = info_mes["mes"]

            cantidad_kg = _safe_float(_valor(row, columna_mes))
            if cantidad_kg == 0:
                continue

            importe = round(cantidad_kg * precio, 2)

            registros.append(
                {
                    "fila_excel": idx + 2,
                    "company": company or None,
                    "canal": canal or None,
                    "cliente_excel": cliente_excel or None,
                    "vendedor_excel": vendedor_excel or None,
                    "unidad_negocio_excel": unidad_negocio_excel or None,
                    "linea_excel": linea_excel or None,
                    "producto_excel": producto_excel,
                    "precio": precio,
                    "anio": int(anio),
                    "mes": int(mes),
                    "cantidad_kg": cantidad_kg,
                    "importe": importe,
                    "comentario": comentario or None,
                }
            )

    return registros


def registrar_carga_presupuesto_ventas_ctrl(
    nombre_archivo: str,
    hoja_origen: str,
    anio: int,
    version: Optional[str],
    comentarios: Optional[str],
    usuario_id: int,
) -> int:
    return insertar_carga_presupuesto_ventas_model(
        nombre_archivo=nombre_archivo,
        hoja_origen=hoja_origen,
        anio=anio,
        version=version,
        comentarios=comentarios,
        usuario_id=usuario_id,
    )


def cargar_excel_a_staging_presupuesto_ventas_ctrl(
    archivo,
    nombre_archivo: str,
    anio: int,
    usuario_id: int,
    hoja: Optional[str] = None,
    header: int = 0,
    version: Optional[str] = None,
    comentarios: Optional[str] = None,
    limpiar_staging: bool = True,
) -> dict:

    if not hoja:
        raise ValueError("Debes seleccionar una hoja del archivo Excel.")

    archivo.seek(0)

    df_norm, tablas = normalizar_presupuesto_excel_auto(
        archivo=archivo,
        hoja=hoja,
        anio=int(anio),
    )

    if df_norm is None or df_norm.empty:
        raise ValueError("No se generaron registros para cargar a staging.")

    id_carga = registrar_carga_presupuesto_ventas_ctrl(
        nombre_archivo=nombre_archivo,
        hoja_origen=hoja,
        anio=anio,
        version=version,
        comentarios=comentarios,
        usuario_id=usuario_id,
    )

    if limpiar_staging:
        eliminar_staging_por_carga_presupuesto_ventas_model(id_carga=id_carga)

    total_insertados = 0

    for _, reg in df_norm.iterrows():
        insertar_staging_presupuesto_ventas_model(
            id_carga=id_carga,
            fila_excel=int(reg.get("fila_excel") or 0),
            seccion=reg.get("seccion"),
            region=reg.get("region"),
            estatus_excel=reg.get("estatus_excel"),
            company=reg.get("company"),
            canal=reg.get("canal"),
            cliente_excel=reg.get("cliente_excel"),
            codigo_origen=reg.get("codigo_origen"),
            vendedor_excel=reg.get("vendedor_excel"),
            unidad_negocio_excel=reg.get("unidad_negocio_excel"),
            linea_excel=reg.get("linea_excel"),
            producto_excel=reg.get("producto_excel"),
            precio=float(reg.get("precio") or 0),
            anio=int(reg.get("anio") or anio),
            mes=int(reg.get("mes") or 0),
            cantidad_kg=float(reg.get("cantidad_kg") or 0),
            importe=float(reg.get("importe") or 0),
            valor=float(reg.get("valor") or 0),
            comentario=reg.get("comentario"),
        )
        total_insertados += 1

    actualizar_estatus_carga_presupuesto_ventas_model(
        id_carga=id_carga,
        estatus="staging",
    )

    return {
        "id_carga": id_carga,
        "hoja": hoja,
        "tablas_detectadas": len(tablas),
        "total_registros_staging": total_insertados,
    }

def validar_staging_presupuesto_ventas_con_sae_ctrl(
    id_carga: int,
    resolver_por_nombre: bool = True,
) -> dict:
    staging = obtener_staging_presupuesto_ventas_model(
        id_carga=id_carga,
        limit=200000,
    )

    if staging.empty:
        return {
            "id_carga": id_carga,
            "total_ok": 0,
            "total_error": 0,
            "resumen": obtener_resumen_staging_presupuesto_ventas_model(id_carga=id_carga),
        }

    productos = obtener_productos_sae_model()
    clientes = obtener_clientes_sae_model()
    vendedores = obtener_vendedores_sae_model()
    lineas = obtener_lineas_sae_model()

    productos_por_clave = _df_to_lookup(productos, "cve_art")
    productos_por_nombre = _df_to_lookup(productos, "descr")

    clientes_por_clave = _df_to_lookup(clientes, "clave")
    clientes_por_nombre = _df_to_lookup(clientes, "nombre")

    vendedores_por_clave = _df_to_lookup(vendedores, "cve_vend")
    vendedores_por_nombre = _df_to_lookup(vendedores, "nombre")

    lineas_por_clave = _df_to_lookup(lineas, "cve_lin")
    lineas_por_nombre = _df_to_lookup(lineas, "desc_lin")

    total_ok = 0
    total_error = 0

    for _, row in staging.iterrows():
        id_staging = int(row["id_staging"])

        producto_excel = _clean_text(row.get("producto_excel"))
        cve_prod_manual = _clean_text(row.get("cve_prod"))
        cliente_excel = _clean_text(row.get("cliente_excel"))
        vendedor_excel = _clean_text(row.get("vendedor_excel"))
        linea_excel = _clean_text(row.get("linea_excel"))

        cve_prod: Optional[str] = None
        cve_clie: Optional[str] = None
        cve_vend: Optional[str] = None
        cve_linea: Optional[str] = None

        observaciones: list[str] = []

        pe = _clean_upper(producto_excel)
        cp_manual = _clean_upper(cve_prod_manual)

        if cp_manual:
            if cp_manual in productos_por_clave:
                cve_prod = productos_por_clave[cp_manual]["cve_art"]
            else:
                observaciones.append("cve_prod_manual_no_existe_en_sae")
        elif pe in productos_por_clave:
            cve_prod = productos_por_clave[pe]["cve_art"]
        elif resolver_por_nombre and pe in productos_por_nombre:
            cve_prod = productos_por_nombre[pe]["cve_art"]
        else:
            observaciones.append("producto_sae_no_encontrado")

        ce = _clean_upper(cliente_excel)
        if cliente_excel:
            if ce in clientes_por_clave:
                cve_clie = clientes_por_clave[ce]["clave"]
            elif resolver_por_nombre and ce in clientes_por_nombre:
                cve_clie = clientes_por_nombre[ce]["clave"]
            else:
                observaciones.append("cliente_sae_no_encontrado")

        ve = _clean_upper(vendedor_excel)
        if vendedor_excel:
            if ve in vendedores_por_clave:
                cve_vend = vendedores_por_clave[ve]["cve_vend"]
            elif resolver_por_nombre and ve in vendedores_por_nombre:
                cve_vend = vendedores_por_nombre[ve]["cve_vend"]
            else:
                observaciones.append("vendedor_sae_no_encontrado")

        le = _clean_upper(linea_excel)
        if linea_excel:
            if le in lineas_por_clave:
                cve_linea = lineas_por_clave[le]["cve_lin"]
            elif resolver_por_nombre and le in lineas_por_nombre:
                cve_linea = lineas_por_nombre[le]["cve_lin"]
            else:
                observaciones.append("linea_sae_no_encontrada")

        id_unidad_negocio = row.get("id_unidad_negocio", None)
        if pd.isna(id_unidad_negocio) or id_unidad_negocio in ("", None):
            id_unidad_negocio = None
            observaciones.append("unidad_negocio_no_asignada")
        else:
            id_unidad_negocio = int(id_unidad_negocio)

        estatus_match = "ok" if len(observaciones) == 0 else "error"

        actualizar_match_staging_presupuesto_ventas_model(
            id_staging=id_staging,
            cve_prod=cve_prod,
            cve_clie=cve_clie,
            cve_vend=cve_vend,
            cve_linea=cve_linea if cve_linea else None,
            id_unidad_negocio=id_unidad_negocio,
            estatus_match=estatus_match,
            observaciones="|".join(observaciones) if observaciones else None,
        )

        if estatus_match == "ok":
            total_ok += 1
        else:
            total_error += 1

    actualizar_estatus_carga_presupuesto_ventas_model(
        id_carga=id_carga,
        estatus="validado",
        comentarios=f"ok={total_ok}, error={total_error}",
    )

    return {
        "id_carga": id_carga,
        "total_ok": total_ok,
        "total_error": total_error,
        "resumen": obtener_resumen_staging_presupuesto_ventas_model(id_carga=id_carga),
    }


def asignar_unidad_negocio_staging_presupuesto_ventas_ctrl(
    id_carga: int,
    id_unidad_negocio: int,
    filtro_unidad_negocio_excel: Optional[str] = None,
) -> int:
    staging = obtener_staging_presupuesto_ventas_model(
        id_carga=id_carga,
        limit=200000,
    )

    if staging.empty:
        return 0

    total_actualizados = 0
    filtro = _clean_upper(filtro_unidad_negocio_excel)

    for _, row in staging.iterrows():
        unidad_negocio_excel = _clean_upper(row.get("unidad_negocio_excel"))

        if filtro and unidad_negocio_excel != filtro:
            continue

        actualizar_match_staging_presupuesto_ventas_model(
            id_staging=int(row["id_staging"]),
            id_unidad_negocio=int(id_unidad_negocio),
        )
        total_actualizados += 1

    return total_actualizados


def confirmar_importacion_presupuesto_ventas_ctrl(
    id_carga: int,
    usuario_id: int,
    reemplazar_existentes: bool = False,
) -> dict:
    total_insertados = insertar_presupuesto_desde_staging_model(
        id_carga=id_carga,
        usuario_id=usuario_id,
        solo_estatus_match="completo",
        reemplazar_existentes=reemplazar_existentes,
    )

    actualizar_estatus_carga_presupuesto_ventas_model(
        id_carga=id_carga,
        estatus="importado",
        comentarios=f"total_insertados={total_insertados}",
    )

    return {
        "id_carga": id_carga,
        "total_insertados": total_insertados,
    }

def eliminar_carga_completa_presupuesto_ventas_ctrl(id_carga: int) -> dict:
    eliminar_presupuesto_ventas_por_carga_model(id_carga)
    eliminar_staging_por_carga_presupuesto_ventas_model(id_carga)
    eliminar_carga_presupuesto_ventas_model(id_carga)
    return {"id_carga": id_carga, "eliminado": True}


def obtener_cargas_presupuesto_ventas_ctrl(
    anio: Optional[int] = None,
    id_carga: Optional[int] = None,
    limit: int = 100,
    usuario_id: int = None,
) -> pd.DataFrame:
    return obtener_cargas_presupuesto_ventas_model(
        anio=anio,
        id_carga=id_carga,
        limit=limit,
        usuario_id=usuario_id,
    )


def obtener_staging_presupuesto_ventas_ctrl(
    id_carga: Optional[int] = None,
    estatus_match: Optional[str] = None,
    anio: Optional[int] = None,
    mes: Optional[int] = None,
    id_producto: Optional[int] = None,
    id_cliente: Optional[int] = None,
    id_vendedor: Optional[int] = None,
    id_unidad_negocio: Optional[int] = None,
    limit: int = 5000,
) -> pd.DataFrame:
    return obtener_staging_presupuesto_ventas_model(
        id_carga=id_carga,
        estatus_match=estatus_match,
        anio=anio,
        mes=mes,
        id_producto=id_producto,
        id_cliente=id_cliente,
        id_vendedor=id_vendedor,
        id_unidad_negocio=id_unidad_negocio,
        limit=limit,
    )


def obtener_resumen_staging_presupuesto_ventas_ctrl(
    id_carga: int,
) -> pd.DataFrame:
    return obtener_resumen_staging_presupuesto_ventas_model(id_carga=id_carga)


def obtener_presupuesto_ventas_ctrl(
    anio: Optional[int] = None,
    mes: Optional[int] = None,
    id_unidad_negocio: Optional[int] = None,
    cve_linea: Optional[str] = None,
    cve_vend: Optional[str] = None,
    cve_clie: Optional[str] = None,
    cve_prod: Optional[str] = None,
    id_carga: Optional[int] = None,
    estatus: str = "activo",
    limit: int = 10000,
) -> pd.DataFrame:
    return obtener_presupuesto_ventas_model(
        anio=anio,
        mes=mes,
        id_unidad_negocio=id_unidad_negocio,
        cve_linea=cve_linea,
        cve_vend=cve_vend,
        cve_clie=cve_clie,
        cve_prod=cve_prod,
        id_carga=id_carga,
        estatus=estatus,
        limit=limit,
    )


def obtener_resumen_presupuesto_ventas_ctrl(
    anio: Optional[int] = None,
    id_unidad_negocio: Optional[int] = None,
    cve_vend: Optional[str] = None,
    cve_clie: Optional[str] = None,
    cve_prod: Optional[str] = None,
    estatus: str = "activo",
) -> pd.DataFrame:
    return obtener_resumen_presupuesto_ventas_model(
        anio=anio,
        id_unidad_negocio=id_unidad_negocio,
        cve_vend=cve_vend,
        cve_clie=cve_clie,
        cve_prod=cve_prod,
        estatus=estatus,
    )

def asignar_clave_producto_staging_presupuesto_ventas_ctrl(
    id_carga: int,
    producto_excel: str,
    cve_prod: str,
    cve_linea: Optional[str] = None,
) -> int:
    staging = obtener_staging_presupuesto_ventas_model(id_carga=id_carga, limit=200000)

    if staging.empty:
        return 0

    producto_excel_buscar = _clean_upper(producto_excel)
    total_actualizados = 0

    for _, row in staging.iterrows():
        if _clean_upper(row.get("producto_excel")) != producto_excel_buscar:
            continue

        actualizar_match_staging_presupuesto_ventas_model(
            id_staging=int(row["id_staging"]),
            cve_prod=str(cve_prod).strip(),
            cve_linea=str(cve_linea).strip() if cve_linea else None,
        )
        total_actualizados += 1

    return total_actualizados


def asignar_clave_cliente_staging_presupuesto_ventas_ctrl(
    id_carga: int,
    cliente_excel: str,
    cve_clie: str,
) -> int:
    staging = obtener_staging_presupuesto_ventas_model(id_carga=id_carga, limit=200000)

    if staging.empty:
        return 0

    buscar = _clean_upper(cliente_excel)
    total = 0

    for _, row in staging.iterrows():
        if _clean_upper(row.get("cliente_excel")) != buscar:
            continue
        actualizar_match_staging_presupuesto_ventas_model(
            id_staging=int(row["id_staging"]),
            cve_clie=str(cve_clie).strip(),
        )
        total += 1

    return total


def asignar_clave_vendedor_staging_presupuesto_ventas_ctrl(
    id_carga: int,
    vendedor_excel: str,
    cve_vend: str,
) -> int:
    staging = obtener_staging_presupuesto_ventas_model(id_carga=id_carga, limit=200000)

    if staging.empty:
        return 0

    buscar = _clean_upper(vendedor_excel)
    total = 0

    for _, row in staging.iterrows():
        if _clean_upper(row.get("vendedor_excel")) != buscar:
            continue
        actualizar_match_staging_presupuesto_ventas_model(
            id_staging=int(row["id_staging"]),
            cve_vend=str(cve_vend).strip(),
        )
        total += 1

    return total


def asignar_clave_linea_staging_presupuesto_ventas_ctrl(
    id_carga: int,
    linea_excel: str,
    cve_linea: str,
) -> int:
    staging = obtener_staging_presupuesto_ventas_model(id_carga=id_carga, limit=200000)

    if staging.empty:
        return 0

    buscar = _clean_upper(linea_excel)
    total = 0

    for _, row in staging.iterrows():
        if _clean_upper(row.get("linea_excel")) != buscar:
            continue
        actualizar_match_staging_presupuesto_ventas_model(
            id_staging=int(row["id_staging"]),
            cve_linea=str(cve_linea).strip(),
        )
        total += 1

    return total


def actualizar_cantidad_staging_presupuesto_ventas_ctrl(
    id_staging: int,
    cantidad_kg: Optional[float] = None,
    importe: Optional[float] = None,
    precio: Optional[float] = None,
    valor: Optional[float] = None,
) -> bool:
    return actualizar_cantidad_staging_presupuesto_ventas_model(
        id_staging=id_staging,
        cantidad_kg=cantidad_kg,
        importe=importe,
        precio=precio,
        valor=valor,
    )


def obtener_productos_sae_presupuesto_ventas_ctrl(
    cve_art: Optional[str] = None,
    descr: Optional[str] = None,
    limit: int = 5000,
) -> pd.DataFrame:
    return obtener_productos_sae_model(cve_art=cve_art, descr=descr, limit=limit)


def obtener_clientes_sae_presupuesto_ventas_ctrl(
    clave: Optional[str] = None,
    nombre: Optional[str] = None,
    limit: int = 5000,
) -> pd.DataFrame:
    return obtener_clientes_sae_model(clave=clave, nombre=nombre, limit=limit)


def obtener_vendedores_sae_presupuesto_ventas_ctrl(
    cve_vend: Optional[str] = None,
    nombre: Optional[str] = None,
    limit: int = 1000,
) -> pd.DataFrame:
    return obtener_vendedores_sae_model(cve_vend=cve_vend, nombre=nombre, limit=limit)


def obtener_lineas_sae_presupuesto_ventas_ctrl(
    cve_lin: Optional[str] = None,
    desc_lin: Optional[str] = None,
    limit: int = 500,
) -> pd.DataFrame:
    return obtener_lineas_sae_model(cve_lin=cve_lin, desc_lin=desc_lin, limit=limit)

def recalcular_estatus_staging_presupuesto_ventas_ctrl(id_carga: int) -> dict:
    staging = obtener_staging_presupuesto_ventas_model(
        id_carga=id_carga,
        limit=200000,
    )

    if staging.empty:
        return {"id_carga": id_carga, "total_completo": 0, "total_pendiente": 0}

    total_completo = 0
    total_pendiente = 0

    for _, row in staging.iterrows():
        id_staging = int(row["id_staging"])

        id_unidad_negocio = row.get("id_unidad_negocio")
        cve_prod = row.get("cve_prod")
        id_producto = row.get("id_producto")

        tiene_unidad = not pd.isna(id_unidad_negocio) and id_unidad_negocio not in ("", None)
        tiene_producto = (
            (not pd.isna(cve_prod) and cve_prod not in ("", None))
            or (not pd.isna(id_producto) and id_producto not in ("", None))
        )

        if tiene_unidad and tiene_producto:
            estatus = "completo"
            observaciones = None
            total_completo += 1
        else:
            estatus = "pendiente"
            faltantes = []
            if not tiene_unidad:
                faltantes.append("falta_unidad_negocio")
            if not tiene_producto:
                faltantes.append("falta_producto")
            observaciones = "|".join(faltantes)
            total_pendiente += 1

        actualizar_match_staging_presupuesto_ventas_model(
            id_staging=id_staging,
            estatus_match=estatus,
            observaciones=observaciones,
        )

    actualizar_estatus_carga_presupuesto_ventas_model(
        id_carga=id_carga,
        estatus="complementado",
        comentarios=f"completo={total_completo}, pendiente={total_pendiente}",
    )

    return {
        "id_carga": id_carga,
        "total_completo": total_completo,
        "total_pendiente": total_pendiente,
    }

def detectar_tablas_presupuesto_ventas_ctrl(archivo, hoja: str) -> list[dict]:
    return detectar_tablas_presupuesto_excel(archivo, hoja)


def obtener_preview_presupuesto_ventas_dinamico_ctrl(
    archivo,
    hoja: str,
    anio: int,
    limit: int = 100,
) -> dict:
    df_norm, tablas = normalizar_presupuesto_excel_dinamico(
        archivo=archivo,
        hoja=hoja,
        anio=anio,
    )

    return {
        "hoja": hoja,
        "tablas": tablas,
        "preview": df_norm.head(limit).copy(),
        "total_registros": len(df_norm),
    }

# ── carga directa sin staging ─────────────────────────────────────────────────

def cargar_excel_directo_presupuesto_ventas_ctrl(
    archivo,
    nombre_archivo: str,
    hoja: str,
    anio: int,
    usuario_id: int,
    version: Optional[str] = None,
    comentarios: Optional[str] = None,
    reemplazar: bool = True,
) -> dict:
    if not hoja:
        raise ValueError("Debes seleccionar una hoja del archivo Excel.")

    archivo.seek(0)
    df_norm, tablas = normalizar_presupuesto_excel_auto(
        archivo=archivo,
        hoja=hoja,
        anio=int(anio),
    )

    if df_norm is None or df_norm.empty:
        raise ValueError("No se generaron registros para cargar.")

    id_carga = insertar_carga_presupuesto_ventas_model(
        nombre_archivo=nombre_archivo,
        hoja_origen=hoja,
        anio=anio,
        version=version,
        comentarios=comentarios,
        usuario_id=usuario_id,
    )

    if reemplazar:
        eliminar_presupuesto_ventas_por_carga_model(id_carga)

    total = insertar_presupuesto_ventas_desde_df_model(
        id_carga=id_carga,
        usuario_id=usuario_id,
        df=df_norm,
    )

    actualizar_estatus_carga_presupuesto_ventas_model(
        id_carga=id_carga,
        estatus="activo",
        comentarios=f"total={total}",
    )

    return {
        "id_carga": id_carga,
        "hoja": hoja,
        "tablas_detectadas": len(tablas),
        "total_registros": total,
    }


def obtener_presupuesto_ventas_ctrl(
    id_carga: Optional[int] = None,
    anio: Optional[int] = None,
    mes: Optional[int] = None,
    seccion: Optional[str] = None,
    region: Optional[str] = None,
    limit: int = 200000,
) -> pd.DataFrame:
    df = obtener_presupuesto_ventas_model(
        id_carga=id_carga,
        anio=anio,
        mes=mes,
        limit=limit,
    )
    if df is None or df.empty:
        return df
    if seccion and "seccion" in df.columns:
        df = df[df["seccion"].astype(str) == seccion]
    if region and "region" in df.columns:
        df = df[df["region"].astype(str) == region]
    return df.reset_index(drop=True)


def insertar_presupuesto_ventas_unitario_ctrl(
    id_carga: int,
    seccion: str,
    region: Optional[str],
    anio: int,
    mes: int,
    company: Optional[str],
    cliente_excel: Optional[str],
    codigo_origen: Optional[str],
    producto_excel: str,
    cve_prod: Optional[str],
    estatus_excel: Optional[str],
    precio: float,
    valor: float,
    cantidad_kg: float,
    importe: float,
    usuario_id: int,
) -> int:
    return insertar_presupuesto_ventas_unitario_model(
        id_carga=id_carga,
        seccion=seccion,
        region=region,
        anio=anio,
        mes=mes,
        company=company,
        cliente_excel=cliente_excel,
        codigo_origen=codigo_origen,
        producto_excel=producto_excel,
        cve_prod=cve_prod,
        estatus_excel=estatus_excel,
        precio=precio,
        valor=valor,
        cantidad_kg=cantidad_kg,
        importe=importe,
        usuario_id=usuario_id,
    )


def actualizar_presupuesto_ventas_ctrl(
    id_presupuesto: int,
    valor: Optional[float] = None,
    precio: Optional[float] = None,
    cantidad_kg: Optional[float] = None,
    importe: Optional[float] = None,
    cliente_excel: Optional[str] = None,
    producto_excel: Optional[str] = None,
    company: Optional[str] = None,
    codigo_origen: Optional[str] = None,
    comentario: Optional[str] = None,
    estatus_excel: Optional[str] = None,
) -> bool:
    return actualizar_presupuesto_ventas_model(
        id_presupuesto=id_presupuesto,
        valor=valor,
        precio=precio,
        cantidad_kg=cantidad_kg,
        importe=importe,
        cliente_excel=cliente_excel,
        producto_excel=producto_excel,
        company=company,
        codigo_origen=codigo_origen,
        comentario=comentario,
        estatus_excel=estatus_excel,
    )


def eliminar_registro_presupuesto_ventas_ctrl(
    id_carga: int,
    seccion: str,
    region: Optional[str],
    producto_excel: str,
    cliente_excel: Optional[str] = None,
    codigo_origen: Optional[str] = None,
    company: Optional[str] = None,
) -> int:
    """Elimina un registro completo (todos sus meses) de la tabla presupuesto."""
    return eliminar_presupuesto_ventas_por_registro_model(
        id_carga=id_carga,
        seccion=seccion,
        region=region,
        producto_excel=producto_excel,
        cliente_excel=cliente_excel,
        codigo_origen=codigo_origen,
        company=company,
    )


def guardar_presupuesto_ventas_batch_ctrl(
    inserts: list[dict],
    updates: list[dict],
    cve_prod_updates: list[dict],
    identidad_updates: Optional[list[dict]] = None,
) -> dict:
    return guardar_presupuesto_ventas_batch_model(
        inserts=inserts,
        updates=updates,
        cve_prod_updates=cve_prod_updates,
        identidad_updates=identidad_updates or [],
    )


def actualizar_cve_prod_presupuesto_ventas_ctrl(
    id_carga: int,
    producto_excel: str,
    cliente_excel: Optional[str],
    codigo_origen: Optional[str],
    company: Optional[str],
    cve_prod: Optional[str],
) -> int:
    return actualizar_cve_prod_presupuesto_ventas_model(
        id_carga=id_carga,
        producto_excel=producto_excel,
        cliente_excel=cliente_excel,
        codigo_origen=codigo_origen,
        company=company,
        cve_prod=cve_prod,
    )


@st.cache_data(ttl=3600, show_spinner="cargando catálogo SAE…")
def obtener_catalogo_productos_pv_ctrl() -> pd.DataFrame:
    try:
        return obtener_catalogo_productos_pv_model()
    except Exception:
        return pd.DataFrame(columns=["cve_prod", "descr", "cve_linea", "linea", "precio", "codigo_origen", "unidad"])


@st.cache_data(ttl=3600, show_spinner=False)
def obtener_ultimo_precio_venta_ctrl(cve_art: str, cve_clie: Optional[str] = None) -> float:
    """Precio de respaldo cuando el precio público (tabla de precios x art) es 0:
    el último precio de venta en facturas cruzado con el cliente si se conoce,
    o el último precio de venta a cualquier cliente si no."""
    try:
        if cve_clie:
            precio = obtener_ultimo_precio_venta_sae_model(cve_art=cve_art, cve_clie=cve_clie)
            if precio:
                return precio
        return obtener_ultimo_precio_venta_sae_model(cve_art=cve_art) or 0.0
    except Exception:
        return 0.0


@st.cache_data(ttl=3600, show_spinner="cargando catálogo de clientes SAE…")
def obtener_catalogo_clientes_pv_ctrl() -> pd.DataFrame:
    """Mismo catálogo de clientes SAE que consume el módulo de Solicitudes
    (buscar_clientes_sae_ctrl) — se reutiliza aquí para no mantener una
    segunda fuente de verdad."""
    try:
        return pd.DataFrame(buscar_clientes_sae_ctrl(q="", limit=5000))
    except Exception:
        return pd.DataFrame(columns=["clave", "nombre", "rfc", "calle", "municipio", "estado"])


@st.cache_data(ttl=3600, show_spinner="cargando existencias SAE…")
def obtener_existencias_productos_pv_ctrl() -> pd.DataFrame:
    try:
        return obtener_existencias_productos_sae_model()
    except Exception:
        return pd.DataFrame(columns=[
            "cve_art", "descr", "lin_prod", "linea", "uni_med",
            "existencia", "peso", "costo_prom", "ult_costo", "status",
        ])


@st.cache_data(ttl=900, show_spinner="cargando órdenes de compra pendientes SAE…")
def obtener_ordenes_compra_pendientes_pv_ctrl() -> pd.DataFrame:
    try:
        return obtener_ordenes_compra_pendientes_sae_model()
    except Exception:
        return pd.DataFrame(columns=[
            "cve_doc", "serie", "folio", "fecha_doc", "fecha_rec",
            "cve_prov", "proveedor", "cve_art", "producto", "cve_linea", "linea",
            "cantidad", "unidad", "precio",
        ])


# ── autorización por línea ──────────────────────────────────────────────────

def upsert_presupuesto_ventas_linea_ctrl(
    id_carga: int,
    company: Optional[str],
    cliente_excel: Optional[str],
    codigo_origen: Optional[str],
    producto_excel: str,
    estatus: str,
    usuario_id: int,
) -> tuple[int, Optional[str]]:
    return upsert_presupuesto_ventas_linea_model(
        id_carga=id_carga,
        company=company,
        cliente_excel=cliente_excel,
        codigo_origen=codigo_origen,
        producto_excel=producto_excel,
        estatus=estatus,
        usuario_id=usuario_id,
    )


def insertar_presupuesto_ventas_linea_estatus_ctrl(
    linea_id: int,
    estatus_anterior: Optional[str],
    estatus_nuevo: str,
    usuario_id: Optional[int],
    usuario_nombre: Optional[str],
    usuario_email: Optional[str],
    comentario: Optional[str],
) -> int:
    return insertar_presupuesto_ventas_linea_estatus_model(
        linea_id=linea_id,
        estatus_anterior=estatus_anterior,
        estatus_nuevo=estatus_nuevo,
        usuario_id=usuario_id,
        usuario_nombre=usuario_nombre,
        usuario_email=usuario_email,
        comentario=comentario,
    )


def obtener_presupuesto_ventas_lineas_ctrl(id_carga: int) -> pd.DataFrame:
    return obtener_presupuesto_ventas_lineas_model(id_carga)


def obtener_presupuesto_ventas_lineas_pendientes_ctrl() -> pd.DataFrame:
    return obtener_presupuesto_ventas_lineas_pendientes_model()
