"""Reporte de productos obsoletos por lote (Almacenes 17/18/22) — SAE vía
Firebird, solo lectura.

Esquema real (no hay FK directa entre MINVE01 y LTPD01, hay que pasar por
la tabla de enlace):

    MINVE01 (movimientos) --E_LTPD--> ENLACE_LTPD01 --REG_LTPD--> LTPD01 (lotes/pedimentos)

- "Compra" = MINVE01.CVE_CPTO = 1 (confirmado con el usuario) — las
  Órdenes/Requisiciones (COMPO01/COMPQ01) no afectan inventario, por eso
  nunca aparecen en MINVE01; solo la compra facturada (CVE_CPTO=1) sí.
- LTPD01.CANTIDAD guarda la existencia ACTUAL del lote (hoy) — para evitar
  ruido de punto flotante (saldos "en cero" que en realidad son 1e-14 por
  redondeos acumulados de SAE) se usa CANTIDAD > 0.01 como "tiene
  existencia real", confirmado contra datos reales.
- "Final Mes N" se calcula hacia atrás desde la existencia actual: se le
  resta todo lo que movió el lote DESPUÉS del fin de ese mes — así no hace
  falta asumir un saldo inicial, y siempre cuadra con el saldo real de hoy.
"""

from datetime import date, datetime
from calendar import monthrange

import pandas as pd

from models.db import run_query_firebird

_FIREBIRD_SAE = "FIREBIRD_BIO_SAE"
_UMBRAL_EXISTENCIA = 0.01
_CVE_CPTO_COMPRA = 1

_MESES = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio",
    7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
}


def _meses_vigencia(fecha_caducidad, hoy: date) -> int | None:
    """Meses completos entre hoy y la fecha de caducidad — negativo si ya
    caducó. Cuenta mes calendario completo: si el día de caducidad todavía
    no se alcanza en el mes de corte, no cuenta ese mes como completo."""
    if fecha_caducidad is None:
        return None
    fc = _a_fecha(fecha_caducidad)
    meses = (fc.year - hoy.year) * 12 + (fc.month - hoy.month)
    if fc.day < hoy.day:
        meses -= 1
    return meses


def obtener_lotes_obsoletos_base_model(almacenes: list[int]) -> pd.DataFrame:
    """Lotes con existencia real (> 0.01) en los almacenes indicados, con
    datos de producto/línea/control de almacén."""
    placeholders = ",".join(["?"] * len(almacenes))
    sql = f"""
        SELECT
            l.REG_LTPD, l.CVE_ALM, l.CVE_ART, l.LOTE, l.PEDIMENTO,
            l.FCHCADUC, l.FCHULTMOV, l.CANTIDAD AS existencia_actual,
            i.DESCR AS producto, i.CTRL_ALM AS control_almacen,
            cl.DESC_LIN AS linea, i.COSTO_PROM AS costo_promedio
        FROM LTPD01 l
        LEFT JOIN INVE01 i ON i.CVE_ART = l.CVE_ART
        LEFT JOIN CLIN01 cl ON cl.CVE_LIN = i.LIN_PROD
        WHERE l.CVE_ALM IN ({placeholders}) AND l.CANTIDAD > {_UMBRAL_EXISTENCIA}
        ORDER BY l.CVE_ALM, i.DESCR, l.LOTE
    """
    rows = run_query_firebird(_FIREBIRD_SAE, sql, tuple(almacenes))
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=[
        "REG_LTPD", "CVE_ALM", "CVE_ART", "LOTE", "PEDIMENTO", "FCHCADUC", "FCHULTMOV",
        "existencia_actual", "producto", "control_almacen", "linea", "costo_promedio",
    ])


def obtener_fecha_ultima_compra_por_lote_model(regs_ltpd: list[int]) -> dict[int, datetime]:
    """Fecha más reciente de una entrada por compra (CVE_CPTO=1, signo
    positivo) para cada lote — sin límite de fecha, puede ser de cualquier
    año (el lote pudo haberse comprado hace tiempo y seguir en inventario)."""
    if not regs_ltpd:
        return {}
    placeholders = ",".join(["?"] * len(regs_ltpd))
    sql = f"""
        SELECT en.REG_LTPD, MAX(m.FECHA_DOCU) AS fecha_ultima_compra
        FROM MINVE01 m
        INNER JOIN ENLACE_LTPD01 en ON en.E_LTPD = m.E_LTPD
        WHERE en.REG_LTPD IN ({placeholders})
          AND m.CVE_CPTO = {_CVE_CPTO_COMPRA} AND m.SIGNO = 1
        GROUP BY en.REG_LTPD
    """
    rows = run_query_firebird(_FIREBIRD_SAE, sql, tuple(regs_ltpd))
    return {int(r["REG_LTPD"]): r["FECHA_ULTIMA_COMPRA"] for r in (rows or [])}


def obtener_movimientos_por_lote_model(regs_ltpd: list[int], fecha_desde: date) -> pd.DataFrame:
    """Todos los movimientos de esos lotes desde fecha_desde (inicio del
    año del reporte) hasta HOY — se necesita hasta hoy, no solo hasta fin
    de año, para poder calcular "Final Mes N" restando hacia atrás desde
    la existencia actual aunque el año consultado ya haya cerrado."""
    if not regs_ltpd:
        return pd.DataFrame(columns=["REG_LTPD", "FECHA_DOCU", "SIGNO", "CANTIDAD"])
    placeholders = ",".join(["?"] * len(regs_ltpd))
    sql = f"""
        SELECT en.REG_LTPD, m.FECHA_DOCU, m.SIGNO, en.CANTIDAD
        FROM MINVE01 m
        INNER JOIN ENLACE_LTPD01 en ON en.E_LTPD = m.E_LTPD
        WHERE en.REG_LTPD IN ({placeholders}) AND m.FECHA_DOCU >= ?
        ORDER BY en.REG_LTPD, m.FECHA_DOCU
    """
    rows = run_query_firebird(_FIREBIRD_SAE, sql, tuple(regs_ltpd) + (fecha_desde,))
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["REG_LTPD", "FECHA_DOCU", "SIGNO", "CANTIDAD"])


def construir_reporte_productos_obsoletos_model(anio: int, almacenes: list[int] = (17, 18, 22)) -> pd.DataFrame:
    hoy = date.today()
    ultimo_mes = 12 if anio < hoy.year else hoy.month if anio == hoy.year else 0
    if ultimo_mes == 0:
        return pd.DataFrame()

    base = obtener_lotes_obsoletos_base_model(list(almacenes))
    if base.empty:
        return pd.DataFrame()

    regs = base["REG_LTPD"].astype(int).tolist()
    fecha_ultima_compra_por_lote = obtener_fecha_ultima_compra_por_lote_model(regs)
    movimientos = obtener_movimientos_por_lote_model(regs, date(anio, 1, 1))

    movimientos_por_lote: dict[int, list[dict]] = {}
    if not movimientos.empty:
        for reg, grupo in movimientos.groupby("REG_LTPD"):
            movimientos_por_lote[int(reg)] = grupo.to_dict("records")

    filas = []
    for _, lote in base.iterrows():
        reg = int(lote["REG_LTPD"])
        existencia_actual = float(lote["EXISTENCIA_ACTUAL"])
        movs = movimientos_por_lote.get(reg, [])

        fila = {
            "Almacén": int(lote["CVE_ALM"]),
            "Clave": lote["CVE_ART"],
            "Producto": lote["PRODUCTO"],
            "Lote": lote["LOTE"],
            "Línea": lote["LINEA"],
            "Control Almacén": lote["CONTROL_ALMACEN"],
            "Fecha Última Compra": fecha_ultima_compra_por_lote.get(reg),
            "Fecha Último Movimiento": lote["FCHULTMOV"],
            "Fecha de Caducidad": lote["FCHCADUC"],
            "Año de compra": (
                fecha_ultima_compra_por_lote[reg].year if reg in fecha_ultima_compra_por_lote else None
            ),
            "Meses de Vigencia": _meses_vigencia(lote["FCHCADUC"], hoy),
        }

        for mes in range(1, ultimo_mes + 1):
            fin_de_mes = date(anio, mes, monthrange(anio, mes)[1])
            etiqueta_mes = f"{_MESES[mes]} {anio}"

            # Entradas: todo movimiento con signo positivo de ESTE lote en
            # el mes (compras, ajustes de entrada, devoluciones, etc.) —
            # no se limita a CVE_CPTO=1 (eso solo se usa para "Fecha Última
            # Compra"/"Año de compra"), aquí se suma cualquier entrada real
            # al lote.
            entradas_mes = sum(
                float(m["CANTIDAD"]) for m in movs
                if m["SIGNO"] == 1 and _a_fecha(m["FECHA_DOCU"]).year == anio and _a_fecha(m["FECHA_DOCU"]).month == mes
            )
            # Salidas: todo movimiento con signo negativo de ESTE lote en
            # el mes (consumo, ventas, mermas, ajustes de salida, etc.),
            # reportado en positivo (unidades que salieron).
            salidas_mes = sum(
                float(m["CANTIDAD"]) for m in movs
                if m["SIGNO"] == -1 and _a_fecha(m["FECHA_DOCU"]).year == anio and _a_fecha(m["FECHA_DOCU"]).month == mes
            )
            # Final: existencia de HOY menos todo lo que se movió (con su
            # signo) después del cierre de ese mes — no se asume un saldo
            # inicial, siempre cuadra con el saldo real actual.
            movimiento_posterior = sum(
                float(m["CANTIDAD"]) * int(m["SIGNO"]) for m in movs
                if _a_fecha(m["FECHA_DOCU"]) > fin_de_mes
            )
            final_mes = round(existencia_actual - movimiento_posterior, 4)

            fila[f"Entradas {etiqueta_mes}"] = round(entradas_mes, 4)
            fila[f"Salidas {etiqueta_mes}"] = round(salidas_mes, 4)
            fila[f"Final {etiqueta_mes}"] = final_mes

        costo_promedio = lote.get("COSTO_PROMEDIO")
        costo_promedio = float(costo_promedio) if pd.notna(costo_promedio) else None
        fila["Costo Promedio del Artículo"] = round(costo_promedio, 4) if costo_promedio is not None else None
        fila["Costo Promedio Total"] = (
            round(costo_promedio * existencia_actual, 2) if costo_promedio is not None else None
        )

        filas.append(fila)

    return pd.DataFrame(filas)


def _a_fecha(valor) -> date:
    if isinstance(valor, datetime):
        return valor.date()
    return valor
