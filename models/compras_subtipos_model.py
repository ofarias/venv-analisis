import pandas as pd
from mysql.connector.errors import IntegrityError
from database.conexion import obtener_conexion


def obtener_subtipos_model(id_tipo_compra: int | None = None) -> pd.DataFrame:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)
        sql = """
            select
                s.id_subtipo, s.id_tipo_compra, t.nombre as tipo_compra, s.nombre, s.descripcion,
                s.activo, s.created_at, s.updated_at,
                GROUP_CONCAT(p.nombre ORDER BY p.nombre SEPARATOR ', ') as puestos_permitidos_nombres
            from compras_subtipos s
            join compras_tipos t on t.id_tipo_compra = s.id_tipo_compra
            left join compras_subtipos_puestos_permitidos sp on sp.id_subtipo = s.id_subtipo
            left join compras_puestos p on p.id_puesto = sp.id_puesto
            where 1 = 1
        """
        params: list = []
        if id_tipo_compra is not None:
            sql += " and s.id_tipo_compra = %s"
            params.append(int(id_tipo_compra))
        sql += " group by s.id_subtipo order by t.nombre, s.nombre"

        cur.execute(sql, tuple(params))
        rows = cur.fetchall() or []
        if not rows:
            return pd.DataFrame(columns=[
                "id_subtipo", "id_tipo_compra", "tipo_compra", "nombre", "descripcion",
                "activo", "created_at", "updated_at", "puestos_permitidos_nombres",
            ])
        return pd.DataFrame(rows)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def existe_subtipo_model(id_tipo_compra: int, nombre: str, id_excluir: int | None = None) -> bool:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)
        sql = (
            "select count(*) as total from compras_subtipos "
            "where id_tipo_compra = %s and upper(trim(nombre)) = upper(trim(%s))"
        )
        params = [int(id_tipo_compra), nombre]
        if id_excluir is not None:
            sql += " and id_subtipo <> %s"
            params.append(int(id_excluir))
        cur.execute(sql, tuple(params))
        row = cur.fetchone() or {}
        return int(row.get("total", 0) or 0) > 0
    finally:
        try:
            conn.close()
        except Exception:
            pass


def crear_subtipo_model(id_tipo_compra: int, nombre: str, descripcion: str | None) -> int | None:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute(
            "insert into compras_subtipos (id_tipo_compra, nombre, descripcion, activo) values (%s, %s, %s, 1)",
            (int(id_tipo_compra), str(nombre).strip(), str(descripcion).strip() if descripcion else None),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def actualizar_subtipo_model(id_subtipo: int, nombre: str, descripcion: str | None) -> bool:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute(
            "update compras_subtipos set nombre = %s, descripcion = %s where id_subtipo = %s",
            (str(nombre).strip(), str(descripcion).strip() if descripcion else None, int(id_subtipo)),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def cambiar_estatus_subtipo_model(id_subtipo: int, activo: int) -> bool:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("update compras_subtipos set activo = %s where id_subtipo = %s", (int(activo), int(id_subtipo)))
        conn.commit()
        return True
    finally:
        conn.close()


def eliminar_subtipo_model(id_subtipo: int) -> tuple[bool, str]:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("delete from compras_subtipos_puestos_permitidos where id_subtipo = %s", (int(id_subtipo),))
        cur.execute("delete from compras_subtipos where id_subtipo = %s", (int(id_subtipo),))
        conn.commit()
        return True, "subtipo eliminado correctamente."
    except IntegrityError:
        conn.rollback()
        return False, "no se puede eliminar: hay solicitudes de compra que usan este subtipo — desactívalo en vez de eliminarlo."
    finally:
        conn.close()


def obtener_puestos_permitidos_subtipo_model(id_subtipo: int) -> list[int]:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute(
            "select id_puesto from compras_subtipos_puestos_permitidos where id_subtipo = %s",
            (int(id_subtipo),),
        )
        return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()


def guardar_puestos_permitidos_subtipo_model(id_subtipo: int, puesto_ids: list[int]) -> bool:
    """Reemplaza la lista completa de puestos permitidos para un subtipo —
    vacío significa "cualquiera puede solicitarlo" (sin restricción), mismo
    criterio que el resto de la app."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute(
            "delete from compras_subtipos_puestos_permitidos where id_subtipo = %s", (int(id_subtipo),),
        )
        if puesto_ids:
            cur.executemany(
                "insert into compras_subtipos_puestos_permitidos (id_subtipo, id_puesto) values (%s, %s)",
                [(int(id_subtipo), int(pid)) for pid in puesto_ids],
            )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


def obtener_subtipos_activos_para_usuario_model(id_tipo_compra: int, usuario_id: int | None) -> list[dict]:
    """Subtipos activos de un tipo de compra que este usuario puede usar al
    capturar una solicitud — mismo criterio que
    get_tipos_compra_activos_para_usuario_model: sin puestos asignados =
    visible para cualquiera; con puesto(s) asignado(s), solo quien
    pertenezca a alguno de ellos."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            select s.id_subtipo, s.nombre, s.descripcion
            from compras_subtipos s
            where s.id_tipo_compra = %s and s.activo = 1
              and (
                not exists (
                    select 1 from compras_subtipos_puestos_permitidos sp where sp.id_subtipo = s.id_subtipo
                )
                or exists (
                    select 1 from compras_subtipos_puestos_permitidos sp
                    join compras_puestos_usuarios pu on pu.id_puesto = sp.id_puesto
                    where sp.id_subtipo = s.id_subtipo and pu.usuario_id = %s
                )
              )
            order by s.nombre
            """,
            (int(id_tipo_compra), usuario_id),
        )
        return cur.fetchall() or []
    finally:
        try:
            conn.close()
        except Exception:
            pass
