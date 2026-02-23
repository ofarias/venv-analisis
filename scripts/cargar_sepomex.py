# scripts/cargar_sepomex.py
from __future__ import annotations

import csv
from typing import Iterable, List, Tuple
from database.conexion import obtener_conexion


COLS = [
    "d_codigo",
    "d_asenta",
    "d_tipo_asenta",
    "d_mnpio",
    "d_estado",
    "d_ciudad",
    "d_cp",
    "c_estado",
    "c_oficina",
    "c_cp",
    "c_tipo_asenta",
    "c_mnpio",
    "id_asenta_cpcons",
    "d_zona",
    "c_cve_ciudad",
]

INSERT_SQL = """
insert into sepomex_cp (
  d_codigo, d_asenta, d_tipo_asenta, d_mnpio, d_estado, d_ciudad,
  d_cp, c_estado, c_oficina, c_cp, c_tipo_asenta, c_mnpio,
  id_asenta_cpcons, d_zona, c_cve_ciudad
) values (
  %s,%s,%s,%s,%s,%s,
  %s,%s,%s,%s,%s,%s,
  %s,%s,%s
)
"""

def _norm(s: str) -> str:
    if s is None:
        return ""
    return str(s).strip()

def _chunks(it: Iterable[Tuple[str, ...]], size: int) -> Iterable[List[Tuple[str, ...]]]:
    batch: List[Tuple[str, ...]] = []
    for x in it:
        batch.append(x)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch

def iter_rows_txt(path: str):
    # el txt sepomex suele venir en latin-1 / cp1252
    # si tu archivo viene en utf-8, cambia encoding="utf-8"
    with open(path, "r", encoding="latin-1", newline="") as f:
        reader = csv.reader(f, delimiter="|")
        for row in reader:
            if not row:
                continue
            # algunos archivos traen columnas extra al final; recortamos a 15
            row = (row + [""] * 15)[:15]
            yield tuple(_norm(x) for x in row)

def cargar(path_txt: str, batch_size: int = 5000):
    con = obtener_conexion()
    try:
        cur = con.cursor()
        inserted = 0
        for batch in _chunks(iter_rows_txt(path_txt), batch_size):
            cur.executemany(INSERT_SQL, batch)
            con.commit()
            inserted += len(batch)
            print(f"insertados: {inserted}")
        print(f"listo. total insertados: {inserted}")
    finally:
        try:
            con.close()
        except Exception:
            pass

if __name__ == "__main__":
    # ejemplo: python scripts/cargar_sepomex.py /ruta/CPdescarga.txt
    import sys
    if len(sys.argv) < 2:
        raise SystemExit("uso: python scripts/cargar_sepomex.py scripts/CPdescarga.txt")
    cargar(sys.argv[1])
