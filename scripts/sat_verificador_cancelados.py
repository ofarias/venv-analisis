# scripts/sat_verificador_cancelados.py
"""
Job diario (systemd timer) que revisa contra el SAT si algún CFDI que tenemos
guardado como "Vigente" ya fue cancelado (webservice público de Consulta de
Estado de CFDI, no requiere FIEL).

Uso:
    venv/bin/python3 scripts/sat_verificador_cancelados.py
    venv/bin/python3 scripts/sat_verificador_cancelados.py --limite 1000
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from controllers.sat_cfdi_controller import verificar_cancelados


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limite", type=int, default=500)
    args = parser.parse_args()

    print(f"[sat_verificador_cancelados] revisando hasta {args.limite} CFDI vigentes...")
    res = verificar_cancelados("systemd", origen="timer", limite=args.limite)
    print(f"[sat_verificador_cancelados] revisados={res['revisados']} actualizados={res['actualizados']} errores={res['errores']}")

    return 1 if res["errores"] > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
