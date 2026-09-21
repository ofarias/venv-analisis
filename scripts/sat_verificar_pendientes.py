# scripts/sat_verificar_pendientes.py
"""
Job de reintento automático (systemd timer, cada 60s) para las solicitudes
de Descarga Masiva de CFDI del SAT que quedaron "en proceso".

El SAT procesa la descarga de forma asíncrona y puede tardar desde
segundos hasta varios minutos, por eso hay que reconsultar el estatus
periódicamente hasta que quede "Terminada" (o "error"/"rechazada"). Antes
esto dependía de que alguien le diera clic manual a "Verificar pendientes"
en la vista, o de esperar al timer diario de las 03:00
(sat-cfdi-descarga.timer). Este script reusa exactamente la misma función
que esos dos caminos (controllers/sat_cfdi_controller.py) y no hace nada
(ni llama al SAT) cuando no hay ninguna solicitud pendiente — por eso es
seguro correrlo cada 60s de forma indefinida vía sat-cfdi-verificar-pendientes.timer.

Uso:
    venv/bin/python3 scripts/sat_verificar_pendientes.py
"""
from __future__ import annotations

import os
import sys

# bootstrap: al correr "python3 scripts/sat_verificar_pendientes.py" desde la
# raíz del repo, sys.path[0] queda apuntando a scripts/, no a la raíz -> hay
# que agregar la raíz a mano para que "from controllers...." funcione standalone.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from controllers.sat_cfdi_controller import verificar_y_completar_pendientes


def main() -> int:
    resultados = verificar_y_completar_pendientes(None)
    if not resultados:
        return 0

    hubo_error = False
    for r in resultados:
        print(f"[sat_verificar_pendientes] run_id={r['run_id']} -> {r}")
        if r.get("estado") == "error":
            hubo_error = True

    return 1 if hubo_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
