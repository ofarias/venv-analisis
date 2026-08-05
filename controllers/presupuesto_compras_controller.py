from __future__ import annotations

from typing import Optional

import pandas as pd
import streamlit as st

from models.presupuesto_compras_model import (
    actualizar_cve_prod_presupuesto_compras_model,
    actualizar_estatus_carga_presupuesto_compras_model,
    actualizar_presupuesto_compras_model,
    eliminar_carga_presupuesto_compras_model,
    eliminar_presupuesto_compras_por_carga_model,
    eliminar_presupuesto_compras_por_registro_model,
    guardar_presupuesto_compras_batch_model,
    insertar_carga_presupuesto_compras_model,
    insertar_presupuesto_compras_desde_df_model,
    insertar_presupuesto_compras_unitario_model,
    insertar_presupuesto_compras_linea_estatus_model,
    obtener_cargas_presupuesto_compras_model,
    obtener_presupuesto_compras_lineas_model,
    obtener_presupuesto_compras_lineas_pendientes_model,
    obtener_presupuesto_compras_model,
    upsert_presupuesto_compras_linea_model,
)
from models.presupuesto_ventas_sae_model import (
    obtener_catalogo_productos_pv_model,
    obtener_existencias_productos_sae_model,
    obtener_ordenes_compra_pendientes_sae_model,
)
from controllers.solicitudes_controller import buscar_clientes_sae_ctrl
from utils.presupuesto_compras_excel_parser import normalizar_presupuesto_compras_excel_auto


def registrar_carga_presupuesto_compras_ctrl(
    nombre_archivo: str,
    hoja_origen: str,
    anio: int,
    version: Optional[str],
    comentarios: Optional[str],
    usuario_id: int,
) -> int:
    return insertar_carga_presupuesto_compras_model(
        nombre_archivo=nombre_archivo,
        hoja_origen=hoja_origen,
        anio=anio,
        version=version,
        comentarios=comentarios,
        usuario_id=usuario_id,
    )


def cargar_excel_directo_presupuesto_compras_ctrl(
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
    df_norm, tablas = normalizar_presupuesto_compras_excel_auto(
        archivo=archivo,
        hoja=hoja,
        anio=int(anio),
    )

    if df_norm is None or df_norm.empty:
        raise ValueError("No se generaron registros para cargar.")

    id_carga = insertar_carga_presupuesto_compras_model(
        nombre_archivo=nombre_archivo,
        hoja_origen=hoja,
        anio=anio,
        version=version,
        comentarios=comentarios,
        usuario_id=usuario_id,
    )

    if reemplazar:
        eliminar_presupuesto_compras_por_carga_model(id_carga)

    total = insertar_presupuesto_compras_desde_df_model(
        id_carga=id_carga,
        usuario_id=usuario_id,
        df=df_norm,
    )

    actualizar_estatus_carga_presupuesto_compras_model(
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


def obtener_cargas_presupuesto_compras_ctrl(
    anio: Optional[int] = None,
    id_carga: Optional[int] = None,
    limit: int = 100,
    usuario_id: int = None,
) -> pd.DataFrame:
    return obtener_cargas_presupuesto_compras_model(
        anio=anio,
        id_carga=id_carga,
        limit=limit,
        usuario_id=usuario_id,
    )


def obtener_presupuesto_compras_ctrl(
    id_carga: Optional[int] = None,
    anio: Optional[int] = None,
    mes: Optional[int] = None,
    seccion: Optional[str] = None,
    region: Optional[str] = None,
    limit: int = 200000,
) -> pd.DataFrame:
    df = obtener_presupuesto_compras_model(
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


def insertar_presupuesto_compras_unitario_ctrl(
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
    return insertar_presupuesto_compras_unitario_model(
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


def actualizar_presupuesto_compras_ctrl(
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
    return actualizar_presupuesto_compras_model(
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


def eliminar_registro_presupuesto_compras_ctrl(
    id_carga: int,
    seccion: str,
    region: Optional[str],
    producto_excel: str,
    cliente_excel: Optional[str] = None,
    codigo_origen: Optional[str] = None,
    company: Optional[str] = None,
) -> int:
    """Elimina un registro completo (todos sus meses) de la tabla presupuesto."""
    return eliminar_presupuesto_compras_por_registro_model(
        id_carga=id_carga,
        seccion=seccion,
        region=region,
        producto_excel=producto_excel,
        cliente_excel=cliente_excel,
        codigo_origen=codigo_origen,
        company=company,
    )


def guardar_presupuesto_compras_batch_ctrl(
    inserts: list[dict],
    updates: list[dict],
    cve_prod_updates: list[dict],
    identidad_updates: Optional[list[dict]] = None,
) -> dict:
    return guardar_presupuesto_compras_batch_model(
        inserts=inserts,
        updates=updates,
        cve_prod_updates=cve_prod_updates,
        identidad_updates=identidad_updates or [],
    )


def actualizar_cve_prod_presupuesto_compras_ctrl(
    id_carga: int,
    producto_excel: str,
    cliente_excel: Optional[str],
    codigo_origen: Optional[str],
    company: Optional[str],
    cve_prod: Optional[str],
) -> int:
    return actualizar_cve_prod_presupuesto_compras_model(
        id_carga=id_carga,
        producto_excel=producto_excel,
        cliente_excel=cliente_excel,
        codigo_origen=codigo_origen,
        company=company,
        cve_prod=cve_prod,
    )


def eliminar_carga_completa_presupuesto_compras_ctrl(id_carga: int) -> dict:
    eliminar_presupuesto_compras_por_carga_model(id_carga)
    eliminar_carga_presupuesto_compras_model(id_carga)
    return {"id_carga": id_carga, "eliminado": True}


@st.cache_data(ttl=3600, show_spinner="cargando catálogo SAE…")
def obtener_catalogo_productos_pv_compras_ctrl() -> pd.DataFrame:
    # mismo catálogo de productos SAE que usa presupuesto de ventas — los
    # productos son los mismos, no hay un catálogo distinto para compras
    try:
        return obtener_catalogo_productos_pv_model()
    except Exception:
        return pd.DataFrame(columns=["cve_prod", "descr", "cve_linea", "linea", "precio", "codigo_origen"])


@st.cache_data(ttl=3600, show_spinner="cargando catálogo de clientes SAE…")
def obtener_catalogo_clientes_pv_compras_ctrl() -> pd.DataFrame:
    """Mismo catálogo de clientes SAE que consume el módulo de Solicitudes
    (buscar_clientes_sae_ctrl) — se reutiliza aquí para no mantener una
    segunda fuente de verdad."""
    try:
        return pd.DataFrame(buscar_clientes_sae_ctrl(q="", limit=5000))
    except Exception:
        return pd.DataFrame(columns=["clave", "nombre", "rfc", "calle", "municipio", "estado"])


@st.cache_data(ttl=3600, show_spinner="cargando existencias SAE…")
def obtener_existencias_productos_pv_compras_ctrl() -> pd.DataFrame:
    try:
        return obtener_existencias_productos_sae_model()
    except Exception:
        return pd.DataFrame(columns=[
            "cve_art", "descr", "lin_prod", "linea", "uni_med",
            "existencia", "peso", "costo_prom", "ult_costo", "status",
        ])


@st.cache_data(ttl=900, show_spinner="cargando órdenes de compra pendientes SAE…")
def obtener_ordenes_compra_pendientes_pv_compras_ctrl() -> pd.DataFrame:
    try:
        return obtener_ordenes_compra_pendientes_sae_model()
    except Exception:
        return pd.DataFrame(columns=[
            "cve_doc", "serie", "folio", "fecha_doc", "fecha_rec",
            "cve_prov", "proveedor", "cve_art", "producto", "cve_linea", "linea",
            "cantidad", "unidad", "precio",
        ])


# ── autorización por línea ──────────────────────────────────────────────────

def upsert_presupuesto_compras_linea_ctrl(
    id_carga: int,
    company: Optional[str],
    cliente_excel: Optional[str],
    codigo_origen: Optional[str],
    producto_excel: str,
    estatus: str,
    usuario_id: int,
) -> tuple[int, Optional[str]]:
    return upsert_presupuesto_compras_linea_model(
        id_carga=id_carga,
        company=company,
        cliente_excel=cliente_excel,
        codigo_origen=codigo_origen,
        producto_excel=producto_excel,
        estatus=estatus,
        usuario_id=usuario_id,
    )


def insertar_presupuesto_compras_linea_estatus_ctrl(
    linea_id: int,
    estatus_anterior: Optional[str],
    estatus_nuevo: str,
    usuario_id: Optional[int],
    usuario_nombre: Optional[str],
    usuario_email: Optional[str],
    comentario: Optional[str],
) -> int:
    return insertar_presupuesto_compras_linea_estatus_model(
        linea_id=linea_id,
        estatus_anterior=estatus_anterior,
        estatus_nuevo=estatus_nuevo,
        usuario_id=usuario_id,
        usuario_nombre=usuario_nombre,
        usuario_email=usuario_email,
        comentario=comentario,
    )


def obtener_presupuesto_compras_lineas_ctrl(id_carga: int) -> pd.DataFrame:
    return obtener_presupuesto_compras_lineas_model(id_carga)


def obtener_presupuesto_compras_lineas_pendientes_ctrl() -> pd.DataFrame:
    return obtener_presupuesto_compras_lineas_pendientes_model()
