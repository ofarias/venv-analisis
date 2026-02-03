import streamlit as st
import os
from database.conexion import obtener_conexion
from logs.logger import registrar_log
from utils.envio_correo import *
from models.usuario_model import *
import pandas as pd
os.makedirs("static/tipos", exist_ok=True)

def obtener_usuarios_tipo(tipo_id):
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("SELECT username from usuarios_roles ur left join roles r on r.id = ur.id_rol WHERE r.nombre = (Select nombre from tipos_documento where id = %s)", (tipo_id,))
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows]

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
        cursor.execute("DELETE FROM usuarios_roles WHERE id_rol = %s", (tipo_id,))
        for u in usuarios:
            cursor.execute(
                "INSERT INTO usuarios_roles (id_rol, username) VALUES (%s, %s)",
                (tipo_id, u)
            )
        conn.commit()
        return True
    except Exception as e:
        print("❌ Error actualizando usuarios:", e)
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
        cursor.execute("DELETE FROM tipos_documento WHERE id = %s", (id,))
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

    tipos = obtener_tipos()
    tipos_dict = {t["id"]: t["nombre"] for t in tipos}
    tipos_jerarquia = construir_jerarquia(tipos)
    tipos_by_id = { t['id']: t for t, _ in tipos_jerarquia }
    rutas = { tipo_id: get_logical_type_path(tipo_id) for tipo_id in tipos_by_id.keys() }

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
                opciones_padre = {
                    rutas[tid]: tid
                    for tid in rutas
                    if tid != tipo['id']
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

            if st.button("Guardar usuarios", key=f"guardar_usuarios_{tipo['id']}"):
                anteriores = set(st.session_state[clave_anteriores])
                nuevos = set(seleccion)

                agregados = nuevos - anteriores
                eliminados = anteriores - nuevos

                if actualizar_usuarios_tipo(tipo['id'], seleccion):
                    ruta = get_logical_type_path(tipo['id'])
                    token = st.session_state["microsoft_token"]

                    for usuario in agregados:
                        email = obtener_usuario_por_username(usuario)
                        if not email:
                            st.toast(f"❌ Email no encontrado para {usuario}")
                            continue
                        email = email['email']
                        ok, msg = enviar_correo(
                            destinatario=email,
                            asunto="🔐 Permiso otorgado",
                            cuerpo_html=f"Se ha otorgado permiso a la carpeta: {ruta}",
                            token=token
                        )
                        st.toast(f"📧 Correo enviado a {usuario} / {email}" if ok else f"❌ Error con {usuario}: {msg}")

                    for usuario in eliminados:
                        email = obtener_usuario_por_username(usuario)
                        if not email:
                            st.toast(f"❌ Email no encontrado para {usuario}")
                            continue
                        email = email['email']
                        ok, msg = enviar_correo(
                            destinatario=email,
                            asunto="🚫 Permiso revocado",
                            cuerpo_html=f"Se ha retirado el acceso a la carpeta: {ruta}",
                            token=token
                        )
                        st.toast(f"📧 Notificación enviada a {usuario} / {email}" if ok else f"❌ Error con {usuario}: {msg}")

                    # Actualiza sesión para reflejar lo guardado
                    st.session_state[clave_anteriores] = list(nuevos)
                    st.session_state[clave_seleccion] = list(nuevos)

                    st.success("✅ Permisos de usuarios actualizados")
                    st.rerun()
                else:
                    st.toast("❌ Error al actualizar permisos")

####
            col_guardar, col_eliminar = st.columns([1, 1])
            with col_guardar:
                if st.button("Guardar", key=f"guardar_{tipo['id']}"):
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
