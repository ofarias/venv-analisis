import streamlit as st

from controllers.compras_solicitudes_controller import (
    obtener_tipos_compra_activos_ctrl,
    obtener_solicitudes_compra_ctrl,
)
from views.modulo_compras.forms.form_producto_view import mostrar_formulario_compra_producto


def mostrar_tab_solicitudes_compras():
    st.subheader("solicitudes de compra")

    df_tipos = obtener_tipos_compra_activos_ctrl()

    if df_tipos.empty:
        st.info("no hay tipos de compra activos en el catálogo.")
        return

    opciones = {
        row["nombre"]: int(row["id_tipo_compra"])
        for _, row in df_tipos.iterrows()
    }

    nombre_tipo = st.selectbox(
        "tipo de compra",
        options=list(opciones.keys())
    )

    id_tipo_compra = opciones[nombre_tipo]

    st.divider()

    if nombre_tipo == "Producto":
        mostrar_formulario_compra_producto(id_tipo_compra=id_tipo_compra)
    else:
        st.warning(f"el formulario para '{nombre_tipo}' aún no ha sido creado.")

    st.divider()
    st.markdown("### solicitudes registradas")

    df_solicitudes = obtener_solicitudes_compra_ctrl()

    if df_solicitudes.empty:
        st.info("no hay solicitudes registradas.")
        return

    cols = [
        "id_solicitud_compra",
        "fecha_solicitud",
        "tipo_compra",
        "solicitante",
        "estatus",
        "cliente",
        "numero_pedido",
        "producto",
        "cantidad",
    ]

    cols_existentes = [c for c in cols if c in df_solicitudes.columns]

    st.dataframe(
        df_solicitudes[cols_existentes],
        use_container_width=True,
        hide_index=True,
    )