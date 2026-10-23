"""Fase 2 del plan de Materia Prima (Inventario): generar la requisición
real en SAE (COMPQ01 / PAR_COMPQ01, TIP_DOC='q') a partir de una solicitud
ya autorizada. Folio propio "OneCore" (creado por el usuario en SAE,
independiente del consecutivo legado "STAND.") — formato confirmado en vivo
con el usuario: SERIE + número pegado, sin separador, justificado a la
derecha en un campo de ancho LONGITUD, relleno con espacios (no ceros).
Ej. folio 1 con SERIE='OneCore' y LONGITUD=10 -> "OneCore         1".
"""

from models.db import run_query_firebird, run_firebird_transaccion

_FIREBIRD_SAE = "FIREBIRD_BIO_SAE"
_TIP_DOC_REQUISICION = "q"
_SERIE_ONECORE = "OneCore"


def obtener_parametros_folio_onecore_model() -> dict:
    """Trae longitud/separador reales de PARAM_FOLIOSC01 — no se hardcodea
    por si el usuario ajusta la máscara en SAE más adelante."""
    rows = run_query_firebird(
        _FIREBIRD_SAE,
        "SELECT LONGITUD, SEPARADOR FROM PARAM_FOLIOSC01 WHERE TIPODOCTO = 'Q' AND SERIE = ?",
        (_SERIE_ONECORE,),
    )
    if not rows:
        return {"longitud": 10, "separador": ""}
    r = rows[0]
    return {"longitud": int(r.get("LONGITUD") or 10), "separador": str(r.get("SEPARADOR") or "")}


def _formatear_cve_doc(folio: int, longitud: int, separador: str) -> str:
    return f"{_SERIE_ONECORE}{separador}{str(folio).rjust(longitud)}"


def obtener_proximo_folio_requisicion_model() -> dict:
    """Vista previa (de solo lectura) del próximo folio/CVE_DOC — el
    consecutivo real se vuelve a leer dentro de la misma transacción al
    generar, para no pisar otro folio si alguien generó uno mientras tanto."""
    rows = run_query_firebird(
        _FIREBIRD_SAE,
        "SELECT ULT_DOC FROM FOLIOSC01 WHERE TIP_DOC = ? AND SERIE = ?",
        (_TIP_DOC_REQUISICION, _SERIE_ONECORE),
    )
    ult_doc = int(rows[0]["ULT_DOC"]) if rows else 0
    folio = ult_doc + 1
    params = obtener_parametros_folio_onecore_model()
    cve_doc = _formatear_cve_doc(folio, params["longitud"], params["separador"])
    return {"folio": folio, "cve_doc": cve_doc}


def generar_requisicion_sae_model(
    *,
    cve_clpv: str,
    fecha_doc,
    num_alma: int,
    num_moned: int,
    tipcamb: float,
    lineas: list[dict],
) -> dict | None:
    """lineas: [{"cve_art", "cant", "cost", "uni_venta", "descr_art"}, ...]
    Abre una sola transacción: relee el folio vigente, inserta cabecera +
    detalle, y actualiza el consecutivo — todo o nada. Regresa
    {"cve_doc", "folio"} si quedó bien, None si no había líneas."""
    if not lineas:
        return None

    con_rows = run_query_firebird(
        _FIREBIRD_SAE,
        "SELECT ULT_DOC FROM FOLIOSC01 WHERE TIP_DOC = ? AND SERIE = ?",
        (_TIP_DOC_REQUISICION, _SERIE_ONECORE),
    )
    ult_doc = int(con_rows[0]["ULT_DOC"]) if con_rows else 0
    folio = ult_doc + 1
    params = obtener_parametros_folio_onecore_model()
    cve_doc = _formatear_cve_doc(folio, params["longitud"], params["separador"])

    cant_tot = sum(float(l["cant"]) for l in lineas)
    importe = sum(float(l["cant"]) * float(l["cost"]) for l in lineas)

    statements: list[tuple[str, tuple]] = [
        (
            """
            INSERT INTO COMPQ01 (
                TIP_DOC, CVE_DOC, CVE_CLPV, STATUS, FECHA_DOC, CAN_TOT, IMPORTE,
                NUM_ALMA, ACT_CXP, ACT_COI, NUM_MONED, TIPCAMB, SERIE, FOLIO
            )
            VALUES (?, ?, ?, 'O', ?, ?, ?, ?, 'N', 'N', ?, ?, ?, ?)
            """,
            (
                _TIP_DOC_REQUISICION, cve_doc, cve_clpv, fecha_doc, cant_tot, importe,
                int(num_alma), int(num_moned), float(tipcamb), _SERIE_ONECORE, folio,
            ),
        ),
    ]
    for i, linea in enumerate(lineas, start=1):
        statements.append((
            """
            INSERT INTO PAR_COMPQ01 (
                CVE_DOC, NUM_PAR, CVE_ART, CANT, PXR, PREC, COST, ACT_INV,
                UNI_VENTA, NUM_ALM, DESCR_ART, TIP_CAM
            )
            VALUES (?, ?, ?, ?, ?, 0, ?, 'N', ?, ?, ?, ?)
            """,
            (
                cve_doc, i, linea["cve_art"], float(linea["cant"]), float(linea["cant"]),
                float(linea["cost"]), linea.get("uni_venta") or "KG", int(num_alma),
                linea.get("descr_art"), float(tipcamb),
            ),
        ))
    statements.append((
        "UPDATE FOLIOSC01 SET ULT_DOC = ?, FECH_ULT_DOC = ? WHERE TIP_DOC = ? AND SERIE = ?",
        (folio, fecha_doc, _TIP_DOC_REQUISICION, _SERIE_ONECORE),
    ))

    run_firebird_transaccion(_FIREBIRD_SAE, statements)
    return {"cve_doc": cve_doc, "folio": folio}
