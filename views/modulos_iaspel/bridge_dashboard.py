import streamlit as st
import pandas as pd
from models.listados_model import listar_pendientes, listar_con_regla
from controllers.prorrateo_controller import (
    sugerir_por_proveedor, comparacion_detallada,
    auto_aplicar_lote_controller, auto_aplicar_controller,
)
from controllers.prorrateo_controller import fijar_prorrateo

def pantalla_bridge_dashboard():
    st.title("Pólizas · Bridge COI ⇄ Reglas")

    c1,c2 = st.columns(2)
    eje    = c1.number_input("Eje (2 dígitos)", 0, 99, value=25, step=1)
    origen = c2.text_input("Origen", "JAVA")

    tabs = st.tabs(["Pendientes", "Con reglas"])

    # ----- Pendientes -----
    with tabs[0]:
        c3,c4,c5 = st.columns(3)
        lim = c3.number_input("Límite", 1, 5000, 200, 50)
        off = c4.number_input("Offset", 0, 100000, 0, 100)
        tol = c5.slider("Tolerancia vector (p.p.)", 0.0, 5.0, 0.5, 0.1)

        rows = listar_pendientes(eje, origen, limit=int(lim), offset=int(off))
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True)

        st.markdown("### Auto-aplicar (lote)")
        colA, colB, colC, colD = st.columns(4)
        umbral = colA.number_input("Umbral score", 0.0, 20.0, 1.0, 0.1)
        gap    = colB.number_input("Brecha mínima", 0.0, 20.0, 1.0, 0.1)
        tolsum = colC.number_input("Tolerancia suma %", 0.0, 10.0, 2.0, 0.1)
        dry    = colD.checkbox("Dry-run", True)

        if st.button("Ejecutar auto-aplicación (pendientes)"):
            res = auto_aplicar_lote_controller(
                eje, origen=origen, usar_concepto=True,
                tol_pct=float(tol), umbral=float(umbral), gap=float(gap), tol_suma=float(tolsum),
                limit=int(lim), offset=int(off), dry_run=bool(dry)
            )
            st.success(f"Procesadas: {res['procesadas']} · Aplicadas: {res['aplicadas']} · Saltadas: {res['saltadas']}")
            st.dataframe(pd.DataFrame(res["detalles"]), use_container_width=True)

    # ----- Con reglas -----
    with tabs[1]:
        c6,c7 = st.columns(2)
        lim2 = c6.number_input("Límite", 1, 5000, 200, 50, key="lim2")
        off2 = c7.number_input("Offset", 0, 100000, 0, 100, key="off2")
        rows2 = listar_con_regla(eje, origen, limit=int(lim2), offset=int(off2))
        st.dataframe(pd.DataFrame(rows2), use_container_width=True)

        st.markdown("### Revisar / Reaplicar una póliza")
        cc1,cc2,cc3,cc4 = st.columns(4)
        tipo    = cc1.text_input("Tipo", "Dr", key="tipo_rev")
        per     = cc2.number_input("Periodo", 1, 13, 1, 1, key="per_rev")
        num     = cc3.number_input("Número", 1, 1_000_000, 1, 1, key="num_rev")
        tol_v   = cc4.slider("Tol. vector (p.p.)", 0.0, 5.0, 0.5, 0.1, key="tol_rev")

        if st.button("Sugerir candidatos (por proveedor/concepto)", key="sug_rev"):
            cands = sugerir_por_proveedor(eje, tipo, per, num, usar_concepto=True, tol_pct=float(tol_v), top_n=5)
            st.dataframe(pd.DataFrame(cands), use_container_width=True)
            if cands:
                sel = st.selectbox("Elegir candidato a aplicar", [f"{c['idnumpon']} - {c['nombre']} (score={c['score']})" for c in cands], key="sel_rev")
                if st.button("Aplicar seleccionado", key="apl_rev"):
                    pick = next(c for c in cands if f"{c['idnumpon']} - {c['nombre']} (score={c['score']})" == sel)
                    fijar_prorrateo(eje, tipo, per, num, pick["idnumpon"], pick["nombre"])
                    st.success(f"Aplicado: {pick['idnumpon']} · {pick['nombre']}")