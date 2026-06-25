import pandas as pd
import streamlit as st

from controllers.formulas_readonly_controller import (
    listar_formulas_readonly_ctrl,
    obtener_formula_readonly_ctrl,
)


def _json_to_df(value):
    if not value:
        return pd.DataFrame()

    if isinstance(value, list):
        return pd.DataFrame(value)

    if isinstance(value, dict):
        return pd.DataFrame([value])

    return pd.DataFrame({"valor": [str(value)]})


def mostrar_tab_formulas_readonly():
    st.subheader("consulta de fórmulas")

    df = listar_formulas_readonly_ctrl()

    if df is None or df.empty:
        st.info("no hay fórmulas disponibles.")
        return

    df.columns = [str(c).lower() for c in df.columns]

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        buscar = st.text_input("buscar", key="formulas_buscar")

    with c2:
        segmento = st.selectbox(
            "segmento",
            ["todos"] + sorted(df["segmento"].dropna().astype(str).unique().tolist()),
            key="formulas_segmento",
        )

    with c3:
        estado = st.selectbox(
            "estado",
            ["todos"] + sorted(df["estado"].dropna().astype(str).unique().tolist()),
            key="formulas_estado",
        )

    with c4:
        activas = st.selectbox(
            "estatus",
            ["solo activas", "todas", "solo inactivas"],
            key="formulas_activas",
        )

    df_view = df.copy()

    if buscar:
        b = buscar.lower().strip()
        df_view = df_view[
            df_view["id"].astype(str).str.lower().str.contains(b, na=False)
            | df_view["nombre"].astype(str).str.lower().str.contains(b, na=False)
            | df_view["cve_sae"].astype(str).str.lower().str.contains(b, na=False)
        ]

    if segmento != "todos":
        df_view = df_view[df_view["segmento"].astype(str) == segmento]

    if estado != "todos":
        df_view = df_view[df_view["estado"].astype(str) == estado]

    if activas == "solo activas":
        df_view = df_view[df_view["activa"] == 1]
    elif activas == "solo inactivas":
        df_view = df_view[df_view["activa"] == 0]

    st.caption(f"fórmulas encontradas: {len(df_view):,}")

    cols = [
        "id",
        "nombre",
        "segmento",
        "version",
        "estado",
        "fecha",
        "es_alterna",
        "alterna_ref",
        "activa",
        "consumo",
        "cve_sae",
    ]
    cols = [c for c in cols if c in df_view.columns]

    st.dataframe(df_view[cols], use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("detalle de fórmula")

    opciones = {
        f"{r['id']} - {r['nombre']}": r["id"]
        for _, r in df_view.iterrows()
    }

    sel = st.selectbox("selecciona fórmula", [""] + list(opciones.keys()))

    if not sel:
        return

    formula_id = opciones[sel]
    formula = obtener_formula_readonly_ctrl(formula_id)

    if not formula:
        st.warning("no se encontró la fórmula.")
        return

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.metric("clave", formula.get("id", ""))

    with c2:
        st.metric("versión", formula.get("version", ""))

    with c3:
        st.metric("estado", formula.get("estado", ""))

    with c4:
        st.metric("segmento", formula.get("segmento", ""))

    st.write(f"**producto:** {formula.get('nombre', '')}")

    if formula.get("cve_sae"):
        st.write(f"**clave SAE:** {formula.get('cve_sae')}")

    if formula.get("consumo"):
        st.write(f"**consumo:** {formula.get('consumo')}")

    if formula.get("nota"):
        st.info(formula.get("nota"))

    if formula.get("es_alterna"):
        st.warning(
            f"fórmula alterna de {formula.get('alterna_ref') or '—'} "
            f"motivo: {formula.get('alterna_motivo') or '—'}"
        )

    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["carrier", "enzimas", "auxiliares", "empaque", "versiones"]
    )

    with tab1:
        df_carrier = _json_to_df(formula.get("carrier"))
        if df_carrier.empty:
            st.info("sin carrier registrado.")
        else:
            st.dataframe(df_carrier, use_container_width=True, hide_index=True)

    with tab2:
        df_enzimas = _json_to_df(formula.get("enzimas"))
        if df_enzimas.empty:
            st.info("sin enzimas registradas.")
        else:
            st.dataframe(df_enzimas, use_container_width=True, hide_index=True)

    with tab3:
        df_aux = _json_to_df(formula.get("auxiliares"))
        if df_aux.empty:
            st.info("sin auxiliares registrados.")
        else:
            st.dataframe(df_aux, use_container_width=True, hide_index=True)

    with tab4:
        df_emp = _json_to_df(formula.get("empaque"))
        if df_emp.empty:
            st.info("sin empaque registrado.")
        else:
            st.dataframe(df_emp, use_container_width=True, hide_index=True)

    with tab5:
        df_ver = _json_to_df(formula.get("versiones"))
        if df_ver.empty:
            st.info("sin historial de versiones.")
        else:
            st.dataframe(df_ver, use_container_width=True, hide_index=True)