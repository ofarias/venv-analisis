import streamlit as st
import datetime
from models.politicas_model import crear_politica, crear_detalles_firma
from utils.envio_correo import enviar_correo_a_usuarios
from models.usuario_model import obtener_todos_usuarios
from views.modulos_politicas.ver_politicas_view import mostrar_tabla_politicas
from views.modulos_politicas.analisis_politicas_view import mostrar_analisis_politicas

def mostrar_pestanas_politicas():
    tab_crear, tab_ver, tab_analisis = st.tabs(["📄 Crear Políticas", "📚 Ver Políticas", "📊 Análisis de Políticas"])

    with tab_crear:
        mostrar_formulario_crear_politica()
    
    with tab_ver:
        mostrar_tabla_politicas()
    
    with tab_analisis:
        mostrar_analisis_politicas()


def mostrar_formulario_crear_politica():
    st.subheader("📄 Crear nueva política")

    usuarios_todos = obtener_todos_usuarios()  # Lista de usernames

    with st.form("form_politica"):
        nombre = st.text_input("Nombre de la política", max_chars=100)
        cargada_por = st.session_state["usuario"]["username"]
        fecha_carga = datetime.datetime.now()
        fecha_vencimiento = st.date_input("Fecha de vencimiento de la politica", format="YYYY-MM-DD")
        descripcion = st.text_area("Descripción")
        vigencia_inicial = st.date_input("Periodo inicial de firma: ", format="YYYY-MM-DD")
        vigencia_final = st.date_input("Periodo final de firma: ", format="YYYY-MM-DD")
        requiere_firma = st.checkbox("¿Requiere firma?")
        aviso_email = st.checkbox("¿Enviar aviso por correo?")
        #archivo = st.file_uploader("Sube el documento (PDF, Word)", type=["pdf", "docx"])
        archivo = st.file_uploader("📎 Adjuntar archivo de la política", type=["pdf", "jpg", "jpeg", "png", "docx"])
        
        usuarios_seleccionados = st.multiselect(
            "👥 Selecciona los usuarios que deben firmar esta política",
            options=usuarios_todos,
            key="usuarios_aplican"
        )
        if archivo is not None:
            documento = archivo.read()
            nombre_archivo = archivo.name
            extension = nombre_archivo.split(".")[-1].lower()
        else:
            documento = None
            nombre_archivo = ""
            extension = ""

        submitted = st.form_submit_button("Guardar política")

    if submitted:
        if not archivo:
            st.warning("⚠️ Debes subir un documento.")
            return
        documento_binario = archivo.read()
        politica_id = crear_politica(
            nombre=nombre,
            cargada=cargada_por,
            fecha_carga=fecha_carga,
            fecha_vencimiento=fecha_vencimiento,
            descripcion=descripcion,
            vigencia_inicial=vigencia_inicial,
            vigencia_final=vigencia_final,
            requiere_firma=requiere_firma,
            aviso_email=aviso_email,
            documento_binario=documento, 
            nombre_archivo=nombre_archivo,
            extension=extension,
        )

        if politica_id:
            st.success("✅ Política registrada correctamente.")

            if requiere_firma:
                usuarios=usuarios_seleccionados
                crear_detalles_firma(politica_id, usuarios)
                st.info(f"📝 Se generaron {len(usuarios)} registros en `PoliticasDetalle` para firma.")

            if aviso_email:
                enviar_correo_a_usuarios(
                    asunto=f"Nueva política publicada: {nombre}",
                    cuerpo_html=f"<p>Se ha cargado la política <b>{nombre}</b>.</p><p>{descripcion}</p>",
                    archivo_bytes=documento_binario,
                    nombre_archivo=archivo.name,
                    mimetype=archivo.type
                )
                st.info(f"📧 Correos enviados a todos los usuarios.")

            st.rerun()
        else:
            st.error("❌ Ocurrió un error al guardar la política.")