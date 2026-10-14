# scripts/sat_descarga_semanal.py
"""
Job semanal (systemd timer, todos los sábados) de RECUPERACIÓN de CFDI
recibidos del SAT — red de seguridad sobre `sat_descarga_diaria.py`.

Por qué existe: la descarga diaria (03:00, día anterior) puede perder algún
CFDI puntual si el SAT contesta raro ese día específico (ver comentario de
`_SAT_COD_SIN_INFO`/`_LIMITE_ESPERA_SOLICITUD` en
controllers/sat_cfdi_controller.py) o si el proceso no corrió ese día. Este
job vuelve a pedir TODA la semana calendario anterior (lunes a domingo) como
respaldo. Es seguro repetir un rango ya procesado: tanto `sat_cfdi_recibidos`
como DATOSCFD usan el UUID del CFDI como clave única (upsert), así que los
que ya existen solo se "actualizan", nunca se duplican — ver
models/sat_cfdi_model.py:upsert_cfdis() y models/datoscfd_model.py:upsert_datoscfd().

Igual que sat_descarga_diaria.py, solo llama a `solicitar_sync()`: NO
reimplementa espera/verificación propia — eso lo sigue haciendo
`sat-cfdi-verificar-pendientes.timer` (cada 60s), que es el que de verdad
completa la descarga cuando el SAT marca la solicitud como "Terminada".

Uso:
    venv/bin/python3 scripts/sat_descarga_semanal.py                 # semana calendario anterior (lun-dom), I/E/P
    venv/bin/python3 scripts/sat_descarga_semanal.py --desde 2026-09-01 --hasta 2026-09-10
    venv/bin/python3 scripts/sat_descarga_semanal.py --tipos I E
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta

# bootstrap: al correr "python3 scripts/sat_descarga_semanal.py" desde la raíz
# del repo, sys.path[0] queda apuntando a scripts/, no a la raíz -> hay que
# agregar la raíz a mano para que "from controllers...." funcione standalone.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from controllers.sat_cfdi_controller import solicitar_sync
from utils.sat_client import TIPOS_COMPROBANTE


def _parse_fecha(s: str) -> date:
    return date.fromisoformat(s)


def _semana_calendario_anterior(hoy: date) -> tuple[date, date]:
    """Lunes a domingo de la semana calendario inmediata anterior a `hoy`."""
    lunes_esta_semana = hoy - timedelta(days=hoy.weekday())
    lunes_pasado = lunes_esta_semana - timedelta(days=7)
    domingo_pasado = lunes_pasado + timedelta(days=6)
    return lunes_pasado, domingo_pasado


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    desde_def, hasta_def = _semana_calendario_anterior(date.today())
    parser.add_argument("--desde", type=_parse_fecha, default=desde_def)
    parser.add_argument("--hasta", type=_parse_fecha, default=hasta_def)
    parser.add_argument("--tipos", nargs="+", choices=list(TIPOS_COMPROBANTE), default=list(TIPOS_COMPROBANTE))
    args = parser.parse_args()

    print(
        f"[sat_descarga_semanal] recuperando semana {args.desde} a {args.hasta} "
        f"tipos={args.tipos} (red de seguridad sobre la descarga diaria)"
    )
    resultados = solicitar_sync(None, "systemd", args.desde, args.hasta, tuple(args.tipos), origen="timer")

    hubo_error = False
    for r in resultados:
        print(f"[sat_descarga_semanal] tipo={r['tipo']} ok={r['ok']} id_solicitud={r['id_solicitud']} mensaje={r['mensaje']}")
        if not r["ok"]:
            hubo_error = True

    return 1 if hubo_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
