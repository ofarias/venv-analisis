import streamlit as st
import os
from database.conexion import obtener_conexion
from logs.logger import registrar_log
from utils.envio_correo import *
from models.usuario_model import *
import pandas as pd
os.makedirs("static/tipos", exist_ok=True)


def obtener_ids_padres(tipo_id, tipos_by_id):
    ids = []
    actual = tipos_by_id.get(tipo_id)
    while actual and actual.get("padre_id"):
        ids.append(actual["padre_id"])
        actual = tipos_by_id.get(actual["padre_id"])
    return ids

def obtener_ids_hijos(tipo_id, tipos):
    hijos = []

    def recorrer(nodo_id):
        for t in tipos:
            if t["padre_id"] == nodo_id:
                hijos.append(t["id"])
                recorrer(t["id"])

    recorrer(tipo_id)
    return hijos

def obtener_usuarios_tipo(tipo_id):
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("SELECT username from usuarios_roles ur left join roles r on r.id = ur.id_rol WHERE r.nombre = (Select nombre from tipos_documento where id = %s)", (tipo_id,))
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows]

def existe_rol(nombre):
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM roles WHERE nombre = %s", (nombre,))
    existe = cursor.fetchone()[0] > 0
    conn.close()
    return existe

def obtener_todos_usuarios():
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("SELECT username FROM usuarios")
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows]

def actualizar_usuarios_tipo(tipo_id, usuarios):
    try:
        conn = obtener_conexion()
        cursor = conn.cursor()

        # Buscar el nombre del tipo
        cursor.execute("SELECT nombre FROM tipos_documento WHERE id = %s", (tipo_id,))
        row = cursor.fetchone()
        if not row:
            st.error("❌ No se encontró el tipo de documento.")
            return False
        nombre_tipo = row[0]

        # Buscar el id del rol asociado
        cursor.execute("SELECT id FROM roles WHERE nombre = %s", (nombre_tipo,))
        rol_row = cursor.fetchone()
        if not rol_row:
            st.error(f"❌ No se encontró el rol '{nombre_tipo}' en la tabla roles.")
            return False
        id_rol = rol_row[0]

        # Actualizar registros en usuarios_roles
        cursor.execute("DELETE FROM usuarios_roles WHERE id_rol = %s", (id_rol,))
        for u in usuarios:
            cursor.execute(
                "INSERT INTO usuarios_roles (id_rol, username) VALUES (%s, %s)",
                (id_rol, u)
            )

        conn.commit()
        return True
    except Exception as e:
        st.error(f"❌ Error actualizando usuarios: {e}")
        return False
    finally:
        conn.close()

def get_logical_type_path(tipo_id):
    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)
    segmentos = []
    while tipo_id is not None:
        cursor.execute("SELECT nombre, padre_id FROM tipos_documento WHERE id = %s", (tipo_id,))
        row = cursor.fetchone()
        if not row:
            break
        segmentos.insert(0, row["nombre"])
        tipo_id = row["padre_id"]
    conn.close()
    return "/".join(segmentos)

def obtener_tipos():
    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM tipos_documento ORDER BY nombre")
    tipos = cursor.fetchall()
    conn.close()
    return tipos

def crear_tipo(nombre, padre_id=None, imagen_nombre=None, descripcion_nueva=None):
    try:
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO tipos_documento (nombre, padre_id, imagen, descripcion) VALUES (%s, %s, %s, %s)", (nombre, padre_id, imagen_nombre, descripcion_nueva))
        # El acceso por rol compara tipo.nombre == rol.nombre en toda la app:
        # sin esto, el tipo recién creado quedaba sin nadie con acceso hasta
        # que alguien creara el rol manualmente en Administración de roles.
        cursor.execute("SELECT COUNT(*) FROM roles WHERE nombre = %s", (nombre,))
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO roles (nombre) VALUES (%s)", (nombre,))
        conn.commit()
        return True
    except Exception as e:
        st.error(f"❌ Error al crear tipo: {e}")
        return False
    finally:
        conn.close()

def actualizar_tipo(id, nuevo_nombre, nuevo_padre_id, imagen_nombre, descripcion_nueva):
    try:
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute("UPDATE tipos_documento SET nombre = %s, padre_id = %s, imagen = %s, descripcion = %s WHERE id = %s",
                       (nuevo_nombre, nuevo_padre_id, imagen_nombre, descripcion_nueva, id))
        conn.commit()
        return True
    except Exception as e:
        st.error(f"❌ Error al actualizar tipo: {e}")
        return False
    finally:
        conn.close()

def eliminar_tipo(id):
    try:
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM tipos_documento WHERE padre_id = %s", (id,))
        hijos = cursor.fetchone()[0]
        if hijos > 0:
            st.error(f"⛔ No se puede eliminar el tipo porque tiene {hijos} subtipos asociados.")
            return False
        cursor.execute("SELECT COUNT(*) FROM documentos WHERE estatus != 'Eliminado' and tipo_id = %s", (id,))
        usados = cursor.fetchone()[0]
        if usados > 0:
            st.error(f"⛔ No se puede eliminar el tipo porque está asociado a {usados} documento(s).")
            return False
        cursor.execute("SELECT nombre FROM tipos_documento WHERE id = %s", (id,))
        row = cursor.fetchone()
        nombre_tipo = row[0] if row else None
        cursor.execute("DELETE FROM tipos_documento WHERE id = %s", (id,))
        # Solo borramos el rol huérfano si ningún OTRO tipo sigue usando ese
        # nombre — hay 7 nombres duplicados en la base (hasta 12 veces), y
        # borrar el rol rompería el acceso de los tipos hermanos que quedan.
        if nombre_tipo:
            cursor.execute("SELECT COUNT(*) FROM tipos_documento WHERE nombre = %s AND id != %s", (nombre_tipo, id))
            if cursor.fetchone()[0] == 0:
                cursor.execute("DELETE FROM roles WHERE nombre = %s", (nombre_tipo,))
        conn.commit()
        return True
    except Exception as e:
        st.error(f"❌ Error al eliminar tipo: {e}")
        return False
    finally:
        conn.close()

def construir_jerarquia(tipos):
    hijos = {t["id"]: [] for t in tipos}
    for t in tipos:
        if t["padre_id"]:
            hijos[t["padre_id"]].append(t)

    def recorrer(tipo, nivel=0):
        yield (tipo, nivel)
        for hijo in hijos.get(tipo["id"], []):
            yield from recorrer(hijo, nivel + 1)

    raices = [t for t in tipos if not t["padre_id"]]
    resultado = []
    for raiz in raices:
        resultado.extend(recorrer(raiz))
    return resultado

def mostrar_admin_tipos():
    st.subheader("🗂️ Tipos y subtipos de documento")

    tab_crear, tab_admin = st.tabs(["🆕 Crear tipo", "🛠️ Administrar tipos"])

    tipos = obtener_tipos()
    tipos_dict = {t["id"]: t["nombre"] for t in tipos}
    tipos_jerarquia = construir_jerarquia(tipos)
    tipos_by_id = { t['id']: t for t, _ in tipos_jerarquia }
    rutas = { tipo_id: get_logical_type_path(tipo_id) for tipo_id in tipos_by_id.keys() }

    with tab_crear:
        with st.form("form_crear_tipo"):
            nombre_nuevo = st.text_input("Nombre del nuevo tipo o subtipo")
            padre_opciones = {f"{'⟶ '*nivel}{t['nombre']}": t["id"] for t, nivel in tipos_jerarquia}
            padre_opciones["(Sin padre - tipo raíz)"] = None
            padre_nombre = st.selectbox("Padre del nuevo tipo", list(padre_opciones.keys()))
            padre_id = padre_opciones[padre_nombre]
            descripcion_nueva = st.text_area("Descripción del nuevo tipo")
            imagen_nueva = st.file_uploader("Imagen asociada (opcional)", type=["png", "jpg", "jpeg"], key="imagen_nueva")
            nombre_imagen = imagen_nueva.name if imagen_nueva else None
            submit = st.form_submit_button("Crear")

        if submit and nombre_nuevo:
            if crear_tipo(nombre_nuevo, padre_id, nombre_imagen, descripcion_nueva):
                if imagen_nueva:
                    with open(f"static/tipos/{nombre_imagen}", "wb") as f:
                        f.write(imagen_nueva.read())
                registrar_log(st.session_state["usuario"]["username"], "Crear tipo documento", nombre_nuevo)
                st.success(f"✅ Tipo '{nombre_nuevo}' creado correctamente.")
                st.rerun()

    with tab_admin:
        st.divider()
        search_query = st.text_input("🔍 Buscar tipos y subtipos", key="search_tipos")
        tipos_mostrar = []

        if search_query:
            tipos_filtrados = [
                (t, lvl) for t, lvl in tipos_jerarquia
                if search_query.lower() in rutas[t["id"]].lower()
            ]
            ids_encontrados = {t["id"] for t, _ in tipos_filtrados}

            def pertenece_a_padre(tipo, id_padre):
                actual = tipo
                while actual.get("padre_id"):
                    if actual["padre_id"] == id_padre:
                        return True
                    actual = tipos_by_id.get(actual["padre_id"], {})
                return False

            tipos_mostrar = []
            for t, lvl in tipos_jerarquia:
                if t["id"] in ids_encontrados or any(pertenece_a_padre(t, id) for id in ids_encontrados):
                    tipos_mostrar.append((t, lvl))
        else:
            st.info("🔍 Escribe al menos una palabra para buscar tipos de documento.")
            return

        for tipo, nivel in tipos_mostrar:
            ruta_completa = get_logical_type_path(tipo["id"])
            titulo = f"{ruta_completa} 📄"
            with st.expander(titulo):
                st.markdown(f"**Ruta completa:** <span style='color:blue'>{ruta_completa}</span>", unsafe_allow_html=True)
                col1, col2 = st.columns([3, 2])
                with col1:
                    nuevo_nombre = st.text_input(f"Nombre tipo #{tipo['id']}", tipo['nombre'], key=f"nombre_{tipo['id']}")
                with col2:
                    # Excluye el tipo mismo y todos sus descendientes: elegir uno
                    # de ellos como nuevo padre crearía un ciclo infinito en la
                    # jerarquía (rompe get_logical_type_path, Navegar, etc.).
                    descendientes = set(obtener_ids_hijos(tipo['id'], tipos))
                    opciones_padre = {
                        rutas[tid]: tid
                        for tid in rutas
                        if tid != tipo['id'] and tid not in descendientes
                    }
                    opciones_padre["(Sin padre – tipo raíz)"] = None
                    padre_actual = tipo.get("padre_id")
                    padre_label = next(
                        (label for label, val in opciones_padre.items() if val == padre_actual),
                        "(Sin padre – tipo raíz)"
                    )
                    nuevo_padre = st.selectbox("Padre", options=list(opciones_padre.keys()), index=list(opciones_padre.keys()).index(padre_label), key=f"padre_{tipo['id']}")
                    nuevo_padre_id = opciones_padre[nuevo_padre]

                nueva_descripcion = st.text_area("Descripción", tipo.get("descripcion", ""), key=f"desc_{tipo['id']}")
                imagen_actual = tipo.get("imagen")
                nueva_imagen = st.file_uploader("Cambiar imagen", type=["png", "jpg", "jpeg"], key=f"imagen_{tipo['id']}")
                nombre_nueva_imagen = nueva_imagen.name if nueva_imagen else imagen_actual
    ####
                col_guardar, col_eliminar = st.columns([1, 1])
                with col_guardar:
                    if st.button("Guardar", key=f"guardar_{tipo['id']}"):
                        # El acceso por rol compara tipo.nombre == rol.nombre en toda
                        # la app: renombrar sin un rol que coincida deja el acceso de
                        # los usuarios actuales apuntando a un nombre que ya no existe.
                        if nuevo_nombre != tipo['nombre'] and not existe_rol(nuevo_nombre):
                            st.error(
                                f"⛔ No existe un rol llamado '{nuevo_nombre}'. Créalo primero en "
                                "Administración de roles — si renombras ahora, los usuarios que "
                                "tienen acceso por rol a este tipo lo perderán."
                            )
                        else:
                            if nueva_imagen:
                                with open(f"static/tipos/{nueva_imagen.name}", "wb") as f:
                                    f.write(nueva_imagen.read())
                            if actualizar_tipo(tipo['id'], nuevo_nombre, nuevo_padre_id, nombre_nueva_imagen, nueva_descripcion):
                                registrar_log(st.session_state["usuario"]["username"], "Editar tipo documento", nuevo_nombre)
                                st.success("✅ Actualizado")
                                st.rerun()
                with col_eliminar:
                    if st.button("🗑️", key=f"eliminar_{tipo['id']}"):
                        if eliminar_tipo(tipo['id']):
                            registrar_log(st.session_state["usuario"]["username"], "Eliminar tipo documento", tipo['nombre'])
                            st.success("✅ Eliminado")
                            st.rerun()

    ####
                st.subheader("🔑 Usuarios con acceso")

                clave_anteriores = f"anteriores_tipo_{tipo['id']}"
                clave_seleccion = f"seleccion_tipo_{tipo['id']}"

                actuales = obtener_usuarios_tipo(tipo['id'])
                todos = obtener_todos_usuarios()

                # Guardar los valores originales una sola vez
                if clave_anteriores not in st.session_state:
                    st.session_state[clave_anteriores] = actuales
                if clave_seleccion not in st.session_state:
                    st.session_state[clave_seleccion] = actuales

                # Multiselect que se actualiza sobre selección, sin alterar los "anteriores"
                seleccion = st.multiselect(
                    "Asignar usuarios a este tipo",
                    options=todos,
                    default=st.session_state[clave_seleccion],
                    key=f"usuarios_tipo_{tipo['id']}"
                )

                # ——— Herencia de permisos ———
                st.markdown("### 🔄 Heredar permisos")

                modo_herencia = st.selectbox(
                    "Tipo de herencia de permisos",
                    [
                        "Heredar padres y archivos",
                        "Heredar hijos y archivos",
                        "Heredar padres (solo carpetas)",
                        "Heredar hijos (solo carpetas)",
                        "Heredar archivos (ruta actual)"
                    ],
                    key=f"modo_herencia_{tipo['id']}"
                )

                solo_nuevos = st.checkbox(
                    "Asignar solo a usuarios nuevos (no sobreescribe actuales)",
                    key=f"solo_nuevos_{tipo['id']}"
                )
                ### finaliza la Herencia

                if st.button("Guardar usuarios", key=f"guardar_usuarios_{tipo['id']}"):
                    anteriores = set(st.session_state[clave_anteriores])
                    nuevos = set(seleccion)

                    if solo_nuevos:
                        agregados = nuevos - anteriores
                        eliminados = set()
                    else:
                        agregados = nuevos
                        eliminados = anteriores - nuevos

                    if actualizar_usuarios_tipo(tipo['id'], seleccion):
                        ruta = get_logical_type_path(tipo['id'])
                        token = st.session_state["microsoft_token"]

                        tipos = obtener_tipos()
                        tipos_dict_by_id = {t["id"]: t for t in tipos}

                        def obtener_id_rol_por_nombre(nombre_tipo):
                            conn = obtener_conexion()
                            cursor = conn.cursor()
                            cursor.execute("SELECT id FROM roles WHERE nombre = %s", (nombre_tipo,))
                            row = cursor.fetchone()
                            conn.close()
                            return row[0] if row else None

                        def obtener_documentos_por_tipo(tipo_id):
                            conn = obtener_conexion()
                            cursor = conn.cursor()
                            cursor.execute("SELECT id FROM documentos WHERE tipo_id = %s AND estatus != 'Eliminado'", (tipo_id,))
                            docs = [r[0] for r in cursor.fetchall()]
                            conn.close()
                            return docs

                        tipos_a_heredar = set()
                        documentos_a_heredar = set()
                        modo = st.session_state[f"modo_herencia_{tipo['id']}"]

                        if modo == "Heredar padres y archivos":
                            padres = obtener_ids_padres(tipo['id'], tipos_dict_by_id)
                            tipos_a_heredar.update(padres + [tipo['id']])
                            for tid in padres + [tipo['id']]:
                                documentos_a_heredar.update(obtener_documentos_por_tipo(tid))

                        elif modo == "Heredar hijos y archivos":
                            hijos = obtener_ids_hijos(tipo['id'], tipos)
                            tipos_a_heredar.update(hijos + [tipo['id']])
                            for tid in hijos + [tipo['id']]:
                                documentos_a_heredar.update(obtener_documentos_por_tipo(tid))

                        elif modo == "Heredar padres (solo carpetas)":
                            padres = obtener_ids_padres(tipo['id'], tipos_dict_by_id)
                            tipos_a_heredar.update(padres)

                        elif modo == "Heredar hijos (solo carpetas)":
                            hijos = obtener_ids_hijos(tipo['id'], tipos)
                            tipos_a_heredar.update(hijos)

                        elif modo == "Heredar archivos (ruta actual)":
                            documentos_a_heredar.update(obtener_documentos_por_tipo(tipo['id']))

                        resumen_cambios = {u: {"carpetas": [], "documentos": []} for u in agregados}
                        resumen_eliminados = {u: {"carpetas": [], "documentos": []} for u in eliminados}

                        conn = obtener_conexion()
                        cursor = conn.cursor()

                        usuarios_afectados = list(agregados | eliminados)

                        # permisos sobre tipos (usuarios_roles) — batched: antes hacía
                        # 2 queries por tipo x usuario; para jerarquías con decenas de
                        # subtipos esto podía ser cientos de round-trips por clic.
                        rutas_por_rol = {}
                        for tipo_id_heredar in tipos_a_heredar:
                            nombre_tipo = tipos_dict_by_id.get(tipo_id_heredar, {}).get("nombre")
                            id_rol = obtener_id_rol_por_nombre(nombre_tipo)
                            if not id_rol:
                                continue
                            ruta_completa = get_logical_type_path(tipo_id_heredar)
                            rutas_por_rol.setdefault(id_rol, []).append(ruta_completa)

                        ids_roles = list(rutas_por_rol.keys())
                        roles_existentes = set()
                        if ids_roles and usuarios_afectados:
                            ph_roles = ",".join(["%s"] * len(ids_roles))
                            ph_users = ",".join(["%s"] * len(usuarios_afectados))
                            cursor.execute(
                                f"SELECT id_rol, username FROM usuarios_roles "
                                f"WHERE id_rol IN ({ph_roles}) AND username IN ({ph_users})",
                                (*ids_roles, *usuarios_afectados)
                            )
                            roles_existentes = {(r[0], r[1]) for r in cursor.fetchall()}

                        filas_roles_insertar, filas_roles_borrar = [], []
                        for id_rol, rutas in rutas_por_rol.items():
                            for usuario in agregados:
                                if (id_rol, usuario) not in roles_existentes:
                                    filas_roles_insertar.append((usuario, id_rol))
                                    resumen_cambios[usuario]["carpetas"].extend(rutas)
                            for usuario in eliminados:
                                if (id_rol, usuario) in roles_existentes:
                                    filas_roles_borrar.append((usuario, id_rol))
                                    resumen_eliminados[usuario]["carpetas"].extend(rutas)

                        if filas_roles_insertar:
                            cursor.executemany("INSERT INTO usuarios_roles (username, id_rol) VALUES (%s, %s)", filas_roles_insertar)
                        if filas_roles_borrar:
                            cursor.executemany("DELETE FROM usuarios_roles WHERE username = %s AND id_rol = %s", filas_roles_borrar)

                        # permisos sobre documentos (permisos_documento) — mismo batching:
                        # para tipos con cientos de documentos esto podía ser miles de
                        # round-trips por clic (ya vimos hasta 385 documentos en un tipo).
                        ids_docs = list(documentos_a_heredar)
                        archivo_nombres = {}
                        if ids_docs:
                            ph_docs = ",".join(["%s"] * len(ids_docs))
                            cursor.execute(f"""
                                SELECT vd.documento_id, vd.nombre_archivo
                                FROM versiones_documento vd
                                JOIN (
                                    SELECT documento_id, MAX(version) AS ultima_version
                                    FROM versiones_documento
                                    WHERE documento_id IN ({ph_docs})
                                    GROUP BY documento_id
                                ) ult ON ult.documento_id = vd.documento_id AND ult.ultima_version = vd.version
                            """, ids_docs)
                            archivo_nombres = {r[0]: r[1] for r in cursor.fetchall()}

                        permisos_existentes = set()
                        if ids_docs and usuarios_afectados:
                            ph_docs = ",".join(["%s"] * len(ids_docs))
                            ph_users = ",".join(["%s"] * len(usuarios_afectados))
                            cursor.execute(
                                f"SELECT documento_id, username FROM permisos_documento "
                                f"WHERE documento_id IN ({ph_docs}) AND username IN ({ph_users})",
                                (*ids_docs, *usuarios_afectados)
                            )
                            permisos_existentes = {(r[0], r[1]) for r in cursor.fetchall()}

                        filas_docs_insertar, filas_docs_borrar = [], []
                        for doc_id in ids_docs:
                            archivo_nombre = archivo_nombres.get(doc_id)
                            for usuario in agregados:
                                if (doc_id, usuario) not in permisos_existentes:
                                    filas_docs_insertar.append((doc_id, usuario))
                                    if archivo_nombre:
                                        resumen_cambios[usuario]["documentos"].append(archivo_nombre)
                            for usuario in eliminados:
                                if (doc_id, usuario) in permisos_existentes:
                                    filas_docs_borrar.append((doc_id, usuario))
                                    if archivo_nombre:
                                        resumen_eliminados[usuario]["documentos"].append(archivo_nombre)

                        if filas_docs_insertar:
                            cursor.executemany(
                                "INSERT INTO permisos_documento (documento_id, username, puede_editar, puede_eliminar) VALUES (%s, %s, 1, 1)",
                                filas_docs_insertar
                            )
                        if filas_docs_borrar:
                            cursor.executemany(
                                "DELETE FROM permisos_documento WHERE documento_id = %s AND username = %s",
                                filas_docs_borrar
                            )

                        conn.commit()
                        conn.close()

                        # enviar correos
                        for usuario in agregados:
                            email = obtener_usuario_por_username(usuario)
                            if not email:
                                st.toast(f"❌ Email no encontrado para {usuario}")
                                continue
                            email = email["email"]
                            carpetas = resumen_cambios[usuario]["carpetas"] or []
                            documentos = resumen_cambios[usuario]["documentos"] or []

                            carpetas_html = "".join(f"<li>{c}</li>" for c in carpetas) or "<li>Ninguna</li>"
                            documentos_html = "".join(f"<li>{d}</li>" for d in documentos) or "<li>Ninguno</li>"

                            cuerpo = f"""
                            <p>Se han asignado los siguientes permisos:</p>
                            <b>Carpetas:</b>
                            <ul>{carpetas_html}</ul>
                            <b>Archivos:</b>
                            <ul>{documentos_html}</ul>
                            """
                            ok, msg = enviar_correo(
                                destinatario=email,
                                asunto="🔐 Permisos otorgados",
                                cuerpo_html=cuerpo,
                                token=token
                            )
                            log_msg = f"Modo: {modo} / Carpetas: {carpetas} / Archivos: {documentos}"
                            registrar_log(usuario, "Permisos otorgados", log_msg)
                            st.toast(f"📧 Correo enviado a {usuario} / {email}" if ok else f"❌ Error con {usuario}: {msg}")

                        for usuario in eliminados:
                            email = obtener_usuario_por_username(usuario)
                            if not email:
                                st.toast(f"❌ Email no encontrado para {usuario}")
                                continue
                            email = email["email"]
                            carpetas = resumen_eliminados[usuario]["carpetas"] or []
                            documentos = resumen_eliminados[usuario]["documentos"] or []

                            carpetas_html = "".join(f"<li>{c}</li>" for c in carpetas) or "<li>Ninguna</li>"
                            documentos_html = "".join(f"<li>{d}</li>" for d in documentos) or "<li>Ninguno</li>"

                            cuerpo = f"""
                            <p>Se han revocado los siguientes permisos:</p>
                            <b>Carpetas:</b>
                            <ul>{carpetas_html}</ul>
                            <b>Archivos:</b>
                            <ul>{documentos_html}</ul>
                            """
                            ok, msg = enviar_correo(
                                destinatario=email,
                                asunto="🚫 Permisos revocados",
                                cuerpo_html=cuerpo,
                                token=token
                            )
                            log_msg = f"Modo: {modo} / Carpetas: {carpetas} / Archivos: {documentos}"
                            registrar_log(usuario, "Permisos revocados", log_msg)
                            st.toast(f"📧 Notificación enviada a {usuario} / {email}" if ok else f"❌ Error con {usuario}: {msg}")

                        st.session_state[clave_anteriores] = list(nuevos)
                        st.session_state[clave_seleccion] = list(nuevos)

                        st.success("✅ Permisos de usuarios actualizados")
                        st.rerun()
                    else:
                        st.toast("❌ Error al actualizar permisos")