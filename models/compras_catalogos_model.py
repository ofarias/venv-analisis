import pandas as pd
from database.conexion import obtener_conexion

def get_tipos_compra_model() -> pd.DataFrame:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)

        sql = """
            select
                t.id_tipo_compra,
                t.nombre,
                t.descripcion,
                t.activo,
                t.created_at,
                t.updated_at,
                t.tipo_formulario,
                GROUP_CONCAT(pu.nombre ORDER BY pu.nombre SEPARATOR ', ') AS puestos_permitidos_nombres
            from compras_tipos t
            left join compras_tipos_puestos_permitidos p on p.id_tipo_compra = t.id_tipo_compra
            left join compras_puestos pu on pu.id_puesto = p.id_puesto
            group by t.id_tipo_compra
            order by t.nombre
        """
        cur.execute(sql)
        rows = cur.fetchall() or []

        if not rows:
            return pd.DataFrame(columns=[
                "id_tipo_compra",
                "nombre",
                "descripcion",
                "activo",
                "created_at",
                "updated_at",
                "puestos_permitidos_nombres",
            ])

        return pd.DataFrame(rows)

    finally:
        try:
            conn.close()
        except Exception:
            pass


def obtener_puestos_permitidos_tipo_model(id_tipo_compra: int) -> list[int]:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id_puesto FROM compras_tipos_puestos_permitidos WHERE id_tipo_compra = %s",
            (int(id_tipo_compra),),
        )
        return [row[0] for row in cur.fetchall()]

    finally:
        conn.close()


def guardar_puestos_permitidos_tipo_model(id_tipo_compra: int, puesto_ids: list[int]) -> bool:
    """Reemplaza la lista completa de puestos permitidos para un tipo de
    compra — vacío significa "cualquiera puede crear este tipo" (sin
    restricción), mismo criterio que el resto de la app."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM compras_tipos_puestos_permitidos WHERE id_tipo_compra = %s",
            (int(id_tipo_compra),),
        )
        if puesto_ids:
            cur.executemany(
                "INSERT INTO compras_tipos_puestos_permitidos (id_tipo_compra, id_puesto) VALUES (%s, %s)",
                [(int(id_tipo_compra), int(pid)) for pid in puesto_ids],
            )
        conn.commit()
        return True

    except Exception:
        conn.rollback()
        return False

    finally:
        conn.close()


def existe_tipo_compra_model(nombre: str, id_excluir: int | None = None) -> bool:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)

        sql = """
            select count(*) as total
            from compras_tipos
            where upper(trim(nombre)) = upper(trim(%s))
        """
        params = [nombre]

        if id_excluir is not None:
            sql += " and id_tipo_compra <> %s"
            params.append(id_excluir)

        cur.execute(sql, tuple(params))
        row = cur.fetchone() or {}

        return int(row.get("total", 0) or 0) > 0

    finally:
        try:
            conn.close()
        except Exception:
            pass


def crear_tipo_compra_model(
    nombre: str,
    descripcion: str | None,
    tipo_formulario: str,
    activo: int = 1,
) -> int | None:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()

        sql = """
            insert into compras_tipos (
                nombre,
                descripcion,
                tipo_formulario,
                activo
            )
            values (%s, %s, %s, %s)
        """
        cur.execute(
            sql,
            (
                str(nombre).strip(),
                str(descripcion).strip() if descripcion else None,
                str(tipo_formulario).strip(),
                int(activo),
            )
        )
        conn.commit()
        return int(cur.lastrowid)

    finally:
        conn.close()


def actualizar_tipo_compra_model(
    id_tipo_compra: int,
    nombre: str,
    descripcion: str | None,
    tipo_formulario: str,
    activo: int,
) -> bool:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()

        sql = """
            update compras_tipos
            set
                nombre = %s,
                descripcion = %s,
                tipo_formulario = %s,
                activo = %s
            where id_tipo_compra = %s
        """
        cur.execute(
            sql,
            (
                str(nombre).strip(),
                str(descripcion).strip() if descripcion else None,
                str(tipo_formulario).strip(),
                int(activo),
                int(id_tipo_compra),
            )
        )
        conn.commit()
        return True

    finally:
        conn.close()

def cambiar_estatus_tipo_compra_model(id_tipo_compra: int, activo: int) -> bool:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()

        sql = """
            update compras_tipos
            set activo = %s
            where id_tipo_compra = %s
        """
        cur.execute(sql, (int(activo), int(id_tipo_compra)))
        conn.commit()
        return True

    finally:
        try:
            conn.close()
        except Exception:
            pass