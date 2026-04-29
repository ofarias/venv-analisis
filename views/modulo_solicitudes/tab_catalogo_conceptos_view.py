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

    st.caption("edita conceptos y guarda · los usuarios a informar se gestionan en la sección inferior")
    edited = st.data_editor(
        df[["id", "concepto", "cuenta", "fiscales", "prepago", "comprobante", "activo", "usuarios_informar"]],
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
                help="Gestiona los usuarios en la sección inferior",
            ),
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

    # ── Usuarios a informar por concepto ────────────────────────────────────
    st.divider()
    st.subheader("usuarios a informar por concepto")

    conceptos_con_id = edited[edited["id"].notna()].copy()
    if conceptos_con_id.empty:
        st.info("guarda primero los conceptos para poder asignar usuarios.")
        return

    opciones_concepto: dict[str, int] = {
        f"[{int(row['id'])}] {row['concepto']}": int(row["id"])
        for _, row in conceptos_con_id.iterrows()
    }

    concepto_label = st.selectbox(
        "concepto",
        options=list(opciones_concepto.keys()),
        key="cg_sel_concepto",
    )
    concepto_id_sel: int = opciones_concepto[concepto_label]

    mask = conceptos_con_id["id"].apply(
        lambda x: int(x) == concepto_id_sel if pd.notna(x) else False
    )
    current_cell = conceptos_con_id.loc[mask, "usuarios_informar"].values
    current_names: list[str] = []
    if len(current_cell) > 0 and isinstance(current_cell[0], list):
        current_names = [n for n in current_cell[0] if n in nombre_a_id]

    seleccionados: list[str] = st.multiselect(
        "seleccionar usuarios",
        options=nombres_validos,
        default=current_names,
        key=f"cg_multiselect_{concepto_id_sel}",
        help="solo se muestran usuarios activos del sistema",
    )

    if st.button("guardar usuarios a informar", key="cg_save_informar", use_container_width=True):
        ids_sel = [nombre_a_id[n] for n in seleccionados if n in nombre_a_id]
        res = sync_usuarios_concepto_ctrl(concepto_id_sel, ids_sel)
        if res.get("ok"):
            st.success("usuarios actualizados")
            st.session_state.pop("cg_editor", None)
            st.rerun()
        else:
            st.error(res.get("msg", "error al actualizar usuarios"))
