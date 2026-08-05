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
}


def _fmt_metodo_default(v) -> str:
    """Etiqueta legible de metodo_default para la tabla de versiones. Se
    guarda en BD como "presupuesto" (ENUM, no admite "pv_carga:<id>") — la
    carga puntual elegida queda en la columna id_carga_pv, no aquí, así que
    se muestra genérico como "Presupuesto Ventas"."""
    s = str(v or "").strip()
    if s in _METODOS:
        return _METODOS[s]
    if s == "presupuesto" or s.startswith("pv_carga:"):
        return "Presupuesto Ventas"
    return s


def _etiqueta_carga_pv(r: dict) -> str:
    """Etiqueta de una carga de presupuesto de ventas para el selector de
    método — usa el comentario (ahí indican de qué industria es) y cae a
    nombre de archivo + año si no hay comentario."""
    comentario = str(r.get("comentarios") or "").strip()
    if comentario:
        return comentario
    nombre = str(r.get("nombre_archivo") or "").strip()
    anio_carga = r.get("anio")
    return f"{nombre} [{anio_carga}]" if nombre else f"carga #{r.get('id_carga')}"

_ESTATUS_BADGE = {
    "borrador": "🔵 borrador",
    "activo":   "🟢 activo",
    "cerrado":  "⚫ cerrado",
}


def _get_usuario_id() -> int:
    u = st.session_state.get("usuario") or {}
    return int(u.get("id") or u.get("id_usuario") or 0)


def _norm_roles_list(values) -> list[str]:
    if not values:
        return []
    if isinstance(values, str):
        values = [values]
    return [str(v).strip().lower() for v in values if str(v or "").strip()]


def _tiene_rol(roles: list[str], *objetivos: str) -> bool:
    roles_set = set(_norm_roles_list(roles))
    objetivos_set = set(_norm_roles_list(objetivos))
    return bool(roles_set.intersection(objetivos_set))


def _puede_ver_todos_forecast() -> bool:
    usuario = st.session_state.get("usuario") or {}
    if usuario.get("rol") == "Admin":
        return True
    return _tiene_rol(usuario.get("roles"), "admin", "superadmin", "forecastadmin")


def mostrar_tab_versiones() -> None:
    usuario_id = _get_usuario_id()
    ver_todas = _puede_ver_todos_forecast()

    # ── lista de versiones ────────────────────────────────────────────────────
    df = obtener_forecast_versiones_ctrl(usuario_id=usuario_id, ver_todas=ver_todas)

    if ver_todas and df is not None and not df.empty and "propietario" in df.columns:
        usuarios_disponibles = sorted(df["propietario"].dropna().astype(str).str.strip().unique())
        usuario_filtro = st.selectbox(
            "filtrar por usuario", ["(todos)"] + usuarios_disponibles, key="fv_filtro_usuario",
        )
        if usuario_filtro != "(todos)":
            df = df[df["propietario"].astype(str).str.strip() == usuario_filtro]

    if df is not None and not df.empty:
        cols_mostrar = [c for c in [
            "id_version", "anio", "nombre", "estatus",
            "metodo_default", "propietario", "nombre_archivo", "version_pv", "created_at",
        ] if c in df.columns and (c != "propietario" or ver_todas)]
        df_mostrar = df[cols_mostrar].copy()
        if "metodo_default" in df_mostrar.columns:
            df_mostrar["metodo_default"] = df_mostrar["metodo_default"].apply(_fmt_metodo_default)
        st.dataframe(
            df_mostrar.rename(columns={
                "id_version": "ID", "anio": "Año", "nombre": "Nombre",
                "estatus": "Estatus", "metodo_default": "Método",
                "propietario": "Usuario", "nombre_archivo": "Presupuesto base",
                "version_pv": "V. pres.", "created_at": "Creado",
            }),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("aún no tienes versiones de forecast — crea una abajo" if not ver_todas
                 else "no hay versiones de forecast registradas")

    st.divider()

    # ── crear nueva versión ───────────────────────────────────────────────────
    with st.expander("➕ crear nueva versión", expanded=df is None or df.empty):
        df_cargas = obtener_cargas_presupuesto_ventas_ctrl(limit=50, usuario_id=usuario_id)

        # método por defecto: fijo (manual) + una opción por cada carga de
        # presupuesto de ventas del usuario, identificada por su comentario
        # (ahí indican de qué industria es) — elegir una de estas últimas
        # define a la vez el método ("presupuesto") y la carga vinculada
        # (id_carga_pv), sin necesidad de un segundo selector
        metodos_opciones = dict(_METODOS)
        if df_cargas is not None and not df_cargas.empty:
            for r in df_cargas.to_dict("records"):
                id_carga_metodo = int(r["id_carga"])
                metodos_opciones[f"pv_carga:{id_carga_metodo}"] = f"Presupuesto Ventas — {_etiqueta_carga_pv(r)}"

        c1, c2, c3 = st.columns([1, 2, 2])
        with c1:
            anio = st.number_input("año", min_value=2024, max_value=2030, value=2026, step=1, key="fv_anio")
        with c2:
            nombre = st.text_input("nombre", placeholder="Forecast Q3 2026 v1", key="fv_nombre")
        with c3:
            metodo = st.selectbox("método por defecto", list(metodos_opciones.keys()),
                                  format_func=lambda k: metodos_opciones[k], key="fv_metodo")

        descripcion = st.text_area("descripción (opcional)", key="fv_desc", height=70)

        if st.button("crear versión", type="primary", key="fv_btn_crear"):
            if not nombre.strip():
                st.error("el nombre es obligatorio")
            elif usuario_id <= 0:
                st.error("usuario no identificado")
            else:
                # "metodo_default" es un ENUM en BD que no admite la clave
                # dinámica "pv_carga:<id>" — se guarda como "presupuesto" y
                # la carga puntual elegida queda en id_carga_pv
                id_carga_pv = None
                metodo_guardado = metodo
                if metodo.startswith("pv_carga:"):
                    try:
                        id_carga_pv = int(metodo.split(":", 1)[1])
                    except (ValueError, IndexError):
                        id_carga_pv = None
                    metodo_guardado = "presupuesto"
                try:
                    id_nueva = crear_forecast_version_ctrl(
                        anio=int(anio),
                        nombre=nombre.strip(),
                        descripcion=descripcion.strip() or None,
                        id_carga_pv=id_carga_pv,
                        metodo_default=metodo_guardado,
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

        if ver_todas:
            opc = {
                f"{r['id_version']} | {r['nombre']} ({_ESTATUS_BADGE.get(r['estatus'], r['estatus'])}) — "
                f"{r.get('propietario') or 'usuario ' + str(r['usuario_id'])}": int(r["id_version"])
                for r in df.to_dict("records")
            }
        else:
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
