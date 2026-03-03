# models/sepomex_model.py
from __future__ import annotations

from typing import List, Dict, Any
from database.conexion import obtener_conexion


def get_sepomex_ciudades_catalogo_rows(limit: int = 200000) -> List[Dict[str, Any]]:
    """
    catálogo para ui: d_codigo, d_asenta, d_estado, d_ciudad
    trae combos únicos para mostrar en select.
    """
    cn = obtener_conexion()
    try:
        cur = cn.cursor()
        sql = """
            select distinct
                d_codigo,
                d_asenta,
                d_estado,
                d_ciudad
            from sepomex_cp
            where d_ciudad is not null and trim(d_ciudad) <> ''
              and d_estado is not null and trim(d_estado) <> ''
              and d_codigo is not null and trim(d_codigo) <> ''
              and d_asenta is not null and trim(d_asenta) <> ''
            order by d_estado, d_ciudad, d_codigo, d_asenta
        """
        cur.execute(sql,)
        rows = cur.fetchall()

        out: List[Dict[str, Any]] = []
        for d_codigo, d_asenta, d_estado, d_ciudad in rows:
            out.append(
                {
                    "d_codigo": str(d_codigo).strip(),
                    "d_asenta": str(d_asenta).strip(),
                    "d_estado": str(d_estado).strip(),
                    "d_ciudad": str(d_ciudad).strip(),
                }
            )
        return out
    finally:
        try:
            cn.close()
        except Exception:
            pass