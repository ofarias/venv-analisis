from __future__ import annotations

import pandas as pd
import streamlit as st

from controllers.forecast_controller import (
    obtener_alertas_ctrl,
    obtener_forecast_detalle_ctrl,
    _ventas_historicas_sae,
    _existencias_sae,
)


_MESES = {1:"ene",2:"feb",3:"mar",4:"abr",5:"may",6:"jun",
          7:"jul",8:"ago",9:"sep",10:"oct",11:"nov",12:"dic"}

_ROL_DASHBOARD = {"SuperAdmin", "Ventas", "Forecast"}


def _tiene_acceso() -> bool:
    roles = set(st.session_state.get("usuario", {}).get("roles", []))
    return bool(roles & _ROL_DASHBOARD)


def mostrar_tab_dashboard(id_version: int, anio: int) -> None:
    if not _tiene_acceso():
        st.warning("🔒 acceso restringido — requiere rol Ventas o Forecast")
        return

    # ── datos base ────────────────────────────────────────────────────────────
    df_fc_kg  = obtener_forecast_detalle_ctrl(id_version=id_version, seccion="KG")
    df_fc_usd = obtener_forecast_detalle_ctrl(id_version=id_version, seccion="USD")
    df_alertas = obtener_alertas_ctrl(id_version=id_version)

    if (df_fc_kg is None or df_fc_kg.empty) and (df_fc_usd is None or df_fc_usd.empty):
        st.info("sin datos de forecast — genera la propuesta en el tab de construcción")
        return

    # convertir columnas numéricas (MySQL devuelve Decimal)
    for _df in (df_fc_kg, df_fc_usd):
        if _df is not None and not _df.empty:
            for _c in ("forecast", "presupuesto_valor", "venta_real_mes_ant", "venta_real_prom_3m"):
                if _c in _df.columns:
                    _df[_c] = pd.to_numeric(_df[_c], errors="coerce").fillna(0.0)

    # ── KPIs ──────────────────────────────────────────────────────────────────
    fc_kg_total  = float(df_fc_kg["forecast"].sum()) if df_fc_kg is not None and not df_fc_kg.empty else 0.0
    fc_usd_total = float(df_fc_usd["forecast"].sum()) if df_fc_usd is not None and not df_fc_usd.empty else 0.0
    pres_kg      = float(df_fc_kg["presupuesto_valor"].sum()) if df_fc_kg is not None and not df_fc_kg.empty else 0.0
    pres_usd     = float(df_fc_usd["presupuesto_valor"].sum()) if df_fc_usd is not None and not df_fc_usd.empty else 0.0
    alertas_crit = int((df_alertas["severidad"] == "critical").sum()) if df_alertas is not None and not df_alertas.empty else 0

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Forecast KG (total)", f"{fc_kg_total:,.0f}",
              delta=f"{fc_kg_total - pres_kg:+,.0f} vs presupuesto" if pres_kg else None)
    c2.metric("Presupuesto KG", f"{pres_kg:,.0f}")
    c3.metric("Forecast USD (total)", f"${fc_usd_total:,.0f}",
              delta=f"{fc_usd_total - pres_usd:+,.0f} vs presupuesto" if pres_usd else None)
    c4.metric("Presupuesto USD", f"${pres_usd:,.0f}")
    c5.metric("Alertas críticas", alertas_crit,
              delta="⚠️" if alertas_crit > 0 else "✅",
              delta_color="inverse" if alertas_crit > 0 else "normal")

    st.divider()

    # ── gráfica mensual forecast vs presupuesto ───────────────────────────────
    col_g1, col_g2 = st.columns(2)

    with col_g1:
        st.markdown("**KG — Forecast vs Presupuesto por mes**")
        if df_fc_kg is not None and not df_fc_kg.empty:
            df_fc_kg["mes"] = pd.to_numeric(df_fc_kg["mes"], errors="coerce").astype(int)
            agg = df_fc_kg.groupby("mes", as_index=False).agg(
                forecast=("forecast", "sum"),
                presupuesto=("presupuesto_valor", "sum"),
            )
            agg["mes_nombre"] = agg["mes"].map(_MESES).str.upper()
            agg = agg.sort_values("mes")
            st.bar_chart(
                agg.set_index("mes_nombre")[["forecast", "presupuesto"]],
                use_container_width=True,
                height=280,
            )

    with col_g2:
        st.markdown("**USD — Forecast vs Presupuesto por mes**")
        if df_fc_usd is not None and not df_fc_usd.empty:
            df_fc_usd["mes"] = pd.to_numeric(df_fc_usd["mes"], errors="coerce").astype(int)
            agg_u = df_fc_usd.groupby("mes", as_index=False).agg(
                forecast=("forecast", "sum"),
                presupuesto=("presupuesto_valor", "sum"),
            )
            agg_u["mes_nombre"] = agg_u["mes"].map(_MESES).str.upper()
            agg_u = agg_u.sort_values("mes")
            st.bar_chart(
                agg_u.set_index("mes_nombre")[["forecast", "presupuesto"]],
                use_container_width=True,
                height=280,
            )

    st.divider()

    # ── top productos desviación ──────────────────────────────────────────────
    if df_fc_kg is not None and not df_fc_kg.empty and "presupuesto_valor" in df_fc_kg.columns:
        st.markdown("**Top 10 productos — desviación forecast vs presupuesto (KG)**")
        top = df_fc_kg.groupby("cve_prod", as_index=False).agg(
            forecast=("forecast", "sum"),
            presupuesto=("presupuesto_valor", "sum"),
            producto=("producto_excel", "first"),
        )
        top["forecast"]    = pd.to_numeric(top["forecast"],    errors="coerce").fillna(0.0)
        top["presupuesto"] = pd.to_numeric(top["presupuesto"], errors="coerce").fillna(0.0)
        top["desviacion"] = top["forecast"] - top["presupuesto"]
        top["pct"] = (top["desviacion"] / top["presupuesto"].replace(0, 1) * 100).round(1)
        top10 = top.nlargest(10, "desviacion")
        st.dataframe(
            top10[["cve_prod", "producto", "presupuesto", "forecast", "desviacion", "pct"]].rename(columns={
                "cve_prod": "cve prod", "presupuesto": "presupuesto kg",
                "forecast": "forecast kg", "desviacion": "desviación", "pct": "% desv.",
            }),
            use_container_width=True,
            hide_index=True,
            column_config={
                "presupuesto kg": st.column_config.NumberColumn(format="%.2f"),
                "forecast kg": st.column_config.NumberColumn(format="%.2f"),
                "desviación": st.column_config.NumberColumn(format="%.2f"),
                "% desv.": st.column_config.NumberColumn(format="%.1f%%"),
            },
        )

    st.divider()

    # ── alertas activas ───────────────────────────────────────────────────────
    if df_alertas is not None and not df_alertas.empty:
        st.markdown("**Alertas activas**")
        _SEV_ICON = {"critical": "🔴", "warning": "🟡", "info": "🔵"}
        df_alertas["🚦"] = df_alertas["severidad"].map(_SEV_ICON)
        df_alertas["mes_nombre"] = pd.to_numeric(df_alertas["mes"], errors="coerce").map(_MESES).str.upper()
        cols_a = ["🚦", "tipo", "cve_prod", "mes_nombre", "mensaje"]
        cols_a = [c for c in cols_a if c in df_alertas.columns]
        st.dataframe(
            df_alertas[cols_a].rename(columns={"mes_nombre": "mes"}),
            use_container_width=True,
            hide_index=True,
            height=min(56 + len(df_alertas) * 35, 350),
        )
    else:
        st.success("✅ sin alertas activas para esta versión")
