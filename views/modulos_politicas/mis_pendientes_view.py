import streamlit as st
from models.politicas_model import obtener_politicas_pendientes_usuario, guardar_evidencia_politica

def mostrar_mis_pendientes():
    st.subheader("📥 Políticas pendientes por firmar")

    username = st.session_state["usuario"]["username"]
    pendientes = obtener_politicas_pendientes_usuario(username)

    if not pendientes:
        st.success("🎉 No tienes políticas pendientes.")
        return

    for p in pendientes:
        with st.expander(f"📄 {p['Nombre']}"):
            st.markdown(f"📝 {p['Descripcion']}")
            st.markdown(f"📅 Fecha de carga: `{p['Fecha_Carga']}`")
            st.markdown(f"📅 Vence: `{p['Fecha_Vencimiento']}`")
            
            archivo = st.file_uploader("📎 Subir evidencia (firma)", type=["pdf", "jpg", "png", "docx"], key=f"file_{p['Id']}")
            
            if archivo and st.button("✅ Subir evidencia", key=f"btn_{p['Id']}"):
                guardar_evidencia_politica(p["Politica_id"], username, archivo)
                st.success("✅ Evidencia cargada correctamente")
                st.rerun()