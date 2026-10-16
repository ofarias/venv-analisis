from __future__ import annotations

import math
from datetime import date

import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, DataReturnMode, GridOptionsBuilder, JsCode

from controllers.forecast_controller import (
    obtener_forecast_versiones_ctrl,
    clientes_por_producto_ctrl,
    _catalogo_productos_sae,
)
from controllers.forecast_autorizacion_controller import calcular_necesidad_compra_consolidada_ctrl


_MESES = {1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
          7: "jul", 8: "ago", 9: "sep", 10: "oct", 11: "nov", 12: "dic"}

_ORIGEN_BADGE = {
    "autorizado": "✅ autorizado",
    "presupuesto (fallback)": "🟡 presupuesto (pendiente de autorizar)",
}

# por cada mes se repiten estas 5 columnas. Resultado = Stock - Forecast + DP
# (sin acotar a 0, puede quedar negativo) y ES el Stock del mes siguiente —
# el arrastre real. "DP" es solo informativo (lo que ya está planeado/
# cubierto por forecast de compra o presupuesto autorizado); "Orden Sugerida"
# es el valor accionable para Compras (ver utils/forecast_engine.py::
# calcular_necesidad_compra_dp_producto para el faltante mes a mes). Ninguno
# de los dos participa en el arrastre, que siempre usa Resultado.
_SUFIJOS_MES = [
    ("Stock", "existencia_inicio"),
    ("Forecast", "venta_forecast"),
    ("DP (info)", "compra_cubierta"),
    ("Resultado", "resultado"),
    ("Orden Sugerida", "necesidad"),
]


def _meses_cobertura_resurtido(tiempo_resurtido) -> int:
    """Cuántos meses hacia adelante cubre un pedido colocado hoy, según el
    tiempo de resurtido del producto (SAE, días) — redondeado hacia arriba a
    meses completos. Sin dato o 0, se asume 1 mes (el actual nada más)."""
    if tiempo_resurtido is None or pd.isna(tiempo_resurtido) or tiempo_resurtido <= 0:
        return 1
    return max(1, math.ceil(float(tiempo_resurtido) / 30))

_VALUE_FORMATTER_MILES_JS = JsCode("""
function(params) {
    if (params.value === null || params.value === undefined || params.value === '') return '';
    return Number(params.value).toLocaleString('en-US', {minimumFractionDigits: 0, maximumFractionDigits: 0});
}
""")

# resalta en rojo un Resultado negativo (déficit arrastrado) y en verde uno
# positivo — igual criterio verde/rojo que el resto de la app
_CELL_STYLE_RESULTADO_JS = JsCode("""
function(params) {
    if (params.value < 0) {
        return {backgroundColor: '#f8d7da', color: '#721c24', fontWeight: 'bold'};
    }
    if (params.value > 0) {
        return {backgroundColor: '#d4edda', color: '#155724'};
    }
    return null;
}
""")


def _construir_tabla_mensual(df_f: pd.DataFrame, meses_sel: list[int]) -> pd.DataFrame:
    """Pivotea el detalle largo (cve_prod × mes) a una fila por producto, con
    5 columnas por cada mes seleccionado (arrastre ya resuelto por el motor)
    y una columna final de necesidad total del período.

    "Orden Sugerida" solo se muestra en el primer mes (el actual): un pedido
    colocado hoy tarda `tiempo_resurtido` días en llegar, así que debe cubrir
    no solo el faltante de este mes sino el de los meses siguientes que
    transcurran mientras llega — se suma el faltante (columna "necesidad") de
    esos meses y se coloca todo en el mes actual; los meses siguientes
    quedan en 0 en esta columna (ya están cubiertos por ese pedido)."""
    base = (
        df_f.drop_duplicates("cve_prod")
        .set_index("cve_prod")[["producto", "tiempo_resurtido", "linea", "origen_forecast", "vendedores"]]
    )
    necesidad_total_por_prod = df_f.groupby("cve_prod")["necesidad"].sum()
    meses_ordenados = sorted(meses_sel)

    filas = []
    for cve, info in base.iterrows():
        fila = {
            "cve_prod": cve,
            "producto": info["producto"],
            "tiempo_resurtido": info["tiempo_resurtido"],
            "linea": info["linea"],
            "origen": _ORIGEN_BADGE.get(info["origen_forecast"], info["origen_forecast"]),
            "vendedores": info["vendedores"],
        }
        sub = df_f[df_f["cve_prod"] == cve].set_index("mes")

        meses_cobertura = _meses_cobertura_resurtido(info["tiempo_resurtido"])
        meses_orden_sugerida = set(meses_ordenados[:meses_cobertura])
        orden_sugerida_total = sum(
            float(sub.loc[m, "necesidad"]) for m in meses_orden_sugerida if m in sub.index
        )
        mes_actual = meses_ordenados[0] if meses_ordenados else None

        for mes in meses_sel:
            mn = _MESES[mes].upper()
            fila_mes = sub.loc[mes] if mes in sub.index else None
            for etiqueta, campo in _SUFIJOS_MES:
                if etiqueta == "Orden Sugerida":
                    valor = orden_sugerida_total if mes == mes_actual else 0.0
                else:
                    valor = float(fila_mes[campo]) if fila_mes is not None else 0.0
                fila[f"{mn} {etiqueta}"] = valor
        fila["Necesidad total"] = float(necesidad_total_por_prod.get(cve, 0.0))
        filas.append(fila)

    return pd.DataFrame(filas)


def mostrar_tab_demanda_forecast() -> None:
    st.caption(
        "Necesidad de **materia prima** consolidada de todos los vendedores — los productos "
        "terminados (con fórmula registrada) se cruzan contra su fórmula y su existencia de "
        "PT (almacén 18) para traducir su venta en materia prima requerida; esta tabla solo "
        "muestra materia prima (cve_prod que inicia con \"B\"), nunca producto terminado. "
        "Usa el forecast de venta/compra ya autorizado de cada vendedor para el mes (o su "
        "presupuesto ya autorizado si todavía no autoriza ese mes), contra la existencia "
        "real de materia prima (almacén 17)."
    )

    hoy = date.today()
    df_versiones = obtener_forecast_versiones_ctrl(usuario_id=0, ver_todas=True)
    anios_disponibles = sorted(
        {int(a) for a in df_versiones["anio"].dropna().unique()} if df_versiones is not None and not df_versiones.empty else set(),
        reverse=True,
    )
    if not anios_disponibles:
        anios_disponibles = [hoy.year]
    elif hoy.year not in anios_disponibles:
        anios_disponibles = sorted(set(anios_disponibles) | {hoy.year}, reverse=True)

    idx_anio_actual = anios_disponibles.index(hoy.year)

    col_anio, col_meses = st.columns([1, 3])
    with col_anio:
        anio_sel = st.selectbox("año", anios_disponibles, index=idx_anio_actual, key="comp_fc_anio")
    with col_meses:
        # necesidad del mes actual en adelante por defecto — sin meses ya
        # pasados que no aportan nada a la compra
        meses_default = [m for m in range(1, 13) if anio_sel > hoy.year or m >= hoy.month]
        meses_sel = st.multiselect(
            "meses", options=list(range(1, 13)), default=meses_default,
            format_func=lambda m: _MESES[m].upper(), key="comp_fc_meses",
        )

    if anio_sel == hoy.year:
        meses_sel = [m for m in meses_sel if m >= hoy.month]
    meses_sel = sorted(meses_sel)
    if not meses_sel:
        st.info("no hay meses vigentes (mes actual en adelante) entre los meses seleccionados")
        return

    with st.spinner("consolidando necesidad de compra de todos los vendedores…"):
        df = calcular_necesidad_compra_consolidada_ctrl(anio=int(anio_sel), meses=meses_sel)

    if df is None or df.empty:
        st.warning(
            "no se encontró necesidad de compra consolidada. Posibles causas:\n"
            "- Ningún vendedor tiene forecast o presupuesto autorizado para ese año\n"
            "- No hay forecast_versiones creadas para ese año"
        )
        return

    # línea (unidad de negocio) y tiempo de resurtido (SAE inve01.tiem_surt,
    # en días) por producto, vía catálogo SAE
    try:
        df_cat = _catalogo_productos_sae()
    except Exception:
        df_cat = pd.DataFrame()
    mapa_linea: dict = {}
    mapa_resurtido: dict = {}
    if df_cat is not None and not df_cat.empty and "cve_art" in df_cat.columns:
        cve_cat = df_cat["cve_art"].astype(str).str.strip()
        if "linea" in df_cat.columns:
            mapa_linea = dict(zip(cve_cat, df_cat["linea"].astype(str).str.strip()))
        if "tiem_surt" in df_cat.columns:
            mapa_resurtido = dict(zip(cve_cat, pd.to_numeric(df_cat["tiem_surt"], errors="coerce")))
    df = df.copy()
    df["linea"] = df["cve_prod"].astype(str).str.strip().map(mapa_linea).fillna("")
    df["tiempo_resurtido"] = df["cve_prod"].astype(str).str.strip().map(mapa_resurtido)

    # cliente(s) por producto, vía líneas autorizadas de presupuesto de ventas
    # del año/meses seleccionados (mismo criterio que Forecast → MDI/Necesidades)
    df_clientes = clientes_por_producto_ctrl(int(anio_sel), meses=tuple(meses_sel))
    clientes_por_prod: dict[str, set] = {}
    if df_clientes is not None and not df_clientes.empty:
        for r in df_clientes.to_dict("records"):
            cve = str(r.get("cve_prod") or "").strip()
            cliente = str(r.get("cliente_excel") or "").strip()
            if cve and cliente:
                clientes_por_prod.setdefault(cve, set()).add(cliente)

    # vendedor(es) por producto — ya viene como texto "A, B" en la columna
    # "vendedores" del consolidado (una fila por mes, el valor se repite)
    vendedores_por_prod: dict[str, set] = {
        str(r["cve_prod"]).strip(): {v.strip() for v in str(r.get("vendedores") or "").split(",") if v.strip()}
        for r in df.drop_duplicates("cve_prod").to_dict("records")
    }

    col_cve, col_prod, col_linea = st.columns(3)
    with col_cve:
        cve_sel = st.multiselect(
            "cve prod", options=sorted(df["cve_prod"].unique()), default=[], key="comp_fc_cve",
        )
    with col_prod:
        prod_sel = st.multiselect(
            "producto", options=sorted(df["producto"].unique()), default=[], key="comp_fc_prod",
        )
    with col_linea:
        lineas_disponibles = sorted({l for l in df["linea"].unique() if l})
        linea_sel = st.multiselect(
            "unidad de negocio (línea)", options=lineas_disponibles, default=[], key="comp_fc_linea",
        )

    col_cliente, col_vendedor, col_origen = st.columns(3)
    with col_cliente:
        clientes_disponibles = sorted({c for cs in clientes_por_prod.values() for c in cs})
        cliente_sel = st.multiselect(
            "cliente", options=clientes_disponibles, default=[], key="comp_fc_cliente",
        )
    with col_vendedor:
        vendedores_disponibles = sorted({v for vs in vendedores_por_prod.values() for v in vs})
        vendedor_sel = st.multiselect(
            "vendedor", options=vendedores_disponibles, default=[], key="comp_fc_vendedor",
        )
    with col_origen:
        origen_sel = st.multiselect(
            "origen", options=["autorizado", "presupuesto (fallback)"],
            default=[], key="comp_fc_origen",
            format_func=lambda o: _ORIGEN_BADGE.get(o, o),
        )

    df_f = df
    if cve_sel:
        df_f = df_f[df_f["cve_prod"].isin(cve_sel)]
    if prod_sel:
        df_f = df_f[df_f["producto"].isin(prod_sel)]
    if linea_sel:
        df_f = df_f[df_f["linea"].isin(linea_sel)]
    if cliente_sel:
        cve_match_cliente = {cve for cve, cs in clientes_por_prod.items() if cs & set(cliente_sel)}
        df_f = df_f[df_f["cve_prod"].isin(cve_match_cliente)]
    if vendedor_sel:
        cve_match_vendedor = {cve for cve, vs in vendedores_por_prod.items() if vs & set(vendedor_sel)}
        df_f = df_f[df_f["cve_prod"].isin(cve_match_vendedor)]
    if origen_sel:
        df_f = df_f[df_f["origen_forecast"].isin(origen_sel)]

    if df_f.empty:
        st.info("sin resultados para los filtros seleccionados")
        return

    productos_fallback = df_f.loc[df_f["origen_forecast"] == "presupuesto (fallback)", "cve_prod"].nunique()
    necesidad_total = float(df_f["necesidad"].sum())
    c1, c2, c3 = st.columns(3)
    c1.metric("productos", df_f["cve_prod"].nunique())
    c2.metric("necesidad total del período (kg)", f"{necesidad_total:,.0f}")
    c3.metric("productos con algún mes sin autorizar", productos_fallback)

    st.divider()
    st.caption(
        "🔒 cve prod, producto, tiempo de resurtido y línea quedan fijos al hacer scroll — "
        "Resultado = Stock - Forecast + DP (si queda en rojo/negativo, se arrastra "
        "como déficit al mes siguiente) — DP (info) es solo informativo (lo ya planeado). "
        "**Orden Sugerida solo aparece en el mes actual**: suma el faltante de ese mes y de "
        "los siguientes que transcurran mientras llega el pedido, según el tiempo de "
        "resurtido del producto (ej. 60 días = 2 meses) — los meses siguientes quedan en 0, "
        "ya cubiertos por ese pedido."
    )
    tabla = _construir_tabla_mensual(df_f, meses_sel).sort_values("Necesidad total", ascending=False)

    cols_orden = ["cve_prod", "producto", "tiempo_resurtido", "linea"]
    cols_numericas = ["Necesidad total"]
    cols_resultado = set()
    for mes in meses_sel:
        mn = _MESES[mes].upper()
        for etiqueta, _campo in _SUFIJOS_MES:
            col = f"{mn} {etiqueta}"
            cols_orden.append(col)
            cols_numericas.append(col)
            if etiqueta == "Resultado":
                cols_resultado.add(col)
    cols_orden += ["Necesidad total", "origen", "vendedores"]

    tabla["tiempo_resurtido"] = pd.to_numeric(tabla["tiempo_resurtido"], errors="coerce")
    for col in cols_numericas:
        tabla[col] = pd.to_numeric(tabla[col], errors="coerce").round(0)

    tabla = tabla[cols_orden].reset_index(drop=True)

    gb = GridOptionsBuilder.from_dataframe(tabla)
    gb.configure_default_column(editable=False, resizable=True, width=110)
    gb.configure_column("cve_prod", headerName="cve prod", pinned="left", width=110)
    gb.configure_column("producto", headerName="producto", pinned="left", width=200)
    gb.configure_column(
        "tiempo_resurtido", headerName="tiempo resurtido (días)", pinned="left", width=140,
        type=["numericColumn"], valueFormatter=_VALUE_FORMATTER_MILES_JS,
    )
    gb.configure_column("linea", headerName="línea", pinned="left", width=120)
    gb.configure_column("origen", headerName="origen del forecast", width=200)
    gb.configure_column("vendedores", headerName="vendedor(es)", width=220)
    for col in cols_numericas:
        cell_style = _CELL_STYLE_RESULTADO_JS if col in cols_resultado else None
        gb.configure_column(
            col, type=["numericColumn"],
            valueFormatter=_VALUE_FORMATTER_MILES_JS,
            cellStyle=cell_style,
        )

    AgGrid(
        tabla,
        gridOptions=gb.build(),
        update_on=[],
        data_return_mode=DataReturnMode.AS_INPUT,
        fit_columns_on_grid_load=False,
        allow_unsafe_jscode=True,
        enable_enterprise_modules=True,
        height=min(56 + len(tabla) * 35, 650),
        key=f"comp_fc_grid_{anio_sel}",
    )

    csv = tabla[cols_orden].to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ descargar CSV",
        data=csv,
        file_name=f"demanda_forecast_consolidada_{anio_sel}.csv",
        mime="text/csv",
        key="comp_fc_dl_csv",
    )
