# tab_prorrateos_config_view.py

import streamlit as st
import pandas as pd
from decimal import Decimal

from st_aggrid import (
    AgGrid,
    GridOptionsBuilder,
    GridUpdateMode,
    DataReturnMode,
    JsCode,
)

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
    copiar_detalle_prorrateo_ctrl,
)


def _append_blank_row_detalle(df: pd.DataFrame, id_actual: int | None) -> pd.DataFrame:
    if df is None or df.empty:
        df = pd.DataFrame(
            columns=[
                "id",
                "idnumpon",
                "dsctacon",
                "idunineg",
                "flporuni",
                "tmstmp",
                "idnuevo",
                "unidad",
            ]
        )

    for c in ["id", "idnumpon", "dsctacon", "idunineg", "flporuni", "tmstmp", "idnuevo", "unidad"]:
        if c not in df.columns:
            df[c] = None

    if id_actual is not None:
        df["idnumpon"] = int(id_actual)

    # si el último renglón ya está vacío, no agregues otro
    if not df.empty:
        last = df.iloc[-1]
        last_empty = (
            (pd.isna(last.get("id")))
            and (str(last.get("dsctacon") or "").strip() == "")
            and (str(last.get("idunineg") or "").strip() in ("", "none", "nan"))
            and (str(last.get("cuenta_contable") or "").strip() == "")
            and (str(last.get("unidad_negocio") or "").strip() == "")
            and (str(last.get("flporuni") or "").strip() in ("", "0", "0.0", "0.0000"))
        )
        if last_empty:
            return df

    blank = {
        "id": None,
        "idnumpon": int(id_actual) if id_actual is not None else None,
        "dsctacon": "",
        "idunineg": None,
        "flporuni": 0.0,
        "tmstmp": None,
        "idnuevo": None,
        "unidad": "",
    }
    return pd.concat([df, pd.DataFrame([blank])], ignore_index=True)


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

    c4, c5, c6 = st.columns([2, 1, 1])

    concepto = c4.text_input("concepto sae (id)", value="", key="concepto_prorrateos")

    ver_eliminados = c6.checkbox(
        "ver eliminados",
        value=False,
        key="ver_eliminados_prorrateos",
        help="si está apagado: solo muestra estatus = 1. si está encendido: muestra 1 y 9.",
    )

    # default: solo activos
    if ver_eliminados:
        estatus_sel = c5.selectbox(
            "estatus",
            options=["(activos + eliminados)", "activos (1)", "eliminados (9)"],
            index=0,
            key="estatus_prorrateos",
        )
    else:
        estatus_sel = "activos (1)"
        c5.selectbox(
            "estatus",
            options=["activos (1)"],
            index=0,
            key="estatus_prorrateos",
            disabled=True,
        )

    filtros: dict[str, str] = {}

    if nombre_like.strip():
        filtros["nombre_like"] = nombre_like.strip()

    if prov_nombre_like.strip():
        filtros["nombre_proveedor_like"] = prov_nombre_like.strip()

    if prov_codigo.strip():
        filtros["proveedor"] = prov_codigo.strip()

    if concepto.strip():
        filtros["concepto"] = concepto.strip()

    if estatus_sel == "activos (1)":
        filtros["estatus"] = "1"
    elif estatus_sel == "eliminados (9)":
        filtros["estatus"] = "9"
    # (activos + eliminados) => no filtra estatus

    # -------------------------
    # consulta prorrateos
    # -------------------------
    df_pr = get_prorrateos_mysql_df(
        limit=50000,
        offset=0,
        filtros=filtros,
    )

    if df_pr.empty:
        st.warning("no se encontraron registros en la tabla prorrateos con los filtros aplicados.")
        return

    # -------------------------------------------------
    # unir conceptos aspel -> descripcion_concepto
    # -------------------------------------------------
    df_conp = get_conceptos_aspel_df()

    if not df_conp.empty and "cdnrocon" in df_pr.columns:
        df_conp.columns = [str(c).lower() for c in df_conp.columns]

        if "num_cpto" in df_conp.columns and "descr" in df_conp.columns:
            df_tmp_pr = df_pr.copy()
            df_tmp_pr["cdnrocon_join"] = df_tmp_pr["cdnrocon"].astype(str).str.strip()

            df_tmp_conp = df_conp[["num_cpto", "descr"]].copy()
            df_tmp_conp["num_cpto_join"] = df_tmp_conp["num_cpto"].astype(str).str.strip()

            df_merged = df_tmp_pr.merge(
                df_tmp_conp[["num_cpto_join", "descr"]],
                how="left",
                left_on="cdnrocon_join",
                right_on="num_cpto_join",
            )

            df_merged = df_merged.rename(columns={"descr": "descripcion_concepto"})
            df_merged = df_merged.drop(columns=["cdnrocon_join", "num_cpto_join"], errors="ignore")
            df_pr = df_merged

    # -------------------------------------------------
    # enriquecer con nombre de proveedor desde sae
    # -------------------------------------------------
    mapa_prov = get_prov_nombres_sae_dict()

    if mapa_prov and "cdcvepro" in df_pr.columns:
        df_pr["cdcvepro_norm"] = df_pr["cdcvepro"].astype(str).str.strip()
        df_pr["nombre_proveedor_sae"] = df_pr["cdcvepro_norm"].map(mapa_prov)
        df_pr = df_pr.drop(columns=["cdcvepro_norm"], errors="ignore")

    # -------------------------------------------------
    # formulario nuevo prorrateo (cabecera)
    # -------------------------------------------------
    if "mostrar_form_nuevo_prorrateo" not in st.session_state:
        st.session_state["mostrar_form_nuevo_prorrateo"] = False

    c_btn, _ = st.columns([1, 5])
    if c_btn.button("nuevo prorrateo", key="btn_nuevo_prorrateo", type="primary"):
        st.session_state["mostrar_form_nuevo_prorrateo"] = not st.session_state["mostrar_form_nuevo_prorrateo"]

    if st.session_state["mostrar_form_nuevo_prorrateo"]:
        st.markdown("### alta de prorrateo (cabecera)")

        prov_labels: list[str] = []
        prov_label_to_clave: dict[str, str] = {}

        if mapa_prov:
            for clave, nombre in sorted(mapa_prov.items(), key=lambda x: x[0]):
                label = f"{clave} - {nombre}"
                prov_labels.append(label)
                prov_label_to_clave[label] = clave

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

        with st.form("form_nuevo_prorrateo"):
            dsnombre_new = st.text_input(
                "nombre del prorrateo",
                key="nuevo_dsnombre",
                max_chars=60,
            )

            c1_form, c2_form = st.columns(2)

            if prov_labels:
                label_prov_sel = c1_form.selectbox(
                    "proveedor (cdcvepro)",
                    prov_labels,
                    key="nuevo_cdcvepro",
                    help="selecciona la clave de proveedor desde sae (prov01.clave)",
                )
                cdcvepro_new = prov_label_to_clave.get(label_prov_sel, "").strip()
            else:
                cdcvepro_new = c1_form.text_input(
                    "proveedor (cdcvepro)",
                    key="nuevo_cdcvepro_fallback",
                    max_chars=30,
                )

            if conp_labels:
                label_conp_sel = c2_form.selectbox(
                    "concepto sae (cdnrocon)",
                    conp_labels,
                    key="nuevo_cdnrocon",
                    help="número de concepto conp01.num_cpto",
                )
                cdnrocon_new = conp_label_to_num.get(label_conp_sel, None)
            else:
                cdnrocon_new = c2_form.number_input(
                    "concepto sae (cdnrocon)",
                    min_value=1,
                    step=1,
                    key="nuevo_cdnrocon_fallback",
                )

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

        if submitted_new:
            errores = []
            if not dsnombre_new.strip():
                errores.append("captura el nombre del prorrateo.")
            if cdnrocon_new is None or str(cdnrocon_new).strip() == "":
                errores.append("selecciona el concepto sae (cdnrocon).")
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
                        idusuari=0,
                        estatus=1,
                    )
                    st.success("prorrateo creado correctamente.")
                    st.session_state["mostrar_form_nuevo_prorrateo"] = False
                    st.rerun()
                except Exception as ex:
                    st.error(f"error al crear el prorrateo: {ex}")

    # -------------------------
    # tabla principal
    # -------------------------
    df_view = df_pr.copy()

    if "estatus" in df_view.columns:
        df_view["estatus_desc"] = df_view["estatus"].map({1: "activo", 9: "baja"}).fillna("otro")

    if "sel" not in df_view.columns:
        df_view.insert(0, "sel", False)

    disabled_cols = [c for c in df_view.columns if c != "sel"]

    orden_principal = [
        "sel",
        "idnumpon",
        "dsnombre",
        "nombre",
        "cdcvepro",
        "nombre_proveedor_sae",
        "cdnrocon",
        "descripcion_concepto",
        "estatus_desc",
        "tmstmp",
        "estatus",
    ]

    column_order = [col for col in orden_principal if col in df_view.columns] + [
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
                st.error("no se encontró la columna idnumpon en la tabla de prorrateos.")
            elif "estatus" not in seleccionados.columns:
                st.error("no se encontró la columna estatus en la tabla de prorrateos.")
            else:
                cambios = []
                for _, fila in seleccionados.iterrows():
                    try:
                        est_int = int(fila["estatus"])
                    except Exception:
                        continue

                    if est_int == 1:
                        nuevo = 9
                    elif est_int == 9:
                        nuevo = 1
                    else:
                        continue

                    cambios.append({"idnumpon": int(fila["idnumpon"]), "estatus": nuevo})

                if not cambios:
                    st.info("no hay filas con estatus 1 o 9 para cambiar.")
                else:
                    afectados = actualizar_estatus_prorrateos(cambios)
                    st.success(f"se actualizaron {afectados} prorrateos.")
                    st.rerun()

    st.divider()

    # -------------------------
    # detalle
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
            st.error("no se encontró la columna idnumpon en el prorrateo seleccionado.")
            return

        idnumpon = int(fila["idnumpon"])

        st.session_state["prorrateo_header"] = {
            "idnumpon": idnumpon,
            "dsnombre": fila.get("dsnombre", ""),
            "cdnrocon": fila.get("cdnrocon", ""),
            "descripcion_concepto": fila.get("descripcion_concepto", ""),
            "cdcvepro": fila.get("cdcvepro", ""),
            "nombre_proveedor": fila.get("nombre_proveedor_sae", ""),
        }

        df_det = get_detalle_prorrateo_df(idnumpon)

        if df_det is None or df_det.empty:
            df_det = pd.DataFrame(
                columns=[
                    "id",
                    "idnumpon",
                    "dsctacon",
                    "idunineg",
                    "flporuni",
                    "tmstmp",
                    "idnuevo",
                    "unidad",
                ]
            )
        elif "id" not in df_det.columns:
            df_det["id"] = None

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

        hdr = st.session_state.get("prorrateo_header", {})
        if hdr:
            st.write(f"concepto de cuenta por pagar: {hdr.get('cdnrocon', '')} - {hdr.get('descripcion_concepto', '')}")
            st.write(f"nombre: {hdr.get('dsnombre', '')}")
            st.write(f"proveedor: {hdr.get('cdcvepro', '')} - {hdr.get('nombre_proveedor', '')}")

        # -----------------------------
        # cambiar concepto de cabecera
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

                if st.button("guardar nuevo concepto", key="btn_cambiar_concepto_prorrateo"):
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
                                hdr["cdnrocon"] = int(nuevo_cdnrocon)
                                hdr["descripcion_concepto"] = label_sel.split(" - ", 1)[1]
                                st.session_state["prorrateo_header"] = hdr
                                st.success(f"concepto actualizado a {nuevo_cdnrocon} para el prorrateo {id_actual}.")
                                st.rerun()
                            else:
                                st.warning("no se actualizó ningún registro (revisa el idnumpon).")
                        except Exception as ex:
                            st.error(f"error al actualizar el concepto: {ex}")
        else:
            st.info("no se pudieron cargar los conceptos de aspel para cambiar el concepto.")

        # ----------------------
        # grid de detalle (sin JsCode: columnas visibles + columnas ocultas para guardar)
        # ----------------------
        df_detalle = st.session_state["df_detalle_prorrateo"].copy()

        if "idunineg" in df_detalle.columns and "idunineg_orig" not in df_detalle.columns:
            df_detalle["idunineg_orig"] = df_detalle["idunineg"]

        # catálogos
        df_ctas = get_cuentas_contables_coi_ctrl()
        df_unis = get_unidades_prorrateo_ctrl()

        # cuentas: label -> cuenta
        cta_labels: list[str] = []
        cta_label_to_val: dict[str, str] = {}

        def _clean_str(v) -> str:
            if v is None:
                return ""
            # evita nan de pandas
            try:
                if isinstance(v, float) and pd.isna(v):
                    return ""
            except Exception:
                pass
            s = str(v).strip()
            if s.lower() in ("nan", "none", "null"):
                return ""
            return s

        if df_ctas is not None and not df_ctas.empty:
            seen = set()
            for _, r in df_ctas.iterrows():
                cta = _clean_str(r.get("cuenta"))
                nom = _clean_str(r.get("nombre"))
                cta_coi = _clean_str(r.get("cuenta_coi"))
                # si la cuenta viene vacía => no se agrega al catálogo
                if not cta:
                    continue
                #label = f"{cta} - {nom} - {cta_coi}" if nom else cta
                label = f"{cta} - {nom}" if nom else cta
                # evita labels repetidos
                if label in seen:
                    continue
                seen.add(label)

                cta_labels.append(label)
                cta_label_to_val[label] = cta

            # opcional: ordena alfabéticamente por label
            cta_labels = sorted(cta_labels)

        # unidades: label(nombre) -> id
        uni_labels: list[str] = []
        uni_label_to_id: dict[str, int] = {}

        if df_unis is not None and not df_unis.empty and "idunineg" in df_unis.columns:
            for _, r in df_unis.iterrows():
                try:
                    uid = int(r.get("idunineg"))
                except Exception:
                    continue
                nomu = str(r.get("dsunineg") or r.get("unidad") or "").strip()
                label = nomu if nomu else str(uid)
                # evita duplicados por nombre
                if label in uni_label_to_id:
                    label = f"{label} ({uid})"
                uni_labels.append(label)
                uni_label_to_id[label] = uid

        # columnas visibles para edición (strings)
        if "cuenta_contable" not in df_detalle.columns:
            df_detalle["cuenta_contable"] = ""
        if "unidad_negocio" not in df_detalle.columns:
            df_detalle["unidad_negocio"] = ""

        # sincroniza visibles desde valores guardados (si hay algo)
        if "dsctacon" in df_detalle.columns:
            # busca un label que empiece con "cta -"
            rev_cta = {v: k for k, v in cta_label_to_val.items()}
            def _cta_to_label(v):
                v = str(v or "").strip()
                if not v:
                    return ""
                return rev_cta.get(v, v)  # si no existe, muestra la cuenta
            df_detalle["cuenta_contable"] = df_detalle["dsctacon"].apply(_cta_to_label)

        if "idunineg" in df_detalle.columns:
            rev_uni = {v: k for k, v in uni_label_to_id.items()}
            def _id_to_unilabel(v):
                if v is None or (isinstance(v, float) and pd.isna(v)):
                    return ""
                try:
                    return rev_uni.get(int(v), str(int(v)))
                except Exception:
                    return ""
            df_detalle["unidad_negocio"] = df_detalle["idunineg"].apply(_id_to_unilabel)

        # agrega renglón vacío al final (alta desde grid)
        df_detalle = _append_blank_row_detalle(df_detalle, int(id_actual) if id_actual is not None else None)
        st.session_state["df_detalle_prorrateo"] = df_detalle

        # --- botón para forzar alta de renglón ---
        c_add, _ = st.columns([1, 5])
        if c_add.button("agregar renglón", key="btn_add_row_detalle"):
            df_tmp = st.session_state["df_detalle_prorrateo"].copy()
            df_tmp = _append_blank_row_detalle(df_tmp, int(id_actual) if id_actual is not None else None)
            st.session_state["df_detalle_prorrateo"] = df_tmp
            st.session_state["detalle_version"] += 1  # fuerza que cambie el key del grid
            st.rerun()

        gb = GridOptionsBuilder.from_dataframe(df_detalle)
        gb.configure_default_column(editable=False, resizable=True)

        # ocultar columnas “de guardado”
        for col in ["id", "dsctacon", "idunineg", "idunineg_orig", "idnuevo", "unidad"]:
            if col in df_detalle.columns:
                gb.configure_column(col, hide=True, editable=False)

        # no editable
        if "idnumpon" in df_detalle.columns:
            gb.configure_column("idnumpon", headerName="id prorrateo", editable=False)
        if "tmstmp" in df_detalle.columns:
            gb.configure_column("tmstmp", headerName="fecha registro", editable=False)
       
        # editable: visibles

        gb.configure_column(
            "cuenta_contable",
            headerName="cuenta contable",
            editable=True,
            cellEditor="agSelectCellEditor",
            cellEditorParams={"values": cta_labels} if cta_labels else None, 
        )

        gb.configure_column(
            "unidad_negocio",
            headerName="unidad de negocio",
            editable=True,
            cellEditor="agSelectCellEditor",
            cellEditorParams={"values": uni_labels} if uni_labels else None,
        )

        if "flporuni" in df_detalle.columns:
            gb.configure_column(
                "flporuni",
                headerName="porcentaje",
                editable=True,
                type=["numericColumn"],
            )

        grid_options = gb.build()
        grid_key = f"agrid_detalle_prorrateo_{st.session_state['detalle_version']}"

        grid_response = AgGrid(
            df_detalle,
            gridOptions=grid_options,
            update_mode=GridUpdateMode.VALUE_CHANGED,
            data_return_mode=DataReturnMode.AS_INPUT,
            fit_columns_on_grid_load=True,
            height=420,
            key=grid_key,
        )

        df_actual = pd.DataFrame(grid_response.get("data", []))

        # reconstruir columnas de guardado desde las visibles
        if "cuenta_contable" in df_actual.columns:
            df_actual["dsctacon"] = df_actual["cuenta_contable"].apply(
                lambda x: cta_label_to_val.get(str(x).strip(), str(x).strip())
            )

        if "unidad_negocio" in df_actual.columns:
            def _uni_to_id(v):
                s = str(v or "").strip()
                if not s:
                    return None
                # si viene "nombre (123)" extrae el 123
                if s.endswith(")") and "(" in s:
                    try:
                        return int(s.rsplit("(", 1)[1].replace(")", "").strip())
                    except Exception:
                        pass
                return uni_label_to_id.get(s, None)
            df_actual["idunineg"] = df_actual["unidad_negocio"].apply(_uni_to_id)
            df_actual["idnuevo"] = df_actual["idunineg"]

        st.session_state["df_detalle_prorrateo"] = df_actual
       

        # ----------------------
        # validación y guardar
        # ----------------------
        total_flporuni = None
        if "flporuni" in df_actual.columns:
            valores_decimal = []
            for v in df_actual["flporuni"]:
                try:
                    # ignora nan
                    if v is None or (isinstance(v, float) and pd.isna(v)):
                        valores_decimal.append(Decimal("0"))
                    else:
                        valores_decimal.append(Decimal(str(v)))
                except Exception:
                    valores_decimal.append(Decimal("0"))
            total_flporuni = sum(valores_decimal)

        if total_flporuni is not None:
            c_total, c_guardar, c_refresh = st.columns([2, 1, 1])
            c_total.write(f"total flporuni: {total_flporuni:.4f}")

            puede_guardar = total_flporuni == Decimal("1")

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

                if df_ref is None or df_ref.empty:
                    df_ref = pd.DataFrame(
                        columns=[
                            "id",
                            "idnumpon",
                            "dsctacon",
                            "idunineg",
                            "flporuni",
                            "tmstmp",
                            "idnuevo",
                            "unidad",
                        ]
                    )
                elif "id" not in df_ref.columns:
                    df_ref["id"] = None

                if "idunineg" in df_ref.columns and "idunineg_orig" not in df_ref.columns:
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

                # limpia renglones “vacíos” (incluye el último renglón)
                def _is_blank_row(r):
                    return (
                        (str(r.get("dsctacon") or "").strip() == "")
                        and (r.get("idunineg") is None or str(r.get("idunineg")).strip() in ("", "none", "nan"))
                        and (str(r.get("flporuni") or "").strip() in ("", "0", "0.0", "0.0000"))
                    )

                df_work = df_edit.copy()
                if not df_work.empty:
                    df_work = df_work[~df_work.apply(_is_blank_row, axis=1)].copy()

                cambios = []
                nuevos = []

                for _, fila in df_work.iterrows():
                    fila_id = fila.get("id", None)
                    is_new = (fila_id is None) or (isinstance(fila_id, float) and pd.isna(fila_id))

                    dsctacon_val = str(fila.get("dsctacon") or "").strip()
                    idunineg_val = fila.get("idunineg", None)

                    if dsctacon_val == "" or idunineg_val is None or str(idunineg_val).strip() in ("", "none", "nan"):
                        continue

                    try:
                        idunineg_int = int(idunineg_val)
                    except Exception:
                        continue

                    fl = fila.get("flporuni")
                    try:
                        flpor = float(fl) if fl is not None and not (isinstance(fl, float) and pd.isna(fl)) else 0.0
                    except Exception:
                        flpor = 0.0

                    if is_new:
                        nuevos.append(
                            {
                                "idnumpon": int(id_actual),
                                "dsctacon": dsctacon_val,
                                "idunineg": int(idunineg_int),
                                "flporuni": float(flpor),
                                "idnuevo": int(idunineg_int),
                            }
                        )
                    else:
                        try:
                            fila_id_int = int(fila_id)
                        except Exception:
                            continue

                        try:
                            orig = df_orig[df_orig["id"] == fila_id_int].iloc[0]
                        except Exception:
                            # si no existe en orig, trátalo como nuevo (por seguridad)
                            nuevos.append(
                                {
                                    "idnumpon": int(id_actual),
                                    "dsctacon": dsctacon_val,
                                    "idunineg": int(idunineg_int),
                                    "flporuni": float(flpor),
                                    "idnuevo": int(idunineg_int),
                                }
                            )
                            continue

                        campos = ["dsctacon", "idunineg", "flporuni"]
                        modificado = any(str(fila.get(c)) != str(orig.get(c)) for c in campos)
                        if not modificado:
                            continue

                        cambios.append(
                            {
                                "id": int(fila_id_int),
                                "idnumpon": int(id_actual),
                                "idunineg": int(idunineg_int),
                                "idunineg_orig": int(orig.get("idunineg")) if pd.notna(orig.get("idunineg")) else None,
                                "dsctacon": dsctacon_val,
                                "flporuni": float(flpor),
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

                    st.success(f"se guardaron {afectados_ins} filas nuevas y se actualizaron {afectados_upd} filas existentes.")

                    if id_actual is not None:
                        df_ref = get_detalle_prorrateo_df(id_actual)

                        if df_ref is None or df_ref.empty:
                            df_ref = pd.DataFrame(
                                columns=[
                                    "id",
                                    "idnumpon",
                                    "dsctacon",
                                    "idunineg",
                                    "flporuni",
                                    "tmstmp",
                                    "idnuevo",
                                    "unidad",
                                ]
                            )
                        elif "id" not in df_ref.columns:
                            df_ref["id"] = None

                        if "idunineg" in df_ref.columns and "idunineg_orig" not in df_ref.columns:
                            df_ref["idunineg_orig"] = df_ref["idunineg"]

                        st.session_state["df_detalle_original"] = df_ref.copy(deep=True)
                        st.session_state["df_detalle_prorrateo"] = df_ref.copy(deep=True)
                        st.session_state["detalle_version"] += 1
                        st.rerun()

            st.divider()
            st.caption("copiar detalle a otra ponderación")

            c1, c2, c3 = st.columns([2, 2, 2])

            with c1:
                id_dest = st.number_input("copiar a (idnumpon)", min_value=0, step=1, value=0, key="cp_idnumpon_dest")

            with c2:
                sobrescribir = st.checkbox("sobrescribir destino (borrar antes)", value=False, key="cp_sobrescribir")

            with c3:
                if st.button("copiar", use_container_width=True):
                    res = copiar_detalle_prorrateo_ctrl(
                        idnumpon_origen=int(id_actual),
                        idnumpon_destino=int(id_dest),
                        sobrescribir=bool(sobrescribir)
                    )
                    if res.get("ok"):
                        st.success(res.get("msg"))
                        st.rerun()
                    else:
                        st.error(res.get("msg"))