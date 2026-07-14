from __future__ import annotations

import pandas as pd
import streamlit as st

from controllers.presupuesto_finanzas_controller import (
    obtener_hojas_presupuesto_finanzas_ctrl,
    cargar_excel_presupuesto_finanzas_ctrl,
    obtener_cargas_presupuesto_finanzas_ctrl,
    eliminar_carga_presupuesto_finanzas_ctrl,
    obtener_opciones_filtro_presupuesto_finanzas_ctrl,
    obtener_presupuesto_finanzas_filtrado_ctrl,
    construir_tabla_pivot_presupuesto_finanzas_ctrl,
    corregir_codigos_producto_presupuesto_finanzas_ctrl,
)


_MESES_LABEL = {1: "ENERO", 2: "FEBRERO", 3: "MARZO", 4: "ABRIL", 5: "MAYO", 6: "JUNIO",
                7: "JULIO", 8: "AGOSTO", 9: "SEPTIEMBRE", 10: "OCTUBRE", 11: "NOVIEMBRE", 12: "DICIEMBRE"}


def _get_usuario_id() -> int:
    u = st.session_state.get("usuario") or {}
    return int(u.get("id") or u.get("id_usuario") or 0)


# ── panel: carga de Excel ─────────────────────────────────────────────────────

def _panel_carga() -> None:
    archivo = st.file_uploader(
        "sube el archivo de presupuesto de finanzas (hoja BD)",
        type=["xlsx", "xls"],
        key="pf_archivo",
    )
    if archivo is None:
        return

    hojas = obtener_hojas_presupuesto_finanzas_ctrl(archivo)
    if not hojas:
        st.error("no fue posible leer las hojas del archivo")
        return

    idx_bd = hojas.index("BD") if "BD" in hojas else 0

    col1, col2, col3 = st.columns([2, 1, 2])
    with col1:
        hoja = st.selectbox("hoja", options=hojas, index=idx_bd, key="pf_hoja")
    with col2:
        anio = st.number_input("año", min_value=2020, max_value=2100, value=2026, step=1, key="pf_anio")
    with col3:
        version = st.text_input("versión", value="v1", key="pf_version")

    comentarios = st.text_input("comentarios", value="", key="pf_comentarios")

    if st.button("cargar presupuesto de finanzas", type="primary", use_container_width=True, key="pf_btn_cargar"):
        usuario_id = _get_usuario_id()
        if usuario_id <= 0:
            st.error("no se encontró el usuario en sesión")
            return
        try:
            archivo.seek(0)
            res = cargar_excel_presupuesto_finanzas_ctrl(
                archivo=archivo,
                nombre_archivo=archivo.name,
                hoja=hoja,
                anio=int(anio),
                usuario_id=usuario_id,
                version=version or None,
                comentarios=comentarios or None,
            )
            st.session_state["pf_id_carga"] = int(res["id_carga"])
            st.success(f"cargado — id={res['id_carga']} | registros={res['total_registros']}")
            st.rerun()
        except Exception as e:
            st.error(f"error al cargar: {e}")


# ── selector de carga ──────────────────────────────────────────────────────────

def _selector_carga() -> int | None:
    df = obtener_cargas_presupuesto_finanzas_ctrl(limit=50, usuario_id=_get_usuario_id())
    if df is None or df.empty:
        st.info("aún no hay presupuestos de finanzas cargados — sube un archivo en el tab 📂 Cargar Excel")
        return None

    opciones = {
        f"{r['id_carga']} | {r['nombre_archivo']} | {r['anio']} | {r.get('version', '')} "
        f"({r.get('total_filas', 0)} filas)": int(r["id_carga"])
        for r in df.to_dict(orient="records")
    }
    labels = list(opciones.keys())
    default = st.session_state.get("pf_id_carga")
    idx = next((i for i, l in enumerate(labels) if opciones[l] == default), 0)

    label = st.selectbox("presupuesto de finanzas", options=labels, index=idx, key="pf_select_carga")
    id_carga = opciones[label]
    st.session_state["pf_id_carga"] = id_carga
    return id_carga


# ── panel: información de la carga + filtros + tabla ───────────────────────────

def _panel_tabla(id_carga: int) -> None:
    opciones = obtener_opciones_filtro_presupuesto_finanzas_ctrl(id_carga)

    st.caption(
        f"vendedores: {len(opciones.get('vendedores', []))} · "
        f"clientes: {len(opciones.get('clientes', []))} · "
        f"productos: {len(opciones.get('claves_producto', []))} · "
        f"áreas: {len(opciones.get('areas', []))}"
    )

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        vendedores_sel = st.multiselect(
            "vendedor", options=opciones.get("vendedores", []), default=[], key="pf_f_vendedor",
        )
    with c2:
        clientes_sel = st.multiselect(
            "cliente", options=opciones.get("clientes", []), default=[], key="pf_f_cliente",
        )
    with c3:
        productos_sel = st.multiselect(
            "clave producto", options=opciones.get("claves_producto", []), default=[], key="pf_f_producto",
        )
    with c4:
        areas_sel = st.multiselect(
            "área", options=opciones.get("areas", []), default=[], key="pf_f_area",
        )

    c5, c6 = st.columns(2)
    with c5:
        meses_disp = sorted(opciones.get("meses", []))
        meses_sel = st.multiselect(
            "mes", options=meses_disp, default=[],
            format_func=lambda m: _MESES_LABEL.get(int(m), str(m)),
            key="pf_f_mes",
        )
    with c6:
        anios_disp = sorted(opciones.get("anios", []))
        anios_sel = st.multiselect("año", options=anios_disp, default=[], key="pf_f_anio")

    df = obtener_presupuesto_finanzas_filtrado_ctrl(
        id_carga=id_carga,
        vendedores=vendedores_sel,
        clientes=clientes_sel,
        claves_producto=productos_sel,
        meses=meses_sel,
        anios=anios_sel,
        areas=areas_sel,
    )

    if df is None or df.empty:
        st.info("sin registros para los filtros seleccionados")
        return

    # ── filtros de rango: volumen / dólares (sobre el resultado ya filtrado por catálogo) ──
    vmin_data, vmax_data = float(df["volumen"].min()), float(df["volumen"].max())
    dmin_data, dmax_data = float(df["dolares"].min()), float(df["dolares"].max())

    cf1, cf2 = st.columns(2)
    with cf1:
        if vmax_data > vmin_data:
            vol_rango = st.slider(
                "rango volumen", min_value=vmin_data, max_value=vmax_data,
                value=(vmin_data, vmax_data), key="pf_f_volumen",
            )
            df = df[(df["volumen"] >= vol_rango[0]) & (df["volumen"] <= vol_rango[1])]
    with cf2:
        if dmax_data > dmin_data:
            dol_rango = st.slider(
                "rango dólares", min_value=dmin_data, max_value=dmax_data,
                value=(dmin_data, dmax_data), key="pf_f_dolares",
            )
            df = df[(df["dolares"] >= dol_rango[0]) & (df["dolares"] <= dol_rango[1])]

    if df.empty:
        st.info("sin registros para los filtros seleccionados")
        return

    st.divider()

    total_vol = df["volumen"].sum()
    total_dol = df["dolares"].sum()
    k1, k2, k3 = st.columns(3)
    k1.metric("registros", f"{len(df):,.0f}")
    k2.metric("volumen total", f"{total_vol:,.0f}")
    k3.metric("dólares total", f"{total_dol:,.0f}")

    st.subheader("📊 tabla presupuesto (formato por cliente/producto y mes)")

    df_pivot = construir_tabla_pivot_presupuesto_finanzas_ctrl(df)
    if df_pivot.empty:
        st.info("no hay datos para construir la tabla")
        return

    col_cfg: dict = {
        "clave_cliente":            st.column_config.TextColumn("clave", disabled=True, width="small"),
        "nombre_cliente":           st.column_config.TextColumn("cliente", disabled=True),
        "clave_producto_sku":       st.column_config.TextColumn("clave sku", disabled=True, width="small"),
        "producto":                 st.column_config.TextColumn("producto", disabled=True),
        "area":                     st.column_config.TextColumn("área", disabled=True),
        "vendedor":                 st.column_config.TextColumn("vendedor", disabled=True),
        "precio_unitario_dolares":  st.column_config.NumberColumn("precio unit. USD", format="%.2f", disabled=True),
        "tipo":                     st.column_config.TextColumn("tipo", disabled=True),
        "TOTAL_volumen":            st.column_config.NumberColumn("total volumen", format="localized", disabled=True),
        "TOTAL_dolares":            st.column_config.NumberColumn("total dólares", format="localized", disabled=True),
    }
    for m in range(1, 13):
        mn = _MESES_LABEL[m]
        col_cfg[f"{mn}_volumen"] = st.column_config.NumberColumn(f"{mn[:3]} volumen", format="localized", disabled=True)
        col_cfg[f"{mn}_dolares"] = st.column_config.NumberColumn(f"{mn[:3]} dólares", format="localized", disabled=True)

    cols_orden = ["clave_cliente", "nombre_cliente", "clave_producto_sku", "producto",
                  "area", "vendedor", "precio_unitario_dolares", "tipo",
                  "TOTAL_volumen", "TOTAL_dolares"]
    for m in range(1, 13):
        mn = _MESES_LABEL[m]
        cols_orden.append(f"{mn}_volumen")
        cols_orden.append(f"{mn}_dolares")

    for c in ("TOTAL_volumen", "TOTAL_dolares") + tuple(
        f"{_MESES_LABEL[m]}_volumen" for m in range(1, 13)
    ) + tuple(f"{_MESES_LABEL[m]}_dolares" for m in range(1, 13)):
        if c in df_pivot.columns:
            df_pivot[c] = pd.to_numeric(df_pivot[c], errors="coerce").round(0)

    df_show = df_pivot[[c for c in cols_orden if c in df_pivot.columns]]

    st.dataframe(
        df_show,
        use_container_width=True,
        hide_index=True,
        column_config=col_cfg,
        height=min(56 + len(df_show) * 35, 680),
    )

    csv = df_show.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ CSV",
        data=csv,
        file_name=f"presupuesto_finanzas_{id_carga}.csv",
        mime="text/csv",
        key="pf_dl_tabla",
    )


# ── panel: gestionar cargas ─────────────────────────────────────────────────────

def _panel_gestionar_cargas() -> None:
    df = obtener_cargas_presupuesto_finanzas_ctrl(limit=100, usuario_id=_get_usuario_id())
    if df is None or df.empty:
        st.info("sin cargas registradas")
        return

    st.dataframe(
        df[["id_carga", "nombre_archivo", "anio", "version", "estatus", "total_filas", "comentarios", "created_at"]],
        use_container_width=True,
        hide_index=True,
    )

    opciones = {
        f"{r['id_carga']} | {r['nombre_archivo']} | {r['anio']}": int(r["id_carga"])
        for r in df.to_dict(orient="records")
    }
    label = st.selectbox("carga", options=list(opciones.keys()), key="pf_del_select")

    col_corr, col_del = st.columns(2)
    with col_corr:
        if st.button("🔧 corregir códigos SAE", use_container_width=True, key="pf_btn_corregir"):
            id_carga = opciones[label]
            n = corregir_codigos_producto_presupuesto_finanzas_ctrl(id_carga)
            if n:
                st.success(f"{n} registros corregidos con el código SAE (INVE_CLIB01.CVE_PROD)")
                st.rerun()
            else:
                st.info("no se encontraron claves para corregir (ya coinciden con SAE o sin match en CVE_ORIGINAL)")
    with col_del:
        if st.button("🗑️ eliminar carga", type="primary", use_container_width=True, key="pf_btn_eliminar"):
            id_carga = opciones[label]
            eliminar_carga_presupuesto_finanzas_ctrl(id_carga)
            if st.session_state.get("pf_id_carga") == id_carga:
                st.session_state["pf_id_carga"] = None
            st.success("carga eliminada")
            st.rerun()


# ── entrada del módulo ──────────────────────────────────────────────────────────

def mostrar_modulo_presupuesto_finanzas() -> None:
    st.subheader("💰 Presupuesto Finanzas")

    tab_tabla, tab_carga, tab_cargas = st.tabs([
        "📊 presupuesto",
        "📂 cargar Excel",
        "🗑️ gestionar cargas",
    ])

    with tab_carga:
        _panel_carga()

    with tab_tabla:
        id_carga = _selector_carga()
        if id_carga is not None:
            _panel_tabla(id_carga)

    with tab_cargas:
        _panel_gestionar_cargas()
