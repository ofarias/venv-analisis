import pandas as pd
from database.conexion import obtener_conexion


# -------------------------
# departamentos
# -------------------------
def get_departamentos_model() -> pd.DataFrame:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)

        sql = """
            select
                id_departamento,
                nombre,
                descripcion,
                activo,
                created_at,
                updated_at
            from compras_departamentos
            order by nombre
        """
        cur.execute(sql)
        rows = cur.fetchall() or []

        if not rows:
            return pd.DataFrame(columns=[
                "id_departamento", "nombre", "descripcion",
                "activo", "created_at", "updated_at"
            ])

        return pd.DataFrame(rows)

    finally:
        conn.close()


def existe_departamento_model(nombre: str, id_excluir: int | None = None) -> bool:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)

        sql = """
            select count(*) as total
            from compras_departamentos
            where upper(trim(nombre)) = upper(trim(%s))
        """
        params = [nombre]

        if id_excluir is not None:
            sql += " and id_departamento <> %s"
            params.append(id_excluir)

        cur.execute(sql, tuple(params))
        row = cur.fetchone() or {}

        return int(row.get("total", 0) or 0) > 0

    finally:
        conn.close()


def crear_departamento_model(nombre: str, descripcion: str | None, activo: int = 1) -> bool:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()

        sql = """
            insert into compras_departamentos (
                nombre,
                descripcion,
                activo
            )
            values (%s, %s, %s)
        """
        cur.execute(
            sql,
            (
                str(nombre).strip(),
                str(descripcion).strip() if descripcion else None,
                int(activo),
            )
        )
        conn.commit()
        return True

    finally:
        conn.close()


def actualizar_departamento_model(
    id_departamento: int,
    nombre: str,
    descripcion: str | None,
    activo: int,
) -> bool:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()

        sql = """
            update compras_departamentos
            set
                nombre = %s,
                descripcion = %s,
                activo = %s
            where id_departamento = %s
        """
        cur.execute(
            sql,
            (
                str(nombre).strip(),
                str(descripcion).strip() if descripcion else None,
                int(activo),
                int(id_departamento),
            )
        )
        conn.commit()
        return True

    finally:
        conn.close()


def cambiar_estatus_departamento_model(id_departamento: int, activo: int) -> bool:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()

        sql = """
            update compras_departamentos
            set activo = %s
            where id_departamento = %s
        """
        cur.execute(sql, (int(activo), int(id_departamento)))
        conn.commit()
        return True

    finally:
        conn.close()


# -------------------------
# formas de pago
# -------------------------
def get_formas_pago_model() -> pd.DataFrame:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)

        sql = """
            select
                id_forma_pago,
                nombre,
                descripcion,
                activo,
                created_at,
                updated_at
            from compras_formas_pago
            order by nombre
        """
        cur.execute(sql)
        rows = cur.fetchall() or []

        if not rows:
            return pd.DataFrame(columns=[
                "id_forma_pago", "nombre", "descripcion",
                "activo", "created_at", "updated_at"
            ])

        return pd.DataFrame(rows)

    finally:
        conn.close()


def existe_forma_pago_model(nombre: str, id_excluir: int | None = None) -> bool:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)

        sql = """
            select count(*) as total
            from compras_formas_pago
            where upper(trim(nombre)) = upper(trim(%s))
        """
        params = [nombre]

        if id_excluir is not None:
            sql += " and id_forma_pago <> %s"
            params.append(id_excluir)

        cur.execute(sql, tuple(params))
        row = cur.fetchone() or {}

        return int(row.get("total", 0) or 0) > 0

    finally:
        conn.close()


def crear_forma_pago_model(nombre: str, descripcion: str | None, activo: int = 1) -> bool:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()

        sql = """
            insert into compras_formas_pago (
                nombre,
                descripcion,
                activo
            )
            values (%s, %s, %s)
        """
        cur.execute(
            sql,
            (
                str(nombre).strip(),
                str(descripcion).strip() if descripcion else None,
                int(activo),
            )
        )
        conn.commit()
        return True

    finally:
        conn.close()


def actualizar_forma_pago_model(
    id_forma_pago: int,
    nombre: str,
    descripcion: str | None,
    activo: int,
) -> bool:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()

        sql = """
            update compras_formas_pago
            set
                nombre = %s,
                descripcion = %s,
                activo = %s
            where id_forma_pago = %s
        """
        cur.execute(
            sql,
            (
                str(nombre).strip(),
                str(descripcion).strip() if descripcion else None,
                int(activo),
                int(id_forma_pago),
            )
        )
        conn.commit()
        return True

    finally:
        conn.close()


def cambiar_estatus_forma_pago_model(id_forma_pago: int, activo: int) -> bool:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()

        sql = """
            update compras_formas_pago
            set activo = %s
            where id_forma_pago = %s
        """
        cur.execute(sql, (int(activo), int(id_forma_pago)))
        conn.commit()
        return True

    finally:
        conn.close()