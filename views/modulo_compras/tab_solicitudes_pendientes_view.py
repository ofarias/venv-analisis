from datetime import date

import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, DataReturnMode, GridOptionsBuilder, JsCode

from controllers.compras_solicitudes_controller import (
    obtener_solicitudes_pendientes_usuario_ctrl,
    obtener_detalle_solicitud_compra_ctrl,
    obtener_cabecera_solicitud_compra_ctrl,
    obtener_cabecera_solicitud_estandar_ctrl,
    obtener_detalle_solicitud_estandar_ctrl,
    obtener_detalle_solicitud_mp_inventario_ctrl,
    enviar_solicitud_compra_ctrl,
    eliminar_solicitud_compra_ctrl,
    actualizar_detalle_mp_inventario_ctrl,
    eliminar_detalle_mp_inventario_ctrl,
    listar_proveedores_mp_sae_ctrl,
    enviar_lineas_mp_inventario_ctrl,
)

_VALUE_FORMATTER_MILES_JS = JsCode("""
function(params) {
    if (params.value === null || params.value === undefined || params.value === '') return '';
    return Number(params.value).toLocaleString('en-US', {minimumFractionDigits: 0, maximumFractionDigits: 0});
}
""")

_VALUE_FORMATTER_USD_JS = JsCode("""
function(params) {
    if (params.value === null || params.value === undefined || params.value === '') return '';
    return '$' + Number(params.value).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
}
""")

_MESES = {1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
          7: "jul", 8: "ago", 9: "sep", 10: "oct", 11: "nov", 12: "dic"}


def _get_usuario_actual():
    return st.session_state.get("usuario") or {}


def _get_solicitante_actual() -> str:
    usuario = _get_usuario_actual()
    return (
        str(usuario.get("nombre") or "").strip()
        or str(usuario.get("username") or "").strip()
        or str(usuario.get("email") or "").strip()
        or ""
    )


def _mostrar_detalle_materias_primas(id_solicitud: int):
    detalle = obtener_detalle_solicitud_compra_ctrl(id_solicitud)

    if detalle.empty:
        st.info("esta solicitud no tiene detalle.")
        return

    cols_det = [
        "cliente",
        "cliente_sae",
        "numero_pedido",
        "persona_solicita",
        "producto",
        "producto_sae",
        "cantidad",
        "unidad_empaque",
        "fecha_entrega",
        "direccion_entrega",
        "observaciones",
    ]
    cols_det = [c for c in cols_det if c in detalle.columns]

    st.dataframe(
        detalle[cols_det],
        use_container_width=True,
        hide_index=True,
    )


def _ventana_meses_actual(n: int = 3) -> list[int]:
    """Mes actual + (n-1) siguientes (con vuelta de año) — mismo criterio
    que Compras -> Demanda (Forecast) para la ventana de compra, para que
    Pendientes siempre muestre el mismo contexto sin importar qué meses
    haya guardados en el detalle."""
    hoy = date.today()
    meses, anio, mes = [], hoy.year, hoy.month
    for _ in range(n):
        meses.append(mes)
        mes += 1
        if mes > 12:
            mes = 1
            anio += 1
    return meses


def _pivotear_detalle_mp_inventario(detalle: pd.DataFrame, meses_ventana: list[int]) -> list[dict]:
    """Una fila por materia prima: Cant. Requerida fija a la ventana de 3
    meses (mes actual + 2 siguientes, siempre, en 0 si no hay nada ese mes)
    + Total Requerido + UNA sola Cantidad Solicitada editable (la suma de lo
    ya guardado para ese producto, sin importar en qué mes quedó) +
    Resultado. "_ids" guarda TODOS los id_detalle_mp_inv de ese producto en
    esta solicitud, para poder colapsarlos en uno solo al guardar."""
    filas = []
    for cve_mp, grupo in detalle.groupby("cve_mp", sort=False):
        proveedor_actual = (
            str(grupo["proveedor_nombre"].dropna().iloc[0])
            if "proveedor_nombre" in grupo.columns and grupo["proveedor_nombre"].notna().any()
            else ""
        )
        precio_usd_actual = (
            float(grupo["precio_usd"].dropna().iloc[0])
            if "precio_usd" in grupo.columns and grupo["precio_usd"].notna().any()
            else 0.0
        )
        fila = {
            "cve MP": cve_mp,
            "Materia Prima": str(grupo["mp_nombre"].iloc[0] or ""),
            "Línea": str(grupo["linea"].iloc[0] or "") or "-",
            "Proveedor": proveedor_actual,
            "Precio USD": round(precio_usd_actual, 4),
        }
        total_req = 0.0
        for mes in meses_ventana:
            mn = _MESES.get(mes, str(mes)).upper()
            fila_mes = grupo[grupo["mes"] == mes]
            req = float(fila_mes["cantidad_requerida_kg"].sum()) if not fila_mes.empty else 0.0
            fila[f"{mn} Cant. Requerida"] = round(req, 2)
            total_req += req
        total_sol = float(grupo["cantidad_kg"].sum())
        fila["Total Requerido"] = round(total_req, 2)
        fila["Cantidad Solicitada"] = round(total_sol, 2)
        fila["Resultado"] = round(total_sol - total_req, 2)
        fila["Costo Total USD"] = round(total_sol * precio_usd_actual, 2)
        folios = [str(f) for f in grupo["folio_sae"].dropna().unique() if str(f).strip()]
        fila["Orden SAE"] = ", ".join(folios) if folios else "—"
        obs = " | ".join(str(o) for o in grupo["observaciones"].dropna().unique() if str(o).strip())
        fila["Trazabilidad"] = obs
        fila["_ids"] = [int(i) for i in grupo["id_detalle_mp_inv"].dropna().tolist()]
        filas.append(fila)
    return filas


def _mostrar_detalle_mp_inventario(id_solicitud: int, editable: bool = False):
    """Pivotea el detalle (una fila por cve_mp×mes en la BD) a una fila por
    materia prima — ver _pivotear_detalle_mp_inventario.

    `editable=True` (solo mientras la solicitud sigue en 'captura'): deja
    cambiar la **Cantidad Solicitada** (un solo total por producto —
    Resultado se recalcula solo) y quitar materias primas completas de la
    solicitud desmarcando su checkbox, ambos hasta presionar "guardar
    cambios". Al guardar, los renglones mensuales de un producto que sigue
    incluido se colapsan en uno solo (ya no se distingue por mes — la
    decisión de compra es un total, el detalle mensual era solo para saber
    cuánto se necesitaba)."""
    detalle = obtener_detalle_solicitud_mp_inventario_ctrl(id_solicitud)

    if detalle.empty:
        st.info("esta solicitud no tiene detalle de materia prima.")
        return

    versiones = detalle["id_version_forecast"].dropna().unique() if "id_version_forecast" in detalle.columns else []
    if len(versiones) > 0:
        lista_versiones = ", ".join(str(int(v)) for v in versiones)
        st.caption(f"generado desde forecast versión(es): {lista_versiones}")

    detalle = detalle.copy()
    detalle["cantidad_kg"] = pd.to_numeric(detalle["cantidad_kg"], errors="coerce").fillna(0.0)
    if "cantidad_requerida_kg" in detalle.columns:
        detalle["cantidad_requerida_kg"] = pd.to_numeric(detalle["cantidad_requerida_kg"], errors="coerce")
    else:
        detalle["cantidad_requerida_kg"] = None
    if "linea" not in detalle.columns:
        detalle["linea"] = None
    if "precio_usd" in detalle.columns:
        detalle["precio_usd"] = pd.to_numeric(detalle["precio_usd"], errors="coerce")
    else:
        detalle["precio_usd"] = None
    if "estatus_linea" in detalle.columns:
        detalle["estatus_linea"] = detalle["estatus_linea"].fillna("captura")
    else:
        detalle["estatus_linea"] = "captura"

    meses_ventana = _ventana_meses_actual()
    meses_ventana_txt = ", ".join(_MESES[m].upper() for m in meses_ventana)
    st.caption(f"Cant. Requerida mostrada para: {meses_ventana_txt}")

    if not editable:
        filas = _pivotear_detalle_mp_inventario(detalle, meses_ventana)
        df_show = pd.DataFrame(filas).drop(columns=["_ids"])
        st.dataframe(df_show, use_container_width=True, hide_index=True)
        return

    # tablero de control: solo las líneas que todavía no se enviaron a
    # autorizar — las ya enviadas/autorizadas/rechazadas desaparecen de esta
    # cola (se revisan en Autorizaciones), hasta que no quede ninguna.
    detalle_pendiente = detalle[detalle["estatus_linea"] == "captura"]
    if detalle_pendiente.empty:
        st.success("todas las líneas de esta solicitud ya se enviaron a autorización.")
        return

    filas = _pivotear_detalle_mp_inventario(detalle_pendiente, meses_ventana)
    col_req = [f"{_MESES[m].upper()} Cant. Requerida" for m in meses_ventana]
    ids_por_fila = {f["cve MP"]: f["_ids"] for f in filas}

    # el detalle se vuelve a leer de la BD en cada rerun — sin cachear la
    # edición en session_state, "Resultado" (y la propia Cantidad
    # Solicitada editada) se perdía en el rerun que dispara
    # cellValueChanged y volvía a mostrar el valor original guardado.
    preview_key = f"pend_mp_inv_preview_{id_solicitud}"
    if preview_key not in st.session_state:
        st.session_state[preview_key] = pd.DataFrame(filas).drop(columns=["_ids"])
    df_preview = st.session_state[preview_key]

    gb = GridOptionsBuilder.from_dataframe(df_preview)
    gb.configure_grid_options(autoSizeStrategy=None)
    gb.configure_default_column(
        editable=False, resizable=True, filter=True, sortable=True,
        wrapHeaderText=True, autoHeaderHeight=True,
    )
    gb.configure_side_bar()
    # el checkbox aquí significa "marcar para eliminar" (no "mantener") —
    # arranca sin nada marcado, y el botón "eliminar seleccionadas" es la
    # única acción que lo usa; "guardar cambios" ya no depende de esto.
    gb.configure_selection(
        selection_mode="multiple", use_checkbox=True, header_checkbox=True,
    )
    gb.configure_column("cve MP", pinned="left", width=110)
    gb.configure_column("Materia Prima", pinned="left", width=200)
    gb.configure_column("Línea", pinned="left", width=120)
    proveedores_sae = listar_proveedores_mp_sae_ctrl()
    cve_por_proveedor = {p["nombre"]: p["cve_prov"] for p in proveedores_sae}
    nombres_proveedores = list(cve_por_proveedor.keys())
    gb.configure_column(
        "Proveedor", pinned="left", width=180, editable=True,
        cellEditor="agSelectCellEditor",
        cellEditorParams={"values": [""] + nombres_proveedores},
        cellStyle=JsCode("function(p){return {backgroundColor:'#fff8e1'};}"),
    )
    gb.configure_column(
        "Precio USD", pinned="left", width=130, editable=True,
        type=["numericColumn"], cellEditor="agNumberCellEditor",
        valueFormatter=_VALUE_FORMATTER_USD_JS,
        cellStyle=JsCode("function(p){return {backgroundColor:'#fff8e1'};}"),
    )
    for c in col_req:
        gb.configure_column(c, type=["numericColumn"], width=120, valueFormatter=_VALUE_FORMATTER_MILES_JS)
    gb.configure_column("Total Requerido", type=["numericColumn"], width=130, valueFormatter=_VALUE_FORMATTER_MILES_JS)
    gb.configure_column(
        "Cantidad Solicitada", type=["numericColumn"], width=140, editable=True,
        cellEditor="agNumberCellEditor", valueFormatter=_VALUE_FORMATTER_MILES_JS,
        cellStyle=JsCode("function(p){return {backgroundColor:'#fff8e1'};}"),
    )
    gb.configure_column(
        "Resultado", type=["numericColumn"], width=110, valueFormatter=_VALUE_FORMATTER_MILES_JS,
        # calculado en el navegador a partir de la fila — se recalcula solo
        # al editar Cantidad Solicitada, sin ida y vuelta a Python
        valueGetter=JsCode("""
        function(params) {
            var sol = Number(params.data['Cantidad Solicitada']) || 0;
            var req = Number(params.data['Total Requerido']) || 0;
            return Math.round((sol - req) * 100) / 100;
        }
        """),
    )
    gb.configure_column(
        "Costo Total USD", type=["numericColumn"], width=140, valueFormatter=_VALUE_FORMATTER_USD_JS,
        valueGetter=JsCode("""
        function(params) {
            var sol = Number(params.data['Cantidad Solicitada']) || 0;
            var precio = Number(params.data['Precio USD']) || 0;
            return Math.round(sol * precio * 100) / 100;
        }
        """),
    )
    gb.configure_column("Trazabilidad", width=280, wrapText=True, autoHeight=True)

    cols_orden = (
        ["cve MP", "Materia Prima", "Línea", "Proveedor", "Precio USD"] + col_req
        + ["Total Requerido", "Cantidad Solicitada", "Resultado", "Costo Total USD", "Orden SAE", "Trazabilidad"]
    )

    st.caption(
        "✏️ edita **Cantidad Solicitada** y presiona \"guardar cambios\" — o marca el checkbox "
        "de una o varias materias primas para \"eliminar seleccionadas\" (las quita de la "
        "solicitud) o \"enviar seleccionadas a autorizar\" (las saca de esta cola y, según las "
        "reglas de autorización, se autorizan solas o se mandan a quien corresponda). Puedes ir "
        "enviando de unas en unas hasta vaciar la lista."
    )
    grid_resp = AgGrid(
        df_preview[cols_orden],
        gridOptions=gb.build(),
        update_on=[("cellValueChanged", 600)],
        data_return_mode=DataReturnMode.AS_INPUT,
        fit_columns_on_grid_load=False,
        allow_unsafe_jscode=True,
        enable_enterprise_modules=True,
        height=min(56 + len(df_preview) * 35, 450),
        key=f"pend_mp_inv_grid_{id_solicitud}",
    )

    df_actual = pd.DataFrame(grid_resp.get("data", []))
    if not df_actual.empty:
        st.session_state[preview_key] = df_actual

    seleccionadas = grid_resp.get("selected_rows")
    cves_marcadas = (
        set(seleccionadas["cve MP"].astype(str)) if isinstance(seleccionadas, pd.DataFrame) else set()
    )

    col_g1, col_g2, col_g3 = st.columns(3)
    with col_g1:
        if st.button(
            "💾 guardar cambios", type="primary", use_container_width=True,
            key=f"pend_mp_inv_guardar_{id_solicitud}",
        ):
            cambios = []
            for _, r in df_actual.iterrows():
                cve = str(r["cve MP"])
                ids_fila = ids_por_fila.get(cve, [])
                if not ids_fila:
                    continue
                # colapsa todos los renglones mensuales de este producto en
                # el primero — la Cantidad Solicitada ya es un total único,
                # no tiene sentido seguir repartida por mes
                total_requerido = float(pd.to_numeric(r.get("Total Requerido"), errors="coerce") or 0.0)
                cantidad_solicitada = pd.to_numeric(r.get("Cantidad Solicitada"), errors="coerce")
                proveedor_nombre = str(r.get("Proveedor") or "").strip() or None
                precio_usd = pd.to_numeric(r.get("Precio USD"), errors="coerce")
                cambios.append({
                    "id_detalle_mp_inv": ids_fila[0],
                    "cantidad_kg": float(cantidad_solicitada) if pd.notna(cantidad_solicitada) else 0.0,
                    "cantidad_requerida_kg": total_requerido,
                    "mes": meses_ventana[0],
                    "proveedor_nombre": proveedor_nombre,
                    "cve_proveedor": cve_por_proveedor.get(proveedor_nombre) if proveedor_nombre else None,
                    "precio_usd": float(precio_usd) if pd.notna(precio_usd) and precio_usd > 0 else None,
                })
                if len(ids_fila) > 1:
                    eliminar_detalle_mp_inventario_ctrl(ids_fila[1:])

            if cambios:
                ok_count, fail_count = actualizar_detalle_mp_inventario_ctrl(cambios)
                st.session_state.pop(preview_key, None)
                if fail_count:
                    st.warning(f"{ok_count} renglón(es) actualizados, {fail_count} no se pudieron actualizar.")
                else:
                    st.success("cambios guardados.")
                st.rerun()
            else:
                st.info("sin cambios para guardar.")

    with col_g2:
        if st.button(
            "🗑️ eliminar seleccionadas", use_container_width=True,
            disabled=not cves_marcadas,
            key=f"pend_mp_inv_eliminar_{id_solicitud}",
        ):
            ids_a_eliminar = [i for cve in cves_marcadas for i in ids_por_fila.get(cve, [])]
            ok_count, fail_count = eliminar_detalle_mp_inventario_ctrl(ids_a_eliminar)
            st.session_state.pop(preview_key, None)
            if fail_count:
                st.warning(f"{ok_count} renglón(es) eliminados, {fail_count} no se pudieron eliminar.")
            else:
                st.success(f"{ok_count} materia(s) prima(s) eliminada(s) de la solicitud.")
            st.rerun()

    with col_g3:
        if st.button(
            "📤 enviar seleccionadas a autorizar", use_container_width=True,
            disabled=not cves_marcadas,
            key=f"pend_mp_inv_enviar_lineas_{id_solicitud}",
        ):
            ids_a_enviar = [i for cve in cves_marcadas for i in ids_por_fila.get(cve, [])]
            token = st.session_state.get("microsoft_token")
            ok, mensaje = enviar_lineas_mp_inventario_ctrl(ids_a_enviar, token=token)
            st.session_state.pop(preview_key, None)
            if ok:
                st.success(mensaje)
            else:
                st.error(mensaje)
            st.rerun()


def _mostrar_accion_generar_sae(cab: dict):
    """Punto de enganche para la Fase 2 del plan (generar la Orden de Compra
    real en SAE, tabla COMPO01/PAR_COMPO01) — todavía no implementada: faltan
    por confirmar proveedor, precio/costo por línea y la fórmula exacta de
    CVE_DOC/FOLIO antes de escribir el INSERT (ver plan). Mientras tanto solo
    informa el estatus, sin ofrecer un botón que no hace nada real."""
    estatus_actual = str(cab.get("estatus") or "").strip().lower()
    if estatus_actual != "autorizada":
        return

    usuario = st.session_state.get("usuario") or {}
    roles = usuario.get("roles", [])
    if not ("SuperAdmin" in roles or "forecastAdmin" in roles):
        return

    st.info(
        "✅ solicitud autorizada — pendiente generarla como Orden de Compra en SAE. "
        "Esa parte todavía no está automatizada en la app (falta confirmar proveedor, "
        "precio/costo y numeración con SAE); mientras tanto, créala manualmente en SAE "
        "con estos datos y notifícalo."
    )


def _mostrar_detalle_estandar(id_solicitud: int):
    cab_est = obtener_cabecera_solicitud_estandar_ctrl(id_solicitud)

    if not cab_est:
        st.info("esta solicitud no tiene cabecera estándar.")
        return

    st.markdown("#### detalle del formato estándar")

    c1, c2, c3 = st.columns(3)

    with c1:
        st.text_input("folio", value=str(cab_est.get("folio") or ""), disabled=True)
        st.text_input("departamento", value=str(cab_est.get("departamento") or ""), disabled=True)

    with c2:
        st.text_input("fecha elaboración", value=str(cab_est.get("fecha_elaboracion") or ""), disabled=True)
        st.text_input("forma de pago", value=str(cab_est.get("forma_pago") or ""), disabled=True)

    with c3:
        st.text_area(
            "observaciones",
            value=str(cab_est.get("observaciones") or ""),
            disabled=True,
            height=100,
        )

    detalle = obtener_detalle_solicitud_estandar_ctrl(id_solicitud)

    if detalle.empty:
        st.info("esta solicitud no tiene detalle estándar.")
        return

    cols_det = [
        "cantidad",
        "descripcion_producto_servicio",
        "unidad_negocio_sigla",
        "porcentaje",
        "fecha_requerida",
        "proveedor",
        "precio_unitario",
        "costo_total_sin_iva",
    ]
    cols_det = [c for c in cols_det if c in detalle.columns]

    st.dataframe(
        detalle[cols_det],
        use_container_width=True,
        hide_index=True,
    )



def mostrar_tab_solicitudes_pendientes():
    usuario = _get_usuario_actual()
    roles = usuario.get("roles", [])
    es_superadmin = "SuperAdmin" in roles

    st.subheader("todas las solicitudes pendientes" if es_superadmin else "mis solicitudes pendientes")

    solicitante_actual = _get_solicitante_actual()

    if not solicitante_actual:
        st.warning("no se pudo identificar el usuario actual.")
        return

    df = obtener_solicitudes_pendientes_usuario_ctrl(solicitante_actual, ver_todas=es_superadmin)

    if df.empty:
        st.info("no hay solicitudes pendientes." if es_superadmin else "no tienes solicitudes pendientes.")
        return

    cols_show = [
        "id_solicitud_compra",
        "fecha_solicitud",
        "tipo_compra",
        "solicitante",
        "estatus",
        "total_renglones",
        "observaciones_generales",
        "created_at",
    ]
    if not es_superadmin:
        cols_show.remove("solicitante")
    cols_show = [c for c in cols_show if c in df.columns]

    st.dataframe(
        df[cols_show],
        use_container_width=True,
        hide_index=True,
    )

    st.divider()
    st.markdown("### detalle de solicitud")

    if es_superadmin:
        opciones = {
            f'{int(row["id_solicitud_compra"])} - {str(row["solicitante"] or "").strip()} - {str(row["tipo_compra"] or "").strip()} - {str(row["estatus"] or "").strip()}': int(row["id_solicitud_compra"])
            for _, row in df.iterrows()
        }
    else:
        opciones = {
            f'{int(row["id_solicitud_compra"])} - {str(row["tipo_compra"] or "").strip()} - {str(row["estatus"] or "").strip()}': int(row["id_solicitud_compra"])
            for _, row in df.iterrows()
        }

    seleccion = st.selectbox(
        "selecciona una solicitud",
        options=list(opciones.keys()),
        key="scp_pendientes_sel",
    )

    id_solicitud = opciones[seleccion]

    cab = obtener_cabecera_solicitud_compra_ctrl(id_solicitud)
    estatus_actual = str(cab.get("estatus") or "").strip().lower()
    tipo_formulario = str(cab.get("tipo_formulario") or "").strip().upper()

    c1, c2, c3, c4 = st.columns([2, 2, 2, 4])

    with c1:
        # Materia Prima (Inventario) ya no se envía de un solo golpe — se
        # va enviando línea por línea desde el detalle de abajo (ver
        # _mostrar_detalle_mp_inventario), así que este botón no aplica ahí.
        if tipo_formulario == "MP_INV":
            st.button(
                "enviar solicitud", use_container_width=True, disabled=True,
                key=f"btn_enviar_sol_compra_{id_solicitud}",
                help="Materia Prima (Inventario) se envía línea por línea desde el detalle de abajo.",
            )
        elif st.button(
            "enviar solicitud",
            use_container_width=True,
            disabled=(estatus_actual != "captura"),
            key=f"btn_enviar_sol_compra_{id_solicitud}",
        ):
            token = st.session_state.get("microsoft_token")
            ok, mensaje = enviar_solicitud_compra_ctrl(id_solicitud, token=token)

            if ok:
                st.success(mensaje)
                st.rerun()
            else:
                st.error(mensaje)

    with c2:
        if st.button(
            "eliminar solicitud",
            use_container_width=True,
            disabled=(estatus_actual != "captura"),
            key=f"btn_eliminar_sol_compra_{id_solicitud}",
        ):
            ok, mensaje = eliminar_solicitud_compra_ctrl(id_solicitud)

            if ok:
                st.success(mensaje)
                st.rerun()
            else:
                st.error(mensaje)

    with c3:
        st.caption(f"estatus actual: {cab.get('estatus', '')}")

    st.markdown("#### cabecera general")
    g1, g2, g3 = st.columns(3)

    with g1:
        st.text_input("id solicitud", value=str(cab.get("id_solicitud_compra") or ""), disabled=True)
        st.text_input("tipo de compra", value=str(cab.get("tipo_compra") or ""), disabled=True)

    with g2:
        st.text_input("fecha solicitud", value=str(cab.get("fecha_solicitud") or ""), disabled=True)
        st.text_input("solicitante", value=str(cab.get("solicitante") or ""), disabled=True)

    with g3:
        st.text_input("estatus", value=str(cab.get("estatus") or ""), disabled=True)
        st.text_area(
            "observaciones generales",
            value=str(cab.get("observaciones_generales") or ""),
            disabled=True,
            height=90,
        )

    st.divider()

    if tipo_formulario == "MP":
        st.markdown("#### detalle de materias primas")
        _mostrar_detalle_materias_primas(id_solicitud)
    elif tipo_formulario == "MP_INV":
        st.markdown("#### detalle de materia prima (inventario)")
        _mostrar_detalle_mp_inventario(id_solicitud, editable=(estatus_actual == "captura"))
        _mostrar_accion_generar_sae(cab)
    else:
        _mostrar_detalle_estandar(id_solicitud)