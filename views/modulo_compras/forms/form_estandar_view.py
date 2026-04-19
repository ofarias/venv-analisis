from datetime import date
import pandas as pd
import streamlit as st

from controllers.compras_solicitudes_controller import (
    crear_solicitud_estandar_ctrl,
    get_departamentos_compra_ctrl,
    get_formas_pago_compra_ctrl,
    get_unidades_negocio_compra_ctrl,
)


def _fila_vacia_estandar():
    return {
        "cantidad": None,
        "descripcion_producto_servicio": "",
        "unidad_negocio_sigla": "",
        "porcentaje": None,
        "fecha_requerida": None,
        "proveedor": "",
        "precio_unitario": None,
        "costo_total_sin_iva": None,
    }


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


def _init_form_estandar_state():
    if "sce_observaciones" not in st.session_state:
        st.session_state.sce_observaciones = ""

    if "sce_departamento" not in st.session_state:
        st.session_state.sce_departamento = ""

    if "sce_forma_pago" not in st.session_state:
        st.session_state.sce_forma_pago = ""

    if "sce_detalle" not in st.session_state:
        st.session_state.sce_detalle = pd.DataFrame([_fila_vacia_estandar()])

    if "sce_limpiar_pendiente" not in st.session_state:
        st.session_state.sce_limpiar_pendiente = False

    if "sce_editor_nonce" not in st.session_state:
        st.session_state.sce_editor_nonce = 0


def _limpiar_form_estandar():
    st.session_state.sce_observaciones = ""
    st.session_state.sce_departamento = ""
    st.session_state.sce_forma_pago = ""
    st.session_state.sce_detalle = pd.DataFrame([_fila_vacia_estandar()])
    st.session_state.sce_limpiar_pendiente = False
    st.session_state.sce_editor_nonce += 1


def _aplicar_limpieza_estandar():
    if st.session_state.get("sce_limpiar_pendiente", False):
        _limpiar_form_estandar()


def _normalizar_df_estandar(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    cols = [
        "cantidad",
        "descripcion_producto_servicio",
        "unidad_negocio_sigla",
        "porcentaje",
        "fecha_requerida",
        "proveedor",
        "precio_unitario",
        "costo_total_sin_iva",
    ]
    for col in cols:
        if col not in df.columns:
            df[col] = None if col in ("cantidad", "porcentaje", "fecha_requerida", "precio_unitario", "costo_total_sin_iva") else ""

    for col in ["cantidad", "porcentaje", "precio_unitario", "costo_total_sin_iva"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    def _to_date(v):
        if pd.isna(v) or v in ("", None):
            return None
        try:
            return pd.to_datetime(v).date()
        except Exception:
            return None

    df["fecha_requerida"] = df["fecha_requerida"].apply(_to_date)

    for col in ["descripcion_producto_servicio", "unidad_negocio_sigla", "proveedor"]:
        df[col] = df[col].apply(lambda x: "" if pd.isna(x) else str(x).strip())

    return df


def mostrar_formulario_compra_estandar(id_tipo_compra: int):
    _init_form_estandar_state()
    _aplicar_limpieza_estandar()

    solicitante_actual = _get_solicitante_actual()
    fecha_hoy = date.today()

    departamentos = get_departamentos_compra_ctrl() or []
    formas_pago = get_formas_pago_compra_ctrl() or []
    df_unidades = get_unidades_negocio_compra_ctrl()

    opciones_departamentos = {
        str(r.get("nombre") or "").strip(): int(r.get("id_departamento") or 0)
        for r in departamentos
        if int(r.get("id_departamento") or 0) > 0 and str(r.get("nombre") or "").strip()
    }

    opciones_forma_pago = {
        str(r.get("nombre") or "").strip(): int(r.get("id_forma_pago") or 0)
        for r in formas_pago
        if int(r.get("id_forma_pago") or 0) > 0 and str(r.get("nombre") or "").strip()
    }

    opciones_unidades = []
    if not df_unidades.empty:
        for col in ["sigla", "Sigla", "SIGLA"]:
            if col in df_unidades.columns:
                opciones_unidades = [
                    str(x).strip() for x in df_unidades[col].dropna().tolist() if str(x).strip()
                ]
                break

    st.markdown("### solicitud de compra - formato estándar")

    c1, c2, c3 = st.columns([2, 1, 1])

    with c1:
        st.text_input(
            "solicitante interno",
            value=solicitante_actual,
            disabled=True,
            key="sce_solicitante_mostrar",
        )

    with c2:
        st.date_input(
            "fecha elaboración",
            value=fecha_hoy,
            disabled=True,
            format="DD/MM/YYYY",
            key="sce_fecha_mostrar",
        )

    with c3:
        st.text_input(
            "folio",
            value="se genera al guardar",
            disabled=True,
            key="sce_folio_mostrar",
        )

    c4, c5 = st.columns(2)

    with c4:
        st.selectbox(
            "departamento",
            options=[""] + list(opciones_departamentos.keys()),
            key="sce_departamento",
        )

    with c5:
        st.selectbox(
            "forma de pago",
            options=[""] + list(opciones_forma_pago.keys()),
            key="sce_forma_pago",
        )

    st.text_area(
        "observaciones",
        key="sce_observaciones",
        height=100,
    )

    st.divider()
    st.markdown("### detalle de solicitud")

    if (
        "sce_detalle" not in st.session_state
        or not isinstance(st.session_state.sce_detalle, pd.DataFrame)
        or st.session_state.sce_detalle.empty
    ):
        st.session_state.sce_detalle = pd.DataFrame([_fila_vacia_estandar()])

    df_base = st.session_state.sce_detalle.copy()
    editor_key = f"sce_editor_{st.session_state.sce_editor_nonce}"

    df_edit = st.data_editor(
        df_base,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key=editor_key,
        column_config={
            "cantidad": st.column_config.NumberColumn("cantidad", min_value=0.0, step=1.0, format="%.2f"),
            "descripcion_producto_servicio": st.column_config.TextColumn("descripción del producto y/o servicio"),
            "unidad_negocio_sigla": st.column_config.SelectboxColumn(
                "unidad de negocio sigla",
                options=opciones_unidades,
            ),
            "porcentaje": st.column_config.NumberColumn("%", min_value=0.0, max_value=100.0, step=1.0, format="%.2f"),
            "fecha_requerida": st.column_config.DateColumn("fecha requerida", format="DD/MM/YYYY"),
            "proveedor": st.column_config.TextColumn("proveedor"),
            "precio_unitario": st.column_config.NumberColumn("precio unitario", min_value=0.0, step=1.0, format="%.2f"),
            "costo_total_sin_iva": st.column_config.NumberColumn("costo total sin IVA", min_value=0.0, step=1.0, format="%.2f"),
        },
    )

    st.divider()

    b1, b2 = st.columns(2)

    with b1:
        if st.button("guardar solicitud estándar", use_container_width=True):
            nombre_departamento = st.session_state.sce_departamento
            nombre_forma_pago = st.session_state.sce_forma_pago

            id_departamento = opciones_departamentos.get(nombre_departamento, 0)
            id_forma_pago = opciones_forma_pago.get(nombre_forma_pago, 0)

            df_det = _normalizar_df_estandar(df_edit)

            mask_vacias = (
                df_det["cantidad"].isna()
                & df_det["descripcion_producto_servicio"].eq("")
                & df_det["proveedor"].eq("")
                & df_det["precio_unitario"].isna()
                & df_det["costo_total_sin_iva"].isna()
            )
            df_det = df_det[~mask_vacias].copy()

            if df_det.empty:
                st.warning("agrega al menos un renglón con datos")
                return

            errores = []
            detalle_final = []

            for idx, row in df_det.reset_index(drop=True).iterrows():
                fila = idx + 1

                cantidad = row["cantidad"]
                descripcion = row["descripcion_producto_servicio"]
                unidad = row["unidad_negocio_sigla"]
                porcentaje = row["porcentaje"]
                fecha_requerida = row["fecha_requerida"]
                proveedor = row["proveedor"]
                precio_unitario = row["precio_unitario"]
                costo_total = row["costo_total_sin_iva"]

                if pd.isna(cantidad) or float(cantidad) <= 0:
                    errores.append(f"fila {fila}: cantidad inválida")
                if not descripcion:
                    errores.append(f"fila {fila}: falta descripción del producto y/o servicio")

                detalle_final.append({
                    "cantidad": float(cantidad) if not pd.isna(cantidad) else None,
                    "descripcion_producto_servicio": descripcion,
                    "unidad_negocio_sigla": unidad,
                    "porcentaje": float(porcentaje) if not pd.isna(porcentaje) else None,
                    "fecha_requerida": fecha_requerida.isoformat() if fecha_requerida else None,
                    "proveedor": proveedor,
                    "precio_unitario": float(precio_unitario) if not pd.isna(precio_unitario) else None,
                    "costo_total_sin_iva": float(costo_total) if not pd.isna(costo_total) else None,
                })

            if not id_departamento:
                errores.append("falta seleccionar departamento")

            if not id_forma_pago:
                errores.append("falta seleccionar forma de pago")

            if errores:
                st.error("no se puede guardar:\n\n" + "\n".join(errores[:15]))
                return

            ok, mensaje = crear_solicitud_estandar_ctrl(
                id_tipo_compra=id_tipo_compra,
                fecha_solicitud=fecha_hoy,
                solicitante=solicitante_actual,
                observaciones_generales=st.session_state.sce_observaciones,
                id_departamento=id_departamento,
                id_forma_pago=id_forma_pago,
                detalle=detalle_final,
            )

            if ok:
                st.success(mensaje)
                st.session_state.sce_limpiar_pendiente = True
                st.rerun()
            else:
                st.error(mensaje)

    with b2:
        if st.button("limpiar formulario estándar", use_container_width=True):
            st.session_state.sce_limpiar_pendiente = True
            st.rerun()