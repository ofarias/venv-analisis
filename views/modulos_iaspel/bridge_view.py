import streamlit as st
from datetime import date
from controllers.bridge_controller import *


def pantalla_bridge_java():
    st.title("Cargar pólizas ORIGEN=JAVA → test.coi_java_bridge")

    eje_default = date.today().year % 100
    c1, c2, c3 = st.columns(3)
    eje = c1.number_input("Ejercicio (dos dígitos)", 0, 99, value=eje_default, step=1)
    origen = c2.text_input("Origen", "JAVA")
    limit_opt = c3.selectbox("Límite", ["Todos", 1_000, 5_000, 10_000], index=1)
    limit = None if limit_opt == "Todos" else int(limit_opt)

    if st.button("Cargar a puente"):
        with st.spinner("Procesando..."):
            res = cargar_java_a_bridge(eje=eje, origen=origen, limit=limit, offset=0)
        st.success(f"Leídos: {res['leidos']:,} | Upsert: {res['upsert']:,}")

    
    st.markdown("---")
    st.subheader("Calcular porcentaje (cargo / total de cuentas 5/6)")

    escala = st.radio("Escala a guardar", ["0..100", "0..1"], index=0, horizontal=True)
    if st.button("Calcular porcentajes"):
        with st.spinner("Actualizando porcentajes..."):
            calcular_porcentajes_bridge(eje=eje, origen=origen, escala_100=(escala=="0..100"))
        st.success("Listo: porcentajes actualizados.")

    st.markdown("---")
    st.subheader("Actualizar nombre de departamento desde COI")

    if st.button("Actualizar nombre_depto"):
        with st.spinner("Sincronizando nombres de departamentos..."):
            total = sync_nombre_depto(eje=eje, origen=origen)
        st.success(f"Nombres de deptos actualizados: {total}")

    st.markdown("---")
    st.subheader("Actualizar CONCEPTO desde COI")

    if st.button("Sincronizar concepto (AUXILIAR.CONCEP_PO)"):
        with st.spinner("Actualizando conceptos..."):
            n = sync_concepto_bridge(eje=eje, origen=origen)
        st.success(f"Conceptos actualizados: {n:,}")
    
    st.markdown("---")
    st.subheader("Documento y Proveedor desde SAE (Firebird)")

    tol = st.number_input("Tolerancia en importe", min_value=0.0, value=0.01, step=0.01, format="%.2f")
    wnd = st.number_input("Ventana de ± días sobre FECHA_APLI", min_value=0, value=3, step=1)

    if st.button("Sincronizar doc/proveedor (paga_m01 + prov01)"):
        with st.spinner("Buscando coincidencias en SAE y actualizando..."):
            res = sync_doc_prov_desde_sae_fb(eje=eje, origen=origen, tolerancia=float(tol), ventana_dias=int(wnd))
        st.success(f"Procesadas: {res['polizas_procesadas']:,} | Actualizadas: {res['actualizadas']:,} | Sin match: {res['sin_match']:,}")

    st.markdown("---")
    st.subheader("Llenar CONCEPTO desde SAE (Firebird · PAGA_M01.NUM_CPTO)")

    usar_cve = st.checkbox("Cruzar también por CVE_PROV", value=True)

    if st.button("Completar concepto_sae por DOCUMENTO"):
        with st.spinner("Consultando PAGA_M01 y actualizando..."):
            res = sync_concepto_sae_desde_paga(eje=eje, origen=origen, usar_cve_prov=usar_cve)
        st.success(f"Pendientes: {res['pendientes']:,} · Actualizadas: {res['actualizadas']:,}")