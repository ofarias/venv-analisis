# views/modulo_solicitudes/tab_revisa_contabilidad_view.py

from __future__ import annotations

import pandas as pd
import streamlit as st
from io import BytesIO
import zipfile

from controllers.solicitudes_controller import (
    listar_solicitudes_ctrl,
    get_solicitud_ctrl,
    get_detalle_contabilidad_ctrl,
    descargar_xml_ctrl,
    descargar_xmls_ctrl,
    descargar_pdf_ctrl,
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

def _has_uuid(v) -> bool:
    return bool(str(v or "").strip())

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


def _icon_pdf(v) -> str:
    try:
        return "📄" if int(float(v or 0)) == 1 else ""
    except Exception:
        return ""


def _icon_unidades(v) -> str:
    total = _to_float(v)
    if round(total, 6) == 100.0:
        return "☑️"
    if total > 0:
        return "⚠️"
    return ""


def _icon_prepago(concepto: str) -> str:
    concepto = (concepto or "").strip().lower()
    # solo visual; si quieres usar PREPAGO_MAP aquí, lo conectamos luego
    hints = ["hospedaje", "boletos", "hotel", "avión", "avion"]
    return "💳" if any(h in concepto for h in hints) else ""


def _monto_row(r: dict) -> float:
    total_xml = _to_float(r.get("total_xml"))
    if total_xml > 0:
        return total_xml
    return _to_float(r.get("cantidad")) * _to_float(r.get("precio_unitario"))


def mostrar_tab_revisa_contabilidad():
    st.subheader("revisión contabilidad")

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

    s = get_solicitud_ctrl(int(sel_id))
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

    detalle = get_detalle_contabilidad_ctrl(int(sel_id)) or []
    if not detalle:
        st.info("sin detalle")
        return

    df_det = pd.DataFrame(detalle)
                
    if "precio_unitario" in df_det.columns:
        df_det["precio_unitario"] = pd.to_numeric(
            df_det["precio_unitario"], errors="coerce"
        ).fillna(0.0)

    if "fiscales" not in df_det.columns:
        df_det["fiscales"] = 0

    if "uuid" not in df_det.columns:
        df_det["uuid"] = ""

    df_det = pd.DataFrame(detalle)

    if df_det.empty:
        st.info("sin detalle contable")
        return    

    df_det["monto"] = pd.to_numeric(
        df_det.get("total_xml", 0), errors="coerce"
    ).fillna(0.0)
        
    if "tiene_pdf" in df_det.columns:
        df_det["pdf"] = df_det.apply(
            lambda r: "📄" if _requiere_validacion_row(r.to_dict()) and _to_int(r.get("tiene_pdf")) == 1 else "",
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
            "uuid",
            "rfce",
            "proveedor",
            "subtotal_xml",
            "iva_xml",
            "total_xml",
            "moneda",
            "notas",
        ]
        if c in df_det.columns
    ]

    st.markdown("### detalle de gastos")
    st.dataframe(df_det[cols_det], use_container_width=True, hide_index=True)

    total_general = float(df_det["monto"].sum())

    total_fiscal = float(
        df_det.loc[df_det["uuid"].notna() & (df_det["uuid"] != ""), "monto"].sum()
    )

    total_no_fiscal = float(
        df_det.loc[df_det["uuid"].isna() | (df_det["uuid"] == ""), "monto"].sum()
    )
    

    st.markdown("### resumen")
    c1, c2, c3 = st.columns(3)
    c1.metric("total fiscal", _money(total_fiscal))
    c2.metric("total no fiscal", _money(total_no_fiscal))
    c3.metric("total general", _money(total_general))

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

    if pendientes_pdf == 0 and pendientes_un == 0:
        st.success("la solicitud cumple validaciones para pasar a revision comprobacion.")

        if st.button("generar póliza", use_container_width=True):

            from controllers.solicitudes_controller import cambiar_estatus_ctrl

            cambiar_estatus_ctrl(
                int(sel_id),
                "poliza",
                int(usuario.get("id") or 0),
            )

            st.success("estatus actualizado a póliza")
            st.rerun()
    else:
        st.warning("la solicitud aún tiene pendientes antes de pasar a revision comprobacion.")
    
    st.markdown("### documentos")

    uuids = sorted({
        str(r.get("uuid") or "").strip().upper()
        for _, r in df_det.iterrows()
        if str(r.get("uuid") or "").strip()
    })

    if uuids:
        c_zip1, c_zip2 = st.columns([2, 3])

        with c_zip1:
            if st.button("preparar zip xml + pdf", use_container_width=True, key="conta_btn_zip_docs"):
                xml_map = descargar_xmls_ctrl(uuids) or {}

                zip_buffer = BytesIO()

                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
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

                zip_buffer.seek(0)
                st.session_state["conta_zip_docs_bytes"] = zip_buffer.getvalue()
                st.session_state["conta_zip_docs_name"] = f"solicitud_{int(sel_id)}_xml_pdf.zip"

        with c_zip2:
            zip_bytes = st.session_state.get("conta_zip_docs_bytes")
            zip_name = st.session_state.get("conta_zip_docs_name")
            if zip_bytes:
                st.download_button(
                    "descargar zip xml + pdf",
                    data=zip_bytes,
                    file_name=zip_name,
                    mime="application/zip",
                    use_container_width=True,
                    key="conta_download_zip_docs",
                )

    for _, r in df_det.iterrows():
        uuid = str(r.get("uuid") or "").strip().upper()

        if not uuid:
            continue

        xml_bytes, xml_name = descargar_xml_ctrl(uuid)
        pdf_bytes, pdf_name = descargar_pdf_ctrl(uuid)

        c1, c2, c3 = st.columns([3, 1, 1])

        with c1:
            st.write(uuid)

        if xml_bytes:
            with c2:
                xml_filename = (xml_name or f"{uuid}.xml").strip()
                if not xml_filename.lower().endswith(".xml"):
                    xml_filename += ".xml"

                st.download_button(
                    "XML",
                    data=xml_bytes,
                    file_name=xml_filename,
                    mime="text/xml",
                    key=f"xml_{uuid}",
                )

        if pdf_bytes:
            with c3:
                pdf_filename = (pdf_name or f"{uuid}.pdf").strip()
                if not pdf_filename.lower().endswith(".pdf"):
                    pdf_filename += ".pdf"

                st.download_button(
                    "PDF",
                    data=pdf_bytes,
                    file_name=pdf_filename,
                    mime="application/pdf",
                    key=f"pdf_{uuid}",
                )
    
    if pendientes_pdf == 0 and pendientes_un == 0:
        st.success("la solicitud está lista para continuar a la creación de póliza.")
    else:
        st.warning("la solicitud aún tiene pendientes antes de crear la póliza.")