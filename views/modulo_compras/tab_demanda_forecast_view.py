from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from controllers.forecast_controller import obtener_forecast_versiones_ctrl
from controllers.forecast_autorizacion_controller import calcular_necesidad_compra_consolidada_ctrl


_MESES = {1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
          7: "jul", 8: "ago", 9: "sep", 10: "oct", 11: "nov", 12: "dic"}

_ORIGEN_BADGE = {
    "autorizado": "✅ autorizado",
    "presupuesto (fallback)": "🟡 presupuesto (pendiente de autorizar)",
}


def mostrar_tab_demanda_forecast() -> None:
    st.caption(
        "Necesidad de compra consolidada de **todos los vendedores** — suma, producto por "
        "producto, el forecast de venta/compra ya autorizado de cada vendedor para el mes "
        "(o su presupuesto de compras/ventas ya autorizado si todavía no autoriza ese mes) "
        "contra la existencia actual, para dimensionar la compra real sin depender de que "
        "un solo vendedor esté al día."
    )

    df_versiones = obtener_forecast_versiones_ctrl(usuario_id=0, ver_todas=True)
    anios_disponibles = sorted(
        {int(a) for a in df_versiones["anio"].dropna().unique()} if df_versiones is not None and not df_versiones.empty else set(),
        reverse=True,
    )
    if not anios_disponibles:
        anios_disponibles = [date.today().year]

    col_anio, col_meses = st.columns([1, 3])
    with col_anio:
        anio_sel = st.selectbox("año", anios_disponibles, key="comp_fc_anio")
    with col_meses:
        meses_sel = st.multiselect(
            "meses", options=list(range(1, 13)), default=list(range(1, 13)),
            format_func=lambda m: _MESES[m].upper(), key="comp_fc_meses",
        )

    hoy = date.today()
    if anio_sel == hoy.year:
        meses_sel = [m for m in meses_sel if m >= hoy.month]
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

    col_cve, col_prod, col_origen = st.columns(3)
    with col_cve:
        cve_sel = st.multiselect(
            "cve prod", options=sorted(df["cve_prod"].unique()), default=[], key="comp_fc_cve",
        )
    with col_prod:
        prod_sel = st.multiselect(
            "producto", options=sorted(df["producto"].unique()), default=[], key="comp_fc_prod",
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
    if origen_sel:
        df_f = df_f[df_f["origen_forecast"].isin(origen_sel)]

    if df_f.empty:
        st.info("sin resultados para los filtros seleccionados")
        return

    total_necesidad = float(df_f["necesidad"].sum())
    pendientes = int((df_f["origen_forecast"] == "presupuesto (fallback)").sum())
    c1, c2, c3 = st.columns(3)
    c1.metric("productos", df_f["cve_prod"].nunique())
    c2.metric("necesidad total (kg)", f"{total_necesidad:,.2f}")
    c3.metric("productos con algún mes sin autorizar", pendientes)

    st.divider()
    resumen = df_f.sort_values("necesidad", ascending=False).copy()
    resumen["origen"] = resumen["origen_forecast"].map(_ORIGEN_BADGE).fillna(resumen["origen_forecast"])
    st.dataframe(
        resumen[[
            "cve_prod", "producto", "existencia_actual", "forecast_mes_actual",
            "presupuesto_compra_dp", "necesidad", "origen", "vendedores",
        ]],
        use_container_width=True,
        hide_index=True,
        column_config={
            "cve_prod": st.column_config.TextColumn("cve prod", disabled=True),
            "producto": st.column_config.TextColumn("producto", disabled=True),
            "existencia_actual": st.column_config.NumberColumn("existencia actual (kg)", format="%.2f", disabled=True),
            "forecast_mes_actual": st.column_config.NumberColumn("forecast mes actual (kg)", format="%.2f", disabled=True),
            "presupuesto_compra_dp": st.column_config.NumberColumn("compra cubierta (kg)", format="%.2f", disabled=True),
            "necesidad": st.column_config.NumberColumn("necesidad (kg)", format="%.2f", disabled=True),
            "origen": st.column_config.TextColumn("origen del forecast", disabled=True),
            "vendedores": st.column_config.TextColumn("vendedor(es)", disabled=True),
        },
        height=min(56 + len(resumen) * 35, 650),
    )

    csv = resumen.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ descargar CSV",
        data=csv,
        file_name=f"demanda_forecast_consolidada_{anio_sel}.csv",
        mime="text/csv",
        key="comp_fc_dl_csv",
    )
