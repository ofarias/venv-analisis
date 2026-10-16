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


def calcular_venta_acumulada_anio_anterior(
    df_ventas: pd.DataFrame,
    cve_prod: str,
    anio_ref: int,
) -> float:
    """Venta real acumulada (kg) de TODO el año anterior (anio_ref - 1), no
    solo un mes — referencia de "¿cuánto se vendió el año pasado en total?"
    para la columna "vta año ant (Kg)" de Construcción del Forecast."""
    if df_ventas is None or df_ventas.empty:
        return 0.0
    mask = (
        (df_ventas["cve_art"].astype(str).str.strip() == str(cve_prod).strip())
        & (df_ventas["anio"] == anio_ref - 1)
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

            # ventas año anterior, acumulado del año completo (no solo el mes)
            venta_ant = calcular_venta_acumulada_anio_anterior(df_ventas, prod_str, anio) if df_ventas is not None and not df_ventas.empty else 0.0

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
    df_forecast_venta: pd.DataFrame,    # forecast KG de venta por mes
    df_forecast_compra: pd.DataFrame,   # forecast KG de compra (DP) por mes
    anio: int,
    meses: list[int],
) -> list[dict]:
    """
    Calcula el Mapa de Inventario mes a mes para un producto: parte del stock
    actual y cada mes resta la proyección de venta y suma la proyección de
    compra — el resultado es acumulativo, se arrastra como stock de inicio
    del siguiente mes hasta terminar el año (no se trunca a 0: un resultado
    negativo señala un faltante proyectado que no se resuelve solo). No
    considera órdenes de producción, solo lo ya proyectado en el forecast.
    Retorna lista de dicts: {mes, stock_inicio, venta_forecast,
    compra_forecast, resultado, dias_cobertura, semaforo}
    """

    def _forecast_mes(df: pd.DataFrame, mes: int) -> float:
        if df is None or df.empty:
            return 0.0
        mask = (
            (df["cve_prod"].astype(str).str.strip() == str(cve_prod).strip())
            & (df["mes"] == mes)
        )
        return float(df.loc[mask, "forecast"].sum() if mask.any() else 0)

    resultado = []
    stock = float(stock_actual or 0)

    for mes in meses:
        venta = _forecast_mes(df_forecast_venta, mes)
        compra = _forecast_mes(df_forecast_compra, mes)
        stock_inicio = stock
        res = stock_inicio - venta + compra
        dias = dias_cobertura(max(res, 0.0), venta, anio, mes)

        if res <= 0 and venta <= 0:
            # sin stock proyectado y sin demanda proyectada: no es una alerta de cobertura
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
            "stock_inicio": round(stock_inicio, 2),
            "venta_forecast": round(venta, 2),
            "compra_forecast": round(compra, 2),
            "resultado": round(res, 2),
            "dias_cobertura": dias,
            "semaforo": semaforo,
        })
        stock = res  # acumulativo: el resultado de este mes es el stock de inicio del siguiente

    return resultado


def calcular_necesidad_compra_dp_producto(
    cve_prod: str,
    stock_actual: float,
    df_forecast_venta: pd.DataFrame,   # forecast KG de venta por mes
    df_forecast_compra: pd.DataFrame,  # forecast KG de compra (DP) por mes, si ya se capturó
    df_dp_compras: pd.DataFrame,       # presupuesto de compras YA AUTORIZADO por cve_prod × mes (columna total_kg)
    meses: list[int],
) -> list[dict]:
    """
    Necesidad de compra por producto, mes a mes desde el mes actual hasta el
    último mes seleccionado: cada mes compara la venta proyectada contra lo
    que ya está disponible para cubrirla (existencia de inicio + compra). La
    compra del mes se toma del forecast de compra (DP capturado en
    Construcción del Forecast) si ya existe una fila para ese producto/mes;
    si no, se usa el presupuesto de compras YA AUTORIZADO (DP) de ese
    producto/mes como respaldo.

    Resultado del mes = existencia de inicio - venta proyectada + compra
    (DP/forecast de compra). Ese resultado — sin acotar a 0, puede quedar
    negativo — es la existencia de inicio del mes siguiente: un faltante SÍ
    se arrastra como deuda a los meses siguientes, no se "resetea" cada mes.
    "necesidad" es solo informativo: cuánto haría falta ordenar ESE mes para
    no quedar en negativo (max(0, venta - disponible)) — no participa en el
    arrastre, que siempre usa el resultado real (positivo o negativo).

    Retorna lista de dicts: {mes, existencia_inicio, venta_forecast,
    compra_cubierta, origen_compra, necesidad, resultado}
    """

    def _valor_mes(df: pd.DataFrame, mes: int, col: str) -> Optional[float]:
        if df is None or df.empty or col not in df.columns:
            return None
        mask = (
            (df["cve_prod"].astype(str).str.strip() == str(cve_prod).strip())
            & (df["mes"] == mes)
        )
        if not mask.any():
            return None
        return float(df.loc[mask, col].sum())

    filas = []
    stock = float(stock_actual or 0)

    for mes in meses:
        venta = _valor_mes(df_forecast_venta, mes, "forecast") or 0.0
        compra_fc = _valor_mes(df_forecast_compra, mes, "forecast")
        if compra_fc:
            compra = compra_fc
            origen_compra = "forecast"
        else:
            compra_dp = _valor_mes(df_dp_compras, mes, "total_kg")
            compra = compra_dp or 0.0
            origen_compra = "DP autorizado" if compra_dp else "sin dato"

        existencia_inicio = stock
        resultado_mes = existencia_inicio - venta + compra
        necesidad = max(0.0, -resultado_mes)

        filas.append({
            "mes": mes,
            "mes_nombre": _MESES.get(mes, str(mes)),
            "existencia_inicio": round(existencia_inicio, 2),
            "venta_forecast": round(venta, 2),
            "compra_cubierta": round(compra, 2),
            "origen_compra": origen_compra,
            "necesidad": round(necesidad, 2),
            "resultado": round(resultado_mes, 2),
        })
        stock = resultado_mes  # arrastre directo — puede quedar negativo (deuda)

    return filas
