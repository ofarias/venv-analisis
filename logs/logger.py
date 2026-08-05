import os
from datetime import datetime

def registrar_log(usuario, accion, afectado):
    os.makedirs("logs", exist_ok=True)  # Crea la carpeta si no existe

    with open("logs/log_usuarios.txt", "a") as file:
        file.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {usuario} -> {accion}: {afectado}\n")

    # el .txt queda como respaldo; login_activity (MySQL) es la fuente para el
    # KPI de uso — si la BD falla, no debe tumbar el login/la acción que
    # disparó este registro, por eso nunca propaga la excepción
    try:
        from database.conexion import obtener_conexion

        conn = obtener_conexion()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO login_activity (usuario, accion, detalle, creado_en) VALUES (%s, %s, %s, %s)",
                (str(usuario), str(accion), str(afectado) if afectado is not None else None, datetime.now()),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass
