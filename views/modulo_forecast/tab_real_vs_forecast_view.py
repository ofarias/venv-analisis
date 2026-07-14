from __future__ import annotations

import pandas as pd
import streamlit as st

from controllers.forecast_controller import (
    obtener_forecast_detalle_ctrl,
    obtener_presupuesto_resumen_por_anio_ctrl,
    obtener_presupuesto_finanzas_resumen_por_anio_ctrl,
    _catalogo_productos_sae,
    _ventas_historicas_sae,
)


_MESES = {1:"ene",2:"feb",3:"mar",4:"abr",5:"may",6:"jun",
          7:"jul",8:"ago",9:"sep",10:"oct",11:"nov",12:"dic"}

_TABS_SEC = [
    ("KG México",        "KG",  "MEXICO"),
    ("USD México",       "USD", "MEXICO"),
    ("CAM & Caribe KG",  "KG",  "CAM & Caribe"),
    ("CAM & Caribe USD", "USD", "CAM & Caribe"),
]


def _col_sae(seccion: str) -> str:
    return "cantidad" if seccion == "KG" else "importe"


def _col_pv(seccion: str) -> str:
    return "total_kg" if seccion == "KG" else "total_importe"


def _construir_comparativo(
    df_sae: pd.DataFrame,
    df_fc: pd.DataFrame,
    df_pv: pd.DataFrame,
    df_pf: pd.DataFrame,
    seccion: str,
    meses: list[int],
) -> pd.DataFrame:
    """
    Retorna pivot wide:
      cve_prod | producto | total_real | total_fc | total_presupuesto | total_pf | cumplimiento_%
      + ene_real | ene_fc | ene_pv | ene_pf | ene_Δ% | feb_real | ...
    """
    col_sae = _col_sae(seccion)
    col_pv = _col_pv(seccion)

    # ── agrupar ventas SAE por cve_art × mes ──────────────────────────────────
    if df_sae is not None and not df_sae.empty and "cve_art" in df_sae.columns:
        df_sae = df_sae.copy()
        df_sae["mes"] = pd.to_numeric(df_sae["mes"], errors="coerce").astype(int)
        df_sae[col_sae] = pd.to_numeric(df_sae[col_sae], errors="coerce").fillna(0.0)
        sae_grp = df_sae.groupby(["cve_art", "mes"], as_index=False).agg(
            real=(col_sae, "sum"),
            producto=("producto", "first"),
        )
        sae_grp = sae_grp[sae_grp["mes"].isin(meses)]
    else:
        sae_grp = pd.DataFrame(columns=["cve_art", "mes", "real", "producto"])

    # ── agrupar forecast por cve_prod × mes ───────────────────────────────────
    if df_fc is not None and not df_fc.empty:
        df_fc = df_fc.copy()
        df_fc["mes"] = pd.to_numeric(df_fc["mes"], errors="coerce").astype(int)
        df_fc["forecast"] = pd.to_numeric(df_fc["forecast"], errors="coerce").fillna(0.0)
        fc_grp = df_fc[df_fc["mes"].isin(meses)].groupby(["cve_prod", "mes"], as_index=False).agg(
            fc=("forecast", "sum"),
            producto_fc=("producto_excel", "first"),
        )
    else:
        fc_grp = pd.DataFrame(columns=["cve_prod", "mes", "fc", "producto_fc"])

    # ── agrupar presupuesto de ventas por cve_prod × mes ──────────────────────
    if df_pv is not None and not df_pv.empty and "cve_prod" in df_pv.columns:
        df_pv = df_pv.copy()
        df_pv["mes"] = pd.to_numeric(df_pv["mes"], errors="coerce").astype(int)
        df_pv[col_pv] = pd.to_numeric(df_pv[col_pv], errors="coerce").fillna(0.0)
        pv_grp = df_pv[df_pv["mes"].isin(meses)].groupby(["cve_prod", "mes"], as_index=False).agg(
            pv=(col_pv, "sum"),
            producto_pv=("producto_excel", "first"),
        )
    else:
        pv_grp = pd.DataFrame(columns=["cve_prod", "mes", "pv", "producto_pv"])

    # ── agrupar presupuesto de finanzas por cve_prod (clave sku) × mes ────────
    if df_pf is not None and not df_pf.empty and "cve_prod" in df_pf.columns:
        df_pf = df_pf.copy()
        df_pf["mes"] = pd.to_numeric(df_pf["mes"], errors="coerce").astype(int)
        df_pf[col_pv] = pd.to_numeric(df_pf[col_pv], errors="coerce").fillna(0.0)
        pf_grp = df_pf[df_pf["mes"].isin(meses)].groupby(["cve_prod", "mes"], as_index=False).agg(
            pf=(col_pv, "sum"),
            producto_pf=("producto_excel", "first"),
        )
    else:
        pf_grp = pd.DataFrame(columns=["cve_prod", "mes", "pf", "producto_pf"])

    # ── unión por cve_prod = cve_art ──────────────────────────────────────────
    sae_grp = sae_grp.rename(columns={"cve_art": "cve_prod"})
    merged = pd.merge(
        fc_grp, sae_grp,
        on=["cve_prod", "mes"],
        how="outer",
    )
    merged = pd.merge(
        merged, pv_grp,
        on=["cve_prod", "mes"],
        how="outer",
    )
    merged = pd.merge(
        merged, pf_grp,
        on=["cve_prod", "mes"],
        how="outer",
    )
    merged = merged.fillna({"real": 0.0, "fc": 0.0, "pv": 0.0, "pf": 0.0})

    # nombre de producto: preferir el de SAE, fallback forecast, presupuesto, pres. finanzas
    merged["producto"] = (
        merged["producto"].fillna(merged["producto_fc"]).fillna(merged["producto_pv"])
        .fillna(merged["producto_pf"]).fillna(merged["cve_prod"])
    )
    merged = merged.drop(columns=["producto_fc", "producto_pv", "producto_pf"], errors="ignore")
    merged["cve_prod"] = merged["cve_prod"].fillna("").astype(str)

    if merged.empty:
        return pd.DataFrame()

    # ── pivot wide ────────────────────────────────────────────────────────────
    filas: list[dict] = []
    for cve_prod in sorted(merged["cve_prod"].unique()):
        sub = merged[merged["cve_prod"] == cve_prod]
        producto = sub["producto"].iloc[0] if not sub.empty else cve_prod
        fila: dict = {"cve_prod": cve_prod, "producto": producto}

        total_real = 0.0
        total_fc   = 0.0
        total_pv   = 0.0
        total_pf   = 0.0
        for mes in meses:
            row = sub[sub["mes"] == mes]
            real = float(row["real"].sum()) if not row.empty else 0.0
            fc   = float(row["fc"].sum())   if not row.empty else 0.0
            pv   = float(row["pv"].sum())   if not row.empty else 0.0
            pf   = float(row["pf"].sum())   if not row.empty else 0.0
            mn = _MESES[mes]
            fila[f"{mn}_real"] = real
            fila[f"{mn}_fc"]   = fc
            fila[f"{mn}_pv"]   = pv
            fila[f"{mn}_pf"]   = pf
            fila[f"{mn}_Δ%"]   = round((real - fc) / fc * 100, 1) if fc != 0 else None
            fila[f"{mn}_Δ%_pv"] = round((real - pv) / pv * 100, 1) if pv != 0 else None
            fila[f"{mn}_Δ%_pf"] = round((real - pf) / pf * 100, 1) if pf != 0 else None
            total_real += real
            total_fc   += fc
            total_pv   += pv
            total_pf   += pf

        fila["total_real"] = round(total_real, 2)
        fila["total_fc"]   = round(total_fc, 2)
        fila["total_presupuesto"] = round(total_pv, 2)
        fila["total_pf"]   = round(total_pf, 2)
        fila["cumplimiento_%"] = round(total_real / total_fc * 100, 1) if total_fc != 0 else None
        fila["cumplimiento_pv_%"] = round(total_real / total_pv * 100, 1) if total_pv != 0 else None
        fila["cumplimiento_pf_%"] = round(total_real / total_pf * 100, 1) if total_pf != 0 else None
        filas.append(fila)

    return pd.DataFrame(filas)


def _style_delta(df: pd.DataFrame, meses: list[int]) -> pd.io.formats.style.Styler:
    """Colorea columnas Δ% y cumplimiento: verde si ≥0, rojo si <0."""
    delta_cols = [f"{_MESES[m]}_Δ%" for m in meses if f"{_MESES[m]}_Δ%" in df.columns]
    delta_cols += [f"{_MESES[m]}_Δ%_pv" for m in meses if f"{_MESES[m]}_Δ%_pv" in df.columns]
    delta_cols += [f"{_MESES[m]}_Δ%_pf" for m in meses if f"{_MESES[m]}_Δ%_pf" in df.columns]
    if "cumplimiento_%" in df.columns:
        delta_cols.append("cumplimiento_%")
    if "cumplimiento_pv_%" in df.columns:
        delta_cols.append("cumplimiento_pv_%")
    if "cumplimiento_pf_%" in df.columns:
        delta_cols.append("cumplimiento_pf_%")

    def _color(val):
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return ""
        return "background-color: #d4edda; color: #155724" if val >= 0 else "background-color: #f8d7da; color: #721c24"

    styler = df.style
    for col in delta_cols:
        styler = styler.applymap(_color, subset=[col])
    return styler


def mostrar_tab_real_vs_forecast(
    id_version: int,
    anio: int,
    meses: list[int],
) -> None:
    if not meses:
        st.warning("selecciona meses en el tab de construcción")
        return

    st.caption(
        f"Comparativo **Ventas Reales SAE vs Forecast vs Presupuesto vs Presupuesto Finanzas** — año {anio}. "
        "Verde = real ≥ plan (forecast, presupuesto o presupuesto finanzas, según la columna). "
        "Rojo = real < plan. "
        "⚠️ Presupuesto Finanzas no distingue región (MEXICO / CAM & Caribe): se muestra el mismo total en ambas."
    )

    # ── catálogo SAE para armar opciones de línea/producto ─────────────────────
    df_cat = _catalogo_productos_sae()
    lineas_disponibles = (
        sorted(df_cat["linea"].dropna().astype(str).str.strip().unique())
        if df_cat is not None and not df_cat.empty and "linea" in df_cat.columns
        else []
    )

    # ── fila de filtros: año / línea / producto ────────────────────────────────
    col_anio, col_linea, col_prod = st.columns(3)

    with col_anio:
        anio_sel = st.number_input(
            "año a comparar", min_value=2020, max_value=2030,
            value=anio, step=1, key="rvf_anio",
        )

    with col_linea:
        linea_sel = st.multiselect(
            "línea", options=lineas_disponibles, default=[], key="rvf_linea",
        )

    with col_prod:
        df_cat_prod = df_cat
        if df_cat_prod is not None and not df_cat_prod.empty and "status" in df_cat_prod.columns:
            df_cat_prod = df_cat_prod[df_cat_prod["status"].astype(str).str.strip().str.upper() == "A"]
        if df_cat_prod is not None and not df_cat_prod.empty and linea_sel and "linea" in df_cat_prod.columns:
            df_cat_prod = df_cat_prod[df_cat_prod["linea"].astype(str).str.strip().isin(linea_sel)]

        productos_opciones: dict[str, str] = {}
        if df_cat_prod is not None and not df_cat_prod.empty:
            for _, fila_cat in df_cat_prod.iterrows():
                cve = str(fila_cat["cve_art"]).strip()
                desc = str(fila_cat.get("descr") or "").strip()
                productos_opciones[f"{cve} - {desc}" if desc else cve] = cve

        producto_labels_sel = st.multiselect(
            "producto", options=sorted(productos_opciones.keys()), default=[], key="rvf_producto",
        )
    productos_sel = {productos_opciones[lbl] for lbl in producto_labels_sel}

    # carga datos SAE (cacheados)
    with st.spinner("cargando ventas SAE…"):
        df_sae = _ventas_historicas_sae(int(anio_sel))

    # filtrar solo el año seleccionado
    if df_sae is not None and not df_sae.empty and "anio" in df_sae.columns:
        df_sae["anio"] = pd.to_numeric(df_sae["anio"], errors="coerce")
        df_sae = df_sae[df_sae["anio"] == int(anio_sel)]

    # ── filtro por línea (INV01.LIN_PROD ligado con clin01/LINEAS.ID) ──────────
    productos_linea: set[str] | None = None
    if linea_sel:
        if df_sae is not None and not df_sae.empty and "linea" in df_sae.columns:
            df_sae = df_sae[df_sae["linea"].astype(str).str.strip().isin(linea_sel)]
        if df_cat is not None and not df_cat.empty:
            productos_linea = set(
                df_cat.loc[
                    df_cat["linea"].astype(str).str.strip().isin(linea_sel), "cve_art"
                ]
                .astype(str)
                .str.strip()
            )

    # ── filtro por tipo de producto (clave inicia con MP o PT) ─────────────────
    tipo_prod_sel = st.radio(
        "tipo de producto",
        options=["Todos", "Materia Prima (MP)", "Producto Terminado (PT)"],
        horizontal=True, key="rvf_tipo_prod",
    )
    prefijo_tipo = {"Materia Prima (MP)": "B", "Producto Terminado (PT)": "PT"}.get(tipo_prod_sel)

    if prefijo_tipo:
        if df_sae is not None and not df_sae.empty and "cve_art" in df_sae.columns:
            df_sae = df_sae[
                df_sae["cve_art"].astype(str).str.strip().str.upper().str.startswith(prefijo_tipo)
            ]

    # ── filtro por producto ─────────────────────────────────────────────────────
    if productos_sel:
        if df_sae is not None and not df_sae.empty and "cve_art" in df_sae.columns:
            df_sae = df_sae[df_sae["cve_art"].astype(str).str.strip().isin(productos_sel)]
        productos_linea = productos_sel if productos_linea is None else (productos_linea & productos_sel)

    # ── presupuesto de finanzas (no distingue región: se calcula una sola vez) ──
    with st.spinner("cargando presupuesto de finanzas…"):
        df_pf_all = obtener_presupuesto_finanzas_resumen_por_anio_ctrl(int(anio_sel))
    if productos_linea is not None and df_pf_all is not None and not df_pf_all.empty:
        df_pf_all = df_pf_all[
            df_pf_all["cve_prod"].astype(str).str.strip().isin(productos_linea)
        ]
    if prefijo_tipo and df_pf_all is not None and not df_pf_all.empty:
        df_pf_all = df_pf_all[
            df_pf_all["cve_prod"].astype(str).str.strip().str.upper().str.startswith(prefijo_tipo)
        ]

    sub_tabs = st.tabs([t[0] for t in _TABS_SEC])

    for tab_ui, (label, seccion, region) in zip(sub_tabs, _TABS_SEC):
        with tab_ui:
            df_fc = obtener_forecast_detalle_ctrl(
                id_version=id_version, seccion=seccion, region=region
            )
            if productos_linea is not None and df_fc is not None and not df_fc.empty:
                df_fc = df_fc[
                    df_fc["cve_prod"].astype(str).str.strip().isin(productos_linea)
                ]
            if prefijo_tipo and df_fc is not None and not df_fc.empty:
                df_fc = df_fc[
                    df_fc["cve_prod"].astype(str).str.strip().str.upper().str.startswith(prefijo_tipo)
                ]

            df_pv = obtener_presupuesto_resumen_por_anio_ctrl(int(anio_sel), seccion, region)
            if productos_linea is not None and df_pv is not None and not df_pv.empty:
                df_pv = df_pv[
                    df_pv["cve_prod"].astype(str).str.strip().isin(productos_linea)
                ]
            if prefijo_tipo and df_pv is not None and not df_pv.empty:
                df_pv = df_pv[
                    df_pv["cve_prod"].astype(str).str.strip().str.upper().str.startswith(prefijo_tipo)
                ]

            if (
                (df_fc is None or df_fc.empty)
                and (df_sae is None or df_sae.empty)
                and (df_pv is None or df_pv.empty)
                and (df_pf_all is None or df_pf_all.empty)
            ):
                st.info(f"sin datos para {label}")
                continue

            df_comp = _construir_comparativo(df_sae, df_fc, df_pv, df_pf_all, seccion, meses)

            if df_comp is None or df_comp.empty:
                st.info(f"sin productos para comparar en {label}")
                continue

            # ── KPIs del total ─────────────────────────────────────────────
            total_real = df_comp["total_real"].sum()
            total_fc   = df_comp["total_fc"].sum()
            total_pv   = df_comp["total_presupuesto"].sum()
            total_pf   = df_comp["total_pf"].sum()
            cumpl_pct     = round(total_real / total_fc * 100, 1) if total_fc else 0.0
            cumpl_pv_pct  = round(total_real / total_pv * 100, 1) if total_pv else 0.0
            cumpl_pf_pct  = round(total_real / total_pf * 100, 1) if total_pf else 0.0
            delta_abs     = total_real - total_fc
            delta_pv_abs  = total_real - total_pv
            delta_pf_abs  = total_real - total_pf
            unidad     = "kg" if seccion == "KG" else "USD"

            c1, c2, c3, c4 = st.columns(4)
            c1.metric(f"Real {unidad}", f"{total_real:,.0f}")
            c2.metric(f"Forecast {unidad}", f"{total_fc:,.0f}")
            c3.metric(f"Presupuesto {unidad}", f"{total_pv:,.0f}")
            c4.metric(f"Presupuesto Finanzas {unidad}", f"{total_pf:,.0f}")

            c5, c6, c7 = st.columns(3)
            c5.metric("Cumplimiento vs FC", f"{cumpl_pct:.1f}%",
                      delta=f"{cumpl_pct - 100:.1f}pp vs plan",
                      delta_color="normal")
            c6.metric("Cumplimiento vs Presup.", f"{cumpl_pv_pct:.1f}%",
                      delta=f"{cumpl_pv_pct - 100:.1f}pp vs plan",
                      delta_color="normal")
            c7.metric("Cumplimiento vs Presup. Finanzas", f"{cumpl_pf_pct:.1f}%",
                      delta=f"{cumpl_pf_pct - 100:.1f}pp vs plan",
                      delta_color="normal")

            c8, c9, c10 = st.columns(3)
            c8.metric("Diferencia vs FC", f"{delta_abs:+,.0f}", delta_color="normal")
            c9.metric("Diferencia vs Presup.", f"{delta_pv_abs:+,.0f}", delta_color="normal")
            c10.metric("Diferencia vs Presup. Finanzas", f"{delta_pf_abs:+,.0f}", delta_color="normal")

            st.divider()

            # ── tabla comparativa ──────────────────────────────────────────
            fmt_valor = "localized"  # sin decimales, con separador de miles

            col_cfg: dict = {
                "cve_prod":       st.column_config.TextColumn("cve prod", disabled=True, width="small"),
                "producto":       st.column_config.TextColumn("producto", disabled=True),
                "total_real":     st.column_config.NumberColumn(f"total real {unidad}", format=fmt_valor, disabled=True),
                "total_fc":       st.column_config.NumberColumn(f"total forecast {unidad}", format=fmt_valor, disabled=True),
                "total_presupuesto": st.column_config.NumberColumn(f"total presupuesto {unidad}", format=fmt_valor, disabled=True),
                "total_pf":          st.column_config.NumberColumn(f"total presup. finanzas {unidad}", format=fmt_valor, disabled=True),
                "cumplimiento_%": st.column_config.NumberColumn("cumplimiento % (vs FC)", format="%.1f", disabled=True),
                "cumplimiento_pv_%": st.column_config.NumberColumn("cumplimiento % (vs Presup.)", format="%.1f", disabled=True),
                "cumplimiento_pf_%": st.column_config.NumberColumn("cumplimiento % (vs Presup. Finanzas)", format="%.1f", disabled=True),
            }
            for mes in meses:
                mn = _MESES[mes]
                col_cfg[f"{mn}_real"] = st.column_config.NumberColumn(f"{mn.upper()} real", format=fmt_valor, disabled=True)
                col_cfg[f"{mn}_fc"]   = st.column_config.NumberColumn(f"{mn.upper()} fc",   format=fmt_valor, disabled=True)
                col_cfg[f"{mn}_pv"]   = st.column_config.NumberColumn(f"{mn.upper()} presup", format=fmt_valor, disabled=True)
                col_cfg[f"{mn}_pf"]   = st.column_config.NumberColumn(f"{mn.upper()} presup. finanzas", format=fmt_valor, disabled=True)
                col_cfg[f"{mn}_Δ%"]   = st.column_config.NumberColumn(f"{mn.upper()} Δ% (vs FC)",   format="%.1f", disabled=True)
                col_cfg[f"{mn}_Δ%_pv"] = st.column_config.NumberColumn(f"{mn.upper()} Δ% (vs Presup.)", format="%.1f", disabled=True)
                col_cfg[f"{mn}_Δ%_pf"] = st.column_config.NumberColumn(f"{mn.upper()} Δ% (vs Presup. Finanzas)", format="%.1f", disabled=True)

            # columnas en orden
            cols_orden = ["cve_prod", "producto", "total_real", "total_fc", "total_presupuesto", "total_pf",
                          "cumplimiento_%", "cumplimiento_pv_%", "cumplimiento_pf_%"]
            for mes in meses:
                mn = _MESES[mes]
                for suf in ("_real", "_fc", "_pv", "_pf", "_Δ%", "_Δ%_pv", "_Δ%_pf"):
                    c = f"{mn}{suf}"
                    if c in df_comp.columns:
                        cols_orden.append(c)
            df_show = df_comp[[c for c in cols_orden if c in df_comp.columns]].copy()

            # columnas de valores (kg/USD): redondear a entero para que "localized" no muestre decimales
            cols_valor = {"total_real", "total_fc", "total_presupuesto", "total_pf"} | {
                f"{_MESES[m]}{suf}" for m in meses for suf in ("_real", "_fc", "_pv", "_pf")
            }
            for c in cols_valor & set(df_show.columns):
                df_show[c] = pd.to_numeric(df_show[c], errors="coerce").round(0)

            styled = _style_delta(df_show, meses)
            st.dataframe(
                styled,
                use_container_width=True,
                hide_index=True,
                column_config=col_cfg,
                height=min(56 + len(df_show) * 35, 680),
            )

            # ── gráfica real vs forecast vs presupuesto vs presupuesto finanzas por mes ──
            with st.expander("📊 gráfica por mes"):
                datos_grafica: list[dict] = []
                for mes in meses:
                    mn = _MESES[mes]
                    col_r = f"{mn}_real"
                    col_f = f"{mn}_fc"
                    col_p = f"{mn}_pv"
                    col_pf = f"{mn}_pf"
                    datos_grafica.append({
                        "mes": mn.upper(),
                        "real": df_comp[col_r].sum() if col_r in df_comp.columns else 0,
                        "forecast": df_comp[col_f].sum() if col_f in df_comp.columns else 0,
                        "presupuesto": df_comp[col_p].sum() if col_p in df_comp.columns else 0,
                        "presupuesto finanzas": df_comp[col_pf].sum() if col_pf in df_comp.columns else 0,
                    })
                df_g = pd.DataFrame(datos_grafica).set_index("mes")
                st.bar_chart(df_g[["real", "forecast", "presupuesto", "presupuesto finanzas"]], use_container_width=True, height=300)

            # ── descarga ──────────────────────────────────────────────────
            csv = df_show.to_csv(index=False).encode("utf-8")
            st.download_button(
                f"⬇️ CSV {label}",
                data=csv,
                file_name=f"real_vs_forecast_{seccion}_{region}_{anio_sel}_v{id_version}.csv",
                mime="text/csv",
                key=f"rvf_dl_{seccion}_{region}",
            )
