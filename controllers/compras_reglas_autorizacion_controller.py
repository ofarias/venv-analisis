import pandas as pd

from models.compras_reglas_autorizacion_model import (
    crear_regla_model,
    obtener_reglas_model,
    obtener_receptores_regla_model,
    actualizar_regla_model,
    cambiar_estatus_regla_model,
    eliminar_regla_model,
    obtener_tipo_cambio_usd_model,
    obtener_reglas_activas_con_receptores_model,
    resolver_usuario_id_por_nombre_model,
    calcular_monto_autorizado_mes_std_model,
)

_COLS_VACIAS = [
    "id_regla", "usuario_solicita_id", "usuario_solicita_nombre",
    "id_tipo_compra", "tipo_compra_nombre", "linea",
    "monto_limite_usd", "monto_limite_mxn",
    "limite_mensual_usd", "limite_mensual_mxn", "activo", "updated_at",
    "usuarios_recibe_nombres",
]


def _validar(
    usuario_recibe_ids, monto_usd, monto_mxn, limite_mensual_usd=0, limite_mensual_mxn=0,
) -> tuple[bool, str, float | None, float | None, float | None, float | None]:
    if not usuario_recibe_ids:
        return False, "debes seleccionar al menos un usuario que reciba la solicitud.", None, None, None, None
    try:
        usd = float(monto_usd or 0)
        mxn = float(monto_mxn or 0)
        mensual_usd = float(limite_mensual_usd or 0)
        mensual_mxn = float(limite_mensual_mxn or 0)
    except (TypeError, ValueError):
        return False, "monto límite inválido.", None, None, None, None
    if usd < 0 or mxn < 0 or mensual_usd < 0 or mensual_mxn < 0:
        return False, "el monto límite no puede ser negativo.", None, None, None, None
    return True, "", usd, mxn, mensual_usd, mensual_mxn


def obtener_tipo_cambio_usd_ctrl() -> dict:
    return obtener_tipo_cambio_usd_model()


def crear_regla_ctrl(
    usuario_solicita_id, id_tipo_compra, linea, monto_limite_usd, monto_limite_mxn,
    usuario_recibe_ids, activo=1, limite_mensual_usd=0, limite_mensual_mxn=0,
):
    ok, mensaje, usd, mxn, mensual_usd, mensual_mxn = _validar(
        usuario_recibe_ids, monto_limite_usd, monto_limite_mxn, limite_mensual_usd, limite_mensual_mxn,
    )
    if not ok:
        return False, mensaje

    id_regla = crear_regla_model(
        usuario_solicita_id=usuario_solicita_id or None,
        id_tipo_compra=id_tipo_compra or None,
        linea=(linea or "").strip() or None,
        monto_limite_usd=usd,
        monto_limite_mxn=mxn,
        limite_mensual_usd=mensual_usd,
        limite_mensual_mxn=mensual_mxn,
        usuario_recibe_ids=[int(u) for u in usuario_recibe_ids],
        activo=1 if activo else 0,
    )
    return (True, "regla creada correctamente.") if id_regla else (False, "no se pudo crear la regla.")


def obtener_reglas_ctrl() -> pd.DataFrame:
    rows = obtener_reglas_model()
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=_COLS_VACIAS)


def obtener_receptores_regla_ctrl(id_regla) -> list[int]:
    return obtener_receptores_regla_model(int(id_regla))


def actualizar_regla_ctrl(
    id_regla, usuario_solicita_id, id_tipo_compra, linea, monto_limite_usd, monto_limite_mxn,
    usuario_recibe_ids, activo, limite_mensual_usd=0, limite_mensual_mxn=0,
):
    ok, mensaje, usd, mxn, mensual_usd, mensual_mxn = _validar(
        usuario_recibe_ids, monto_limite_usd, monto_limite_mxn, limite_mensual_usd, limite_mensual_mxn,
    )
    if not ok:
        return False, mensaje

    ok = actualizar_regla_model(
        id_regla=int(id_regla),
        usuario_solicita_id=usuario_solicita_id or None,
        id_tipo_compra=id_tipo_compra or None,
        linea=(linea or "").strip() or None,
        monto_limite_usd=usd,
        monto_limite_mxn=mxn,
        limite_mensual_usd=mensual_usd,
        limite_mensual_mxn=mensual_mxn,
        usuario_recibe_ids=[int(u) for u in usuario_recibe_ids],
        activo=1 if activo else 0,
    )
    return (True, "regla actualizada correctamente.") if ok else (False, "no se pudo actualizar la regla.")


def cambiar_estatus_regla_ctrl(id_regla, activo):
    ok = cambiar_estatus_regla_model(int(id_regla), 1 if activo else 0)
    return (True, "estatus actualizado.") if ok else (False, "no se pudo actualizar el estatus.")


def eliminar_regla_ctrl(id_regla):
    ok = eliminar_regla_model(int(id_regla))
    return (True, "regla eliminada correctamente.") if ok else (False, "no se pudo eliminar la regla.")


def obtener_reglas_activas_con_receptores_ctrl() -> list[dict]:
    return obtener_reglas_activas_con_receptores_model()


def resolver_usuario_id_por_nombre_ctrl(nombre: str) -> int | None:
    return resolver_usuario_id_por_nombre_model(nombre)


def calcular_monto_autorizado_mes_std_ctrl(nombre_solicitante: str, anio: int, mes: int) -> float:
    return calcular_monto_autorizado_mes_std_model(nombre_solicitante, anio, mes)
