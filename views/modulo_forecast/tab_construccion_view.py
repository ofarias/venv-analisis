from __future__ import annotations

import pandas as pd
import streamlit as st

from controllers.forecast_controller import (
    generar_propuesta_ctrl,
    guardar_forecast_fila_ctrl,
    obtener_forecast_detalle_ctrl,
    _ventas_historicas_sae,
    _existencias_sae,
)
from controllers.presupuesto_ventas_controller import obtener_catalogo_productos_pv_ctrl


_MESES = {1:"ene",2:"feb",3:"mar",4:"abr",5:"may",6:"jun",
          7:"jul",8:"ago",9:"sep",10:"oct",11:"nov",12:"dic"}

_TABS_SEC = [
    ("KG México",        "KG",  "MEXICO"),
    ("USD México",       "USD", "MEXICO"),
    ("CAM & Caribe KG",  "KG",  "CAM & Caribe"),
    ("CAM & Caribe USD", "USD", "CAM & Caribe"),
]

_METODOS_LABEL = {
    "manual": "Manual",
    "prom_3m": "Promedio 3 meses",
    "prom_12m": "Promedio 12 meses",
    "pct_presupuesto": "95% presupuesto",
    "presupuesto": "= Presupuesto",
    "pv_anio": "Presupuesto Ventas",
}


def _get_usuario_id() -> int:
    u = st.session_state.get("usuario") or {}
    return int(u.get("id") or u.get("id_usuario") or 0)


def _pivot_forecast(df: pd.DataFrame, meses: list[int]) -> pd.DataFrame:
    """Convierte detalle long → wide con columnas de meses."""
    if df is None or df.empty:
        return pd.DataFrame()
    cols_id = ["cve_prod", "producto_excel"]
    ref_cols = ["venta_real_mes_ant", "venta_real_prom_3m", "presupuesto_valor"]

    wide = df.pivot_table(
        index=cols_id,
        columns="mes",
        values="forecast",
        aggfunc="sum",
        fill_value=0.0,
    ).reset_index()
    wide.columns = [c if isinstance(c, str) else _MESES.get(c, str(c)) for c in wide.columns]

    ref = df.groupby(cols_id, as_index=False)[ref_cols].mean()
    wide = wide.merge(ref, on=cols_id, how="left")

    col_order = cols_id + ref_cols + [_MESES[m] for m in meses if _MESES[m] in wide.columns]
    return wide[[c for c in col_order if c in wide.columns]]


def mostrar_tab_construccion(id_version: int, id_carga_pv: int | None, anio: int, metodo_default: str) -> None:
    usuario_id = _get_usuario_id()

    # selector de meses a proyectar
    mes_opciones = list(_MESES.items())
    meses_sel = st.multiselect(
        "meses a proyectar",
        options=[m for m, _ in mes_opciones],
        default=list(range(1, 13)),
        format_func=lambda m: _MESES[m].upper(),
        key="fc_meses_sel",
    )
    if not meses_sel:
        st.warning("selecciona al menos un mes")
        return

    # botón generar propuesta automática
    col_m, col_btn = st.columns([2, 1])
    with col_m:
        metodo = st.selectbox(
            "método automático",
            list(_METODOS_LABEL.keys()),
            index=list(_METODOS_LABEL.keys()).index(metodo_default) if metodo_default in _METODOS_LABEL else 0,
            format_func=lambda k: _METODOS_LABEL[k],
            key="fc_metodo_auto",
        )
    with col_btn:
        st.write("")
        st.write("")
        if st.button("⚡ generar propuesta", use_container_width=True, key="fc_btn_generar"):
            with st.spinner("calculando propuesta…"):
                for _, seccion, region in _TABS_SEC:
                    generar_propuesta_ctrl(
                        id_version=id_version,
                        id_carga_pv=id_carga_pv,
                        anio=anio,
                        meses=meses_sel,
                        seccion=seccion,
                        region=region,
                        metodo=metodo,
                        usuario_id=usuario_id,
                    )
            st.success("propuesta generada — revisa y ajusta en cada sección")
            st.rerun()

    st.divider()

    sub_tabs = st.tabs([t[0] for t in _TABS_SEC])

    for tab_ui, (label, seccion, region) in zip(sub_tabs, _TABS_SEC):
        with tab_ui:
            df_det = obtener_forecast_detalle_ctrl(
                id_version=id_version, seccion=seccion, region=region
            )

            if df_det is None or df_det.empty:
                st.info(f"sin datos para {label} — usa 'generar propuesta' o carga manualmente")
                _panel_carga_manual(id_version, seccion, region, anio, meses_sel, usuario_id)
                continue

            df_det["mes"] = pd.to_numeric(df_det["mes"], errors="coerce").astype(int)
            for _c in ("forecast", "presupuesto_valor", "venta_real_mes_ant", "venta_real_prom_3m"):
                if _c in df_det.columns:
                    df_det[_c] = pd.to_numeric(df_det[_c], errors="coerce").fillna(0.0)
            df_det = df_det[df_det["mes"].isin(meses_sel)]

            if df_det.empty:
                st.info(f"sin datos para los meses seleccionados en {label}")
                _panel_carga_manual(id_version, seccion, region, anio, meses_sel, usuario_id)
                continue

            pivot_orig = _pivot_forecast(df_det, meses_sel)
            fmt = "%.4f" if seccion == "KG" else "%.2f"

            col_cfg: dict = {
                "cve_prod": st.column_config.TextColumn("cve prod", disabled=True),
                "producto_excel": st.column_config.TextColumn("producto", disabled=True),
                "venta_real_mes_ant": st.column_config.NumberColumn("vta año ant", format="%.2f", disabled=True),
                "venta_real_prom_3m": st.column_config.NumberColumn("prom 3m", format="%.2f", disabled=True),
                "presupuesto_valor": st.column_config.NumberColumn("presupuesto", format="%.2f", disabled=True),
            }
            for m in meses_sel:
                mn = _MESES[m]
                if mn in pivot_orig.columns:
                    col_cfg[mn] = st.column_config.NumberColumn(mn.upper(), format=fmt)

            edited = st.data_editor(
                pivot_orig,
                use_container_width=True,
                hide_index=True,
                num_rows="fixed",
                height=min(56 + len(pivot_orig) * 35, 680),
                column_config=col_cfg,
                key=f"fc_editor_{seccion}_{region}_{id_version}",
            )

            if st.button("💾 guardar cambios", type="primary",
                         use_container_width=True,
                         key=f"fc_save_{seccion}_{region}_{id_version}"):
                cambios = _guardar_cambios_pivot(
                    pivot_orig, edited, df_det, id_version, seccion, region, anio, meses_sel, usuario_id
                )
                if cambios:
                    st.success(f"{cambios} registros guardados")
                    st.rerun()
                else:
                    st.info("sin cambios detectados")

            _panel_carga_manual(id_version, seccion, region, anio, meses_sel, usuario_id)


def _guardar_cambios_pivot(
    orig: pd.DataFrame,
    edited: pd.DataFrame,
    df_det: pd.DataFrame,
    id_version: int,
    seccion: str,
    region: str | None,
    anio: int,
    meses_sel: list[int],
    usuario_id: int,
) -> int:
    cambios = 0
    for i in range(len(orig)):
        cve_prod = str(orig.iloc[i].get("cve_prod") or "").strip()
        prod_excel = str(orig.iloc[i].get("producto_excel") or "").strip()

        # referencias guardadas
        mask = df_det["cve_prod"].astype(str).str.strip() == cve_prod
        ref_row = df_det[mask].iloc[0] if mask.any() else pd.Series()

        for mes in meses_sel:
            mn = _MESES[mes]
            if mn not in orig.columns:
                continue
            val_orig = float(orig.iloc[i].get(mn) or 0)
            val_edit = float(edited.iloc[i].get(mn) or 0)
            if abs(val_edit - val_orig) < 1e-4:
                continue
            guardar_forecast_fila_ctrl(
                id_version=id_version,
                seccion=seccion,
                region=region,
                cve_prod=cve_prod or None,
                producto_excel=prod_excel or None,
                anio=anio,
                mes=mes,
                forecast=val_edit,
                justificacion=None,
                metodo="manual",
                usuario_id=usuario_id,
                venta_real_mes_ant=float(ref_row.get("venta_real_mes_ant") or 0) if not ref_row.empty else 0.0,
                venta_real_prom_3m=float(ref_row.get("venta_real_prom_3m") or 0) if not ref_row.empty else 0.0,
                presupuesto_valor=float(ref_row.get("presupuesto_valor") or 0) if not ref_row.empty else 0.0,
            )
            cambios += 1
    return cambios


def _panel_carga_manual(
    id_version: int,
    seccion: str,
    region: str | None,
    anio: int,
    meses_sel: list[int],
    usuario_id: int,
) -> None:
    """Formulario para agregar manualmente una fila al forecast."""
    with st.expander("➕ agregar producto manualmente"):
        try:
            df_cat = obtener_catalogo_productos_pv_ctrl()
        except Exception:
            df_cat = pd.DataFrame()

        if df_cat is not None and not df_cat.empty:
            opciones_prod = {"(escribe cve_prod)": ""} | {
                f"{r['cve_prod']}  {r['descr']}": r['cve_prod']
                for r in df_cat.to_dict("records")
            }
            sel_prod = st.selectbox("producto SAE", list(opciones_prod.keys()), key=f"fc_man_prod_{seccion}_{region}")
            cve_prod = opciones_prod[sel_prod]
        else:
            cve_prod = st.text_input("cve_prod", key=f"fc_man_cve_{seccion}_{region}")

        prod_excel = st.text_input("nombre producto (opcional)", key=f"fc_man_nom_{seccion}_{region}")

        valores: dict[int, float] = {}
        cols = st.columns(min(len(meses_sel), 6))
        for idx, mes in enumerate(meses_sel):
            with cols[idx % len(cols)]:
                valores[mes] = st.number_input(
                    _MESES[mes].upper(), min_value=0.0, value=0.0, format="%.4f",
                    key=f"fc_man_val_{seccion}_{region}_{mes}"
                )

        if st.button("agregar", key=f"fc_man_btn_{seccion}_{region}"):
            if not cve_prod.strip():
                st.error("ingresa cve_prod")
                return
            for mes, val in valores.items():
                guardar_forecast_fila_ctrl(
                    id_version=id_version, seccion=seccion, region=region,
                    cve_prod=cve_prod.strip(), producto_excel=prod_excel.strip() or None,
                    anio=anio, mes=mes, forecast=val,
                    justificacion=None, metodo="manual", usuario_id=usuario_id,
                )
            st.success("producto agregado")
            st.rerun()
