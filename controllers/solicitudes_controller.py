# controllers/solicitudes_controller.py

from __future__ import annotations

import streamlit as st
from datetime import date
from decimal import Decimal, ROUND_DOWN
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
    get_conceptos_gasto_rows,
    get_datoscfd_by_uuid,
    uuid_ya_usado,
    get_conceptos_catalogo_rows,
    upsert_concepto_catalogo_rows,
    desactivar_conceptos_catalogo,
    get_formas_pago_usuario_rows,
    upsert_formas_pago_usuario_rows,
    desactivar_formas_pago_usuario_ids,
)

from models.sae45_model import buscar_clientes_sae


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

    importe = _d(r.get("importe"), "0")
    imp1 = _d(r.get("impuesto1"), "0")
    imp2 = _d(r.get("impuesto2"), "0")
    imp3 = _d(r.get("impuesto3"), "0")
    imp4 = _d(r.get("impuesto4"), "0")

    subtotal_xml = _d(r.get("subtotal_xml"), "0")
    iva_xml = _d(r.get("iva_xml"), "0")
    total_xml = _d(r.get("total_xml"), "0")

    # regla: importe se queda como total_xml (si existe)
    r["importe"] = total_xml


    # subtotal: usa el del xml si viene; si no, usa cantidad*pu o importe
    if subtotal_xml != Decimal("0"):
        subtotal = subtotal_xml
    elif importe != Decimal("0"):
        subtotal = importe
    else:
        subtotal = cantidad * pu

    # mapeo a columnas
    iva = imp4
    ieps = imp3
    ret_isr = imp1
    ret_iva = imp2

    total = subtotal + iva + ieps - ret_iva - ret_isr

    r["cantidad"] = _trunc(cantidad)
    r["precio_unitario"] = _trunc(pu)

    r["importe"] = _trunc(importe)
    r["impuesto1"] = _trunc(imp1)
    r["impuesto2"] = _trunc(imp2)
    r["impuesto3"] = _trunc(imp3)
    r["impuesto4"] = _trunc(imp4)

    r["subtotal_xml"] = _trunc(subtotal_xml)
    r["iva_xml"] = _trunc(iva_xml)
    r["total_xml"] = _trunc(total_xml)

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
        actualizado_por=usuario_id,
    )


def cambiar_estatus_ctrl(solicitud_id: int, estatus: str, usuario_id: int) -> None:
    actualizar_estatus_solicitud(
        solicitud_id=solicitud_id,
        estatus=estatus,
        actualizado_por=usuario_id,
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
        limit=limit,
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
) -> Dict[str, Any]:
    try:
        fixed: List[Dict[str, Any]] = []


        def _is_nullish(v) -> bool:
            if v is None:
                return True
            # nan float (incluye numpy.nan)
            if isinstance(v, float) and v != v:
                return True
            s = str(v).strip().lower()
            return s in ("", "nan", "none", "null", "<na>", "nat")

        for r in rows:
            if not (r.get("concepto") or "").strip():
                continue

            if _is_nullish(r.get("cantidad")):
                r["cantidad"] = 1
            if _is_nullish(r.get("precio_unitario")):
                r["precio_unitario"] = 0
            if _is_nullish(r.get("importe")):
                r["importe"] = 0

            fixed.append(calcular_totales_row(r))
            
        if deleted_ids:
            delete_detalle_ids(solicitud_id, deleted_ids)

        if fixed:
            upsert_detalle_rows(
                solicitud_id=solicitud_id,
                rows=fixed,
                creado_por=usuario_id,
            )

        return {"ok": True, "msg": "detalle guardado"}
    except ValueError as e:
        return {"ok": False, "msg": str(e)}
    except Exception as e:
        return {"ok": False, "msg": f"error al guardar detalle: {e}"}


def get_conceptos_gasto_ctrl(activo: int = 1):
    return get_conceptos_gasto_rows(activo=activo)


def get_datoscfd_by_uuid_ctrl(uuid: str) -> dict | None:
    return get_datoscfd_by_uuid(uuid, secrets=st.secrets)


def uuid_ya_usado_ctrl(uuid: str, exclude_solicitud_id: int | None = None) -> dict | None:
    return uuid_ya_usado(uuid, exclude_solicitud_id=exclude_solicitud_id)


def listar_conceptos_catalogo_ctrl(incluir_inactivos: bool = False):
    return get_conceptos_catalogo_rows(incluir_inactivos=incluir_inactivos)


def upsert_concepto_catalogo_ctrl(rows: list[dict], usuario_id: int):
    try:
        upsert_concepto_catalogo_rows(rows, usuario_id=usuario_id)
        return {"ok": True, "msg": "catálogo guardado"}
    except Exception as e:
        return {"ok": False, "msg": f"error al guardar catálogo: {e}"}


def desactivar_conceptos_catalogo_ctrl(ids: list[int], usuario_id: int):
    try:
        desactivar_conceptos_catalogo(ids, usuario_id=usuario_id)
        return {"ok": True, "msg": "conceptos desactivados"}
    except Exception as e:
        return {"ok": False, "msg": f"error al desactivar: {e}"}
    
def get_formas_pago_usuario_ctrl(id_usuario: int) -> List[Dict[str, Any]]:
    return get_formas_pago_usuario_rows(int(id_usuario))

def upsert_formas_pago_usuario_ctrl(
        id_usuario: int,
        rows: List[Dict[str, Any]],
        usuario_id: int,
    ) -> Dict[str, Any]:
    try:
        upsert_formas_pago_usuario_rows(
            id_usuario=int(id_usuario),
            rows=rows,
            usuario_id=int(usuario_id),
        )
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "msg": f"error al guardar formas de pago: {e}"}

def desactivar_formas_pago_usuario_ctrl(
    id_usuario: int,
    ids: List[int],
    usuario_id: int,
) -> Dict[str, Any]:
    try:
        desactivar_formas_pago_usuario_ids(
            id_usuario=int(id_usuario),
            ids=[int(x) for x in (ids or [])],
            usuario_id=int(usuario_id),
        )
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "msg": f"error al desactivar formas de pago: {e}"}
    

def buscar_clientes_sae_ctrl(q: str = "", limit: int = 50) -> list[dict]:
    return buscar_clientes_sae(st.secrets, q=q, limit=limit)

def eliminar_solicitud_ctrl(solicitud_id: int, usuario_id: int) -> None:
    # aquí solo orquestas, la validación fuerte debe vivir en el model
    from models.solicitudes_model import eliminar_solicitud_model
    eliminar_solicitud_model(solicitud_id=solicitud_id, usuario_id=usuario_id)
    