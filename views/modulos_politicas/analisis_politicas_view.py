import streamlit as st
import base64
import mimetypes
from models.politicas_model import obtener_resumen_firmas, obtener_detalle_firmas

def construir_link_descarga(nombre_archivo, datos_binarios):
    if not datos_binarios:
        return ""
    tipo_mime, _ = mimetypes.guess_type(nombre_archivo)
    if not tipo_mime:
        tipo_mime = "application/octet-stream"
    b64 = base64.b64encode(datos_binarios).decode()
    return f'<a href="data:{tipo_mime};base64,{b64}" download="{nombre_archivo}">📎</a>'

def mostrar_analisis_politicas():
    st.subheader("📊 Análisis de firmas de políticas")

    resumen = obtener_resumen_firmas()

    if not resumen:
        st.info("No hay políticas con firma requerida.")
        return

    for p in resumen:
        total = int(p["total_usuarios"])
        firmados = int(p["firmados"])
        pendientes = int(p["pendientes"])
        porcentaje = (firmados / total) * 100 if total > 0 else 0

        with st.expander(f"📄 {p['Nombre']}"):
            st.markdown(f"👥 Total usuarios: **{total}**")
            st.markdown(f"✍ Firmados: **{firmados}**")
            st.markdown(f"⏳ Pendientes: **{pendientes}**")
            st.progress(porcentaje / 100)

            
            detalles = obtener_detalle_firmas(p["Id"])
            for d in detalles:
                estado = "✅" if d["Estatus"] == "Firmado" else "⏳"
                fecha = d["Fecha_firma"].strftime("%Y-%m-%d %H:%M") if d["Fecha_firma"] else "-"

                link = ""
                if d["Estatus"] == "Firmado" and d.get("Documento_firma"):
                    link = construir_link_descarga(d["evidencia_nombre"], d["Documento_firma"])

                st.markdown(f"{estado} {d['Usuario_id']} — {d['Estatus']} — {fecha} {link}", unsafe_allow_html=True)