from utils.utils import colorear_estatus
from models.documento_model import *
from models.usuario_model import *
import streamlit as st
from utils.msgraph import obtener_archivos_onedrive
import pandas as pd
import requests
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
from utils.envio_correo import enviar_correo

def envio_correo(destinatario, asunto, cuerpo ):
    ok, msg = enviar_correo(
        destinatario=destinatario,
        asunto=asunto,
        cuerpo_html=cuerpo, 
        token= st.session_state["microsoft_token"],
        #archivo_adjunto="/ruta/del/archivo.pdf"
    )
    if ok:
        st.success(msg)
    else:
        st.error(msg)
    return ok, msg

def mostrar_documentos():
    if "tipos_documento" not in st.session_state:
        from models.documento_model import obtener_tipos_documento_con_ruta
        st.session_state["tipos_documento"] = obtener_tipos_documento_con_ruta()
    # --- Filtros ---
    with st.expander("🔍 Filtros test"):
        titulo_busqueda = st.text_input("Buscar por título")
        tipos = st.session_state["tipos_documento"]
        opciones = ["Todos"] + [t["ruta_completa"] for t in tipos]
        tipo_filtrado = st.selectbox("Filtrar por tipo", opciones)
        tipo_id = None
        if tipo_filtrado != "Todos":
            tipo_id = next((t["id"] for t in tipos if t["ruta_completa"] == tipo_filtrado), None)

        fecha_inicio = st.date_input("Desde", value=st.session_state.get("fecha_inicio"))
        fecha_fin = st.date_input("Hasta", value=st.session_state.get("fecha_fin"))

        if st.button("🔎 Buscar documentos"):
            st.session_state["titulo_busqueda"] = titulo_busqueda.strip()
            st.session_state["filtros_aplicados"] = True
            st.session_state["tipo_filtrado"] = tipo_filtrado
            st.session_state["fecha_inicio"] = fecha_inicio
            st.session_state["fecha_fin"] = fecha_fin

        if st.button("🧹 Limpiar filtros"):
            for key in ["filtros_aplicados", "tipo_filtrado", "fecha_inicio", "fecha_fin", "titulo_busqueda"]:
                st.session_state.pop(key, None)
            st.rerun()

    if "mensaje_exito_version" in st.session_state:
        st.success(st.session_state.pop("mensaje_exito_version"))
    if "toast_exito_version" in st.session_state:
        st.toast(st.session_state.pop("toast_exito_version"))

    st.subheader("📂 Documentos disponibles")
    username = st.session_state["usuario"]["username"]
    documentos = []

    if st.session_state.get("filtros_aplicados"):
        tipo_filtrado = st.session_state.get("tipo_filtrado")
        fecha_inicio = st.session_state.get("fecha_inicio")
        fecha_fin = st.session_state.get("fecha_fin")
        titulo_filtro = st.session_state.get("titulo_busqueda")

        tipo_id = next((t["id"] for t in st.session_state["tipos_documento"] if t["ruta_completa"] == tipo_filtrado), None) if tipo_filtrado != "Todos" else None

        documentos = obtener_documentos_por_usuario(
            username,
            tipo=tipo_id,
            fecha_ini=fecha_inicio,
            fecha_fin=fecha_fin,
            titulo=titulo_filtro
        )

    if not st.session_state.get("filtros_aplicados"):
        st.info("Usa los filtros para consultar los documentos.")
        return

    if not documentos:
        st.info("No se encontraron documentos con los filtros aplicados.")
        return

    # --- Tabla AgGrid ---
    data_tabla = []
    for doc in documentos:
        ruta = obtener_ruta(doc["docID"], incluir_nombre_archivo=True)
        doc["ruta_logica"] = ruta
        data_tabla.append({
            "ID": doc["docID"],
            "Nombre": (f"{doc['titulo']}.{doc['extension']}"),
            "Carpeta": doc["tipo"],
            "Versión": doc["version_actual"],
            "Ruta": ruta,
            "Fecha": doc["fecha_creacion"],
            #"Extension":doc["extension"],
            "Creado por": doc["creado_por"]
        })

    df = pd.DataFrame(data_tabla)
    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_selection("single")
    gb.configure_pagination()
    gb.configure_default_column(groupable=True, value=True, enableRowGroup=True, editable=False)
    grid_options = gb.build()

    grid_response = AgGrid(
        df,
        gridOptions=grid_options,
        update_mode=GridUpdateMode.SELECTION_CHANGED,
        fit_columns_on_grid_load=True,
        use_container_width=True
    )
    #st.write("Selección:", grid_response.get("selected_rows"))
    selected = grid_response.get("selected_rows")

    if selected is not None and not selected.empty:
        fila = selected.iloc[0].to_dict()    
        #st.write("Selected:", fila)    
        doc_id = fila["ID"]
        ruta = doc["ruta_logica"]
        doc = next((d for d in documentos if d["docID"] == doc_id), None)
        if doc:
            st.markdown("---")
            st.subheader(f"📄 {doc['titulo']} — v{doc['version_actual']}")
            st.markdown(f"**Ruta:** `{doc['ruta_logica']}`")
            ## st.markdown(f"**Carpeta:** {doc['tipo']}")
            st.markdown(f"**Fecha:** {doc['fecha_creacion']} | **Creado por:** {doc['creado_por']}")

            nuevo_titulo = st.text_input("Editar título", value=doc["titulo"], key=f"titulo_edit_{doc_id}")

            ### Manejo de tipo de documentos
            # Agrega justo después de editar título
            tipos = st.session_state["tipos_documento"]
            opciones_tipo = {t["ruta_completa"]: t["id"] for t in tipos}
            ruta_actual = next((t["ruta_completa"] for t in tipos if t["id"] == doc["tipo_id"]), "Desconocido")
            ruta_seleccionada = st.selectbox("Tipo de documento (**Mover Documento**)", list(opciones_tipo.keys()), index=list(opciones_tipo.keys()).index(ruta_actual), key=f"tipo_edit_{doc_id}")
            tipo_id_nuevo = opciones_tipo[ruta_seleccionada]
            ####  Finaliza el manejo de tipo de documentos

            ### Manejo de usarios:
            usuarios_asignados = obtener_permisos_documento(doc_id)  # función que tú debes tener o definir
            todos_usuarios = obtener_usuarios()
            usuarios_asignados = [u["username"] for u in usuarios_asignados]
            seleccion_usuarios = st.multiselect("Usuarios asignados", options=[u["username"] for u in todos_usuarios], default=usuarios_asignados, key=f"usuarios_{doc_id}")
            #### Finaliza el manejo de usuarios.

            col1, col2 = st.columns([2, 2])
            with col1:
                if "Ver" in doc["permisos"] and doc.get("archivo"):
                    st.download_button(
                        "⬇️ Descargar",
                        data=doc["archivo"],
                        file_name= (f"{doc['titulo']}.{doc['extension']}"),
                        mime="application/octet-stream",
                        key=f"download_aggrid_{doc['id']}"
                    )
            with col2:

                if st.button("💾 Guardar cambios", key=f"guardar_{doc_id}"):
                    # 1. Obtener usuarios antes del cambio
                    anteriores = set(usuarios_asignados)
                    nuevos = set(seleccion_usuarios)

                    # 2. Detectar usuarios agregados y eliminados
                    agregados = nuevos - anteriores
                    eliminados = anteriores - nuevos

                    # 3. Actualizar base de datos
                    actualizar_documento(doc_id, nuevo_titulo, doc["descripcion"], tipo_id_nuevo)
                    actualizar_usuarios_asignados(doc_id, seleccion_usuarios)

                    # 4. Enviar correos
                    #ruta = doc["ruta_logica"]
                    #titulo = doc["titulo"]
    
                    for usuario in agregados:
                        st.write(usuario)
                        email = obtener_usuario_por_username(usuario)
                        email = email['email']
                        envio_correo(
                            destinatario=email,
                            asunto="📎 Permiso otorgado",
                            cuerpo=f"El usuario {username} ha otorgado permiso al documento:\n\n{ruta}"
                        )
                    for usuario in eliminados:
                        st.write(usuario)
                        email = obtener_usuario_por_username(usuario)
                        email = email['email']
                        envio_correo(
                            destinatario=email,
                            asunto="📎 Permiso retirado",
                            cuerpo=f"El usuario {username} ha retirado el acceso al archivo:\n\n{ruta}"
                        )

                    st.success("✅ Cambios guardados y correos enviados.")
                    st.rerun()
            
            st.markdown("### 🔄 Cargar nueva versión")
            nueva_version_file = st.file_uploader("Selecciona el archivo", type=None, key=f"file_nueva_version_{doc_id}")
            comentario_version = st.text_area("Comentario de la versión", key=f"comentario_version_{doc_id}")
            if st.button("⬆️ Subir nueva versión", key=f"subir_version_{doc_id}"):
                if nueva_version_file:
                    # Guarda la nueva versión
                    titulo = nueva_version_file.name
                    titulo_ext = nueva_version_file.name.split(".")[-1],
                    guardar_nueva_version(
                        documento_id=doc_id,
                        archivo=nueva_version_file.read(),
                        nombre_archivo=nueva_version_file.name,
                        extension=nueva_version_file.name.split(".")[-1],
                        subido_por=st.session_state["usuario"]["username"],
                        comentario=comentario_version
                    )
                    st.success("✅ Nueva versión registrada.")
                    ##### aviso de nueva versio 
                    version = obtener_ultima_version_documento(doc_id)
                    usernames = usuarios_asignados

                    email = obtener_emails_usuarios(usernames)
                    
                    ok, msg = envio_correo(
                        destinatario = email,
                        asunto=f"""🆕 Nueva version disponible de {titulo} . {titulo_ext}""",
                        cuerpo= f"""
                        <p>El usuario <strong>{username}</strong> ha creado la versión <strong>{version}</strong> del documento:</p>
                        <p>{ruta}</p>
                        <p><strong>Comentario:</strong> {comentario_version}</p>
                        """
                    )
                    if ok:
                        st.success("✅ Correo enviado a todos los destinatarios")
                    else:
                        st.error(f"❌ Error al enviar el correo: {msg}")
                    st.rerun()
                    #### aviso nueva version
                else:
                    st.warning("Debes seleccionar un archivo para subir la nueva versión.")

            if st.button("📜 Ver historial de versiones", key=f"historial_{doc_id}"):
                historial = obtener_historial_versiones(doc_id)
                if historial:
                    with st.expander("🕓 Historial de versiones"):
                        for v in historial:
                            st.markdown(f"**Versión {v['version']}** - Subido por {v['subido_por']} el {v['fecha_subida']}")
                            st.markdown(f"**Comentario:** {v['comentario']}")
                            st.download_button(
                                label="⬇️ Descargar esta versión",
                                data=v['archivo'],
                                file_name=v.get("nombre_archivo", f"version_{v['version']}.bin"),
                                mime='application/octet-stream',
                                key=f"descargar_version_{doc_id}_{v['version']}"
                            )
                else:
                    st.info("No hay versiones anteriores.")


    ### Termina la visualizacion de los documentos

    # --- Sección OneDrive con navegación ---
    st.subheader("☁️ Archivos personales en OneDrive")

    token = st.session_state.get("microsoft_token", None)
    username = st.session_state["usuario"]["username"]

    if token:
        archivos_onedrive = obtener_archivos_onedrive(token)

        if not archivos_onedrive:
            st.info("No se encontraron archivos en OneDrive.")
        else:
            for archivo in archivos_onedrive:
                nombre = archivo.get("name", "Sin nombre")
                extension = archivo.get("extension", "xlsx")
                tamano = archivo.get("size", 0)
                fecha = archivo.get("lastModifiedDateTime", "Desconocido")
                download_url = archivo.get("@microsoft.graph.downloadUrl")

                with st.expander(f"📄 {nombre}"):
                    st.markdown(f"- 📏 **Tamaño**: {tamano} bytes")
                    st.markdown(f"- 🕒 **Última modificación**: {fecha}")

                    st.markdown(f"[⬇️ Descargar]({download_url})", unsafe_allow_html=True)

                    # --- Registro en el sistema ---
                    titulo = st.text_input(f"Título para {nombre}", value=nombre, key=f"titulo_{archivo['id']}")
                    descripcion = st.text_area(f"Descripción", value="Importado desde OneDrive", key=f"desc_{archivo['id']}")

                    # Selector de tipo
                    tipo_nombres = [t["nombre"] for t in st.session_state["tipos_documento"]]
                    tipo_seleccionado = st.selectbox("Tipo de documento", tipo_nombres, key=f"tipo_{archivo['id']}")
                    tipo_id = next(t["id"] for t in st.session_state["tipos_documento"] if t["nombre"] == tipo_seleccionado)

                    if st.button(f"📥 Registrar en el sistema", key=f"registrar_{archivo['id']}"):
                        try:
                            archivo_bytes = descargar_archivo(token, download_url)

                            doc_id = registrar_documento_onedrive(
                                titulo=nombre,
                                descripcion=descripcion,
                                tipo_id=tipo_id,
                                creado_por=st.session_state["usuario"]["username"],
                                archivo_bytes=archivo_bytes,
                                nombre_archivo=nombre,
                                extension=extension,
                                tamaño=tamano
                            )

                            if doc_id:
                                st.success("✅ Documento registrado correctamente.")
                                st.rerun()
                            else:
                                st.error("❌ No se pudo registrar el documento.")
                        except Exception as e:
                            st.error(f"❌ Error al descargar o registrar el archivo: {e}")
    else:
        st.warning("No se ha iniciado sesión con Microsoft.")


# Función auxiliar si la quieres dejar aparte
def descargar_archivo(token, url):
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    return response.content if response.status_code == 200 else None