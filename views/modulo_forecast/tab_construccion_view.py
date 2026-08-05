from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, DataReturnMode, GridOptionsBuilder, JsCode

from controllers.forecast_controller import (
    generar_propuesta_ctrl,
    guardar_forecast_fila_ctrl,
    obtener_forecast_detalle_ctrl,
    _ventas_historicas_sae,
    _existencias_sae,
)
from controllers.presupuesto_ventas_controller import (
    obtener_cargas_presupuesto_ventas_ctrl,
    obtener_catalogo_productos_pv_ctrl,
)


_MESES = {1:"ene",2:"feb",3:"mar",4:"abr",5:"may",6:"jun",
          7:"jul",8:"ago",9:"sep",10:"oct",11:"nov",12:"dic"}

_TABS_SEC = [
    ("KG México",        "KG",  "MEXICO"),
]

_TIPOS = [
    ("venta",  "🟢 Venta (Forecast)"),
    ("compra", "🔵 Compra (Demand Plan)"),
]

_METODOS_LABEL_VENTA = {
    "manual": "Manual",
}
_METODOS_LABEL_COMPRA = {
    "manual": "Manual",
    "pc_anio": "Presupuesto Compras",
}

# resalta en verde los valores positivos y en rojo los negativos; 0 sin color
# — mismo criterio y colores que presupuesto_ventas_view.py / presupuesto_compras_view.py
_CELL_STYLE_VALORES = JsCode("""
function(params) {
    if (params.value > 0) {
        return {backgroundColor: '#d4edda', color: '#155724'};
    }
    if (params.value < 0) {
        return {backgroundColor: '#f8d7da', color: '#721c24'};
    }
    return null;
}
""")


def _value_formatter_js(decimales: int) -> JsCode:
    return JsCode(f"""
    function(params) {{
        if (params.value === null || params.value === undefined || params.value === '') return '';
        return Number(params.value).toFixed({decimales});
    }}
    """)


def _etiqueta_carga_pv(r: dict) -> str:
    """Etiqueta de una carga de presupuesto de ventas para el selector de
    método — usa el comentario (ahí indican de qué industria es) y cae a
    nombre de archivo + año si no hay comentario."""
    comentario = str(r.get("comentarios") or "").strip()
    if comentario:
        return comentario
    nombre = str(r.get("nombre_archivo") or "").strip()
    anio_carga = r.get("anio")
    return f"{nombre} [{anio_carga}]" if nombre else f"carga #{r.get('id_carga')}"


def _metodos_opciones(usuario_datos_id: int, tipo: str) -> dict:
    """Opciones del selector de método, según el tipo del sub-tab activo:
    - compra: fijas (manual, presupuesto compras) — no aplican las cargas de
      presupuesto de ventas.
    - venta: manual + una opción por cada carga de presupuesto de ventas del
      dueño de la versión, identificada por su comentario/industria."""
    if tipo == "compra":
        return dict(_METODOS_LABEL_COMPRA)

    opciones = dict(_METODOS_LABEL_VENTA)
    try:
        df_cargas_pv = obtener_cargas_presupuesto_ventas_ctrl(limit=50, usuario_id=usuario_datos_id)
    except Exception:
        df_cargas_pv = None
    if df_cargas_pv is not None and not df_cargas_pv.empty:
        for r in df_cargas_pv.to_dict("records"):
            id_carga = int(r["id_carga"])
            opciones[f"pv_carga:{id_carga}"] = f"Presupuesto Ventas — {_etiqueta_carga_pv(r)}"
    return opciones


def _get_usuario_id() -> int:
    u = st.session_state.get("usuario") or {}
    return int(u.get("id") or u.get("id_usuario") or 0)


def _norm_roles_list(values) -> list[str]:
    if not values:
        return []
    if isinstance(values, str):
        values = [values]
    return [str(v).strip().lower() for v in values if str(v or "").strip()]


def _tiene_rol(roles: list[str], *objetivos: str) -> bool:
    roles_set = set(_norm_roles_list(roles))
    objetivos_set = set(_norm_roles_list(objetivos))
    return bool(roles_set.intersection(objetivos_set))


def _puede_editar_sin_restriccion() -> bool:
    usuario = st.session_state.get("usuario") or {}
    if usuario.get("rol") == "Admin":
        return True
    return _tiene_rol(usuario.get("roles"), "admin", "superadmin", "forecastadmin")


def _mes_editable(anio: int, mes: int) -> bool:
    """Regla de los 3 meses: el vendedor solo puede mover el forecast de
    meses posteriores a los 3 meses siguientes al actual — si estamos en
    julio, agosto/septiembre/octubre quedan bloqueados y noviembre en
    adelante (incluido cualquier año futuro) queda editable."""
    hoy = date.today()
    idx_hoy = hoy.year * 12 + hoy.month
    idx_celda = int(anio) * 12 + int(mes)
    return idx_celda >= idx_hoy + 4


def _pivot_forecast(df: pd.DataFrame, meses: list[int], precio_map: dict | None = None) -> pd.DataFrame:
    """Convierte detalle long → wide con columnas de meses. "precio" es el
    precio SAE del producto; "total_kg" es la suma de los meses mostrados;
    "total_usd" la convierte a dólares con ese precio — mismo criterio que
    "Total Kilos Año"/"Total USD Año" en presupuesto de ventas."""
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

    meses_cols = [_MESES[m] for m in meses if _MESES[m] in wide.columns]
    wide["total_kg"] = wide[meses_cols].sum(axis=1) if meses_cols else 0.0

    precio_map = precio_map or {}
    precio_prod = wide["cve_prod"].astype(str).str.strip().map(precio_map).fillna(0.0)
    wide["precio"] = precio_prod
    wide["total_usd"] = wide["total_kg"] * precio_prod

    col_order = cols_id + ["precio", "total_kg", "total_usd"] + ref_cols + meses_cols
    return wide[[c for c in col_order if c in wide.columns]]


def mostrar_tab_construccion(
    id_version: int, id_carga_pv: int | None, anio: int, metodo_default: str, usuario_datos_id: int,
) -> None:
    usuario_id = _get_usuario_id()
    es_admin = _puede_editar_sin_restriccion()

    # selector de meses a proyectar — compartido entre Venta y Compra
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

    # regla de los 3 meses: solo se puede mover el forecast de meses más
    # allá de los 3 siguientes al actual (Admin/SuperAdmin/forecastAdmin sin
    # restricción) — se ven todos los meses seleccionados, pero los
    # bloqueados quedan de solo lectura en la tabla y no se tocan al generar
    # propuesta ni al agregar un producto manualmente
    meses_editables = [m for m in meses_sel if es_admin or _mes_editable(anio, m)]
    if not es_admin and len(meses_editables) < len(meses_sel):
        st.caption(
            "🔒 el mes actual y los 3 siguientes están bloqueados — solo se puede mover "
            "el forecast a partir del 4º mes en adelante"
        )

    st.divider()

    try:
        df_cat_precio = obtener_catalogo_productos_pv_ctrl()
    except Exception:
        df_cat_precio = pd.DataFrame()
    precio_map = {
        str(r.get("cve_prod") or "").strip(): float(r.get("precio") or 0.0)
        for r in df_cat_precio.to_dict("records")
    } if df_cat_precio is not None and not df_cat_precio.empty else {}

    tipo_tabs = st.tabs([label for _, label in _TIPOS])
    for tab_ui, (tipo, _label) in zip(tipo_tabs, _TIPOS):
        with tab_ui:
            _mostrar_construccion_tipo(
                tipo=tipo,
                id_version=id_version,
                id_carga_pv=id_carga_pv,
                anio=anio,
                metodo_default=metodo_default,
                usuario_datos_id=usuario_datos_id,
                usuario_id=usuario_id,
                es_admin=es_admin,
                meses_sel=meses_sel,
                meses_editables=meses_editables,
                precio_map=precio_map,
            )


def _mostrar_construccion_tipo(
    tipo: str,
    id_version: int,
    id_carga_pv: int | None,
    anio: int,
    metodo_default: str,
    usuario_datos_id: int,
    usuario_id: int,
    es_admin: bool,
    meses_sel: list[int],
    meses_editables: list[int],
    precio_map: dict,
) -> None:
    # botón generar propuesta automática
    metodos_opciones = _metodos_opciones(usuario_datos_id, tipo)
    # "presupuesto" (guardado en metodo_default) no es una clave de este
    # selector — si la versión quedó vinculada a una carga puntual
    # (id_carga_pv), se preselecciona esa opción "pv_carga:<id>" — solo
    # aplica al sub-tab de venta, que es el único ligado a presupuesto de ventas
    metodo_default_ui = metodo_default if tipo == "venta" else "manual"
    if tipo == "venta" and metodo_default == "presupuesto" and id_carga_pv:
        candidato = f"pv_carga:{int(id_carga_pv)}"
        if candidato in metodos_opciones:
            metodo_default_ui = candidato

    col_m, col_btn = st.columns([2, 1])
    with col_m:
        metodo = st.selectbox(
            "método automático",
            list(metodos_opciones.keys()),
            index=list(metodos_opciones.keys()).index(metodo_default_ui) if metodo_default_ui in metodos_opciones else 0,
            format_func=lambda k: metodos_opciones[k],
            key=f"fc_metodo_auto_{tipo}",
        )
    with col_btn:
        st.write("")
        st.write("")
        if st.button("⚡ generar propuesta", use_container_width=True, key=f"fc_btn_generar_{tipo}"):
            if not meses_editables:
                st.warning("los meses seleccionados están dentro de la ventana bloqueada (mes actual + 3 siguientes)")
            else:
                with st.spinner("calculando propuesta…"):
                    for _, seccion, region in _TABS_SEC:
                        generar_propuesta_ctrl(
                            id_version=id_version,
                            id_carga_pv=id_carga_pv,
                            anio=anio,
                            meses=meses_editables,
                            seccion=seccion,
                            region=region,
                            metodo=metodo,
                            usuario_id=usuario_id,
                            usuario_datos_id=usuario_datos_id,
                            tipo=tipo,
                        )
                st.success("propuesta generada — revisa y ajusta los valores")
                st.rerun()

    st.divider()

    sub_tabs = st.tabs([t[0] for t in _TABS_SEC])

    for tab_ui, (label, seccion, region) in zip(sub_tabs, _TABS_SEC):
        with tab_ui:
            df_det = obtener_forecast_detalle_ctrl(
                id_version=id_version, seccion=seccion, region=region, tipo=tipo
            )

            if df_det is None or df_det.empty:
                st.info(f"sin datos para {label} — usa 'generar propuesta' o carga manualmente")
                _panel_carga_manual(id_version, seccion, region, anio, meses_editables, usuario_id, tipo)
                continue

            df_det["mes"] = pd.to_numeric(df_det["mes"], errors="coerce").astype(int)
            for _c in ("forecast", "presupuesto_valor", "venta_real_mes_ant", "venta_real_prom_3m"):
                if _c in df_det.columns:
                    df_det[_c] = pd.to_numeric(df_det[_c], errors="coerce").fillna(0.0)
            df_det = df_det[df_det["mes"].isin(meses_sel)]

            if df_det.empty:
                st.info(f"sin datos para los meses seleccionados en {label}")
                _panel_carga_manual(id_version, seccion, region, anio, meses_editables, usuario_id, tipo)
                continue

            pivot_orig = _pivot_forecast(df_det, meses_sel, precio_map)
            decimales = 0 if seccion == "KG" else 2

            gb = GridOptionsBuilder.from_dataframe(pivot_orig)
            gb.configure_default_column(editable=False, resizable=True, width=100)

            gb.configure_column("cve_prod", headerName="cve prod", editable=False, width=130)
            gb.configure_column("producto_excel", headerName="producto", editable=False, width=220)
            gb.configure_column(
                "precio", headerName="precio", editable=False, width=100,
                type=["numericColumn"], valueFormatter=_value_formatter_js(4),
            )
            gb.configure_column(
                "total_kg", headerName="Total KG", editable=False, width=110,
                type=["numericColumn"], valueFormatter=_value_formatter_js(0),
            )
            gb.configure_column(
                "total_usd", headerName="Total USD", editable=False, width=110,
                type=["numericColumn"], valueFormatter=_value_formatter_js(2),
            )
            gb.configure_column(
                "venta_real_mes_ant", headerName="vta año ant", editable=False, width=110,
                type=["numericColumn"], valueFormatter=_value_formatter_js(2),
            )
            gb.configure_column(
                "venta_real_prom_3m", headerName="prom 3m", editable=False, width=100,
                type=["numericColumn"], valueFormatter=_value_formatter_js(2),
            )
            gb.configure_column(
                "presupuesto_valor", headerName="presupuesto", editable=False, width=110,
                type=["numericColumn"], valueFormatter=_value_formatter_js(2),
            )
            for m in meses_sel:
                mn = _MESES[m]
                if mn not in pivot_orig.columns:
                    continue
                editable_mes = es_admin or _mes_editable(anio, m)
                gb.configure_column(
                    mn,
                    headerName=mn.upper() if editable_mes else f"🔒 {mn.upper()}",
                    editable=editable_mes,
                    width=90,
                    type=["numericColumn"],
                    cellEditor="agNumberCellEditor",
                    cellStyle=_CELL_STYLE_VALORES,
                    valueFormatter=_value_formatter_js(decimales),
                )

            st.caption("🟩 valor positivo  |  🟥 valor negativo  |  🔒 mes bloqueado (regla de los 3 meses)")

            grid_response = AgGrid(
                pivot_orig,
                gridOptions=gb.build(),
                update_on=[("cellValueChanged", 600)],
                data_return_mode=DataReturnMode.AS_INPUT,
                fit_columns_on_grid_load=False,
                allow_unsafe_jscode=True,
                height=min(56 + len(pivot_orig) * 35, 680),
                key=f"fc_editor_{tipo}_{seccion}_{region}_{id_version}",
            )
            edited = pd.DataFrame(grid_response.get("data", []))

            if st.button("💾 guardar cambios", type="primary",
                         use_container_width=True,
                         key=f"fc_save_{tipo}_{seccion}_{region}_{id_version}"):
                cambios = _guardar_cambios_pivot(
                    pivot_orig, edited, df_det, id_version, seccion, region, anio, meses_sel, usuario_id, es_admin, tipo,
                )
                if cambios:
                    st.success(f"{cambios} registros guardados")
                    st.rerun()
                else:
                    st.info("sin cambios detectados")

            _panel_carga_manual(id_version, seccion, region, anio, meses_editables, usuario_id, tipo)


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
    es_admin: bool,
    tipo: str,
) -> int:
    cambios = 0
    for i in range(len(orig)):
        cve_prod = str(orig.iloc[i].get("cve_prod") or "").strip()
        prod_excel = str(orig.iloc[i].get("producto_excel") or "").strip()

        # referencias guardadas
        mask = df_det["cve_prod"].astype(str).str.strip() == cve_prod
        ref_row = df_det[mask].iloc[0] if mask.any() else pd.Series()

        for mes in meses_sel:
            # defensa adicional: la columna ya viene bloqueada en la UI
            # (editable=False), esto solo evita persistir un cambio si de
            # todas formas llegara uno para un mes bloqueado
            if not es_admin and not _mes_editable(anio, mes):
                continue
            mn = _MESES[mes]
            if mn not in orig.columns or i >= len(edited):
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
                tipo=tipo,
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
    tipo: str,
) -> None:
    """Formulario para agregar manualmente una fila al forecast."""
    with st.expander("➕ agregar producto manualmente"):
        try:
            df_cat = obtener_catalogo_productos_pv_ctrl()
        except Exception:
            df_cat = pd.DataFrame()

        nom_key = f"fc_man_nom_{tipo}_{seccion}_{region}"

        if df_cat is not None and not df_cat.empty:
            sel_key = f"fc_man_prod_{tipo}_{seccion}_{region}"
            opciones_prod = {"(escribe cve_prod)": ""} | {
                f"{r['cve_prod']}  {r['descr']}": r['cve_prod']
                for r in df_cat.to_dict("records")
            }
            cve_a_descr = {
                str(r["cve_prod"]).strip(): str(r.get("descr") or "").strip()
                for r in df_cat.to_dict("records")
            }

            def _autofill_nombre_producto() -> None:
                cve_sel = opciones_prod.get(st.session_state.get(sel_key), "")
                if cve_sel:
                    st.session_state[nom_key] = cve_a_descr.get(cve_sel, "")

            sel_prod = st.selectbox(
                "producto SAE", list(opciones_prod.keys()), key=sel_key,
                on_change=_autofill_nombre_producto,
            )
            cve_prod = opciones_prod[sel_prod]
        else:
            cve_prod = st.text_input("cve_prod", key=f"fc_man_cve_{tipo}_{seccion}_{region}")

        prod_excel = st.text_input("nombre producto (opcional)", key=nom_key)

        # se arma en bloques de hasta 6 columnas por fila, creando un st.columns()
        # nuevo por cada fila: así el orden real (y el tab-order) queda
        # ene→feb→mar→…→dic en vez de agruparse por columna (ene, jul, feb, ago, …)
        valores: dict[int, float] = {}
        CHUNK = 6
        for inicio in range(0, len(meses_sel), CHUNK):
            fila_meses = meses_sel[inicio:inicio + CHUNK]
            cols = st.columns(len(fila_meses))
            for col, mes in zip(cols, fila_meses):
                with col:
                    valores[mes] = st.number_input(
                        _MESES[mes].upper(), min_value=0.0, value=0.0, format="%.4f",
                        key=f"fc_man_val_{tipo}_{seccion}_{region}_{mes}"
                    )

        if st.button("agregar", key=f"fc_man_btn_{tipo}_{seccion}_{region}"):
            if not cve_prod.strip():
                st.error("ingresa cve_prod")
                return
            for mes, val in valores.items():
                guardar_forecast_fila_ctrl(
                    id_version=id_version, seccion=seccion, region=region,
                    cve_prod=cve_prod.strip(), producto_excel=prod_excel.strip() or None,
                    anio=anio, mes=mes, forecast=val,
                    justificacion=None, metodo="manual", usuario_id=usuario_id,
                    tipo=tipo,
                )
            st.success("producto agregado")
            st.rerun()
