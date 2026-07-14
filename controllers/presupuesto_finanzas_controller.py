from __future__ import annotations

from typing import Optional

import pandas as pd
import streamlit as st

from models.presupuesto_finanzas_model import (
    insertar_carga_presupuesto_finanzas_model,
    actualizar_total_filas_carga_presupuesto_finanzas_model,
    obtener_cargas_presupuesto_finanzas_model,
    eliminar_carga_presupuesto_finanzas_model,
    insertar_presupuesto_finanzas_desde_df_model,
    obtener_presupuesto_finanzas_model,
    obtener_opciones_filtro_presupuesto_finanzas_model,
    actualizar_clave_producto_sku_model,
)
from models.presupuesto_ventas_sae_model import obtener_mapa_cve_original_sae_model
from utils.presupuesto_finanzas_excel_parser import (
    obtener_hojas_presupuesto_finanzas,
    parsear_excel_presupuesto_finanzas,
)


@st.cache_data(ttl=1800, show_spinner="cargando catálogo SAE de claves originales…")
def _mapa_cve_original_sae() -> dict[str, str]:
    """dict {cve_original: cve_prod} desde INVE_CLIB01, normalizado (strip/upper)."""
    try:
        df = obtener_mapa_cve_original_sae_model()
    except Exception:
        return {}
    if df is None or df.empty:
        return {}
    df = df.dropna(subset=["cve_original", "cve_prod"])
    return {
        str(o).strip().upper(): str(p).strip()
        for o, p in zip(df["cve_original"], df["cve_prod"])
        if str(o).strip()
    }


def _corregir_clave_producto_sku(df: pd.DataFrame) -> pd.DataFrame:
    """Sustituye clave_producto_sku por el CVE_PROD correcto de SAE (INVE_CLIB01)
    cuando la clave importada coincide con un CVE_ORIGINAL. Si no hay coincidencia,
    conserva la clave tal cual venía."""
    if df is None or df.empty or "clave_producto_sku" not in df.columns:
        return df
    mapa = _mapa_cve_original_sae()
    if not mapa:
        return df
    df = df.copy()
    df["clave_producto_sku"] = df["clave_producto_sku"].map(
        lambda v: mapa.get(str(v).strip().upper(), v)
    )
    return df


_MESES = {1: "ENERO", 2: "FEBRERO", 3: "MARZO", 4: "ABRIL", 5: "MAYO", 6: "JUNIO",
          7: "JULIO", 8: "AGOSTO", 9: "SEPTIEMBRE", 10: "OCTUBRE", 11: "NOVIEMBRE", 12: "DICIEMBRE"}


def obtener_hojas_presupuesto_finanzas_ctrl(archivo) -> list[str]:
    try:
        return obtener_hojas_presupuesto_finanzas(archivo)
    except Exception:
        return []


def cargar_excel_presupuesto_finanzas_ctrl(
    archivo,
    nombre_archivo: str,
    hoja: str,
    anio: int,
    usuario_id: int,
    version: Optional[str] = None,
    comentarios: Optional[str] = None,
) -> dict:
    df = parsear_excel_presupuesto_finanzas(archivo, hoja=hoja, anio=anio)
    if df.empty:
        raise ValueError("no se encontraron registros en la hoja seleccionada")

    df = _corregir_clave_producto_sku(df)

    id_carga = insertar_carga_presupuesto_finanzas_model(
        nombre_archivo=nombre_archivo,
        hoja_origen=hoja,
        anio=anio,
        version=version,
        comentarios=comentarios,
        usuario_id=usuario_id,
    )
    total = insertar_presupuesto_finanzas_desde_df_model(id_carga=id_carga, usuario_id=usuario_id, df=df)
    actualizar_total_filas_carga_presupuesto_finanzas_model(id_carga=id_carga, total_filas=total)

    return {"id_carga": id_carga, "total_registros": total}


def obtener_cargas_presupuesto_finanzas_ctrl(
    anio: Optional[int] = None,
    usuario_id: Optional[int] = None,
    limit: int = 100,
) -> pd.DataFrame:
    return obtener_cargas_presupuesto_finanzas_model(anio=anio, usuario_id=usuario_id, limit=limit)


def eliminar_carga_presupuesto_finanzas_ctrl(id_carga: int) -> bool:
    return eliminar_carga_presupuesto_finanzas_model(id_carga)


def corregir_codigos_producto_presupuesto_finanzas_ctrl(id_carga: int) -> int:
    """Corrige, para una carga ya existente, las claves_producto_sku que coincidan
    con un CVE_ORIGINAL en SAE (INVE_CLIB01), reemplazándolas por el CVE_PROD correcto."""
    opciones = obtener_opciones_filtro_presupuesto_finanzas_model(id_carga)
    claves_actuales = opciones.get("claves_producto") or []
    if not claves_actuales:
        return 0

    mapa_sae = _mapa_cve_original_sae()
    if not mapa_sae:
        return 0

    mapa_aplicar = {
        clave: mapa_sae[str(clave).strip().upper()]
        for clave in claves_actuales
        if str(clave).strip().upper() in mapa_sae
    }
    return actualizar_clave_producto_sku_model(id_carga, mapa_aplicar)


def obtener_opciones_filtro_presupuesto_finanzas_ctrl(id_carga: int) -> dict[str, list]:
    return obtener_opciones_filtro_presupuesto_finanzas_model(id_carga)


def obtener_presupuesto_finanzas_filtrado_ctrl(
    id_carga: int,
    vendedores: Optional[list[str]] = None,
    clientes: Optional[list[str]] = None,
    claves_producto: Optional[list[str]] = None,
    meses: Optional[list[int]] = None,
    anios: Optional[list[int]] = None,
    areas: Optional[list[str]] = None,
    volumen_min: Optional[float] = None,
    volumen_max: Optional[float] = None,
    dolares_min: Optional[float] = None,
    dolares_max: Optional[float] = None,
) -> pd.DataFrame:
    df = obtener_presupuesto_finanzas_model(
        id_carga=id_carga,
        vendedores=vendedores or None,
        clientes=clientes or None,
        claves_producto=claves_producto or None,
        meses=meses or None,
        anios=anios or None,
        areas=areas or None,
    )
    if df is None or df.empty:
        return df

    df["volumen"] = pd.to_numeric(df["volumen"], errors="coerce").fillna(0.0)
    df["dolares"] = pd.to_numeric(df["dolares"], errors="coerce").fillna(0.0)

    if volumen_min is not None:
        df = df[df["volumen"] >= float(volumen_min)]
    if volumen_max is not None:
        df = df[df["volumen"] <= float(volumen_max)]
    if dolares_min is not None:
        df = df[df["dolares"] >= float(dolares_min)]
    if dolares_max is not None:
        df = df[df["dolares"] <= float(dolares_max)]

    return df


def construir_tabla_pivot_presupuesto_finanzas_ctrl(df: pd.DataFrame) -> pd.DataFrame:
    """
    Replica el formato de las hojas de ejemplo (p.ej. "ROGELIO 2026"):
    una fila por cliente/producto con volumen y dólares desglosados por mes.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()
    df["mes"] = pd.to_numeric(df["mes"], errors="coerce").fillna(0).astype(int)
    df["volumen"] = pd.to_numeric(df["volumen"], errors="coerce").fillna(0.0)
    df["dolares"] = pd.to_numeric(df["dolares"], errors="coerce").fillna(0.0)

    llave = ["clave_cliente", "nombre_cliente", "clave_producto_sku", "producto",
             "area", "vendedor", "precio_unitario_dolares", "tipo"]

    filas: list[dict] = []
    for valores, grupo in df.groupby(llave, dropna=False):
        fila = dict(zip(llave, valores))
        total_vol = 0.0
        total_dol = 0.0
        for m in range(1, 13):
            sub = grupo[grupo["mes"] == m]
            vol = float(sub["volumen"].sum())
            dol = float(sub["dolares"].sum())
            fila[f"{_MESES[m]}_volumen"] = vol
            fila[f"{_MESES[m]}_dolares"] = dol
            total_vol += vol
            total_dol += dol
        fila["TOTAL_volumen"] = total_vol
        fila["TOTAL_dolares"] = total_dol
        filas.append(fila)

    return pd.DataFrame(filas)
