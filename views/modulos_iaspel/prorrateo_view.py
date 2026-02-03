# prorrateo_view.py
import streamlit as st
import pandas as pd
from controllers.prorrateo_controller import *
from controllers.prorrateo_controller import _signals_de_poliza

def pantalla_prorrateos():
    st.title("Sugerencia de prorrateo")

    # --- estado inicial ---
    ss = st.session_state
    ss.setdefault("cands_pp", [])          # candidatos persistidos
    ss.setdefault("sel_pp", None)          # texto seleccionado
    ss.setdefault("comp_ready", False)     # bandera para comparar

    c1,c2,c3,c4 = st.columns(4)
    eje     = c1.number_input("Eje (2 dígitos)", 0, 99, value=25, step=1)
    tipo    = c2.text_input("Tipo", "Dr")
    periodo = c3.number_input("Periodo", 1, 13, value=1, step=1)
    numero  = c4.number_input("Número", 1, 1_000_000, value=2, step=1)
    tol     = st.slider("Tolerancia (p.p.)", 0.0, 5.0, 0.5, 0.1)

    # --- botón: calcular candidatos (y guardarlos en sesión) ---
    if st.button("Sugerir (filtrado por proveedor/concepto)"):
        cands = sugerir_por_proveedor(eje, tipo, periodo, numero, usar_concepto=False, tol_pct=float(tol), top_n=5)
        ss.cands_pp = cands
        ss.sel_pp = None
        ss.comp_ready = False

    #if st.button("Sugerir candidatos (por proveedor/concepto)", key="sug_rev"):
    sig = _signals_de_poliza(eje, tipo, periodo, numero)   # 👈 trae proveedor y concepto
    st.info(f"Proveedor: {sig.get('cve_prov') or '-'} · Concepto: {sig.get('concepto_sae') or '-'} - Concepto Poliza: {sig.get('concepto') or '-'}- Regla: {sig.get('regla') or '-'}")

    #cands = sugerir_por_proveedor(eje, tipo, per, num, usar_concepto=True, tol_pct=float(tol_v), top_n=5)
    #st.dataframe(pd.DataFrame(cands), use_container_width=True)

    # muestra candidatos si existen en sesión
    if ss.cands_pp:
        st.dataframe(pd.DataFrame(ss.cands_pp), use_container_width=True)

        opciones = [f"{c['idnumpon']} - {c['nombre']} (score={c['score']})" for c in ss.cands_pp]
        ss.sel_pp = st.selectbox("Candidato", opciones, index=0 if ss.sel_pp is None and opciones else (opciones.index(ss.sel_pp) if ss.sel_pp in opciones else 0)) if opciones else None

        colA, colB = st.columns(2)
        if colA.button("Ver comparación detallada"):
            ss.comp_ready = True  # marcamos intención; el rerun leerá esto

        if colB.button("Aplicar candidato seleccionado"):
            pick = next((c for c in ss.cands_pp if f"{c['idnumpon']} - {c['nombre']} (score={c['score']})" == ss.sel_pp), None)
            if pick:
                fijar_prorrateo(eje, tipo, periodo, numero, pick["idnumpon"], pick["nombre"])
                st.success(f"Aplicado: {pick['idnumpon']} · {pick['nombre']}")
            else:
                st.warning("Selecciona un candidato válido.")

    # tras el rerun, si hay bandera, hacemos la comparación de forma segura
    if ss.comp_ready and ss.cands_pp and ss.sel_pp:
        try:
            pick = next((c for c in ss.cands_pp if f"{c['idnumpon']} - {c['nombre']} (score={c['score']})" == ss.sel_pp), None)
            if pick is None:
                st.warning("La selección ya no está disponible. Vuelve a sugerir candidatos.")
            else:
                comp = comparacion_detallada(eje, tipo, periodo, numero, pick["idnumpon"])
                st.subheader(f"Comparación con regla: {pick['idnumpon']} · {comp['nombre_regla'] or pick['nombre']}")
                dfc = pd.DataFrame(comp["rows"])
                st.dataframe(dfc, use_container_width=True)

                c1, c2, c3 = st.columns(3)
                c1.metric("Suma % póliza", f"{comp['totales']['poliza']:.2f}")
                c2.metric("Suma % regla", f"{comp['totales']['regla']:.2f}")
                c3.metric("Diferencia total", f"{comp['totales']['diff']:.2f}")

                # gráfica comparativa
                if not dfc.empty:
                    dfplot = dfc.sort_values("unidad")
                    st.bar_chart(dfplot.set_index("unidad")[["pct_poliza", "pct_regla"]], use_container_width=True)
        except Exception as e:
            st.error(f"Error en la comparación: {e}")
        finally:
            # opcional: mantener la bandera en True para que la comparación se siga mostrando,
            # o ponerla en False si quieres que solo se ejecute una vez.
            ss.comp_ready = True

    st.markdown("---")
    st.subheader("Auto-aplicar (solo esta póliza)")

    col1, col2, col3 = st.columns(3)
    umbral = col1.number_input("Umbral score", 0.0, 20.0, value=1.0, step=0.1)
    gap    = col2.number_input("Brecha mínima", 0.0, 20.0, value=1.0, step=0.1)
    tolsum = col3.number_input("Tolerancia suma %", 0.0, 10.0, value=2.0, step=0.1)

    if st.button("Auto-aplicar esta póliza"):
        res = auto_aplicar_controller(eje, tipo, periodo, numero, usar_concepto=True, tol_pct=float(tol), umbral=float(umbral), gap=float(gap), tol_suma=float(tolsum))
        st.write(res)

    st.markdown("---")
    st.subheader("Auto-aplicar en lote (pendientes)")

    dry = st.checkbox("Dry-run (simular sin escribir)", value=True)
    lim = st.number_input("Límite de pólizas", 1, 5000, value=200, step=50)
    off = st.number_input("Offset", 0, 100000, value=0, step=100)

    if st.button("Ejecutar lote"):
        res = auto_aplicar_lote_controller(eje, origen="JAVA", usar_concepto=True,
                                        tol_pct=float(tol), umbral=float(umbral), gap=float(gap), tol_suma=float(tolsum),
                                        limit=int(lim), offset=int(off), dry_run=bool(dry))
        st.success(f"Procesadas: {res['procesadas']} · Aplicadas: {res['aplicadas']} · Saltadas: {res['saltadas']}")
        st.dataframe(pd.DataFrame(res["detalles"]), use_container_width=True)