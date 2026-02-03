# tab_registrar_gastos_view.py
import streamlit as st
import pandas as pd
import re
from controllers.presupuesto_controller import *
from controllers.datoscfd_controller import registrar_cfdi_desde_xml
from models.datoscfd_model import guardar_pdf_datoscfd, extraer_uuid_desde_pdf

uuid_re = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def mostrar_tab_registrar_gasto():
    st.title(" registrar gasto")
    st.session_state.setdefault("rg_resultados", None)
    st.session_state.setdefault("rg_doc_idx", 0)

    st.info("busca los comprobantes fiscales (cfdi) para asociarlos a tu presupuesto.")

    # ---------------------------------------------------------------------
    # nuevo: importar xml a DATOSCFD (mysql)
    # ---------------------------------------------------------------------
    # tab_registrar_gastos_view.py
    # cambia tu uploader + botón por este bloque (permite múltiples xml)

    st.subheader("📥 importar xml/pdf a mysql (datoscfd)")

    up_files = st.file_uploader(
        "selecciona uno o varios archivos (xml o pdf)",
        type=["xml", "pdf"],
        accept_multiple_files=True,
        key="rg_uploader_archivos",
    )

    user = st.session_state.get("usuario", {}) or {}
    username = user.get("username") or st.session_state.get("username") or "admin"

    cimp1, cimp2 = st.columns([1.2, 3.0])
    cimp1.text_input("usuario", username, disabled=True, key="rg_show_user_import")

    btn_importar = cimp2.button(
        "importar archivo(s)",
        use_container_width=True,
        key="rg_btn_importar_archivos",
        disabled=(not up_files),
    )

    def _uuid_en_nombre(nombre: str) -> Optional[str]:
        m = uuid_re.search(nombre or "")
        return m.group(0).upper() if m else None

    if btn_importar and up_files:
        xml_inserted = xml_duplicated = xml_updated = 0
        pdf_guardados = 0
        errores = []

        xml_files = [f for f in up_files if (f.name or "").lower().endswith(".xml")]
        pdf_files = [f for f in up_files if (f.name or "").lower().endswith(".pdf")]

        # regla 1: si viene exactamente 1 xml y 1 pdf, el uuid del xml se asigna al pdf
        uuid_par = None
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

                uuid_pdf = extraer_uuid_desde_pdf(b)
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
    # buscador actual (queda igual)
    # ---------------------------------------------------------------------

    with st.form("buscar_gasto"):
        st.subheader("🔍 buscar comprobante fiscal")
        col1, col2, col3 = st.columns(3)
        uuid = col1.text_input("uuid fiscal (obligatorio)", key="rg_uuid").strip().upper()
        folio = col2.text_input("folio (opcional)", key="rg_folio").strip()
        monto = col3.number_input("monto (opcional)", min_value=0.0, step=100.0, key="rg_monto")
        buscar = st.form_submit_button("buscar gasto")

    # --- busqueda ---
    if buscar:
        if not uuid:
            st.error("⚠️ debes capturar un uuid fiscal para continuar.")
        else:
            try:
                res = buscar_gasto_por_uuid(uuid, folio, monto)
                st.session_state["rg_resultados"] = res
                st.session_state["rg_doc_idx"] = 0
            except Exception as e:
                st.error(f"error al buscar: {e}")

    # --- nueva búsqueda ---
    if st.session_state["rg_resultados"] is not None:
        if st.button("🔄 nueva búsqueda", key="rg_nueva_busqueda"):
            st.session_state["rg_resultados"] = None
            st.session_state["rg_doc_idx"] = 0
            st.rerun()

    resultados = st.session_state["rg_resultados"]

    if resultados is not None and not resultados.empty:
        st.success("✅ documento encontrado")

        if len(resultados) > 1:
            st.number_input(
                "coincidencia",
                min_value=0,
                max_value=len(resultados) - 1,
                value=int(st.session_state["rg_doc_idx"]),
                step=1,
                key="rg_doc_idx",
            )

        doc = resultados.iloc[int(st.session_state["rg_doc_idx"])]

        with st.container():
            st.markdown("### 🧾 datos del documento")

            c1, c2, c3, c4 = st.columns([1.5, 3, 1.2, 1.2])
            c1.text_input("folio", str(doc.get("FOLIO", "")), disabled=True, key="rg_show_folio")
            c2.text_input("uuid", str(doc.get("UUID", "")), disabled=True, key="rg_show_uuid")
            c3.text_input("moneda", str(doc.get("MONEDA", "")), disabled=True, key="rg_show_moneda")
            c4.text_input("tipo de cambio", str(doc.get("TIPOCAMBIO", "")), disabled=True, key="rg_show_tc")

            c5, c6, c7 = st.columns(3)
            c5.number_input("total", value=float(doc.get("TOTAL", 0.0) or 0.0), disabled=True, key="rg_show_total")

            fecha_emision = doc.get("FECHA_EMISION")
            if pd.notna(fecha_emision):
                c6.date_input("fecha emisión", pd.to_datetime(fecha_emision).date(), disabled=True, key="rg_show_fecha")
            else:
                c6.text_input("fecha emisión", "", disabled=True, key="rg_show_fecha_txt")

            c7.text_input("serie", str(doc.get("SERIE", "")), disabled=True, key="rg_show_serie")

            st.divider()
            st.markdown("### 📄 datos fiscales del cfdi (ada)")

            col1, col2 = st.columns(2)
            col1.text_input("emisor", str(doc.get("NOMBRE_EMISOR", "")), disabled=True, key="rg_show_emisor")
            col2.text_input("rfc emisor", str(doc.get("RFC_EMISOR", "")), disabled=True, key="rg_show_rfc_emisor")

            col3, col4 = st.columns(2)
            col3.text_input("receptor", str(doc.get("NOMBRE_RECEPTOR", "")), disabled=True, key="rg_show_receptor")
            col4.text_input("rfc receptor", str(doc.get("RFC_RECEPTOR", "")), disabled=True, key="rg_show_rfc_receptor")

            col5, col6 = st.columns(2)
            col5.text_input("forma de pago", str(doc.get("FORMAPAGO", "")), disabled=True, key="rg_show_formapago")
            col6.text_input("uso cfdi", str(doc.get("USOCFDI", "")), disabled=True, key="rg_show_usocfdi")

            st.text_input("lugar de expedición", str(doc.get("LUGAR_EXPEDICION", "")), disabled=True, key="rg_show_lugexp")

        # --- asignar a presupuesto ---
        st.markdown("---")
        st.subheader("📘 asignar a un presupuesto")

        user = st.session_state.get("usuario", {}) or {}
        username = user.get("username") or st.session_state.get("username") or "admin"

        df_pres = get_presupuestos_por_usuario(username)
        df_uni_all = get_presupuestos_por_usuario_unidades(username)
        df_con = get_conceptos_sae()

        if df_pres.empty or df_con.empty:
            st.warning("no hay registros en alguno de los catálogos necesarios.")
        else:
            colp1, colp2, colp3 = st.columns(3)
            pres = colp1.selectbox("presupuesto", df_pres["Nombre"].tolist(), key="rg_sel_pres")

            df_uni = df_uni_all[df_uni_all["Nombre"] == pres]

            if df_uni.empty:
                colp2.info("este presupuesto no tiene unidades asociadas para tu usuario.")
            else:
                unidades_opts = df_uni["Unidad_Negocio"].dropna().unique().tolist()

                unidades_sel = colp2.multiselect(
                    "unidades de negocio",
                    options=unidades_opts,
                    default=[unidades_opts[0]] if unidades_opts else [],
                    key="rg_sel_unis",
                )

                concepto_sel = colp3.selectbox(
                    "tipo de gasto (concepto sae)",
                    df_con["DESCR"].tolist(),
                    key="rg_sel_con",
                )
                num_cpto = df_con.loc[df_con["DESCR"] == concepto_sel, "NUM_CPTO"].values[0]

                moneda = str(doc.get("MONEDA", "") or "").upper().strip()
                total = float(doc.get("TOTAL", 0.0) or 0.0)

                porcentajes = {}
                suma = 0.0

                if len(unidades_sel) == 0:
                    st.warning("selecciona al menos una unidad de negocio.")
                elif len(unidades_sel) == 1:
                    porcentajes[unidades_sel[0]] = 100.0
                    suma = 100.0
                else:
                    st.markdown("#### prorrateo por unidad")
                    st.caption("captura el porcentaje para cada unidad. deben sumar 100.")

                    cols = st.columns(2)
                    for i, uni in enumerate(unidades_sel):
                        with cols[i % 2]:
                            key_pct = f"rg_pct_{pres}_{uni}"
                            st.session_state.setdefault(key_pct, 0.0)
                            pct = st.number_input(
                                f"% {uni}",
                                min_value=0.0,
                                max_value=100.0,
                                step=1.0,
                                value=float(st.session_state[key_pct]),
                                key=key_pct,
                            )
                            porcentajes[uni] = float(pct)
                            suma += float(pct)

                    if abs(suma - 100.0) > 0.01:
                        st.warning(f"la suma de porcentajes es {suma:.2f} y debe ser 100.00")

                if st.button("💾 registrar gasto en presupuesto", use_container_width=True, key="rg_btn_registrar"):
                    if len(unidades_sel) == 0:
                        st.error("debes seleccionar al menos una unidad.")
                    elif abs(suma - 100.0) > 0.01:
                        st.error("los porcentajes deben sumar 100.")
                    else:
                        errores = []
                        ok_total = 0

                        for uni, pct in porcentajes.items():
                            id_detalle = get_id_detalle_presupuesto(pres, uni, username)
                            if not id_detalle:
                                errores.append(f"no se encontró detalle para {uni}.")
                                continue

                            monto_prorrateado = total * (pct / 100.0)

                            monto_mnx = monto_prorrateado if moneda == "MXN" else 0.0
                            monto_usd = monto_prorrateado if moneda == "USD" else 0.0

                            data = {
                                "id_detalle": id_detalle,
                                "nombre_presupuesto": pres,
                                "unidad_negocio": uni,
                                "concepto_descr": concepto_sel,
                                "num_cpto": num_cpto,
                                "uuid": doc.get("UUID"),
                                "app_ada_cfd_doc": int(doc.get("ID_DOCTODIG", 0)),
                                "monto_mnx": float(monto_mnx),
                                "monto_usd": float(monto_usd),
                                "moneda": str(doc.get("MONEDA", "")),
                                "autorizador": "pendiente",
                                "username": username,
                                "porcentaje": float(pct),
                                "monto_original": float(total),
                            }

                            if crear_comprobante_presupuesto(data):
                                ok_total += 1
                            else:
                                errores.append(f"error al registrar para {uni}.")

                        if ok_total > 0 and not errores:
                            st.success("✅ gasto registrado correctamente (prorrateado) con estatus pendiente.")
                        elif ok_total > 0 and errores:
                            st.warning("se registró parcialmente. " + " | ".join(errores))
                        else:
                            st.error("❌ no se pudo registrar el gasto. " + " | ".join(errores))
    else:
        st.info("ingrese un uuid y presione 'buscar gasto' para iniciar.")