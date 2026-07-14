from __future__ import annotations

from typing import Optional

import pandas as pd

from database.conexion import obtener_conexion


# ── cargas ───────────────────────────────────────────────────────────────────

def insertar_carga_presupuesto_finanzas_model(
    nombre_archivo: str,
    hoja_origen: Optional[str],
    anio: int,
    version: Optional[str],
    comentarios: Optional[str],
    usuario_id: int,
) -> int:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            insert into presupuesto_finanzas_cargas
                (nombre_archivo, hoja_origen, anio, version, comentarios, usuario_id)
            values (%s, %s, %s, %s, %s, %s)
            """,
            (
                str(nombre_archivo).strip(),
                str(hoja_origen).strip() if hoja_origen else None,
                int(anio),
                str(version).strip() if version else None,
                str(comentarios).strip() if comentarios else None,
                int(usuario_id),
            ),
        )
        conn.commit()
        return int(cur.lastrowid or 0)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def actualizar_total_filas_carga_presupuesto_finanzas_model(id_carga: int, total_filas: int) -> None:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute(
            "update presupuesto_finanzas_cargas set total_filas = %s, updated_at = current_timestamp where id_carga = %s",
            (int(total_filas), int(id_carga)),
        )
        conn.commit()
    finally:
        try:
            conn.close()
        except Exception:
            pass


def obtener_cargas_presupuesto_finanzas_model(
    anio: Optional[int] = None,
    usuario_id: Optional[int] = None,
    limit: int = 100,
) -> pd.DataFrame:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)
        sql = """
            select id_carga, nombre_archivo, hoja_origen, anio, version, estatus,
                   comentarios, total_filas, usuario_id, created_at, updated_at
            from presupuesto_finanzas_cargas
            where 1 = 1
        """
        params: list = []
        if usuario_id is not None and int(usuario_id) > 0:
            sql += " and usuario_id = %s"
            params.append(int(usuario_id))
        if anio is not None:
            sql += " and anio = %s"
            params.append(int(anio))
        sql += " order by id_carga desc limit %s"
        params.append(int(limit))

        cur.execute(sql, tuple(params))
        rows = cur.fetchall() or []
        if not rows:
            return pd.DataFrame(columns=[
                "id_carga", "nombre_archivo", "hoja_origen", "anio", "version",
                "estatus", "comentarios", "total_filas", "usuario_id",
                "created_at", "updated_at",
            ])
        return pd.DataFrame(rows)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def eliminar_carga_presupuesto_finanzas_model(id_carga: int) -> bool:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("delete from presupuesto_finanzas_cargas where id_carga = %s", (int(id_carga),))
        conn.commit()
        return True
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ── detalle ──────────────────────────────────────────────────────────────────

def insertar_presupuesto_finanzas_desde_df_model(
    id_carga: int,
    usuario_id: int,
    df: pd.DataFrame,
) -> int:
    if df is None or df.empty:
        return 0

    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        sql = """
            insert into presupuesto_finanzas (
                id_carga, codigo, fila_excel, anio, mes,
                clave_cliente, nombre_cliente, clave_producto_sku, producto,
                area, vendedor, precio_unitario_dolares, tipo,
                volumen, pu, dolares, usuario_id
            ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """
        registros = [
            (
                int(id_carga),
                int(row.get("codigo") or 0) or None,
                int(row.get("fila_excel") or 0) or None,
                int(row.get("anio") or 0),
                int(row.get("mes") or 0),
                str(row.get("clave_cliente") or "").strip() or None,
                str(row.get("nombre_cliente") or "").strip() or None,
                str(row.get("clave_producto_sku") or "").strip() or None,
                str(row.get("producto") or "").strip() or None,
                str(row.get("area") or "").strip() or None,
                str(row.get("vendedor") or "").strip() or None,
                float(row.get("precio_unitario_dolares") or 0),
                str(row.get("tipo") or "").strip() or None,
                float(row.get("volumen") or 0),
                float(row.get("pu") or 0),
                float(row.get("dolares") or 0),
                int(usuario_id),
            )
            for _, row in df.iterrows()
        ]
        cur.executemany(sql, registros)
        conn.commit()
        return len(registros)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def actualizar_clave_producto_sku_model(id_carga: int, mapa: dict[str, str]) -> int:
    """Corrige clave_producto_sku de una carga usando un mapa {codigo_actual: codigo_correcto}."""
    if not mapa:
        return 0
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        actualizados = 0
        for actual, correcto in mapa.items():
            if not actual or not correcto or actual == correcto:
                continue
            cur.execute(
                "update presupuesto_finanzas set clave_producto_sku = %s "
                "where id_carga = %s and clave_producto_sku = %s",
                (correcto, int(id_carga), actual),
            )
            actualizados += cur.rowcount
        conn.commit()
        return actualizados
    finally:
        try:
            conn.close()
        except Exception:
            pass


def obtener_presupuesto_finanzas_model(
    id_carga: int,
    vendedores: Optional[list[str]] = None,
    clientes: Optional[list[str]] = None,
    claves_producto: Optional[list[str]] = None,
    meses: Optional[list[int]] = None,
    anios: Optional[list[int]] = None,
    areas: Optional[list[str]] = None,
) -> pd.DataFrame:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)
        sql = "select * from presupuesto_finanzas where id_carga = %s"
        params: list = [int(id_carga)]

        def _in_clause(campo: str, valores: Optional[list]) -> None:
            nonlocal sql
            if valores:
                placeholders = ", ".join(["%s"] * len(valores))
                sql += f" and {campo} in ({placeholders})"
                params.extend(valores)

        _in_clause("vendedor", vendedores)
        _in_clause("nombre_cliente", clientes)
        _in_clause("clave_producto_sku", claves_producto)
        _in_clause("mes", meses)
        _in_clause("anio", anios)
        _in_clause("area", areas)

        sql += " order by vendedor, nombre_cliente, clave_producto_sku, mes"
        cur.execute(sql, tuple(params))
        rows = cur.fetchall() or []
        if not rows:
            return pd.DataFrame(columns=[
                "id", "id_carga", "codigo", "fila_excel", "anio", "mes",
                "clave_cliente", "nombre_cliente", "clave_producto_sku", "producto",
                "area", "vendedor", "precio_unitario_dolares", "tipo",
                "volumen", "pu", "dolares", "usuario_id", "created_at",
            ])
        return pd.DataFrame(rows)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def obtener_presupuesto_finanzas_resumen_por_anio_model(anio: int) -> pd.DataFrame:
    """
    Presupuesto de finanzas agregado por clave_producto_sku × mes de todas las
    cargas activas del año — usado en el comparativo Real vs Forecast.
    """
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            select
                pf.clave_producto_sku as cve_prod,
                pf.mes,
                sum(pf.volumen) as total_volumen,
                sum(pf.dolares) as total_dolares,
                substring_index(group_concat(pf.producto separator '||'), '||', 1) as producto_excel
            from presupuesto_finanzas pf
            inner join presupuesto_finanzas_cargas c on c.id_carga = pf.id_carga
            where pf.anio = %s and c.estatus = 'activo' and pf.clave_producto_sku is not null
            group by pf.clave_producto_sku, pf.mes
            """,
            (int(anio),),
        )
        rows = cur.fetchall() or []
        if not rows:
            return pd.DataFrame(columns=["cve_prod", "mes", "total_volumen", "total_dolares", "producto_excel"])
        return pd.DataFrame(rows)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def obtener_opciones_filtro_presupuesto_finanzas_model(id_carga: int) -> dict[str, list]:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        opciones: dict[str, list] = {}
        campos = {
            "vendedores": "vendedor",
            "clientes": "nombre_cliente",
            "claves_producto": "clave_producto_sku",
            "meses": "mes",
            "anios": "anio",
            "areas": "area",
        }
        for clave, campo in campos.items():
            cur.execute(
                f"select distinct {campo} from presupuesto_finanzas where id_carga = %s and {campo} is not null order by {campo}",
                (int(id_carga),),
            )
            opciones[clave] = [r[0] for r in cur.fetchall() or []]
        return opciones
    finally:
        try:
            conn.close()
        except Exception:
            pass
