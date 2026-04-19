import pandas as pd
from database.conexion import obtener_conexion

def get_tipos_compra_model() -> pd.DataFrame:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)

        sql = """
            select
                id_tipo_compra,
                nombre,
                descripcion,
                activo,
                created_at,
                updated_at, 
                tipo_formulario
            from compras_tipos
            order by nombre
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
            ])

        return pd.DataFrame(rows)

    finally:
        try:
            conn.close()
        except Exception:
            pass


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
) -> bool:
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
        return True

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