import pandas as pd
import streamlit as st

from controllers.compras_catalogos_controller import (
    obtener_tipos_compra_ctrl,
    crear_tipo_compra_ctrl,
    actualizar_tipo_compra_ctrl,
    cambiar_estatus_tipo_compra_ctrl,
)


def _inicializar_session_state():
    if "compras_tipo_editar_id" not in st.session_state:
        st.session_state.compras_tipo_editar_id = None

    if "compras_tipo_nombre" not in st.session_state:
        st.session_state.compras_tipo_nombre = ""

    if "compras_tipo_descripcion" not in st.session_state:
        st.session_state.compras_tipo_descripcion = ""

    if "compras_tipo_activo" not in st.session_state:
        st.session_state.compras_tipo_activo = True

    if "compras_tipo_cargar_edicion" not in st.session_state:
        st.session_state.compras_tipo_cargar_edicion = None

    if "compras_tipo_limpiar_pendiente" not in st.session_state:
        st.session_state.compras_tipo_limpiar_pendiente = False


def _solicitar_limpieza_formulario():
    st.session_state.compras_tipo_limpiar_pendiente = True


def _aplicar_limpieza_pendiente():
    if not st.session_state.get("compras_tipo_limpiar_pendiente", False):
        return

    st.session_state.compras_tipo_editar_id = None
    st.session_state.compras_tipo_nombre = ""
    st.session_state.compras_tipo_descripcion = ""
    st.session_state.compras_tipo_activo = True
    st.session_state.compras_tipo_cargar_edicion = None
    st.session_state.compras_tipo_limpiar_pendiente = False


def _preparar_edicion(row):
    st.session_state.compras_tipo_cargar_edicion = {
        "id_tipo_compra": int(row["id_tipo_compra"]),
        "nombre": row["nombre"] if pd.notna(row["nombre"]) else "",
        "descripcion": row["descripcion"] if pd.notna(row["descripcion"]) else "",
        "activo": bool(row["activo"]),
    }


def _aplicar_edicion_pendiente():
    data = st.session_state.get("compras_tipo_cargar_edicion")

    if not data:
        return

    st.session_state.compras_tipo_editar_id = data["id_tipo_compra"]
    st.session_state.compras_tipo_nombre = data["nombre"]
    st.session_state.compras_tipo_descripcion = data["descripcion"]
    st.session_state.compras_tipo_activo = data["activo"]
    st.session_state.compras_tipo_cargar_edicion = None


def mostrar_tab_catalogos_compras():
    _inicializar_session_state()
    _aplicar_limpieza_pendiente()
    _aplicar_edicion_pendiente()

    st.subheader("catálogo de tipos de compra")

    df = obtener_tipos_compra_ctrl()

    col1, col2 = st.columns([1, 2])

    with col1:
        st.markdown("### captura / edición")

        st.text_input(
            "nombre",
            key="compras_tipo_nombre",
            placeholder="ej. papelería"
        )

        st.text_area(
            "descripción",
            key="compras_tipo_descripcion",
            placeholder="descripción opcional"
        )

        st.checkbox(
            "activo",
            key="compras_tipo_activo"
        )

        c1, c2 = st.columns(2)

        with c1:
            if st.session_state.compras_tipo_editar_id is None:
                if st.button("guardar", use_container_width=True):
                    ok, mensaje = crear_tipo_compra_ctrl(
                        nombre=st.session_state.compras_tipo_nombre,
                        descripcion=st.session_state.compras_tipo_descripcion,
                        activo=1 if st.session_state.compras_tipo_activo else 0
                    )

                    if ok:
                        _solicitar_limpieza_formulario()
                        st.success(mensaje)
                        st.rerun()
                    else:
                        st.error(mensaje)
            else:
                if st.button("actualizar", use_container_width=True):
                    ok, mensaje = actualizar_tipo_compra_ctrl(
                        id_tipo_compra=st.session_state.compras_tipo_editar_id,
                        nombre=st.session_state.compras_tipo_nombre,
                        descripcion=st.session_state.compras_tipo_descripcion,
                        activo=1 if st.session_state.compras_tipo_activo else 0
                    )

                    if ok:
                        _solicitar_limpieza_formulario()
                        st.success(mensaje)
                        st.rerun()
                    else:
                        st.error(mensaje)

        with c2:
            if st.button("limpiar", use_container_width=True):
                _solicitar_limpieza_formulario()
                st.rerun()

        if st.session_state.compras_tipo_editar_id is not None:
            st.caption(f"editando id: {st.session_state.compras_tipo_editar_id}")

    with col2:
        st.markdown("### registros")

        if df.empty:
            st.info("no hay tipos de compra registrados.")
            return

        df_mostrar = df[[
            "id_tipo_compra",
            "nombre",
            "descripcion",
            "estatus"
        ]].copy()

        st.dataframe(df_mostrar, use_container_width=True, hide_index=True)

        opciones = {
            f'{row["id_tipo_compra"]} - {row["nombre"]}': row["id_tipo_compra"]
            for _, row in df.iterrows()
        }

        seleccion = st.selectbox(
            "selecciona un registro",
            options=list(opciones.keys())
        )

        id_seleccionado = opciones[seleccion]
        row_sel = df[df["id_tipo_compra"] == id_seleccionado].iloc[0]

        a1, a2 = st.columns(2)

        with a1:
            if st.button("editar seleccionado", use_container_width=True):
                _preparar_edicion(row_sel)
                st.rerun()

        with a2:
            nuevo_estatus = 0 if int(row_sel["activo"]) == 1 else 1
            texto_boton = "desactivar seleccionado" if int(row_sel["activo"]) == 1 else "activar seleccionado"

            if st.button(texto_boton, use_container_width=True):
                ok, mensaje = cambiar_estatus_tipo_compra_ctrl(
                    id_tipo_compra=int(row_sel["id_tipo_compra"]),
                    activo=nuevo_estatus
                )

                if ok:
                    if (
                        st.session_state.compras_tipo_editar_id is not None
                        and st.session_state.compras_tipo_editar_id == int(row_sel["id_tipo_compra"])
                    ):
                        _solicitar_limpieza_formulario()
                    st.success(mensaje)
                    st.rerun()
                else:
                    st.error(mensaje)