# views/modulo_solicitudes/tab_usuarios_forma_pago_view.py
from __future__ import annotations

import streamlit as st
import pandas as pd
from datetime import date
from typing import Any, Dict, List, Optional

from controllers.solicitudes_controller import (
    get_usuarios_activos_ctrl,
    get_formas_pago_usuario_ctrl,
    upsert_formas_pago_usuario_ctrl,
    desactivar_formas_pago_usuario_ctrl,
)

TIPOS_FORMA_PAGO = [
    "Tarjeta Crédito",
    "Tarjeta Debito",
    "Efectivo",
    "Tarjeta Despensa",
    "Tarjeta Personal",
    "Tag Pase Urbano",
    "Tarjeta Combustible",
    "Vales",
]

MONEDAS = ["MXN", "USD"]


def _to_int(x) -> Optional[int]:
    try:
        if x is None or str(x).strip() == "":
            return None
        return int(float(x))
    except Exception:
        return None


def _norm_str(x) -> str:
    if x is None:
        return ""
    return str(x).strip()


def _norm_date(x) -> Optional[date]:
    if x is None or str(x).strip() == "":
        return None
    try:
        dt = pd.to_datetime(x, errors="coerce")
        if pd.isna(dt):
            return None
        return dt.date()
    except Exception:
        return None


def _defaults_row(id_usuario: int) -> Dict[str, Any]:
    return {
        "id": None,
        "id_usuario": int(id_usuario),
        "tipo": "Tarjeta Crédito",
        "entidad_bancaria": "",
        "moneda": "MXN",
        "cuenta_contable": "",
        "ultimos4": "",
        "numero_tarjeta_enmascarado": "",
        "vigencia_inicio": None,
        "vigencia_fin": None,
        "activo": 1,
    }


def _normalize_df(df: pd.DataFrame, id_usuario: int) -> pd.DataFrame:
    cols = [
        "id",
        "id_usuario",
        "tipo",
        "entidad_bancaria",
        "moneda",
        "cuenta_contable",
        "ultimos4",
        "numero_tarjeta_enmascarado",
        "vigencia_inicio",
        "vigencia_fin",
        "activo",
    ]

    d = df.copy()

    for c in cols:
        if c not in d.columns:
            d[c] = None

    d["id_usuario"] = int(id_usuario)

    d["tipo"] = d["tipo"].fillna("").astype(str).str.strip()
    d.loc[~d["tipo"].isin(TIPOS_FORMA_PAGO), "tipo"] = "Tarjeta Crédito"

    d["entidad_bancaria"] = d["entidad_bancaria"].fillna("").astype(str).str.strip()

    d["moneda"] = d["moneda"].fillna("MXN").astype(str).str.strip().str.upper()
    d.loc[~d["moneda"].isin(MONEDAS), "moneda"] = "MXN"

    d["cuenta_contable"] = d["cuenta_contable"].fillna("").astype(str).str.strip()
    d["ultimos4"] = d["ultimos4"].fillna("").astype(str).str.strip()
    d["numero_tarjeta_enmascarado"] = d["numero_tarjeta_enmascarado"].fillna("").astype(str).str.strip()

    d["vigencia_inicio"] = d["vigencia_inicio"].apply(_norm_date)
    d["vigencia_fin"] = d["vigencia_fin"].apply(_norm_date)

    # checkbox del editor llega bool; guardamos 0/1
    d["activo"] = d["activo"].apply(lambda x: 1 if bool(x) else 0)

    d["id"] = d["id"].apply(_to_int)

    return d[cols].copy()


def mostrar_tab_usuarios_forma_pago():
    st.subheader("catálogo: formas de pago por usuario")

    user = st.session_state.get("usuario") or {}
    if not user:
        st.warning("no hay sesión de usuario en st.session_state['usuario']")
        return

    #if (user.get("rol") or "") != "Admin":
    #    st.warning("solo administrador puede administrar este catálogo")
    #    return

    usuarios = get_usuarios_activos_ctrl()
    if not usuarios:
        st.info("no hay usuarios activos")
        return

    usuarios_map = {int(u["id"]): u for u in usuarios}
    ids_usuarios = sorted(list(usuarios_map.keys()))

    c1, c2 = st.columns([2, 3])
    with c1:
        sel_usuario = st.selectbox(
            "usuario",
            options=ids_usuarios,
            index=0,
            format_func=lambda _id: f"{usuarios_map[int(_id)]['nombre']} ({usuarios_map[int(_id)]['username']})",
            key="ufp_sel_usuario",
        )

    with c2:
        st.text_input(
            "correo",
            value=str(usuarios_map[int(sel_usuario)].get("email") or ""),
            disabled=True,
            key="ufp_show_email",
        )

    st.divider()

    # carga inicial solo cuando cambia el usuario (o no existe en sesión)
    if "ufp_df" not in st.session_state or st.session_state.get("ufp_loaded_user") != int(sel_usuario):
        rows = get_formas_pago_usuario_ctrl(int(sel_usuario))
        df = pd.DataFrame(rows or [])
        if df.empty:
            df = pd.DataFrame([_defaults_row(int(sel_usuario))])
        st.session_state["ufp_df"] = df  # ojo: aquí no normalizamos para no pelear con el editor
        st.session_state["ufp_loaded_user"] = int(sel_usuario)

    st.session_state.setdefault("ufp_ids_desactivar", [])

    st.caption("formas de pago (agregar / editar / desactivar)")

    cbtn1, cbtn2 = st.columns([1.2, 1.2])

    if cbtn1.button("agregar renglón", use_container_width=True, key="ufp_add_row_btn"):
        df_tmp = st.session_state["ufp_df"].copy()
        df_tmp = pd.concat([df_tmp, pd.DataFrame([_defaults_row(int(sel_usuario))])], ignore_index=True)
        st.session_state["ufp_df"] = df_tmp
        st.rerun()

    if cbtn2.button("recargar", use_container_width=True, key="ufp_reload_btn"):
        st.session_state.pop("ufp_df", None)
        st.session_state["ufp_loaded_user"] = None
        st.session_state["ufp_ids_desactivar"] = []
        st.rerun()

    st.divider()

    # form: evita que cada tecleo dispare un rerun que te borre campos
    with st.form(key=f"ufp_form_user_{int(sel_usuario)}", clear_on_submit=False):
        edited = st.data_editor(
            st.session_state["ufp_df"],
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic",
            key=f"ufp_editor_user_{int(sel_usuario)}",
            column_config={
                "id": st.column_config.TextColumn("id", disabled=True),
                "id_usuario": st.column_config.NumberColumn("id_usuario", disabled=True),
                "tipo": st.column_config.SelectboxColumn("tipo", options=TIPOS_FORMA_PAGO, required=True),
                "entidad_bancaria": st.column_config.TextColumn("entidad_bancaria"),
                "moneda": st.column_config.SelectboxColumn("moneda", options=MONEDAS, required=True),
                "cuenta_contable": st.column_config.TextColumn("cuenta_contable"),
                "ultimos4": st.column_config.TextColumn("ultimos4"),
                "numero_tarjeta_enmascarado": st.column_config.TextColumn("numero_tarjeta_enmascarado"),
                "vigencia_inicio": st.column_config.DateColumn("vigencia_inicio"),
                "vigencia_fin": st.column_config.DateColumn("vigencia_fin"),
                "activo": st.column_config.CheckboxColumn("activo"),
            },
        )

        # ids existentes para desactivar (solo los que ya existen en bd)
        try:
            df_ids = pd.DataFrame(edited)
        except Exception:
            df_ids = st.session_state["ufp_df"].copy()

        ids_existentes = sorted(
            [int(x) for x in df_ids.get("id", pd.Series([])).dropna().tolist() if str(x).strip() not in ("", "none", "nan")]
        )

        ids_a_desactivar = st.multiselect(
            "desactivar ids (no borra físico)",
            options=ids_existentes,
            default=st.session_state.get("ufp_ids_desactivar", []),
            key=f"ufp_ids_desactivar_user_{int(sel_usuario)}",
        )

        csave1, csave2 = st.columns([2, 1])
        submitted = csave1.form_submit_button("guardar cambios", use_container_width=True)
        clear_sel = csave2.form_submit_button("limpiar selección", use_container_width=True)

    # aplicar acciones del form
    if clear_sel:
        st.session_state["ufp_ids_desactivar"] = []
        st.rerun()

    if submitted:
        try:
            # guardar lo editado a sesión (tal cual) y normalizar solo para persistir
            st.session_state["ufp_df"] = pd.DataFrame(edited)

            df_norm = _normalize_df(st.session_state["ufp_df"], int(sel_usuario))
            rows_out = df_norm.to_dict(orient="records")
    
            fixed: List[Dict[str, Any]] = []
            for r in rows_out:
                if not _norm_str(r.get("tipo")):
                    continue
                r["id_usuario"] = int(sel_usuario)
                r["activo"] = 1 if int(r.get("activo") or 0) == 1 else 0
                fixed.append(r)

            upsert_formas_pago_usuario_ctrl(int(sel_usuario), fixed, int(user["id"]))

            # desactivar seleccionados (bd)
            ids_to_off = ids_a_desactivar or []
            if ids_to_off:
                desactivar_formas_pago_usuario_ctrl(
                    int(sel_usuario),
                    [int(x) for x in ids_to_off],
                    int(user["id"]),
                )

            st.success("catálogo actualizado")

            # recarga desde bd para reflejar ids nuevos
            st.session_state.pop("ufp_df", None)
            st.session_state["ufp_loaded_user"] = None
            st.session_state["ufp_ids_desactivar"] = []
            st.rerun()

        except Exception as e:
            st.error(f"error al guardar: {e}")