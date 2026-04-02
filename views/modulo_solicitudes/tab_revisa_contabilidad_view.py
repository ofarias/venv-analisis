# views/modulo_solicitudes/tab_revisa_contabilidad_view.py

from __future__ import annotations

import pandas as pd
import streamlit as st
from io import BytesIO
import zipfile

#from controllers.solicitudes_controller import cambiar_estatus_ctrl
from controllers.solicitudes_controller import (
    listar_solicitudes_ctrl,
    get_solicitud_ctrl,
    get_detalle_contabilidad_ctrl,
    descargar_xml_ctrl,
    descargar_xmls_ctrl,
    descargar_pdf_ctrl,
    generar_poliza_solicitud_gasto_ctrl,
    descargar_comprobantes_detalle_ctrl,
)

ESTATUS_OPTS = [
    "todas",
    "autorizada",
    "dispersion",
    "contabilidad",
    "poliza",
    "revision comprobacion",
    "cerrada",
]


@st.cache_data(show_spinner=False, ttl=60)
def _get_solicitud_cached(solicitud_id: int):
    return get_solicitud_ctrl(int(solicitud_id))


@st.cache_data(show_spinner=False, ttl=60)
def _get_detalle_contabilidad_cached(solicitud_id: int):
    return get_detalle_contabilidad_ctrl(int(solicitud_id))


def _has_uuid(v) -> bool:
    return bool(str(v or "").strip())


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


def _requiere_validacion_row(r: dict) -> bool:
    precio_unitario = _to_float(r.get("precio_unitario"))
    fiscales = _to_int(r.get("fiscales"))
    uuid_ok = _has_uuid(r.get("uuid"))
    return precio_unitario > 0 or uuid_ok or fiscales == 1


def _get_usuario_actual():
    return st.session_state.get("usuario") or {}


def _money(x) -> str:
    try:
        return f"${float(x or 0):,.2f}"
    except Exception:
        return "$0.00"


def _money_text(x) -> str:
    try:
        return f"$ {float(x or 0):,.2f}"
    except Exception:
        return "$ 0.00"


def _estatus_badge(e: str) -> str:
    e = (e or "").strip().lower()
    if e == "autorizada":
        return "🟢 autorizada"
    if e == "dispersion":
        return "🟠 dispersion"
    if e == "contabilidad":
        return "🔵 contabilidad"
    if e == "poliza":
        return "🟣 poliza"
    if e == "revision comprobacion":
        return "🟡 revision comprobacion"
    if e == "cerrada":
        return "⚫ cerrada"
    return e


def _icon_prepago(concepto: str) -> str:
    concepto = (concepto or "").strip().lower()
    hints = ["hospedaje", "boletos", "hotel", "avión", "avion"]
    return "💳" if any(h in concepto for h in hints) else ""


def _es_prepago(concepto: str) -> bool:
    return _icon_prepago(concepto) == "💳"


def _aplicar_prorrateo_visual(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()

    if "porcentaje" not in d.columns:
        d["porcentaje"] = 100.0

    d["porcentaje"] = pd.to_numeric(d["porcentaje"], errors="coerce").fillna(100.0)

    for col in ["subtotal_xml", "iva_xml", "isr_ret_xml", "total_xml", "precio_unitario"]:
        if col not in d.columns:
            d[col] = 0.0
        d[col] = pd.to_numeric(d[col], errors="coerce").fillna(0.0)

    factor = d["porcentaje"] / 100.0
    d["subtotal_xml_prorr"] = d["subtotal_xml"] * factor
    d["iva_xml_prorr"] = d["iva_xml"] * factor
    d["isr_ret_xml_prorr"] = d["isr_ret_xml"] * factor
    d["total_xml_prorr"] = d["total_xml"] * factor
    d["precio_unitario_prorr"] = d["precio_unitario"] * factor

    d["monto"] = d["total_xml_prorr"].copy()
    sin_uuid = d["uuid"].isna() | (d["uuid"].astype(str).str.strip() == "")
    d.loc[sin_uuid, "monto"] = d.loc[sin_uuid, "precio_unitario_prorr"]

    return d


def _clear_doc_cache_for_current_request(sel_id: int, uuids: list[str]) -> None:
    st.session_state.pop("conta_zip_docs_bytes", None)
    st.session_state.pop("conta_zip_docs_name", None)

    for uuid in uuids:
        st.session_state.pop(f"xml_bytes_{uuid}", None)
        st.session_state.pop(f"xml_name_{uuid}", None)
        st.session_state.pop(f"pdf_bytes_{uuid}", None)
        st.session_state.pop(f"pdf_name_{uuid}", None)

    _get_solicitud_cached.clear()
    _get_detalle_contabilidad_cached.clear()


def mostrar_tab_revisa_contabilidad():
    st.subheader("revisión contabilidad")
    msg_ok = st.session_state.pop("conta_poliza_ok", "")
    msg_err = st.session_state.pop("conta_poliza_err", "")

    if msg_ok:
        st.success(msg_ok)

    if msg_err:
        st.error(msg_err)

    usuario = _get_usuario_actual()
    roles = [str(x).strip().lower() for x in (usuario.get("roles", []) or [])]

    if "contabilidad" not in roles:
        st.info("sin acceso")
        return

    st.caption("revisión previa a la creación de póliza")

    c1, c2, c3, c4 = st.columns([2, 2, 2, 2])

    with c1:
        folio_like = st.text_input("folio contiene", key="conta_rev_folio_like")

    with c2:
        estatus = st.selectbox(
            "estatus",
            options=ESTATUS_OPTS,
            index=1,
            key="conta_rev_estatus",
        )

    with c3:
        anio = st.number_input(
            "año",
            min_value=2020,
            max_value=2100,
            value=pd.Timestamp.now().year,
            step=1,
            key="conta_rev_anio",
        )

    with c4:
        limit = st.number_input(
            "límite",
            min_value=50,
            max_value=2000,
            value=300,
            step=50,
            key="conta_rev_limit",
        )

    estatus_param = "" if estatus == "todas" else estatus

    rows = listar_solicitudes_ctrl(
        folio_like=folio_like,
        estatus=estatus_param,
        anio=int(anio) if anio else None,
        empleado_id=None,
        limit=int(limit),
    ) or []

    df = pd.DataFrame(rows)

    st.markdown("### documentos")

    if df.empty:
        st.info("sin resultados")
        return

    if "estatus" in df.columns:
        df.insert(0, "estatus_visual", df["estatus"].apply(_estatus_badge))

    cols_show = [
        c
        for c in [
            "id",
            "estatus_visual",
            "folio",
            "empleado_nombre",
            "clientes",
            "ciudades",
            "fecha_inicio",
            "fecha_fin",
            "fecha_creacion",
        ]
        if c in df.columns
    ]

    st.dataframe(df[cols_show] if cols_show else df, use_container_width=True, hide_index=True)

    st.divider()
    st.caption("detalle de solicitud")

    sel_id = st.number_input(
        "id solicitud",
        min_value=0,
        value=int(st.session_state.get("conta_rev_selected_id") or 0),
        step=1,
        key="conta_rev_selected_id",
    )

    if not sel_id:
        st.info("captura un id para revisar la solicitud")
        return

    s = _get_solicitud_cached(int(sel_id))
    if not s:
        st.warning("no existe esa solicitud")
        return

    st.markdown("### cabecera")
    st.markdown(
        f"""
        <div style="line-height:1.8">
        <b>folio:</b> {s.get('folio', '')}<br>
        <b>empleado:</b> {s.get('empleado_nombre', '')}<br>
        <b>clientes:</b> {s.get('clientes', '')}<br>
        <b>ciudades:</b> {s.get('ciudades', '')}<br>
        <b>fecha inicio:</b> {s.get('fecha_inicio', '')}<br>
        <b>fecha fin:</b> {s.get('fecha_fin', '')}<br>
        <b>estatus:</b> {s.get('estatus', '')}
        </div>
        """,
        unsafe_allow_html=True,
    )

    detalle = _get_detalle_contabilidad_cached(int(sel_id)) or []
    if not detalle:
        st.info("sin detalle")
        return

    df_det = pd.DataFrame(detalle)
    if df_det.empty:
        st.info("sin detalle contable")
        return

    df_det = _aplicar_prorrateo_visual(df_det)

    if "precio_unitario" in df_det.columns:
        df_det["precio_unitario"] = pd.to_numeric(
            df_det["precio_unitario"], errors="coerce"
        ).fillna(0.0)

    if "fiscales" not in df_det.columns:
        df_det["fiscales"] = 0

    if "uuid" not in df_det.columns:
        df_det["uuid"] = ""

    if "concepto" not in df_det.columns:
        df_det["concepto"] = ""

    df_det["es_prepago"] = df_det["concepto"].fillna("").apply(_es_prepago)

    if "tiene_pdf" in df_det.columns:
        df_det["pdf"] = df_det.apply(
            lambda r: "📄"
            if _requiere_validacion_row(r.to_dict()) and _to_int(r.get("tiene_pdf")) == 1
            else "",
            axis=1,
        )
    else:
        df_det["pdf"] = ""

    if "total_unidades" in df_det.columns:
        def _icon_un_row(r):
            if not _requiere_validacion_row(r.to_dict()):
                return ""
            total = _to_float(r.get("total_unidades"))
            if round(total, 6) == 100.0:
                return "☑️"
            if total > 0:
                return "⚠️"
            return ""

        df_det["un"] = df_det.apply(_icon_un_row, axis=1)
    else:
        df_det["un"] = ""

    df_det["prep"] = df_det["concepto"].apply(_icon_prepago)

    cols_det = [
        c
        for c in [
            "fecha",
            "concepto_catalogo",
            "cuenta",
            "unidad_negocio",
            "depto",
            "porcentaje",
            "uuid",
            "rfce",
            "proveedor",
            "subtotal_xml_prorr",
            "iva_xml_prorr",
            "isr_ret_xml_prorr",
            "total_xml_prorr",
            "precio_unitario_prorr",
            "moneda",
            "notas",
        ]
        if c in df_det.columns
    ]

    st.markdown("### detalle de gastos")
    df_det_show = df_det[cols_det].copy()

    rename_map = {
        "concepto_catalogo": "concepto",
        "unidad_negocio": "unidad_negocio",
        "porcentaje": "% prorrateo",
        "subtotal_xml_prorr": "subtotal_xml",
        "iva_xml_prorr": "iva_xml",
        "isr_ret_xml_prorr": "isr_ret_xml",
        "total_xml_prorr": "total_xml",
        "precio_unitario_prorr": "precio_unitario",
    }

    df_det_show = df_det_show.rename(columns=rename_map)

    for col in ["subtotal_xml", "iva_xml", "isr_ret_xml", "total_xml", "precio_unitario"]:
        if col in df_det_show.columns:
            df_det_show[col] = df_det_show[col].apply(_money_text)

    st.dataframe(df_det_show, use_container_width=True, hide_index=True)

    total_general = float(df_det["monto"].sum())

    total_fiscal = float(
        df_det.loc[df_det["uuid"].notna() & (df_det["uuid"] != ""), "monto"].sum()
    )

    total_no_fiscal = float(
        df_det.loc[df_det["uuid"].isna() | (df_det["uuid"] == ""), "monto"].sum()
    )

    total_no_prepago = float(
        df_det.loc[~df_det["es_prepago"], "monto"].sum()
    )

    st.markdown("### resumen")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("total fiscal", _money(total_fiscal))
    c2.metric("total no fiscal", _money(total_no_fiscal))
    c3.metric("total general", _money(total_general))
    c4.metric("gastos no prepagos", _money(total_no_prepago))

    st.markdown("### resumen por concepto (sin prorrateo)")

    df_concepto = df_det.copy()

    if "concepto_catalogo" not in df_concepto.columns:
        df_concepto["concepto_catalogo"] = df_concepto.get("concepto", "")

    df_concepto["subtotal_xml"] = pd.to_numeric(df_concepto.get("subtotal_xml", 0), errors="coerce").fillna(0.0)
    df_concepto["iva_xml"] = pd.to_numeric(df_concepto.get("iva_xml", 0), errors="coerce").fillna(0.0)
    df_concepto["isr_ret_xml"] = pd.to_numeric(df_concepto.get("isr_ret_xml", 0), errors="coerce").fillna(0.0)
    df_concepto["total_xml"] = pd.to_numeric(df_concepto.get("total_xml", 0), errors="coerce").fillna(0.0)
    df_concepto["precio_unitario"] = pd.to_numeric(df_concepto.get("precio_unitario", 0), errors="coerce").fillna(0.0)
    df_concepto["es_prepago"] = df_concepto["concepto"].fillna("").apply(_es_prepago)

    resumen_concepto = (
        df_concepto.groupby("detalle_id", as_index=False)
        .agg(
            concepto=("concepto_catalogo", "first"),
            cuenta=("cuenta", "first"),
            proveedor=("proveedor", "first"),
            uuid=("uuid", "first"),
            subtotal_xml=("subtotal_xml", "first"),
            iva_xml=("iva_xml", "first"),
            isr_ret_xml=("isr_ret_xml", "first"),
            total_xml=("total_xml", "first"),
            precio_unitario=("precio_unitario", "first"),
            moneda=("moneda", "first"),
            es_prepago=("es_prepago", "first"),
        )
    )

    resumen_concepto["monto"] = resumen_concepto.apply(
        lambda r: _to_float(r.get("total_xml"))
        if _has_uuid(r.get("uuid"))
        else _to_float(r.get("precio_unitario")),
        axis=1,
    )

    resumen_concepto = (
        resumen_concepto.groupby(["concepto", "cuenta", "moneda"], as_index=False)
        .agg(
            subtotal_xml=("subtotal_xml", "sum"),
            iva_xml=("iva_xml", "sum"),
            isr_ret_xml=("isr_ret_xml", "sum"),
            total_xml=("total_xml", "sum"),
            precio_unitario=("precio_unitario", "sum"),
            monto=("monto", "sum"),
            es_prepago=("es_prepago", "max"),
        )
        .sort_values(["concepto", "cuenta", "moneda"])
    )

    resumen_concepto_show = resumen_concepto.copy()

    for col in ["subtotal_xml", "iva_xml", "isr_ret_xml", "total_xml", "precio_unitario", "monto"]:
        resumen_concepto_show[col] = resumen_concepto_show[col].apply(_money_text)

    st.markdown(
        """
        <style>
        div[data-testid="stDataFrame"] div[role="gridcell"] {
            font-variant-numeric: tabular-nums;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.dataframe(
        resumen_concepto_show,
        use_container_width=True,
        hide_index=True,
        column_config={
            "subtotal_xml": st.column_config.TextColumn("subtotal_xml", width="medium"),
            "iva_xml": st.column_config.TextColumn("iva_xml", width="medium"),
            "isr_ret_xml": st.column_config.TextColumn("isr_ret_xml", width="medium"),
            "total_xml": st.column_config.TextColumn("total_xml", width="medium"),
            "precio_unitario": st.column_config.TextColumn("precio_unitario", width="medium"),
            "monto": st.column_config.TextColumn("monto", width="medium"),
            "es_prepago": None,
        },
    )

    pendientes_pdf = 0
    pendientes_un = 0

    if "tiene_pdf" in df_det.columns:
        pendientes_pdf = int(
            df_det.apply(
                lambda r: 1
                if _requiere_validacion_row(r.to_dict()) and _to_int(r.get("tiene_pdf")) != 1
                else 0,
                axis=1,
            ).sum()
        )

    if "total_unidades" in df_det.columns:
        pendientes_un = int(
            df_det.apply(
                lambda r: 1
                if _requiere_validacion_row(r.to_dict())
                and round(_to_float(r.get("total_unidades")), 6) != 100.0
                else 0,
                axis=1,
            ).sum()
        )

    st.markdown("### control")
    c4, c5 = st.columns(2)
    c4.metric("líneas sin pdf", pendientes_pdf)
    c5.metric("líneas sin unidades al 100", pendientes_un)

    uuids = sorted({
        str(r.get("uuid") or "").strip().upper()
        for _, r in df_det.iterrows()
        if str(r.get("uuid") or "").strip()
    })
    
    detalle_ids = sorted({
        int(r.get("detalle_id"))
        for _, r in df_det.iterrows()
        if r.get("detalle_id") not in (None, "", "nan")
    })

    if pendientes_pdf == 0 and pendientes_un == 0:
        st.success("la solicitud cumple validaciones para pasar a revision comprobacion.")

        if st.button("generar póliza", use_container_width=True):
            res = generar_poliza_solicitud_gasto_ctrl(
                solicitud_id=int(sel_id),
                usuario_id=int(usuario.get("id") or 0),
            )

            if res.get("ok"):
                _clear_doc_cache_for_current_request(int(sel_id), uuids)
                st.session_state["conta_poliza_ok"] = res.get("msg") or "póliza generada correctamente"
                st.rerun()
            else:
                st.session_state["conta_poliza_err"] = res.get("msg") or "no se pudo generar la póliza"
                st.rerun()
    else:
        st.warning("la solicitud aún tiene pendientes antes de pasar a revision comprobacion.")

    st.markdown("### documentos")

    if uuids or detalle_ids:
        c_zip1, c_zip2 = st.columns([2, 3])

        with c_zip1:
            if st.button("preparar zip xml + pdf + comprobantes", use_container_width=True, key="conta_btn_zip_docs"):
                xml_map = descargar_xmls_ctrl(uuids) or {}
                comprobantes_map = descargar_comprobantes_detalle_ctrl(detalle_ids) or {}

                zip_buffer = BytesIO()

                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                    # xml y pdf por uuid
                    for uuid in uuids:
                        xml_data = xml_map.get(uuid)
                        if xml_data:
                            xml_bytes, xml_name = xml_data
                            xml_filename = (xml_name or f"{uuid}.xml").strip()
                            if not xml_filename.lower().endswith(".xml"):
                                xml_filename += ".xml"
                            zf.writestr(f"xml/{xml_filename}", xml_bytes)

                        pdf_bytes, pdf_name = descargar_pdf_ctrl(uuid)
                        if pdf_bytes:
                            pdf_filename = (pdf_name or f"{uuid}.pdf").strip()
                            if not pdf_filename.lower().endswith(".pdf"):
                                pdf_filename += ".pdf"
                            zf.writestr(f"pdf/{pdf_filename}", pdf_bytes)

                    # comprobantes por detalle_id
                    for detalle_id, comp in comprobantes_map.items():
                        archivo = comp.get("archivo")
                        nombre = (comp.get("nombre_archivo") or f"detalle_{detalle_id}").strip()

                        if not archivo:
                            continue

                        # evita nombres duplicados y deja claro a qué detalle pertenece
                        nombre_zip = f"detalle_{int(detalle_id)}_{nombre}"
                        zf.writestr(f"comprobantes/{nombre_zip}", archivo)

                zip_buffer.seek(0)
                st.session_state["conta_zip_docs_bytes"] = zip_buffer.getvalue()
                st.session_state["conta_zip_docs_name"] = f"solicitud_{int(sel_id)}_xml_pdf_comprobantes.zip"

        with c_zip2:
            zip_bytes = st.session_state.get("conta_zip_docs_bytes")
            zip_name = st.session_state.get("conta_zip_docs_name")
            if zip_bytes:
                st.download_button(
                    "descargar zip xml + pdf + comprobantes",
                    data=zip_bytes,
                    file_name=zip_name,
                    mime="application/zip",
                    use_container_width=True,
                    key="conta_download_zip_docs",
                )

    for uuid in uuids:
        c1, c2, c3 = st.columns([3, 1, 1])

        with c1:
            st.write(uuid)

        with c2:
            if st.button("preparar XML", key=f"prep_xml_{uuid}", use_container_width=True):
                xml_bytes, xml_name = descargar_xml_ctrl(uuid)
                if xml_bytes:
                    xml_filename = (xml_name or f"{uuid}.xml").strip()
                    if not xml_filename.lower().endswith(".xml"):
                        xml_filename += ".xml"
                    st.session_state[f"xml_bytes_{uuid}"] = xml_bytes
                    st.session_state[f"xml_name_{uuid}"] = xml_filename

            xml_bytes = st.session_state.get(f"xml_bytes_{uuid}")
            xml_name = st.session_state.get(f"xml_name_{uuid}")
            if xml_bytes:
                st.download_button(
                    "XML",
                    data=xml_bytes,
                    file_name=xml_name,
                    mime="text/xml",
                    key=f"xml_{uuid}",
                    use_container_width=True,
                )

        with c3:
            if st.button("preparar PDF", key=f"prep_pdf_{uuid}", use_container_width=True):
                pdf_bytes, pdf_name = descargar_pdf_ctrl(uuid)
                if pdf_bytes:
                    pdf_filename = (pdf_name or f"{uuid}.pdf").strip()
                    if not pdf_filename.lower().endswith(".pdf"):
                        pdf_filename += ".pdf"
                    st.session_state[f"pdf_bytes_{uuid}"] = pdf_bytes
                    st.session_state[f"pdf_name_{uuid}"] = pdf_filename

            pdf_bytes = st.session_state.get(f"pdf_bytes_{uuid}")
            pdf_name = st.session_state.get(f"pdf_name_{uuid}")
            if pdf_bytes:
                st.download_button(
                    "PDF",
                    data=pdf_bytes,
                    file_name=pdf_name,
                    mime="application/pdf",
                    key=f"pdf_{uuid}",
                    use_container_width=True,
                )

    if pendientes_pdf == 0 and pendientes_un == 0:
        st.success("la solicitud está lista para continuar a la creación de póliza.")
    else:
        st.warning("la solicitud aún tiene pendientes antes de crear la póliza.")