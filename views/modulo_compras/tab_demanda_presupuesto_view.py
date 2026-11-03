from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, DataReturnMode, GridOptionsBuilder, JsCode

from controllers.forecast_controller import _catalogo_productos_sae
from controllers.forecast_autorizacion_controller import (
    calcular_congruencia_presupuesto_anual_ctrl,
    desglosar_necesidad_mp_presupuesto_ctrl,
)

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
        "Congruencia ANUAL (sin desglose por mes) entre lo que se presupuesta **vender**, lo "
        "que se presupuesta **comprar** y la **existencia real de hoy** — tomado DIRECTO del "
        "Presupuesto de Ventas y Presupuesto de Compras capturados (todos los vendedores/"
        "usuarios, sin filtrar por autorización — a diferencia de 'Demanda (Forecast)', aquí "
        "no interviene ninguna versión de Forecast). Los productos terminados (con fórmula "
        "registrada) se cruzan contra su fórmula y su existencia de PT (almacén 18) para "
        "traducir su venta en materia prima requerida; esta tabla solo muestra materia prima "
        "(cve_prod que inicia con \"B\")."
    )

    hoy = date.today()
    anio_sel = st.number_input(
        "año", min_value=2016, max_value=hoy.year + 2, value=hoy.year,
        step=1, key="comp_pv_anio",
    )
    anio_sel = int(anio_sel)

    with st.spinner("calculando congruencia de presupuesto…"):
        df = calcular_congruencia_presupuesto_anual_ctrl(anio=anio_sel)

    if df is None or df.empty:
        st.warning(f"no hay Presupuesto de Ventas capturado para el año {anio_sel}.")
        return

    try:
        df_cat = _catalogo_productos_sae()
    except Exception:
        df_cat = pd.DataFrame()
    mapa_linea: dict = {}
    if df_cat is not None and not df_cat.empty and "cve_art" in df_cat.columns and "linea" in df_cat.columns:
        cve_cat = df_cat["cve_art"].astype(str).str.strip()
        mapa_linea = dict(zip(cve_cat, df_cat["linea"].astype(str).str.strip()))
    df = df.copy()
    df["linea"] = df["cve_prod"].astype(str).str.strip().map(mapa_linea).fillna("")

    vendedores_por_prod: dict[str, set] = {
        str(r["cve_prod"]).strip(): {v.strip() for v in str(r.get("vendedores") or "").split(",") if v.strip()}
        for r in df.to_dict("records")
    }

    col_cve, col_prod, col_linea = st.columns(3)
    with col_cve:
        cve_sel = st.multiselect(
            "cve prod", options=sorted(df["cve_prod"].unique()), default=[], key="comp_pv_cve",
        )
    with col_prod:
        prod_sel = st.multiselect(
            "producto", options=sorted(df["producto"].unique()), default=[], key="comp_pv_prod",
        )
    with col_linea:
        lineas_disponibles = sorted({l for l in df["linea"].unique() if l})
        linea_sel = st.multiselect(
            "unidad de negocio (línea)", options=lineas_disponibles, default=[], key="comp_pv_linea",
        )

    vendedores_disponibles = sorted({v for vs in vendedores_por_prod.values() for v in vs})
    vendedor_sel = st.multiselect(
        "vendedor", options=vendedores_disponibles, default=[], key="comp_pv_vendedor",
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
