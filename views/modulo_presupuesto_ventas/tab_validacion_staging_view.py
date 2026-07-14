from __future__ import annotations

from typing import Optional

import pandas as pd
import streamlit as st

from controllers.presupuesto_ventas_controller import (
    actualizar_cantidad_staging_presupuesto_ventas_ctrl,
    asignar_clave_cliente_staging_presupuesto_ventas_ctrl,
    asignar_clave_linea_staging_presupuesto_ventas_ctrl,
    asignar_clave_producto_staging_presupuesto_ventas_ctrl,
    asignar_clave_vendedor_staging_presupuesto_ventas_ctrl,
    asignar_unidad_negocio_staging_presupuesto_ventas_ctrl,
    obtener_cargas_presupuesto_ventas_ctrl,
    obtener_clientes_sae_presupuesto_ventas_ctrl,
    obtener_lineas_sae_presupuesto_ventas_ctrl,
    obtener_productos_sae_presupuesto_ventas_ctrl,
    obtener_resumen_staging_presupuesto_ventas_ctrl,
    obtener_staging_presupuesto_ventas_ctrl,
    obtener_vendedores_sae_presupuesto_ventas_ctrl,
    recalcular_estatus_staging_presupuesto_ventas_ctrl,
    validar_staging_presupuesto_ventas_con_sae_ctrl,
)
from models.presupuesto_ventas_model import obtener_staging_presupuesto_ventas_model
from database.conexion import obtener_conexion


@st.cache_data(ttl=300, show_spinner=False)
def _cargar_productos_sae() -> pd.DataFrame:
    return obtener_productos_sae_presupuesto_ventas_ctrl()


@st.cache_data(ttl=300, show_spinner=False)
def _cargar_clientes_sae() -> pd.DataFrame:
    return obtener_clientes_sae_presupuesto_ventas_ctrl()


@st.cache_data(ttl=300, show_spinner=False)
def _cargar_vendedores_sae() -> pd.DataFrame:
    return obtener_vendedores_sae_presupuesto_ventas_ctrl()


@st.cache_data(ttl=300, show_spinner=False)
def _cargar_lineas_sae() -> pd.DataFrame:
    return obtener_lineas_sae_presupuesto_ventas_ctrl()


def _get_usuario_id() -> int:
    usuario = st.session_state.get("usuario") or {}
    return int(usuario.get("id") or usuario.get("id_usuario") or 0)


def _obtener_unidades_negocio() -> list[dict]:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("select id, nombre from Unidades_Negocio where estatus = 1 order by nombre")
        return cur.fetchall() or []
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _selector_carga() -> Optional[int]:
    cargas = obtener_cargas_presupuesto_ventas_ctrl(limit=50, usuario_id=_get_usuario_id())

    if cargas is None or cargas.empty:
        st.info("aún no hay cargas registradas")
        return None

    opciones = {
        f"{r['id_carga']} | {r['nombre_archivo']} | {r['anio']} | {r['estatus']}": int(r["id_carga"])
        for r in cargas.to_dict(orient="records")
    }

    labels = list(opciones.keys())
    valor_default = st.session_state.get("pv_id_carga_actual")
    index_default = next(
        (i for i, lbl in enumerate(labels) if opciones[lbl] == valor_default), 0
    )

    label = st.selectbox("carga", options=labels, index=index_default, key="pv_val_select_carga")
    id_carga = int(opciones[label])
    st.session_state["pv_id_carga_actual"] = id_carga
    return id_carga


# ── helpers ──────────────────────────────────────────────────────────────────

def _filtrar_sae(df: pd.DataFrame, texto: str, cols: list[str]) -> pd.DataFrame:
    if not texto or df.empty:
        return df
    t = texto.upper().strip()
    mask = pd.Series([False] * len(df), index=df.index)
    for col in cols:
        if col in df.columns:
            mask |= df[col].astype(str).str.upper().str.contains(t, na=False)
    return df[mask]


def _resumen_staging(id_carga: int) -> None:
    resumen = obtener_resumen_staging_presupuesto_ventas_ctrl(id_carga=id_carga)
    if resumen is None or resumen.empty:
        st.info("sin datos en staging para esta carga")
        return
    st.dataframe(resumen, use_container_width=True, hide_index=True, height=200)


# ── panel: validación automática ─────────────────────────────────────────────

def _panel_validacion_auto(id_carga: int) -> None:
    col1, col2 = st.columns(2)

    with col1:
        if st.button("validar contra SAE", type="primary", use_container_width=True, key="pv_val_btn_validar"):
            with st.spinner("consultando SAE y actualizando staging…"):
                try:
                    res = validar_staging_presupuesto_ventas_con_sae_ctrl(id_carga=id_carga)
                    st.success(f"validación completa — ok: {res['total_ok']} | error: {res['total_error']}")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"error en validación: {e}")

    with col2:
        if st.button("recalcular estatus", use_container_width=True, key="pv_val_btn_recalc"):
            try:
                res = recalcular_estatus_staging_presupuesto_ventas_ctrl(id_carga=id_carga)
                st.success(f"recalculado — completo: {res['total_completo']} | pendiente: {res['total_pendiente']}")
                st.rerun()
            except Exception as e:
                st.error(f"error al recalcular: {e}")

    st.markdown("#### resumen por estatus")
    _resumen_staging(id_carga)


# ── panel: productos ──────────────────────────────────────────────────────────

def _panel_productos(id_carga: int) -> None:
    staging = obtener_staging_presupuesto_ventas_ctrl(id_carga=id_carga, limit=200000)

    if staging.empty:
        st.info("sin registros en staging")
        return

    # tabla de productos únicos
    cols_prod = ["producto_excel", "cve_prod", "estatus_match"]
    df_prods = (
        staging[[c for c in cols_prod if c in staging.columns]]
        .drop_duplicates(subset=["producto_excel"])
        .sort_values("producto_excel")
        .reset_index(drop=True)
    )

    st.markdown("##### productos en staging")
    st.dataframe(df_prods, use_container_width=True, hide_index=True, height=220)

    st.divider()
    st.markdown("##### asignar clave SAE")

    sin_asignar = df_prods[df_prods["cve_prod"].isna() | (df_prods["cve_prod"] == "")][
        "producto_excel"
    ].tolist()

    col1, col2 = st.columns([3, 1])
    with col1:
        prod_sel = st.selectbox(
            "producto excel",
            options=[""] + sin_asignar,
            key="pv_val_prod_sel",
        )
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        todos = st.checkbox("todos los productos", key="pv_val_prod_todos")

    # búsqueda SAE
    filtro = st.text_input("buscar en catálogo SAE (código o descripción)", key="pv_val_prod_filtro")

    with st.spinner("cargando catálogo SAE…"):
        df_sae = _cargar_productos_sae()

    df_sae_fil = _filtrar_sae(df_sae, filtro, ["cve_art", "descr", "linea"])
    st.dataframe(
        df_sae_fil[["cve_art", "descr", "linea"]].head(50) if not df_sae_fil.empty else df_sae_fil,
        use_container_width=True,
        hide_index=True,
        height=200,
    )

    col3, col4 = st.columns([3, 1])
    with col3:
        cve_input = st.text_input("cve_art a asignar", key="pv_val_prod_cve").strip().upper()
    with col4:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("asignar", type="primary", use_container_width=True, key="pv_val_prod_btn"):
            objetivo = None if todos else prod_sel
            if not todos and not objetivo:
                st.warning("selecciona un producto o marca 'todos'")
            elif not cve_input:
                st.warning("ingresa la clave SAE")
            else:
                productos_a_asignar = (
                    df_prods["producto_excel"].tolist() if todos else [objetivo]
                )
                total = 0
                for p in productos_a_asignar:
                    total += asignar_clave_producto_staging_presupuesto_ventas_ctrl(
                        id_carga=id_carga,
                        producto_excel=p,
                        cve_prod=cve_input,
                    )
                st.success(f"asignado '{cve_input}' a {total} registros")
                st.rerun()


# ── panel: clientes ───────────────────────────────────────────────────────────

def _panel_clientes(id_carga: int) -> None:
    staging = obtener_staging_presupuesto_ventas_ctrl(id_carga=id_carga, limit=200000)

    if staging.empty:
        st.info("sin registros en staging")
        return

    df_clie = (
        staging[["cliente_excel", "cve_clie", "estatus_match"]]
        .dropna(subset=["cliente_excel"])
        .drop_duplicates(subset=["cliente_excel"])
        .sort_values("cliente_excel")
        .reset_index(drop=True)
    )

    st.markdown("##### clientes en staging")
    st.dataframe(df_clie, use_container_width=True, hide_index=True, height=220)

    st.divider()
    st.markdown("##### asignar clave SAE")

    sin_asignar = df_clie[df_clie["cve_clie"].isna() | (df_clie["cve_clie"] == "")][
        "cliente_excel"
    ].tolist()

    clie_sel = st.selectbox("cliente excel", options=[""] + sin_asignar, key="pv_val_clie_sel")

    filtro = st.text_input("buscar cliente SAE", key="pv_val_clie_filtro")

    with st.spinner("cargando clientes SAE…"):
        df_sae = _cargar_clientes_sae()

    df_sae_fil = _filtrar_sae(df_sae, filtro, ["clave", "nombre"])
    st.dataframe(
        df_sae_fil[["clave", "nombre", "rfc"]].head(50) if not df_sae_fil.empty else df_sae_fil,
        use_container_width=True,
        hide_index=True,
        height=200,
    )

    col1, col2 = st.columns([3, 1])
    with col1:
        cve_input = st.text_input("clave SAE a asignar", key="pv_val_clie_cve").strip().upper()
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("asignar", type="primary", use_container_width=True, key="pv_val_clie_btn"):
            if not clie_sel:
                st.warning("selecciona un cliente")
            elif not cve_input:
                st.warning("ingresa la clave SAE")
            else:
                total = asignar_clave_cliente_staging_presupuesto_ventas_ctrl(
                    id_carga=id_carga,
                    cliente_excel=clie_sel,
                    cve_clie=cve_input,
                )
                st.success(f"asignado a {total} registros")
                st.rerun()


# ── panel: vendedores ─────────────────────────────────────────────────────────

def _panel_vendedores(id_carga: int) -> None:
    staging = obtener_staging_presupuesto_ventas_ctrl(id_carga=id_carga, limit=200000)

    if staging.empty:
        st.info("sin registros en staging")
        return

    df_vend = (
        staging[["vendedor_excel", "cve_vend", "estatus_match"]]
        .dropna(subset=["vendedor_excel"])
        .drop_duplicates(subset=["vendedor_excel"])
        .sort_values("vendedor_excel")
        .reset_index(drop=True)
    )

    st.markdown("##### vendedores en staging")
    st.dataframe(df_vend, use_container_width=True, hide_index=True, height=200)

    st.divider()
    st.markdown("##### asignar clave SAE")

    sin_asignar = df_vend[df_vend["cve_vend"].isna() | (df_vend["cve_vend"] == "")][
        "vendedor_excel"
    ].tolist()

    vend_sel = st.selectbox("vendedor excel", options=[""] + sin_asignar, key="pv_val_vend_sel")

    filtro = st.text_input("buscar vendedor SAE", key="pv_val_vend_filtro")

    with st.spinner("cargando vendedores SAE…"):
        df_sae = _cargar_vendedores_sae()

    df_sae_fil = _filtrar_sae(df_sae, filtro, ["cve_vend", "nombre"])
    st.dataframe(
        df_sae_fil[["cve_vend", "nombre"]].head(50) if not df_sae_fil.empty else df_sae_fil,
        use_container_width=True,
        hide_index=True,
        height=180,
    )

    col1, col2 = st.columns([3, 1])
    with col1:
        cve_input = st.text_input("cve_vend a asignar", key="pv_val_vend_cve").strip().upper()
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("asignar", type="primary", use_container_width=True, key="pv_val_vend_btn"):
            if not vend_sel:
                st.warning("selecciona un vendedor")
            elif not cve_input:
                st.warning("ingresa la clave SAE")
            else:
                total = asignar_clave_vendedor_staging_presupuesto_ventas_ctrl(
                    id_carga=id_carga,
                    vendedor_excel=vend_sel,
                    cve_vend=cve_input,
                )
                st.success(f"asignado a {total} registros")
                st.rerun()


# ── panel: líneas ─────────────────────────────────────────────────────────────

def _panel_lineas(id_carga: int) -> None:
    staging = obtener_staging_presupuesto_ventas_ctrl(id_carga=id_carga, limit=200000)

    if staging.empty:
        st.info("sin registros en staging")
        return

    df_lin = (
        staging[["linea_excel", "cve_linea", "estatus_match"]]
        .dropna(subset=["linea_excel"])
        .drop_duplicates(subset=["linea_excel"])
        .sort_values("linea_excel")
        .reset_index(drop=True)
    )

    st.markdown("##### líneas en staging")
    st.dataframe(df_lin, use_container_width=True, hide_index=True, height=180)

    st.divider()
    st.markdown("##### asignar clave SAE")

    sin_asignar = df_lin[df_lin["cve_linea"].isna() | (df_lin["cve_linea"] == "")][
        "linea_excel"
    ].tolist()

    lin_sel = st.selectbox("línea excel", options=[""] + sin_asignar, key="pv_val_lin_sel")

    filtro = st.text_input("buscar línea SAE", key="pv_val_lin_filtro")

    with st.spinner("cargando líneas SAE…"):
        df_sae = _cargar_lineas_sae()

    df_sae_fil = _filtrar_sae(df_sae, filtro, ["cve_lin", "desc_lin"])
    st.dataframe(
        df_sae_fil[["cve_lin", "desc_lin"]].head(50) if not df_sae_fil.empty else df_sae_fil,
        use_container_width=True,
        hide_index=True,
        height=160,
    )

    col1, col2 = st.columns([3, 1])
    with col1:
        cve_input = st.text_input("cve_lin a asignar", key="pv_val_lin_cve").strip().upper()
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("asignar", type="primary", use_container_width=True, key="pv_val_lin_btn"):
            if not lin_sel:
                st.warning("selecciona una línea")
            elif not cve_input:
                st.warning("ingresa la clave SAE")
            else:
                total = asignar_clave_linea_staging_presupuesto_ventas_ctrl(
                    id_carga=id_carga,
                    linea_excel=lin_sel,
                    cve_linea=cve_input,
                )
                st.success(f"asignado a {total} registros")
                st.rerun()


# ── panel: unidad de negocio ──────────────────────────────────────────────────

def _panel_unidad_negocio(id_carga: int) -> None:
    staging = obtener_staging_presupuesto_ventas_ctrl(id_carga=id_carga, limit=200000)

    if staging.empty:
        st.info("sin registros en staging")
        return

    df_un = (
        staging[["unidad_negocio_excel", "id_unidad_negocio", "estatus_match"]]
        .drop_duplicates(subset=["unidad_negocio_excel"])
        .sort_values("unidad_negocio_excel")
        .reset_index(drop=True)
    )

    st.markdown("##### unidades de negocio en staging")
    st.dataframe(df_un, use_container_width=True, hide_index=True, height=200)

    st.divider()
    st.markdown("##### asignar unidad de negocio")

    sin_asignar = df_un[df_un["id_unidad_negocio"].isna()][
        "unidad_negocio_excel"
    ].fillna("(sin nombre)").tolist()

    todas_un = df_un["unidad_negocio_excel"].fillna("(sin nombre)").tolist()

    col1, col2 = st.columns([3, 1])
    with col1:
        un_sel = st.selectbox(
            "valor excel sin asignar",
            options=[""] + sin_asignar,
            key="pv_val_un_sel",
        )
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        aplicar_todos = st.checkbox("aplicar a todos", key="pv_val_un_todos")

    unidades = _obtener_unidades_negocio()
    if not unidades:
        st.warning("no se encontraron unidades de negocio")
        return

    opciones_un = {f"{u['id']} – {u['nombre']}": int(u["id"]) for u in unidades}
    label_un = st.selectbox("unidad de negocio", options=list(opciones_un.keys()), key="pv_val_un_pick")
    id_un = opciones_un[label_un]

    if st.button("asignar unidad de negocio", type="primary", use_container_width=True, key="pv_val_un_btn"):
        filtro_val = None if aplicar_todos else (un_sel or None)
        total = asignar_unidad_negocio_staging_presupuesto_ventas_ctrl(
            id_carga=id_carga,
            id_unidad_negocio=id_un,
            filtro_unidad_negocio_excel=filtro_val,
        )
        st.success(f"asignado a {total} registros")
        st.rerun()


# ── constantes pivot ─────────────────────────────────────────────────────────

_MESES_NOMBRES = {
    1: "ene", 2: "feb", 3: "mar", 4: "abr",
    5: "may", 6: "jun", 7: "jul", 8: "ago",
    9: "sep", 10: "oct", 11: "nov", 12: "dic",
}

_TABS_PIVOT = [
    ("USD México",       "USD", "MEXICO"),
    ("KG México",        "KG",  "MEXICO"),
    ("CAM & Caribe USD", "USD", "CAM & Caribe"),
    ("CAM & Caribe KG",  "KG",  "CAM & Caribe"),
]

_COLS_ID_PIVOT = ["company", "cliente_excel", "codigo_origen", "producto_excel"]


# ── helpers pivot ─────────────────────────────────────────────────────────────

def _construir_pivot(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, dict]:
    cols_id = [c for c in _COLS_ID_PIVOT if c in df.columns]

    # mapping (row_key_tuple, mes) → id_staging
    mapping: dict = {}
    for _, row in df.iterrows():
        key = tuple(str(row.get(c) or "") for c in cols_id)
        mapping[(key, int(row["mes"]))] = int(row["id_staging"])

    # precio por fila de identidad (primero encontrado)
    precio_map = (
        df.groupby(cols_id, dropna=False)["precio"]
        .first()
        .reset_index()
    )

    # pivot: filas = identidad, columnas = mes, valor = valor numérico
    pivot = df.pivot_table(
        index=cols_id,
        columns="mes",
        values="valor",
        aggfunc="sum",
        fill_value=0.0,
    ).reset_index()

    pivot = pivot.rename(columns=_MESES_NOMBRES)

    pivot = pivot.merge(precio_map, on=cols_id, how="left")

    # orden de columnas: identidad, precio, meses disponibles
    meses_presentes = [_MESES_NOMBRES[m] for m in range(1, 13) if _MESES_NOMBRES[m] in pivot.columns]
    col_order = cols_id + ["precio"] + meses_presentes
    pivot = pivot[[c for c in col_order if c in pivot.columns]]

    return pivot, mapping


def _guardar_pivot(
    orig: pd.DataFrame,
    edited: pd.DataFrame,
    mapping: dict,
    seccion: str,
    cols_id: list[str],
) -> tuple[int, int]:
    cambios = 0
    errores = 0

    for i in range(len(orig)):
        row_key = tuple(str(orig.iloc[i].get(c) or "") for c in cols_id)

        precio_orig = float(orig.iloc[i].get("precio") or 0)
        precio_edit = float(edited.iloc[i].get("precio") or 0)
        precio_cambio = abs(precio_edit - precio_orig) > 1e-6

        for mes_num in range(1, 13):
            mes_name = _MESES_NOMBRES[mes_num]
            if mes_name not in orig.columns:
                continue

            val_orig = float(orig.iloc[i].get(mes_name) or 0)
            val_edit = float(edited.iloc[i].get(mes_name) or 0)
            val_cambio = abs(val_edit - val_orig) > 1e-4

            if not val_cambio and not precio_cambio:
                continue

            id_staging = mapping.get((row_key, mes_num))
            if not id_staging:
                continue

            precio_final = precio_edit if precio_cambio else precio_orig
            valor_final = val_edit if val_cambio else val_orig

            if seccion == "KG":
                cantidad_kg_final = valor_final
                importe_final = round(valor_final * precio_final, 2)
            else:
                cantidad_kg_final = 0.0
                importe_final = valor_final

            try:
                actualizar_cantidad_staging_presupuesto_ventas_ctrl(
                    id_staging=id_staging,
                    cantidad_kg=cantidad_kg_final,
                    importe=importe_final,
                    precio=precio_final,
                    valor=valor_final,
                )
                cambios += 1
            except Exception:
                errores += 1

    return cambios, errores


# ── panel: tabla presupuesto (pivot por sección) ──────────────────────────────

def _panel_tabla_pivot(id_carga: int) -> None:
    staging = obtener_staging_presupuesto_ventas_ctrl(id_carga=id_carga, limit=200000)

    if staging is None or staging.empty:
        st.info("sin registros en staging para esta carga")
        return

    # normalizar columnas numéricas
    for col in ("valor", "importe", "cantidad_kg", "precio"):
        if col in staging.columns:
            staging[col] = pd.to_numeric(staging[col], errors="coerce").fillna(0.0)
        else:
            staging[col] = 0.0

    if "valor" not in staging.columns or staging["valor"].eq(0).all():
        staging["valor"] = staging["importe"]

    staging["mes"] = pd.to_numeric(staging["mes"], errors="coerce").fillna(0).astype(int)

    sub_tabs = st.tabs([t[0] for t in _TABS_PIVOT])

    for tab_ui, (label, seccion, region) in zip(sub_tabs, _TABS_PIVOT):
        with tab_ui:
            mask = staging["seccion"].astype(str) == seccion
            if region:
                mask &= staging["region"].astype(str) == region

            df_sec = staging[mask].copy()

            if df_sec.empty:
                st.info(f"sin datos para {label}")
                continue

            cols_id = [c for c in _COLS_ID_PIVOT if c in df_sec.columns]
            pivot, mapping = _construir_pivot(df_sec)

            meses_presentes = [
                _MESES_NOMBRES[m] for m in range(1, 13)
                if _MESES_NOMBRES[m] in pivot.columns
            ]

            fmt_valor = "%.2f" if seccion == "USD" else "%.4f"

            col_config: dict = {}
            for c in cols_id:
                col_config[c] = st.column_config.TextColumn(c.replace("_excel", "").replace("_", " "), disabled=True)
            col_config["precio"] = st.column_config.NumberColumn("precio USD/kg", format="%.4f")
            for m in meses_presentes:
                col_config[m] = st.column_config.NumberColumn(m.upper(), format=fmt_valor)

            edited = st.data_editor(
                pivot,
                use_container_width=True,
                hide_index=True,
                num_rows="fixed",
                height=min(56 + len(pivot) * 35, 650),
                column_config=col_config,
                key=f"pv_pivot_{seccion}_{region}_{id_carga}",
            )

            if st.button(
                "💾 guardar cambios",
                type="primary",
                use_container_width=True,
                key=f"pv_pivot_save_{seccion}_{region}_{id_carga}",
            ):
                cambios, errores = _guardar_pivot(pivot, edited, mapping, seccion, cols_id)
                if cambios:
                    st.success(f"guardados {cambios} registros")
                    st.rerun()
                if errores:
                    st.error(f"{errores} filas con error al guardar")
                if not cambios and not errores:
                    st.info("sin cambios detectados")


# ── entry point ───────────────────────────────────────────────────────────────

def mostrar_tab_validacion_staging_presupuesto_ventas() -> None:
    st.subheader("validación staging vs SAE")

    id_carga = _selector_carga()
    if id_carga is None:
        return

    with st.container(border=True):
        _panel_validacion_auto(id_carga)

    st.divider()

    tab_pivot, tab_prod, tab_clie, tab_vend, tab_lin, tab_un = st.tabs([
        "tabla presupuesto",
        "productos",
        "clientes",
        "vendedores",
        "líneas",
        "unidad de negocio",
    ])

    with tab_pivot:
        _panel_tabla_pivot(id_carga)

    with tab_prod:
        _panel_productos(id_carga)

    with tab_clie:
        _panel_clientes(id_carga)

    with tab_vend:
        _panel_vendedores(id_carga)

    with tab_lin:
        _panel_lineas(id_carga)

    with tab_un:
        _panel_unidad_negocio(id_carga)
