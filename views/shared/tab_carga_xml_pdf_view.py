# views/shared/tab_carga_xml_pdf_view.py
from __future__ import annotations

import re
from typing import Optional

import streamlit as st

from controllers.datoscfd_controller import registrar_cfdi_desde_xml
from models.datoscfd_model import extraer_uuid_desde_pdf, guardar_pdf_datoscfd

UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)

_HYPHENS = "‐‑‒–—−"


def _normaliza_texto_uuid(s: str) -> str:
    if not s:
        return ""
    s = str(s).strip()
    for h in _HYPHENS:
        s = s.replace(h, "-")
    return re.sub(r"\s+", "", s)


def _uuid_en_texto(texto: str) -> Optional[str]:
    t = _normaliza_texto_uuid(texto)
    m = UUID_RE.search(t)
    return m.group(0).upper() if m else None


def _uuid_en_nombre(nombre: str) -> Optional[str]:
    return _uuid_en_texto(nombre or "")


def mostrar_tab_carga_xml_pdf(key_prefix: str = "cxp"):
    st.subheader("carga xml/pdf")

    up_files = st.file_uploader(
        "selecciona uno o varios archivos (xml o pdf)",
        type=["xml", "pdf"],
        accept_multiple_files=True,
        key=f"{key_prefix}_uploader_archivos",
    )

    user = st.session_state.get("usuario", {}) or {}
    username = user.get("username") or st.session_state.get("username") or "admin"

    cimp1, cimp2 = st.columns([1.2, 3.0])
    cimp1.text_input("usuario", username, disabled=True, key=f"{key_prefix}_show_user_import")

    btn_importar = cimp2.button(
        "importar archivo(s)",
        use_container_width=True,
        key=f"{key_prefix}_btn_importar_archivos",
        disabled=(not up_files),
    )

    if btn_importar and up_files:
        xml_inserted = xml_duplicated = xml_updated = 0
        pdf_guardados = 0
        errores = []

        xml_files = [f for f in up_files if (f.name or "").lower().endswith(".xml")]
        pdf_files = [f for f in up_files if (f.name or "").lower().endswith(".pdf")]

        uuid_par = None

        if len(xml_files) == 1 and len(pdf_files) == 1:
            try:
                rxml = registrar_cfdi_desde_xml(
                    xml_bytes=xml_files[0].getvalue(),
                    username=username,
                )
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
