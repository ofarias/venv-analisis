from __future__ import annotations

from typing import Optional

import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, DataReturnMode, GridOptionsBuilder, GridUpdateMode, JsCode

from controllers.presupuesto_ventas_controller import (
    actualizar_cve_prod_presupuesto_ventas_ctrl,
    actualizar_presupuesto_ventas_ctrl,
    cargar_excel_directo_presupuesto_ventas_ctrl,
    eliminar_carga_completa_presupuesto_ventas_ctrl,
    eliminar_registro_presupuesto_ventas_ctrl,
    insertar_presupuesto_ventas_unitario_ctrl,
    obtener_cargas_presupuesto_ventas_ctrl,
    obtener_catalogo_productos_pv_ctrl,
    obtener_presupuesto_ventas_ctrl,
    registrar_carga_presupuesto_ventas_ctrl,
)


# ── constantes ────────────────────────────────────────────────────────────────

_MESES = {
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

_COLS_ID = ["company", "cliente_excel", "codigo_origen", "producto_excel"]

# resalta en verde los valores positivos y en rojo los negativos; 0 sin color
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


# ── helpers ───────────────────────────────────────────────────────────────────

def _get_usuario_id() -> int:
    usuario = st.session_state.get("usuario") or {}
    return int(usuario.get("id") or usuario.get("id_usuario") or 0)


def _obtener_hojas(archivo) -> list[str]:
    try:
        archivo.seek(0)
        return pd.ExcelFile(archivo).sheet_names or []
    except Exception:
        return []


def _catalogo_sae() -> tuple[set, dict, dict, dict, list]:
    """Returns (sae_set, code_to_label, label_to_code, code_to_desc, options_list)."""
    df = obtener_catalogo_productos_pv_ctrl()
    if df is None or df.empty:
        return set(), {}, {"": None}, {}, [""]

    records = df.to_dict("records")
    sae_set: set = set()
    code_to_label: dict = {}
    label_to_code: dict = {"": None}
    code_to_desc: dict = {}
    items: list = []

    for r in records:
        code = str(r.get("cve_prod") or "").strip()
        desc = str(r.get("descr") or "").strip()
        if not code:
            continue
        label = f"{code}  {desc}" if desc else code
        sae_set.add(code)
        code_to_label[code] = label
        code_to_desc[code] = desc
        label_to_code[label] = code
        items.append(((desc or code).lower(), label))

    # opciones ordenadas alfabéticamente por nombre de producto
    items.sort(key=lambda t: t[0])
    options = [""] + [lbl for _, lbl in items]
    return sae_set, code_to_label, label_to_code, code_to_desc, options


def _construir_pivot(
    df: pd.DataFrame,
    sae_set: set,
    code_to_label: dict,
) -> tuple[pd.DataFrame, dict, dict]:
    cols_id = [c for c in _COLS_ID if c in df.columns]

    if df.empty:
        pivot_vacio = pd.DataFrame(
            columns=cols_id + ["_status", "_cve_prod_label", "estatus_excel", "precio"]
        )
        return pivot_vacio, {}, {}

    # pivot_table descarta filas con NaN en el índice; rellenamos con ""
    df = df.copy()
    for c in cols_id:
        df[c] = df[c].fillna("")

    # mapping (row_key, mes) → id_presupuesto  (solo meses con registro real)
    mapping: dict = {}
    for _, row in df.iterrows():
        key = tuple(str(row.get(c) or "") for c in cols_id)
        mapping[(key, int(row["mes"]))] = int(row["id_presupuesto"])

    # row_meta: datos constantes por fila para insertar nuevos meses
    meta_cols = ["id_carga", "seccion", "region", "anio",
                 "cve_prod", "estatus_excel", "precio"] + cols_id
    meta_cols = [c for c in meta_cols if c in df.columns]
    row_meta: dict = {}
    for _, row in df.iterrows():
        key = tuple(str(row.get(c) or "") for c in cols_id)
        if key not in row_meta:
            row_meta[key] = {c: row.get(c) for c in meta_cols}

    meta_map = df.groupby(cols_id, dropna=False)[
        [c for c in ["precio", "cve_prod", "estatus_excel"] if c in df.columns]
    ].first().reset_index()

    pivot = df.pivot_table(
        index=cols_id,
        columns="mes",
        values="valor",
        aggfunc="sum",
        fill_value=0.0,
    ).reset_index()
    pivot = pivot.rename(columns=_MESES)
    pivot = pivot.merge(meta_map, on=cols_id, how="left")

    meses_presentes = [_MESES[m] for m in range(1, 13) if _MESES[m] in pivot.columns]

    # indicador SAE por fila
    def _status(cve):
        return "🟢" if str(cve or "").strip() in sae_set else "🟠"

    def _label(cve):
        code = str(cve or "").strip()
        return code_to_label.get(code, code)  # fallback: raw code

    pivot["_status"] = pivot["cve_prod"].apply(_status) if "cve_prod" in pivot.columns else "🟠"
    pivot["_cve_prod_label"] = pivot["cve_prod"].apply(_label) if "cve_prod" in pivot.columns else ""

    col_order = cols_id + ["_status", "_cve_prod_label", "estatus_excel", "precio"] + meses_presentes
    pivot = pivot[[c for c in col_order if c in pivot.columns]]
    return pivot, mapping, row_meta


def _guardar_pivot(
    orig: pd.DataFrame,
    edited: pd.DataFrame,
    mapping: dict,
    row_meta: dict,
    seccion: str,
    region: Optional[str],
    cols_id: list[str],
    usuario_id: int,
    label_to_code: dict,
    id_carga: int,
    anio: int,
) -> tuple[int, int]:
    cambios = errores = 0

    for i in range(len(orig)):
        es_nueva = bool(orig.iloc[i].get("_nueva"))

        if es_nueva:
            producto = str(edited.iloc[i].get("producto_excel") or "").strip()
            sin_llenar = not producto and all(
                not str(edited.iloc[i].get(c) or "").strip() for c in cols_id
            )
            if sin_llenar:
                # fila agregada pero nunca llenada: se ignora sin marcar error
                continue
            if not producto:
                errores += 1
                continue

            row_key = tuple(str(edited.iloc[i].get(c) or "").strip() for c in cols_id)
            meta = {
                "id_carga": id_carga,
                "seccion": seccion,
                "region": region,
                "anio": anio,
                **{c: edited.iloc[i].get(c) for c in cols_id},
            }
        else:
            row_key = tuple(str(orig.iloc[i].get(c) or "") for c in cols_id)
            meta = row_meta.get(row_key, {})

        # ── cve_prod (nuevo valor u origen) ──────────────────────────────────
        cve_edit_lbl = str(edited.iloc[i].get("_cve_prod_label") or "")
        cve_edit_cod = label_to_code.get(cve_edit_lbl, cve_edit_lbl.strip() or None)

        # ── estatus (editable) ────────────────────────────────────────────────
        estatus_orig = "" if es_nueva else str(orig.iloc[i].get("estatus_excel") or "")
        estatus_edit = str(edited.iloc[i].get("estatus_excel") or "").strip()
        estatus_cambio = es_nueva or estatus_orig != estatus_edit

        if es_nueva:
            meta["cve_prod"] = cve_edit_cod
            meta["estatus_excel"] = estatus_edit or None
        else:
            cve_orig_lbl = str(orig.iloc[i].get("_cve_prod_label") or "")
            if cve_orig_lbl != cve_edit_lbl:
                try:
                    actualizar_cve_prod_presupuesto_ventas_ctrl(
                        id_carga=int(meta.get("id_carga") or 0),
                        producto_excel=str(meta.get("producto_excel") or ""),
                        cliente_excel=meta.get("cliente_excel") or None,
                        codigo_origen=meta.get("codigo_origen") or None,
                        company=meta.get("company") or None,
                        cve_prod=cve_edit_cod,
                    )
                    cambios += 1
                except Exception:
                    errores += 1

        # ── cambios en precio / valores mensuales ───────────────────────────
        precio_orig = 0.0 if es_nueva else float(orig.iloc[i].get("precio") or 0)
        precio_edit = float(edited.iloc[i].get("precio") or 0)
        precio_cambio = es_nueva or abs(precio_edit - precio_orig) > 1e-6

        for mes_num in range(1, 13):
            mes_name = _MESES[mes_num]
            if mes_name not in orig.columns:
                continue

            val_orig = 0.0 if es_nueva else float(orig.iloc[i].get(mes_name) or 0)
            val_edit = float(edited.iloc[i].get(mes_name) or 0)
            val_cambio = abs(val_edit - val_orig) > 1e-4

            if es_nueva and abs(val_edit) < 1e-9:
                # fila nueva: no crea registros para meses que quedaron en cero
                continue

            if not es_nueva and not val_cambio and not precio_cambio and not estatus_cambio:
                continue

            precio_final = precio_edit if precio_cambio else precio_orig
            valor_final = val_edit if val_cambio else val_orig

            if seccion == "KG":
                cantidad_kg = valor_final
                importe = round(valor_final * precio_final, 2)
            else:
                cantidad_kg = 0.0
                importe = valor_final

            id_pv = None if es_nueva else mapping.get((row_key, mes_num))

            try:
                if id_pv:
                    actualizar_presupuesto_ventas_ctrl(
                        id_presupuesto=id_pv,
                        valor=valor_final,
                        precio=precio_final,
                        cantidad_kg=cantidad_kg,
                        importe=importe,
                        estatus_excel=estatus_edit if estatus_cambio else None,
                    )
                else:
                    insertar_presupuesto_ventas_unitario_ctrl(
                        id_carga=int(meta.get("id_carga") or 0),
                        seccion=seccion,
                        region=meta.get("region") or None,
                        anio=int(meta.get("anio") or 0),
                        mes=mes_num,
                        company=meta.get("company") or None,
                        cliente_excel=meta.get("cliente_excel") or None,
                        codigo_origen=meta.get("codigo_origen") or None,
                        producto_excel=str(meta.get("producto_excel") or ""),
                        cve_prod=meta.get("cve_prod") or None,
                        estatus_excel=meta.get("estatus_excel") or None,
                        precio=precio_final,
                        valor=valor_final,
                        cantidad_kg=cantidad_kg,
                        importe=importe,
                        usuario_id=usuario_id,
                    )
                cambios += 1
            except Exception:
                errores += 1

    return cambios, errores


# ── panel: selector de carga ──────────────────────────────────────────────────

def _selector_carga() -> Optional[int]:
    df = obtener_cargas_presupuesto_ventas_ctrl(limit=50, usuario_id=_get_usuario_id())

    if df is None or df.empty:
        st.info("aún no hay presupuestos cargados")
        return None

    opciones = {
        f"{r['id_carga']} | {r['nombre_archivo']} | {r['anio']} | {r.get('version', '')}": int(r["id_carga"])
        for r in df.to_dict(orient="records")
    }
    labels = list(opciones.keys())
    default = st.session_state.get("pv_id_carga")
    idx = next((i for i, l in enumerate(labels) if opciones[l] == default), 0)

    label = st.selectbox("presupuesto", options=labels, index=idx, key="pv_select_carga")
    id_carga = opciones[label]
    st.session_state["pv_id_carga"] = id_carga
    return id_carga


# ── panel: crear presupuesto manual (sin depender de un Excel) ────────────────

def _panel_crear_manual() -> None:
    with st.expander("➕ crear presupuesto manual (sin Excel)"):
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            anio = st.number_input(
                "año", min_value=2020, max_value=2100, value=2026, step=1, key="pv_manual_anio"
            )
        with col2:
            version = st.text_input("versión", value="manual", key="pv_manual_version")
        with col3:
            comentarios = st.text_input("comentarios", value="", key="pv_manual_comentarios")

        if st.button("crear presupuesto manual", key="pv_btn_manual"):
            usuario_id = _get_usuario_id()
            if usuario_id <= 0:
                st.error("no se encontró el usuario en sesión")
                return
            try:
                id_carga = registrar_carga_presupuesto_ventas_ctrl(
                    nombre_archivo="Presupuesto manual",
                    hoja_origen="manual",
                    anio=int(anio),
                    version=version or None,
                    comentarios=comentarios or None,
                    usuario_id=usuario_id,
                )
                st.session_state["pv_id_carga"] = int(id_carga)
                st.success(f"presupuesto manual creado — id={id_carga}")
                st.rerun()
            except Exception as e:
                st.error(f"error al crear el presupuesto manual: {e}")


# ── panel: carga de Excel ─────────────────────────────────────────────────────

def _panel_carga() -> None:
    archivo = st.file_uploader(
        "sube el archivo de presupuesto ventas",
        type=["xlsx", "xls"],
        key="pv_archivo",
    )
    if archivo is None:
        return

    hojas = _obtener_hojas(archivo)
    if not hojas:
        st.error("no fue posible leer las hojas del archivo")
        return

    col1, col2, col3 = st.columns([2, 1, 2])
    with col1:
        hoja = st.selectbox("hoja", options=hojas, key="pv_hoja")
    with col2:
        anio = st.number_input("año", min_value=2020, max_value=2100, value=2026, step=1, key="pv_anio")
    with col3:
        version = st.text_input("versión", value="v1", key="pv_version")

    comentarios = st.text_input("comentarios", value="", key="pv_comentarios")

    if st.button("cargar presupuesto", type="primary", use_container_width=True, key="pv_btn_cargar"):
        usuario_id = _get_usuario_id()
        if usuario_id <= 0:
            st.error("no se encontró el usuario en sesión")
            return
        try:
            archivo.seek(0)
            res = cargar_excel_directo_presupuesto_ventas_ctrl(
                archivo=archivo,
                nombre_archivo=archivo.name,
                hoja=hoja,
                anio=int(anio),
                usuario_id=usuario_id,
                version=version or None,
                comentarios=comentarios or None,
                reemplazar=True,
            )
            st.session_state["pv_id_carga"] = int(res["id_carga"])
            st.success(
                f"cargado — id={res['id_carga']} | "
                f"tablas={res['tablas_detectadas']} | "
                f"registros={res['total_registros']}"
            )
            st.rerun()
        except Exception as e:
            st.error(f"error al cargar: {e}")


# ── panel: tabla pivot ────────────────────────────────────────────────────────

def _panel_pivot(id_carga: int) -> None:
    df_all = obtener_presupuesto_ventas_ctrl(id_carga=id_carga)
    if df_all is None:
        df_all = pd.DataFrame()

    anio_default = None
    if df_all.empty:
        # presupuesto sin registros aún (p. ej. creado de forma manual, sin Excel):
        # se arma una estructura vacía con las columnas base para permitir captura manual
        df_all = pd.DataFrame(columns=_COLS_ID + [
            "mes", "anio", "seccion", "region", "valor", "importe",
            "cantidad_kg", "precio", "cve_prod", "estatus_excel",
            "id_carga", "id_presupuesto",
        ])
        carga_meta = obtener_cargas_presupuesto_ventas_ctrl(id_carga=id_carga, limit=1)
        if carga_meta is not None and not carga_meta.empty and "anio" in carga_meta.columns:
            anio_default = int(carga_meta.iloc[0]["anio"])

    for col in ("valor", "importe", "cantidad_kg", "precio"):
        if col in df_all.columns:
            df_all[col] = pd.to_numeric(df_all[col], errors="coerce").fillna(0.0)
        else:
            df_all[col] = 0.0

    if df_all["valor"].eq(0).all() and "importe" in df_all.columns:
        df_all["valor"] = df_all["importe"]

    df_all["mes"] = pd.to_numeric(df_all["mes"], errors="coerce").fillna(0).astype(int)

    # catálogo SAE (cacheado 1 hora)
    sae_set, code_to_label, label_to_code, code_to_desc, sae_opciones = _catalogo_sae()

    if "anio" in df_all.columns and not df_all.empty:
        anio_actual = int(df_all["anio"].iloc[0])
    else:
        anio_actual = int(anio_default or pd.Timestamp.today().year)

    # se muestran siempre los 12 meses (aunque no tengan datos aún) para poder
    # capturar cualquier mes al agregar o completar un registro
    meses_todos = list(_MESES.values())

    sub_tabs = st.tabs([t[0] for t in _TABS_PIVOT])

    for tab_ui, (label, seccion, region) in zip(sub_tabs, _TABS_PIVOT):
        with tab_ui:
            mask = pd.Series(True, index=df_all.index)
            if "seccion" in df_all.columns:
                mask &= df_all["seccion"].astype(str) == seccion
            if region and "region" in df_all.columns:
                mask &= df_all["region"].astype(str) == region
            df_sec = df_all[mask].copy()

            cols_id = [c for c in _COLS_ID if c in df_all.columns]
            pivot, mapping, row_meta = _construir_pivot(df_sec, sae_set, code_to_label)

            for m in meses_todos:
                if m not in pivot.columns:
                    pivot[m] = 0.0
            meses_presentes = meses_todos

            col_order = (
                cols_id + ["_status", "_cve_prod_label", "estatus_excel", "precio"] + meses_presentes
            )
            pivot = pivot[[c for c in col_order if c in pivot.columns]]
            pivot["_nueva"] = False

            ver_key = f"pv_ver_{seccion}_{region}_{id_carga}"
            nuevas_key = f"pv_nuevas_{seccion}_{region}_{id_carga}"
            st.session_state.setdefault(ver_key, 0)
            st.session_state.setdefault(nuevas_key, [])

            if st.session_state[nuevas_key]:
                pivot = pd.concat(
                    [pivot, pd.DataFrame(st.session_state[nuevas_key])], ignore_index=True
                )

            decimales = 2 if seccion == "USD" else 4

            if st.button("➕ agregar registro", key=f"pv_add_{seccion}_{region}_{id_carga}"):
                fila = {c: "" for c in cols_id}
                fila.update({
                    "_status": "🟠",
                    "_cve_prod_label": "",
                    "estatus_excel": "",
                    "precio": 0.0,
                    "_nueva": True,
                })
                for m in meses_presentes:
                    fila[m] = 0.0
                st.session_state[nuevas_key].append(fila)
                st.session_state[ver_key] += 1
                st.rerun()

            if pivot.empty:
                st.info(f"sin datos para {label} — usa \"➕ agregar registro\" para capturar uno")
                continue

            editable_si_nueva = JsCode(
                "function(params) { return !!(params.data && params.data._nueva); }"
            )
            # producto: editable solo en filas nuevas y mientras no se haya elegido cve_prod
            # (al elegir cve_prod, el nombre se llena automáticamente y se bloquea)
            editable_producto_si_nueva = JsCode(
                "function(params) { return !!(params.data && params.data._nueva"
                " && !params.data._cve_prod_label); }"
            )

            gb = GridOptionsBuilder.from_dataframe(pivot)
            gb.configure_default_column(editable=False, resizable=True, width=100)
            gb.configure_selection("multiple", use_checkbox=True, header_checkbox=True)

            for c in cols_id:
                editable_col = editable_producto_si_nueva if c == "producto_excel" else editable_si_nueva
                gb.configure_column(
                    c, headerName=c.replace("_excel", "").replace("_", " "),
                    editable=editable_col, width=130,
                )

            gb.configure_column("_nueva", hide=True)
            gb.configure_column(
                "_status", headerName="SAE", editable=False, width=70,
                headerTooltip="🟢 producto en catálogo SAE  |  🟠 no encontrado en SAE",
            )
            gb.configure_column(
                "_cve_prod_label",
                headerName="cve prod",
                editable=True,
                width=200,
                cellEditor="agSelectCellEditor",
                cellEditorParams={"values": sae_opciones},
            )
            gb.configure_column("estatus_excel", headerName="status", editable=True, width=110)
            gb.configure_column(
                "precio",
                headerName="precio USD/kg",
                editable=True,
                width=110,
                type=["numericColumn"],
                cellEditor="agNumberCellEditor",
                valueFormatter=_value_formatter_js(4),
            )
            for m in meses_presentes:
                gb.configure_column(
                    m,
                    headerName=m.upper(),
                    editable=True,
                    width=90,
                    type=["numericColumn"],
                    cellEditor="agNumberCellEditor",
                    cellStyle=_CELL_STYLE_VALORES,
                    valueFormatter=_value_formatter_js(decimales),
                )

            st.caption(
                "🟢 en SAE  |  🟠 no en SAE  |  🟩 valor positivo  |  🟥 valor negativo "
                " — edita **cve prod** o **status** para actualizarlos  |  las filas nuevas permiten editar"
                " company/cliente/código/producto  |  selecciona filas con el checkbox para eliminarlas"
            )

            grid_response = AgGrid(
                pivot,
                gridOptions=gb.build(),
                update_mode=GridUpdateMode.VALUE_CHANGED | GridUpdateMode.SELECTION_CHANGED,
                data_return_mode=DataReturnMode.AS_INPUT,
                fit_columns_on_grid_load=False,
                allow_unsafe_jscode=True,
                height=min(56 + len(pivot) * 35, 680),
                key=f"pv_pivot_{seccion}_{region}_{id_carga}_{st.session_state[ver_key]}",
            )
            edited = pd.DataFrame(grid_response.get("data", []))

            # al elegir cve_prod en una fila nueva, se llena "producto" con el
            # nombre del producto y ese campo queda bloqueado (ver editable_producto_si_nueva)
            if not edited.empty and "_cve_prod_label" in edited.columns and "producto_excel" in edited.columns:
                hubo_cambio = False
                for i in range(len(edited)):
                    if not bool(edited.iloc[i].get("_nueva")):
                        continue
                    lbl = str(edited.iloc[i].get("_cve_prod_label") or "").strip()
                    if not lbl:
                        continue
                    code = label_to_code.get(lbl, lbl)
                    nombre = code_to_desc.get(code, "")
                    if nombre and str(edited.iloc[i].get("producto_excel") or "") != nombre:
                        edited.at[i, "producto_excel"] = nombre
                        hubo_cambio = True
                    if "_status" in edited.columns and code in sae_set:
                        edited.at[i, "_status"] = "🟢"

                if hubo_cambio:
                    mask_nueva = edited["_nueva"].apply(lambda v: bool(v) if pd.notna(v) else False)
                    st.session_state[nuevas_key] = edited[mask_nueva].to_dict("records")
                    st.session_state[ver_key] += 1
                    st.rerun()

            seleccionadas = grid_response.get("selected_rows")
            if seleccionadas is None:
                seleccionadas = []
            elif isinstance(seleccionadas, pd.DataFrame):
                seleccionadas = seleccionadas.to_dict("records")

            col_save, col_del = st.columns(2)
            with col_save:
                if st.button(
                    "💾 guardar cambios",
                    type="primary",
                    use_container_width=True,
                    key=f"pv_save_{seccion}_{region}_{id_carga}",
                ):
                    cambios, errores = _guardar_pivot(
                        pivot, edited, mapping, row_meta,
                        seccion, region, cols_id, _get_usuario_id(), label_to_code,
                        id_carga, anio_actual,
                    )
                    if cambios:
                        st.success(f"guardados {cambios} registros")
                        st.session_state[nuevas_key] = []
                        st.session_state[ver_key] += 1
                        st.rerun()
                    if errores:
                        st.error(f"{errores} filas con error")
                    if not cambios and not errores:
                        st.info("sin cambios detectados")
            with col_del:
                if st.button(
                    "🗑️ eliminar seleccionados",
                    use_container_width=True,
                    disabled=not seleccionadas,
                    key=f"pv_del_{seccion}_{region}_{id_carga}",
                ):
                    registros_borrados = 0
                    filas_bd = 0
                    nuevas_borradas = [
                        tuple(str(f.get(c) or "").strip() for c in cols_id)
                        for f in seleccionadas if f.get("_nueva")
                    ]
                    for fila in seleccionadas:
                        if fila.get("_nueva"):
                            continue
                        try:
                            n = eliminar_registro_presupuesto_ventas_ctrl(
                                id_carga=id_carga,
                                seccion=seccion,
                                region=region,
                                producto_excel=str(fila.get("producto_excel") or ""),
                                cliente_excel=fila.get("cliente_excel") or None,
                                codigo_origen=fila.get("codigo_origen") or None,
                                company=fila.get("company") or None,
                            )
                            filas_bd += n
                            if n:
                                registros_borrados += 1
                        except Exception:
                            pass

                    if nuevas_borradas:
                        st.session_state[nuevas_key] = [
                            r for r in st.session_state[nuevas_key]
                            if tuple(str(r.get(c) or "").strip() for c in cols_id) not in nuevas_borradas
                        ]

                    if registros_borrados or nuevas_borradas:
                        st.success(
                            f"{registros_borrados} registro(s) eliminados ({filas_bd} filas de detalle)"
                            + (f", {len(nuevas_borradas)} fila(s) nueva(s) descartadas" if nuevas_borradas else "")
                        )
                        st.session_state[ver_key] += 1
                        st.rerun()
                    else:
                        st.info("no se eliminó nada")


# ── panel: gestión de cargas ──────────────────────────────────────────────────

def _panel_gestionar_cargas() -> None:
    df = obtener_cargas_presupuesto_ventas_ctrl(limit=200, usuario_id=_get_usuario_id())

    if df is None or df.empty:
        st.info("no hay cargas registradas")
        return

    cols_mostrar = [c for c in
                    ["id_carga", "nombre_archivo", "anio", "version", "estatus", "comentarios", "created_at"]
                    if c in df.columns]
    st.dataframe(df[cols_mostrar], use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("#### eliminar carga")
    st.caption("esto borra la carga, sus registros de presupuesto y el staging asociado de forma permanente")

    opciones = {
        f"{r['id_carga']} | {r['nombre_archivo']} | {r['anio']} | {r.get('version', '')}": int(r["id_carga"])
        for r in df.to_dict(orient="records")
    }
    label = st.selectbox("selecciona la carga a eliminar", options=list(opciones.keys()), key="gc_select")
    id_sel = opciones[label]

    confirmar = st.checkbox(f"confirmo que quiero eliminar la carga {id_sel}", key="gc_confirmar")

    if st.button("🗑️ eliminar carga", type="primary", disabled=not confirmar, key="gc_btn_eliminar"):
        try:
            eliminar_carga_completa_presupuesto_ventas_ctrl(id_sel)
            st.success(f"carga {id_sel} eliminada correctamente")
            if st.session_state.get("pv_id_carga") == id_sel:
                del st.session_state["pv_id_carga"]
            st.rerun()
        except Exception as e:
            st.error(f"error al eliminar: {e}")


# ── entry point ───────────────────────────────────────────────────────────────

def mostrar_modulo_presupuesto_ventas() -> None:
    st.subheader("presupuesto de ventas")

    tab_carga, tab_tabla, tab_cargas = st.tabs(["📂 cargar Excel", "📊 tabla presupuesto", "🗑️ gestionar cargas"])

    with tab_carga:
        with st.container(border=True):
            _panel_carga()

    with tab_tabla:
        _panel_crear_manual()
        id_carga = _selector_carga()
        if id_carga is not None:
            _panel_pivot(id_carga)

    with tab_cargas:
        _panel_gestionar_cargas()
