"""Fase 2: generar la requisición real en SAE (COMPQ01/PAR_COMPQ01, folio
OneCore) a partir de las líneas ya autorizadas de una solicitud Materia
Prima (Inventario). Agrupa por proveedor porque una requisición en SAE es
de un solo proveedor (CVE_CLPV) — si una solicitud trae materias primas de
más de un proveedor, se generan varias requisiciones, una por proveedor."""

from datetime import date

from models.compras_solicitudes_model import (
    obtener_lineas_autorizadas_sin_generar_model,
    marcar_lineas_generadas_sae_model,
)
from models.compras_solicitudes_sae_model import (
    obtener_proximo_folio_requisicion_model,
    generar_requisicion_sae_model,
)
from controllers.compras_reglas_autorizacion_controller import obtener_tipo_cambio_usd_ctrl

_NUM_ALMACEN_MP = 17  # mismo almacén que usa el resto de la app para materia prima
_NUM_MONEDA_USD = 2   # MONED01.NUM_MONED para USD (verificado en vivo)


def obtener_vista_previa_requisiciones_sae_ctrl(id_solicitud_compra: int) -> list[dict]:
    """Una entrada por proveedor con sus líneas, el folio candidato (de
    solo lectura — el real se vuelve a calcular al generar) y el total."""
    df = obtener_lineas_autorizadas_sin_generar_model(id_solicitud_compra)
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


def generar_requisicion_sae_ctrl(id_solicitud_compra: int, proveedor_nombre: str) -> tuple[bool, str]:
    previews = obtener_vista_previa_requisiciones_sae_ctrl(id_solicitud_compra)
    preview = next((p for p in previews if p["proveedor_nombre"] == proveedor_nombre), None)
    if not preview:
        return False, "no hay líneas pendientes de generar para ese proveedor."
    if preview["sin_proveedor"]:
        return False, "falta asignar un proveedor SAE a estas líneas (hazlo en Pendientes antes de generar)."
    if preview["sin_precio"]:
        return False, "falta el precio USD en alguna línea — complétalo en Pendientes antes de generar."

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
