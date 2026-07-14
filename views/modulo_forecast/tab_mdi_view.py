from __future__ import annotations

import pandas as pd
import streamlit as st

from controllers.forecast_controller import (
    calcular_mdi_ctrl,
    recalcular_alertas_ctrl,
    _existencias_sae,
)


_MESES = {1:"ene",2:"feb",3:"mar",4:"abr",5:"may",6:"jun",
          7:"jul",8:"ago",9:"sep",10:"oct",11:"nov",12:"dic"}

_COLOR_SEM = {"🟢": "#d4edda", "🟡": "#fff3cd", "🔴": "#f8d7da", "🔵": "#cce5ff"}


def _semaforo_style(val: str) -> str:
    return f"background-color: {_COLOR_SEM.get(str(val), '')}"


def mostrar_tab_mdi(id_version: int, anio: int, meses: list[int]) -> None:
    if not meses:
        st.warning("selecciona meses en el tab de construcción")
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

    # ── datos ─────────────────────────────────────────────────────────────────
    with st.spinner("calculando MDI…"):
        df_mdi = calcular_mdi_ctrl(id_version=id_version, anio=anio, meses=meses)
    if df_mdi is not None and not df_mdi.empty:
        for _c in df_mdi.columns:
            if any(x in _c for x in ("stock", "fc_", "dias_")):
                df_mdi[_c] = pd.to_numeric(df_mdi[_c], errors="coerce").fillna(0.0)

    if df_mdi is None or df_mdi.empty:
        st.info("sin datos de forecast KG para este período — genera la propuesta primero")
        return

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

    st.dataframe(df_sem, use_container_width=True, hide_index=True, height=min(56 + len(df_sem) * 35, 500))

    st.divider()

    # ── detalle por mes: stock inicio → salidas → stock fin ────────────────────
    st.markdown("##### Detalle de stock proyectado (KG)")
    st.caption("no considera órdenes de producción — solo el stock actual menos el forecast de salidas")

    # construir tabla wide: cve_prod | producto | stock_actual | ene_fc | ene_stock | ...
    cols_det = ["cve_prod", "producto", "stock_actual"]
    rename_det: dict = {"cve_prod": "cve prod", "producto": "producto", "stock_actual": "stock hoy"}
    for m in meses:
        mn = _MESES[m].upper()
        fc_c = f"fc_{m:02d}"
        stk_c = f"stock_{m:02d}"
        for c, lbl in [(fc_c, f"{mn} forecast"), (stk_c, f"{mn} stock fin")]:
            if c in df_mdi.columns:
                cols_det.append(c)
                rename_det[c] = lbl

    df_det = df_mdi[[c for c in cols_det if c in df_mdi.columns]].rename(columns=rename_det)

    # colorear columnas "stock fin" según semáforo
    def _style_stock(df_styled):
        for m in meses:
            stk_col = f"{_MESES[m].upper()} stock fin"
            sem_col = f"sem_{m:02d}"
            if stk_col not in df_styled.columns or sem_col not in df_mdi.columns:
                continue
            colors = df_mdi[sem_col].map(_COLOR_SEM).fillna("")
            df_styled = df_styled.apply(
                lambda col, c=stk_col, clrs=colors: (
                    [f"background-color: {clr}" for clr in clrs] if col.name == c else [""] * len(col)
                ),
                axis=0,
            )
        return df_styled

    styled = df_det.style.pipe(_style_stock).format(
        {c: "{:,.2f}" for c in df_det.columns if "stock" in c.lower() or "forecast" in c.lower()},
        na_rep="—"
    )
    st.dataframe(styled, use_container_width=True, hide_index=True, height=min(56 + len(df_det) * 35, 600))

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
