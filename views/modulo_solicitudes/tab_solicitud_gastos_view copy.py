# views/modulo_solicitudes/tab_solicitud_gastos_view.py
from __future__ import annotations

import re
from typing import Optional
from datetime import datetime, date, time, timedelta

import pandas as pd
import streamlit as st

from controllers.solicitudes_controller import (
    get_usuarios_activos_ctrl,
    crear_solicitud_ctrl,
    actualizar_cabecera_ctrl,
    listar_solicitudes_ctrl,
    get_solicitud_ctrl,
    get_detalle_ctrl,
    guardar_detalle_ctrl,
    cambiar_estatus_ctrl,
    get_conceptos_gasto_ctrl,
    get_datoscfd_by_uuid_ctrl,
    uuid_ya_usado_ctrl,
    get_formas_pago_usuario_ctrl,
)

from controllers.datoscfd_controller import registrar_cfdi_desde_xml
from models.datoscfd_model import guardar_pdf_datoscfd, extraer_uuid_desde_pdf


UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
_HYPHENS = "\u2010\u2011\u2012\u2013\u2014\u2212"


def _normaliza_texto_uuid(s: str) -> str:
    if not s:
        return ""
    s = str(s).strip()
    for h in _HYPHENS:
        s = s.replace(h, "-")
    s = re.sub(r"\s+", "", s)
    return s


def _uuid_en_texto(texto: str) -> Optional[str]:
    t = _normaliza_texto_uuid(texto)
    m = UUID_RE.search(t)
    return m.group(0).upper() if m else None


def _uuid_en_nombre(nombre: str) -> Optional[str]:
    return _uuid_en_texto(nombre or "")


def _to_time(v):
    if v is None or v == "":
        return None
    if isinstance(v, time):
        return v
    if isinstance(v, datetime):
        return v.time()
    if isinstance(v, timedelta):
        total = int(v.total_seconds())
        hh = (total // 3600) % 24
        mm = (total % 3600) // 60
        ss = total % 60
        return time(hh, mm, ss)
    if isinstance(v, str):
        s = v.strip()
        try:
            parts = s.split(":")
            hh = int(parts[0])
            mm = int(parts[1]) if len(parts) > 1 else 0
            ss = int(parts[2]) if len(parts) > 2 else 0
            return time(hh, mm, ss)
        except Exception:
            return None
    return None


def _get_usuario_actual():
    u = st.session_state.get("usuario")
    if not u:
        return None
    return u


def _hora_default(hh: int, mm: int) -> time:
    return time(hour=hh, minute=mm)


def _norm_uuid(x) -> str:
    return ("" if x is None else str(x)).strip().upper()


def _to_float(x) -> float:
    try:
        if x is None or str(x).strip() == "":
            return 0.0
        return float(x)
    except Exception:
        return 0.0


def _to_int(x) -> int:
    try:
        if x is None or str(x).strip() == "":
            return 0
        return int(float(x))
    except Exception:
        return 0


def _defaults_row():
    return {
        "id": None,
        "fecha_gasto": date.today(),
        "concepto": "",
        "uuid": "",
        "observaciones": "",
        "cantidad": 1,
        "precio_unitario": 0,
        "importe": 0,
        "usuario_forma_pago_id": None,
        "pagado_con": "",
        #"impuesto1": 0,
        #"impuesto2": 0,
        #"impuesto3": 0,
        #"impuesto4": 0,
        #"moneda": "mxn",
        "proveedor": "",
        "receptor": "",
        "serie": "",
        "folio": "",
        "version": "",
        "moneda_xml": "",
        "tipo_cambio": 0,
        "estado_sat": "",
        "forma_pago": "",
        "metodo_pago": "",
        "tipo_comprobante": "",
        "uso_cfdi": "",
        "subtotal_xml": 0,
        "iva_xml": 0,
        "total_xml": 0,
    }


def _normalize_df(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    for c in cols:
        if c not in df.columns:
            df[c] = None

    if "fecha_gasto" in df.columns:

        def _fix_date(v):
            if v is None or (isinstance(v, float) and pd.isna(v)) or (
                isinstance(v, str) and v.strip() == ""
            ):
                return date.today()
            try:
                dt = pd.to_datetime(v, errors="coerce")
                if pd.isna(dt):
                    return date.today()
                return dt.date()
            except Exception:
                return date.today()

        df["fecha_gasto"] = df["fecha_gasto"].apply(_fix_date)

    # tipo_cambio numérico
    if "tipo_cambio" in df.columns:
        df["tipo_cambio"] = pd.to_numeric(df["tipo_cambio"], errors="coerce").fillna(0.0)    

    for c in ["concepto", "uuid", "descripcion", "proveedor"]:
        if c in df.columns:
            df[c] = df[c].apply(
                lambda x: ""
                if x is None or (isinstance(x, float) and pd.isna(x))
                else str(x)
            )
    for c in ["importe","impuesto1","impuesto2","impuesto3","impuesto4","subtotal_xml","iva_xml","total_xml"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)

    for c in ["cantidad"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)

    return df[cols].copy()


def _tipo_comprobante_a_clave(x: str) -> str:
    s = (x or "").strip().upper()
    if not s:
        return ""
    # si ya viene clave
    if s[:1] in ("I", "E", "P", "T", "N"):
        return s[:1]
    # si viene descripción
    mapa = {
        "INGRESO": "I",
        "EGRESO": "E",
        "PAGO": "P",
        "TRASLADO": "T",
        "NOMINA": "N",
        "NÓMINA": "N",
    }
    return mapa.get(s, "")


def _normaliza_sat_campos_en_df(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()

    if "moneda_xml" in d.columns:
        d["moneda_xml"] = d["moneda_xml"].fillna("").astype(str).str.strip().str.upper()
        if "tipo_cambio" in d.columns:
            d.loc[d["moneda_xml"] == "MXN", "tipo_cambio"] = 1

    if "estado_sat" in d.columns:
        d["estado_sat"] = d["estado_sat"].fillna("").astype(str).str.strip()
        d.loc[d["estado_sat"] == "", "estado_sat"] = "Vigente"

    if "metodo_pago" in d.columns:
        d["metodo_pago"] = d["metodo_pago"].fillna("").astype(str).str.strip().str.upper()

    if "tipo_comprobante" in d.columns:
        d["tipo_comprobante"] = d["tipo_comprobante"].fillna("").astype(str).str.strip()
        d["tipo_comprobante"] = d["tipo_comprobante"].apply(_tipo_comprobante_a_clave)

    if "uso_cfdi" in d.columns:
        d["uso_cfdi"] = d["uso_cfdi"].fillna("").astype(str).str.strip().str.upper()

    if "forma_pago" in d.columns:
        d["forma_pago"] = d["forma_pago"].fillna("").astype(str).str.strip()

    return d


def mostrar_tab_solicitudes_gastos():
    st.subheader("solicitudes de gastos")

    usuario = _get_usuario_actual()
    if not usuario:
        st.warning("no hay sesión de usuario en st.session_state['usuario']")
        return

    st.session_state.setdefault("sg_selected_id", None)
    selected_id = st.session_state.get("sg_selected_id") or None

    modo_widget = st.radio(
        "modo",
        options=["crear", "editar"],
        horizontal=True,
        key="sg_modo_widget",
    )
    modo = "editar" if selected_id else modo_widget

    solicitud = None
    if modo == "editar" and selected_id:
        solicitud = get_solicitud_ctrl(int(selected_id))
        if solicitud and usuario.get("rol") != "Admin":
            if int(solicitud.get("empleado_id") or 0) != int(usuario["id"]):
                st.session_state["sg_selected_id"] = None
                st.warning("no tienes acceso a esa solicitud")
                st.rerun()

    usuarios = get_usuarios_activos_ctrl()
    usuarios_map = {u["id"]: u for u in usuarios}

    st.caption("cabecera")

    if modo == "editar" and solicitud:
        st.text_input("folio", value=solicitud["folio"], disabled=True)
        st.text_input("estatus", value=solicitud["estatus"], disabled=True)
    else:
        st.text_input("folio", value="(se genera al guardar)", disabled=True)

    empleado_default = (
        solicitud["empleado_id"] if solicitud else (usuario["id"] if usuario else None)
    )
    ids_usuarios = [u["id"] for u in usuarios]
    idx_default = ids_usuarios.index(empleado_default) if empleado_default in ids_usuarios else 0

    empleado_id = st.selectbox(
        "empleado",
        options=ids_usuarios,
        format_func=lambda _id: f"{usuarios_map[_id]['nombre']} ({usuarios_map[_id]['rol']})",
        index=idx_default,
        key="sg_empleado_id",
    )
    empleado_nombre = usuarios_map[empleado_id]["nombre"]

    c3, c4 = st.columns(2)
    with c3:
        clientes = st.text_input(
            "cliente(s)",
            value=(solicitud["clientes"] or "") if solicitud else "",
            key="sg_clientes",
        )
        ciudades = st.text_input(
            "ciudad(es)",
            value=(solicitud["ciudades"] or "") if solicitud else "",
            key="sg_ciudades",
        )
        objetivo = st.text_area(
            "objetivo",
            value=(solicitud["objetivo"] or "") if solicitud else "",
            height=120,
            key="sg_objetivo",
        )
    with c4:
        fecha_inicio = st.date_input(
            "fecha inicio",
            value=(solicitud["fecha_inicio"] if solicitud else date.today()),
            key="sg_fecha_ini",
        )
        fecha_fin = st.date_input(
            "fecha fin",
            value=(solicitud["fecha_fin"] if solicitud else date.today()),
            key="sg_fecha_fin",
        )

        hs = _to_time(solicitud["hora_salida"]) if solicitud else None
        hr = _to_time(solicitud["hora_regreso"]) if solicitud else None

        hora_salida = st.time_input(
            "hora salida",
            value=(hs if hs else _hora_default(5, 0)),
            key="sg_hora_salida",
        )
        hora_regreso = st.time_input(
            "hora regreso",
            value=(hr if hr else _hora_default(19, 0)),
            key="sg_hora_regreso",
        )

    if fecha_inicio > fecha_fin:
        st.error("fecha inicio no puede ser mayor a fecha fin")
        return

    cbtn1, cbtn2, cbtn3, cbtn4 = st.columns([2, 2, 2, 2])

    if modo == "crear":
        if cbtn1.button("guardar cabecera", use_container_width=True):
            solicitud_id, folio = crear_solicitud_ctrl(
                empleado_id=int(empleado_id),
                empleado_nombre=empleado_nombre,
                clientes=clientes.strip() or None,
                ciudades=ciudades.strip() or None,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                hora_salida=hora_salida,
                hora_regreso=hora_regreso,
                objetivo=objetivo.strip() or None,
                usuario_id=int(usuario["id"]),
            )
            st.success(f"solicitud creada: {folio} (id {solicitud_id})")
            st.session_state["sg_selected_id"] = int(solicitud_id)
            st.rerun()
    else:
        if selected_id:
            if cbtn1.button("guardar cambios cabecera", use_container_width=True):
                actualizar_cabecera_ctrl(
                    solicitud_id=int(selected_id),
                    empleado_id=int(empleado_id),
                    empleado_nombre=empleado_nombre,
                    clientes=clientes.strip() or None,
                    ciudades=ciudades.strip() or None,
                    fecha_inicio=fecha_inicio,
                    fecha_fin=fecha_fin,
                    hora_salida=hora_salida,
                    hora_regreso=hora_regreso,
                    objetivo=objetivo.strip() or None,
                    usuario_id=int(usuario["id"]),
                )
                st.success("cabecera actualizada")
                st.rerun()

            estatus_actual = solicitud["estatus"] if solicitud else ""

            if cbtn2.button(
                "enviar",
                use_container_width=True,
                disabled=(estatus_actual not in ("captura", "rechazada")),
            ):
                cambiar_estatus_ctrl(int(selected_id), "enviada", int(usuario["id"]))
                st.success("estatus actualizado: enviada")
                st.rerun()

            if cbtn3.button(
                "autorizar",
                use_container_width=True,
                disabled=(usuario.get("rol") != "Admin" or estatus_actual != "enviada"),
            ):
                cambiar_estatus_ctrl(int(selected_id), "autorizada", int(usuario["id"]))
                st.success("estatus actualizado: autorizada")
                st.rerun()

            if cbtn4.button(
                "rechazar",
                use_container_width=True,
                disabled=(usuario.get("rol") != "Admin" or estatus_actual != "enviada"),
            ):
                cambiar_estatus_ctrl(int(selected_id), "rechazada", int(usuario["id"]))
                st.success("estatus actualizado: rechazada")
                st.rerun()
        else:
            st.info("para editar, selecciona una solicitud abajo.")

    st.divider()

    st.caption("buscar / resultados")

    b1, b2 = st.columns([2, 3])

    with b1:
        folio_like = st.text_input("folio contiene", key="sg_folio_like")
        estatus = st.selectbox(
            "estatus",
            options=["", "captura", "enviada", "autorizada", "rechazada", "cancelada", "cerrada"],
            index=0,
            key="sg_estatus",
        )
        anio = st.number_input(
            "año",
            min_value=2020,
            max_value=2100,
            value=datetime.now().year,
            step=1,
            key="sg_anio",
        )

    with b2:
        empleado_id_filtro = None if usuario.get("rol") == "Admin" else int(usuario["id"])

        rows = listar_solicitudes_ctrl(
            folio_like=folio_like,
            estatus=estatus,
            anio=int(anio) if anio else None,
            empleado_id=empleado_id_filtro,
            limit=200,
        )

        df = pd.DataFrame(rows)
        if df.empty:
            st.info("sin resultados")
        else:
            st.dataframe(df, use_container_width=True, hide_index=True)

        selected_id_widget = st.number_input(
            "id solicitud seleccionada",
            min_value=0,
            value=int(st.session_state.get("sg_selected_id") or 0),
            step=1,
            key="sg_selected_id_widget",
        )

        if selected_id_widget and int(selected_id_widget) != int(st.session_state.get("sg_selected_id") or 0):
            nuevo_id = int(selected_id_widget)

            if usuario.get("rol") == "Admin":
                st.session_state["sg_selected_id"] = nuevo_id
                st.rerun()
            else:
                s = get_solicitud_ctrl(nuevo_id)
                if s and int(s.get("empleado_id") or 0) == int(usuario["id"]):
                    st.session_state["sg_selected_id"] = nuevo_id
                    st.rerun()
                else:
                    st.warning("esa solicitud no es tuya o no existe")

    st.divider()

    selected_id = st.session_state.get("sg_selected_id") or None
    if not selected_id:
        st.info("selecciona una solicitud para capturar detalle.")
        return


    # ---------------------------------------------------------------------
    # importar xml/pdf a datoscfd (global)
    # ---------------------------------------------------------------------
    st.subheader("importar xml/pdf a mysql (datoscfd)")

    up_files = st.file_uploader(
        "selecciona uno o varios archivos (xml o pdf)",
        type=["xml", "pdf"],
        accept_multiple_files=True,
        key="sg_uploader_archivos",
    )

    user = st.session_state.get("usuario", {}) or {}
    username = user.get("username") or st.session_state.get("username") or "admin"

    cimp1, cimp2 = st.columns([1.2, 3.0])
    cimp1.text_input("usuario", username, disabled=True, key="sg_show_user_import")

    btn_importar = cimp2.button(
        "importar archivo(s)",
        use_container_width=True,
        key="sg_btn_importar_archivos",
        disabled=(not up_files),
    )

    if btn_importar and up_files:
        xml_inserted = xml_duplicated = xml_updated = 0
        pdf_guardados = 0
        errores = []

        xml_files = [f for f in up_files if (f.name or "").lower().endswith(".xml")]
        pdf_files = [f for f in up_files if (f.name or "").lower().endswith(".pdf")]

        uuid_par = None

        # regla 1: exactamente 1 xml y 1 pdf -> el uuid del xml se asigna al pdf
        if len(xml_files) == 1 and len(pdf_files) == 1:
            try:
                rxml = registrar_cfdi_desde_xml(xml_bytes=xml_files[0].getvalue(), username=username)
                if rxml.get("ok"):
                    stt = rxml.get("status")
                    if stt == "inserted":
                        xml_inserted += 1
                    elif stt == "updated":
                        xml_updated += 1
                    else:
                        xml_duplicated += 1
                    uuid_par = (rxml.get("uuid") or "").strip().upper() or None
                else:
                    errores.append(f"{xml_files[0].name}: {rxml.get('error') or 'error xml'}")
            except Exception as e:
                errores.append(f"{xml_files[0].name}: {e}")

            try:
                rpdf = guardar_pdf_datoscfd(
                    pdf_bytes=pdf_files[0].getvalue(),
                    nombre_archivo=pdf_files[0].name,
                    usuario=username,
                    uuid=uuid_par,
                    id_doctodig=None,
                    metodo_uuid="par_xml_pdf" if uuid_par else "par_xml_pdf_sin_uuid",
                    status="cargado",
                )
                if rpdf.get("ok"):
                    pdf_guardados += 1
                else:
                    errores.append(f"{pdf_files[0].name}: {rpdf.get('error') or 'error pdf'}")
            except Exception as e:
                errores.append(f"{pdf_files[0].name}: {e}")

            xml_files = []
            pdf_files = []

        # xml restantes
        for f in xml_files:
            try:
                rxml = registrar_cfdi_desde_xml(xml_bytes=f.getvalue(), username=username)
                if rxml.get("ok"):
                    stt = rxml.get("status")
                    if stt == "inserted":
                        xml_inserted += 1
                    elif stt == "updated":
                        xml_updated += 1
                    else:
                        xml_duplicated += 1
                else:
                    errores.append(f"{f.name}: {rxml.get('error') or 'error xml'}")
            except Exception as e:
                errores.append(f"{f.name}: {e}")

        # pdf restantes con regla 2 y 3
        for f in pdf_files:
            try:
                b = f.getvalue()

                uuid_pdf_raw = extraer_uuid_desde_pdf(b)
                uuid_pdf = _uuid_en_texto(uuid_pdf_raw or "")
                metodo = "pdf_texto" if uuid_pdf else None

                if not uuid_pdf:
                    uuid_pdf = _uuid_en_nombre(f.name)
                    if uuid_pdf:
                        metodo = "nombre_archivo"

                if not uuid_pdf:
                    metodo = "sin_uuid"

                rpdf = guardar_pdf_datoscfd(
                    pdf_bytes=b,
                    nombre_archivo=f.name,
                    usuario=username,
                    uuid=uuid_pdf,
                    id_doctodig=None,
                    metodo_uuid=metodo,
                    status="cargado",
                )

                if rpdf.get("ok"):
                    pdf_guardados += 1
                else:
                    errores.append(f"{f.name}: {rpdf.get('error') or 'error pdf'}")

            except Exception as e:
                errores.append(f"{f.name}: {e}")

        msg = (
            f"xml insertados: {xml_inserted} | xml duplicados: {xml_duplicated} | "
            f"xml actualizados: {xml_updated} | pdf guardados: {pdf_guardados}"
        )

        if errores:
            st.warning(msg + f" | errores: {len(errores)}")
            st.text("\n".join(errores))
        else:
            st.success(msg)

    st.divider()

    # ---------------------------------------------------------------------
    # detalle
    # ---------------------------------------------------------------------
    st.caption("detalle de gastos")

    detalle_rows = get_detalle_ctrl(int(selected_id))
    df_det = pd.DataFrame(detalle_rows)

    cols = [
        "id",
        "fecha_gasto",
        "concepto",
        "uuid",
        "descripcion",
        "cantidad",
        "precio_unitario",
        "importe",
        "pagado_con",

        "proveedor",
        "receptor",
        "serie",
        "folio",
        "version",
        "moneda_xml",
        "tipo_cambio",
        "estado_sat",
        "forma_pago",
        "metodo_pago",
        "tipo_comprobante",
        "uso_cfdi",
        "subtotal_xml",
        "iva_xml",
        "total_xml",
    ]

    if df_det.empty:
        df_det = pd.DataFrame([_defaults_row()])
    df_edit = _normalize_df(df_det, cols)
    df_edit = _normaliza_sat_campos_en_df(df_edit)

    if st.session_state.get("sg_det_df_solicitud_id") != int(selected_id):
        st.session_state["sg_det_df"] = df_edit
        st.session_state["sg_det_df_solicitud_id"] = int(selected_id)
        st.session_state["sg_uuid_prev"] = {}
        st.session_state["sg_uuid_cache"] = {}

    st.session_state.setdefault("sg_det_df", df_edit)

    cat_conceptos = get_conceptos_gasto_ctrl(activo=1)
    conceptos_opts = [
        str(r.get("concepto", "")).strip()
        for r in (cat_conceptos or [])
        if str(r.get("concepto", "")).strip()
    ]

    if "usuario_forma_pago_id" not in df_edit.columns:
        df_edit["usuario_forma_pago_id"] = None

    # columna visible
    df_edit["pagado_con"] = df_edit["usuario_forma_pago_id"].apply(
        lambda v: id_to_label.get(int(v), "") if v not in (None, "", "nan") else ""
    )


    valores_actuales = sorted(
        {
            str(x).strip()
            for x in st.session_state["sg_det_df"]["concepto"].dropna().tolist()
            if str(x).strip() != ""
        }
    )
    extras = [v for v in valores_actuales if v not in set(conceptos_opts)]
    conceptos_opts_final = conceptos_opts + extras

    if st.button("agregar renglón", use_container_width=False):
        df_tmp = st.session_state["sg_det_df"].copy()
        df_tmp = pd.concat([df_tmp, pd.DataFrame([_defaults_row()])], ignore_index=True)
        df_tmp = _normalize_df(df_tmp, cols)
        df_tmp = _normaliza_sat_campos_en_df(df_tmp)
        st.session_state["sg_det_df"] = df_tmp
        st.session_state["sg_uuid_prev"] = {}
        st.rerun()

    formas = get_formas_pago_usuario_ctrl(int(empleado_id))
    id_to_label = {int(x["id"]): str(x.get("etiqueta") or "").strip() for x in (formas or []) if x.get("id") is not None}
    label_to_id = {v: k for k, v in id_to_label.items()}
    formas_opts = list(label_to_id.keys())
    # si no hay opciones, metemos un placeholder (pero no guardará id)
    if not formas_opts:
        formas_opts = ["(sin formas de pago activas)"]



    edited = st.data_editor(
        st.session_state["sg_det_df"],
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        key="sg_det_editor",
        column_config={
            "id": st.column_config.TextColumn("id", disabled=True),
            "concepto": st.column_config.SelectboxColumn(
                "concepto", options=conceptos_opts_final, required=True
            ),
            #"moneda": st.column_config.SelectboxColumn(
            #    "moneda", options=["mxn", "usd"], required=True
            #),
            "uuid": st.column_config.TextColumn("uuid"),
            "descripcion": st.column_config.TextColumn("Observaciones"),
            "pagado_con": st.column_config.SelectboxColumn(
                "Pagado Con",
                options=formas_opts,
                required=False,
            ),
            "proveedor": st.column_config.TextColumn("proveedor", disabled=True),
            "fecha_gasto": st.column_config.DateColumn("fecha", disabled=True),
            "cantidad": st.column_config.NumberColumn("cantidad", min_value=0.0, step=1.0, disabled=True),
            "precio_unitario": st.column_config.NumberColumn("Gasto Estimado", min_value=0.0, step=1.0, disabled=True),
            "importe": st.column_config.NumberColumn("importe", disabled=True),
            #"impuesto1": st.column_config.NumberColumn("impuesto1", disabled=True),
            #"impuesto2": st.column_config.NumberColumn("impuesto2", disabled=True),
            #"impuesto3": st.column_config.NumberColumn("impuesto3", disabled=True),
            #"impuesto4": st.column_config.NumberColumn("impuesto4", disabled=True),
            "receptor": st.column_config.TextColumn("receptor", disabled=True),
            "serie": st.column_config.TextColumn("serie", disabled=True),
            "folio": st.column_config.TextColumn("folio", disabled=True),
            "version": st.column_config.TextColumn("versión", disabled=True),
            "moneda_xml": st.column_config.TextColumn("moneda xml", disabled=True),
            "tipo_cambio": st.column_config.NumberColumn("tipo cambio", disabled=True),
            "estado_sat": st.column_config.TextColumn("estado sat", disabled=True),
            "forma_pago": st.column_config.TextColumn("forma pago", disabled=True),
            "metodo_pago": st.column_config.TextColumn("método pago", disabled=True),
            "tipo_comprobante": st.column_config.TextColumn("tipo comprobante", disabled=True),
            "uso_cfdi": st.column_config.TextColumn("uso cfdi", disabled=True),
            "subtotal_xml": st.column_config.NumberColumn("subtotal xml", disabled=True),
            "iva_xml": st.column_config.NumberColumn("iva xml", disabled=True),
            "total_xml": st.column_config.NumberColumn("total xml", disabled=True),
        },
    )

    st.session_state.setdefault("sg_uuid_cache", {})
    st.session_state.setdefault("sg_uuid_prev", {})

    changed = False

    for i, r in edited.iterrows():
        uuid_now = _norm_uuid(r.get("uuid"))
        uuid_prev = st.session_state["sg_uuid_prev"].get(i, "")

        if not uuid_now:
            st.session_state["sg_uuid_prev"][i] = ""
            continue

        falta_datos = (
            _to_float(r.get("importe")) == 0.0
            and _to_float(r.get("impuesto1")) == 0.0
            and _to_float(r.get("impuesto2")) == 0.0
            and _to_float(r.get("impuesto3")) == 0.0
            and _to_float(r.get("impuesto4")) == 0.0
            and (str(r.get("proveedor") or "").strip() == "")
        )

        if uuid_now != uuid_prev or falta_datos:
            if uuid_now in st.session_state["sg_uuid_cache"]:
                cfd = st.session_state["sg_uuid_cache"][uuid_now]
            else:
                cfd = get_datoscfd_by_uuid_ctrl(uuid_now)
                st.session_state["sg_uuid_cache"][uuid_now] = cfd

            if not cfd:
                st.warning(f"uuid no encontrado en DATOSCFD: {uuid_now}")
            else:
                proveedor = (
                    cfd.get("NOMBRE_EMISOR")
                    or cfd.get("nombre_emisor")
                    or cfd.get("NOMBRE")
                    or cfd.get("nombre")
                    or ""
                )
                fecha = cfd.get("FECHA_EMISION") or cfd.get("fecha_emision")

                importe = cfd.get("IMPORTE") or cfd.get("importe") or cfd.get("TOTAL") or cfd.get("total")
                impuesto1 = cfd.get("TOTAL_RETENCIONES_ISR") or cfd.get("total_retenciones_isr") or 0
                impuesto2 = cfd.get("TOTAL_RETENCIONES_IVA") or cfd.get("total_retenciones_iva") or 0
                impuesto3 = cfd.get("TOTAL_RETENCIONES_IEPS") or cfd.get("total_retenciones_ieps") or 0
                impuesto4 = cfd.get("TOTAL_RETENCIONES") or cfd.get("total_retenciones") or 0  # fallback
                cantidad = cfd.get("CANTIDAD") or cfd.get("cantidad") or 1
                precio_unitario = cfd.get("PRECIO_UNITARIO") or cfd.get("precio_unitario") or 0

                receptor = cfd.get("NOMBRE_RECEPTOR") or cfd.get("nombre_receptor") or ""
                folio = cfd.get("FOLIO") or cfd.get("folio") or ""
                serie = cfd.get("SERIE") or cfd.get("serie") or ""
                version = cfd.get("VERSION") or cfd.get("version") or ""
                moneda_xml = cfd.get("MONEDA") or cfd.get("moneda") or ""
                tipo_cambio = cfd.get("TIPOCAMBIO") or cfd.get("tipocambio") or 0

                estado_sat = cfd.get("ESTADO_SAT") or cfd.get("estado_sat") or ""
                forma_pago = cfd.get("FORMAPAGO") or cfd.get("formapago") or ""
                metodo_pago = cfd.get("METODOPAGO") or cfd.get("metodopago") or ""
                tipo_comprobante = cfd.get("TIPOCOMPROBANTE") or cfd.get("tipocomprobante") or ""
                uso_cfdi = cfd.get("USOCFDI") or cfd.get("usocfdi") or ""

                total_xml = cfd.get("TOTAL") or cfd.get("total") or 0
                subtotal_xml = cfd.get("SUBTOTAL") or cfd.get("subtotal") or 0
                iva_xml = cfd.get("IVA") or cfd.get("iva") or 0

                edited.at[i, "proveedor"] = str(proveedor).strip()

                if fecha is not None and str(fecha).strip() != "":
                    dt = pd.to_datetime(fecha, errors="coerce")
                    if not pd.isna(dt):
                        edited.at[i, "fecha_gasto"] = dt.date()

                edited.at[i, "importe"] = _to_float(importe)
                edited.at[i, "impuesto1"] = _to_float(impuesto1)
                edited.at[i, "impuesto2"] = _to_float(impuesto2)
                edited.at[i, "impuesto3"] = _to_float(impuesto3)
                edited.at[i, "impuesto4"] = _to_float(impuesto4)
                edited.at[i, "cantidad"] = _to_int(cantidad)
                edited.at[i, "precio_unitario"] = _to_float(precio_unitario)

                edited.at[i, "receptor"] = str(receptor).strip()
                edited.at[i, "folio"] = str(folio).strip()
                edited.at[i, "serie"] = str(serie).strip()
                edited.at[i, "version"] = str(version).strip()
                edited.at[i, "moneda_xml"] = str(moneda_xml).strip().upper()

                # normalizaciones sat
                if str(moneda_xml).strip().upper() == "MXN":
                    edited.at[i, "tipo_cambio"] = 1
                else:
                    edited.at[i, "tipo_cambio"] = _to_float(tipo_cambio)

                est = str(estado_sat).strip()
                edited.at[i, "estado_sat"] = est if est else "Vigente"

                edited.at[i, "forma_pago"] = str(forma_pago).strip()
                edited.at[i, "metodo_pago"] = str(metodo_pago).strip().upper()
                edited.at[i, "tipo_comprobante"] = _tipo_comprobante_a_clave(str(tipo_comprobante))
                edited.at[i, "uso_cfdi"] = str(uso_cfdi).strip().upper()

                edited.at[i, "total_xml"] = _to_float(total_xml)
                edited.at[i, "subtotal_xml"] = _to_float(subtotal_xml)
                edited.at[i, "iva_xml"] = _to_float(iva_xml)

                changed = True

            usado = uuid_ya_usado_ctrl(uuid_now, exclude_solicitud_id=int(selected_id))
            if usado:
                st.warning(
                    f"este uuid ya fue usado en otra solicitud: "
                    f"folio {usado.get('folio','')} (solicitud_id {usado.get('solicitud_id','')}), "
                    f"estatus {usado.get('estatus','')}, empleado {usado.get('empleado_nombre','')}"
                )

            st.session_state["sg_uuid_prev"][i] = uuid_now

    edited = _normalize_df(edited, cols)
    edited = _normaliza_sat_campos_en_df(edited)
    st.session_state["sg_det_df"] = edited

    if changed:
        st.rerun()

    csave, cdel = st.columns([2, 1])

    with cdel:
        ids_opts = []
        if "id" in st.session_state["sg_det_df"].columns:
            ids_opts = [
                int(x)
                for x in st.session_state["sg_det_df"]["id"].dropna().tolist()
                if str(x).strip() not in ("", "none", "nan")
            ]

        ids_a_borrar = st.multiselect(
            "borrar ids",
            options=ids_opts,
            default=[],
            key="sg_ids_borrar",
        )

    with csave:
        if st.button("guardar detalle", use_container_width=True):
            rows_out = st.session_state["sg_det_df"].to_dict(orient="records")

            res = guardar_detalle_ctrl(
                solicitud_id=int(selected_id),
                rows=rows_out,
                deleted_ids=[int(x) for x in ids_a_borrar],
                usuario_id=int(usuario["id"]),
            )

            if res.get("ok"):
                st.success(res.get("msg", "detalle guardado"))

                st.session_state.pop("sg_det_df", None)
                st.session_state.pop("sg_det_df_solicitud_id", None)
                st.session_state["sg_uuid_prev"] = {}
                st.session_state["sg_uuid_cache"] = {}
                st.session_state.pop("sg_det_editor", None)

                st.rerun()
            else:
                msg = res.get("msg", "")
                if "uuid" in msg.lower() and "ya fue usado" in msg.lower():
                    st.warning(msg)
                else:
                    st.error(msg or "no se pudo guardar el detalle")