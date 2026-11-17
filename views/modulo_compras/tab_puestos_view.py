import streamlit as st

from controllers.compras_puestos_controller import (
    obtener_puestos_ctrl,
    crear_puesto_ctrl,
    actualizar_puesto_ctrl,
    cambiar_estatus_puesto_ctrl,
    obtener_usuarios_de_puesto_ctrl,
    asignar_usuarios_puesto_ctrl,
)
from models.usuario_model import obtener_usuarios


def mostrar_tab_puestos() -> None:
    st.subheader("🧑‍💼 puestos")
    st.caption(
        "Catálogo de puestos (solo para el módulo de Compras) — cada puesto agrupa a uno o "
        "más usuarios; los flujos de autorización se configuran por puesto, no por usuario "
        "fijo ni por rol."
    )

    with st.expander("➕ crear puesto nuevo"):
        with st.form("form_crear_puesto", clear_on_submit=True):
            nombre_nuevo = st.text_input("nombre del puesto")
            descripcion_nueva = st.text_area("descripción", height=80)
            crear_click = st.form_submit_button("crear puesto", type="primary")
        if crear_click:
            ok, mensaje = crear_puesto_ctrl(nombre_nuevo, descripcion_nueva)
            (st.success if ok else st.error)(mensaje)
            if ok:
                st.rerun()

    st.divider()
    df_puestos = obtener_puestos_ctrl()
    if df_puestos.empty:
        st.info("no hay puestos creados todavía.")
        return

    usuarios = obtener_usuarios()
    opciones_usuario = {f"{u['nombre']} ({u['username']})": u["id"] for u in usuarios}
    nombre_por_usuario_id = {u["id"]: f"{u['nombre']} ({u['username']})" for u in usuarios}

    st.dataframe(
        df_puestos[["nombre", "descripcion", "activo", "usuarios_nombres"]].rename(columns={
            "nombre": "puesto", "descripcion": "descripción", "activo": "activo",
            "usuarios_nombres": "usuarios asignados",
        }),
        hide_index=True, use_container_width=True,
    )

    st.divider()
    st.markdown("### ✏️ editar puesto / asignar usuarios")
    opciones_puesto = {f"{r['nombre']}": r["id_puesto"] for r in df_puestos.to_dict("records")}
    puesto_sel_label = st.selectbox("puesto", options=list(opciones_puesto.keys()), key="puestos_sel")
    id_puesto_sel = opciones_puesto[puesto_sel_label]
    fila_sel = df_puestos[df_puestos["id_puesto"] == id_puesto_sel].iloc[0]

    with st.form(f"form_editar_puesto_{id_puesto_sel}"):
        nombre_edit = st.text_input("nombre", value=fila_sel["nombre"])
        descripcion_edit = st.text_area("descripción", value=fila_sel["descripcion"] or "", height=80)
        activo_edit = st.checkbox("activo", value=bool(fila_sel["activo"]))

        usuarios_actuales_ids = set(obtener_usuarios_de_puesto_ctrl(id_puesto_sel))
        default_sel = [lbl for lbl, uid in opciones_usuario.items() if uid in usuarios_actuales_ids]
        usuarios_sel_labels = st.multiselect(
            "usuarios asignados a este puesto", options=list(opciones_usuario.keys()), default=default_sel,
        )
        guardar_click = st.form_submit_button("💾 guardar cambios", type="primary")

    if guardar_click:
        ok, mensaje = actualizar_puesto_ctrl(id_puesto_sel, nombre_edit, descripcion_edit)
        if ok:
            cambiar_estatus_puesto_ctrl(id_puesto_sel, activo_edit)
            usuario_ids_nuevos = [opciones_usuario[lbl] for lbl in usuarios_sel_labels]
            asignar_usuarios_puesto_ctrl(id_puesto_sel, usuario_ids_nuevos)
            st.success("puesto actualizado.")
            st.rerun()
        else:
            st.error(mensaje)
