# views/modulo_auxiliar_contable/tab_ada_insertaSAE_view.py
import streamlit as st
from datetime import date, timedelta
import pandas as pd
import matplotlib.pyplot as plt
from io import BytesIO
import zipfile
import re
import xml.etree.ElementTree as ET
from reportlab.platypus import Paragraph


from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

from models.sae_model import (
    cargar_conceptos_por_prov,
    insertar_en_sae_por_uso,
    cargar_conceptos_sae,
)
from controllers.ada_controller import (
    cargar_tipos,
    cargar_documentos,
    contar_documentos_cached,
    exportar_excel,
    cargar_proveedores_activos,
    cargar_paga_por_fecha,     # snapshots SAE por rango de fechas
    cargar_compc_por_fecha,    # snapshots SAE por rango de fechas
    cargar_conceptos_por_documento,
    buscar_concep_en_paga_g03,
    cargar_documentos_con_mysql,
    obtener_xml_doctodig,
)

# ---------------------------
# Helpers
# ---------------------------

def _safe_name(value: str) -> str:
    value = str(value or "").strip()
    value = re.sub(r"[^A-Za-z0-9_\-\.]", "_", value)
    return value[:120] or "documento"


def _xml_bytes_to_pdf_bytes(xml_bytes: bytes) -> bytes:
    root = ET.fromstring(xml_bytes.decode("utf-8", errors="ignore").encode("utf-8"))
    ns = {
        "cfdi": "http://www.sat.gob.mx/cfd/4",
        "tfd": "http://www.sat.gob.mx/TimbreFiscalDigital",
    }

    comp = root
    emisor = root.find("cfdi:Emisor", ns)
    receptor = root.find("cfdi:Receptor", ns)
    timbre = root.find(".//tfd:TimbreFiscalDigital", ns)

    def attr(node, name):
        return node.attrib.get(name, "") if node is not None else ""

    uuid = attr(timbre, "UUID")
    fecha = comp.attrib.get("Fecha", "")
    serie = comp.attrib.get("Serie", "")
    folio = comp.attrib.get("Folio", "")
    moneda = comp.attrib.get("Moneda", "")
    subtotal = comp.attrib.get("SubTotal", "")
    total = comp.attrib.get("Total", "")
    metodo = comp.attrib.get("MetodoPago", "")
    forma = comp.attrib.get("FormaPago", "")
    total_impuestos_trasladados = ""
    total_impuestos_retenidos = ""

    impuestos_general = root.find("cfdi:Impuestos", ns)

    if impuestos_general is not None:
        total_impuestos_trasladados = impuestos_general.attrib.get("TotalImpuestosTrasladados", "")
        total_impuestos_retenidos = impuestos_general.attrib.get("TotalImpuestosRetenidos", "")

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("Representación impresa CFDI", styles["Title"]))
    story.append(Spacer(1, 12))

    datos = [
        ["UUID", uuid],
        ["Fecha", fecha],
        ["Serie/Folio", f"{serie} {folio}".strip()],
        ["Moneda", moneda],
        ["Subtotal", subtotal],
        ["Impuestos trasladados", total_impuestos_trasladados],
        ["Impuestos retenidos", total_impuestos_retenidos],
        ["Total", total],
        ["Método de pago", metodo],
        ["Forma de pago", forma],
    ]

    tabla = Table(datos, colWidths=[120, 360])
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(tabla)
    story.append(Spacer(1, 14))

    story.append(Paragraph("Emisor", styles["Heading2"]))
    story.append(Paragraph(f"{attr(emisor, 'Nombre')} - {attr(emisor, 'Rfc')}", styles["Normal"]))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Receptor", styles["Heading2"]))
    story.append(Paragraph(f"{attr(receptor, 'Nombre')} - {attr(receptor, 'Rfc')}", styles["Normal"]))
    story.append(Spacer(1, 14))

    conceptos = []

    for c in root.findall(".//cfdi:Concepto", ns):
        descripcion = c.attrib.get("Descripcion", "")

        conceptos.append([
            c.attrib.get("Cantidad", ""),
            c.attrib.get("ClaveUnidad", ""),
            Paragraph(descripcion, styles["Normal"]),
            c.attrib.get("ValorUnitario", ""),
            c.attrib.get("Importe", ""),
        ])

        lineas_imp = []

        traslados = c.findall(".//cfdi:Traslado", ns)
        for t_imp in traslados:
            lineas_imp.append(
                "Traslado: "
                f"Base {t_imp.attrib.get('Base', '')} | "
                f"Impuesto {t_imp.attrib.get('Impuesto', '')} | "
                f"Factor {t_imp.attrib.get('TipoFactor', '')} | "
                f"Tasa {t_imp.attrib.get('TasaOCuota', '')} | "
                f"Importe {t_imp.attrib.get('Importe', '')}"
            )

        retenciones = c.findall(".//cfdi:Retencion", ns)
        for r_imp in retenciones:
            lineas_imp.append(
                "Retención: "
                f"Base {r_imp.attrib.get('Base', '')} | "
                f"Impuesto {r_imp.attrib.get('Impuesto', '')} | "
                f"Factor {r_imp.attrib.get('TipoFactor', '')} | "
                f"Tasa {r_imp.attrib.get('TasaOCuota', '')} | "
                f"Importe {r_imp.attrib.get('Importe', '')}"
            )

        if lineas_imp:
            conceptos.append([
                "",
                "",
                Paragraph("<br/>".join(lineas_imp), styles["Normal"]),
                "",
                "",
            ])

    if conceptos:
        story.append(Paragraph("Conceptos", styles["Heading2"]))

        data = [["Cantidad", "Unidad", "Descripción", "V. unitario", "Importe"]] + conceptos

        t = Table(data, colWidths=[55, 55, 310, 70, 70])

        estilos = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]

        # combina columnas en los renglones de impuestos
        for idx, row in enumerate(data):
            if idx == 0:
                continue

            cantidad = str(row[0] or "").strip()
            unidad = str(row[1] or "").strip()
            descripcion = row[2]

            if cantidad == "" and unidad == "":
                estilos.append(("SPAN", (2, idx), (4, idx)))
                estilos.append(("BACKGROUND", (0, idx), (-1, idx), colors.whitesmoke))
                estilos.append(("TEXTCOLOR", (2, idx), (4, idx), colors.darkgrey))

        t.setStyle(TableStyle(estilos))
        story.append(t)

    doc.build(story)
    return buffer.getvalue()

def _default_dates():
    hoy = date.today()
    first_this = hoy.replace(day=1)
    last_prev = first_this - timedelta(days=1)
    first_prev = last_prev.replace(day=1)
    return first_prev, hoy

def _norm_rfc(x: str) -> str:
    return (str(x) if x is not None else "").strip().upper()[:13]

def _cve_match(clave: str | None) -> str:
    base = (clave or "").strip() or "0001"
    return base.rjust(10)[:10]

def _to_num_2(x):
    try:
        return round(float(str(x).replace(",", "").replace("$", "")), 2)
    except Exception:
        return 0.0

def _first_series(dframe: pd.DataFrame, candidates):
    for c in candidates:
        if c in dframe.columns:
            return dframe[c]
    return pd.Series(index=dframe.index, dtype="object")

def _first_col(df_: pd.DataFrame, candidates: list[str]) -> str | None:
    for c in candidates:
        if c in df_.columns:
            return c
    return None

def _style_en_sae(series: pd.Series) -> list[str]:
    styles = []
    for v in series:
        if bool(v):
            styles.append("background-color:#ffe082; color:black;")  # amarillo suave
        else:
            styles.append("")
    return styles

def _obtener_xml_documento(row):
    id_doctodig = row.get("ID_DOCTODIG")

    if pd.isna(id_doctodig):
        raise ValueError("el documento no tiene ID_DOCTODIG")

    return obtener_xml_doctodig(st.secrets, int(id_doctodig))

def insertarSAE():
    # --- defaults pedidos ---
    fdef_desde, fdef_hasta = _default_dates()

    col_f1, col_f2, col_rfc, col_nom, col_folio, col_tipo, col_rfc_rec = st.columns([1,1,1,1,1,1,1])
    with col_f1:
        f_desde = st.date_input("desde", value=fdef_desde, format="YYYY-MM-DD")
    with col_f2:
        f_hasta = st.date_input("hasta", value=fdef_hasta, format="YYYY-MM-DD")
    with col_rfc:
        rfc = st.text_input("rfc emisor", value="")
    with col_nom:
        nombre = st.text_input("nombre emisor", value="")
    with col_folio:
        folio = st.text_input("folio", value="")
    with col_rfc_rec:
        rfc_rec = st.text_input("rfc receptor", value="BIO870307QD0")

    tipos = ["(todos)"]
    try:
        tipos += cargar_tipos(st.secrets)
    except Exception as e:
        st.warning(f"no se pudieron cargar tipos: {e}")
    idx_tipo = tipos.index("Ingreso") if "Ingreso" in tipos else 0
    with col_tipo:
        tipo = st.selectbox("tipo", tipos, index=idx_tipo)

    filtros = {
        "fecha_desde": str(f_desde) if f_desde else None,
        "fecha_hasta": str(f_hasta) if f_hasta else None,
        "rfc_emisor": rfc.strip() or None,
        "nombre_emisor": nombre.strip() or None,
        "folio": folio.strip() or None,
        "tipo": None if tipo == "(todos)" else tipo,
        "rfc_receptor": rfc_rec.strip() or None,
    }

    # contar
    try:
        total = contar_documentos_cached(st.secrets, filtros)
    except Exception as e:
        st.error(f"error al contar documentos: {e}")
        return

    # paginación (default: Todas)
    c1, c2, c3 = st.columns([1,1,2])
    with c1:
        page_size_opt = st.selectbox("tamaño página", [200, 500, 1000, "Todas"], index=3)
    with c2:
        page = st.number_input("página", min_value=1, value=1, step=1, disabled=(page_size_opt == "Todas"))
    with c3:
        if st.button("buscar", use_container_width=True, key="btn_buscar"):
            st.cache_data.clear()

    page_size = total if page_size_opt == "Todas" else int(page_size_opt)

    # cargar ADA
    try:
        df = cargar_documentos_con_mysql(st.secrets, filtros, page, page_size)

        # solo G03
        if not df.empty:
            col_usocfdi = next((c for c in df.columns if c.lower() == "usocfdi_"), None)
            if col_usocfdi:
                df = df[df[col_usocfdi].astype(str).str.strip().str.upper() == "G03"].copy()
    except Exception as e:
        st.error(f"error al cargar documentos: {e}")
        return

    if df.empty:
        st.info("sin resultados con los filtros actuales")
        return

    # formateo visible
    if "TOTAL" in df.columns:
        df["TOTAL"] = df["TOTAL"].map(lambda x: f"{x:,.2f}")
    if "TOTAL_MXN" in df.columns:
        df["TOTAL_MXN"] = df["TOTAL_MXN"].map(lambda x: f"{x:,.2f}")

    # RFC → CLAVE_PROV_SAE (activos) y marcado rojo
    try:
        prov_activos = cargar_proveedores_activos(st.secrets)  # {RFC: CLAVE}
    except Exception as e:
        prov_activos = {}
        st.warning(f"no se pudieron cargar proveedores activos de SAE: {e}")

    df["RFC_NORM"] = df["RFC_EMISOR"].apply(_norm_rfc) if "RFC_EMISOR" in df.columns else ""
    df["CLAVE_PROV_SAE"] = df["RFC_NORM"].map(prov_activos).fillna("")

    # llaves de comparación ADA
    df["REFER_MATCH"] = (
        df["SERIE"].fillna("").astype(str).str.strip() +
        df["FOLIO"].fillna("").astype(str).str.strip()
    ).str.upper().str.slice(0, 20)
    df["CVE_PROV_MATCH"] = df.get("CLAVE_PROV_SAE", "").apply(_cve_match)

    uso_series = _first_series(df, ["uso_cfdi", "USO_CFDI", "USOCFDI", "USOCFDI_"]).fillna("").astype(str)
    df["DESTINO_SAE"] = uso_series.str.upper().map(
        lambda u: "COMPC01" if u.startswith("G01") else ("PAGA_M01" if u.startswith("G03") else "")
    )

    # llaves ADA para match por APP_UUID
    df["_UUID_ADA"] = df.get("UUID", "").astype(str).str.upper().str.strip()

    # snapshots SAE por fecha (todo en rango)
    f_ini = pd.to_datetime(filtros.get("fecha_desde")).date() if filtros.get("fecha_desde") else None
    f_fin = pd.to_datetime(filtros.get("fecha_hasta")).date() if filtros.get("fecha_hasta") else None

    paga_raw = cargar_paga_por_fecha(st.secrets, f_ini, f_fin)
    compc_raw = cargar_compc_por_fecha(st.secrets, f_ini, f_fin)  # se sigue cargando por si lo usas en otros lados

    # ---------------------------
    # match único: uuid (ada) vs app_uuid (paga_m01)
    # + traer refer/no_factura/docto desde paga_raw
    # ---------------------------
    df_cmp = df.copy()

    st.markdown("#### Descarga de XML y PDF")
    if st.button("generar ZIP con XML y PDF", key="btn_zip_xml_pdf"):
        zip_buffer = BytesIO()
        errores = []

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
            for _, row in df_cmp.iterrows():
                try:
                    xml_bytes = _obtener_xml_documento(row)

                    uuid = row.get("UUID", "")
                    folio = row.get("FOLIO", "")
                    nombre_base = _safe_name(uuid or folio or row.get("ID_DOCTODIG"))

                    zipf.writestr(f"{nombre_base}.xml", xml_bytes)

                    pdf_bytes = _xml_bytes_to_pdf_bytes(xml_bytes)
                    zipf.writestr(f"{nombre_base}.pdf", pdf_bytes)

                except Exception as e:
                    errores.append(f"{row.get('ID_DOCTODIG')} - {e}")

        if errores:
            st.warning("algunos documentos no se pudieron generar.")
            st.text("\n".join(errores[:20]))

        st.download_button(
            label="descargar XML y PDF",
            data=zip_buffer.getvalue(),
            file_name=f"documentos_ada_xml_pdf_{f_desde}_{f_hasta}.zip",
            mime="application/zip",
            key="btn_download_zip_xml_pdf",
        )



    # ordenar por fecha desc (y desempate por id)

    if paga_raw is None or paga_raw.empty:
        df_cmp["EN_SAE"] = False
        df_cmp["REFER_SAE"] = None
        df_cmp["NO_FACTURA_SAE"] = None
        st.caption(f"ya insertados en sae (por app_uuid en paga_m01): 0 de {len(df_cmp)}")
    else:
        col_app = _first_col(paga_raw, ["APP_UUID", "APP_UUID ", "APPUUID"])
        col_ref = _first_col(paga_raw, ["REFER", "REFERENCIA", "REF_SIST", "REF_SIST ", "REF"])
        col_nf  = _first_col(paga_raw, ["NO_FACTURA", "NOFACTURA", "FACTURA", "NO_FAC"])
        col_doc = _first_col(paga_raw, ["DOCTO", "DOCUMENTO", "DOC", "NO_DOCTO"])

        if col_app is None:
            df_cmp["EN_SAE"] = False
            df_cmp["REFER_SAE"] = None
            df_cmp["NO_FACTURA_SAE"] = None
            st.caption(f"ya insertados en sae (por app_uuid en paga_m01): 0 de {len(df_cmp)}")
        else:
            p = paga_raw.copy()
            p["_APP_UUID_N"] = p[col_app].astype(str).str.upper().str.strip()

            # refer
            if col_ref is not None:
                p["_REFER_N"] = p[col_ref].astype(str).str.upper().str.strip().str.slice(0, 20)
            else:
                p["_REFER_N"] = ""

            # no_factura / docto
            if col_nf is not None:
                p["_NF_N"] = p[col_nf].astype(str).str.upper().str.strip()
            else:
                p["_NF_N"] = ""
            if col_doc is not None:
                p["_DOC_N"] = p[col_doc].astype(str).str.upper().str.strip()
            else:
                p["_DOC_N"] = ""

            p = (
                p[p["_APP_UUID_N"].ne("")][["_APP_UUID_N", "_REFER_N", "_NF_N", "_DOC_N"]]
                .drop_duplicates(subset=["_APP_UUID_N"], keep="first")
                .set_index("_APP_UUID_N")
            )

            df_cmp["EN_SAE"] = df_cmp["_UUID_ADA"].isin(p.index)

            # refer_sae: si existe match, mapea; si no, None
            df_cmp["REFER_SAE"] = df_cmp["_UUID_ADA"].map(p["_REFER_N"]).where(df_cmp["EN_SAE"], None)

            # no_factura_sae: no_factura si existe, si no docto
            nf = df_cmp["_UUID_ADA"].map(p["_NF_N"]).fillna("").astype(str).str.strip()
            dc = df_cmp["_UUID_ADA"].map(p["_DOC_N"]).fillna("").astype(str).str.strip()
            df_cmp["NO_FACTURA_SAE"] = nf.where(nf.ne(""), dc).where(df_cmp["EN_SAE"], None)

            n_ya = int(df_cmp["EN_SAE"].sum())
            st.caption(f"ya insertados en sae (por app_uuid en paga_m01): {n_ya} de {len(df_cmp)}")

    # formapago / metodopago (soporta varias llaves) -> sobre df_cmp
    fp = _first_series(df_cmp, ["FORMAPAGO", "FORMA_PAGO", "FORMADEPAGO", "forma_pago"]).fillna("")
    mp = _first_series(df_cmp, ["METODOPAGO", "METODO_PAGO", "METODODEPAGO", "metodo_pago"]).fillna("")
    df_cmp["FORMAPAGO"] = fp.astype(str).str.strip().str.upper()
    df_cmp["METODOPAGO"] = mp.astype(str).str.strip().str.upper()

    # columna de selección
    df_cmp["INSERTAR"] = False

    def _style_rfc(series: pd.Series) -> list[str]:
        styles = []
        for raw in series:
            r = _norm_rfc(raw)
            if not r or r not in prov_activos:
                styles.append("background-color:#e53935; color:white;")
            else:
                styles.append("")
        return styles

    # mostrar/ocultar gráficas (default: ocultas)
    st.session_state.setdefault("mostrar_graficas_ada", False)

    colg1, colg2 = st.columns([1, 6])
    with colg1:
        if st.button(
            "📈 mostrar gráficas" if not st.session_state["mostrar_graficas_ada"] else "🙈 ocultar gráficas",
            key="btn_toggle_graficas_ada",
            use_container_width=True,
        ):
            st.session_state["mostrar_graficas_ada"] = not st.session_state["mostrar_graficas_ada"]

    if st.session_state["mostrar_graficas_ada"]:
        st.markdown("## gráficas")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("#### documentos por día")
            grafica_por_dia(df_cmp)
        with col2:
            st.markdown("#### montos por día")
            grafica_montos_por_dia(df_cmp)

    # asegurar tipos antes de mostrar
    if "ID_DOCTODIG" in df_cmp.columns:
        df_cmp["ID_DOCTODIG"] = pd.to_numeric(df_cmp["ID_DOCTODIG"], errors="coerce").astype("Int64")

    visible_cols = [
        "DESTINO_SAE","INSERTAR","EN_SAE","FECHA_EMISION","CVE_PROV_MATCH","CLAVE_PROV_SAE",
        "RFC_EMISOR","NOMBRE_EMISOR","SERIE","FOLIO",
        "MONEDA","TOTAL","TIPOCAMBIO","TOTAL_MXN","USOCFDI_","UUID","METODOPAGO","FORMAPAGO",
        "REFER_SAE","ID_DOCTODIG", "TIPOCOMPROBANTE"
    ]
    visible_cols = [c for c in visible_cols if c in df_cmp.columns]

    st.markdown("### documentos ada")

    # dejar solo INSERTAR editable
    disabled_cols = [c for c in visible_cols if c != "INSERTAR"]

    # ordenar por fecha desc
    if "FECHA_EMISION" in df_cmp.columns:
        df_cmp = df_cmp.sort_values(
            by="FECHA_EMISION",
            ascending=False
        )
    
    if "FECHA_EMISION" in df_cmp.columns:
        df_cmp["_FECHA_SORT"] = pd.to_datetime(df_cmp["FECHA_EMISION"], errors="coerce")
        df_cmp = df_cmp.sort_values("_FECHA_SORT", ascending=False).drop(columns=["_FECHA_SORT"])
        
    sty = df_cmp[visible_cols].style
    if "RFC_EMISOR" in visible_cols:
        sty = sty.apply(_style_rfc, subset=["RFC_EMISOR"])
    if "EN_SAE" in visible_cols:
        sty = sty.apply(_style_en_sae, subset=["EN_SAE"])
    
    df_edit = st.data_editor(
        sty,
        hide_index=True,
        use_container_width=True,
        disabled=disabled_cols,
        key="ada_editor_insercion",
        height=min(900, 120 + 34 * len(df_cmp)),
    )

    # ----------------------------------------
    # documento seleccionado via columna INSERTAR
    # ----------------------------------------
    st.divider()
    st.markdown("### detalle y concepto para el documento seleccionado")

    doc_sel = None
    if "INSERTAR" in df_edit.columns:
        mask_sel = df_edit["INSERTAR"] == True
        if mask_sel.any():
            if mask_sel.sum() > 1:
                st.info("hay varias filas marcadas; tomando la primera.")
            idx_sel = df_edit[mask_sel].index[0]
            doc_sel = df_cmp.loc[idx_sel]

    if doc_sel is None:
        st.info("marca la casilla insertar de un documento para ver su detalle.")
        return

    st.write(
        f"id_doctodig: {doc_sel.get('ID_DOCTODIG')} | "
        f"proveedor: {doc_sel.get('NOMBRE_EMISOR')} | "
        f"folio: {doc_sel.get('FOLIO')} | "
        f"uuid: {doc_sel.get('UUID')}"
    )

    # ---------------------------
    # conceptos ada del documento
    # ---------------------------
    try:
        id_docto_dig = int(doc_sel.get("ID_DOCTODIG"))
        df_det = cargar_conceptos_por_documento(st.secrets, id_docto_dig)
    except Exception as e:
        st.error(f"error al cargar conceptos de ada: {e}")
        df_det = pd.DataFrame()

    if df_det.empty:
        st.info("no se encontraron conceptos en ada para este documento.")
    else:
        cols_montos = [
            "VALORUNITARIO", "DESCUENTO", "IMPORTE", "BASE_IVA",
            "IVA", "IEPS", "IVA_RET", "IEPS_RET", "ISR"
        ]
        for col in cols_montos:
            if col in df_det.columns:
                df_det[col] = pd.to_numeric(df_det[col], errors="coerce").fillna(0)

        orden_cols = [
            "CLAVEPRODSERV", "NO_IDENTIFICACION", "DESCRIPCION",
            "CANTIDAD", "CLAVEUNIDAD", "UNIDAD",
            "VALORUNITARIO", "DESCUENTO", "IMPORTE",
            "OBJETOIMP", "BASE_IVA", "IVA", "IEPS",
            "IVA_RET", "IEPS_RET", "ISR"
        ]
        orden_cols = [c for c in orden_cols if c in df_det.columns]

        st.markdown("#### conceptos ada")
        st.dataframe(
            df_det[orden_cols],
            use_container_width=True,
            hide_index=True,
        )

    # ---------------------------
    # concepto sae: sugerencia + catálogo completo
    # ---------------------------
    st.markdown("#### concepto sae")

    # sugerencia
    try:
        col_uso_local = next(
            (c for c in ["uso_cfdi","USO_CFDI","USOCFDI","USOCFDI_"] if c in df_cmp.columns),
            None,
        )
        uso_cfdi_val = str(doc_sel.get(col_uso_local, "") or "").strip()

        rfc_receptor = str(doc_sel.get("RFC_RECEPTOR", "") or "").strip()
        clave_prov   = str(doc_sel.get("CVE_PROV_MATCH", "") or "").strip()
        serie        = str(doc_sel.get("SERIE", "") or "").strip()
        folio_doc    = str(doc_sel.get("FOLIO", "") or "").strip()




        total_mxn = doc_sel.get("TOTAL_MXN", 0.0)
        try:
            total_mxn = float(str(total_mxn).replace(",", "").replace("$", ""))
        except Exception:
            total_mxn = 0.0

        res_cptos = buscar_concep_en_paga_g03(
            st.secrets,
            uso_cfdi_val,
            rfc_receptor,
            clave_prov,
            serie,
            folio_doc,
            total_mxn,
        )
    except Exception as e:
        st.error(f"error al detectar concepto en sae: {e}")
        res_cptos = None

    if isinstance(res_cptos, pd.DataFrame):
        df_cptos_sug = res_cptos.copy()
    elif isinstance(res_cptos, (list, tuple)):
        df_cptos_sug = pd.DataFrame(res_cptos)
    elif isinstance(res_cptos, dict):
        df_cptos_sug = pd.DataFrame([res_cptos])
    else:
        df_cptos_sug = pd.DataFrame()

    num_cpto_sugerido = None
    if not df_cptos_sug.empty and "NUM_CPTO" in df_cptos_sug.columns:
        try:
            num_cpto_sugerido = int(df_cptos_sug.iloc[0]["NUM_CPTO"])
        except Exception:
            num_cpto_sugerido = None

        st.caption("sugerencias encontradas por la lógica existente")
        st.dataframe(df_cptos_sug, use_container_width=True, hide_index=True)
    else:
        st.info("no se encontró un concepto sugerido; usa el catálogo de conceptos.")

    # catálogo completo
    try:
        df_cat = cargar_conceptos_sae(st.secrets)
    except Exception as e:
        st.error(f"error al cargar catálogo de conceptos de sae: {e}")
        df_cat = pd.DataFrame()

    concepto_elegido = None
    num_cpto_sel = None

    if df_cat.empty:
        st.warning("no se pudo obtener el catálogo de conceptos de sae.")
        return

    nombre_col = "NOMBRE_CPTO" if "NOMBRE_CPTO" in df_cat.columns else ("DESCR" if "DESCR" in df_cat.columns else None)
    if "NUM_CPTO" not in df_cat.columns or nombre_col is None:
        st.error("el catálogo de conceptos no tiene columnas NUM_CPTO y descripción esperadas.")
        return

    df_cat = df_cat.copy().reset_index(drop=True)
    opciones = df_cat.apply(lambda x: f"{x['NUM_CPTO']} - {x.get(nombre_col, '')}", axis=1).tolist()

    idx_default = 0
    if num_cpto_sugerido is not None:
        coincidencias = df_cat.index[df_cat["NUM_CPTO"] == num_cpto_sugerido].tolist()
        if coincidencias:
            idx_default = coincidencias[0]

    concepto_elegido = st.selectbox(
        "elige concepto de sae (se preselecciona el sugerido si existe):",
        opciones,
        index=idx_default,
    )
    num_cpto_sel = int(concepto_elegido.split("-")[0].strip())
    st.caption(f"concepto seleccionado: {concepto_elegido}")

    with st.expander("ver catálogo completo de conceptos sae"):
        st.dataframe(df_cat, use_container_width=True, hide_index=True)

    # ----------------------------------------
    # inserción en PAGA_M01 usando el concepto elegido
    # ----------------------------------------
    st.markdown("#### insertar movimiento en paga_m01")

    if st.button("insertar en paga_m01", key="btn_insertar_paga_m01"):
        col_uso_local = next(
            (c for c in ["uso_cfdi","USO_CFDI","USOCFDI","USOCFDI_"] if c in df_cmp.columns),
            None,
        )
        uso_cfdi_val = str(doc_sel.get(col_uso_local, "") or "").strip()

        rfc_emisor = doc_sel.get("RFC_EMISOR")
        serie = doc_sel.get("SERIE")
        folio_doc = doc_sel.get("FOLIO")
        fecha_emision = doc_sel.get("FECHA_EMISION")
        total_mxn = doc_sel.get("TOTAL_MXN")
        uuid = doc_sel.get("UUID")
        clave_prov = doc_sel.get("CVE_PROV_MATCH")
        id_docto_dig = doc_sel.get("ID_DOCTODIG")
        moneda = doc_sel.get("MONEDA", "MXN")
        tcambio = doc_sel.get("TIPOCAMBIO", 1.0)
        impext = doc_sel.get("TOTAL", 0.0)

        try:
            res = insertar_en_sae_por_uso(
                st.secrets,
                uso_cfdi_val,
                rfc_emisor=rfc_emisor,
                serie=serie,
                folio=folio_doc,
                fecha_emision=fecha_emision,
                total_mxn=total_mxn,
                uuid=uuid,
                clave_prov=clave_prov,
                id_docto_dig=id_docto_dig,
                moneda=moneda,
                tcambio=tcambio,
                impext=impext,
                num_cpto_manual=num_cpto_sel,
                concepto_label=concepto_elegido,
            )
            if res.get("ok"):
                st.success(f"movimiento insertado en paga_m01. folio: {res.get('folio_num')}")
            else:
                st.error(f"error al insertar en sae: {res.get('msg')}")
        except Exception as e:
            st.error(f"error al llamar insertar_en_sae_por_uso: {e}")

    # refresco
    st.divider()
    col_ref, _ = st.columns([1, 5])
    with col_ref:
        if st.button("🔄 refrescar datos", key="btn_refrescar_despues"):
            st.cache_data.clear()
            st.rerun()

    # exportar
    col_a, _ = st.columns([1,3])
    with col_a:
        if st.button("exportar a excel", key="btn_exportar"):
            try:
                df_export = df_cmp[visible_cols].copy()
                xlsx = exportar_excel(df_export)
                st.download_button(
                    "descargar documentos.xlsx",
                    data=xlsx,
                    file_name="documentos_ada.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="btn_descarga_xlsx"
                )
            except Exception as e:
                st.error(f"no se pudo exportar: {e}")

# ---------------------------
# Gráficas
# ---------------------------
def grafica_por_dia(df: pd.DataFrame):
    if "FECHA_EMISION" not in df.columns or df.empty:
        return
    df = df.copy()
    df["FECHA_EMISION"] = pd.to_datetime(df["FECHA_EMISION"], errors="coerce")
    df["DIA_NUM"] = df["FECHA_EMISION"].dt.dayofweek
    nombres = {0:"Lunes",1:"Martes",2:"Miércoles",3:"Jueves",4:"Viernes",5:"Sábado",6:"Domingo"}
    df["DIA_SEMANA"] = df["DIA_NUM"].map(nombres)
    conteo = df["DIA_SEMANA"].value_counts().reindex(nombres.values())

    fig, ax = plt.subplots(figsize=(8, 4))
    conteo.plot(kind="bar", ax=ax)
    ax.set_title("Documentos por día de la semana", fontsize=10)
    ax.set_xlabel("Día", fontsize=10)
    ax.set_ylabel("Cantidad de documentos", fontsize=10)
    ax.tick_params(axis="x", labelsize=8)
    ax.tick_params(axis="y", labelsize=8)
    for patch in ax.patches:
        altura = patch.get_height()
        if pd.notna(altura):
            ax.text(patch.get_x()+patch.get_width()/2, altura+1, f"{int(altura)}", ha="center", va="bottom", fontsize=10)
    st.pyplot(fig)

def grafica_montos_por_dia(df: pd.DataFrame):
    if df.empty or "FECHA_EMISION" not in df.columns or "TOTAL_MXN" not in df.columns:
        return
    df = df.copy()
    df["FECHA_EMISION"] = pd.to_datetime(df["FECHA_EMISION"], errors="coerce")
    nombres = {0:"Lunes",1:"Martes",2:"Miércoles",3:"Jueves",4:"Viernes",5:"Sábado",6:"Domingo"}
    df["DIA_SEMANA"] = df["FECHA_EMISION"].dt.dayofweek.map(nombres)
    if df["TOTAL_MXN"].dtype == object:
        df["TOTAL_MXN"] = df["TOTAL_MXN"].astype(str).str.replace(",", "", regex=False).str.replace("$", "", regex=False)
    df["TOTAL_MXN"] = pd.to_numeric(df["TOTAL_MXN"], errors="coerce").fillna(0.0)
    orden = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"]
    serie = df.groupby("DIA_SEMANA", dropna=False)["TOTAL_MXN"].sum().reindex(orden).fillna(0.0)

    fig, ax = plt.subplots(figsize=(9, 4.5))
    barras = ax.bar(serie.index.tolist(), serie.values)
    ax.set_title("monto total por día de la semana", fontsize=14)
    ax.set_xlabel("día", fontsize=12)
    ax.set_ylabel("monto", fontsize=12)
    ax.tick_params(axis="x", labelsize=10)
    ax.tick_params(axis="y", labelsize=10)
    for rect, val in zip(barras, serie.values):
        ax.text(rect.get_x()+rect.get_width()/2.0, rect.get_height()+(0.01*(serie.max() if serie.max() else 1)), f"{val:,.2f}", ha="center", va="bottom", fontsize=10)
    st.pyplot(fig)

def grafica_resumen_tabla(resumen: pd.DataFrame, top_prov: int = 10):
    st.markdown("### Proveedores con más conceptos distintos (Resumen)")
    if resumen is None or resumen.empty:
        st.info("Sin datos en Resumen para graficar.")
        return
    req = {"NOMBRE_PROV", "N_CONCEPTOS"}
    if not req.issubset(resumen.columns):
        st.warning(f"Resumen no contiene columnas {sorted(req)}")
        return

    top = (resumen[["NOMBRE_PROV","N_CONCEPTOS"]]
           .sort_values("N_CONCEPTOS", ascending=False)
           .head(int(top_prov)))

    if top.empty:
        st.info("No hay datos para graficar.")
        return

    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.bar(top["NOMBRE_PROV"], top["N_CONCEPTOS"])
    ax.set_title("N.º de conceptos distintos por proveedor", fontsize=12)
    ax.set_xlabel("Proveedor", fontsize=10)
    ax.set_ylabel("Conceptos distintos", fontsize=10)
    ax.tick_params(axis="x", labelrotation=90, labelsize=9)

    for x, y in zip(top["NOMBRE_PROV"], top["N_CONCEPTOS"]):
        ax.text(x, y + max(1, top["N_CONCEPTOS"].max()*0.01), str(int(y)), ha="center", va="bottom", fontsize=9)

    st.pyplot(fig)

def grafica_detalle_tabla(detalle: pd.DataFrame, top_prov: int = 10, top_conc: int = 8):
    st.markdown("### Distribución de USOS por proveedor y concepto (Detalle)")
    if detalle is None or detalle.empty:
        st.info("Sin datos en Detalle para graficar.")
        return
    req = {"NOMBRE_PROV", "DESCR", "USOS"}
    if not req.issubset(detalle.columns):
        st.warning(f"Detalle no contiene columnas {sorted(req)}")
        return

    det = detalle.copy()
    det["USOS"] = pd.to_numeric(det["USOS"], errors="coerce").fillna(0)

    top_proveedores = (det.groupby("NOMBRE_PROV", as_index=False)["USOS"].sum()
                         .sort_values("USOS", ascending=False)
                         .head(int(top_prov)))["NOMBRE_PROV"].tolist()
    det = det[det["NOMBRE_PROV"].isin(top_proveedores)]
    if det.empty:
        st.info("No hay suficientes datos tras filtrar por top proveedores.")
        return

    top_conceptos = (det.groupby("DESCR", as_index=False)["USOS"].sum()
                       .sort_values("USOS", ascending=False)
                       .head(int(top_conc)))["DESCR"].tolist()
    det = det[det["DESCR"].isin(top_conceptos)]
    if det.empty:
        st.info("No hay suficientes datos tras filtrar por top conceptos.")
        return

    pivot = det.pivot_table(index="NOMBRE_PROV", columns="DESCR", values="USOS", aggfunc="sum", fill_value=0)
    pivot = pivot.sort_index()

    fig, ax = plt.subplots(figsize=(11, 5))
    bottom = None
    for col in pivot.columns:
        vals = pivot[col].values
        ax.bar(pivot.index, vals, bottom=bottom, label=col)
        bottom = vals if bottom is None else (bottom + vals)

    ax.set_title("USOS por proveedor y concepto", fontsize=12)
    ax.set_xlabel("Proveedor", fontsize=10)
    ax.set_ylabel("USOS", fontsize=10)
    ax.tick_params(axis="x", labelrotation=90, labelsize=9)
    ax.legend(title="Concepto", fontsize=8, title_fontsize=9, bbox_to_anchor=(1.02, 1), loc="upper left")

    st.pyplot(fig)