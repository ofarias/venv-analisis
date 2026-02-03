# controllers/datoscfd_controller.py
from __future__ import annotations

from typing import Dict, Any

from models.datoscfd_model import importar_cfdi_xml_a_mysql


def registrar_cfdi_desde_xml(xml_bytes: bytes, username: str) -> Dict[str, Any]:
    if not xml_bytes:
        return {"ok": False, "error": "xml vacío"}

    try:
        # username queda por si luego metes auditoría
        r = importar_cfdi_xml_a_mysql(xml_bytes)
        return r
    except Exception as e:
        return {"ok": False, "error": str(e)}