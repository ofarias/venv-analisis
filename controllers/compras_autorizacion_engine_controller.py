"""Motor de resolución de reglas de autorización de Solicitudes de Compra.

Dado quién crea la solicitud, el tipo y la línea (unidad de negocio), decide
qué regla de compras_reglas_autorizacion aplica (la más específica) y si la
solicitud requiere autorización — comparando el monto contra el límite por
solicitud y, si no lo supera, contra el límite mensual acumulado (solo cuenta
lo YA autorizado en el mes, no lo rechazado ni lo pendiente).

Si no hay forma de calcular un monto (precio incompleto, o un tipo de
solicitud que no lo captura) siempre se requiere autorización — no hay contra
qué comparar un límite, así que nunca se autoriza sola."""

from datetime import date

from controllers.compras_reglas_autorizacion_controller import (
    obtener_reglas_activas_con_receptores_ctrl,
    calcular_monto_autorizado_mes_std_ctrl,
    obtener_tipo_cambio_usd_ctrl,
)
from models.compras_solicitudes_model import calcular_monto_autorizado_mes_mp_inv_usd_model

_CAMPOS_CONDICION = ("usuario_solicita_id", "id_tipo_compra", "linea")


def _especificidad(regla: dict) -> int:
    return sum(1 for campo in _CAMPOS_CONDICION if regla.get(campo) not in (None, ""))


def resolver_regla_aplicable_ctrl(
    usuario_solicita_id: int | None, id_tipo_compra: int | None, linea: str | None,
) -> dict | None:
    """Entre las reglas activas cuyas condiciones (usuario/tipo/línea, con
    NULL = "cualquiera") coinciden, regresa la más específica. En caso de
    empate: la de límite más bajo (más conservadora) con la unión de
    receptores de todas las empatadas."""
    reglas = obtener_reglas_activas_con_receptores_ctrl()
    linea_norm = (linea or "").strip() or None

    candidatas = [
        r for r in reglas
        if (r.get("usuario_solicita_id") is None or r.get("usuario_solicita_id") == usuario_solicita_id)
        and (r.get("id_tipo_compra") is None or r.get("id_tipo_compra") == id_tipo_compra)
        and (not r.get("linea") or r.get("linea") == linea_norm)
    ]
    if not candidatas:
        return None

    max_esp = max(_especificidad(r) for r in candidatas)
    empatadas = [r for r in candidatas if _especificidad(r) == max_esp]
    if len(empatadas) == 1:
        return empatadas[0]

    empatadas_orden = sorted(empatadas, key=lambda r: float(r.get("monto_limite_mxn") or 0))
    ganadora = dict(empatadas_orden[0])
    receptores = set()
    for r in empatadas:
        receptores.update(r.get("receptor_ids") or [])
    ganadora["receptor_ids"] = sorted(receptores)
    return ganadora


def calcular_monto_autorizado_mes_mxn_ctrl(nombre_solicitante: str, anio: int, mes: int) -> float:
    """Acumulado YA autorizado en el mes, en MXN — suma los dos tipos que
    hoy traen un monto: Estándar (ya capturado en MXN) y Materia Prima
    (Inventario) (precio capturado en USD por renglón, convertido al tipo de
    cambio vigente de SAE — ver precio_usd en
    compras_solicitudes_mp_inventario_detalle)."""
    std_mxn = calcular_monto_autorizado_mes_std_ctrl(nombre_solicitante, anio, mes)
    mp_inv_usd = calcular_monto_autorizado_mes_mp_inv_usd_model(nombre_solicitante, anio, mes)
    tipo_cambio = obtener_tipo_cambio_usd_ctrl().get("tipo_cambio") or 1.0
    return round(std_mxn + mp_inv_usd * tipo_cambio, 2)


def evaluar_autorizacion_ctrl(
    *,
    usuario_solicita_id: int | None,
    id_tipo_compra: int | None,
    linea: str | None,
    monto_mxn: float | None,
    nombre_solicitante: str = "",
    fecha: date | None = None,
) -> dict:
    """Regresa {"requiere_autorizacion": bool, "receptor_ids": [...],
    "id_regla": int|None, "motivo": str}."""
    regla = resolver_regla_aplicable_ctrl(usuario_solicita_id, id_tipo_compra, linea)

    if monto_mxn is None:
        return {
            "requiere_autorizacion": True,
            "receptor_ids": (regla or {}).get("receptor_ids") or [],
            "id_regla": (regla or {}).get("id_regla"),
            "motivo": "sin monto para evaluar contra un límite — siempre requiere autorización",
        }

    if not regla:
        return {
            "requiere_autorizacion": True,
            "receptor_ids": [],
            "id_regla": None,
            "motivo": "ninguna regla de autorización coincide",
        }

    limite_mxn = float(regla.get("monto_limite_mxn") or 0)
    if monto_mxn >= limite_mxn:
        return {
            "requiere_autorizacion": True,
            "receptor_ids": regla["receptor_ids"],
            "id_regla": regla["id_regla"],
            "motivo": f"monto ${monto_mxn:,.2f} alcanza o supera el límite por solicitud (${limite_mxn:,.2f})",
        }

    limite_mensual_mxn = float(regla.get("limite_mensual_mxn") or 0)
    if limite_mensual_mxn > 0:
        fecha = fecha or date.today()
        ya_autorizado_mxn = calcular_monto_autorizado_mes_mxn_ctrl(nombre_solicitante, fecha.year, fecha.month)
        if ya_autorizado_mxn + monto_mxn >= limite_mensual_mxn:
            return {
                "requiere_autorizacion": True,
                "receptor_ids": regla["receptor_ids"],
                "id_regla": regla["id_regla"],
                "motivo": (
                    f"acumulado autorizado del mes (${ya_autorizado_mxn:,.2f}) + este monto "
                    f"(${monto_mxn:,.2f}) alcanza o supera el límite mensual (${limite_mensual_mxn:,.2f})"
                ),
            }

    return {
        "requiere_autorizacion": False,
        "receptor_ids": regla["receptor_ids"],
        "id_regla": regla["id_regla"],
        "motivo": "por debajo del límite por solicitud y del límite mensual",
    }
