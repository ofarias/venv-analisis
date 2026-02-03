import streamlit as st
import datetime
from models.politicas_model import obtener_politicas

def mostrar_tabla_politicas():
    st.subheader("📚 Políticas registradas")

    politicas = obtener_politicas()

    if not politicas:
        st.info("No hay políticas registradas.")
        return

    for p in politicas:
        col1, col2 = st.columns([5, 1])
        with col1:
            st.markdown(f"### 📄 {p['Nombre']}")
            st.markdown(f"🗓️ Cargada: `{p['Fecha_Carga'].strftime('%Y-%m-%d')}`  •  Vence: `{p['Fecha_Vencimiento'].strftime('%Y-%m-%d')}`")
            st.markdown(f"📝 {p['Descripcion']}")
            etiquetas = []
            if p["Requiere_Firma"]:
                etiquetas.append("✍ Requiere firma")
            if p["Aviso_email"]:
                etiquetas.append("📧 Enviada por correo")
            if p["Estatus"] != "Activo":
                etiquetas.append(f"🚫 {p['Estatus']}")
            if etiquetas:
                st.markdown(" • ".join(etiquetas))
        with col2:
            if st.button("🔽 Descargar", key=f"ver_{p['Id']}"):
                st.warning("⚠️ Función de descarga pendiente")  # Aquí luego integramos

        st.divider()

