#tab_prorrateos_config_view.py

import streamlit as st
import pandas as pd
from decimal import Decimal
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode

from controllers.dashboard_controller import (
    get_prorrateos_mysql_df,
    get_detalle_prorrateo_df,
    guardar_detalle_prorrateo,
    actualizar_estatus_prorrateos,
    get_conceptos_aspel_df,
    get_prov_nombres_sae_dict,
    crear_prorrateo_cabecera_ctrl,
    get_unidades_prorrateo_ctrl,
    get_cuentas_contables_coi_ctrl,
    insertar_detalle_prorrateo_ctrl,
    actualizar_concepto_prorrateo_ctrl,
)

def mostrar_tab_prorrateos_mysql():
    st.subheader("tabla prorrateos (mysql_bio)")
    # -------------------------
    # filtros (sin límite / offset)
    # -------------------------
    c1, c2, c3 = st.columns([2, 2, 2])
    nombre_like = c1.text_input(
        "nombre contiene (prorrateo)", value="", key="nombre_like_prorrateos"
    )
    prov_nombre_like = c2.text_input(
        "proveedor (nombre contiene)", value="", key="prov_nombre_like_prorrateos"
    )
    prov_codigo = c3.text_input(
        "proveedor (cdcvepro exacto)", value="", key="proveedor_prorrateos"
    )

    c4, c5 = st.columns([2, 1])
    concepto = c4.text_input(
        "concepto sae (id)", value="", key="concepto_prorrateos"
    )
    activo = c5.selectbox(
        "activo", options=["(todos)", "1", "0"], index=0, key="activo_prorrateos"
    )

    filtros: dict[str, str] = {}

    # nombre del prorrateo
    if nombre_like.strip():
        filtros["nombre_like"] = nombre_like.strip()

    # nombre del proveedor (búsqueda por nombre, contiene)
    if prov_nombre_like.strip():
        # la clave del filtro es a nivel python; en el model tú decides
        # cómo aplicarlo (ej. like sobre nombre_proveedor)
        filtros["nombre_proveedor_like"] = prov_nombre_like.strip()

    # código de proveedor (cdcvepro exacto) normalizado
    if prov_codigo.strip():
        filtros["proveedor"] = prov_codigo.strip()

    # concepto sae
    if concepto.strip():
        filtros["concepto"] = concepto.strip()

    # activo / inactivo
    if activo in ("1", "0"):
        filtros["activo"] = activo

    # -------------------------
    # consulta de prorrateos (sin mostrar limit/offset)
    # -------------------------
    df_pr = get_prorrateos_mysql_df(
        limit=50000,  # valor alto fijo; límite ya no se expone en la ui
        offset=0,
        filtros=filtros,
    )

    if df_pr.empty:
        st.warning(
            "no se encontraron registros en la tabla prorrateos "
            "con los filtros aplicados."
        )
        return
    
    # -------------------------------------------------
    # unir conceptos aspel (CONP01) -> descripcion_concepto
    # -------------------------------------------------
    df_conp = get_conceptos_aspel_df()

    if not df_conp.empty and "cdnrocon" in df_pr.columns:
        # por si acaso, normalizamos nombres (ya viene así desde el model)
        df_conp.columns = [str(c).lower() for c in df_conp.columns]

        # nos quedamos con num_cpto y descr de aspel
        if "num_cpto" in df_conp.columns and "descr" in df_conp.columns:
            # igualamos tipos para el join (por si uno es int y otro str)
            df_tmp_pr = df_pr.copy()
            df_tmp_pr["cdnrocon_join"] = df_tmp_pr["cdnrocon"].astype(str).str.strip()

            df_tmp_conp = df_conp[["num_cpto", "descr"]].copy()
            df_tmp_conp["num_cpto_join"] = (
                df_tmp_conp["num_cpto"].astype(str).str.strip()
            )

            # merge por NUM_CPTO (aspel) = cdnrocon (prorrateos)
            df_merged = df_tmp_pr.merge(
                df_tmp_conp[["num_cpto_join", "descr"]],
                how="left",
                left_on="cdnrocon_join",
                right_on="num_cpto_join",
            )

            # renombramos la descripción del concepto
            df_merged = df_merged.rename(
                columns={"descr": "descripcion_concepto"}
            )

            # limpiamos columnas auxiliares de join
            df_merged = df_merged.drop(
                columns=["cdnrocon_join", "num_cpto_join"], errors="ignore"
            )

            df_pr = df_merged

    # -------------------------------------------------
    # enriquecer con nombre de proveedor desde sae (prov01)
    # match: prov01.clave ↔ prorrateos.cdcvepro
    # -------------------------------------------------
    mapa_prov = get_prov_nombres_sae_dict()

    if mapa_prov and "cdcvepro" in df_pr.columns:
        # normalizamos el código de proveedor: quitamos espacios
        df_pr["cdcvepro_norm"] = (
            df_pr["cdcvepro"].astype(str).str.strip()
        )
        # usamos el dict { clave -> nombre } para mapear
        df_pr["nombre_proveedor_sae"] = df_pr["cdcvepro_norm"].map(mapa_prov)
        # si quieres un nombre más corto:
        # df_pr = df_pr.rename(columns={"nombre_proveedor_sae": "nombre_proveedor"})
        # limpiamos la columna auxiliar
        df_pr = df_pr.drop(columns=["cdcvepro_norm"], errors="ignore")


    # -------------------------------------------------
    # botón + formulario para crear NUEVO prorrateo (solo cabecera)
    # -------------------------------------------------
    if "mostrar_form_nuevo_prorrateo" not in st.session_state:
        st.session_state["mostrar_form_nuevo_prorrateo"] = False

    c_btn, _ = st.columns([1, 5])
    if c_btn.button("nuevo prorrateo", key="btn_nuevo_prorrateo", type="primary"):
        st.session_state["mostrar_form_nuevo_prorrateo"] = not st.session_state[
            "mostrar_form_nuevo_prorrateo"
        ]
    
    if st.session_state["mostrar_form_nuevo_prorrateo"]:
        st.markdown("### alta de prorrateo (cabecera)")

        # -----------------------------
        # opciones de PROVEEDOR desde mapa_prov
        # -----------------------------
        prov_labels: list[str] = []
        prov_label_to_clave: dict[str, str] = {}

        if mapa_prov:
            # ordenamos por clave de proveedor
            for clave, nombre in sorted(mapa_prov.items(), key=lambda x: x[0]):
                label = f"{clave} - {nombre}"
                prov_labels.append(label)
                prov_label_to_clave[label] = clave

        # -----------------------------
        # opciones de CONCEPTO desde df_conp (CONP01)
        # -----------------------------
        conp_labels: list[str] = []
        conp_label_to_num: dict[str, int] = {}

        if (
            "df_conp" in locals()
            and df_conp is not None
            and not df_conp.empty
            and "num_cpto" in df_conp.columns
        ):
            df_conp_unique = (
                df_conp[["num_cpto", "descr"]]
                .drop_duplicates(subset=["num_cpto"])
                .sort_values("num_cpto")
            )

            for _, row in df_conp_unique.iterrows():
                num = row["num_cpto"]
                descr = row.get("descr", "")
                try:
                    num_int = int(num)
                except Exception:
                    continue
                label = f"{num_int} - {descr}"
                conp_labels.append(label)
                conp_label_to_num[label] = num_int

        # -----------------------------
        # formulario
        # -----------------------------
        with st.form("form_nuevo_prorrateo"):
            dsnombre_new = st.text_input(
                "nombre del prorrateo",
                key="nuevo_dsnombre",
                max_chars=60,
            )

            c1_form, c2_form = st.columns(2)

            # ----- proveedor (select) -----
            if prov_labels:
                label_prov_sel = c1_form.selectbox(
                    "proveedor (cdcvepro)",
                    prov_labels,
                    key="nuevo_cdcvepro",
                    help="selecciona la clave de proveedor desde SAE (PROV01.CLAVE)",
                )
                cdcvepro_new = prov_label_to_clave.get(label_prov_sel, "").strip()
            else:
                cdcvepro_new = c1_form.text_input(
                    "proveedor (cdcvepro)",
                    key="nuevo_cdcvepro_fallback",
                    max_chars=30,
                )

            # ----- concepto (select) -----
            if conp_labels:
                label_conp_sel = c2_form.selectbox(
                    "concepto SAE (cdnrocon)",
                    conp_labels,
                    key="nuevo_cdnrocon",
                    help="número de concepto CONP01.NUM_CPTO",
                )
                cdnrocon_new = conp_label_to_num.get(label_conp_sel, None)
            else:
                cdnrocon_new = c2_form.number_input(
                    "concepto SAE (cdnrocon)",
                    min_value=1,
                    step=1,
                    key="nuevo_cdnrocon_fallback",
                )

            # ----- importe / moneda / variación -----
            c3_form, c4_form, c5_form = st.columns(3)

            importe_new = c3_form.number_input(
                "importe",
                min_value=0.0,
                step=0.01,
                format="%.2f",
                key="nuevo_importe",
            )

            moneda_new = c4_form.number_input(
                "moneda (id)",
                min_value=0,
                step=1,
                key="nuevo_moneda",
                help="id de moneda (según catálogo que estés usando)",
            )

            variacion_new = c5_form.number_input(
                "variación",
                min_value=0.0,
                step=0.01,
                format="%.4f",
                key="nuevo_variacion",
                help="variación asociada al prorrateo",
            )

            submitted_new = st.form_submit_button("guardar prorrateo")
    
    # -----------------------------
    # finaliza formulario
    # -----------------------------

        if submitted_new:
            errores = []

            if not dsnombre_new.strip():
                errores.append("captura el nombre del prorrateo.")
            if cdnrocon_new is None or str(cdnrocon_new).strip() == "":
                errores.append("selecciona el concepto SAE (cdnrocon).")
            if not cdcvepro_new.strip():
                errores.append("selecciona el proveedor (cdcvepro).")

            if errores:
                for e in errores:
                    st.error(e)
            else:
                try:
                    crear_prorrateo_cabecera_ctrl(
                        dsnombre=dsnombre_new.strip(),
                        cdnrocon=int(cdnrocon_new),
                        cdcvepro=cdcvepro_new.strip(),
                        importe=float(importe_new),
                        moneda=int(moneda_new),
                        variacion=float(variacion_new),
                        idusuari=0,   # luego lo ligamos al usuario real
                        estatus=1,    # se crea Activo
                    )
                    st.success("prorrateo creado correctamente.")
                    st.session_state["mostrar_form_nuevo_prorrateo"] = False
                    st.rerun()
                except Exception as ex:
                    st.error(f"error al crear el prorrateo: {ex}")
    

    # -------------------------
    # tabla principal con selección y estatus
    # -------------------------
    df_view = df_pr.copy()

    # mapeo de estatus → texto legible
    if "estatus" in df_view.columns:
        df_view["estatus_desc"] = (
            df_view["estatus"]
            .map({1: "activo", 9: "baja"})
            .fillna("otro")
        )

    if "sel" not in df_view.columns:
        df_view.insert(0, "sel", False)

    disabled_cols = [c for c in df_view.columns if c != "sel"]

    orden_principal = [
        "sel",
        "idnumpon",
        "dsnombre",
        "nombre",                  # nombre del prorrateo
        "cdcvepro",
        "nombre_proveedor_sae",    # nombre proveedor desde SAE
        "cdnrocon",
        "descripcion_concepto",    # CONP01.DESCR
        "estatus_desc",
        "tmstmp",
        "estatus",
    ]

    # agregamos el resto de columnas que existan pero no estén en la lista
    column_order = [
        col for col in orden_principal if col in df_view.columns
    ] + [
        col for col in df_view.columns if col not in orden_principal
    ]
    
    tabla_editada = st.data_editor(
        df_view,
        use_container_width=True,
        height=520,
        key="editor_prorrateos",
        column_order=column_order,
        column_config={
            "sel": st.column_config.CheckboxColumn(
                "sel",
                help="marca un prorrateo para ver el detalle o cambiar estatus",
                default=False,
            ),
            "estatus_desc": st.column_config.TextColumn(
                "estatus",
                help="estatus del prorrateo (activo / baja)",
            ),
        },
        disabled=disabled_cols,
    )

    # -------------------------
    # descargar csv + cambiar estatus
    # -------------------------
    col_csv, col_status = st.columns([1, 1])

    col_csv.download_button(
        "descargar csv",
        data=df_pr.to_csv(index=False).encode("utf-8"),
        file_name="prorrateos_filtrados.csv",
        mime="text/csv",
        key="download_prorrateos",
    )

    if col_status.button("cambiar estatus", key="btn_cambiar_estatus", type="primary"):
        seleccionados = tabla_editada[tabla_editada["sel"] == True]

        if seleccionados.empty:
            st.warning("selecciona al menos un prorrateo en la columna sel.")
        else:
            if "idnumpon" not in seleccionados.columns:
                st.error(
                    "no se encontró la columna idnumpon en la tabla de prorrateos.\n"
                    "verifica que la consulta principal incluya ese campo."
                )
            elif "estatus" not in seleccionados.columns:
                st.error(
                    "no se encontró la columna estatus en la tabla de prorrateos.\n"
                    "verifica que la consulta principal incluya ese campo."
                )
            else:
                cambios = []
                for _, fila in seleccionados.iterrows():
                    est = fila["estatus"]
                    try:
                        est_int = int(est)
                    except Exception:
                        continue

                    if est_int == 1:
                        nuevo = 9
                    elif est_int == 9:
                        nuevo = 1
                    else:
                        continue

                    cambios.append(
                        {
                            "idnumpon": int(fila["idnumpon"]),
                            "estatus": nuevo,
                        }
                    )

                if not cambios:
                    st.info(
                        "no hay filas con estatus 1 o 9 para cambiar. "
                        "nada que actualizar."
                    )
                else:
                    afectados = actualizar_estatus_prorrateos(cambios)
                    st.success(f"se actualizaron {afectados} prorrateos.")
                    st.rerun()

    st.divider()

    # -------------------------
    # a partir de aquí sigue igual: detalle en agrid + guardar cambios
    # (no toco nada de esto)
    # -------------------------

    if "detalle_version" not in st.session_state:
        st.session_state["detalle_version"] = 0

    if st.button("ver detalle del prorrateo seleccionado"):
        seleccionados = tabla_editada[tabla_editada["sel"] == True]

        if seleccionados.empty:
            st.warning("selecciona un prorrateo en la columna sel.")
            return

        if len(seleccionados) > 1:
            st.warning("selecciona solo un prorrateo para ver su detalle.")
            return

        fila = seleccionados.iloc[0]

        if "idnumpon" not in fila.index:
            st.error(
                "no se encontró la columna idnumpon en el prorrateo seleccionado."
            )
            return

        idnumpon = int(fila["idnumpon"])
        
        # guardar cabecera del prorrateo para mostrar arriba del detalle
        st.session_state["prorrateo_header"] = {
            "idnumpon": idnumpon,
            "dsnombre": fila.get("dsnombre", ""),
            "cdnrocon": fila.get("cdnrocon", ""),
            "descripcion_concepto": fila.get("descripcion_concepto", ""),
            "cdcvepro": fila.get("cdcvepro", ""),
            "nombre_proveedor": fila.get("nombre_proveedor_sae", ""),
        }

        df_det = get_detalle_prorrateo_df(idnumpon)

        if df_det.empty:
            df_det = pd.DataFrame(
                columns=[
                    "idnumpon",
                    "dsctacon",
                    "idunineg",
                    "flporuni",
                    "tmstmp",
                    "idnuevo",
                    "unidad",
                ]
            )

        if "idunineg" in df_det.columns and "idunineg_orig" not in df_det.columns:
            df_det["idunineg_orig"] = df_det["idunineg"]

        st.session_state["df_detalle_original"] = df_det.copy(deep=True)
        st.session_state["df_detalle_prorrateo"] = df_det.copy(deep=True)
        st.session_state["idnumpon_detalle_actual"] = idnumpon
        st.session_state["detalle_version"] += 1
        st.success(f"detalle cargado para idnumpon = {idnumpon}.")
        st.rerun()

    if "df_detalle_prorrateo" in st.session_state:

        st.markdown("### detalle del prorrateo (editable)")

        id_actual = st.session_state.get("idnumpon_detalle_actual", None)
        if id_actual is not None:
            st.write(f"idnumpon actual: {id_actual}")

        # cabecera del prorrateo (si la guardamos cuando se selecciona)
        hdr = st.session_state.get("prorrateo_header", {})
        if hdr:
            st.write(
                f"concepto de cuenta por pagar: "
                f"{hdr.get('cdnrocon', '')} - {hdr.get('descripcion_concepto', '')}"
            )
            st.write(
                f"nombre: {hdr.get('dsnombre', '')}"
            )
            st.write(
                f"proveedor: {hdr.get('cdcvepro', '')} - {hdr.get('nombre_proveedor', '')}"
            )

        # -----------------------------
        # cambiar concepto de la cabecera (cdnrocon)
        # -----------------------------
        st.markdown("#### cambiar concepto de cuenta por pagar")

        df_conp_hdr = get_conceptos_aspel_df()

        opciones_conc = []
        label_to_num = {}
        idx_default = 0

        if not df_conp_hdr.empty and "num_cpto" in df_conp_hdr.columns:
            df_conp_hdr = df_conp_hdr.copy()
            df_conp_hdr.columns = [str(c).lower() for c in df_conp_hdr.columns]
            df_conp_unique = (
                df_conp_hdr[["num_cpto", "descr"]]
                .drop_duplicates(subset=["num_cpto"])
                .sort_values("num_cpto")
            )

            cdnrocon_actual = str(hdr.get("cdnrocon", "")).strip()

            for i, row in df_conp_unique.reset_index(drop=True).iterrows():
                num = int(row["num_cpto"])
                descr = str(row.get("descr", "")).strip()
                label = f"{num} - {descr}"
                opciones_conc.append(label)
                label_to_num[label] = num

                if cdnrocon_actual and str(num) == cdnrocon_actual:
                    idx_default = i

            if opciones_conc:
                label_sel = st.selectbox(
                    "concepto sae (cdnrocon) del prorrateo",
                    opciones_conc,
                    index=idx_default,
                    key="concepto_prorrateo_detalle",
                )

                if st.button(
                    "guardar nuevo concepto",
                    key="btn_cambiar_concepto_prorrateo",
                ):
                    nuevo_cdnrocon = label_to_num.get(label_sel)

                    try:
                        cdnrocon_act_int = int(cdnrocon_actual) if cdnrocon_actual else None
                    except Exception:
                        cdnrocon_act_int = None

                    if nuevo_cdnrocon is None:
                        st.error("no se pudo determinar el concepto seleccionado.")
                    elif cdnrocon_act_int is not None and nuevo_cdnrocon == cdnrocon_act_int:
                        st.info("el concepto seleccionado es el mismo que el actual.")
                    else:
                        try:
                            afectados = actualizar_concepto_prorrateo_ctrl(
                                idnumpon=int(id_actual),
                                cdnrocon=int(nuevo_cdnrocon),
                            )
                            if afectados > 0:
                                # actualiza cabecera en memoria
                                hdr["cdnrocon"] = int(nuevo_cdnrocon)
                                hdr["descripcion_concepto"] = label_sel.split(" - ", 1)[1]
                                st.session_state["prorrateo_header"] = hdr
                                st.success(
                                    f"concepto actualizado a {nuevo_cdnrocon} para el prorrateo {id_actual}."
                                )
                                st.rerun()
                            else:
                                st.warning("no se actualizó ningún registro (revisa el idnumpon).")
                        except Exception as ex:
                            st.error(f"error al actualizar el concepto: {ex}")
        else:
            st.info("no se pudieron cargar los conceptos de aspel para cambiar el concepto.")


        df_detalle = st.session_state["df_detalle_prorrateo"].copy()

        # asegurar columna idunineg_orig
        if "idunineg" in df_detalle.columns and "idunineg_orig" not in df_detalle.columns:
            df_detalle["idunineg_orig"] = df_detalle["idunineg"]


        # ----------------------
        # botón + formulario "agregar detalle"
        # ----------------------
        if "mostrar_form_detalle" not in st.session_state:
            st.session_state["mostrar_form_detalle"] = False

        c_btn_add, _ = st.columns([1, 5])
        if c_btn_add.button("agregar detalle", key="btn_mostrar_form_detalle", type="primary"):
            st.session_state["mostrar_form_detalle"] = not st.session_state[
                "mostrar_form_detalle"
            ]

        if st.session_state["mostrar_form_detalle"]:
            st.markdown("#### nuevo detalle de prorrateo")

            # cargamos catálogo de cuentas contables y unidades
            df_ctas = get_cuentas_contables_coi_ctrl()
            df_unis = get_unidades_prorrateo_ctrl()

            # opciones de cuentas contables (ajusta columnas según tu COI)
            opciones_ctas = []
            cuenta_from_label = {}

            if not df_ctas.empty:
                # aquí supongo columnas 'cuenta' y 'nombre'; AJUSTA a las reales
                for _, row in df_ctas.iterrows():
                    cta = str(row["cuenta"]).strip()
                    nom = str(row["nombre"]).strip()
                    label = f"{cta} - {nom}"
                    opciones_ctas.append(label)
                    cuenta_from_label[label] = cta

            opciones_unis = []
            idunineg_from_label = {}
            if not df_unis.empty and "idunineg" in df_unis.columns and "dsunineg" in df_unis.columns:
                for _, row in df_unis.iterrows():
                    uid = int(row["idunineg"])
                    nomu = str(row["dsunineg"]).strip()
                    label = f"{uid} - {nomu}"
                    opciones_unis.append(label)
                    idunineg_from_label[label] = uid

            with st.form("form_nuevo_detalle_prorrateo"):
                c_f1, c_f2, c_f3 = st.columns([3, 2, 1])

                # cuenta contable (dsctacon)
                if opciones_ctas:
                    label_cta_sel = c_f1.selectbox(
                        "cuenta contable (COI)",
                        opciones_ctas,
                        key="nuevo_det_cta",
                    )
                    dsctacon_new = cuenta_from_label.get(label_cta_sel, "")
                else:
                    dsctacon_new = c_f1.text_input(
                        "cuenta contable (dsctacon)",
                        key="nuevo_det_cta_fallback",
                    )

                # unidad de prorrateo (idunineg)
                if opciones_unis:
                    label_uni_sel = c_f2.selectbox(
                        "unidad de prorrateo",
                        opciones_unis,
                        key="nuevo_det_uni",
                    )
                    idunineg_new = idunineg_from_label.get(label_uni_sel, None)
                else:
                    idunineg_new = c_f2.number_input(
                        "id unidad (idunineg)",
                        min_value=0,
                        step=1,
                        key="nuevo_det_uni_fallback",
                    )

                # porcentaje flporuni
                flporuni_new = c_f3.number_input(
                    "porcentaje",
                    min_value=0.0,
                    step=0.01,
                    format="%.4f",
                    key="nuevo_det_flporuni",
                )

                btn_add_det = st.form_submit_button("agregar línea")

            if btn_add_det:
                errores = []
                if not dsctacon_new.strip():
                    errores.append("captura o selecciona la cuenta contable (dsctacon).")
                if idunineg_new is None or (isinstance(idunineg_new, float) and idunineg_new != idunineg_new):
                    errores.append("captura o selecciona la unidad (idunineg).")

                if errores:
                    for e in errores:
                        st.error(e)
                else:
                    # armamos la nueva fila en el dataframe en memoria
                    nueva_fila = {
                        "idnumpon": id_actual,
                        "dsctacon": dsctacon_new.strip(),
                        "idunineg": int(idunineg_new),
                        "flporuni": float(flporuni_new),
                        "tmstmp": None,     # se llenará en la BD
                        "idnuevo": int(idunineg_new),
                        "unidad": "",       # se llenará al recargar desde BD
                        "idunineg_orig": None,
                        "es_nuevo": True,   # bandera para futuro insert real
                    }
                    df_detalle = pd.concat(
                        [df_detalle, pd.DataFrame([nueva_fila])],
                        ignore_index=True,
                    )
                    st.session_state["df_detalle_prorrateo"] = df_detalle
                    st.session_state["detalle_version"] += 1
                    st.success("línea agregada al detalle (pendiente de guardar en BD).")
                    st.rerun()

    ####
    ####  Se deja lo ultimo donde se ve la informacion de las partidas
    #####

        if "idunineg" in df_detalle.columns and "idunineg_orig" not in df_detalle.columns:
            df_detalle["idunineg_orig"] = df_detalle["idunineg"]

        gb = GridOptionsBuilder.from_dataframe(df_detalle)
        gb.configure_default_column(editable=False, resizable=True)

        if "idnumpon" in df_detalle.columns:
            gb.configure_column("idnumpon", headerName="id prorrateo")
        if "dsctacon" in df_detalle.columns:
            gb.configure_column("dsctacon", headerName="cuenta contable")
        if "idunineg" in df_detalle.columns:
            gb.configure_column("idunineg", headerName="id unidad")
        if "flporuni" in df_detalle.columns:
            gb.configure_column("flporuni", headerName="porcentaje")
        if "tmstmp" in df_detalle.columns:
            gb.configure_column("tmstmp", headerName="fecha registro")
        if "idnuevo" in df_detalle.columns:
            gb.configure_column("idnuevo", headerName="id unidad nueva")
        if "unidad" in df_detalle.columns:
            gb.configure_column("unidad", headerName="unidad")
        if "idunineg_orig" in df_detalle.columns:
            gb.configure_column("idunineg_orig", hide=True, editable=False)

        for col in ["dsctacon", "idunineg", "flporuni"]:
            if col in df_detalle.columns:
                gb.configure_column(col, editable=True)

        grid_options = gb.build()
        grid_key = f"agrid_detalle_prorrateo_{st.session_state['detalle_version']}"

        grid_response = AgGrid(
            df_detalle,
            gridOptions=grid_options,
            update_mode=GridUpdateMode.VALUE_CHANGED,
            data_return_mode="AS_INPUT",
            fit_columns_on_grid_load=True,
            height=400,
            key=grid_key,
        )

        df_actual = pd.DataFrame(grid_response["data"])
        st.session_state["df_detalle_prorrateo"] = df_actual

        total_flporuni = None
        if "flporuni" in df_actual.columns:
            valores_decimal = []
            for v in df_actual["flporuni"]:
                try:
                    valores_decimal.append(Decimal(str(v)))
                except Exception:
                    valores_decimal.append(Decimal("0"))
            total_flporuni = sum(valores_decimal)

        if total_flporuni is not None:
            c_total, c_guardar, c_refresh = st.columns([2, 1, 1])
            c_total.write(f"total flporuni: {total_flporuni:.4f}")

            puede_guardar = (total_flporuni == Decimal("1"))

            btn_guardar = c_guardar.button(
                "guardar cambios",
                key="btn_guardar_prorrateo",
                disabled=not puede_guardar,
                type="primary",
            )

            btn_refrescar = c_refresh.button(
                "refrescar desde bd",
                key="btn_refrescar_detalle",
                disabled=(id_actual is None),
            )

            if btn_refrescar and id_actual is not None:
                df_ref = get_detalle_prorrateo_df(id_actual)
                if (
                    "idunineg" in df_ref.columns
                    and "idunineg_orig" not in df_ref.columns
                ):
                    df_ref["idunineg_orig"] = df_ref["idunineg"]
                st.session_state["df_detalle_original"] = df_ref.copy(deep=True)
                st.session_state["df_detalle_prorrateo"] = df_ref.copy(deep=True)
                st.session_state["detalle_version"] += 1
                st.success("detalle recargado desde bd.")
                st.rerun()

            if btn_guardar:
                df_edit = st.session_state["df_detalle_prorrateo"].copy()
                df_orig = st.session_state.get("df_detalle_original")

                if df_orig is None:
                    st.error("no se encontró el dataframe original para comparar.")
                    return

                cambios = []       # updates
                nuevos = []        # inserts

                for _, fila in df_edit.iterrows():
                    es_nuevo = bool(fila.get("es_nuevo", False))

                    if es_nuevo:
                        # fila nueva → insert
                        if pd.isna(fila.get("idnumpon")) or pd.isna(fila.get("idunineg")):
                            continue

                        nuevos.append(
                            {
                                "idnumpon": int(fila["idnumpon"]),
                                "dsctacon": str(fila.get("dsctacon", "")).strip(),
                                "idunineg": int(fila["idunineg"]),
                                "flporuni": float(fila.get("flporuni") or 0.0),
                                "idnuevo": int(fila.get("idnuevo") or fila["idunineg"]),
                            }
                        )
                    else:
                        # fila existente → comparar contra df_orig y hacer update si cambió
                        try:
                            orig = df_orig[
                                (df_orig["idnumpon"] == fila["idnumpon"])
                                & (df_orig["idunineg_orig"] == fila["idunineg_orig"])
                            ].iloc[0]
                        except IndexError:
                            continue

                        campos = ["dsctacon", "idunineg", "flporuni"]
                        modificado = any(
                            str(fila.get(c)) != str(orig.get(c)) for c in campos
                        )
                        if not modificado:
                            continue

                        cambios.append(
                            {
                                "idnumpon": int(fila["idnumpon"]),
                                "idunineg": int(fila["idunineg"])
                                if pd.notna(fila["idunineg"])
                                else None,
                                "idunineg_orig": int(fila["idunineg_orig"])
                                if pd.notna(fila["idunineg_orig"])
                                else None,
                                "dsctacon": str(fila["dsctacon"])
                                if pd.notna(fila["dsctacon"])
                                else None,
                                "flporuni": float(fila["flporuni"])
                                if pd.notna(fila["flporuni"])
                                else 0.0,
                            }
                        )

                if not nuevos and not cambios:
                    st.info("no hay cambios que guardar.")
                else:
                    afectados_ins = 0
                    afectados_upd = 0

                    if nuevos:
                        afectados_ins = insertar_detalle_prorrateo_ctrl(nuevos)

                    if cambios:
                        afectados_upd = guardar_detalle_prorrateo(cambios)

                    st.success(
                        f"se guardaron {afectados_ins} filas nuevas y "
                        f"se actualizaron {afectados_upd} filas existentes."
                    )

                    # recargar desde bd para limpiar flags es_nuevo y tener tmstmp / unidad
                    if id_actual is not None:
                        df_ref = get_detalle_prorrateo_df(id_actual)
                        if (
                            "idunineg" in df_ref.columns
                            and "idunineg_orig" not in df_ref.columns
                        ):
                            df_ref["idunineg_orig"] = df_ref["idunineg"]
                        st.session_state["df_detalle_original"] = df_ref.copy(
                            deep=True
                        )
                        st.session_state["df_detalle_prorrateo"] = df_ref.copy(
                            deep=True
                        )
                        st.session_state["detalle_version"] += 1
                        st.rerun()