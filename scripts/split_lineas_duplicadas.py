"""Separa en líneas independientes las filas duplicadas que se acumularon en
presupuesto_ventas / presupuesto_compras antes de existir `linea_uid`.

Contexto: la captura manual identificaba un renglón solo por
(company, cliente_excel, codigo_origen, producto_excel); como el índice único
incluye company/codigo_origen y MySQL trata los NULL como distintos, recapturar
el mismo producto insertaba filas paralelas que `_construir_pivot` sumaba al
recargar. Con `linea_uid` cada línea es independiente; este script le asigna un
uid a las filas duplicadas que ya están en la BD para que se muestren separadas.

Regla: dentro de cada identidad
(id_carga, seccion, region, company, cliente_excel, codigo_origen, producto_excel),
si algún mes tiene más de una fila, a cada fila con nº de ocurrencia >= 2 (por mes,
ordenando por id_presupuesto) se le pone linea_uid = f"d{min_id}_{slot}"
(mismo slot en todos los meses = misma línea). El slot 1 se queda en '' (línea 1).
Además crea la fila correspondiente en *_lineas (estatus 'captura').

Uso:  python scripts/split_lineas_duplicadas.py [--commit]
Sin --commit solo reporta (dry-run).
"""
from __future__ import annotations

import sys
from collections import defaultdict

import mysql.connector

DB = dict(host="localhost", user="root", password="genseg01", database="documentos")

TABLAS = [
    ("presupuesto_ventas", "presupuesto_ventas_lineas"),
    ("presupuesto_compras", "presupuesto_compras_lineas"),
]

IDENT = ("id_carga", "seccion", "region", "company", "cliente_excel",
         "codigo_origen", "producto_excel")


def _norm(v) -> str:
    return "" if v is None else str(v)


def procesar_tabla(cur, tabla: str, tabla_lineas: str, commit: bool) -> None:
    cur.execute(
        f"select id_presupuesto, mes, "
        f"{', '.join(IDENT)}, linea_uid "
        f"from {tabla} order by id_presupuesto"
    )
    filas = cur.fetchall()

    # agrupar por identidad
    por_identidad: dict[tuple, list[dict]] = defaultdict(list)
    for r in filas:
        ident = tuple(_norm(r[c]) for c in IDENT)
        por_identidad[ident].append(r)

    updates: list[tuple[str, int]] = []          # (linea_uid, id_presupuesto)
    lineas_nuevas: dict[tuple, str] = {}          # ident -> set de uids (via dict)
    lineas_por_uid: dict[str, tuple] = {}
    identidades_afectadas = 0

    for ident, rows in por_identidad.items():
        # ¿algún mes con más de una fila?
        por_mes: dict[int, list[dict]] = defaultdict(list)
        for r in rows:
            por_mes[int(r["mes"])].append(r)
        if not any(len(v) > 1 for v in por_mes.values()):
            continue

        identidades_afectadas += 1
        min_id = min(int(r["id_presupuesto"]) for r in rows)

        for mes, rs in por_mes.items():
            rs.sort(key=lambda r: int(r["id_presupuesto"]))
            for slot, r in enumerate(rs, start=1):
                if slot == 1:
                    continue
                uid = f"d{min_id}_{slot}"
                if _norm(r["linea_uid"]) != uid:
                    updates.append((uid, int(r["id_presupuesto"])))
                lineas_por_uid[uid] = ident

    print(f"\n=== {tabla} ===")
    print(f"identidades con duplicados: {identidades_afectadas}")
    print(f"filas a reasignar a una línea nueva: {len(updates)}")
    print(f"líneas nuevas (linea_uid): {len(lineas_por_uid)}")
    for uid, ident in sorted(lineas_por_uid.items()):
        d = dict(zip(IDENT, ident))
        cli = d["cliente_excel"] or "(sin cliente)"
        print(f"  {uid:16}  carga {d['id_carga']:>4}  {d['seccion'] or '-'}/{d['region'] or '-'}  "
              f"{cli[:34]:34}  {d['producto_excel'][:28]}")

    if not commit:
        print("  (dry-run — nada se escribió; usa --commit para aplicar)")
        return

    for uid, id_pres in updates:
        cur.execute(
            f"update {tabla} set linea_uid = %s where id_presupuesto = %s",
            (uid, id_pres),
        )

    for uid, ident in lineas_por_uid.items():
        d = dict(zip(IDENT, ident))
        cur.execute(
            f"""insert into {tabla_lineas}
                (id_carga, company, cliente_excel, codigo_origen, producto_excel, linea_uid, estatus)
                values (%s, %s, %s, %s, %s, %s, 'captura')
                on duplicate key update linea_uid = linea_uid""",
            (
                int(d["id_carga"]),
                d["company"] or None,
                d["cliente_excel"] or None,
                d["codigo_origen"] or None,
                d["producto_excel"],
                uid,
            ),
        )

    print(f"  aplicado: {len(updates)} updates, {len(lineas_por_uid)} líneas de autorización")


def main() -> None:
    commit = "--commit" in sys.argv
    conn = mysql.connector.connect(**DB)
    try:
        cur = conn.cursor(dictionary=True)
        for tabla, tabla_lineas in TABLAS:
            procesar_tabla(cur, tabla, tabla_lineas, commit)
        if commit:
            conn.commit()
            print("\nCOMMIT hecho.")
        else:
            print("\nDRY-RUN — sin cambios. Corre con --commit para aplicar.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
