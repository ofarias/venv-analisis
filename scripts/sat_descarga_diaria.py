# scripts/sat_descarga_diaria.py
"""
Job diario (systemd timer) para la Descarga Masiva de CFDI recibidos del SAT.

Reusa exactamente la misma lógica que el botón manual de la vista de Streamlit
(controllers/sat_cfdi_controller.py), pasando secrets=None para que
utils/sat_client.py lea la FIEL directo de .streamlit/secrets.toml (fuera de
un proceso streamlit, st.secrets no es confiable en este repo).

Uso:
    venv/bin/python3 scripts/sat_descarga_diaria.py                 # día anterior, I/E/P
    venv/bin/python3 scripts/sat_descarga_diaria.py --desde 2026-09-01 --hasta 2026-09-10
    venv/bin/python3 scripts/sat_descarga_diaria.py --tipos I E
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta

# bootstrap: al correr "python3 scripts/sat_descarga_diaria.py" desde la raíz
# del repo, sys.path[0] queda apuntando a scripts/, no a la raíz -> hay que
# agregar la raíz a mano para que "from controllers...." funcione standalone.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from controllers.sat_cfdi_controller import solicitar_sync, verificar_y_completar_pendientes
from utils.sat_client import TIPOS_COMPROBANTE


def _parse_fecha(s: str) -> date:
    return date.fromisoformat(s)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    ayer = date.today() - timedelta(days=1)
    parser.add_argument("--desde", type=_parse_fecha, default=ayer)
    parser.add_argument("--hasta", type=_parse_fecha, default=ayer)
    parser.add_argument("--tipos", nargs="+", choices=list(TIPOS_COMPROBANTE), default=list(TIPOS_COMPROBANTE))
    args = parser.parse_args()

    print(f"[sat_descarga_diaria] completando solicitudes pendientes de días anteriores...")
    pendientes = verificar_y_completar_pendientes(None)
    for r in pendientes:
        print(f"[sat_descarga_diaria] pendiente run_id={r['run_id']} -> {r}")

    print(f"[sat_descarga_diaria] solicitando descarga {args.desde} a {args.hasta} tipos={args.tipos}")
    resultados = solicitar_sync(None, "systemd", args.desde, args.hasta, tuple(args.tipos), origen="timer")

    hubo_error = False
    for r in resultados:
        print(f"[sat_descarga_diaria] tipo={r['tipo']} ok={r['ok']} id_solicitud={r['id_solicitud']} mensaje={r['mensaje']}")
        if not r["ok"]:
            hubo_error = True

    return 1 if hubo_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
