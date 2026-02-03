import streamlit as st
import pandas as pd
from datetime import date
from controllers.presupuesto_controller import (
    get_presupuestos,
    get_unidades_activas,
    get_usuarios_activos,
    crear_presupuesto,
    get_detalle_presupuesto,
    obtener_usuarios_autorizados,
)

# --- Función para reiniciar formulario ---
##def reset_form():
##    """Activa el flag de reinicio y fuerza un rerun"""
##    st.session_state["reset_form_flag"] = True
##    st.rerun()

def reset_form():
    """Limpia campos sin generar advertencia"""
    st.session_state["f_nombre"] = ""
    st.session_state["f_periodo"] = "Mensual"
    st.session_state["f_fecha_ini"] = date.today()
    st.session_state["f_fecha_fin"] = date.today()
    st.session_state["f_monto_mnx"] = 0.0
    st.session_state["f_monto_usd"] = 0.0
    st.session_state["f_unidades"] = []
    st.session_state["f_usuarios"] = []
    st.session_state["f_autorizadores"] = []
    st.toast("🧹 Formulario limpiado correctamente")

    # Ejecuta rerun fuera del callback
    st.session_state["trigger_rerun"] = True


def pantalla_presupuestos():
    st.title("📊 Administración de Presupuestos")

    tabs = st.tabs(["➕ Crear Presupuesto", "📋 Presupuestos", "🔎 Detalle de Presupuestos"])

    # --- TAB 1: CREAR PRESUPUESTO ---
    with tabs[0]:
        if st.session_state.get("trigger_rerun"):
            st.session_state["trigger_rerun"] = False
            st.rerun()

        st.header("➕ Crear nuevo presupuesto")

        unidades_df = get_unidades_activas()
        usuarios_df = get_usuarios_activos()
        usu_auto_df = obtener_usuarios_autorizados()
        username = st.session_state.get("username", "admin")

        # --- Control de reinicio (antes del formulario) ---
        if st.session_state.get("reset_form_flag"):
            st.session_state["f_nombre"] = ""
            st.session_state["f_periodo"] = "Mensual"
            st.session_state["f_fecha_ini"] = date.today()
            st.session_state["f_fecha_fin"] = date.today()
            st.session_state["f_monto_mnx"] = 0.0
            st.session_state["f_monto_usd"] = 0.0
            st.session_state["f_unidades"] = []
            st.session_state["f_usuarios"] = []
            st.session_state["f_autorizadores"] = []
            st.session_state["reset_form_flag"] = False

        with st.form("nuevo_presupuesto"):
            col1, col2 = st.columns(2)
            nombre = col1.text_input("Nombre del presupuesto", key="f_nombre")
            periodo = col2.selectbox(
                "Periodo",
                ["Semanal", "Mensual", "Bimestral", "Trimestral", "Semestral", "Anual"],
                key="f_periodo",
            )

            col3, col4 = st.columns(2)
            fecha_ini = col3.date_input("Fecha inicial", key="f_fecha_ini")
            fecha_fin = col4.date_input("Fecha final", key="f_fecha_fin")

            col5, col6 = st.columns(2)
            monto_mnx = col5.number_input(
                "Monto asignado (MNX)", min_value=0.0, step=100.0, key="f_monto_mnx"
            )
            monto_usd = col6.number_input(
                "Monto asignado (USD)", min_value=0.0, step=100.0, key="f_monto_usd"
            )

            unidades = st.multiselect(
                "Unidades de negocio",
                options=unidades_df["id"].tolist(),
                format_func=lambda x: unidades_df.loc[
                    unidades_df["id"] == x, "nombre"
                ].values[0],
                key="f_unidades",
            )

            usuarios = st.multiselect(
                "Usuarios asignados",
                options=usuarios_df["username"].tolist(),
                format_func=lambda x: usuarios_df.loc[
                    usuarios_df["username"] == x, "nombre_completo"
                ].values[0],
                key="f_usuarios",
            )

            autorizadores = st.multiselect(
                "Autorizadores",
                options=usu_auto_df["username"].tolist(),
                format_func=lambda x: usu_auto_df.loc[
                    usu_auto_df["username"] == x, "nombre_completo"
                ].values[0],
                key="f_autorizadores",
            )

            colb1, colb2 = st.columns(2)
            submitted = colb1.form_submit_button("💾 Guardar presupuesto")
            #limpiar = colb2.form_submit_button("🧹 Limpiar formulario", on_click=reset_form)

            if submitted:
                data = {
                    "unidades": unidades,
                    "usuarios": usuarios,
                    "autorizadores": autorizadores,
                    "nombre": nombre,
                    "periodo": periodo,
                    "fecha_ini": fecha_ini,
                    "fecha_fin": fecha_fin,
                    "monto_mnx": monto_mnx,
                    "monto_usd": monto_usd,
                    "creador": username,
                }

                if crear_presupuesto(data):
                    st.success("✅ Presupuesto creado correctamente con detalle.")
                    st.rerun()
                else:
                    st.error("❌ No se pudo guardar el presupuesto.")
        # Botón fuera del form para evitar conflicto
        st.button("🧹 Limpiar formulario", on_click=reset_form)

    # --- TAB 2: LISTADO DE PRESUPUESTOS ---
    with tabs[1]:
        st.header("📋 Presupuestos existentes")
        df = get_presupuestos()
        if df.empty:
            st.info("No hay presupuestos registrados.")
        else:
            st.dataframe(df, use_container_width=True)

    # --- TAB 3: DETALLE DE PRESUPUESTOS ---
    with tabs[2]:
        st.header("🔎 Detalle por presupuesto")

        df = get_presupuestos()
        if df.empty:
            st.info("No hay presupuestos registrados.")
        else:
            sel_id = st.selectbox(
                "Selecciona un presupuesto",
                df["Id"].tolist(),
                format_func=lambda x: df.loc[df["Id"] == x, "Nombre"].values[0],
            )

            detalle_df = get_detalle_presupuesto(sel_id)
            if detalle_df.empty:
                st.warning("Este presupuesto no tiene detalle registrado.")
            else:
                st.dataframe(detalle_df, use_container_width=True)