# controllers/solicitudes_controller.py

from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_DOWN
#from turtle import pu
from typing import Any, Dict, List, Optional, Tuple


from models.solicitudes_model import (
    get_usuarios_activos,
    obtener_siguiente_consecutivo,
    insertar_solicitud_cabecera,
    actualizar_solicitud_cabecera,
    actualizar_estatus_solicitud,
    get_solicitudes_df,
    get_solicitud_by_id,
    get_detalle_by_solicitud,
    upsert_detalle_rows,
    delete_detalle_ids,
)


def _d(x: Any, default: str = "0") -> Decimal:
    if x in (None, ""):
        return Decimal(default)
    try:
        return Decimal(str(x))
    except Exception:
        return Decimal(default)


def _trunc(x: Decimal, n: int = 6) -> Decimal:
    q = Decimal("1." + ("0" * n))
    return x.quantize(q, rounding=ROUND_DOWN)


def calcular_totales_row(r: Dict[str, Any]) -> Dict[str, Any]:
    cantidad = _d(r.get("cantidad"), "1")
    pu = _d(r.get("precio_unitario"), "0")
    # impuestos no los captura el usuario; se llenarán desde el xml al capturar uuid
    iva = Decimal("0")
    ieps = Decimal("0")
    ret_iva = Decimal("0")
    ret_isr = Decimal("0")
    subtotal = cantidad * pu
    total = subtotal + iva + ieps - ret_iva - ret_isr

    r["cantidad"] = _trunc(cantidad)
    r["precio_unitario"] = _trunc(pu)
    r["subtotal"] = _trunc(subtotal)
    r["iva"] = _trunc(iva)
    r["ieps"] = _trunc(ieps)
    r["ret_iva"] = _trunc(ret_iva)
    r["ret_isr"] = _trunc(ret_isr)
    r["total"] = _trunc(total)

    return r


def crear_solicitud_ctrl(
    *,
    empleado_id: int,
    empleado_nombre: str,
    clientes: Optional[str],
    ciudades: Optional[str],
    fecha_inicio: date,
    fecha_fin: date,
    hora_salida,
    hora_regreso,
    objetivo: Optional[str],
    usuario_id: int
) -> Tuple[int, str]:
    anio = int(fecha_inicio.year)

    # por concurrencia: si choca por unique (anio, consecutivo) reintenta
    for _ in range(5):
        consecutivo = obtener_siguiente_consecutivo(anio)
        folio = f"{anio}-{consecutivo:04d}"
        try:
            solicitud_id = insertar_solicitud_cabecera(
                anio=anio,
                consecutivo=consecutivo,
                folio=folio,
                empleado_id=empleado_id,
                empleado_nombre=empleado_nombre,
                clientes=clientes,
                ciudades=ciudades,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                hora_salida=hora_salida,
                hora_regreso=hora_regreso,
                objetivo=objetivo,
                creado_por=usuario_id,
            )
            return solicitud_id, folio
        except Exception as e:
            msg = str(e).lower()
            if "uk_solicitudes_anio_consec" in msg or "duplicate" in msg:
                continue
            raise

    raise RuntimeError("no se pudo generar consecutivo por año (colisión repetida)")


def actualizar_cabecera_ctrl(
    *,
    solicitud_id: int,
    empleado_id: int,
    empleado_nombre: str,
    clientes: Optional[str],
    ciudades: Optional[str],
    fecha_inicio: date,
    fecha_fin: date,
    hora_salida,
    hora_regreso,
    objetivo: Optional[str],
    usuario_id: int
) -> None:
    actualizar_solicitud_cabecera(
        solicitud_id=solicitud_id,
        empleado_id=empleado_id,
        empleado_nombre=empleado_nombre,
        clientes=clientes,
        ciudades=ciudades,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        hora_salida=hora_salida,
        hora_regreso=hora_regreso,
        objetivo=objetivo,
        actualizado_por=usuario_id
    )


def cambiar_estatus_ctrl(solicitud_id: int, estatus: str, usuario_id: int) -> None:
    actualizar_estatus_solicitud(
        solicitud_id=solicitud_id,
        estatus=estatus,
        actualizado_por=usuario_id
    )


def get_usuarios_activos_ctrl() -> List[Dict[str, Any]]:
    return get_usuarios_activos()


def listar_solicitudes_ctrl(
    folio_like: str = "",
    estatus: str = "",
    anio: Optional[int] = None,
    empleado_id: Optional[int] = None,
    limit: int = 200
) -> List[Dict[str, Any]]:
    return get_solicitudes_df(
        folio_like=folio_like,
        estatus=estatus,
        anio=anio,
        empleado_id=empleado_id,
        limit=limit
    )


def get_solicitud_ctrl(solicitud_id: int) -> Optional[Dict[str, Any]]:
    return get_solicitud_by_id(solicitud_id)


def get_detalle_ctrl(solicitud_id: int) -> List[Dict[str, Any]]:
    return get_detalle_by_solicitud(solicitud_id)


def guardar_detalle_ctrl(
    *,
    solicitud_id: int,
    rows: List[Dict[str, Any]],
    deleted_ids: List[int],
    usuario_id: int
) -> None:
    # recalcular totales y normalizar
    fixed: List[Dict[str, Any]] = []
    for r in rows:
        if not (r.get("tipo_gasto") or "").strip():
            # no guardes renglones vacíos
            continue
        fixed.append(calcular_totales_row(r))

    if deleted_ids:
        delete_detalle_ids(solicitud_id, deleted_ids)

    if fixed:
        upsert_detalle_rows(
            solicitud_id=solicitud_id,
            rows=fixed,
            creado_por=usuario_id
        )