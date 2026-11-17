from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, DataReturnMode, GridOptionsBuilder, JsCode

from controllers.forecast_controller import _catalogo_productos_sae
from controllers.forecast_autorizacion_controller import (
    calcular_congruencia_presupuesto_anual_ctrl,
    calcular_congruencia_presupuesto_mensual_ctrl,
    desglosar_necesidad_mp_presupuesto_ctrl,
    desglosar_necesidad_mp_presupuesto_mensual_ctrl,
)

_MESES = {1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
          7: "jul", 8: "ago", 9: "sep", 10: "oct", 11: "nov", 12: "dic"}

# etiquetas correctas para esta pantalla — el origen es el Presupuesto de
# Ventas/Compras capturado, NUNCA un Forecast, así que no se reutilizan los
# sufijos ("Forecast", "DP (info)", "Orden Sugerida") de
# tab_demanda_forecast_view.py.
_SUFIJOS_MES_PV = [
    ("Existencia", "existencia_inicio"),
    ("Presupuesto Venta", "venta_forecast"),
    ("Presupuesto Compra", "compra_cubierta"),
    ("Resultado", "resultado"),
    ("Faltante", "necesidad"),
]

_VALUE_FORMATTER_MILES_JS = JsCode("""
function(params) {
    if (params.value === null || params.value === undefined || params.value === '') return '';
    return Number(params.value).toLocaleString('en-US', {minimumFractionDigits: 0, maximumFractionDigits: 0});
}
""")

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


def mostrar_tab_demanda_presupuesto() -> None:
    st.caption(
        "Congruencia entre lo que se presupuesta **vender**, lo que se presupuesta **comprar** "
        "y la **existencia real de hoy** — tomado DIRECTO del Presupuesto de Ventas y "
        "Presupuesto de Compras capturados (todos los vendedores/usuarios, sin filtrar por "
        "autorización — a diferencia de 'Demanda (Forecast)', aquí no interviene ninguna "
        "versión de Forecast). Los productos terminados (con fórmula registrada) se cruzan "
        "contra su fórmula y su existencia de PT (almacén 18) para traducir su venta en "
        "materia prima requerida; esta tabla solo muestra materia prima (cve_prod que inicia "
        "con \"B\")."
    )

    hoy = date.today()
    col_anio, col_vista = st.columns([1, 2])
    with col_anio:
        anio_sel = st.number_input(
            "año", min_value=2016, max_value=hoy.year + 2, value=hoy.year,
            step=1, key="comp_pv_anio",
        )
    anio_sel = int(anio_sel)
    with col_vista:
        vista = st.radio(
            "vista", ["Anual (totales)", "Mensual (detalle por mes)"],
            horizontal=True, key="comp_pv_vista",
        )

    if vista == "Anual (totales)":
        _mostrar_vista_anual(anio_sel)
    else:
        _mostrar_vista_mensual(anio_sel)


def _catalogo_linea() -> dict:
    try:
        df_cat = _catalogo_productos_sae()
    except Exception:
        df_cat = pd.DataFrame()
    if df_cat is None or df_cat.empty or "cve_art" not in df_cat.columns or "linea" not in df_cat.columns:
        return {}
    cve_cat = df_cat["cve_art"].astype(str).str.strip()
    return dict(zip(cve_cat, df_cat["linea"].astype(str).str.strip()))


def _filtros_comunes(df: pd.DataFrame, key_prefix: str) -> tuple[pd.DataFrame, dict]:
    """Filtros de cve_prod/producto/línea/vendedor, iguales para la vista
    anual y la mensual — devuelve el df filtrado y un resumen de filtros
    aplicados (para el caption del CSV/encabezado, si se necesita)."""
    vendedores_por_prod: dict[str, set] = {
        str(r["cve_prod"]).strip(): {v.strip() for v in str(r.get("vendedores") or "").split(",") if v.strip()}
        for r in df.drop_duplicates("cve_prod").to_dict("records")
    }

    col_cve, col_prod, col_linea = st.columns(3)
    with col_cve:
        cve_sel = st.multiselect(
            "cve prod", options=sorted(df["cve_prod"].unique()), default=[], key=f"{key_prefix}_cve",
        )
    with col_prod:
        prod_sel = st.multiselect(
            "producto", options=sorted(df["producto"].unique()), default=[], key=f"{key_prefix}_prod",
        )
    with col_linea:
        lineas_disponibles = sorted({l for l in df["linea"].unique() if l})
        linea_sel = st.multiselect(
            "unidad de negocio (línea)", options=lineas_disponibles, default=[], key=f"{key_prefix}_linea",
        )
    vendedores_disponibles = sorted({v for vs in vendedores_por_prod.values() for v in vs})
    vendedor_sel = st.multiselect(
        "vendedor", options=vendedores_disponibles, default=[], key=f"{key_prefix}_vendedor",
    )

    df_f = df
    if cve_sel:
        df_f = df_f[df_f["cve_prod"].isin(cve_sel)]
    if prod_sel:
        df_f = df_f[df_f["producto"].isin(prod_sel)]
    if linea_sel:
        df_f = df_f[df_f["linea"].isin(linea_sel)]
    if vendedor_sel:
        cve_match_vendedor = {cve for cve, vs in vendedores_por_prod.items() if vs & set(vendedor_sel)}
        df_f = df_f[df_f["cve_prod"].isin(cve_match_vendedor)]

    return df_f, {"cve": cve_sel, "producto": prod_sel, "linea": linea_sel, "vendedor": vendedor_sel}


def _mostrar_vista_anual(anio_sel: int) -> None:
    with st.spinner("calculando congruencia de presupuesto…"):
        df = calcular_congruencia_presupuesto_anual_ctrl(anio=anio_sel)

    if df is None or df.empty:
        st.warning(f"no hay Presupuesto de Ventas capturado para el año {anio_sel}.")
        return

    df = df.copy()
    mapa_linea = _catalogo_linea()
    df["linea"] = df["cve_prod"].astype(str).str.strip().map(mapa_linea).fillna("")

    df_f, _ = _filtros_comunes(df, "comp_pv")
    if df_f.empty:
        st.info("sin resultados para los filtros seleccionados")
        return

    con_faltante = int((df_f["necesidad"] > 0).sum())
    c1, c2, c3 = st.columns(3)
    c1.metric("materias primas analizadas", df_f["cve_prod"].nunique())
    c2.metric("con faltante (necesidad > 0)", con_faltante)
    c3.metric("faltante total del año (kg)", f"{float(df_f['necesidad'].sum()):,.0f}")

    tabla = df_f.rename(columns={
        "existencia_inicio": "Existencia hoy",
        "venta_forecast": "Presupuesto Venta",
        "compra_cubierta": "Presupuesto Compra",
        "necesidad": "Faltante",
        "resultado": "Resultado",
    }).sort_values("Faltante", ascending=False)

    cols_numericas = ["Existencia hoy", "Presupuesto Venta", "Presupuesto Compra", "Faltante", "Resultado"]
    for col in cols_numericas:
        tabla[col] = pd.to_numeric(tabla[col], errors="coerce").round(0)

    cols_orden = ["cve_prod", "producto", "linea"] + cols_numericas + ["vendedores"]
    tabla = tabla[cols_orden].reset_index(drop=True)

    gb = GridOptionsBuilder.from_dataframe(tabla)
    gb.configure_default_column(editable=False, resizable=True, width=140)
    gb.configure_column("cve_prod", headerName="cve prod", pinned="left", width=110)
    gb.configure_column("producto", headerName="producto", pinned="left", width=220)
    gb.configure_column("linea", headerName="línea", pinned="left", width=130)
    gb.configure_column("vendedores", headerName="vendedor(es)", width=250)
    for col in cols_numericas:
        gb.configure_column(
            col, type=["numericColumn"],
            valueFormatter=_VALUE_FORMATTER_MILES_JS,
            cellStyle=_CELL_STYLE_RESULTADO_JS if col == "Resultado" else None,
        )

    AgGrid(
        tabla,
        gridOptions=gb.build(),
        update_on=[],
        data_return_mode=DataReturnMode.AS_INPUT,
        fit_columns_on_grid_load=False,
        allow_unsafe_jscode=True,
        height=min(56 + len(tabla) * 35, 650),
        key=f"comp_pv_grid_{anio_sel}",
    )
    st.caption(
        "**Resultado** = Existencia hoy + Presupuesto Compra − Presupuesto Venta — negativo "
        "(rojo) significa que falta comprar para cubrir lo presupuestado a vender; positivo "
        "(verde) significa superávit. **Faltante** = lo mismo en positivo (0 si ya está "
        "cubierto)."
    )

    csv = tabla.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ descargar CSV",
        data=csv,
        file_name=f"congruencia_presupuesto_{anio_sel}.csv",
        mime="text/csv",
        key="comp_pv_dl_csv",
    )

    st.divider()
    st.markdown("### 🔍 desglosar una materia prima")
    st.caption(
        "Elige una materia prima para ver de dónde sale su demanda anual: venta directa "
        "capturada (si alguien la vende tal cual) y/o la venta capturada del/los producto(s) "
        "terminado(s) que la usan en su fórmula — cruzada contra la existencia de ese PT — "
        "con el vendedor y las líneas de cliente que la arman."
    )
    opciones_desglose = {
        f"{r['cve_prod']} - {r['producto']}": r["cve_prod"]
        for r in tabla.sort_values("producto").to_dict("records")
    }
    if opciones_desglose:
        col_sel, col_btn = st.columns([3, 1])
        with col_sel:
            label_sel = st.selectbox(
                "producto a desglosar", options=list(opciones_desglose.keys()), key="comp_pv_desglose_sel",
            )
        with col_btn:
            st.write("")
            st.write("")
            desglosar_click = st.button(
                "🔍 desglosar", use_container_width=True, key="comp_pv_desglose_btn",
            )

        desglose_key = f"comp_pv_desglose_{anio_sel}"
        if desglosar_click:
            cve_mp_sel = opciones_desglose[label_sel]
            nombre_sel = label_sel.split(" - ", 1)[1] if " - " in label_sel else label_sel
            with st.spinner("calculando desglose…"):
                desglose = desglosar_necesidad_mp_presupuesto_ctrl(cve_mp_sel, anio_sel)
            st.session_state[desglose_key] = {
                "cve_mp": cve_mp_sel, "nombre": nombre_sel, "data": desglose,
            }

        desglose_guardado = st.session_state.get(desglose_key)
        if desglose_guardado:
            _renderizar_desglose_anual(
                desglose_guardado["data"], desglose_guardado["cve_mp"], desglose_guardado["nombre"],
            )


def _mostrar_vista_mensual(anio_sel: int) -> None:
    hoy = date.today()
    meses_default = [m for m in range(1, 13) if anio_sel > hoy.year or m >= hoy.month]
    meses_sel = st.multiselect(
        "meses", options=list(range(1, 13)), default=meses_default,
        format_func=lambda m: _MESES[m].upper(), key="comp_pv_meses",
    )
    meses_sel = sorted(meses_sel)
    if not meses_sel:
        st.info("elige al menos un mes")
        return

    with st.spinner("calculando congruencia de presupuesto por mes…"):
        df = calcular_congruencia_presupuesto_mensual_ctrl(anio=anio_sel, meses=meses_sel)

    if df is None or df.empty:
        st.warning(f"no hay Presupuesto de Ventas capturado para el año {anio_sel} en esos meses.")
        return

    df = df.copy()
    mapa_linea = _catalogo_linea()
    df["linea"] = df["cve_prod"].astype(str).str.strip().map(mapa_linea).fillna("")

    df_f, _ = _filtros_comunes(df, "comp_pvm")
    if df_f.empty:
        st.info("sin resultados para los filtros seleccionados")
        return

    necesidad_total = float(df_f["necesidad"].sum())
    c1, c2 = st.columns(2)
    c1.metric("materias primas analizadas", df_f["cve_prod"].nunique())
    c2.metric("faltante total del período (kg)", f"{necesidad_total:,.0f}")

    tabla = _construir_tabla_mensual_pv(df_f, meses_sel).sort_values("Faltante total", ascending=False)

    cols_orden = ["cve_prod", "producto", "linea"]
    cols_numericas = ["Faltante total"]
    cols_resultado = set()
    for mes in meses_sel:
        mn = _MESES[mes].upper()
        for etiqueta, _campo in _SUFIJOS_MES_PV:
            col = f"{mn} {etiqueta}"
            cols_orden.append(col)
            cols_numericas.append(col)
            if etiqueta == "Resultado":
                cols_resultado.add(col)
    cols_orden += ["Faltante total", "vendedores"]

    for col in cols_numericas:
        tabla[col] = pd.to_numeric(tabla[col], errors="coerce").round(0)
    tabla = tabla[cols_orden].reset_index(drop=True)

    gb = GridOptionsBuilder.from_dataframe(tabla)
    gb.configure_default_column(editable=False, resizable=True, width=120)
    gb.configure_column("cve_prod", headerName="cve prod", pinned="left", width=110)
    gb.configure_column("producto", headerName="producto", pinned="left", width=200)
    gb.configure_column("linea", headerName="línea", pinned="left", width=120)
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
        key=f"comp_pvm_grid_{anio_sel}",
    )
    st.caption(
        "🔒 cve prod, producto y línea quedan fijos al hacer scroll — **Resultado** = "
        "Existencia + Presupuesto Compra − Presupuesto Venta de ese mes (se arrastra como "
        "déficit/superávit al mes siguiente, sin topar en 0) — negativo en rojo, positivo en "
        "verde. **Faltante** es lo mismo en positivo (0 si ya está cubierto ese mes)."
    )

    csv = tabla.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ descargar CSV",
        data=csv,
        file_name=f"congruencia_presupuesto_mensual_{anio_sel}.csv",
        mime="text/csv",
        key="comp_pvm_dl_csv",
    )

    st.divider()
    st.markdown("### 🔍 desglosar una materia prima")
    st.caption(
        "Elige una materia prima para ver, mes a mes, de dónde sale su demanda: venta directa "
        "capturada (si alguien la vende tal cual) y/o la venta capturada del producto terminado "
        "que la usa en su fórmula — cruzada contra la existencia de ese PT — con el vendedor y "
        "las líneas de cliente que la arman."
    )
    opciones_desglose = {
        f"{r['cve_prod']} - {r['producto']}": r["cve_prod"]
        for r in tabla.sort_values("producto").to_dict("records")
    }
    if opciones_desglose:
        col_sel, col_btn = st.columns([3, 1])
        with col_sel:
            label_sel = st.selectbox(
                "producto a desglosar", options=list(opciones_desglose.keys()), key="comp_pvm_desglose_sel",
            )
        with col_btn:
            st.write("")
            st.write("")
            desglosar_click = st.button(
                "🔍 desglosar", use_container_width=True, key="comp_pvm_desglose_btn",
            )

        desglose_key = f"comp_pvm_desglose_{anio_sel}"
        if desglosar_click:
            cve_mp_sel = opciones_desglose[label_sel]
            nombre_sel = label_sel.split(" - ", 1)[1] if " - " in label_sel else label_sel
            with st.spinner("calculando desglose…"):
                desglose = desglosar_necesidad_mp_presupuesto_mensual_ctrl(cve_mp_sel, anio_sel, meses_sel)
            st.session_state[desglose_key] = {
                "cve_mp": cve_mp_sel, "nombre": nombre_sel, "data": desglose,
            }

        desglose_guardado = st.session_state.get(desglose_key)
        if desglose_guardado:
            _renderizar_desglose_mensual(
                desglose_guardado["data"], desglose_guardado["cve_mp"], desglose_guardado["nombre"],
            )


def _construir_tabla_mensual_pv(df_f: pd.DataFrame, meses_sel: list[int]) -> pd.DataFrame:
    base = df_f.drop_duplicates("cve_prod").set_index("cve_prod")[["producto", "linea", "vendedores"]]
    faltante_total_por_prod = df_f.groupby("cve_prod")["necesidad"].sum()

    filas = []
    for cve, info in base.iterrows():
        fila = {"cve_prod": cve, "producto": info["producto"], "linea": info["linea"]}
        sub = df_f[df_f["cve_prod"] == cve].set_index("mes")
        for mes in meses_sel:
            mn = _MESES[mes].upper()
            fila_mes = sub.loc[mes] if mes in sub.index else None
            for etiqueta, campo in _SUFIJOS_MES_PV:
                valor = float(fila_mes[campo]) if fila_mes is not None else 0.0
                fila[f"{mn} {etiqueta}"] = valor
        fila["Faltante total"] = float(faltante_total_por_prod.get(cve, 0.0))
        fila["vendedores"] = info["vendedores"]
        filas.append(fila)

    return pd.DataFrame(filas)


def _renderizar_desglose_anual(desglose: dict, cve_mp: str, nombre_producto: str) -> None:
    st.markdown(f"#### 🔍 {cve_mp} — {nombre_producto}")
    directo = desglose.get("directo", [])
    formula = desglose.get("formula", [])

    if not directo and not formula:
        st.caption("sin demanda capturada para esta materia prima.")
        return

    if directo:
        st.markdown("**venta directa de esta materia prima** (alguien la vende tal cual)")
        st.dataframe(
            pd.DataFrame([{"vendedor": f["vendedor"], "kg (año)": f["valor"]} for f in directo]),
            hide_index=True, use_container_width=True,
        )

    if formula:
        st.markdown(
            "**vía fórmula** — producto(s) terminado(s) que usan esta materia prima como "
            "insumo, cruzado contra su propia venta capturada y su existencia (almacén 18)"
        )
        st.dataframe(
            pd.DataFrame([
                {
                    "PT": f["cve_pt"], "producto": f["producto_pt"], "rol en fórmula": f["rol"],
                    "%": f["pct"], "venta capturada (kg, año)": f["venta_consolidada"],
                    "stock PT hoy (kg)": f["existencia_pt_inicio"],
                    "a producir (kg)": f["a_producir"], "aporte a esta MP (kg)": f["aporte"],
                }
                for f in formula
            ]),
            hide_index=True, use_container_width=True,
        )

        for f in formula:
            if not f["fuentes"]:
                continue
            st.caption(f"**{f['cve_pt']} ({f['producto_pt']})** — de dónde sale esa venta:")
            for fu in f["fuentes"]:
                st.caption(f"- {fu['vendedor']} · {fu['valor']:,.2f} kg (año)")
                if fu.get("lineas"):
                    st.dataframe(
                        pd.DataFrame(fu["lineas"]).rename(columns={
                            "cliente": "cliente", "cve_clie": "cve cliente", "cantidad_kg": "kg",
                        }),
                        hide_index=True, use_container_width=True,
                    )


def _renderizar_desglose_mensual(desglose: dict, cve_mp: str, nombre_producto: str) -> None:
    st.markdown(f"#### 🔍 {cve_mp} — {nombre_producto}")
    meses = desglose.get("meses", [])
    if not meses:
        st.info("sin meses para desglosar")
        return

    for mes in meses:
        directo = desglose["directo"].get(mes, [])
        formula = desglose["formula"].get(mes, [])
        total_directo = sum(f["valor"] for f in directo)
        total_formula = sum(f["aporte"] for f in formula)
        total_mes = total_directo + total_formula

        with st.expander(
            f"{_MESES[mes].upper()} — Presupuesto total: {total_mes:,.2f} kg",
            expanded=(mes == meses[0]),
        ):
            if not directo and not formula:
                st.caption("sin demanda este mes.")
                continue

            if directo:
                st.markdown("**venta directa capturada de este producto**")
                st.dataframe(
                    pd.DataFrame([{"vendedor": f["vendedor"], "kg": f["valor"]} for f in directo]),
                    hide_index=True, use_container_width=True,
                )

            if formula:
                st.markdown(
                    "**vía fórmula** — producto terminado que usa esta materia prima como "
                    "insumo, cruzado contra su propia venta capturada y su existencia "
                    "(almacén 18)"
                )
                st.dataframe(
                    pd.DataFrame([
                        {
                            "PT": f["cve_pt"], "producto": f["producto_pt"], "rol en fórmula": f["rol"],
                            "%": f["pct"], "venta capturada (kg)": f["venta_consolidada"],
                            "stock PT inicio mes (kg)": f["existencia_pt_inicio"],
                            "a producir (kg)": f["a_producir"], "aporte a esta MP (kg)": f["aporte"],
                        }
                        for f in formula
                    ]),
                    hide_index=True, use_container_width=True,
                )

                for f in formula:
                    if not f["fuentes"]:
                        continue
                    st.caption(f"**{f['cve_pt']} ({f['producto_pt']})** — de dónde sale esa venta:")
                    for fu in f["fuentes"]:
                        st.caption(f"- {fu['vendedor']} · {fu['valor']:,.2f} kg")
                        if fu.get("lineas"):
                            st.dataframe(
                                pd.DataFrame(fu["lineas"]).rename(columns={
                                    "cliente": "cliente", "cve_clie": "cve cliente", "cantidad_kg": "kg",
                                }),
                                hide_index=True, use_container_width=True,
                            )
