#unidades_view.py
import streamlit as st
import pandas as pd
from controllers.unidades_controller import get_unidades, crear_unidad, cambiar_estatus_unidad

def pantalla_unidades():
    st.title("Gestión de Unidades de Negocio")

    with st.expander("➕ Agregar nueva unidad", expanded=False):
        col1, col2, col3 = st.columns(3)
        nombre = col1.text_input("Nombre de la unidad")
        id_ant = col2.number_input("ID anterior (opcional)", value=0, step=1)
        creador = col3.text_input("Creador", value="admin")

        if st.button("Guardar unidad", use_container_width=True):
            crear_unidad(nombre, id_ant if id_ant > 0 else None, creador)
            st.success(f"Unidad '{nombre}' creada correctamente.")
            st.rerun()

    st.divider()
    st.subheader("📋 Unidades existentes")

    df = get_unidades()
    if df.empty:
        st.info("No hay unidades registradas.")
        return

    st.dataframe(df, use_container_width=True)

    ids = df["id"].tolist()
    sel_id = st.selectbox("Seleccionar unidad para cambiar estatus", ids)
    nuevo_estatus = st.radio("Nuevo estatus", [1, 0], format_func=lambda x: "Activo" if x == 1 else "Inactivo")

    if st.button("Actualizar estatus", type="primary"):
        cambiar_estatus_unidad(sel_id, nuevo_estatus)
        st.success("Estatus actualizado correctamente.")
        st.rerun()

#unidades_controller.py
from models.unidades_model import obtener_unidades, insertar_unidad, actualizar_estatus_unidad

def get_unidades(limit=500, offset=0):
    return obtener_unidades(limit, offset)

def crear_unidad(nombre, id_ant, creador):
    return insertar_unidad(nombre, id_ant, creador)

def cambiar_estatus_unidad(id_unidad, estatus):
    return actualizar_estatus_unidad(id_unidad, estatus)