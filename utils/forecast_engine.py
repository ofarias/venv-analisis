from __future__ import annotations

import calendar
from typing import Optional
import pandas as pd


_MESES = {1:"ene",2:"feb",3:"mar",4:"abr",5:"may",6:"jun",
          7:"jul",8:"ago",9:"sep",10:"oct",11:"nov",12:"dic"}


def calcular_promedio_n_meses(
    df_ventas: pd.DataFrame,
    cve_prod: str,
    anio_ref: int,
    mes_ref: int,
    n: int = 3,
) -> float:
    """Promedio de ventas KG/importe de los últimos n meses antes de mes_ref."""
    if df_ventas is None or df_ventas.empty:
        return 0.0

    filas = []
    a, m = anio_ref, mes_ref
    for _ in range(n):
        m -= 1
        if m == 0:
            m = 12
            a -= 1
        filas.append((a, m))

    mask = df_ventas["cve_art"].astype(str).str.strip() == str(cve_prod).strip()
    sub = df_ventas[mask]
    total = 0.0
    for a2, m2 in filas:
        val = sub.loc[(sub["anio"] == a2) & (sub["mes"] == m2), "cantidad"].sum()
        total += float(val or 0)
    return round(total / n, 4)


def calcular_venta_mismo_mes_anio_anterior(
    df_ventas: pd.DataFrame,
    cve_prod: str,
    anio_ref: int,
    mes_ref: int,
) -> float:
    if df_ventas is None or df_ventas.empty:
        return 0.0
    mask = (
        (df_ventas["cve_art"].astype(str).str.strip() == str(cve_prod).strip())
        & (df_ventas["anio"] == anio_ref - 1)
        & (df_ventas["mes"] == mes_ref)
    )
    return float(df_ventas.loc[mask, "cantidad"].sum() or 0)


def dias_cobertura(stock_kg: float, forecast_kg_mes: float, anio: int, mes: int) -> float:
    """Cuántos días dura el stock con base en el forecast mensual."""
    dias = calendar.monthrange(anio, mes)[1]
    if forecast_kg_mes <= 0:
        return 9999.0
    consumo_diario = forecast_kg_mes / dias
    return round(stock_kg / consumo_diario, 1)


def generar_propuesta_forecast(
    df_pv: pd.DataFrame,           # resumen presupuesto por cve_prod/mes
    df_ventas: pd.DataFrame,       # ventas reales SAE por cve_art/anio/mes
    df_existencias: pd.DataFrame,  # existencias SAE (cve_art, existencia)
    anio: int,
    meses: list[int],
    seccion: str,
    metodo: str = "prom_3m",
) -> pd.DataFrame:
    """
    Genera una propuesta de forecast por producto × mes.
    Retorna DataFrame con columnas:
        cve_prod, producto_excel, mes, anio, seccion,
        venta_real_mes_ant, venta_real_prom_3m,
        presupuesto_valor, forecast, metodo
    """
    registros = []

    col_val = "total_kg" if seccion == "KG" else "total_importe"
    col_cant_ventas = "cantidad" if seccion == "KG" else "importe"

    if col_cant_ventas not in df_ventas.columns and not df_ventas.empty:
        col_cant_ventas = df_ventas.columns[-1]

    productos = []
    if df_pv is not None and not df_pv.empty and "cve_prod" in df_pv.columns:
        productos = df_pv["cve_prod"].dropna().unique().tolist()

    for cve_prod in productos:
        prod_str = str(cve_prod).strip()
        if not prod_str:
            continue

        mask_pv = df_pv["cve_prod"].astype(str).str.strip() == prod_str
        nombre = df_pv.loc[mask_pv, "producto_excel"].iloc[0] if "producto_excel" in df_pv.columns and mask_pv.any() else prod_str

        for mes in meses:
            # referencia presupuesto
            pv_mask = mask_pv & (df_pv["mes"] == mes) if "mes" in df_pv.columns else mask_pv
            pres_val = float(df_pv.loc[pv_mask, col_val].sum()) if col_val in df_pv.columns else 0.0

            # ventas año anterior mismo mes
            venta_ant = calcular_venta_mismo_mes_anio_anterior(df_ventas, prod_str, anio, mes) if df_ventas is not None and not df_ventas.empty else 0.0

            # promedio 3 o 12 meses
            n = 3 if metodo == "prom_3m" else 12
            prom_3m = calcular_promedio_n_meses(df_ventas, prod_str, anio, mes, n=3) if df_ventas is not None and not df_ventas.empty else 0.0

            # forecast propuesto
            if metodo in ("presupuesto", "pv_anio"):
                fc = pres_val
            elif metodo == "prom_3m":
                fc = calcular_promedio_n_meses(df_ventas, prod_str, anio, mes, n=3) if df_ventas is not None and not df_ventas.empty else pres_val
            elif metodo == "prom_12m":
                fc = calcular_promedio_n_meses(df_ventas, prod_str, anio, mes, n=12) if df_ventas is not None and not df_ventas.empty else pres_val
            elif metodo == "pct_presupuesto":
                # 95% del presupuesto como conservador por defecto
                fc = pres_val * 0.95
            else:
                fc = pres_val

            registros.append({
                "cve_prod": prod_str,
                "producto_excel": nombre,
                "anio": anio,
                "mes": mes,
                "seccion": seccion,
                "venta_real_mes_ant": venta_ant,
                "venta_real_prom_3m": prom_3m,
                "presupuesto_valor": pres_val,
                "forecast": round(fc, 4),
                "metodo": metodo,
            })

    return pd.DataFrame(registros) if registros else pd.DataFrame(columns=[
        "cve_prod", "producto_excel", "anio", "mes", "seccion",
        "venta_real_mes_ant", "venta_real_prom_3m", "presupuesto_valor", "forecast", "metodo",
    ])


def calcular_mdi_producto(
    cve_prod: str,
    stock_actual: float,
    df_forecast: pd.DataFrame,          # forecast KG por mes
    anio: int,
    meses: list[int],
) -> list[dict]:
    """
    Calcula el Mapa de Inventario mes a mes para un producto.
    No considera órdenes de producción: el stock solo se reduce por el forecast de salidas.
    Retorna lista de dicts: {mes, stock_inicio, salidas_forecast, stock_fin, dias_cobertura, semaforo}
    """
    resultado = []
    stock = float(stock_actual or 0)

    for mes in meses:
        # salidas según forecast
        salidas = 0.0
        if df_forecast is not None and not df_forecast.empty:
            mask_f = (
                (df_forecast["cve_prod"].astype(str).str.strip() == str(cve_prod).strip())
                & (df_forecast["mes"] == mes)
            )
            salidas = float(df_forecast.loc[mask_f, "forecast"].sum() if mask_f.any() else 0)

        stock_fin = max(stock - salidas, 0)
        dias = dias_cobertura(stock_fin, salidas, anio, mes)

        if stock_fin <= 0 and salidas <= 0:
            # sin stock y sin demanda proyectada: no es una alerta de cobertura
            semaforo = "🔵"
        elif dias >= 30:
            semaforo = "🟢"
        elif dias >= 15:
            semaforo = "🟡"
        else:
            semaforo = "🔴"

        resultado.append({
            "mes": mes,
            "mes_nombre": _MESES.get(mes, str(mes)),
            "stock_inicio": round(stock, 2),
            "salidas_forecast": round(salidas, 2),
            "stock_fin": round(stock_fin, 2),
            "dias_cobertura": dias,
            "semaforo": semaforo,
        })
        stock = stock_fin

    return resultado
