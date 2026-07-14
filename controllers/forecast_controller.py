from __future__ import annotations

from typing import Optional
import pandas as pd
import streamlit as st

from models.forecast_model import (
    actualizar_estatus_forecast_version_model,
    eliminar_forecast_version_model,
    eliminar_forecast_detalle_por_version_model,
    insertar_alerta_forecast_model,
    insertar_forecast_version_model,
    limpiar_alertas_forecast_model,
    obtener_alertas_forecast_model,
    obtener_forecast_detalle_model,
    obtener_forecast_versiones_model,
    upsert_forecast_detalle_model,
)
from models.presupuesto_ventas_model import (
    obtener_presupuesto_ventas_model,
    obtener_resumen_presupuesto_ventas_model,
)
from models.presupuesto_finanzas_model import (
    obtener_presupuesto_finanzas_resumen_por_anio_model,
)
from models.presupuesto_ventas_sae_model import (
    obtener_catalogo_productos_pv_model,
    obtener_existencias_productos_sae_model,
    obtener_productos_sae_model,
    obtener_ventas_reales_resumen_sae_model,
)
from models.formulas_readonly_model import (
    listar_formulas_readonly_model,
    listar_materias_primas_readonly_model,
)
from models.formulas_model import listar_mp_sae_model, listar_pt_sae_model
from utils.forecast_engine import (
    calcular_mdi_producto,
    generar_propuesta_forecast,
)


# ── versiones ─────────────────────────────────────────────────────────────────

def crear_forecast_version_ctrl(
    anio: int,
    nombre: str,
    descripcion: Optional[str],
    id_carga_pv: Optional[int],
    metodo_default: str,
    usuario_id: int,
) -> int:
    return insertar_forecast_version_model(
        anio=anio,
        nombre=nombre,
        descripcion=descripcion,
        id_carga_pv=id_carga_pv,
        metodo_default=metodo_default,
        usuario_id=usuario_id,
    )


def obtener_forecast_versiones_ctrl(usuario_id: int, anio: Optional[int] = None) -> pd.DataFrame:
    return obtener_forecast_versiones_model(usuario_id=usuario_id, anio=anio)


def cambiar_estatus_version_ctrl(id_version: int, estatus: str) -> bool:
    return actualizar_estatus_forecast_version_model(id_version=id_version, estatus=estatus)


def eliminar_forecast_version_ctrl(id_version: int) -> bool:
    return eliminar_forecast_version_model(id_version=id_version)


# ── detalle ───────────────────────────────────────────────────────────────────

def guardar_forecast_fila_ctrl(
    id_version: int,
    seccion: str,
    region: Optional[str],
    cve_prod: Optional[str],
    producto_excel: Optional[str],
    anio: int,
    mes: int,
    forecast: float,
    justificacion: Optional[str],
    metodo: str,
    usuario_id: int,
    venta_real_mes_ant: float = 0.0,
    venta_real_prom_3m: float = 0.0,
    presupuesto_valor: float = 0.0,
) -> None:
    upsert_forecast_detalle_model(
        id_version=id_version,
        seccion=seccion,
        region=region,
        cve_prod=cve_prod,
        producto_excel=producto_excel,
        anio=anio,
        mes=mes,
        forecast=forecast,
        justificacion=justificacion,
        metodo=metodo,
        usuario_id=usuario_id,
        venta_real_mes_ant=venta_real_mes_ant,
        venta_real_prom_3m=venta_real_prom_3m,
        presupuesto_valor=presupuesto_valor,
    )


def obtener_forecast_detalle_ctrl(
    id_version: int,
    seccion: Optional[str] = None,
    region: Optional[str] = None,
) -> pd.DataFrame:
    return obtener_forecast_detalle_model(
        id_version=id_version, seccion=seccion, region=region
    )


_COLS_PRESUPUESTO_VACIO = ["cve_prod", "mes", "total_kg", "total_importe", "producto_excel"]


def _resumir_presupuesto(df_raw: pd.DataFrame, seccion: str, region: Optional[str]) -> pd.DataFrame:
    if df_raw is None or df_raw.empty:
        return pd.DataFrame(columns=_COLS_PRESUPUESTO_VACIO)

    for col in ("cantidad_kg", "importe", "valor"):
        if col in df_raw.columns:
            df_raw[col] = pd.to_numeric(df_raw[col], errors="coerce").fillna(0)

    if "seccion" in df_raw.columns:
        df_raw = df_raw[df_raw["seccion"].astype(str) == seccion]
    if region and "region" in df_raw.columns:
        df_raw = df_raw[df_raw["region"].astype(str) == region]

    if df_raw.empty:
        return pd.DataFrame(columns=_COLS_PRESUPUESTO_VACIO)

    return df_raw.groupby(["cve_prod", "mes"], dropna=False, as_index=False).agg(
        total_kg=("cantidad_kg", "sum"),
        total_importe=("importe", "sum"),
        producto_excel=("producto_excel", "first"),
    )


def obtener_presupuesto_resumen_ctrl(
    id_carga_pv: Optional[int],
    seccion: str,
    region: Optional[str],
) -> pd.DataFrame:
    """Presupuesto de ventas agregado por cve_prod × mes de UNA carga (usado al generar propuesta)."""
    if not id_carga_pv:
        return pd.DataFrame(columns=_COLS_PRESUPUESTO_VACIO)
    df_raw = obtener_presupuesto_ventas_model(id_carga=id_carga_pv)
    return _resumir_presupuesto(df_raw, seccion, region)


def obtener_presupuesto_resumen_por_anio_ctrl(
    anio: int,
    seccion: str,
    region: Optional[str],
) -> pd.DataFrame:
    """
    Presupuesto de ventas agregado por cve_prod × mes de TODAS las cargas activas del año
    (no depende de una carga en particular) — usado en el comparativo Real vs Forecast.
    """
    df_raw = obtener_presupuesto_ventas_model(anio=anio)
    return _resumir_presupuesto(df_raw, seccion, region)


@st.cache_data(ttl=900, show_spinner="cargando presupuesto de finanzas…")
def obtener_presupuesto_finanzas_resumen_por_anio_ctrl(anio: int) -> pd.DataFrame:
    """
    Presupuesto de finanzas agregado por cve_prod (clave SKU) × mes, de TODAS
    las cargas activas del año. No distingue región (MEXICO / CAM & Caribe) —
    se usa el mismo total en ambas regiones del comparativo Real vs Forecast.
    """
    df_raw = obtener_presupuesto_finanzas_resumen_por_anio_model(anio)
    if df_raw is None or df_raw.empty:
        return pd.DataFrame(columns=_COLS_PRESUPUESTO_VACIO)

    df = df_raw.rename(columns={"total_volumen": "total_kg", "total_dolares": "total_importe"})
    df["cve_prod"] = df["cve_prod"].astype(str).str.strip().str.upper()
    df["total_kg"] = pd.to_numeric(df["total_kg"], errors="coerce").fillna(0.0)
    df["total_importe"] = pd.to_numeric(df["total_importe"], errors="coerce").fillna(0.0)
    return df[_COLS_PRESUPUESTO_VACIO]


def generar_propuesta_ctrl(
    id_version: int,
    id_carga_pv: Optional[int],
    anio: int,
    meses: list[int],
    seccion: str,
    region: Optional[str],
    metodo: str,
    usuario_id: int,
) -> dict:
    """Genera propuesta automática y la persiste en forecast_detalle."""
    # 1. presupuesto de referencia (agrupado por cve_prod × mes)
    if metodo == "pv_anio":
        # "Presupuesto Ventas": agrupado por cve_prod × mes de TODAS las cargas
        # activas del año, sin depender de la carga ligada a la versión de forecast
        df_pv = obtener_presupuesto_resumen_por_anio_ctrl(anio, seccion, region)
    else:
        df_pv = obtener_presupuesto_resumen_ctrl(id_carga_pv, seccion, region)

    # 2. ventas históricas SAE (2 años atrás)
    df_ventas_raw = _ventas_historicas_sae(anio)

    # 3. generar propuesta
    df_prop = generar_propuesta_forecast(
        df_pv=df_pv,
        df_ventas=df_ventas_raw,
        df_existencias=pd.DataFrame(),
        anio=anio,
        meses=meses,
        seccion=seccion,
        metodo=metodo,
    )

    # 4. persistir
    guardados = 0
    for _, row in df_prop.iterrows():
        upsert_forecast_detalle_model(
            id_version=id_version,
            seccion=seccion,
            region=region,
            cve_prod=row.get("cve_prod"),
            producto_excel=row.get("producto_excel"),
            anio=int(row["anio"]),
            mes=int(row["mes"]),
            forecast=float(row.get("forecast") or 0),
            justificacion=None,
            metodo=str(row.get("metodo") or metodo),
            usuario_id=usuario_id,
            venta_real_mes_ant=float(row.get("venta_real_mes_ant") or 0),
            venta_real_prom_3m=float(row.get("venta_real_prom_3m") or 0),
            presupuesto_valor=float(row.get("presupuesto_valor") or 0),
        )
        guardados += 1

    return {"guardados": guardados, "productos": len(df_prop["cve_prod"].unique()) if not df_prop.empty else 0}


# ── alertas ───────────────────────────────────────────────────────────────────

def obtener_alertas_ctrl(id_version: int) -> pd.DataFrame:
    return obtener_alertas_forecast_model(id_version=id_version)


def recalcular_alertas_ctrl(
    id_version: int,
    anio: int,
    meses: list[int],
) -> int:
    limpiar_alertas_forecast_model(id_version)
    df_forecast = obtener_forecast_detalle_model(id_version=id_version, seccion="KG")
    if df_forecast is None or df_forecast.empty:
        return 0

    df_exist = _existencias_sae()

    alertas = 0
    for cve_prod in df_forecast["cve_prod"].dropna().unique():
        stock = 0.0
        if df_exist is not None and not df_exist.empty:
            m = df_exist["cve_art"].astype(str).str.strip() == str(cve_prod).strip()
            stock = float(df_exist.loc[m, "existencia"].sum() if m.any() else 0)

        filas_mdi = calcular_mdi_producto(
            cve_prod=str(cve_prod),
            stock_actual=stock,
            df_forecast=df_forecast,
            anio=anio,
            meses=meses,
        )
        for fila in filas_mdi:
            if fila["semaforo"] == "🔴":
                insertar_alerta_forecast_model(
                    id_version=id_version,
                    tipo="stock_critico",
                    cve_prod=str(cve_prod),
                    anio=anio,
                    mes=fila["mes"],
                    severidad="critical",
                    mensaje=f"{cve_prod}: stock proyectado {fila['stock_fin']:.1f} kg — {fila['dias_cobertura']:.0f} días cobertura",
                )
                alertas += 1
            elif fila["semaforo"] == "🟡":
                insertar_alerta_forecast_model(
                    id_version=id_version,
                    tipo="stock_critico",
                    cve_prod=str(cve_prod),
                    anio=anio,
                    mes=fila["mes"],
                    severidad="warning",
                    mensaje=f"{cve_prod}: stock proyectado {fila['stock_fin']:.1f} kg — {fila['dias_cobertura']:.0f} días cobertura",
                )
                alertas += 1
    return alertas


# ── necesidades de compra ─────────────────────────────────────────────────────

def calcular_necesidades_compra_ctrl(
    id_version: int,
    anio: int,
    meses: list[int],
) -> pd.DataFrame:
    """
    Cruza el forecast KG con la composición de materias primas (B) de cada fórmula
    (carrier + enzimas + auxiliares), netea primero la existencia de producto
    terminado en SAE (almacén 18, MULT01/INVE01) contra el forecast mes a mes
    (lo que ya hay en almacén no hace falta producirlo/comprarlo), y con el
    remanente a producir calcula la materia prima requerida contra la existencia
    de MP en SAE (almacén 17, MULT01/INVE01).

    Cuando un producto del forecast NO tiene fórmula registrada, se asume que ese
    producto ES la materia prima que se requiere comprar/consumir directamente
    (no se fabrica a partir de una receta); igual se le resta primero su
    existencia de PT (almacén 18) antes de compararlo contra la existencia de MP.

    Retorna un detalle (una fila por PT × MP × mes) con columnas:
        cve_prod, producto_pt, origen ('fórmula' | 'directo (sin fórmula)'),
        cve_mp, mp_nombre, mes, anio,
        forecast_kg, existencia_pt, necesidad_kg, existencia_mp, compra_requerida
    A partir de este detalle se puede agrupar tanto por materia prima como por
    producto terminado.
    """
    df_forecast = obtener_forecast_detalle_model(id_version=id_version, seccion="KG")
    if df_forecast is None or df_forecast.empty:
        return pd.DataFrame()

    # fórmulas con cve_sae vinculado (incluye composición de MP: carrier/enzimas/auxiliares)
    formulas = listar_formulas_readonly_model()
    formula_por_sae = {
        str(f.get("cve_sae") or "").strip(): f
        for f in formulas if str(f.get("cve_sae") or "").strip()
    }

    # existencias MP almacén 17 (SAE) — se referencian por clave (cve_art), no por nombre
    try:
        rows_mp = listar_mp_sae_model()
        df_mp_exist = pd.DataFrame(rows_mp) if rows_mp else pd.DataFrame()
    except Exception:
        df_mp_exist = pd.DataFrame()
    if not df_mp_exist.empty:
        df_mp_exist.columns = [c.lower() for c in df_mp_exist.columns]

    mp_exist_map: dict = {}
    mp_nombre_map: dict = {}
    if not df_mp_exist.empty and "cve_art" in df_mp_exist.columns:
        for r in df_mp_exist.to_dict("records"):
            cve = str(r.get("cve_art") or "").strip().upper()
            if not cve:
                continue
            mp_exist_map[cve] = float(r.get("exist") or 0)
            mp_nombre_map[cve] = str(r.get("descr") or cve).strip()

    def _existencia_mp(cve_mp: str) -> tuple[float, str]:
        cve = str(cve_mp or "").strip().upper()
        return mp_exist_map.get(cve, 0.0), mp_nombre_map.get(cve, cve)

    # existencias PT almacén 18 (SAE) — se netean contra el forecast antes de
    # calcular la materia prima requerida (lo que ya está en almacén no hace
    # falta producirlo)
    try:
        rows_pt = listar_pt_sae_model()
        df_pt_exist = pd.DataFrame(rows_pt) if rows_pt else pd.DataFrame()
    except Exception:
        df_pt_exist = pd.DataFrame()
    if not df_pt_exist.empty:
        df_pt_exist.columns = [c.lower() for c in df_pt_exist.columns]

    pt_exist_map: dict = {}
    if not df_pt_exist.empty and "cve_art" in df_pt_exist.columns:
        for r in df_pt_exist.to_dict("records"):
            cve = str(r.get("cve_art") or "").strip().upper()
            if not cve:
                continue
            pt_exist_map[cve] = float(r.get("exist") or 0)

    def _existencia_pt(cve_prod: str) -> float:
        cve = str(cve_prod or "").strip().upper()
        return pt_exist_map.get(cve, 0.0)

    # catálogo de nombres de PT (para mostrar aunque no tenga fórmula vinculada)
    try:
        df_cat = obtener_catalogo_productos_pv_model()
    except Exception:
        df_cat = pd.DataFrame()
    pt_nombre_map: dict = {}
    if df_cat is not None and not df_cat.empty:
        pt_nombre_map = dict(zip(df_cat["cve_prod"].astype(str).str.strip(), df_cat["descr"]))

    registros: list[dict] = []

    for cve_prod in sorted(df_forecast["cve_prod"].dropna().unique()):
        prod_str = str(cve_prod).strip()
        if not prod_str:
            continue
        formula = formula_por_sae.get(prod_str)

        # componentes de materia prima (B) declarados en la fórmula: carrier + enzimas + auxiliares
        componentes: list[dict] = []
        if formula:
            carrier = formula.get("carrier")
            if isinstance(carrier, dict) and carrier.get("mp"):
                componentes.append(carrier)
            for grupo in ("enzimas", "auxiliares"):
                lista = formula.get(grupo)
                if isinstance(lista, list):
                    componentes.extend([c for c in lista if isinstance(c, dict) and c.get("mp")])

        # existencia de PT (almacén 18) que se va consumiendo mes a mes contra el forecast
        stock_pt = _existencia_pt(prod_str)

        for mes in meses:
            mask_mes = (
                (df_forecast["cve_prod"].astype(str).str.strip() == prod_str)
                & (df_forecast["mes"] == mes)
            )
            fc_kg = float(df_forecast.loc[mask_mes, "forecast"].sum() if mask_mes.any() else 0)
            if fc_kg <= 0:
                continue

            # neteo contra existencia de PT (almacén 18): lo que ya está en almacén
            # cubre parte (o todo) del forecast del mes antes de producir/comprar más
            existencia_pt_mes = stock_pt
            a_producir_kg = max(0.0, round(fc_kg - existencia_pt_mes, 4))
            stock_pt = max(0.0, round(existencia_pt_mes - fc_kg, 4))

            if componentes:
                # producto con fórmula: se desglosa en sus materias primas
                for comp in componentes:
                    cve_mp = str(comp.get("mp") or "").strip()
                    pct = float(comp.get("pct") or 0)
                    if not cve_mp or pct <= 0:
                        continue
                    necesidad_kg = round(a_producir_kg * (pct / 100), 4)
                    exist_mp, mp_nombre = _existencia_mp(cve_mp)
                    registros.append({
                        "cve_prod": prod_str,
                        "producto_pt": pt_nombre_map.get(prod_str, prod_str),
                        "origen": "fórmula",
                        "cve_mp": cve_mp,
                        "mp_nombre": mp_nombre,
                        "mes": mes,
                        "anio": anio,
                        "forecast_kg": round(fc_kg, 2),
                        "existencia_pt": round(existencia_pt_mes, 2),
                        "necesidad_kg": necesidad_kg,
                        "existencia_mp": round(exist_mp, 2),
                        "compra_requerida": max(0.0, round(necesidad_kg - exist_mp, 2)),
                    })
            else:
                # sin fórmula: el producto en sí es la materia prima que se requiere directa
                exist_mp, mp_nombre = _existencia_mp(prod_str)
                if mp_nombre == prod_str:
                    mp_nombre = pt_nombre_map.get(prod_str, prod_str)
                registros.append({
                    "cve_prod": prod_str,
                    "producto_pt": pt_nombre_map.get(prod_str, prod_str),
                    "origen": "directo (sin fórmula)",
                    "cve_mp": prod_str,
                    "mp_nombre": mp_nombre,
                    "mes": mes,
                    "anio": anio,
                    "forecast_kg": round(fc_kg, 2),
                    "existencia_pt": round(existencia_pt_mes, 2),
                    "necesidad_kg": round(a_producir_kg, 2),
                    "existencia_mp": round(exist_mp, 2),
                    "compra_requerida": max(0.0, round(a_producir_kg - exist_mp, 2)),
                })

    if not registros:
        return pd.DataFrame(columns=[
            "cve_prod", "producto_pt", "origen", "cve_mp", "mp_nombre", "mes", "anio",
            "forecast_kg", "existencia_pt", "necesidad_kg", "existencia_mp", "compra_requerida",
        ])

    return pd.DataFrame(registros).sort_values(
        ["compra_requerida", "mp_nombre"], ascending=[False, True]
    )


# ── MDI ───────────────────────────────────────────────────────────────────────

def calcular_mdi_ctrl(
    id_version: int,
    anio: int,
    meses: list[int],
) -> pd.DataFrame:
    """
    Retorna DataFrame MDI: cve_prod + columnas de meses con stock proyectado y semáforo.
    """
    df_forecast = obtener_forecast_detalle_model(id_version=id_version, seccion="KG")
    if df_forecast is None or df_forecast.empty:
        return pd.DataFrame()

    df_exist = _existencias_sae()

    # catálogo nombre de producto
    try:
        df_cat = obtener_catalogo_productos_pv_model()
    except Exception:
        df_cat = pd.DataFrame()
    cat_map = {}
    if df_cat is not None and not df_cat.empty:
        cat_map = dict(zip(df_cat["cve_prod"].astype(str).str.strip(), df_cat["descr"]))

    filas = []
    for cve_prod in sorted(df_forecast["cve_prod"].dropna().unique()):
        prod_str = str(cve_prod).strip()
        stock = 0.0
        if df_exist is not None and not df_exist.empty:
            m = df_exist["cve_art"].astype(str).str.strip() == prod_str
            stock = float(df_exist.loc[m, "existencia"].sum() if m.any() else 0)

        datos_mdi = calcular_mdi_producto(
            cve_prod=prod_str,
            stock_actual=stock,
            df_forecast=df_forecast,
            anio=anio,
            meses=meses,
        )

        fila: dict = {
            "cve_prod": prod_str,
            "producto": cat_map.get(prod_str, prod_str),
            "stock_actual": round(stock, 2),
        }
        for d in datos_mdi:
            mes = d["mes"]
            fila[f"fc_{mes:02d}"] = d["salidas_forecast"]
            fila[f"stock_{mes:02d}"] = d["stock_fin"]
            fila[f"dias_{mes:02d}"] = d["dias_cobertura"]
            fila[f"sem_{mes:02d}"] = d["semaforo"]
        filas.append(fila)

    return pd.DataFrame(filas) if filas else pd.DataFrame()


# ── helpers internos con caché ────────────────────────────────────────────────

@st.cache_data(ttl=1800, show_spinner="cargando ventas SAE…")
def _ventas_historicas_sae(anio: int) -> pd.DataFrame:
    try:
        df = obtener_ventas_reales_resumen_sae_model(anio=anio)
        if df is None or df.empty:
            df2 = obtener_ventas_reales_resumen_sae_model(anio=anio - 1)
            return df2 if df2 is not None else pd.DataFrame()
        # también trae año anterior para cálculos de referencia
        df_ant = obtener_ventas_reales_resumen_sae_model(anio=anio - 1)
        if df_ant is not None and not df_ant.empty:
            return pd.concat([df, df_ant], ignore_index=True)
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=1800, show_spinner="cargando catálogo de líneas SAE…")
def _catalogo_productos_sae() -> pd.DataFrame:
    """cve_art + línea (inve01.lin_prod ligado con clin01.cve_lin) para filtrar por línea."""
    try:
        return obtener_productos_sae_model(solo_activos=False, limit=20000)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=900, show_spinner="cargando existencias SAE…")
def _existencias_sae() -> pd.DataFrame:
    try:
        return obtener_existencias_productos_sae_model()
    except Exception:
        return pd.DataFrame()


