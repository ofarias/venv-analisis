from database.conexion import obtener_conexion
import json
import base64

def guardar_documento(nombre, descripcion, tipo_id, contenido, nombre_archivo, extension, version, subido_por, fecha_subida, permisos, usuarios):
    try:
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO documentos
            (titulo, descripcion, tipo_id, version_actual, creado_por, fecha_creacion, estatus)
            VALUES (%s, %s, %s, %s, %s, %s, 'Activo')
        """, (nombre, descripcion, tipo_id, version, subido_por, fecha_subida))

        documento_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO versiones_documento
            (documento_id, version, archivo, extension, tamaño, subido_por, fecha_subida, comentario, nombre_archivo)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (documento_id, version, contenido, extension, len(contenido), subido_por, fecha_subida, "Versión inicial", nombre_archivo))

        for usuario in usuarios:
            puede_editar = int("Editar" in permisos)
            puede_eliminar = int("Eliminar" in permisos)

            cursor.execute("""
                INSERT INTO permisos_documento (documento_id, username, puede_editar, puede_eliminar)
                VALUES (%s, %s, %s, %s)
            """, (documento_id, usuario, puede_editar, puede_eliminar))
        
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"❌ Error al guardar documento: {e}")
        return False

def obtener_tipos_documento():
    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM tipos_documento")
    tipos = cursor.fetchall()
    conn.close()
    return tipos

def obtener_documentos():
    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT d.*, t.nombre AS tipo
        FROM documentos d
        JOIN tipos_documento t ON d.tipo_id = t.id
        ORDER BY d.fecha_creacion DESC
    """)
    documentos = cursor.fetchall()
    conn.close()
    return documentos

def obtener_usuarios():
    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT username FROM usuarios WHERE estatus = 'Activo'")
    usuarios = cursor.fetchall()
    conn.close()
    return usuarios

def obtener_documentos_por_usuario(username, roles_usuario=None, tipo=None, fecha_ini=None, fecha_fin=None, documento_id=None):
    """Documentos visibles para el usuario: por permiso explícito (permisos_documento)
    O por rol (tipos_documento.nombre in roles_usuario), igual que en el módulo Navegar."""
    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)

    roles_usuario = roles_usuario or []
    roles_placeholders = ",".join(["%s"] * len(roles_usuario)) if roles_usuario else "NULL"

    query = f"""SELECT
                    d.id AS docID, d.*, t.nombre AS tipo,
                    p.puede_editar, p.puede_eliminar,
                    v.extension
                FROM documentos d
                JOIN tipos_documento t ON t.id = d.tipo_id
                LEFT JOIN permisos_documento p ON p.documento_id = d.id AND p.username = %s
                LEFT JOIN versiones_documento v
                    ON v.documento_id = d.id
                    AND v.version = (
                        SELECT MAX(v2.version)
                        FROM versiones_documento v2
                        WHERE v2.documento_id = d.id
                    )
                WHERE (p.username IS NOT NULL OR t.nombre IN ({roles_placeholders}))"""
    params = [username, *roles_usuario]

    if tipo:
        query += " AND d.tipo_id = %s"
        params.append(tipo)
    if fecha_ini:
        query += " AND d.fecha_creacion >= %s"
        params.append(fecha_ini)
    if fecha_fin:
        query += " AND d.fecha_creacion <= %s"
        params.append(fecha_fin)
    if documento_id:
        query += " AND d.id = %s"
        params.append(documento_id)

    cursor.execute(query, params)

    docs = cursor.fetchall()
    conn.close()

    for doc in docs:
        permisos = ["Ver"]
        if doc.get("puede_editar"):
            permisos.append("Editar")
        if doc.get("puede_eliminar"):
            permisos.append("Eliminar")
        doc["permisos"] = permisos

    return docs


def obtener_archivo_actual(documento_id):
    """Trae el archivo (bytes) de la última versión de un documento, bajo demanda
    (solo se llama para el documento que el usuario tiene seleccionado)."""
    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT archivo, nombre_archivo, extension
        FROM versiones_documento
        WHERE documento_id = %s
        ORDER BY version DESC
        LIMIT 1
    """, (documento_id,))
    row = cursor.fetchone()
    conn.close()
    return row


def obtener_documentos_accesibles_resumen(username, roles_usuario=None):
    """Lista liviana (id, título, nombre_archivo) de los documentos que el usuario
    puede ver (por permiso explícito o por rol), para poblar el selector de búsqueda."""
    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)
    roles_usuario = roles_usuario or []
    roles_placeholders = ",".join(["%s"] * len(roles_usuario)) if roles_usuario else "NULL"
    cursor.execute(f"""
        SELECT d.id, d.titulo, vd.nombre_archivo
        FROM documentos d
        JOIN tipos_documento t ON t.id = d.tipo_id
        LEFT JOIN permisos_documento p ON p.documento_id = d.id AND p.username = %s
        LEFT JOIN versiones_documento vd
            ON vd.documento_id = d.id
            AND vd.version = (
                SELECT MAX(v2.version) FROM versiones_documento v2 WHERE v2.documento_id = d.id
            )
        WHERE (p.username IS NOT NULL OR t.nombre IN ({roles_placeholders}))
        ORDER BY d.titulo
    """, (username, *roles_usuario))
    filas = cursor.fetchall()
    conn.close()
    return filas


def actualizar_documento(documento_id, nuevo_titulo, nueva_descripcion, nuevo_tipo_id):
    try:
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE documentos
            SET titulo = %s,
                descripcion = %s,
                tipo_id = %s
            WHERE id = %s
        """, (nuevo_titulo, nueva_descripcion, nuevo_tipo_id, documento_id))
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"❌ Error al actualizar documento: {e}")
        return False
    
def eliminar_documento(documento_id):
    conn = obtener_conexion()
    cursor = conn.cursor()

    try:
        # Eliminar primero registros relacionados
        cursor.execute("DELETE FROM permisos_documento WHERE documento_id = %s", (documento_id,))
        cursor.execute("DELETE FROM versiones_documento WHERE documento_id = %s", (documento_id,))
        
        # Luego eliminar el documento
        cursor.execute("DELETE FROM documentos WHERE id = %s", (documento_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def obtener_documentos_por_tipo(tipo_id):
    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT d.id, d.titulo, d.descripcion, d.creado_por, d.fecha_creacion, d.estatus,
               vd.nombre_archivo, vd.tamaño, vd.extension, vd.fecha_subida, vd.archivo,
               vd.version AS version_actual, vd.comentario, vd.subido_por
        FROM documentos d
        JOIN (
            SELECT documento_id, MAX(version) AS ultima_version
            FROM versiones_documento
            GROUP BY documento_id
        ) ult ON d.id = ult.documento_id
        JOIN versiones_documento vd ON d.id = vd.documento_id AND vd.version = ult.ultima_version
        WHERE d.tipo_id = %s
        ORDER BY d.fecha_creacion DESC
    """, (tipo_id,))
    documentos = cursor.fetchall()
    conn.close()
    return documentos

def obtener_todos_los_documentos():
    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT d.*, t.nombre as tipo_nombre 
        FROM documentos d
        JOIN tipos_documento t ON d.tipo_id = t.id           
        ORDER BY d.fecha_creacion DESC
    """)
    documentos = cursor.fetchall()
    conn.close()
    return documentos

def registrar_documento_onedrive(titulo, descripcion, tipo_id, creado_por, archivo_bytes, nombre_archivo, extension, tamaño):
    conexion = obtener_conexion()
    try:
        with conexion.cursor() as cursor:
            # 1. Insertar en documentos
            cursor.execute("""
                INSERT INTO documentos (titulo, descripcion, tipo_id, creado_por)
                VALUES (%s, %s, %s, %s)
            """, (titulo, descripcion, tipo_id, creado_por))
            documento_id = cursor.lastrowid

            # 2. Insertar en versiones_documento
            cursor.execute("""
                INSERT INTO versiones_documento (documento_id, version, archivo, extension, tamaño, subido_por, comentario, nombre_archivo)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                documento_id,
                1,
                archivo_bytes,
                extension,
                tamaño,
                creado_por,
                "Versión inicial importada desde OneDrive",
                nombre_archivo
            ))

            # 3. Insertar en permisos_documento
            cursor.execute("""
                INSERT INTO permisos_documento (documento_id, username, puede_editar, puede_eliminar)
                VALUES (%s, %s, %s, %s)
            """, (documento_id, creado_por, 1, 1))

        conexion.commit()
        return documento_id

    except Exception as e:
        print("Error al registrar documento desde OneDrive:", e)
        conexion.rollback()
        return None

    finally:
        conexion.close()

def obtener_ultima_version_documento(documento_id):
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(version) FROM versiones_documento WHERE documento_id = %s", (documento_id,))
    resultado = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    return resultado

def registrar_nueva_version_documento(documento_id, version, archivo, extension, tamaño, subido_por, comentario, nombre_archivo):
    try:
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO versiones_documento (documento_id, version, archivo, extension, tamaño, subido_por, comentario, nombre_archivo)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (documento_id, version, archivo, extension, tamaño, subido_por, comentario, nombre_archivo))
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        st.error(f"❌ Error al registrar nueva versión: {e}")
        return False
    
def obtener_historial_versiones(documento_id):
    conexion = obtener_conexion()
    with conexion.cursor(dictionary=True) as cursor:
        cursor.execute("""
            SELECT version, archivo, extension, tamaño, subido_por, fecha_subida, nombre_archivo, comentario
            FROM versiones_documento
            WHERE documento_id = %s
            ORDER BY version DESC
        """, (documento_id,))
        return cursor.fetchall()
    
def obtener_ruta(documento_id, incluir_nombre_archivo=False):
    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)

    # 1) Obtenemos el tipo_id del documento
    cursor.execute("SELECT tipo_id, titulo FROM documentos WHERE id = %s", (documento_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return ""
    tipo_id = row["tipo_id"]
    nombre_archivo = row["titulo"] if incluir_nombre_archivo else None

    # 2) Subimos por la jerarquía de tipos_documento
    segments = []
    while tipo_id:
        cursor.execute(
            "SELECT nombre, padre_id FROM tipos_documento WHERE id = %s",
            (tipo_id,)
        )
        tr = cursor.fetchone()
        if not tr:
            break
        segments.insert(0, tr["nombre"])
        tipo_id = tr["padre_id"]

    conn.close()

    if incluir_nombre_archivo and nombre_archivo:
            segments.append(nombre_archivo)

    return "/".join(segments)


def obtener_tipos_documento_con_ruta():
    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)

    # Obtener todos los tipos y subtipos
    cursor.execute("SELECT id, nombre, padre_id FROM tipos_documento")
    tipos_raw = cursor.fetchall()
    conn.close()

    # Mapeo por ID para armar rutas completas
    mapa = {t["id"]: t for t in tipos_raw}
    for t in tipos_raw:
        ruta = []
        actual = t
        while actual:
            ruta.insert(0, actual["nombre"])
            actual = mapa.get(actual["padre_id"])
        t["ruta_completa"] = " / ".join(ruta)

    return sorted(tipos_raw, key=lambda x: x["ruta_completa"])


def obtener_permisos_documento(documento_id):
    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT * 
        FROM permisos_documento 
        WHERE documento_id = %s
    """, (documento_id,))
    perms = cursor.fetchall()
    conn.close()
    return perms


def actualizar_usuarios_asignados(documento_id, lista_usernames):
    conn = obtener_conexion()
    cursor = conn.cursor()

    # 1. Eliminar los usuarios actuales asignados al documento
    cursor.execute("DELETE FROM permisos_documento WHERE documento_id = %s", (documento_id,))

    # 2. Insertar los nuevos usuarios asignados
    for username in lista_usernames:
        cursor.execute("""
            INSERT INTO permisos_documento (documento_id, username, puede_editar, puede_eliminar)
            VALUES (%s, %s, %s, %s)
        """, (documento_id, username, 1, 1))

    conn.commit()
    conn.close()

def guardar_nueva_version(documento_id, archivo, nombre_archivo, extension, subido_por, comentario):
    conn = obtener_conexion()
    cursor = conn.cursor()

    # 1. Obtener la versión actual
    cursor.execute("SELECT version_actual FROM documentos WHERE id = %s", (documento_id,))
    row = cursor.fetchone()
    version_actual = row[0] if row else 1
    nueva_version = version_actual + 1

    # 2. Insertar en historial
    cursor.execute("""
        INSERT INTO versiones_documento 
        (documento_id, version, archivo, nombre_archivo, extension, subido_por, fecha_subida, comentario)
        VALUES (%s, %s, %s, %s, %s, %s, NOW(), %s)
    """, (documento_id, nueva_version, archivo, nombre_archivo, extension, subido_por, comentario))

    # 3. Actualizar documento principal
    cursor.execute("""
        UPDATE documentos 
        SET version_actual = %s  
        WHERE id = %s
    """, (nueva_version, documento_id))

    conn.commit()
    conn.close()