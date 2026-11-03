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
from models.presupuesto_ventas_model import obtener_presupuesto_ventas_model
from models.formulas_readonly_model import listar_formulas_readonly_model
from models.formulas_model import listar_mp_sae_model, listar_pt_sae_model
from utils.forecast_engine import calcular_necesidad_compra_dp_producto
from controllers.forecast_controller import (
    obtener_forecast_versiones_ctrl,
    obtener_forecast_detalle_ctrl,
    obtener_presupuesto_resumen_por_anio_ctrl,
    obtener_presupuesto_compras_resumen_por_anio_ctrl,
)
from controllers.presupuesto_admin_controller import obtener_presupuesto_ventas_compras_ctrl


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
    Necesidad de **materia prima** (cve_prod que inicia con "B") por mes,
    consolidada entre TODOS los vendedores: para cada vendedor y mes, usa su
    forecast de venta/compra si ese mes está 'autorizada'; si no, cae al
    presupuesto de ventas/compras YA AUTORIZADO de ESE MISMO vendedor.

    Un producto terminado (PT, con fórmula registrada) no se compra, se
    fabrica — su venta consolidada se cruza contra su fórmula (carrier +
    enzimas + auxiliares, % por componente) y contra su existencia de PT
    (almacén 18, neteada mes a mes) para obtener cuánta materia prima hace
    falta producirlo; esa necesidad derivada se suma a la de cada materia
    prima junto con lo que esa misma se forecastea/compra directamente (una
    materia prima puede venderse ella misma Y ser insumo de varias fórmulas
    a la vez). Solo hasta el final, ya por materia prima, se corre el motor
    de arrastre mes a mes (`calcular_necesidad_compra_dp_producto`) contra su
    existencia física real (almacén 17).

    Retorna una fila por (cve_prod, mes) — "formato largo" para poder
    pivotear en la vista a Stock | Forecast | DP | Resultado | Orden
    Sugerida por mes. `origen_forecast` y `vendedores` son a nivel producto
    (repetidos en cada fila de mes); para una materia prima derivada de un
    PT, los vendedores son los de ese PT.
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

    return _necesidad_compra_desde_acumulados(
        venta_acc, compra_acc, vendedores_por_producto, meses,
        fallback_venta_keys=fallback_venta, fallback_compra_keys=fallback_compra,
        etiqueta_normal="autorizado", etiqueta_fallback="presupuesto (fallback)",
    )


def _necesidad_compra_desde_acumulados(
    venta_acc: dict[tuple[str, int], float],
    compra_acc: dict[tuple[str, int], float],
    vendedores_por_producto: dict[str, set[str]],
    meses: list[int],
    fallback_venta_keys: set[tuple[str, int]],
    fallback_compra_keys: set[tuple[str, int]],
    etiqueta_normal: str,
    etiqueta_fallback: str,
) -> pd.DataFrame:
    """Explosión de fórmula (PT → materia prima) + arrastre mes a mes contra
    existencia real — parte común de `calcular_necesidad_compra_consolidada_ctrl`
    (Forecast, con distinción autorizado/fallback) y
    `calcular_necesidad_compra_presupuesto_ctrl` (Presupuesto de Ventas
    capturado, sin esa distinción — ahí ambas etiquetas llegan iguales y
    `fallback_venta_keys`/`fallback_compra_keys` llegan vacíos).

    Un producto terminado no se compra, se fabrica — se cruza su venta
    consolidada (`venta_acc`) contra su fórmula y su existencia de PT
    (almacén 18, neteada mes a mes) para traducirla a materia prima
    requerida; esa necesidad derivada se suma a la de cada materia prima
    junto con lo que esa misma se forecastea/compra directamente. Solo hasta
    el final, ya por materia prima, se corre el motor de arrastre mes a mes
    (`calcular_necesidad_compra_dp_producto`) contra su existencia física
    real (almacén 17), neteando también contra `compra_acc`.
    """
    try:
        formulas = listar_formulas_readonly_model()
    except Exception:
        formulas = []
    formula_por_sae = {
        str(f.get("cve_sae") or "").strip(): f
        for f in formulas if str(f.get("cve_sae") or "").strip()
    }

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
            if cve:
                pt_exist_map[cve] = float(r.get("exist") or 0)

    venta_mp_acc: dict[tuple[str, int], float] = {}
    fallback_mp: set[tuple[str, int]] = set()
    vendedores_mp: dict[str, set[str]] = {}

    def _propagar_mp(cve_mp: str, mes: int, valor: float, origen_cve: str, es_fallback: bool) -> None:
        if not valor:
            return
        key = (cve_mp, mes)
        venta_mp_acc[key] = venta_mp_acc.get(key, 0.0) + valor
        if es_fallback:
            fallback_mp.add(key)
        vendedores_mp.setdefault(cve_mp, set()).update(vendedores_por_producto.get(origen_cve, set()))

    meses_ordenados = sorted(meses)
    for cve_prod in sorted({k[0] for k in venta_acc}):
        formula = formula_por_sae.get(cve_prod)
        componentes: list[dict] = []
        if formula:
            carrier = formula.get("carrier")
            if isinstance(carrier, dict) and carrier.get("mp"):
                componentes.append(carrier)
            for grupo in ("enzimas", "auxiliares"):
                lista = formula.get(grupo)
                if isinstance(lista, list):
                    componentes.extend([c for c in lista if isinstance(c, dict) and c.get("mp")])

        if not componentes:
            # sin fórmula (o fórmula sin materias primas declaradas): pasa
            # tal cual — si de verdad es materia prima (prefijo "B"), queda
            # igual más abajo; si no, se descarta al filtrar por "B"
            for mes in meses_ordenados:
                valor = venta_acc.get((cve_prod, mes), 0.0)
                _propagar_mp(cve_prod, mes, valor, cve_prod, (cve_prod, mes) in fallback_venta_keys)
            continue

        stock_pt = pt_exist_map.get(str(cve_prod).strip().upper(), 0.0)
        for mes in meses_ordenados:
            fc_kg = venta_acc.get((cve_prod, mes), 0.0)
            existencia_pt_mes = stock_pt
            a_producir_kg = max(0.0, fc_kg - existencia_pt_mes)
            stock_pt = max(0.0, existencia_pt_mes - fc_kg)
            if a_producir_kg <= 0:
                continue
            es_fallback = (cve_prod, mes) in fallback_venta_keys
            for comp in componentes:
                cve_mp = str(comp.get("mp") or "").strip()
                pct = float(comp.get("pct") or 0)
                if not cve_mp or pct <= 0:
                    continue
                _propagar_mp(cve_mp, mes, a_producir_kg * (pct / 100), cve_prod, es_fallback)

    cve_prods_mp = sorted({
        cve for cve in ({k[0] for k in venta_mp_acc} | {k[0] for k in compra_acc})
        if str(cve).strip().upper().startswith("B")
    })
    if not cve_prods_mp:
        return pd.DataFrame()

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
            if cve:
                mp_exist_map[cve] = float(r.get("exist") or 0)
                mp_nombre_map[cve] = str(r.get("descr") or cve).strip()

    try:
        df_cat = obtener_catalogo_productos_pv_model()
    except Exception:
        df_cat = pd.DataFrame()
    cat_map: dict = {}
    if df_cat is not None and not df_cat.empty:
        cat_map = dict(zip(df_cat["cve_prod"].astype(str).str.strip(), df_cat["descr"]))

    filas = []
    for cve in cve_prods_mp:
        cve_up = cve.strip().upper()
        stock = mp_exist_map.get(cve_up, 0.0)

        df_venta_prod = pd.DataFrame([
            {"cve_prod": cve, "mes": mes, "forecast": venta_mp_acc.get((cve, mes), 0.0)} for mes in meses
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

        hubo_fallback = any((cve, mes) in fallback_mp or (cve, mes) in fallback_compra_keys for mes in meses)
        origen_prod = etiqueta_fallback if hubo_fallback else etiqueta_normal
        vendedores = ", ".join(sorted(vendedores_mp.get(cve, set())))
        producto = mp_nombre_map.get(cve_up) or cat_map.get(cve, cve)

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


_MES_UNICO_ANUAL = [1]  # bucket único: el helper compartido solo necesita UN "mes" cuando
# se le pasa el total anual ya sumado — no hay arrastre que resolver con un
# solo periodo. El resultado final (existencia - venta + compra, sin topar en
# 0) y la explosión de fórmula PT→MP dan el mismo total trabajando así que
# mes a mes y sumando al final, porque ninguno de los dos tiene un "piso" que
# dependa del orden de los meses (demostrable: ambos son una resta corrida
# que nunca se repone a la mitad del año en este modelo).


@st.cache_data(ttl=300, show_spinner="calculando congruencia de presupuesto (venta vs. compra vs. existencia)…")
def calcular_congruencia_presupuesto_anual_ctrl(anio: int) -> pd.DataFrame:
    """
    Congruencia ANUAL (sin desglose por mes) entre lo que se presupuesta
    vender, lo que se presupuesta comprar y la existencia real de hoy: toma
    DIRECTAMENTE todo el Presupuesto de Ventas capturado de ese año (todos
    los vendedores, sin filtrar por autorización — así lo pidió el usuario),
    lo convierte a materia prima vía fórmula, y neta el total contra el
    Presupuesto de Compras capturado de ese mismo año (también global, todos
    los usuarios) y contra la existencia real en SAE (almacén 17).

    Una fila por materia prima: cve_prod, producto, existencia_inicio
    (existencia real de HOY), venta_forecast (total anual presupuestado a
    vender, ya convertido a MP), compra_cubierta (total anual presupuestado
    a comprar), necesidad (faltante para no quedar en negativo — 0 si ya
    está cubierto), resultado (existencia + compra - venta; negativo =
    faltante, positivo = superávit), vendedores.
    """
    df = obtener_presupuesto_ventas_compras_ctrl(anio=anio, tipo=["venta", "compra"])
    if df is None or df.empty:
        return pd.DataFrame()

    df["cantidad_kg"] = pd.to_numeric(df["cantidad_kg"], errors="coerce").fillna(0.0)
    df["anio"] = pd.to_numeric(df["anio"], errors="coerce")
    df["cve_prod"] = df["cve_prod"].astype(str).str.strip()
    # el filtro anio=anio ya va en el SQL (obtener_presupuesto_ventas_compras_model);
    # se repite aquí como segunda barrera para que nunca se mezclen años aunque
    # llegara alguna fila con anio distinto o NaN. Sin filtro de mes — se
    # quiere el total del año completo, no un rango.
    df = df[(df["cve_prod"] != "") & (df["anio"] == anio) & (df["cantidad_kg"] != 0)]
    if df.empty:
        return pd.DataFrame()

    venta_acc: dict[tuple[str, int], float] = {}
    compra_acc: dict[tuple[str, int], float] = {}
    vendedores_por_producto: dict[str, set[str]] = {}

    for r in df.to_dict("records"):
        key = (r["cve_prod"], _MES_UNICO_ANUAL[0])
        if r["tipo"] == "venta":
            venta_acc[key] = venta_acc.get(key, 0.0) + float(r["cantidad_kg"])
            nombre = str(r.get("usuario_nombre") or "").strip()
            if nombre:
                vendedores_por_producto.setdefault(r["cve_prod"], set()).add(nombre)
        else:
            compra_acc[key] = compra_acc.get(key, 0.0) + float(r["cantidad_kg"])

    df_resultado = _necesidad_compra_desde_acumulados(
        venta_acc, compra_acc, vendedores_por_producto, _MES_UNICO_ANUAL,
        fallback_venta_keys=set(), fallback_compra_keys=set(),
        etiqueta_normal="presupuesto capturado", etiqueta_fallback="presupuesto capturado",
    )
    if df_resultado.empty:
        return df_resultado
    return df_resultado.drop(columns=["mes", "mes_nombre", "origen_forecast"])


def _lineas_presupuesto_fallback(usuario_id: int, anio: int, mes: int, cve_prod: str) -> list[dict]:
    """Líneas de Presupuesto de Ventas (del dueño `usuario_id`, ya
    autorizadas) que arman el total usado como fallback para `cve_prod` en
    `mes` — para poder mostrar, ej., qué cliente(s) componen un total
    consolidado (ver `desglosar_necesidad_mp_ctrl`)."""
    try:
        df = obtener_presupuesto_ventas_model(
            anio=anio, mes=mes, cve_prod=cve_prod, usuario_id=usuario_id, solo_autorizados=True,
        )
    except Exception:
        return []
    if df is None or df.empty:
        return []
    df = df[df["seccion"] == "KG"]
    if df.empty:
        return []
    return [
        {
            "cliente": str(r.get("cliente_excel") or "").strip(),
            "cve_clie": str(r.get("cve_clie") or "").strip(),
            "cantidad_kg": float(r.get("cantidad_kg") or 0.0),
        }
        for r in df.to_dict("records")
        if float(r.get("cantidad_kg") or 0.0)
    ]


@st.cache_data(ttl=300, show_spinner="calculando desglose…")
def desglosar_necesidad_mp_ctrl(cve_mp: str, anio: int, meses: list[int]) -> dict:
    """Desglose, mes a mes, de cómo se arma el "Forecast" (demanda) de UNA
    materia prima en el consolidado de Compras -> Demanda — mismo cálculo
    que `calcular_necesidad_compra_consolidada_ctrl`, pero conservando la
    atribución (qué vendedor, autorizado o presupuesto/fallback, y si es
    fallback qué líneas de Presupuesto de Ventas lo componen) en vez de solo
    el total ya sumado. Dos fuentes posibles, no excluyentes:
    - "directo": la propia materia prima tiene forecast/presupuesto de venta
      (alguien la vende directamente, ej. para reventa).
    - "formula": viene de un producto terminado que la usa como insumo
      (carrier/enzima/auxiliar) — se cruza la venta consolidada de ESE PT
      contra su existencia (almacén 18) mes a mes, igual que en el
      consolidado real, y se expone el % que le toca a esta materia prima.

    Retorna {"meses": [...], "directo": {mes: [fuente,...]},
    "formula": {mes: [{"cve_pt","producto_pt","rol","pct",
    "venta_consolidada","existencia_pt_inicio","a_producir","aporte",
    "fuentes":[...]}]}} — cada "fuente" es
    {"vendedor","origen","valor","id_version","lineas"} (lineas solo si
    origen es fallback)."""
    cve_mp = str(cve_mp).strip().upper()
    meses_ordenados = sorted(meses)

    df_versiones = obtener_forecast_versiones_ctrl(usuario_id=0, anio=anio, ver_todas=True)
    if df_versiones is None or df_versiones.empty:
        return {"meses": meses_ordenados, "directo": {m: [] for m in meses_ordenados}, "formula": {m: [] for m in meses_ordenados}}

    # fórmulas que usan cve_mp como componente (carrier/enzima/auxiliar)
    try:
        formulas = listar_formulas_readonly_model()
    except Exception:
        formulas = []
    pts_relevantes: dict[str, tuple[str, float]] = {}
    for f in formulas:
        cve_sae = str(f.get("cve_sae") or "").strip()
        if not cve_sae:
            continue
        componentes = []
        carrier = f.get("carrier")
        if isinstance(carrier, dict) and carrier.get("mp"):
            componentes.append(("carrier", carrier))
        for grupo in ("enzimas", "auxiliares"):
            for c in (f.get(grupo) or []):
                if isinstance(c, dict) and c.get("mp"):
                    componentes.append((grupo, c))
        for rol, c in componentes:
            if str(c.get("mp") or "").strip().upper() == cve_mp:
                pts_relevantes[cve_sae] = (rol, float(c.get("pct") or 0))

    cve_prods_fuente = {cve_mp} | set(pts_relevantes.keys())

    # venta consolidada CON atribución, solo de los cve_prod relevantes
    # (la propia materia prima + los PT que la usan en su fórmula)
    venta_acc: dict[tuple[str, int], float] = {}
    fuentes: dict[tuple[str, int], list[dict]] = {}

    for v in df_versiones.to_dict("records"):
        id_version = int(v["id_version"])
        usuario_id_v = int(v.get("usuario_id") or 0)
        nombre_v = str(v.get("propietario") or f"usuario {usuario_id_v}")

        df_estatus = obtener_forecast_mes_estatus_ctrl(id_version=id_version, anio=anio)
        estatus_venta: dict[int, str] = {}
        if df_estatus is not None and not df_estatus.empty:
            for r in df_estatus.to_dict("records"):
                if r["tipo"] == "venta":
                    estatus_venta[int(r["mes"])] = r["estatus"]

        df_fc_venta = obtener_forecast_detalle_ctrl(id_version=id_version, seccion="KG", tipo="venta")
        df_pv_v = obtener_presupuesto_resumen_por_anio_ctrl(
            anio=anio, seccion="KG", region=None, usuario_id=usuario_id_v, solo_autorizados=True,
        )

        for mes in meses_ordenados:
            autorizado = estatus_venta.get(mes) == "autorizada"
            if autorizado and df_fc_venta is not None and not df_fc_venta.empty:
                df_mes = df_fc_venta[pd.to_numeric(df_fc_venta["mes"], errors="coerce") == mes]
                col_valor = "forecast"
            elif df_pv_v is not None and not df_pv_v.empty:
                df_mes = df_pv_v[pd.to_numeric(df_pv_v["mes"], errors="coerce") == mes]
                col_valor = "total_kg"
            else:
                continue
            if df_mes is None or df_mes.empty or col_valor not in df_mes.columns:
                continue

            for r in df_mes.to_dict("records"):
                cve = str(r.get("cve_prod") or "").strip()
                if cve not in cve_prods_fuente:
                    continue
                valor = float(r.get(col_valor) or 0.0)
                if not valor:
                    continue
                key = (cve, mes)
                venta_acc[key] = venta_acc.get(key, 0.0) + valor
                origen = "autorizado" if autorizado else "presupuesto (fallback)"
                lineas = _lineas_presupuesto_fallback(usuario_id_v, anio, mes, cve) if not autorizado else None
                fuentes.setdefault(key, []).append({
                    "vendedor": nombre_v, "origen": origen, "valor": round(valor, 2),
                    "id_version": id_version, "lineas": lineas,
                })

    directo = {mes: fuentes.get((cve_mp, mes), []) for mes in meses_ordenados}

    # explosión de fórmula, igual que en el consolidado real — arrastre de
    # existencia PT mes a mes, solo para los PT que sí usan esta MP
    try:
        rows_pt = listar_pt_sae_model()
        df_pt_exist = pd.DataFrame(rows_pt) if rows_pt else pd.DataFrame()
    except Exception:
        df_pt_exist = pd.DataFrame()
    if not df_pt_exist.empty:
        df_pt_exist.columns = [c.lower() for c in df_pt_exist.columns]
    pt_exist_map: dict = {}
    pt_nombre_map: dict = {}
    if not df_pt_exist.empty and "cve_art" in df_pt_exist.columns:
        for r in df_pt_exist.to_dict("records"):
            cve = str(r.get("cve_art") or "").strip().upper()
            if cve:
                pt_exist_map[cve] = float(r.get("exist") or 0)
                pt_nombre_map[cve] = str(r.get("descr") or cve).strip()

    formula_detalle: dict[int, list[dict]] = {mes: [] for mes in meses_ordenados}
    for cve_pt, (rol, pct) in pts_relevantes.items():
        stock_pt = pt_exist_map.get(cve_pt.strip().upper(), 0.0)
        for mes in meses_ordenados:
            fc_kg = venta_acc.get((cve_pt, mes), 0.0)
            existencia_pt_mes = stock_pt
            a_producir_kg = max(0.0, fc_kg - existencia_pt_mes)
            stock_pt = max(0.0, existencia_pt_mes - fc_kg)
            aporte = a_producir_kg * (pct / 100) if a_producir_kg > 0 else 0.0
            if fc_kg or aporte:
                formula_detalle[mes].append({
                    "cve_pt": cve_pt,
                    "producto_pt": pt_nombre_map.get(cve_pt.strip().upper(), cve_pt),
                    "rol": rol,
                    "pct": pct,
                    "venta_consolidada": round(fc_kg, 2),
                    "existencia_pt_inicio": round(existencia_pt_mes, 2),
                    "a_producir": round(a_producir_kg, 2),
                    "aporte": round(aporte, 3),
                    "fuentes": fuentes.get((cve_pt, mes), []),
                })

    return {"meses": meses_ordenados, "directo": directo, "formula": formula_detalle}


@st.cache_data(ttl=300, show_spinner="calculando desglose…")
def desglosar_necesidad_mp_presupuesto_ctrl(cve_mp: str, anio: int) -> dict:
    """Desglose ANUAL (sin separar por mes) de cómo se arma la demanda de UNA
    materia prima en `calcular_congruencia_presupuesto_anual_ctrl`: de qué
    vendedor(es)/cliente(s) sale la venta capturada (directa, si alguien la
    vende tal cual) y/o qué producto(s) terminado(s) la usan en su fórmula —
    cruzado contra la existencia de ese PT — para el año completo.

    Retorna {"directo": [fuente,...], "formula": [{"cve_pt","producto_pt",
    "rol","pct","venta_consolidada","existencia_pt_inicio","a_producir",
    "aporte","fuentes":[...]}]} — cada "fuente" es
    {"vendedor","origen","valor","lineas"}."""
    cve_mp = str(cve_mp).strip().upper()

    try:
        formulas = listar_formulas_readonly_model()
    except Exception:
        formulas = []
    pts_relevantes: dict[str, tuple[str, float]] = {}
    for f in formulas:
        cve_sae = str(f.get("cve_sae") or "").strip()
        if not cve_sae:
            continue
        componentes = []
        carrier = f.get("carrier")
        if isinstance(carrier, dict) and carrier.get("mp"):
            componentes.append(("carrier", carrier))
        for grupo in ("enzimas", "auxiliares"):
            for c in (f.get(grupo) or []):
                if isinstance(c, dict) and c.get("mp"):
                    componentes.append((grupo, c))
        for rol, c in componentes:
            if str(c.get("mp") or "").strip().upper() == cve_mp:
                pts_relevantes[cve_sae] = (rol, float(c.get("pct") or 0))

    cve_prods_fuente = {cve_mp} | set(pts_relevantes.keys())

    df = obtener_presupuesto_ventas_compras_ctrl(anio=anio, tipo=["venta"])
    venta_acc: dict[str, float] = {}
    fuentes: dict[str, list[dict]] = {}
    if df is not None and not df.empty:
        df["cantidad_kg"] = pd.to_numeric(df["cantidad_kg"], errors="coerce").fillna(0.0)
        df["anio"] = pd.to_numeric(df["anio"], errors="coerce")
        df["cve_prod"] = df["cve_prod"].astype(str).str.strip()
        df = df[
            (df["anio"] == anio) & df["cve_prod"].isin(cve_prods_fuente) & (df["cantidad_kg"] != 0)
        ]
        for (cve, vendedor), grupo in df.groupby(["cve_prod", "usuario_nombre"], dropna=False):
            total_vendedor = float(grupo["cantidad_kg"].sum())
            venta_acc[cve] = venta_acc.get(cve, 0.0) + total_vendedor
            fuentes.setdefault(cve, []).append({
                "vendedor": str(vendedor or "").strip() or "(sin vendedor)",
                "origen": "presupuesto capturado",
                "valor": round(total_vendedor, 2),
                "lineas": [
                    {
                        "cliente": str(r.get("cliente_excel") or "").strip(),
                        "cve_clie": str(r.get("cve_clie") or "").strip(),
                        "cantidad_kg": float(r.get("cantidad_kg") or 0.0),
                    }
                    for r in grupo.to_dict("records")
                    if float(r.get("cantidad_kg") or 0.0)
                ],
            })

    directo = fuentes.get(cve_mp, [])

    try:
        rows_pt = listar_pt_sae_model()
        df_pt_exist = pd.DataFrame(rows_pt) if rows_pt else pd.DataFrame()
    except Exception:
        df_pt_exist = pd.DataFrame()
    if not df_pt_exist.empty:
        df_pt_exist.columns = [c.lower() for c in df_pt_exist.columns]
    pt_exist_map: dict = {}
    pt_nombre_map: dict = {}
    if not df_pt_exist.empty and "cve_art" in df_pt_exist.columns:
        for r in df_pt_exist.to_dict("records"):
            cve = str(r.get("cve_art") or "").strip().upper()
            if cve:
                pt_exist_map[cve] = float(r.get("exist") or 0)
                pt_nombre_map[cve] = str(r.get("descr") or cve).strip()

    formula_detalle: list[dict] = []
    for cve_pt, (rol, pct) in pts_relevantes.items():
        stock_pt = pt_exist_map.get(cve_pt.strip().upper(), 0.0)
        fc_kg = venta_acc.get(cve_pt, 0.0)
        existencia_pt_inicio = stock_pt
        a_producir_kg = max(0.0, fc_kg - existencia_pt_inicio)
        aporte = a_producir_kg * (pct / 100) if a_producir_kg > 0 else 0.0
        if fc_kg or aporte:
            formula_detalle.append({
                "cve_pt": cve_pt,
                "producto_pt": pt_nombre_map.get(cve_pt.strip().upper(), cve_pt),
                "rol": rol,
                "pct": pct,
                "venta_consolidada": round(fc_kg, 2),
                "existencia_pt_inicio": round(existencia_pt_inicio, 2),
                "a_producir": round(a_producir_kg, 2),
                "aporte": round(aporte, 3),
                "fuentes": fuentes.get(cve_pt, []),
            })

    return {"directo": directo, "formula": formula_detalle}
