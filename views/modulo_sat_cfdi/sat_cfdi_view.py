# views/modulo_sat_cfdi/sat_cfdi_view.py
from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from controllers.sat_cfdi_controller import (
    solicitar_sync,
    verificar_y_completar_pendientes,
    verificar_cancelados,
    cargar_cfdi,
    contar_cfdi_cached,
    cargar_bitacora,
    exportar_excel,
)
from utils.sat_client import TIPOS_COMPROBANTE
from logs.logger import registrar_log

_NOMBRES_TIPO = {"I": "I - Ingreso", "E": "E - Egreso", "P": "P - Pago"}


def _default_dates():
    hoy = date.today()
    return hoy - timedelta(days=7), hoy


def _usuario_actual() -> str:
    usuario = st.session_state.get("usuario") or {}
    if isinstance(usuario, dict):
        return usuario.get("username", "desconocido")
    return str(usuario)


def mostrar_modulo_sat_cfdi():
    st.title("🧾 Descarga SAT CFDI (recibidos)")
    st.caption(
        "Fuente propia de CFDI recibidos (I/E/P), independiente de ADA — bajada "
        "directo del webservice de Descarga Masiva del SAT con la FIEL."
    )

    usuario = _usuario_actual()
    f_desde_def, f_hasta_def = _default_dates()

    tab_sync, tab_docs, tab_bitacora = st.tabs(["Sincronizar", "Documentos", "Bitácora"])

    # ------------------------------------------------------------------
    # Sincronizar
    # ------------------------------------------------------------------
    with tab_sync:
        st.subheader("1. Solicitar descarga al SAT")
        col1, col2 = st.columns(2)
        with col1:
            f_desde = st.date_input("Desde", value=f_desde_def, format="YYYY-MM-DD", key="sat_f_desde")
        with col2:
            f_hasta = st.date_input("Hasta", value=f_hasta_def, format="YYYY-MM-DD", key="sat_f_hasta")

        tipos_sel = st.multiselect(
            "Tipo de comprobante",
            options=list(TIPOS_COMPROBANTE),
            default=list(TIPOS_COMPROBANTE),
            format_func=lambda t: _NOMBRES_TIPO.get(t, t),
            key="sat_tipos",
        )

        if st.button("Solicitar descarga ahora", key="sat_btn_solicitar"):
            if f_desde > f_hasta:
                st.error("La fecha 'desde' no puede ser mayor a 'hasta'.")
            elif not tipos_sel:
                st.error("Selecciona al menos un tipo de comprobante.")
            else:
                with st.spinner("Enviando solicitud(es) al SAT..."):
                    resultados = solicitar_sync(
                        st.secrets, usuario, f_desde, f_hasta, tuple(tipos_sel), origen="manual"
                    )
                ok = [r for r in resultados if r["ok"]]
                fail = [r for r in resultados if not r["ok"]]
                if ok:
                    st.success(
                        f"Solicitadas: {', '.join(r['tipo'] for r in ok)}. "
                        "El SAT procesa esto de forma asíncrona — usa 'Verificar pendientes' "
                        "en unos minutos."
                    )
                    registrar_log(usuario, "SAT CFDI - solicitar descarga",
                                  f"{f_desde} a {f_hasta}, tipos={tuple(tipos_sel)}")
                if fail:
                    st.error("Fallaron: " + "; ".join(f"{r['tipo']}: {r['mensaje']}" for r in fail))
                cargar_bitacora.clear()

        st.divider()
        st.subheader("2. Verificar y descargar pendientes")
        st.caption("Revisa las solicitudes ya enviadas; si el SAT ya las terminó, descarga los XML.")
        if st.button("Verificar pendientes ahora", key="sat_btn_verificar_pend"):
            with st.spinner("Consultando al SAT..."):
                resultados = verificar_y_completar_pendientes(st.secrets)
            if not resultados:
                st.info("No hay solicitudes pendientes.")
            else:
                terminadas = [r for r in resultados if r["estado"] == "terminada"]
                en_proceso = [r for r in resultados if r["estado"] == "en_proceso"]
                errores = [r for r in resultados if r["estado"] == "error"]
                if terminadas:
                    nuevos = sum(r["nuevos"] for r in terminadas)
                    actualizados = sum(r["actualizados"] for r in terminadas)
                    st.success(f"Completadas: {len(terminadas)} | XML nuevos: {nuevos} | actualizados: {actualizados}")
                    registrar_log(usuario, "SAT CFDI - descarga completada",
                                  f"nuevos={nuevos}, actualizados={actualizados}")
                if en_proceso:
                    st.info(f"Siguen en proceso en el SAT: {len(en_proceso)} (intenta de nuevo en unos minutos)")
                if errores:
                    st.error(f"Con error: {len(errores)} — revisa la bitácora")
                cargar_cfdi.clear()
                contar_cfdi_cached.clear()
                cargar_bitacora.clear()

        st.divider()
        st.subheader("3. Verificar cancelados")
        st.caption("Revisa contra el SAT si algún CFDI que tenemos como Vigente ya fue cancelado.")
        limite = st.number_input(
            "Máximo a revisar en esta corrida", min_value=10, max_value=5000, value=500, step=10,
            key="sat_limite_cancelados",
        )
        if st.button("Verificar cancelados ahora", key="sat_btn_verificar_cancelados"):
            with st.spinner("Consultando estatus en el SAT..."):
                res = verificar_cancelados(usuario, origen="manual", limite=int(limite))
            st.success(
                f"Revisados: {res['revisados']} | Actualizados a otro estatus: {res['actualizados']} | "
                f"Errores: {res['errores']}"
            )
            registrar_log(usuario, "SAT CFDI - verificar cancelados",
                          f"revisados={res['revisados']}, actualizados={res['actualizados']}")
            cargar_cfdi.clear()
            contar_cfdi_cached.clear()
            cargar_bitacora.clear()

    # ------------------------------------------------------------------
    # Documentos
    # ------------------------------------------------------------------
    with tab_docs:
        st.subheader("CFDI recibidos guardados")
        colf1, colf2, colf3, colf4 = st.columns(4)
        with colf1:
            f_desde2 = st.date_input("Desde", value=f_desde_def, format="YYYY-MM-DD", key="sat_doc_desde")
        with colf2:
            f_hasta2 = st.date_input("Hasta", value=f_hasta_def, format="YYYY-MM-DD", key="sat_doc_hasta")
        with colf3:
            tipo_f = st.selectbox("Tipo", options=["Todos"] + list(TIPOS_COMPROBANTE), key="sat_doc_tipo")
        with colf4:
            estado_f = st.selectbox("Estatus", options=["Todos", "Vigente", "Cancelado"], key="sat_doc_estado")

        rfc_f = st.text_input("RFC emisor contiene", key="sat_doc_rfc")

        filtros = {"fecha_desde": str(f_desde2), "fecha_hasta": str(f_hasta2)}
        if tipo_f != "Todos":
            filtros["tipo_comprobante"] = tipo_f
        if estado_f != "Todos":
            filtros["estado_sat"] = estado_f
        if rfc_f:
            filtros["rfc_emisor"] = rfc_f

        page = st.number_input("Página", min_value=1, value=1, step=1, key="sat_doc_page")
        page_size = 50

        total = contar_cfdi_cached(filtros)
        st.caption(f"{total} documentos encontrados")

        df = cargar_cfdi(filtros, int(page), page_size)
        st.dataframe(df, use_container_width=True, hide_index=True)

        if st.button("Exportar a Excel", key="sat_doc_export"):
            try:
                xlsx = exportar_excel(df)
                st.download_button(
                    "Descargar cfdi_recibidos.xlsx",
                    data=xlsx,
                    file_name="cfdi_recibidos.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="sat_doc_export_btn",
                )
            except Exception as e:
                st.error(f"No se pudo exportar: {e}")

    # ------------------------------------------------------------------
    # Bitácora
    # ------------------------------------------------------------------
    with tab_bitacora:
        st.subheader("Bitácora de corridas")
        df_log = cargar_bitacora(50)
        st.dataframe(df_log, use_container_width=True, hide_index=True)
