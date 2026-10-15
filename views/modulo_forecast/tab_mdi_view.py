from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from controllers.forecast_controller import (
    calcular_mdi_ctrl,
    recalcular_alertas_ctrl,
    _existencias_sae,
    _catalogo_productos_sae,
    clientes_por_producto_ctrl,
    obtener_forecast_detalle_ctrl,
    obtener_presupuesto_resumen_por_anio_ctrl,
)


_MESES = {1:"ene",2:"feb",3:"mar",4:"abr",5:"may",6:"jun",
          7:"jul",8:"ago",9:"sep",10:"oct",11:"nov",12:"dic"}

_COLOR_SEM = {"🟢": "#d4edda", "🟡": "#fff3cd", "🔴": "#f8d7da", "🔵": "#cce5ff"}


def _semaforo_style(val: str) -> str:
    return f"background-color: {_COLOR_SEM.get(str(val), '')}"


def _venta_mes(
    cve_prod: str, mes: int, df_forecast_venta: pd.DataFrame, df_pv_resumen: pd.DataFrame,
) -> tuple[float, str]:
    """Venta pronóstico de un producto en un mes: forecast capturado en
    Construcción si ya existe una fila para ese producto/mes; si no, el
    presupuesto de ventas autorizado (agrupado por producto) de ese mes."""
    if df_forecast_venta is not None and not df_forecast_venta.empty:
        mask = (
            (df_forecast_venta["cve_prod"].astype(str).str.strip() == str(cve_prod).strip())
            & (df_forecast_venta["mes"] == mes)
        )
        if mask.any():
            return float(df_forecast_venta.loc[mask, "forecast"].sum()), "forecast"
    if df_pv_resumen is not None and not df_pv_resumen.empty and "cve_prod" in df_pv_resumen.columns:
        mask = (
            (df_pv_resumen["cve_prod"].astype(str).str.strip() == str(cve_prod).strip())
            & (df_pv_resumen["mes"] == mes)
        )
        if mask.any():
            return float(df_pv_resumen.loc[mask, "total_kg"].sum()), "presupuesto ventas"
    return 0.0, "sin dato"


def _mostrar_clientes_producto(
    cve_prod: str, producto: str, df_clientes: pd.DataFrame,
    meses: list[int], df_forecast_venta: pd.DataFrame, df_pv_resumen: pd.DataFrame,
) -> None:
    filtrado = (
        df_clientes[df_clientes["cve_prod"] == str(cve_prod).strip()]
        if df_clientes is not None and not df_clientes.empty
        else pd.DataFrame()
    )
    with st.container(border=True):
        st.markdown(f"**📋 Clientes que requieren `{cve_prod}` — {producto}**")
        if filtrado.empty:
            st.caption(
                "sin datos de cliente para este producto (forecast capturado manualmente "
                "o sin línea de presupuesto de ventas autorizada asociada)"
            )
        else:
            for _, fila in filtrado.sort_values("kg", ascending=False).iterrows():
                nombre = fila["cliente_excel"] or fila["cve_clie"] or "cliente sin nombre"
                st.markdown(f"- {nombre} — {fila['kg']:,.0f} kg (${fila['usd']:,.0f})")

        st.markdown("**📈 Venta pronóstico por mes**")
        for mes in meses:
            valor, origen = _venta_mes(cve_prod, mes, df_forecast_venta, df_pv_resumen)
            st.markdown(f"- {_MESES[mes].upper()}: {valor:,.0f} kg ({origen})")


def mostrar_tab_mdi(
    id_version: int, anio: int, meses: list[int], usuario_datos_id: int | None = None,
) -> None:
    if not meses:
        st.warning("selecciona meses en el tab de construcción")
        return

    # el MDI es "¿qué pasa de aquí en adelante?" — los meses ya pasados no
    # aportan y solo abultan la tabla, así que aunque el selector global
    # (compartido con Real vs Forecast / Necesidades de Compra) tenga más
    # meses marcados, aquí se recorta al mes actual en adelante.
    hoy = date.today()
    if anio == hoy.year:
        meses = [m for m in meses if m >= hoy.month]

    if not meses:
        st.info("no hay meses vigentes (mes actual en adelante) entre los meses seleccionados")
        return

    col_act, col_alerta = st.columns([3, 1])
    with col_act:
        st.caption(
            "**Mapa de Inventario** — stock proyectado mes a mes por producto. "
            "🟢 ≥ 30 días cobertura   🟡 15-29 días   🔴 < 15 días   🔵 sin stock y sin presupuesto"
        )
    with col_alerta:
        if st.button("🔄 recalcular alertas", use_container_width=True, key="mdi_btn_alertas"):
            with st.spinner("recalculando…"):
                n = recalcular_alertas_ctrl(id_version=id_version, anio=anio, meses=meses)
            st.success(f"{n} alertas generadas")
            st.rerun()

    # ── datos (cacheados — el spinner, si aplica, lo pone el propio cache_data) ─
    df_mdi = calcular_mdi_ctrl(id_version=id_version, anio=anio, meses=meses)
    if df_mdi is not None and not df_mdi.empty:
        for _c in df_mdi.columns:
            if any(x in _c for x in ("stock", "venta_", "compra_", "resultado_", "dias_")):
                df_mdi[_c] = pd.to_numeric(df_mdi[_c], errors="coerce").fillna(0.0)

    if df_mdi is None or df_mdi.empty:
        st.info("sin datos de forecast KG para este período — genera la propuesta primero")
        return

    # ── filtros: cve prod / producto / unidad de negocio (línea) ───────────────
    df_cat = _catalogo_productos_sae()
    mapa_linea: dict = {}
    if df_cat is not None and not df_cat.empty and "cve_art" in df_cat.columns and "linea" in df_cat.columns:
        mapa_linea = dict(zip(
            df_cat["cve_art"].astype(str).str.strip(),
            df_cat["linea"].astype(str).str.strip(),
        ))
    df_mdi["linea"] = df_mdi["cve_prod"].astype(str).str.strip().map(mapa_linea).fillna("")

    cves_disponibles = sorted(df_mdi["cve_prod"].dropna().astype(str).str.strip().unique())
    productos_disponibles = sorted(df_mdi["producto"].dropna().astype(str).str.strip().unique())
    lineas_disponibles = sorted(l for l in df_mdi["linea"].unique() if l)

    col_cve, col_prod, col_linea = st.columns(3)
    with col_cve:
        cve_sel = st.multiselect("cve prod", options=cves_disponibles, default=[], key="mdi_cve_prod")
    with col_prod:
        prod_sel = st.multiselect("producto", options=productos_disponibles, default=[], key="mdi_producto")
    with col_linea:
        linea_sel = st.multiselect(
            "unidad de negocio (línea)", options=lineas_disponibles, default=[], key="mdi_linea",
        )

    if cve_sel:
        df_mdi = df_mdi[df_mdi["cve_prod"].astype(str).str.strip().isin(cve_sel)]
    if prod_sel:
        df_mdi = df_mdi[df_mdi["producto"].astype(str).str.strip().isin(prod_sel)]
    if linea_sel:
        df_mdi = df_mdi[df_mdi["linea"].astype(str).str.strip().isin(linea_sel)]

    if df_mdi.empty:
        st.info("sin resultados para los filtros seleccionados")
        return

    df_clientes = clientes_por_producto_ctrl(anio, meses=tuple(meses))
    df_forecast_venta = obtener_forecast_detalle_ctrl(id_version=id_version, seccion="KG", tipo="venta")
    df_pv_resumen = obtener_presupuesto_resumen_por_anio_ctrl(
        anio=anio, seccion="KG", region=None, usuario_id=usuario_datos_id, solo_autorizados=True,
    )

    # ── vista resumen: tabla de semáforos ─────────────────────────────────────
    st.markdown("##### Semáforo de cobertura por mes")
    sem_cols = ["cve_prod", "producto", "stock_actual"]
    for m in meses:
        col = f"sem_{m:02d}"
        if col in df_mdi.columns:
            sem_cols.append(col)

    df_sem = df_mdi[[c for c in sem_cols if c in df_mdi.columns]].copy()
    df_sem = df_sem.rename(columns={
        "cve_prod": "cve prod", "producto": "producto", "stock_actual": "stock hoy (kg)",
        **{f"sem_{m:02d}": _MESES[m].upper() for m in meses if f"sem_{m:02d}" in df_mdi.columns}
    })

    sel_sem = st.dataframe(
        df_sem, use_container_width=True, hide_index=True, height=min(56 + len(df_sem) * 35, 500),
        on_select="rerun", selection_mode="single-row", key="mdi_tabla_semaforo",
    )
    filas_sem = sel_sem.selection.get("rows", [])
    if filas_sem:
        fila_sem = df_sem.iloc[filas_sem[0]]
        _mostrar_clientes_producto(
            fila_sem["cve prod"], fila_sem["producto"], df_clientes,
            meses, df_forecast_venta, df_pv_resumen,
        )
    else:
        st.caption("👆 haz clic en una fila para ver qué clientes requieren ese producto")

    st.divider()

    # ── detalle por mes: stock → venta → compra → resultado (acumulativo) ──────
    st.markdown("##### Detalle de stock proyectado (KG)")
    st.caption(
        "no considera órdenes de producción — cada mes resta la proyección de venta y "
        "suma la proyección de compra (DP) al stock de inicio; el resultado se arrastra "
        "como stock de inicio del mes siguiente hasta terminar el año."
    )

    # construir tabla wide: cve_prod | producto | stock_actual | ene stock | ene venta | ene compra | ene resultado | ...
    cols_det = ["cve_prod", "producto", "stock_actual"]
    rename_det: dict = {"cve_prod": "cve prod", "producto": "producto", "stock_actual": "stock hoy"}
    for m in meses:
        mn = _MESES[m].upper()
        for c, lbl in [
            (f"stock_ini_{m:02d}", f"{mn} Stock"),
            (f"venta_{m:02d}", f"{mn} Proyección Venta"),
            (f"compra_{m:02d}", f"{mn} Proyección Compra"),
            (f"resultado_{m:02d}", f"{mn} Resultado"),
        ]:
            if c in df_mdi.columns:
                cols_det.append(c)
                rename_det[c] = lbl

    df_det = df_mdi[[c for c in cols_det if c in df_mdi.columns]].rename(columns=rename_det)

    # colorear la columna "Resultado" de cada mes según su semáforo
    def _style_stock(df_styled):
        for m in meses:
            res_col = f"{_MESES[m].upper()} Resultado"
            sem_col = f"sem_{m:02d}"
            if res_col not in df_styled.columns or sem_col not in df_mdi.columns:
                continue
            colors = df_mdi[sem_col].map(_COLOR_SEM).fillna("")
            df_styled = df_styled.apply(
                lambda col, c=res_col, clrs=colors: (
                    [f"background-color: {clr}" for clr in clrs] if col.name == c else [""] * len(col)
                ),
                axis=0,
            )
        return df_styled

    cols_numericas = [c for c in df_det.columns if c not in ("cve prod", "producto")]
    styled = df_det.style.pipe(_style_stock).format(
        {c: "{:,.2f}" for c in cols_numericas},
        na_rep="—"
    )
    sel_det = st.dataframe(
        styled, use_container_width=True, hide_index=True, height=min(56 + len(df_det) * 35, 600),
        on_select="rerun", selection_mode="single-row", key="mdi_tabla_detalle",
    )
    filas_det = sel_det.selection.get("rows", [])
    if filas_det:
        fila_det = df_det.iloc[filas_det[0]]
        _mostrar_clientes_producto(
            fila_det["cve prod"], fila_det["producto"], df_clientes,
            meses, df_forecast_venta, df_pv_resumen,
        )
    else:
        st.caption("👆 haz clic en una fila para ver qué clientes requieren ese producto")

    st.divider()

    # ── existencias actuales detalle ──────────────────────────────────────────
    with st.expander("📦 existencias actuales SAE (productos en forecast)"):
        try:
            df_exist = _existencias_sae()
            if df_exist is not None and not df_exist.empty:
                prod_en_fc = set(df_mdi["cve_prod"].astype(str).str.strip().tolist())
                mask = df_exist["cve_art"].astype(str).str.strip().isin(prod_en_fc)
                df_ex_f = df_exist[mask][["cve_art", "descr", "existencia", "uni_med"]].copy()
                df_ex_f = df_ex_f.sort_values("existencia", ascending=False)
                st.dataframe(df_ex_f.rename(columns={
                    "cve_art": "cve prod", "descr": "descripción",
                    "existencia": "existencia (kg)", "uni_med": "unidad",
                }), use_container_width=True, hide_index=True)
            else:
                st.info("no se pudieron cargar existencias SAE")
        except Exception as e:
            st.warning(f"error cargando existencias: {e}")
