from datetime import date

import pandas as pd
import streamlit as st

from controllers.compras_tipos_campos_controller import obtener_campos_tipo_ctrl
from controllers.compras_solicitudes_dinamico_controller import crear_solicitud_dinamica_ctrl


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


def _render_campo(campo: dict, key: str, valor_actual=None):
    etiqueta = campo["nombre_campo"] + (" *" if campo["requerido"] else "")
    tipo_dato = campo["tipo_dato"]

    if tipo_dato == "numero":
        return st.number_input(etiqueta, value=float(valor_actual) if valor_actual not in (None, "") else 0.0, key=key)
    if tipo_dato == "fecha":
        return st.date_input(etiqueta, value=valor_actual or date.today(), key=key)
    if tipo_dato == "texto_largo":
        return st.text_area(etiqueta, value=str(valor_actual or ""), key=key)
    if tipo_dato == "seleccion":
        opciones = [o.strip() for o in str(campo.get("opciones") or "").splitlines() if o.strip()]
        opciones_con_vacio = [""] + opciones
        indice = opciones_con_vacio.index(valor_actual) if valor_actual in opciones_con_vacio else 0
        return st.selectbox(etiqueta, options=opciones_con_vacio, index=indice, key=key)
    return st.text_input(etiqueta, value=str(valor_actual or ""), key=key)


def _fila_vacia(campos_det: list[dict]) -> dict:
    return {c["clave_campo"]: ("" if c["tipo_dato"] != "numero" else 0.0) for c in campos_det}


def mostrar_formulario_compra_dinamico(id_tipo_compra: int):
    campos_cab = obtener_campos_tipo_ctrl(id_tipo_compra, "cabecera")
    campos_det = obtener_campos_tipo_ctrl(id_tipo_compra, "detalle")

    nonce_key = f"sdin_editor_nonce_{id_tipo_compra}"
    if nonce_key not in st.session_state:
        st.session_state[nonce_key] = 0

    detalle_key = f"sdin_detalle_{id_tipo_compra}_{st.session_state[nonce_key]}"
    if detalle_key not in st.session_state:
        st.session_state[detalle_key] = pd.DataFrame([_fila_vacia(campos_det)]) if campos_det else pd.DataFrame()

    st.markdown("#### cabecera")
    fecha_solicitud = st.date_input("fecha de solicitud", value=date.today(), key=f"sdin_fecha_{id_tipo_compra}")
    observaciones_generales = st.text_area(
        "observaciones generales", key=f"sdin_obs_{id_tipo_compra}",
    )

    valores_cabecera = {}
    if campos_cab:
        cols = st.columns(2)
        for i, campo in enumerate(campos_cab):
            with cols[i % 2]:
                valores_cabecera[campo["clave_campo"]] = _render_campo(
                    campo, key=f"sdin_cab_{id_tipo_compra}_{campo['clave_campo']}",
                )
    else:
        st.caption("este tipo de compra no tiene campos de cabecera configurados.")

    if campos_det:
        st.markdown("#### detalle")
        column_config = {}
        for campo in campos_det:
            etiqueta = campo["nombre_campo"] + (" *" if campo["requerido"] else "")
            if campo["tipo_dato"] == "numero":
                column_config[campo["clave_campo"]] = st.column_config.NumberColumn(etiqueta)
            elif campo["tipo_dato"] == "fecha":
                column_config[campo["clave_campo"]] = st.column_config.DateColumn(etiqueta)
            elif campo["tipo_dato"] == "seleccion":
                opciones = [o.strip() for o in str(campo.get("opciones") or "").splitlines() if o.strip()]
                column_config[campo["clave_campo"]] = st.column_config.SelectboxColumn(etiqueta, options=opciones)
            else:
                column_config[campo["clave_campo"]] = st.column_config.TextColumn(etiqueta)

        df_detalle = st.data_editor(
            st.session_state[detalle_key],
            num_rows="dynamic",
            use_container_width=True,
            column_config=column_config,
            key=f"sdin_editor_{id_tipo_compra}_{st.session_state[nonce_key]}",
        )
    else:
        df_detalle = pd.DataFrame()
        st.caption("este tipo de compra no tiene campos de detalle configurados.")

    if st.button("guardar solicitud", type="primary", key=f"sdin_btn_guardar_{id_tipo_compra}"):
        renglones = [
            {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in row.items()}
            for row in df_detalle.to_dict("records")
        ] if not df_detalle.empty else []
        valores_cabecera_serial = {
            k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in valores_cabecera.items()
        }
        ok, mensaje = crear_solicitud_dinamica_ctrl(
            id_tipo_compra=id_tipo_compra,
            fecha_solicitud=fecha_solicitud,
            solicitante=_get_solicitante_actual(),
            observaciones_generales=observaciones_generales,
            valores_cabecera=valores_cabecera_serial,
            renglones=renglones,
        )
        if ok:
            st.success(mensaje)
            st.session_state[nonce_key] += 1
            st.rerun()
        else:
            st.error(mensaje)
