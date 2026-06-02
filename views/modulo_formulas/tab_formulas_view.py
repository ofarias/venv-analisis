import streamlit as st
import pandas as pd

from controllers.formulas_controller import (
    listar_formulas_ctrl,
    listar_mp_ctrl,
    crear_formula_ctrl,
    nueva_version_formula_ctrl,
    cambiar_estado_formula_ctrl,
    get_formula_ctrl,
)


SEGMENTOS_COA = ["Pan", "Tortilla", "Alimentos"]


def _usuario_id():
    return st.session_state.get("usuario_id")


def _fmt_pct(v):
    try:
        return f"{float(v):,.4f}%"
    except Exception:
        return ""


def _total_detalle(detalle):
    return sum(float(x.get("porcentaje") or 0) for x in detalle)


def _build_detalle(mp_df, segmento):
    detalle = []

    st.markdown("### carrier")

    mp_options = {
        f"{r['clave']} - {r['nombre']}": int(r["id"])
        for _, r in mp_df.iterrows()
    }

    c1, c2 = st.columns(2)

    with c1:
        carrier_sel = st.selectbox("MP carrier", [""] + list(mp_options.keys()), key="formula_carrier")

    with c2:
        carrier_pct = st.number_input("% carrier", min_value=0.0, max_value=100.0, step=0.0001, key="formula_carrier_pct")

    if carrier_sel:
        detalle.append({
            "mp_id": mp_options[carrier_sel],
            "tipo": "Carrier",
            "orden_adicion": None,
            "porcentaje": carrier_pct,
            "actividad_objetivo": None,
            "actividad_coa": None,
        })

    st.markdown("### enzimas activas")

    num_enzimas = st.number_input("cantidad de enzimas", min_value=0, max_value=6, value=1, step=1)

    aplica_coa = segmento in SEGMENTOS_COA

    for i in range(int(num_enzimas)):
        with st.container(border=True):
            st.caption(f"enzima {i + 1}")

            c1, c2, c3 = st.columns(3)

            with c1:
                enzima_sel = st.selectbox(
                    "MP enzimática",
                    [""] + list(mp_options.keys()),
                    key=f"enzima_mp_{i}"
                )

                orden = st.number_input(
                    "orden adición",
                    min_value=1,
                    value=i + 1,
                    step=1,
                    key=f"enzima_orden_{i}"
                )

            with c2:
                if aplica_coa:
                    act_obj = st.number_input(
                        "actividad objetivo",
                        min_value=0.0,
                        step=0.01,
                        key=f"enzima_act_obj_{i}"
                    )

                    act_coa = st.number_input(
                        "actividad CoA lote actual",
                        min_value=0.0,
                        step=0.01,
                        key=f"enzima_act_coa_{i}"
                    )
                else:
                    act_obj = None
                    act_coa = None

            with c3:
                if aplica_coa:
                    pct = (act_obj / act_coa * 100) if act_obj and act_coa else 0
                    st.metric("% calculado", f"{pct:,.4f}%")
                else:
                    pct = st.number_input(
                        "% en peso",
                        min_value=0.0,
                        max_value=100.0,
                        step=0.0001,
                        key=f"enzima_pct_{i}"
                    )

            if enzima_sel:
                detalle.append({
                    "mp_id": mp_options[enzima_sel],
                    "tipo": "Enzima",
                    "orden_adicion": orden,
                    "porcentaje": pct,
                    "actividad_objetivo": act_obj,
                    "actividad_coa": act_coa,
                })

    st.markdown("### ingredientes auxiliares")

    num_aux = st.number_input("cantidad de auxiliares", min_value=0, max_value=20, value=0, step=1)

    for i in range(int(num_aux)):
        with st.container(border=True):
            c1, c2, c3 = st.columns(3)

            with c1:
                aux_sel = st.selectbox(
                    "MP auxiliar",
                    [""] + list(mp_options.keys()),
                    key=f"aux_mp_{i}"
                )

            with c2:
                aux_pct = st.number_input(
                    "% auxiliar",
                    min_value=0.0,
                    max_value=100.0,
                    step=0.0001,
                    key=f"aux_pct_{i}"
                )

            with c3:
                aux_orden = st.number_input(
                    "orden",
                    min_value=1,
                    value=i + 10,
                    step=1,
                    key=f"aux_orden_{i}"
                )

            if aux_sel:
                detalle.append({
                    "mp_id": mp_options[aux_sel],
                    "tipo": "Auxiliar",
                    "orden_adicion": aux_orden,
                    "porcentaje": aux_pct,
                    "actividad_objetivo": None,
                    "actividad_coa": None,
                })

    total = _total_detalle(detalle)

    st.progress(min(total / 100, 1))
    st.caption(f"suma total: {total:,.4f}%")

    if abs(total - 100) < 0.0001:
        st.success("la fórmula suma exactamente 100.0000%")
    elif total > 100:
        st.error(f"excede 100% por {total - 100:,.4f}%")
    else:
        st.warning(f"faltan {100 - total:,.4f}% para llegar a 100.0000%")

    return detalle, total


def mostrar_tab_formulas(es_admin=False):
    st.subheader("fórmulas")

    df = listar_formulas_ctrl(solo_activas=False)

    if es_admin:
        with st.expander("crear nueva fórmula", expanded=False):
            _form_crear_formula()

    if df.empty:
        st.info("no hay fórmulas registradas.")
        return

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        buscar = st.text_input("buscar", key="buscar_formula")

    with c2:
        segmento = st.selectbox(
            "segmento",
            ["todos"] + sorted(df["segmento"].dropna().unique().tolist())
        )

    with c3:
        estado = st.selectbox("estado", ["todos", "Borrador", "Aprobada"])

    with c4:
        ver_inactivas = st.checkbox("ver inactivas", value=False)

    df_view = df.copy()

    if buscar:
        b = buscar.lower().strip()
        df_view = df_view[
            df_view["nombre_producto"].astype(str).str.lower().str.contains(b, na=False)
            | df_view["clave_formula"].astype(str).str.lower().str.contains(b, na=False)
        ]

    if segmento != "todos":
        df_view = df_view[df_view["segmento"] == segmento]

    if estado != "todos":
        df_view = df_view[df_view["estado"] == estado]

    if not ver_inactivas:
        df_view = df_view[df_view["activo"] == 1]

    st.dataframe(df_view, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("detalle de fórmula")

    opciones = {
        f"{r['clave_formula']} - {r['nombre_producto']}": int(r["id"])
        for _, r in df_view.iterrows()
    }

    sel = st.selectbox("selecciona fórmula", [""] + list(opciones.keys()))

    if not sel:
        return

    formula_id = opciones[sel]
    formula = get_formula_ctrl(formula_id)

    if not formula:
        st.warning("no se encontró la fórmula.")
        return

    _mostrar_detalle_formula(formula, es_admin=es_admin)


def _mostrar_detalle_formula(formula, es_admin=False):
    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.metric("clave", formula["clave_formula"])

    with c2:
        st.metric("versión", f"v{formula['version_actual']}")

    with c3:
        st.metric("estado", formula["estado"])

    with c4:
        st.metric("segmento", formula["segmento"])

    st.write(f"producto: {formula['nombre_producto']}")

    if formula.get("observaciones"):
        st.info(formula["observaciones"])

    detalle = formula.get("detalle", [])

    if detalle:
        df_det = pd.DataFrame(detalle)
        cols = [
            "tipo",
            "orden_adicion",
            "mp_clave",
            "mp_nombre",
            "porcentaje",
            "actividad_objetivo",
            "actividad_coa",
        ]
        cols = [c for c in cols if c in df_det.columns]

        st.dataframe(df_det[cols], use_container_width=True, hide_index=True)

        total = df_det["porcentaje"].astype(float).sum()
        st.caption(f"total fórmula: {total:,.4f}%")

    versiones = formula.get("versiones", [])
    if versiones:
        with st.expander("historial de versiones"):
            st.dataframe(pd.DataFrame(versiones), use_container_width=True, hide_index=True)

    if es_admin:
        st.divider()

        c1, c2 = st.columns(2)

        with c1:
            if formula.get("activo"):
                if st.button("inactivar fórmula"):
                    cambiar_estado_formula_ctrl(formula["id"], False, _usuario_id())
                    st.success("fórmula inactivada.")
                    st.rerun()
            else:
                if st.button("activar fórmula", type="primary"):
                    cambiar_estado_formula_ctrl(formula["id"], True, _usuario_id())
                    st.success("fórmula activada.")
                    st.rerun()

        with c2:
            with st.expander("crear nueva versión"):
                _form_nueva_version(formula)


def _form_crear_formula():
    mp_df = listar_mp_ctrl(solo_activas=True)

    if mp_df.empty:
        st.warning("primero registra materias primas.")
        return

    with st.form("form_crear_formula"):
        c1, c2, c3 = st.columns(3)

        with c1:
            clave_formula = st.text_input("clave fórmula").upper().strip()
            nombre_producto = st.text_input("nombre producto").upper().strip()

        with c2:
            segmento = st.selectbox(
                "segmento",
                ["Pan", "Tortilla", "Alimentos", "Textil", "Cuero", "Cerveza", "Jugos", "Bacterias"]
            )
            estado = st.selectbox("estado", ["Borrador", "Aprobada"])

        with c3:
            es_alterna = st.checkbox("es fórmula alterna", value=False)
            motivo_alterna = st.text_input("motivo alterna") if es_alterna else None

        observaciones = st.text_area("observaciones")

        st.caption("guarda primero los datos generales; después se captura el detalle.")
        guardar = st.form_submit_button("continuar captura detalle", type="primary")

    if guardar:
        if not clave_formula or not nombre_producto:
            st.warning("captura clave y nombre.")
            return

        st.session_state["formula_tmp"] = {
            "clave_formula": clave_formula,
            "nombre_producto": nombre_producto,
            "segmento": segmento,
            "estado": estado,
            "es_alterna": 1 if es_alterna else 0,
            "formula_principal_id": None,
            "motivo_alterna": motivo_alterna,
            "observaciones": observaciones,
            "usuario_id": _usuario_id(),
        }

    if "formula_tmp" in st.session_state:
        data = st.session_state["formula_tmp"]

        st.info(f"capturando detalle para: {data['nombre_producto']}")

        detalle, total = _build_detalle(mp_df, data["segmento"])

        if st.button("guardar fórmula completa", type="primary"):
            if abs(total - 100) > 0.0001:
                st.error("la fórmula debe sumar exactamente 100%.")
                return

            crear_formula_ctrl(data, detalle)
            st.session_state.pop("formula_tmp", None)
            st.success("fórmula creada.")
            st.rerun()


def _form_nueva_version(formula):
    mp_df = listar_mp_ctrl(solo_activas=True)

    estado = st.selectbox(
        "estado nueva versión",
        ["Borrador", "Aprobada"],
        key=f"estado_nv_{formula['id']}"
    )

    observaciones = st.text_area(
        "observaciones nueva versión",
        value=formula.get("observaciones") or "",
        key=f"obs_nv_{formula['id']}"
    )

    detalle, total = _build_detalle(mp_df, formula["segmento"])

    if st.button("guardar nueva versión", type="primary", key=f"btn_nv_{formula['id']}"):
        if abs(total - 100) > 0.0001:
            st.error("la fórmula debe sumar exactamente 100%.")
            return

        nueva_version_formula_ctrl(
            formula["id"],
            {
                "estado": estado,
                "observaciones": observaciones,
                "usuario_id": _usuario_id(),
            },
            detalle,
        )

        st.success("nueva versión creada.")
        st.rerun()