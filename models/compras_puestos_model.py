import pandas as pd
from database.conexion import obtener_conexion


def obtener_puestos_model() -> pd.DataFrame:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            select
                p.id_puesto, p.nombre, p.descripcion, p.activo, p.created_at, p.updated_at,
                GROUP_CONCAT(u.nombre ORDER BY u.nombre SEPARATOR ', ') as usuarios_nombres
            from compras_puestos p
            left join compras_puestos_usuarios pu on pu.id_puesto = p.id_puesto
            left join usuarios u on u.id = pu.usuario_id
            group by p.id_puesto
            order by p.nombre
            """
        )
        rows = cur.fetchall() or []
        if not rows:
            return pd.DataFrame(columns=[
                "id_puesto", "nombre", "descripcion", "activo", "created_at", "updated_at", "usuarios_nombres",
            ])
        return pd.DataFrame(rows)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def existe_puesto_model(nombre: str, id_excluir: int | None = None) -> bool:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)
        sql = "select count(*) as total from compras_puestos where upper(trim(nombre)) = upper(trim(%s))"
        params = [nombre]
        if id_excluir is not None:
            sql += " and id_puesto <> %s"
            params.append(int(id_excluir))
        cur.execute(sql, tuple(params))
        row = cur.fetchone() or {}
        return int(row.get("total", 0) or 0) > 0
    finally:
        try:
            conn.close()
        except Exception:
            pass


def crear_puesto_model(nombre: str, descripcion: str | None) -> int | None:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute(
            "insert into compras_puestos (nombre, descripcion, activo) values (%s, %s, 1)",
            (str(nombre).strip(), str(descripcion).strip() if descripcion else None),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def actualizar_puesto_model(id_puesto: int, nombre: str, descripcion: str | None) -> bool:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute(
            "update compras_puestos set nombre = %s, descripcion = %s where id_puesto = %s",
            (str(nombre).strip(), str(descripcion).strip() if descripcion else None, int(id_puesto)),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def cambiar_estatus_puesto_model(id_puesto: int, activo: int) -> bool:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("update compras_puestos set activo = %s where id_puesto = %s", (int(activo), int(id_puesto)))
        conn.commit()
        return True
    finally:
        conn.close()


def obtener_usuarios_de_puesto_model(id_puesto: int) -> list[int]:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("select usuario_id from compras_puestos_usuarios where id_puesto = %s", (int(id_puesto),))
        return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()


def obtener_puestos_de_usuario_model(usuario_id: int) -> list[int]:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute(
            "select pu.id_puesto from compras_puestos_usuarios pu "
            "join compras_puestos p on p.id_puesto = pu.id_puesto "
            "where pu.usuario_id = %s and p.activo = 1",
            (int(usuario_id),),
        )
        return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()


def asignar_usuarios_puesto_model(id_puesto: int, usuario_ids: list[int]) -> bool:
    """Reemplaza el set completo de usuarios asignados a un puesto."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("delete from compras_puestos_usuarios where id_puesto = %s", (int(id_puesto),))
        if usuario_ids:
            cur.executemany(
                "insert into compras_puestos_usuarios (id_puesto, usuario_id) values (%s, %s)",
                [(int(id_puesto), int(uid)) for uid in usuario_ids],
            )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


def obtener_correos_de_puesto_model(id_puesto: int) -> list[str]:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute(
            "select u.email from compras_puestos_usuarios pu "
            "join usuarios u on u.id = pu.usuario_id "
            "where pu.id_puesto = %s and u.email is not null and u.email <> ''",
            (int(id_puesto),),
        )
        return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()
