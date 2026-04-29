# views/modulo_solicitudes/tab_catalogo_conceptos_view.py
from __future__ import annotations

import streamlit as st
import pandas as pd

from controllers.solicitudes_controller import (
    listar_conceptos_catalogo_ctrl,
    upsert_concepto_catalogo_ctrl,
    desactivar_conceptos_catalogo_ctrl,
    get_usuarios_activos_ctrl,
    get_usuarios_por_concepto_ctrl,
    sync_usuarios_concepto_ctrl,
)


def mostrar_tab_catalogo_conceptos():
    st.subheader("catálogo de conceptos de gasto")

    usuario = st.session_state.get("usuario") or {}

    roles_permitidos = ["Admin", "Contabilidad"]

    if not any(rol in usuario.get("roles", []) for rol in roles_permitidos):
        st.info("Solo el personal de Admin o Contabilidad puede administrar el catálogo")
        return

    ver_inactivos = st.checkbox("ver inactivos", value=False, key="cg_ver_inactivos")

    rows = listar_conceptos_catalogo_ctrl(incluir_inactivos=ver_inactivos)
    df = pd.DataFrame(rows or [])

    if df.empty:
        df = pd.DataFrame(
            [
                {
                    "id": None,
                    "concepto": "",
                    "cuenta": "",
                    "fiscales": 0,
                    "prepago": 0,
                    "activo": 1,
                }
            ]
        )

    for c in ["id", "concepto", "cuenta", "fiscales", "prepago", "comprobante", "activo"]:
        if c not in df.columns:
            df[c] = None

    df["fiscales"] = df["fiscales"].fillna(0).astype(int).astype(bool)
    df["prepago"] = df["prepago"].fillna(0).astype(int).astype(bool)
    df["activo"] = df["activo"].fillna(1).astype(int).astype(bool)
    df["comprobante"] = df["comprobante"].fillna(0).astype(int).astype(bool)

    st.caption("edita y luego guarda cambios")
    edited = st.data_editor(
        df[["id", "concepto", "cuenta", "fiscales", "prepago", "comprobante", "activo"]],
        hide_index=True,
        use_container_width=True,
        num_rows="dynamic",
        key="cg_editor",
        column_config={
            "id": st.column_config.NumberColumn("id", disabled=True),
            "concepto": st.column_config.TextColumn("concepto", required=True),
            "cuenta": st.column_config.TextColumn("cuenta", required=True),
            "fiscales": st.column_config.CheckboxColumn("fiscales"),
            "prepago": st.column_config.CheckboxColumn("prepago"),
            "comprobante": st.column_config.CheckboxColumn("comprobante"),
            "activo": st.column_config.CheckboxColumn("activo"),
        },
    )

    c1, c2, c3 = st.columns([2, 2, 3])

    with c1:
        if st.button("guardar cambios", use_container_width=True):
            rows_out = []
            for r in edited.to_dict(orient="records"):
                concepto = (r.get("concepto") or "").strip()
                cuenta = (r.get("cuenta") or "").strip()
                if not concepto or not cuenta:
                    continue

                rid = r.get("id")
                try:
                    rid = None if pd.isna(rid) else int(rid)
                except Exception:
                    rid = None

                rows_out.append(
                    {
                        "id": rid,
                        "concepto": concepto,
                        "cuenta": cuenta,
                        "fiscales": 1 if bool(r.get("fiscales")) else 0,
                        "prepago": 1 if bool(r.get("prepago")) else 0,
                        "comprobante": 1 if bool(r.get("comprobante")) else 0,
                        "activo": 1 if bool(r.get("activo")) else 0,
                    }
                )

            res = upsert_concepto_catalogo_ctrl(rows_out, usuario_id=int(usuario.get("id") or 0))
            if res.get("ok"):
                st.success(res.get("msg", "guardado"))
                st.session_state.pop("cg_editor", None)
                st.rerun()
            else:
                st.error(res.get("msg", "no se pudo guardar"))

    with c2:
        ids_opts = [
            int(x)
            for x in edited["id"].dropna().tolist()
            if str(x).strip() not in ("", "none", "nan")
        ]
        ids_baja = st.multiselect("eliminar (desactivar) ids", options=ids_opts, default=[], key="cg_ids_baja")

        if st.button("eliminar seleccionados", use_container_width=True, disabled=(len(ids_baja) == 0)):
            res = desactivar_conceptos_catalogo_ctrl([int(x) for x in ids_baja], usuario_id=int(usuario.get("id") or 0))
            if res.get("ok"):
                st.success(res.get("msg", "eliminados"))
                st.session_state.pop("cg_editor", None)
                st.rerun()
            else:
                st.error(res.get("msg", "no se pudo eliminar"))

    with c3:
        st.caption("nota: eliminar = desactivar (activo=0).")

    # ── Sección: usuarios a notificar por concepto ──────────────────────────
    st.divider()
    st.subheader("usuarios a notificar por concepto")
    st.caption(
        "Selecciona un concepto y los usuarios que deben recibir notificación cuando se usa ese concepto en una solicitud."
    )

    # Solo conceptos activos con ID real para esta sección
    conceptos_activos = [
        r for r in (rows or [])
        if r.get("id") and r.get("activo", 1)
    ]

    if not conceptos_activos:
        st.info("No hay conceptos activos en el catálogo.")
        return

    concepto_opciones = {str(r["id"]): r["concepto"] for r in conceptos_activos}
    concepto_sel_label = st.selectbox(
        "concepto",
        options=list(concepto_opciones.keys()),
        format_func=lambda k: concepto_opciones[k],
        key="cg_concepto_sel",
    )

    if concepto_sel_label is None:
        return

    concepto_id_sel = int(concepto_sel_label)

    # Usuarios disponibles
    todos_usuarios = get_usuarios_activos_ctrl()
    usuario_map = {u["id"]: f"{u['nombre']} ({u['email']})" for u in todos_usuarios}

    # Usuarios ya asignados al concepto
    asignados_raw = get_usuarios_por_concepto_ctrl(concepto_id_sel)
    ids_asignados = [int(r["id_usuario"]) for r in asignados_raw]

    nuevos_ids = st.multiselect(
        "usuarios notificados",
        options=list(usuario_map.keys()),
        default=ids_asignados,
        format_func=lambda uid: usuario_map.get(uid, str(uid)),
        key=f"cg_usuarios_concepto_{concepto_id_sel}",
    )

    if st.button("guardar usuarios del concepto", key="cg_guardar_usuarios"):
        res = sync_usuarios_concepto_ctrl(concepto_id_sel, nuevos_ids)
        if res.get("ok"):
            st.success(res.get("msg", "guardado"))
            st.rerun()
        else:
            st.error(res.get("msg", "no se pudo guardar"))
