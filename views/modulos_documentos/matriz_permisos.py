
import streamlit as st
import pandas as pd
import io
from database.conexion import obtener_conexion
from models.usuario_model import obtener_todos_usuarios
from views.modulos_documentos.admin_tipos import get_logical_type_path

def mostrar_matriz_permisos():
    st.title("📊 Matriz de permisos por usuario ")
    # 🔄 Botón para recargar datos desde cero
    if st.button("🔄 Recargar datos desde base de datos"):
        st.session_state["recargar"] = True
        st.rerun()

    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)

    usuarios = obtener_todos_usuarios()
    todos_los_usuarios = [u for u in usuarios]
    usuarios_seleccionados = st.multiselect("Filtrar por usuarios", todos_los_usuarios, default=[])

    if not usuarios_seleccionados:
        usuarios_filtrados = todos_los_usuarios
    else:
        usuarios_filtrados = usuarios_seleccionados

    cursor.execute("SELECT id, nombre FROM tipos_documento")
    tipos_all = cursor.fetchall()
    tipo_id_map = {t["id"]: t["nombre"] for t in tipos_all}
    carpetas_por_id = {t["id"]: get_logical_type_path(t["id"]) for t in tipos_all}

    cursor.execute("SELECT username, r.nombre AS tipo FROM usuarios_roles ur JOIN roles r ON ur.id_rol = r.id")
    permisos_carpeta = cursor.fetchall()
    permisos_carpeta_dict = {(p["username"], p["tipo"]): True for p in permisos_carpeta}

    cursor.execute("SELECT d.id, d.tipo_id FROM documentos d WHERE d.estatus != 'Eliminado'")
    docs_all = cursor.fetchall()

    cursor.execute("SELECT username, documento_id FROM permisos_documento")
    permisos_archivo = cursor.fetchall()
    permisos_archivo_dict = {(p["username"], p["documento_id"]): True for p in permisos_archivo}

    cursor.execute("""
        SELECT vd.documento_id, vd.nombre_archivo
        FROM versiones_documento vd
        INNER JOIN (
            SELECT documento_id, MAX(version) AS max_ver
            FROM versiones_documento
            GROUP BY documento_id
        ) v2 ON vd.documento_id = v2.documento_id AND vd.version = v2.max_ver
    """)
    nombres_docs = cursor.fetchall()
    nombre_doc_dict = {d["documento_id"]: d["nombre_archivo"] for d in nombres_docs}

    conn.close()
    rows = []
    for doc in docs_all:
        doc_id = doc["id"]
        tipo_id = doc["tipo_id"]
        ruta = carpetas_por_id.get(tipo_id, "?")
        archivo = nombre_doc_dict.get(doc_id, f"Archivo {doc_id}")

        fila = {"Ruta Carpeta": ruta, "Archivo": archivo}

        for user in usuarios_filtrados:
            tiene_archivo = permisos_archivo_dict.get((user, doc_id), False)
            fila[user] = tiene_archivo  # Booleano

        rows.append(fila)

    df_matriz = pd.DataFrame(rows)

    # Reconstruir el DataFrame editable si cambian los usuarios seleccionados
    if (
        "df_check_editable" not in st.session_state
        or st.session_state.get("usuarios_filtrados_actuales") != usuarios_filtrados
        or st.session_state.get("recargar") == True
    ):
        st.session_state["df_check_editable"] = df_matriz.copy()
        st.session_state["df_check_original"] = df_matriz.copy()
        st.session_state["usuarios_filtrados_actuales"] = usuarios_filtrados.copy()
        st.session_state["recargar"] = False  # ya recargado

    config_checkbox = {
        col: st.column_config.CheckboxColumn(label=col)
        for col in df_matriz.columns if col not in ["Ruta Carpeta", "Archivo"]
    }

    with st.form("form_edicion_permisos"):
        st.markdown("### ✏️ Edita los permisos (usa checkboxes)")
        edited_df = st.data_editor(
            st.session_state["df_check_editable"],
            column_config=config_checkbox,
            use_container_width=True,
            key="editor_checkbox"
        )
        submit = st.form_submit_button("💾 Guardar cambios")

    if submit:
        conn = obtener_conexion()
        cursor = conn.cursor()

        df_actual = edited_df.set_index(["Ruta Carpeta", "Archivo"])
        df_anterior = st.session_state["df_check_original"].set_index(["Ruta Carpeta", "Archivo"])

        # Diccionario para buscar documento_id por nombre de archivo
        archivo_to_id = {v: k for k, v in nombre_doc_dict.items()}

        permisos_agregados = []
        permisos_eliminados = []

        for (ruta, archivo), fila_actual in df_actual.iterrows():
            fila_anterior = df_anterior.loc[(ruta, archivo)]

            doc_id = archivo_to_id.get(archivo)
            if not doc_id:
                continue  # documento no encontrado

            for user in usuarios_filtrados:
                valor_actual = fila_actual.get(user, False)
                valor_anterior = fila_anterior.get(user, False)

                if valor_actual == valor_anterior:
                    continue  # sin cambio

                if valor_actual:  # se marcó (insertar)
                    cursor.execute(
                        "INSERT IGNORE INTO permisos_documento (username, documento_id, puede_editar, puede_eliminar) VALUES (%s, %s, 1, 1)",
                        (user, doc_id)
                    )
                    permisos_agregados.append((user, archivo))
                else:  # se desmarcó (eliminar)
                    cursor.execute(
                        "DELETE FROM permisos_documento WHERE username = %s AND documento_id = %s",
                        (user, doc_id)
                    )
                    permisos_eliminados.append((user, archivo))
        conn.commit()
        conn.close()
        # Botón para recargar datos desde cero
        

        st.success(f"✅ {len(permisos_agregados)} permisos agregados, ❌ {len(permisos_eliminados)} eliminados.")

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        st.session_state["df_check_editable"].to_excel(writer, sheet_name="MatrizPermisos", index=False)

    st.download_button(
        label="📥 Descargar Excel",
        data=output.getvalue(),
        file_name="matriz_permisos.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
