from __future__ import annotations

import streamlit as st
import pandas as pd

from controllers.forecast_controller import (
    cambiar_estatus_version_ctrl,
    crear_forecast_version_ctrl,
    eliminar_forecast_version_ctrl,
    obtener_forecast_versiones_ctrl,
)
from controllers.presupuesto_ventas_controller import obtener_cargas_presupuesto_ventas_ctrl


_METODOS = {
    "manual": "Manual (el usuario ingresa los valores)",
    "prom_3m": "Promedio 3 meses",
    "prom_12m": "Promedio 12 meses",
    "pct_presupuesto": "95% del presupuesto",
    "presupuesto": "Igual al presupuesto",
}

_ESTATUS_BADGE = {
    "borrador": "🔵 borrador",
    "activo":   "🟢 activo",
    "cerrado":  "⚫ cerrado",
}


def _get_usuario_id() -> int:
    u = st.session_state.get("usuario") or {}
    return int(u.get("id") or u.get("id_usuario") or 0)


def mostrar_tab_versiones() -> None:
    usuario_id = _get_usuario_id()

    # ── lista de versiones ────────────────────────────────────────────────────
    df = obtener_forecast_versiones_ctrl(usuario_id=usuario_id)

    if df is not None and not df.empty:
        cols_mostrar = [c for c in [
            "id_version", "anio", "nombre", "estatus",
            "metodo_default", "nombre_archivo", "version_pv", "created_at",
        ] if c in df.columns]
        st.dataframe(
            df[cols_mostrar].rename(columns={
                "id_version": "ID", "anio": "Año", "nombre": "Nombre",
                "estatus": "Estatus", "metodo_default": "Método",
                "nombre_archivo": "Presupuesto base", "version_pv": "V. pres.",
                "created_at": "Creado",
            }),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("aún no tienes versiones de forecast — crea una abajo")

    st.divider()

    # ── crear nueva versión ───────────────────────────────────────────────────
    with st.expander("➕ crear nueva versión", expanded=df is None or df.empty):
        c1, c2, c3 = st.columns([1, 2, 2])
        with c1:
            anio = st.number_input("año", min_value=2024, max_value=2030, value=2026, step=1, key="fv_anio")
        with c2:
            nombre = st.text_input("nombre", placeholder="Forecast Q3 2026 v1", key="fv_nombre")
        with c3:
            metodo = st.selectbox("método por defecto", list(_METODOS.keys()),
                                  format_func=lambda k: _METODOS[k], key="fv_metodo")

        descripcion = st.text_area("descripción (opcional)", key="fv_desc", height=70)

        # selector de carga de presupuesto vinculada
        df_cargas = obtener_cargas_presupuesto_ventas_ctrl(limit=50, usuario_id=usuario_id)
        id_carga_pv = None
        if df_cargas is not None and not df_cargas.empty:
            opc_cargas = {"(ninguna)": None}
            for r in df_cargas.to_dict("records"):
                lbl = f"{r['id_carga']} | {r['nombre_archivo']} | {r['anio']} | {r.get('version','')}"
                opc_cargas[lbl] = int(r["id_carga"])
            sel = st.selectbox("presupuesto de ventas base", list(opc_cargas.keys()), key="fv_carga_pv")
            id_carga_pv = opc_cargas[sel]
        else:
            st.caption("no hay cargas de presupuesto disponibles")

        if st.button("crear versión", type="primary", key="fv_btn_crear"):
            if not nombre.strip():
                st.error("el nombre es obligatorio")
            elif usuario_id <= 0:
                st.error("usuario no identificado")
            else:
                try:
                    id_nueva = crear_forecast_version_ctrl(
                        anio=int(anio),
                        nombre=nombre.strip(),
                        descripcion=descripcion.strip() or None,
                        id_carga_pv=id_carga_pv,
                        metodo_default=metodo,
                        usuario_id=usuario_id,
                    )
                    st.session_state["fc_id_version"] = id_nueva
                    st.success(f"versión creada — id={id_nueva}")
                    st.rerun()
                except Exception as e:
                    st.error(f"error: {e}")

    # ── gestionar versión existente ───────────────────────────────────────────
    if df is not None and not df.empty:
        st.divider()
        st.markdown("#### gestionar versión")

        opc = {
            f"{r['id_version']} | {r['nombre']} ({_ESTATUS_BADGE.get(r['estatus'], r['estatus'])})": int(r["id_version"])
            for r in df.to_dict("records")
        }
        sel_label = st.selectbox("selecciona versión", list(opc.keys()), key="fv_sel_gestion")
        id_sel = opc[sel_label]

        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("✅ marcar como activo", use_container_width=True, key="fv_btn_activo"):
                cambiar_estatus_version_ctrl(id_sel, "activo")
                st.success("estatus → activo")
                st.rerun()
        with c2:
            if st.button("⚫ cerrar versión", use_container_width=True, key="fv_btn_cerrar"):
                cambiar_estatus_version_ctrl(id_sel, "cerrado")
                st.success("estatus → cerrado")
                st.rerun()
        with c3:
            confirmar = st.checkbox(f"confirmo eliminar {id_sel}", key="fv_chk_del")
            if st.button("🗑️ eliminar", type="primary", disabled=not confirmar,
                         use_container_width=True, key="fv_btn_del"):
                try:
                    eliminar_forecast_version_ctrl(id_sel)
                    if st.session_state.get("fc_id_version") == id_sel:
                        del st.session_state["fc_id_version"]
                    st.success(f"versión {id_sel} eliminada")
                    st.rerun()
                except Exception as e:
                    st.error(f"error: {e}")
