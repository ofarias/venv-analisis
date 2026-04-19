import pandas as pd
import streamlit as st

from controllers.compras_catalogos_adicionales_controller import (
    obtener_departamentos_ctrl,
    crear_departamento_ctrl,
    actualizar_departamento_ctrl,
    cambiar_estatus_departamento_ctrl,
    obtener_formas_pago_ctrl,
    crear_forma_pago_ctrl,
    actualizar_forma_pago_ctrl,
    cambiar_estatus_forma_pago_ctrl,
)


def _init_state():
    # departamentos
    if "cad_dep_id" not in st.session_state:
        st.session_state.cad_dep_id = None
    if "cad_dep_nombre" not in st.session_state:
        st.session_state.cad_dep_nombre = ""
    if "cad_dep_descripcion" not in st.session_state:
        st.session_state.cad_dep_descripcion = ""
    if "cad_dep_activo" not in st.session_state:
        st.session_state.cad_dep_activo = True
    if "cad_dep_cargar" not in st.session_state:
        st.session_state.cad_dep_cargar = None
    if "cad_dep_limpiar" not in st.session_state:
        st.session_state.cad_dep_limpiar = False

    # formas de pago
    if "cad_fp_id" not in st.session_state:
        st.session_state.cad_fp_id = None
    if "cad_fp_nombre" not in st.session_state:
        st.session_state.cad_fp_nombre = ""
    if "cad_fp_descripcion" not in st.session_state:
        st.session_state.cad_fp_descripcion = ""
    if "cad_fp_activo" not in st.session_state:
        st.session_state.cad_fp_activo = True
    if "cad_fp_cargar" not in st.session_state:
        st.session_state.cad_fp_cargar = None
    if "cad_fp_limpiar" not in st.session_state:
        st.session_state.cad_fp_limpiar = False


def _aplicar_pendientes():
    if st.session_state.get("cad_dep_limpiar", False):
        st.session_state.cad_dep_id = None
        st.session_state.cad_dep_nombre = ""
        st.session_state.cad_dep_descripcion = ""
        st.session_state.cad_dep_activo = True
        st.session_state.cad_dep_cargar = None
        st.session_state.cad_dep_limpiar = False

    data_dep = st.session_state.get("cad_dep_cargar")
    if data_dep:
        st.session_state.cad_dep_id = data_dep["id"]
        st.session_state.cad_dep_nombre = data_dep["nombre"]
        st.session_state.cad_dep_descripcion = data_dep["descripcion"]
        st.session_state.cad_dep_activo = data_dep["activo"]
        st.session_state.cad_dep_cargar = None

    if st.session_state.get("cad_fp_limpiar", False):
        st.session_state.cad_fp_id = None
        st.session_state.cad_fp_nombre = ""
        st.session_state.cad_fp_descripcion = ""
        st.session_state.cad_fp_activo = True
        st.session_state.cad_fp_cargar = None
        st.session_state.cad_fp_limpiar = False

    data_fp = st.session_state.get("cad_fp_cargar")
    if data_fp:
        st.session_state.cad_fp_id = data_fp["id"]
        st.session_state.cad_fp_nombre = data_fp["nombre"]
        st.session_state.cad_fp_descripcion = data_fp["descripcion"]
        st.session_state.cad_fp_activo = data_fp["activo"]
        st.session_state.cad_fp_cargar = None


def _preparar_departamento(row):
    st.session_state.cad_dep_cargar = {
        "id": int(row["id_departamento"]),
        "nombre": row["nombre"] if pd.notna(row["nombre"]) else "",
        "descripcion": row["descripcion"] if pd.notna(row["descripcion"]) else "",
        "activo": bool(row["activo"]),
    }


def _preparar_forma_pago(row):
    st.session_state.cad_fp_cargar = {
        "id": int(row["id_forma_pago"]),
        "nombre": row["nombre"] if pd.notna(row["nombre"]) else "",
        "descripcion": row["descripcion"] if pd.notna(row["descripcion"]) else "",
        "activo": bool(row["activo"]),
    }


def _bloque_departamentos():
    st.markdown("### departamentos")

    df = obtener_departamentos_ctrl()

    c1, c2 = st.columns([1, 2])

    with c1:
        st.text_input("nombre departamento", key="cad_dep_nombre")
        st.text_area("descripción departamento", key="cad_dep_descripcion", height=100)
        st.checkbox("activo", key="cad_dep_activo")

        b1, b2 = st.columns(2)

        with b1:
            if st.session_state.cad_dep_id is None:
                if st.button("guardar departamento", use_container_width=True):
                    ok, mensaje = crear_departamento_ctrl(
                        nombre=st.session_state.cad_dep_nombre,
                        descripcion=st.session_state.cad_dep_descripcion,
                        activo=1 if st.session_state.cad_dep_activo else 0,
                    )
                    if ok:
                        st.success(mensaje)
                        st.session_state.cad_dep_limpiar = True
                        st.rerun()
                    else:
                        st.error(mensaje)
            else:
                if st.button("actualizar departamento", use_container_width=True):
                    ok, mensaje = actualizar_departamento_ctrl(
                        id_departamento=st.session_state.cad_dep_id,
                        nombre=st.session_state.cad_dep_nombre,
                        descripcion=st.session_state.cad_dep_descripcion,
                        activo=1 if st.session_state.cad_dep_activo else 0,
                    )
                    if ok:
                        st.success(mensaje)
                        st.session_state.cad_dep_limpiar = True
                        st.rerun()
                    else:
                        st.error(mensaje)

        with b2:
            if st.button("limpiar departamento", use_container_width=True):
                st.session_state.cad_dep_limpiar = True
                st.rerun()

        if st.session_state.cad_dep_id is not None:
            st.caption(f"editando id: {st.session_state.cad_dep_id}")

    with c2:
        if df.empty:
            st.info("no hay departamentos registrados.")
            return

        st.dataframe(
            df[["id_departamento", "nombre", "descripcion", "estatus"]],
            use_container_width=True,
            hide_index=True,
        )

        opciones = {
            f'{int(row["id_departamento"])} - {str(row["nombre"] or "").strip()}': int(row["id_departamento"])
            for _, row in df.iterrows()
        }

        seleccion = st.selectbox(
            "selecciona departamento",
            options=list(opciones.keys()),
            key="cad_dep_sel",
        )

        id_sel = opciones[seleccion]
        row_sel = df[df["id_departamento"] == id_sel].iloc[0]

        x1, x2 = st.columns(2)

        with x1:
            if st.button("editar departamento", use_container_width=True):
                _preparar_departamento(row_sel)
                st.rerun()

        with x2:
            nuevo_estatus = 0 if int(row_sel["activo"]) == 1 else 1
            texto = "desactivar departamento" if int(row_sel["activo"]) == 1 else "activar departamento"

            if st.button(texto, use_container_width=True):
                ok, mensaje = cambiar_estatus_departamento_ctrl(
                    id_departamento=int(row_sel["id_departamento"]),
                    activo=nuevo_estatus,
                )
                if ok:
                    st.success(mensaje)
                    if (
                        st.session_state.cad_dep_id is not None
                        and st.session_state.cad_dep_id == int(row_sel["id_departamento"])
                    ):
                        st.session_state.cad_dep_limpiar = True
                    st.rerun()
                else:
                    st.error(mensaje)


def _bloque_formas_pago():
    st.markdown("### formas de pago")

    df = obtener_formas_pago_ctrl()

    c1, c2 = st.columns([1, 2])

    with c1:
        st.text_input("nombre forma de pago", key="cad_fp_nombre")
        st.text_area("descripción forma de pago", key="cad_fp_descripcion", height=100)
        st.checkbox("activo forma pago", key="cad_fp_activo")

        b1, b2 = st.columns(2)

        with b1:
            if st.session_state.cad_fp_id is None:
                if st.button("guardar forma pago", use_container_width=True):
                    ok, mensaje = crear_forma_pago_ctrl(
                        nombre=st.session_state.cad_fp_nombre,
                        descripcion=st.session_state.cad_fp_descripcion,
                        activo=1 if st.session_state.cad_fp_activo else 0,
                    )
                    if ok:
                        st.success(mensaje)
                        st.session_state.cad_fp_limpiar = True
                        st.rerun()
                    else:
                        st.error(mensaje)
            else:
                if st.button("actualizar forma pago", use_container_width=True):
                    ok, mensaje = actualizar_forma_pago_ctrl(
                        id_forma_pago=st.session_state.cad_fp_id,
                        nombre=st.session_state.cad_fp_nombre,
                        descripcion=st.session_state.cad_fp_descripcion,
                        activo=1 if st.session_state.cad_fp_activo else 0,
                    )
                    if ok:
                        st.success(mensaje)
                        st.session_state.cad_fp_limpiar = True
                        st.rerun()
                    else:
                        st.error(mensaje)

        with b2:
            if st.button("limpiar forma pago", use_container_width=True):
                st.session_state.cad_fp_limpiar = True
                st.rerun()

        if st.session_state.cad_fp_id is not None:
            st.caption(f"editando id: {st.session_state.cad_fp_id}")

    with c2:
        if df.empty:
            st.info("no hay formas de pago registradas.")
            return

        st.dataframe(
            df[["id_forma_pago", "nombre", "descripcion", "estatus"]],
            use_container_width=True,
            hide_index=True,
        )

        opciones = {
            f'{int(row["id_forma_pago"])} - {str(row["nombre"] or "").strip()}': int(row["id_forma_pago"])
            for _, row in df.iterrows()
        }

        seleccion = st.selectbox(
            "selecciona forma de pago",
            options=list(opciones.keys()),
            key="cad_fp_sel",
        )

        id_sel = opciones[seleccion]
        row_sel = df[df["id_forma_pago"] == id_sel].iloc[0]

        x1, x2 = st.columns(2)

        with x1:
            if st.button("editar forma pago", use_container_width=True):
                _preparar_forma_pago(row_sel)
                st.rerun()

        with x2:
            nuevo_estatus = 0 if int(row_sel["activo"]) == 1 else 1
            texto = "desactivar forma pago" if int(row_sel["activo"]) == 1 else "activar forma pago"

            if st.button(texto, use_container_width=True):
                ok, mensaje = cambiar_estatus_forma_pago_ctrl(
                    id_forma_pago=int(row_sel["id_forma_pago"]),
                    activo=nuevo_estatus,
                )
                if ok:
                    st.success(mensaje)
                    if (
                        st.session_state.cad_fp_id is not None
                        and st.session_state.cad_fp_id == int(row_sel["id_forma_pago"])
                    ):
                        st.session_state.cad_fp_limpiar = True
                    st.rerun()
                else:
                    st.error(mensaje)


def mostrar_tab_catalogos_adicionales():
    _init_state()
    _aplicar_pendientes()

    tabs = st.tabs(["departamentos", "formas de pago"])

    with tabs[0]:
        _bloque_departamentos()

    with tabs[1]:
        _bloque_formas_pago()