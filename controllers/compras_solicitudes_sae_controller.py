"""Fase 2: generar la requisición real en SAE (COMPQ01/PAR_COMPQ01, folio
OneCore) a partir de las líneas ya autorizadas de una solicitud Materia
Prima (Inventario). Agrupa por proveedor porque una requisición en SAE es
de un solo proveedor (CVE_CLPV) — si una solicitud trae materias primas de
más de un proveedor, se generan varias requisiciones, una por proveedor."""

from datetime import date

from models.compras_solicitudes_model import (
    obtener_lineas_autorizadas_sin_generar_model,
    obtener_lineas_solicitud_sin_generar_model,
    marcar_lineas_generadas_sae_model,
)
from models.compras_solicitudes_sae_model import (
    obtener_proximo_folio_requisicion_model,
    generar_requisicion_sae_model,
)
from controllers.compras_reglas_autorizacion_controller import obtener_tipo_cambio_usd_ctrl

_NUM_ALMACEN_MP = 17  # mismo almacén que usa el resto de la app para materia prima
_NUM_MONEDA_USD = 2   # MONED01.NUM_MONED para USD (verificado en vivo)


def _construir_previews_desde_df(df) -> list[dict]:
    """Una entrada por proveedor con sus líneas, el folio candidato (de
    solo lectura — el real se vuelve a calcular al generar) y el total."""
    if df.empty:
        return []

    tipo_cambio = obtener_tipo_cambio_usd_ctrl().get("tipo_cambio") or 1.0
    folio_preview = obtener_proximo_folio_requisicion_model()

    previews = []
    for proveedor_nombre, grupo in df.groupby(df["proveedor_nombre"].fillna("(sin proveedor asignado)")):
        lineas = []
        for _, r in grupo.iterrows():
            cantidad = float(r.get("cantidad_kg") or 0.0)
            precio = r.get("precio_usd")
            precio = float(precio) if precio not in (None, "") else None
            lineas.append({
                "id_detalle_mp_inv": int(r["id_detalle_mp_inv"]),
                "cve_art": r.get("cve_mp"),
                "descr_art": r.get("mp_nombre"),
                "cant": cantidad,
                "cost": precio,
                "total_usd": round(cantidad * precio, 2) if precio is not None else None,
                "uni_venta": "KG",
                "cve_proveedor": r.get("cve_proveedor"),
            })
        cve_proveedor = next((l["cve_proveedor"] for l in lineas if l["cve_proveedor"]), None)
        sin_precio = any(l["cost"] is None for l in lineas)
        previews.append({
            "proveedor_nombre": proveedor_nombre,
            "cve_proveedor": cve_proveedor,
            "lineas": lineas,
            "total_usd": sum(l["total_usd"] for l in lineas if l["total_usd"] is not None),
            "sin_precio": sin_precio,
            "sin_proveedor": not cve_proveedor,
            "tipo_cambio": tipo_cambio,
            "folio_candidato": folio_preview["folio"],
            "cve_doc_candidato": folio_preview["cve_doc"],
        })
    return previews


def obtener_vista_previa_requisiciones_sae_ctrl(id_solicitud_compra: int) -> list[dict]:
    return _construir_previews_desde_df(obtener_lineas_autorizadas_sin_generar_model(id_solicitud_compra))


def obtener_vista_previa_requisiciones_solicitud_ctrl(id_solicitud_compra: int) -> list[dict]:
    """Igual que obtener_vista_previa_requisiciones_sae_ctrl, pero para el
    motor de flujos nuevo: considera TODAS las líneas de la solicitud (ya
    no hace falta que cada línea esté marcada 'autorizada' por separado,
    basta con que la solicitud completa haya llegado a su último nivel)."""
    return _construir_previews_desde_df(obtener_lineas_solicitud_sin_generar_model(id_solicitud_compra))


def _generar_desde_preview(preview: dict) -> tuple[bool, str]:
    if preview["sin_proveedor"]:
        return False, f"[{preview['proveedor_nombre']}] falta asignar un proveedor SAE a estas líneas."
    if preview["sin_precio"]:
        return False, f"[{preview['proveedor_nombre']}] falta el precio USD en alguna línea."

    try:
        resultado = generar_requisicion_sae_model(
            cve_clpv=preview["cve_proveedor"],
            fecha_doc=date.today(),
            num_alma=_NUM_ALMACEN_MP,
            num_moned=_NUM_MONEDA_USD,
            tipcamb=preview["tipo_cambio"],
            lineas=[
                {"cve_art": l["cve_art"], "cant": l["cant"], "cost": l["cost"], "descr_art": l["descr_art"]}
                for l in preview["lineas"]
            ],
        )
    except Exception as e:
        return False, f"error al escribir la requisición en SAE: {e}"

    if not resultado:
        return False, "no se pudo generar la requisición."

    ids_detalle = [l["id_detalle_mp_inv"] for l in preview["lineas"]]
    marcar_lineas_generadas_sae_model(
        ids_detalle, resultado["cve_doc"], str(resultado["folio"]), date.today(),
    )
    return True, f"requisición generada en SAE — folio OneCore #{resultado['folio']} ({resultado['cve_doc'].strip()})"


def generar_requisicion_sae_ctrl(id_solicitud_compra: int, proveedor_nombre: str) -> tuple[bool, str]:
    """Genera UNA requisición para el proveedor indicado — se mantiene para
    el flujo manual existente en Pendientes (autorización por línea)."""
    previews = obtener_vista_previa_requisiciones_sae_ctrl(id_solicitud_compra)
    preview = next((p for p in previews if p["proveedor_nombre"] == proveedor_nombre), None)
    if not preview:
        return False, "no hay líneas pendientes de generar para ese proveedor."
    return _generar_desde_preview(preview)


def generar_requisiciones_solicitud_ctrl(id_solicitud_compra: int) -> tuple[bool, str]:
    """Genera TODAS las requisiciones que hagan falta (una por proveedor)
    para una solicitud ya finalizada por el motor de flujos nuevo — sin
    necesidad de que alguien elija el proveedor a mano, ya viene capturado
    en cada línea desde que se armó la solicitud."""
    previews = obtener_vista_previa_requisiciones_solicitud_ctrl(id_solicitud_compra)
    if not previews:
        return False, "no hay líneas pendientes de generar en SAE para esta solicitud."

    mensajes = []
    hubo_error = False
    for preview in previews:
        ok, msg = _generar_desde_preview(preview)
        mensajes.append(msg)
        hubo_error = hubo_error or not ok
    return (not hubo_error), " | ".join(mensajes)
