import streamlit as st

from controllers.compras_solicitudes_controller import (
    obtener_tipos_compra_activos_ctrl,
)
from views.modulo_compras.forms.form_producto_view import (
    mostrar_formulario_compra_materias_primas,
)

from views.modulo_compras.forms.form_estandar_view import (
    mostrar_formulario_compra_estandar,
)



def mostrar_tab_solicitudes_compras():
    st.subheader("solicitudes de compra")

    tipos = obtener_tipos_compra_activos_ctrl() or []

    if not tipos:
        st.info("no hay tipos de compra activos")
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

    st.divider()

    if nombre_tipo == "Materias Primas":
        mostrar_formulario_compra_materias_primas(id_tipo_compra=id_tipo_compra)
    else:
        mostrar_formulario_compra_estandar(id_tipo_compra=id_tipo_compra)