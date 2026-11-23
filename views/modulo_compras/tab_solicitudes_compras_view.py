#tab_solicitudes_compras_view.py

import streamlit as st

from controllers.compras_solicitudes_controller import (
    obtener_tipos_compra_activos_para_usuario_ctrl,
)
from controllers.compras_subtipos_controller import obtener_subtipos_activos_para_usuario_ctrl
from views.modulo_compras.forms.form_producto_view import (
    mostrar_formulario_compra_materias_primas,
)
from views.modulo_compras.forms.form_estandar_view import (
    mostrar_formulario_compra_estandar,
)
from views.modulo_compras.forms.form_mp_inventario_view import (
    mostrar_formulario_compra_mp_inventario,
)
from views.modulo_compras.forms.form_dinamico_view import (
    mostrar_formulario_compra_dinamico,
)


def _get_tipo_formulario(id_tipo_compra: int, tipos: list) -> str:
    for t in tipos:
        if int(t.get("id_tipo_compra") or 0) == int(id_tipo_compra):
            return str(t.get("tipo_formulario") or "").strip().upper()
    return ""


def mostrar_tab_solicitudes_compras():
    st.subheader("solicitudes de compra")

    usuario_id = (st.session_state.get("usuario") or {}).get("id")
    tipos = obtener_tipos_compra_activos_para_usuario_ctrl(usuario_id) or []

    if not tipos:
        st.info("no hay tipos de compra disponibles para tu usuario.")
        return

    opciones = {
        str(t.get("nombre") or "").strip(): int(t.get("id_tipo_compra") or 0)
        for t in tipos
        if int(t.get("id_tipo_compra") or 0) > 0 and str(t.get("nombre") or "").strip()
    }

    if not opciones:
        st.info("no hay tipos de compra disponibles")
        return

    nombre_tipo = st.selectbox(
        "tipo de compra",
        options=list(opciones.keys()),
        key="scp_tipo_compra",
    )

    id_tipo_compra = opciones[nombre_tipo]
    tipo_formulario = _get_tipo_formulario(id_tipo_compra, tipos)
    st.write(f"has seleccionado el tipo de compra: **{nombre_tipo}** con formulario **{tipo_formulario}**")

    # subtipo: si el tipo tiene subtipos capturados (ver Catálogos -> subtipos),
    # hay que elegir uno antes de continuar — solo se ofrecen los que el
    # usuario puede solicitar según su puesto (vacío de puestos = cualquiera).
    id_subtipo = None
    subtipos = obtener_subtipos_activos_para_usuario_ctrl(id_tipo_compra, usuario_id) or []
    if subtipos:
        opciones_subtipo = {str(s["nombre"]).strip(): int(s["id_subtipo"]) for s in subtipos}
        nombre_subtipo = st.selectbox(
            "subtipo", options=list(opciones_subtipo.keys()), key=f"scp_subtipo_{id_tipo_compra}",
        )
        id_subtipo = opciones_subtipo[nombre_subtipo]

    st.divider()

    if tipo_formulario == "MP":
        mostrar_formulario_compra_materias_primas(id_tipo_compra=id_tipo_compra, id_subtipo=id_subtipo)

    elif tipo_formulario == "STD":
        mostrar_formulario_compra_estandar(id_tipo_compra=id_tipo_compra, id_subtipo=id_subtipo)

    elif tipo_formulario == "MP_INV":
        mostrar_formulario_compra_mp_inventario(id_tipo_compra=id_tipo_compra, id_subtipo=id_subtipo)

    elif tipo_formulario == "DINAMICO":
        mostrar_formulario_compra_dinamico(id_tipo_compra=id_tipo_compra, id_subtipo=id_subtipo)

    else:
        st.warning("este tipo de compra no tiene formulario configurado.")