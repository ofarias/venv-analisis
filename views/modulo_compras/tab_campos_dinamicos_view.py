import pandas as pd
import streamlit as st

from controllers.compras_catalogos_controller import obtener_tipos_compra_ctrl
from controllers.compras_tipos_campos_controller import (
    TIPOS_DATO,
    obtener_campos_tipo_ctrl,
    crear_campo_tipo_ctrl,
    actualizar_campo_tipo_ctrl,
    eliminar_campo_tipo_ctrl,
)

_ETIQUETA_TIPO_DATO = {
    "texto": "texto corto", "texto_largo": "texto largo", "numero": "número",
    "fecha": "fecha", "seleccion": "selección (catálogo fijo)",
}


def _init_state(seccion: str):
    defaults = {
        f"cd_{seccion}_id": None,
        f"cd_{seccion}_nombre": "",
        f"cd_{seccion}_tipo_dato": "texto",
        f"cd_{seccion}_opciones": "",
        f"cd_{seccion}_requerido": False,
        f"cd_{seccion}_orden": 0,
        f"cd_{seccion}_activo": True,
        f"cd_{seccion}_cargar": None,
        f"cd_{seccion}_limpiar": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _aplicar_pendientes(seccion: str):
    if st.session_state.get(f"cd_{seccion}_limpiar", False):
        st.session_state[f"cd_{seccion}_id"] = None
        st.session_state[f"cd_{seccion}_nombre"] = ""
        st.session_state[f"cd_{seccion}_tipo_dato"] = "texto"
        st.session_state[f"cd_{seccion}_opciones"] = ""
        st.session_state[f"cd_{seccion}_requerido"] = False
        st.session_state[f"cd_{seccion}_orden"] = 0
        st.session_state[f"cd_{seccion}_activo"] = True
        st.session_state[f"cd_{seccion}_cargar"] = None
        st.session_state[f"cd_{seccion}_limpiar"] = False

    data = st.session_state.get(f"cd_{seccion}_cargar")
    if data:
        st.session_state[f"cd_{seccion}_id"] = data["id"]
        st.session_state[f"cd_{seccion}_nombre"] = data["nombre_campo"]
        st.session_state[f"cd_{seccion}_tipo_dato"] = data["tipo_dato"]
        st.session_state[f"cd_{seccion}_opciones"] = data["opciones"] or ""
        st.session_state[f"cd_{seccion}_requerido"] = bool(data["requerido"])
        st.session_state[f"cd_{seccion}_orden"] = int(data["orden"])
        st.session_state[f"cd_{seccion}_activo"] = bool(data["activo"])
        st.session_state[f"cd_{seccion}_cargar"] = None


def _bloque_seccion(id_tipo_compra: int, seccion: str, titulo: str):
    _init_state(seccion)
    _aplicar_pendientes(seccion)

    st.markdown(f"#### {titulo}")

    campos = obtener_campos_tipo_ctrl(id_tipo_compra, seccion)

    c1, c2 = st.columns([1, 2])

    with c1:
        st.text_input("nombre del campo", key=f"cd_{seccion}_nombre")
        st.selectbox(
            "tipo de dato", options=TIPOS_DATO,
            format_func=lambda t: _ETIQUETA_TIPO_DATO.get(t, t),
            key=f"cd_{seccion}_tipo_dato",
        )
        if st.session_state[f"cd_{seccion}_tipo_dato"] == "seleccion":
            st.text_area(
                "opciones (una por línea)", key=f"cd_{seccion}_opciones", height=100,
            )
        st.checkbox("obligatorio", key=f"cd_{seccion}_requerido")
        st.number_input("orden", min_value=0, step=1, key=f"cd_{seccion}_orden")
        st.checkbox("activo", key=f"cd_{seccion}_activo")

        b1, b2 = st.columns(2)
        with b1:
            if st.session_state[f"cd_{seccion}_id"] is None:
                if st.button("agregar campo", use_container_width=True, key=f"cd_{seccion}_btn_crear"):
                    ok, mensaje = crear_campo_tipo_ctrl(
                        id_tipo_compra=id_tipo_compra, seccion=seccion,
                        nombre_campo=st.session_state[f"cd_{seccion}_nombre"],
                        tipo_dato=st.session_state[f"cd_{seccion}_tipo_dato"],
                        opciones=st.session_state[f"cd_{seccion}_opciones"],
                        requerido=st.session_state[f"cd_{seccion}_requerido"],
                        orden=st.session_state[f"cd_{seccion}_orden"],
                    )
                    if ok:
                        st.success(mensaje)
                        st.session_state[f"cd_{seccion}_limpiar"] = True
                        st.rerun()
                    else:
                        st.error(mensaje)
            else:
                if st.button("actualizar campo", use_container_width=True, key=f"cd_{seccion}_btn_actualizar"):
                    ok, mensaje = actualizar_campo_tipo_ctrl(
                        id=st.session_state[f"cd_{seccion}_id"],
                        nombre_campo=st.session_state[f"cd_{seccion}_nombre"],
                        tipo_dato=st.session_state[f"cd_{seccion}_tipo_dato"],
                        opciones=st.session_state[f"cd_{seccion}_opciones"],
                        requerido=st.session_state[f"cd_{seccion}_requerido"],
                        orden=st.session_state[f"cd_{seccion}_orden"],
                        activo=st.session_state[f"cd_{seccion}_activo"],
                    )
                    if ok:
                        st.success(mensaje)
                        st.session_state[f"cd_{seccion}_limpiar"] = True
                        st.rerun()
                    else:
                        st.error(mensaje)
        with b2:
            if st.button("limpiar", use_container_width=True, key=f"cd_{seccion}_btn_limpiar"):
                st.session_state[f"cd_{seccion}_limpiar"] = True
                st.rerun()

    with c2:
        if not campos:
            st.info(f"no hay campos de {seccion} capturados todavía.")
            return

        df = pd.DataFrame(campos)
        df["tipo_dato"] = df["tipo_dato"].map(lambda t: _ETIQUETA_TIPO_DATO.get(t, t))
        df["requerido"] = df["requerido"].map({1: "sí", 0: "no"})
        df["activo"] = df["activo"].map({1: "activo", 0: "inactivo"})
        st.dataframe(
            df[["orden", "nombre_campo", "tipo_dato", "requerido", "activo"]].rename(columns={
                "nombre_campo": "nombre", "orden": "orden",
            }),
            use_container_width=True, hide_index=True,
        )

        opciones_sel = {
            f'{c["nombre_campo"]} ({_ETIQUETA_TIPO_DATO.get(c["tipo_dato"], c["tipo_dato"])})': c["id"]
            for c in campos
        }
        seleccion = st.selectbox(
            "selecciona un campo", options=list(opciones_sel.keys()), key=f"cd_{seccion}_sel",
        )
        id_sel = opciones_sel[seleccion]
        campo_sel = next(c for c in campos if c["id"] == id_sel)

        x1, x2 = st.columns(2)
        with x1:
            if st.button("editar", use_container_width=True, key=f"cd_{seccion}_btn_editar"):
                st.session_state[f"cd_{seccion}_cargar"] = campo_sel
                st.rerun()
        with x2:
            if st.button("🗑️ eliminar", use_container_width=True, key=f"cd_{seccion}_btn_eliminar"):
                ok, mensaje = eliminar_campo_tipo_ctrl(id_sel)
                if ok:
                    st.success(mensaje)
                    if st.session_state[f"cd_{seccion}_id"] == id_sel:
                        st.session_state[f"cd_{seccion}_limpiar"] = True
                    st.rerun()
                else:
                    st.error(mensaje)


def mostrar_tab_campos_dinamicos():
    st.subheader("⚙️ formularios dinámicos")
    st.caption(
        "Define los campos de cabecera y de detalle para un tipo de compra con formulario "
        "\"DINAMICO\" — sin tocar código. Los tipos MP, STD y Materia Prima (Inventario) ya "
        "tienen su propio formulario y no se configuran aquí."
    )

    df_tipos = obtener_tipos_compra_ctrl()
    df_dinamicos = df_tipos[df_tipos["tipo_formulario"].astype(str).str.strip().str.upper() == "DINAMICO"]

    if df_dinamicos.empty:
        st.info(
            "no hay tipos de compra con formulario \"DINAMICO\" todavía — crea uno en "
            "Catálogos → Tipos de Compra (tipo de formulario = DINAMICO) y vuelve aquí."
        )
        return

    opciones = {
        f'{int(row["id_tipo_compra"])} - {str(row["nombre"] or "").strip()}': int(row["id_tipo_compra"])
        for _, row in df_dinamicos.iterrows()
    }
    seleccion = st.selectbox("tipo de compra", options=list(opciones.keys()), key="cd_tipo_sel")
    id_tipo_compra = opciones[seleccion]

    st.divider()
    _bloque_seccion(id_tipo_compra, "cabecera", "campos de cabecera")
    st.divider()
    _bloque_seccion(id_tipo_compra, "detalle", "campos de detalle")
