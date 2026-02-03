import streamlit as st
import pandas as pd
from datetime import date
from controllers.presupuesto_controller import (
    get_presupuestos_por_usuario,
    get_presupuestos_por_usuario_unidades
)
from models.presupuesto_model import insertar_gasto_no_fiscal


def mostrar_tab_gastos_no_fiscales():
    st.subheader("🧾 Registro de Gastos No Fiscales")

    # -------- inicializa banderas --------
    if "reset_form_nf_flag" not in st.session_state:
        st.session_state["reset_form_nf_flag"] = False
    if "trigger_rerun_nf" not in st.session_state:
        st.session_state["trigger_rerun_nf"] = False

    # -------- control de reinicio (ANTES del formulario) --------
    if st.session_state["reset_form_nf_flag"]:
        st.session_state["proveedor_nf"] = ""
        st.session_state["tipo_nf"] = "Alimentos"
        st.session_state["pago_nf"] = "Efectivo"
        st.session_state["descripcion_nf"] = ""
        st.session_state["monto_nf"] = 0.0
        st.session_state["fecha_nf"] = date.today()
        st.session_state["reset_form_nf_flag"] = False
        st.toast("🧹 Formulario limpiado correctamente")

    # -------- control de rerun como en Crear Presupuesto --------
    if st.session_state["trigger_rerun_nf"]:
        st.session_state["trigger_rerun_nf"] = False
        st.rerun()

    user = st.session_state["usuario"]
    username = user.get("username")
    user_id = user.get("id")

    # --- selección de presupuesto y unidad ---
    col1, col2 = st.columns(2)
    with col1:
        presupuestos_df = get_presupuestos_por_usuario(username)
        if presupuestos_df.empty:
            st.info("No tienes presupuestos asignados.")
            return
        presupuesto_sel = st.selectbox(
            "Selecciona un presupuesto",
            presupuestos_df["Nombre"].tolist(),
            key="presupuesto_nf",
        )

    with col2:
        unidades_df = get_presupuestos_por_usuario_unidades(username)
        if unidades_df.empty:
            st.warning("No hay unidades asignadas para el presupuesto seleccionado.")
            return
        unidad_sel = st.selectbox(
            "Unidad de negocio",
            unidades_df["Unidad_Negocio"].unique().tolist(),
            key="unidad_nf",
        )

    # --- formulario del gasto ---
    with st.form("form_gasto_no_fiscal"):
        col1, col2, col3 = st.columns(3)
        with col1:
            proveedor = st.text_input("Proveedor / Lugar", key="proveedor_nf")
        with col2:
            tipo = st.selectbox(
                "Tipo de gasto",
                ["Alimentos", "Hospedaje", "Propina", "Transporte"],
                key="tipo_nf",
            )
        with col3:
            pago = st.selectbox(
                "Forma de pago",
                ["Efectivo", "TD-Personal", "TC-Personal", "Vales", "TD-Empresa", "TC-Empresa"],
                key="pago_nf",
            )

        descripcion = st.text_area("Descripción del gasto", key="descripcion_nf")

        col4, col5 = st.columns(2)
        with col4:
            fecha_gasto = st.date_input("Fecha del gasto", key="fecha_nf")
        with col5:
            monto = st.number_input(
                "Monto (MXN)", min_value=0.0, step=0.01, format="%.2f", key="monto_nf"
            )

        submitted = st.form_submit_button("💾 Guardar gasto no fiscal")

        if submitted:
            if monto <= 0:
                st.warning("El monto debe ser mayor a 0.")
            else:
                data = {
                    "usuario_id": user_id,
                    "presupuesto": presupuesto_sel,
                    "unidad": unidad_sel,
                    "proveedor": proveedor,
                    "tipo": tipo,
                    "pago": pago,
                    "descripcion": descripcion,
                    "monto": monto,
                    "fecha_gasto": fecha_gasto,
                }

                ok = insertar_gasto_no_fiscal(data)
                if ok:
                    st.success("✅ Gasto no fiscal registrado correctamente.")
                    st.session_state["reset_form_nf_flag"] = True
                    st.session_state["trigger_rerun_nf"] = True
                    st.rerun()
                else:
                    st.error("❌ Ocurrió un error al registrar el gasto.")

    # --- botón externo de limpieza manual ---
    st.button("🧹 Limpiar formulario", on_click=lambda: (
        st.session_state.update({
            "reset_form_nf_flag": True,
            "trigger_rerun_nf": True
        }),
        st.rerun()
    ))