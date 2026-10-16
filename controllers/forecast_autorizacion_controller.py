from __future__ import annotations

import pandas as pd
import streamlit as st

from models.forecast_autorizacion_model import (
    insertar_forecast_mes_estatus_historico_model,
    obtener_forecast_mes_estatus_autorizados_model,
    obtener_forecast_mes_estatus_model,
    obtener_forecast_mes_estatus_pendientes_model,
    obtener_forecast_mes_estatus_resueltos_model,
    upsert_forecast_mes_estatus_model,
)
from models.presupuesto_ventas_sae_model import obtener_catalogo_productos_pv_model
from utils.forecast_engine import calcular_necesidad_compra_dp_producto
from controllers.forecast_controller import (
    obtener_forecast_versiones_ctrl,
    obtener_forecast_detalle_ctrl,
    obtener_presupuesto_resumen_por_anio_ctrl,
    obtener_presupuesto_compras_resumen_por_anio_ctrl,
    _existencias_sae,
)


def cambiar_estatus_forecast_mes_ctrl(
    id_version: int,
    tipo: str,
    anio: int,
    mes: int,
    estatus_nuevo: str,
    usuario_id: int,
    usuario_nombre: str | None = None,
    usuario_email: str | None = None,
    comentario: str | None = None,
) -> int:
    """Upsert + histórico en un solo wrapper — mismo patrón que
    `_cambiar_estatus_linea_compras` (views/modulo_presupuesto_ventas/
    presupuesto_compras_view.py). Invalida los caches de lectura."""
    mes_estatus_id, estatus_anterior = upsert_forecast_mes_estatus_model(
        id_version=id_version, tipo=tipo, anio=anio, mes=mes,
        estatus=estatus_nuevo, usuario_id=usuario_id,
    )
    insertar_forecast_mes_estatus_historico_model(
        mes_estatus_id=mes_estatus_id,
        estatus_anterior=estatus_anterior,
        estatus_nuevo=estatus_nuevo,
        usuario_id=usuario_id,
        usuario_nombre=usuario_nombre,
        usuario_email=usuario_email,
        comentario=comentario,
    )
    obtener_forecast_mes_estatus_ctrl.clear()
    obtener_forecast_mes_estatus_pendientes_ctrl.clear()
    obtener_forecast_mes_estatus_autorizados_ctrl.clear()
    calcular_necesidad_compra_consolidada_ctrl.clear()
    return mes_estatus_id


@st.cache_data(ttl=120, show_spinner=False)
def obtener_forecast_mes_estatus_ctrl(
    id_version: int, tipo: str | None = None, anio: int | None = None,
) -> pd.DataFrame:
    return obtener_forecast_mes_estatus_model(id_version=id_version, tipo=tipo, anio=anio)


@st.cache_data(ttl=60, show_spinner=False)
def obtener_forecast_mes_estatus_pendientes_ctrl() -> pd.DataFrame:
    return obtener_forecast_mes_estatus_pendientes_model()


@st.cache_data(ttl=60, show_spinner=False)
def obtener_forecast_mes_estatus_resueltos_ctrl(usuario_id: int) -> pd.DataFrame:
    return obtener_forecast_mes_estatus_resueltos_model(usuario_id=usuario_id)


@st.cache_data(ttl=300, show_spinner=False)
def obtener_forecast_mes_estatus_autorizados_ctrl(anio: int, tipo: str) -> pd.DataFrame:
    return obtener_forecast_mes_estatus_autorizados_model(anio=anio, tipo=tipo)


# ── consolidado cross-vendedor para Compras ──────────────────────────────────

def _acumular_contribucion_mes(
    *,
    mes: int,
    df_forecast: pd.DataFrame,
    autorizado: bool,
    df_fallback: pd.DataFrame,
    acc: dict[tuple[str, int], float],
    fallback_keys: set[tuple[str, int]],
    vendedores_por_producto: dict[str, set[str]],
    nombre_vendedor: str,
) -> None:
    """Suma al acumulador la contribución de UN vendedor a UN mes: su propio
    forecast si ese mes está 'autorizada', si no su propio presupuesto
    autorizado (nunca el de otro vendedor) — evita duplicar el conteo porque
    cada vendedor aporta un solo valor por producto/mes, igual si viene de
    forecast o de presupuesto."""
    if autorizado and df_forecast is not None and not df_forecast.empty:
        df_mes = df_forecast[pd.to_numeric(df_forecast["mes"], errors="coerce") == mes]
        col_valor = "forecast"
    elif df_fallback is not None and not df_fallback.empty:
        df_mes = df_fallback[pd.to_numeric(df_fallback["mes"], errors="coerce") == mes]
        col_valor = "total_kg"
    else:
        return

    if df_mes is None or df_mes.empty or col_valor not in df_mes.columns:
        return

    for r in df_mes.to_dict("records"):
        cve = str(r.get("cve_prod") or "").strip()
        valor = float(r.get(col_valor) or 0.0)
        if not cve or not valor:
            continue
        key = (cve, mes)
        acc[key] = acc.get(key, 0.0) + valor
        if not autorizado:
            fallback_keys.add(key)
        vendedores_por_producto.setdefault(cve, set()).add(nombre_vendedor)


_MESES_CTRL = {1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
               7: "jul", 8: "ago", 9: "sep", 10: "oct", 11: "nov", 12: "dic"}


@st.cache_data(ttl=300, show_spinner="consolidando necesidad de compra de todos los vendedores…")
def calcular_necesidad_compra_consolidada_ctrl(anio: int, meses: list[int]) -> pd.DataFrame:
    """
    Necesidad de compra por producto × mes, consolidada entre TODOS los
    vendedores (todas las forecast_versiones del año): para cada vendedor y
    mes, usa su forecast de venta/compra si ese mes está 'autorizada'; si no,
    cae al presupuesto de ventas/compras YA AUTORIZADO de ESE MISMO vendedor.
    Se agrega primero (suma por cve_prod × mes, vendedor por vendedor) y hasta
    el final se corre el motor de arrastre mes a mes
    (`calcular_necesidad_compra_dp_producto`) una sola vez por producto contra
    la existencia física, que es global (no se puede repartir entre
    vendedores sin duplicar el conteo).

    Retorna una fila por (cve_prod, mes) — "formato largo" para poder pivotear
    en la vista a Stock actual | Forecast | DP | Orden de Compra | Resultado
    por mes, con el arrastre de `existencia_inicio`/`resultado` ya resuelto por el
    motor. `origen_forecast` y `vendedores` son a nivel producto (repetidos en
    cada fila de mes) — ver `_acumular_contribucion_mes`.

    No excluye nada del consolidado: un producto/mes sin ningún vendedor
    autorizado todavía aparece con su presupuesto como respaldo, marcado
    `origen_forecast = 'presupuesto (fallback)'` en vez de `'autorizado'`.
    """
    if not meses:
        return pd.DataFrame()

    df_versiones = obtener_forecast_versiones_ctrl(usuario_id=0, anio=anio, ver_todas=True)
    if df_versiones is None or df_versiones.empty:
        return pd.DataFrame()

    venta_acc: dict[tuple[str, int], float] = {}
    compra_acc: dict[tuple[str, int], float] = {}
    fallback_venta: set[tuple[str, int]] = set()
    fallback_compra: set[tuple[str, int]] = set()
    vendedores_por_producto: dict[str, set[str]] = {}

    for v in df_versiones.to_dict("records"):
        id_version = int(v["id_version"])
        usuario_id_v = int(v.get("usuario_id") or 0)
        nombre_v = str(v.get("propietario") or f"usuario {usuario_id_v}")

        df_estatus = obtener_forecast_mes_estatus_ctrl(id_version=id_version, anio=anio)
        estatus_venta: dict[int, str] = {}
        estatus_compra: dict[int, str] = {}
        if df_estatus is not None and not df_estatus.empty:
            for r in df_estatus.to_dict("records"):
                destino = estatus_venta if r["tipo"] == "venta" else estatus_compra
                destino[int(r["mes"])] = r["estatus"]

        df_fc_venta = obtener_forecast_detalle_ctrl(id_version=id_version, seccion="KG", tipo="venta")
        df_fc_compra = obtener_forecast_detalle_ctrl(id_version=id_version, seccion="KG", tipo="compra")
        df_pv_v = obtener_presupuesto_resumen_por_anio_ctrl(
            anio=anio, seccion="KG", region=None, usuario_id=usuario_id_v, solo_autorizados=True,
        )
        df_pc_v = obtener_presupuesto_compras_resumen_por_anio_ctrl(
            anio=anio, seccion="KG", region=None, usuario_id=usuario_id_v, solo_autorizados=True,
        )

        for mes in meses:
            _acumular_contribucion_mes(
                mes=mes, df_forecast=df_fc_venta, autorizado=(estatus_venta.get(mes) == "autorizada"),
                df_fallback=df_pv_v, acc=venta_acc, fallback_keys=fallback_venta,
                vendedores_por_producto=vendedores_por_producto, nombre_vendedor=nombre_v,
            )
            _acumular_contribucion_mes(
                mes=mes, df_forecast=df_fc_compra, autorizado=(estatus_compra.get(mes) == "autorizada"),
                df_fallback=df_pc_v, acc=compra_acc, fallback_keys=fallback_compra,
                vendedores_por_producto=vendedores_por_producto, nombre_vendedor=nombre_v,
            )

    cve_prods = sorted({k[0] for k in venta_acc} | {k[0] for k in compra_acc})
    if not cve_prods:
        return pd.DataFrame()

    df_exist = _existencias_sae()
    try:
        df_cat = obtener_catalogo_productos_pv_model()
    except Exception:
        df_cat = pd.DataFrame()
    cat_map: dict = {}
    if df_cat is not None and not df_cat.empty:
        cat_map = dict(zip(df_cat["cve_prod"].astype(str).str.strip(), df_cat["descr"]))

    filas = []
    for cve in cve_prods:
        stock = 0.0
        if df_exist is not None and not df_exist.empty:
            m = df_exist["cve_art"].astype(str).str.strip() == cve
            stock = float(df_exist.loc[m, "existencia"].sum() if m.any() else 0)

        df_venta_prod = pd.DataFrame([
            {"cve_prod": cve, "mes": mes, "forecast": venta_acc.get((cve, mes), 0.0)} for mes in meses
        ])
        df_compra_prod = pd.DataFrame([
            {"cve_prod": cve, "mes": mes, "forecast": compra_acc.get((cve, mes), 0.0)} for mes in meses
        ])

        detalle = calcular_necesidad_compra_dp_producto(
            cve_prod=cve, stock_actual=stock,
            df_forecast_venta=df_venta_prod, df_forecast_compra=df_compra_prod,
            df_dp_compras=pd.DataFrame(), meses=meses,
        )
        if not detalle:
            continue

        hubo_fallback = any((cve, mes) in fallback_venta or (cve, mes) in fallback_compra for mes in meses)
        origen_prod = "presupuesto (fallback)" if hubo_fallback else "autorizado"
        vendedores = ", ".join(sorted(vendedores_por_producto.get(cve, set())))
        producto = cat_map.get(cve, cve)

        for d in detalle:
            filas.append({
                "cve_prod": cve,
                "producto": producto,
                "mes": int(d["mes"]),
                "mes_nombre": _MESES_CTRL.get(int(d["mes"]), str(d["mes"])),
                "existencia_inicio": round(d["existencia_inicio"], 2),
                "venta_forecast": round(d["venta_forecast"], 2),
                "compra_cubierta": round(d["compra_cubierta"], 2),
                "necesidad": round(d["necesidad"], 2),
                "resultado": round(d["resultado"], 2),
                "origen_forecast": origen_prod,
                "vendedores": vendedores,
            })

    return pd.DataFrame(filas) if filas else pd.DataFrame()
