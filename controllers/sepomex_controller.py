# controllers/sepomex_controller.py
from __future__ import annotations

from typing import List, Dict, Any
from models.sepomex_model import get_sepomex_ciudades_catalogo_rows


def get_sepomex_ciudades_catalogo_ctrl(limit: int = 20000) -> List[Dict[str, Any]]:
    return get_sepomex_ciudades_catalogo_rows(limit=limit)

