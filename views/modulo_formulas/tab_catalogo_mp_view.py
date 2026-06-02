import streamlit as st
import pandas as pd

from controllers.formulas_controller import (
    listar_mp_ctrl,
    crear_mp_ctrl,
    actualizar_mp_ctrl,
    cambiar_estado_mp_ctrl,
    listar_mp_sae_ctrl,
    sincronizar_mp_sae_a_mysql_ctrl,
)


def _usuario_id():
    return st.session_state.get("usuario_id")


def mostrar_tab_catalogo_mp(es_admin=False):
    st.subheader("catálogo de materias primas")
    if es_admin:
        if st.button("sincronizar MP desde SAE almacén 17", type="primary"):
            sincronizar_mp_sae_a_mysql_ctrl(_usuario_id())
            st.success("materias primas sincronizadas desde SAE.")
            st.rerun()
            
    st.subheader("materias primas desde SAE - almacén 17")
    
    df_sae = listar_mp_sae_ctrl()
    
    if df_sae.empty:
        st.info("no se encontraron materias primas en SAE para el almacén 17.")
    else:
        st.dataframe(df_sae, use_container_width=True, hide_index=True)

    if es_admin:
        with st.expander("agregar nueva materia prima", expanded=False):
            with st.form("form_nueva_mp", clear_on_submit=True):
                c1, c2, c3 = st.columns(3)

                with c1:
                    clave = st.text_input("clave", placeholder="MP-001").upper().strip()
                    nombre = st.text_input("nombre MP").upper().strip()

                with c2:
                    proveedor = st.text_input("proveedor").upper().strip()
                    unidad_enzimatica = st.text_input("unidad enzimática", placeholder="MANU/g")

                with c3:
                    actividad = st.number_input("actividad especificación mínima", min_value=0.0, step=0.01)
                    unidad_compra = st.selectbox("unidad compra", ["kg", "L", "g", "mL", "pieza"])
                    aplica_coa = st.checkbox("aplica CoA", value=False)

                guardar = st.form_submit_button("guardar MP", type="primary")

                if guardar:
                    if not clave or not nombre:
                        st.warning("captura clave y nombre.")
                    else:
                        crear_mp_ctrl({
                            "clave": clave,
                            "nombre": nombre,
                            "proveedor": proveedor,
                            "unidad_enzimatica": unidad_enzimatica,
                            "actividad_especificacion": actividad if actividad > 0 else None,
                            "unidad_compra": unidad_compra,
                            "aplica_coa": 1 if aplica_coa else 0,
                            "usuario_id": _usuario_id(),
                        })
                        st.success("materia prima creada.")
                        st.rerun()

    ver_inactivas = st.checkbox("mostrar inactivas", value=False)
    df = listar_mp_ctrl(solo_activas=not ver_inactivas)

    if df.empty:
        st.info("no hay materias primas registradas.")
        return

    st.dataframe(df, use_container_width=True, hide_index=True)

    if es_admin:
        st.divider()
        st.subheader("editar / activar / inactivar MP")

        opciones = {
            f"{r['clave']} - {r['nombre']}": int(r["id"])
            for _, r in df.iterrows()
        }

        sel = st.selectbox("selecciona MP", [""] + list(opciones.keys()))

        if sel:
            mp_id = opciones[sel]
            row = df[df["id"] == mp_id].iloc[0]

            with st.form(f"form_editar_mp_{mp_id}"):
                c1, c2, c3 = st.columns(3)

                with c1:
                    nombre = st.text_input("nombre", value=str(row["nombre"])).upper().strip()
                    proveedor = st.text_input("proveedor", value=str(row.get("proveedor") or "")).upper().strip()

                with c2:
                    unidad_enzimatica = st.text_input(
                        "unidad enzimática",
                        value=str(row.get("unidad_enzimatica") or "")
                    )
                    actividad = st.number_input(
                        "actividad especificación",
                        min_value=0.0,
                        value=float(row.get("actividad_especificacion") or 0),
                        step=0.01
                    )

                with c3:
                    unidad_compra = st.selectbox(
                        "unidad compra",
                        ["kg", "L", "g", "mL", "pieza"],
                        index=["kg", "L", "g", "mL", "pieza"].index(row.get("unidad_compra") or "kg")
                        if row.get("unidad_compra") in ["kg", "L", "g", "mL", "pieza"] else 0
                    )
                    aplica_coa = st.checkbox("aplica CoA", value=bool(row.get("aplica_coa")))

                guardar = st.form_submit_button("guardar cambios", type="primary")

                if guardar:
                    actualizar_mp_ctrl(mp_id, {
                        "nombre": nombre,
                        "proveedor": proveedor,
                        "unidad_enzimatica": unidad_enzimatica,
                        "actividad_especificacion": actividad if actividad > 0 else None,
                        "unidad_compra": unidad_compra,
                        "aplica_coa": 1 if aplica_coa else 0,
                        "usuario_id": _usuario_id(),
                    })
                    st.success("MP actualizada.")
                    st.rerun()

            activo_actual = bool(row.get("activo"))

            if activo_actual:
                if st.button("inactivar MP", type="secondary"):
                    cambiar_estado_mp_ctrl(mp_id, False, _usuario_id())
                    st.success("MP inactivada.")
                    st.rerun()
            else:
                if st.button("activar MP", type="primary"):
                    cambiar_estado_mp_ctrl(mp_id, True, _usuario_id())
                    st.success("MP activada.")
                    st.rerun()
                    