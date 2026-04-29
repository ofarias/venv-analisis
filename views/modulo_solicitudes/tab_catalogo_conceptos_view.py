# views/modulo_solicitudes/tab_catalogo_conceptos_view.py
from __future__ import annotations

import streamlit as st
import pandas as pd

from controllers.solicitudes_controller import (
    listar_conceptos_catalogo_ctrl,
    upsert_concepto_catalogo_ctrl,
    desactivar_conceptos_catalogo_ctrl,
    get_usuarios_activos_ctrl,
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

    usuarios_activos = get_usuarios_activos_ctrl()
    nombres_validos = [u["nombre"] for u in usuarios_activos]
    nombre_a_id: dict[str, int] = {u["nombre"]: u["id"] for u in usuarios_activos}

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
                    "usuarios_informar": "",
                }
            ]
        )

    for c in ["id", "concepto", "cuenta", "fiscales", "prepago", "comprobante", "activo", "usuarios_informar"]:
        if c not in df.columns:
            df[c] = None

    df["fiscales"] = df["fiscales"].fillna(0).astype(int).astype(bool)
    df["prepago"] = df["prepago"].fillna(0).astype(int).astype(bool)
    df["activo"] = df["activo"].fillna(1).astype(int).astype(bool)
    df["comprobante"] = df["comprobante"].fillna(0).astype(int).astype(bool)
    df["usuarios_informar"] = df["usuarios_informar"].fillna("").apply(
        lambda x: [n.strip() for n in str(x).split(",") if n.strip()] if x else []
    )

    # Restaurar checkbox de selección desde session_state
    sel_concepto_id: int | None = st.session_state.get("cg_editar_concepto_id")
    df["_sel"] = df["id"].apply(
        lambda x: bool(pd.notna(x) and sel_concepto_id is not None and int(x) == sel_concepto_id)
    )

    st.caption("edita conceptos · activa ✏️ en una fila para gestionar usuarios a informar in-place")
    edited = st.data_editor(
        df[["id", "concepto", "cuenta", "fiscales", "prepago", "comprobante", "activo", "usuarios_informar", "_sel"]],
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
            "usuarios_informar": st.column_config.ListColumn(
                "usuarios a informar",
                help="Activa ✏️ en la fila para editar los usuarios asignados",
            ),
            "_sel": st.column_config.CheckboxColumn(
                "✏️ usuarios",
                help="Activa para editar los usuarios a informar de este concepto",
            ),
        },
    )

    # Detectar cambio de selección en el checkbox ✏️
    if "_sel" in edited.columns:
        prev_sel = st.session_state.get("cg_editar_concepto_id")
        checked_ids = [
            int(r["id"])
            for _, r in edited.iterrows()
            if r.get("_sel") is True and pd.notna(r.get("id"))
        ]

        if not checked_ids:
            if prev_sel is not None:
                st.session_state.pop("cg_editar_concepto_id", None)
                st.rerun()
        else:
            new_ids = [i for i in checked_ids if i != prev_sel]
            target_id = new_ids[0] if new_ids else checked_ids[0]
            if target_id != prev_sel:
                st.session_state["cg_editar_concepto_id"] = target_id
                st.rerun()

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

    # ── Multiselect in-place de usuarios a informar ──────────────────────────
    sel_id: int | None = st.session_state.get("cg_editar_concepto_id")
    conceptos_con_id = edited[edited["id"].notna()].copy()

    if sel_id is not None and not conceptos_con_id.empty:
        mask = conceptos_con_id["id"].apply(lambda x: pd.notna(x) and int(x) == sel_id)
        matching = conceptos_con_id[mask]

        if not matching.empty:
            concepto_nombre = str(matching.iloc[0].get("concepto") or "")
            current_cell = matching.iloc[0].get("usuarios_informar")
            current_names: list[str] = []
            if isinstance(current_cell, list):
                current_names = [n for n in current_cell if n in nombre_a_id]

            st.divider()
            st.caption(f"usuarios a informar · **{concepto_nombre}** (id {sel_id})")

            seleccionados: list[str] = st.multiselect(
                "seleccionar usuarios",
                options=nombres_validos,
                default=current_names,
                key=f"cg_multiselect_{sel_id}",
                help="Solo se muestran usuarios activos del sistema",
            )

            col_save, col_cancel = st.columns([3, 1])
            with col_save:
                if st.button("guardar usuarios a informar", key="cg_save_informar", use_container_width=True):
                    ids_sel = [nombre_a_id[n] for n in seleccionados if n in nombre_a_id]
                    res = sync_usuarios_concepto_ctrl(sel_id, ids_sel)
                    if res.get("ok"):
                        st.success("usuarios actualizados")
                        st.session_state.pop("cg_editor", None)
                        st.rerun()
                    else:
                        st.error(res.get("msg", "error al actualizar usuarios"))
            with col_cancel:
                if st.button("cancelar", key="cg_cancel_informar", use_container_width=True):
                    st.session_state.pop("cg_editar_concepto_id", None)
                    st.rerun()
    else:
        st.caption("activa ✏️ en una fila de la tabla para editar usuarios a informar.")
