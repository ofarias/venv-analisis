import math
import streamlit as st


def mostrar_tab_calculadora_coa():
    st.subheader("calculadora de ajuste enzimático")

    caso = st.radio(
        "caso",
        [
            "caso 1 - sustitución de lote",
            "caso 2 - combinación de lotes",
            "caso 3 - textil bajo desempeño",
        ],
        horizontal=True,
    )

    if caso.startswith("caso 1"):
        st.caption("% nuevo = (% anterior × actividad anterior) / actividad nuevo")

        c1, c2, c3, c4 = st.columns(4)

        with c1:
            pct_anterior = st.number_input("% enzima lote anterior", min_value=0.0, step=0.0001)

        with c2:
            act_anterior = st.number_input("actividad lote anterior", min_value=0.0, step=1.0)

        with c3:
            act_nuevo = st.number_input("actividad lote nuevo CoA", min_value=0.0, step=1.0)

        with c4:
            act_min = st.number_input("actividad mínima especificación", min_value=0.0, step=1.0)

        if pct_anterior > 0 and act_anterior > 0 and act_nuevo > 0:
            pct_nuevo = (pct_anterior * act_anterior) / act_nuevo
            actividad_resultante = (act_nuevo * pct_nuevo) / 100
            delta = pct_nuevo - pct_anterior

            st.success(f"% lote nuevo: {pct_nuevo:.4f}%")
            st.write(f"actividad resultante: {actividad_resultante:,.2f}")
            st.write(f"cumple especificación: {'sí' if actividad_resultante >= act_min else 'no'}")
            st.write(f"ajuste carrier delta: {delta:+.4f}%")

    elif caso.startswith("caso 2"):
        c1, c2 = st.columns(2)

        with c1:
            kg_totales = st.number_input("kg totales a producir", min_value=0.0, step=1.0)
            pct_formula = st.number_input("% enzima fórmula vigente", min_value=0.0, step=0.0001)

        with c2:
            act_lote_1 = st.number_input("actividad lote 1", min_value=0.0, step=1.0)
            kg_lote_1 = st.number_input("kg disponibles lote 1", min_value=0.0, step=0.001)
            act_lote_2 = st.number_input("actividad lote 2", min_value=0.0, step=1.0)

        if kg_totales > 0 and pct_formula > 0 and act_lote_1 > 0 and kg_lote_1 > 0 and act_lote_2 > 0:
            kg_requeridos = (kg_totales * pct_formula) / 100
            pct_lote_1 = (pct_formula * kg_lote_1) / kg_requeridos
            pct_restante = pct_formula - pct_lote_1
            pct_lote_2 = (pct_restante * act_lote_1) / act_lote_2
            kg_lote_2 = (kg_totales * pct_lote_2) / 100
            actividad_total = ((act_lote_1 * pct_lote_1) / 100) + ((act_lote_2 * pct_lote_2) / 100)

            st.success("resultado combinación")
            st.write(f"kg requeridos: {kg_requeridos:,.3f}")
            st.write(f"% lote 1: {pct_lote_1:.4f}%")
            st.write(f"% lote 2 ajustado: {pct_lote_2:.4f}%")
            st.write(f"kg lote 2: {kg_lote_2:,.3f}")
            st.write(f"actividad total combinada: {actividad_total:,.2f}")

    else:
        c1, c2 = st.columns(2)

        with c1:
            kg_totales = st.number_input("kg totales del lote", min_value=0.0, step=1.0)
            pct_catalasa = st.number_input("% catalasa en fórmula", min_value=0.0, step=0.0001)

        with c2:
            tiempo_max = st.number_input("tiempo máximo especificado", min_value=0.0, step=1.0)
            resultado = st.number_input("resultado análisis liberación", min_value=0.0, step=0.1)

        if kg_totales > 0 and pct_catalasa > 0 and tiempo_max > 0 and resultado > 0:
            kg_originales = (kg_totales * pct_catalasa) / 100
            kg_calculados = (kg_originales * tiempo_max) / resultado
            kg_adicionales = math.ceil(kg_calculados - kg_originales)
            nuevo_pct = ((kg_originales + kg_adicionales) / kg_totales) * 100

            st.success("resultado")
            st.write(f"kg originales: {kg_originales:,.3f}")
            st.write(f"kg calculados: {kg_calculados:,.3f}")
            st.write(f"kg adicionales: {kg_adicionales}")
            st.write(f"nuevo % catalasa: {nuevo_pct:.4f}%")