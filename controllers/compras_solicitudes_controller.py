import streamlit as st
from models.compras_solicitudes_model import (
    crear_solicitud_cabecera_model,
    crear_detalle_productos_model,
    get_unidades_empaque_model,
    get_tipos_compra_activos_model,
    get_solicitudes_pendientes_usuario_model,
    get_detalle_solicitud_compra_model,
    cambiar_estatus_solicitud_compra_model,
    get_correos_roles_compras_model,
    get_cabecera_solicitud_compra_model,
    eliminar_solicitud_compra_model,
    get_departamentos_compra_model,
    get_formas_pago_compra_model,
    get_unidades_negocio_compra_model,
    crear_solicitud_estandar_cabecera_model,
    crear_solicitud_estandar_detalle_model,
    get_cabecera_solicitud_estandar_model,
    get_detalle_solicitud_estandar_model,
    crear_solicitud_mp_inventario_detalle_model,
    get_detalle_solicitud_mp_inventario_model,
    obtener_mp_con_solicitud_model,
    actualizar_renglon_mp_inventario_detalle_model,
    eliminar_detalle_mp_inventario_model,
    listar_proveedores_mp_sae_model,
    guardar_ruteo_solicitud_model,
    obtener_receptores_asignados_model,
    obtener_lineas_mp_inventario_model,
    usuario_tiene_solicitudes_asignadas_model,
    obtener_detalle_mp_inventario_por_ids_model,
    marcar_lineas_mp_inventario_model,
    cambiar_estatus_lineas_mp_inventario_model,
    hay_lineas_captura_mp_inventario_model,
    obtener_receptores_asignados_linea_model,
    obtener_lineas_mp_inventario_pendientes_autorizar_model,
    hay_lineas_pendientes_mp_inventario_model,
    hay_linea_autorizada_mp_inventario_model,
)

from models.sae45_model import buscar_producto_sae

from utils.envio_correo import enviar_correo
from controllers.solicitudes_controller import get_correos_usuarios_por_rol_ctrl, get_usuarios_activos_ctrl
from controllers.compras_reglas_autorizacion_controller import (
    resolver_usuario_id_por_nombre_ctrl,
    obtener_tipo_cambio_usd_ctrl,
)
from controllers.compras_autorizacion_engine_controller import evaluar_autorizacion_ctrl

def obtener_tipos_compra_activos_ctrl():
    return get_tipos_compra_activos_model()


def get_unidades_empaque_ctrl():
    return get_unidades_empaque_model()


def crear_solicitud_producto_ctrl(
    *,
    id_tipo_compra: int,
    fecha_solicitud,
    solicitante: str,
    observaciones_generales: str,
    detalle: list
):
    try:
        solicitante = (solicitante or "").strip()
        observaciones_generales = (observaciones_generales or "").strip()

        if not id_tipo_compra:
            return False, "falta el tipo de compra"

        if not fecha_solicitud:
            return False, "falta la fecha de solicitud"

        if not solicitante:
            return False, "falta el solicitante interno"

        if not detalle:
            return False, "no hay productos para guardar"

        id_solicitud = crear_solicitud_cabecera_model(
            id_tipo_compra=id_tipo_compra,
            fecha_solicitud=fecha_solicitud,
            solicitante=solicitante,
            observaciones_generales=observaciones_generales
        )

        if not id_solicitud:
            return False, "no se pudo crear la cabecera"

        ok = crear_detalle_productos_model(
            id_solicitud=id_solicitud,
            detalle=detalle
        )

        if not ok:
            return False, "error al guardar detalle"

        return True, f"solicitud creada correctamente folio #{id_solicitud}"

    except Exception as e:
        return False, f"error: {str(e)}"


def obtener_solicitudes_pendientes_usuario_ctrl(solicitante: str, ver_todas: bool = False):
    return get_solicitudes_pendientes_usuario_model(solicitante, ver_todas=ver_todas)


def obtener_detalle_solicitud_compra_ctrl(id_solicitud_compra: int):
    return get_detalle_solicitud_compra_model(id_solicitud_compra)

def obtener_cabecera_solicitud_compra_ctrl(id_solicitud_compra: int):
    return get_cabecera_solicitud_compra_model(id_solicitud_compra)


def _correos_por_usuario_ids(usuario_ids: list[int]) -> list[str]:
    if not usuario_ids:
        return []
    usuarios = get_usuarios_activos_ctrl() or []
    correo_por_id = {int(u["id"]): str(u.get("email") or "").strip() for u in usuarios}
    return [correo_por_id[uid] for uid in usuario_ids if correo_por_id.get(uid)]


def _monto_mp_inventario_mxn(df_det, linea: str | None, tipo_cambio: float) -> float | None:
    """Costo en MXN de los renglones de una línea (o de todos, si linea es
    None) — cantidad_kg * precio_usd, convertido con el tipo de cambio
    vigente de SAE. Si falta el precio en CUALQUIER renglón (o la línea no
    tiene renglones), regresa None — no se puede confiar en un total
    incompleto, así que esa línea cae al "siempre requiere autorización"."""
    df_linea = df_det if linea is None else df_det[df_det["linea"] == linea]
    if df_linea.empty:
        return None
    monto_usd = 0.0
    for fila in df_linea.to_dict("records"):
        precio = fila.get("precio_usd")
        if precio in (None, "") or float(precio) <= 0:
            return None
        monto_usd += float(fila.get("cantidad_kg") or 0.0) * float(precio)
    return round(monto_usd * tipo_cambio, 2)


def _evaluar_y_rutear_solicitud(cab: dict) -> dict:
    """Resuelve qué regla de compras_reglas_autorizacion aplica (si alguna)
    y si la solicitud requiere autorización o se autoriza sola — ver
    controllers/compras_autorizacion_engine_controller.py. Materia Prima
    (Inventario) ya trae un precio USD por renglón (ver precio_usd) — se
    evalúa por línea, convirtiendo a MXN con el tipo de cambio vigente de
    SAE; si a alguna línea le falta el precio en algún renglón, esa línea
    siempre requiere autorización (no se puede confiar en un total
    incompleto). Estándar trae costo_total_sin_iva (asumido en MXN, el
    formulario no captura moneda explícita)."""
    tipo_formulario = str(cab.get("tipo_formulario") or "").strip().upper()
    id_solicitud_compra = int(cab["id_solicitud_compra"])
    usuario_solicita_id = resolver_usuario_id_por_nombre_ctrl(cab.get("solicitante"))
    id_tipo_compra = cab.get("id_tipo_compra")
    nombre_solicitante = cab.get("solicitante", "")

    if tipo_formulario == "MP_INV":
        df_det = get_detalle_solicitud_mp_inventario_model(id_solicitud_compra)
        tipo_cambio = obtener_tipo_cambio_usd_ctrl().get("tipo_cambio") or 1.0
        lineas = obtener_lineas_mp_inventario_model(id_solicitud_compra) or [None]
        resultados = [
            evaluar_autorizacion_ctrl(
                usuario_solicita_id=usuario_solicita_id, id_tipo_compra=id_tipo_compra,
                linea=linea, monto_mxn=_monto_mp_inventario_mxn(df_det, linea, tipo_cambio),
                nombre_solicitante=nombre_solicitante,
            )
            for linea in lineas
        ]
        receptor_ids = sorted({uid for r in resultados for uid in r["receptor_ids"]})
        id_regla = next((r["id_regla"] for r in resultados if r["id_regla"]), None)
        motivo = "; ".join(sorted({r["motivo"] for r in resultados}))
        requiere_autorizacion = any(r["requiere_autorizacion"] for r in resultados)
        return {
            "requiere_autorizacion": requiere_autorizacion, "receptor_ids": receptor_ids,
            "id_regla": id_regla, "motivo": motivo,
        }

    if tipo_formulario == "STD":
        df_det = get_detalle_solicitud_estandar_model(id_solicitud_compra)
        monto_mxn = float(df_det["costo_total_sin_iva"].fillna(0).sum()) if not df_det.empty else 0.0
        return evaluar_autorizacion_ctrl(
            usuario_solicita_id=usuario_solicita_id, id_tipo_compra=id_tipo_compra,
            linea=None, monto_mxn=monto_mxn, nombre_solicitante=nombre_solicitante,
        )

    # tipo "MP" (pedido de cliente): tampoco captura un monto
    return evaluar_autorizacion_ctrl(
        usuario_solicita_id=usuario_solicita_id, id_tipo_compra=id_tipo_compra,
        linea=None, monto_mxn=None, nombre_solicitante=nombre_solicitante,
    )


def enviar_solicitud_compra_ctrl(id_solicitud_compra: int, token=None):
    cab = get_cabecera_solicitud_compra_model(id_solicitud_compra)

    if not cab:
        return False, "no se encontró la solicitud"

    estatus_actual = str(cab.get("estatus") or "").strip().lower()
    if estatus_actual != "captura":
        return False, "solo se pueden enviar solicitudes en captura"

    ruteo = _evaluar_y_rutear_solicitud(cab)
    nuevo_estatus = "enviada" if ruteo["requiere_autorizacion"] else "autorizada"

    ok = cambiar_estatus_solicitud_compra_model(id_solicitud_compra, nuevo_estatus)
    if not ok:
        return False, "no se pudo actualizar el estatus"

    guardar_ruteo_solicitud_model(
        id_solicitud_compra=id_solicitud_compra,
        id_regla_aplicada=ruteo.get("id_regla"),
        requiere_autorizacion=ruteo["requiere_autorizacion"],
        motivo=ruteo.get("motivo", ""),
        receptor_ids=ruteo.get("receptor_ids") or [],
    )

    if not ruteo["requiere_autorizacion"]:
        return True, f"solicitud autorizada automáticamente — {ruteo.get('motivo', '')}"

    # Materia Prima (Inventario) tiene su propio circuito de autorización
    # (ver autorizar_solicitud_compra_ctrl). Si una regla resolvió
    # receptor(es) se notifica a ellos; si no hay regla que aplique, se
    # conserva el destino de siempre (SuperAdmin/forecastAdmin para MP_INV,
    # Compras MP/Compras Admin para los demás tipos) para no dejar una
    # solicitud sin avisar a nadie.
    tipo_formulario = str(cab.get("tipo_formulario") or "").strip().upper()
    correos = _correos_por_usuario_ids(ruteo.get("receptor_ids") or [])
    if correos:
        rol_destino = "los usuarios asignados por la regla de autorización"
    elif tipo_formulario == "MP_INV":
        correos = list({
            *get_correos_usuarios_por_rol_ctrl("SuperAdmin"),
            *get_correos_usuarios_por_rol_ctrl("forecastAdmin"),
        })
        rol_destino = "SuperAdmin/forecastAdmin"
    else:
        correos = get_correos_roles_compras_model()
        rol_destino = "Compras MP o Compras Admin"

    if not correos:
        return True, f"solicitud enviada, pero no se encontraron correos de {rol_destino}"

    asunto = f"nueva solicitud de compra enviada #{id_solicitud_compra}"

    cuerpo_html = f"""
    <div style="font-family:arial,sans-serif;font-size:14px;line-height:1.4">
      <p>se envió una nueva solicitud de compra.</p>
      <p>
        <b>id solicitud:</b> {cab.get('id_solicitud_compra', '')}<br>
        <b>tipo:</b> {cab.get('tipo_compra', '')}<br>
        <b>fecha solicitud:</b> {cab.get('fecha_solicitud', '')}<br>
        <b>solicitante:</b> {cab.get('solicitante', '')}<br>
        <b>estatus:</b> enviada
      </p>
      <p>
        <b>observaciones generales:</b><br>
        {cab.get('observaciones_generales', '') or '-'}
      </p>
    </div>
    """

    destinatario = ", ".join(correos)
    remitente = str((st.session_state.get("usuario") or {}).get("email") or "").strip()

    ok_mail, msg_mail = enviar_correo(
        destinatario=destinatario,
        asunto=asunto,
        cuerpo_html=cuerpo_html,
        token=token,
        remitente=remitente,
    )

    if ok_mail:
        return True, "solicitud enviada y correo notificado a compras"
    return True, f"solicitud enviada, pero no se pudo mandar correo: {msg_mail}"

def eliminar_solicitud_compra_ctrl(id_solicitud_compra: int):
    cab = get_cabecera_solicitud_compra_model(id_solicitud_compra)

    if not cab:
        return False, "no se encontró la solicitud"

    estatus_actual = str(cab.get("estatus") or "").strip().lower()
    if estatus_actual != "captura":
        return False, "solo se pueden eliminar solicitudes en captura"

    ok = eliminar_solicitud_compra_model(id_solicitud_compra)
    if not ok:
        return False, "no se pudo eliminar la solicitud"

    return True, "solicitud eliminada correctamente"


def autorizar_solicitud_compra_ctrl(id_solicitud_compra: int, usuario_nombre: str):
    """Autoriza una solicitud 'enviada' — hoy solo lo usa el tipo Materia
    Prima (Inventario) (ver Compras -> Autorizaciones), SuperAdmin/
    forecastAdmin."""
    cab = get_cabecera_solicitud_compra_model(id_solicitud_compra)
    if not cab:
        return False, "no se encontró la solicitud"

    estatus_actual = str(cab.get("estatus") or "").strip().lower()
    if estatus_actual != "enviada":
        return False, "solo se pueden autorizar solicitudes enviadas"

    ok = cambiar_estatus_solicitud_compra_model(id_solicitud_compra, "autorizada")
    if not ok:
        return False, "no se pudo actualizar el estatus"

    return True, f"solicitud #{id_solicitud_compra} autorizada por {usuario_nombre}"


def rechazar_solicitud_compra_ctrl(id_solicitud_compra: int, usuario_nombre: str, motivo: str = ""):
    cab = get_cabecera_solicitud_compra_model(id_solicitud_compra)
    if not cab:
        return False, "no se encontró la solicitud"

    estatus_actual = str(cab.get("estatus") or "").strip().lower()
    if estatus_actual != "enviada":
        return False, "solo se pueden rechazar solicitudes enviadas"

    ok = cambiar_estatus_solicitud_compra_model(id_solicitud_compra, "rechazada")
    if not ok:
        return False, "no se pudo actualizar el estatus"

    return True, f"solicitud #{id_solicitud_compra} rechazada por {usuario_nombre}" + (f" — {motivo}" if motivo else "")


def obtener_mp_con_solicitud_ctrl(anio: int, meses: list[int]):
    return obtener_mp_con_solicitud_model(anio=anio, meses=meses)


def obtener_receptores_asignados_ctrl(id_solicitud_compra: int) -> list[int]:
    return obtener_receptores_asignados_model(id_solicitud_compra)


def usuario_tiene_solicitudes_asignadas_ctrl(usuario_id: int | None) -> bool:
    return usuario_tiene_solicitudes_asignadas_model(usuario_id) if usuario_id else False


def buscar_productos_sae_ctrl(q: str = "", limit: int = 50) -> list[dict]:
    return buscar_producto_sae(st.secrets, q=q, limit=limit)

def get_departamentos_compra_ctrl():
    return get_departamentos_compra_model()


def get_formas_pago_compra_ctrl():
    return get_formas_pago_compra_model()


def get_unidades_negocio_compra_ctrl():
    return get_unidades_negocio_compra_model()


def crear_solicitud_estandar_ctrl(
    *,
    id_tipo_compra: int,
    fecha_solicitud,
    solicitante: str,
    observaciones_generales: str,
    id_departamento: int,
    id_forma_pago: int,
    detalle: list,
):
    try:
        solicitante = (solicitante or "").strip()
        observaciones_generales = (observaciones_generales or "").strip()

        if not id_tipo_compra:
            return False, "falta el tipo de compra"

        if not fecha_solicitud:
            return False, "falta la fecha de solicitud"

        if not solicitante:
            return False, "falta el solicitante interno"

        if not id_departamento:
            return False, "falta el departamento"

        if not id_forma_pago:
            return False, "falta la forma de pago"

        if not detalle:
            return False, "no hay renglones para guardar"

        id_solicitud_compra = crear_solicitud_cabecera_model(
            id_tipo_compra=id_tipo_compra,
            fecha_solicitud=fecha_solicitud,
            solicitante=solicitante,
            observaciones_generales=observaciones_generales,
        )

        if not id_solicitud_compra:
            return False, "no se pudo crear la cabecera"

        id_solicitud_estandar, folio = crear_solicitud_estandar_cabecera_model(
            id_solicitud_compra=id_solicitud_compra,
            fecha_elaboracion=fecha_solicitud,
            id_departamento=id_departamento,
            id_forma_pago=id_forma_pago,
            observaciones=observaciones_generales,
        )

        if not id_solicitud_estandar:
            return False, "no se pudo crear la cabecera estándar"

        ok = crear_solicitud_estandar_detalle_model(
            id_solicitud_estandar=id_solicitud_estandar,
            detalle=detalle,
        )

        if not ok:
            return False, "error al guardar detalle estándar"

        return True, f"solicitud creada correctamente folio {folio}"

    except Exception as e:
        return False, f"error: {str(e)}"
    
def obtener_cabecera_solicitud_estandar_ctrl(id_solicitud_compra: int):
    return get_cabecera_solicitud_estandar_model(id_solicitud_compra)


def obtener_detalle_solicitud_estandar_ctrl(id_solicitud_compra: int):
    return get_detalle_solicitud_estandar_model(id_solicitud_compra)


def obtener_tipo_compra_mp_inventario_ctrl() -> dict | None:
    tipos = get_tipos_compra_activos_model() or []
    for t in tipos:
        if str(t.get("tipo_formulario") or "").strip().upper() == "MP_INV":
            return t
    return None


def crear_solicitud_mp_inventario_ctrl(
    *,
    id_tipo_compra: int,
    fecha_solicitud,
    solicitante: str,
    observaciones_generales: str,
    detalle: list,
):
    try:
        solicitante = (solicitante or "").strip()
        observaciones_generales = (observaciones_generales or "").strip()

        if not id_tipo_compra:
            return False, "falta el tipo de compra"

        if not fecha_solicitud:
            return False, "falta la fecha de solicitud"

        if not solicitante:
            return False, "falta el solicitante interno"

        if not detalle:
            return False, "no hay materias primas para guardar"

        id_solicitud_compra = crear_solicitud_cabecera_model(
            id_tipo_compra=id_tipo_compra,
            fecha_solicitud=fecha_solicitud,
            solicitante=solicitante,
            observaciones_generales=observaciones_generales,
        )

        if not id_solicitud_compra:
            return False, "no se pudo crear la cabecera"

        ok = crear_solicitud_mp_inventario_detalle_model(
            id_solicitud_compra=id_solicitud_compra,
            detalle=detalle,
        )

        if not ok:
            return False, "error al guardar el detalle de materias primas"

        return True, f"solicitud creada correctamente folio #{id_solicitud_compra}"

    except Exception as e:
        return False, f"error: {str(e)}"


def obtener_detalle_solicitud_mp_inventario_ctrl(id_solicitud_compra: int):
    return get_detalle_solicitud_mp_inventario_model(id_solicitud_compra)


def actualizar_detalle_mp_inventario_ctrl(cambios: list[dict]) -> tuple[int, int]:
    """cambios: [{"id_detalle_mp_inv", "cantidad_kg", "cantidad_requerida_kg",
    "mes", "cve_proveedor"?, "proveedor_nombre"?, "precio_usd"?}, ...] — solo
    aplica si la solicitud dueña de cada renglón sigue en 'captura'. Se usa
    al "colapsar" los renglones mensuales de una materia prima en uno solo
    (ver _mostrar_detalle_mp_inventario). Retorna (ok, fallidos)."""
    ok_count = 0
    fail_count = 0
    for c in cambios:
        ok = actualizar_renglon_mp_inventario_detalle_model(
            id_detalle_mp_inv=int(c["id_detalle_mp_inv"]),
            cantidad_kg=float(c["cantidad_kg"]),
            cantidad_requerida_kg=float(c["cantidad_requerida_kg"]),
            mes=int(c["mes"]),
            cve_proveedor=c.get("cve_proveedor"),
            proveedor_nombre=c.get("proveedor_nombre"),
            precio_usd=c.get("precio_usd"),
        )
        if ok:
            ok_count += 1
        else:
            fail_count += 1
    return ok_count, fail_count


def listar_proveedores_mp_sae_ctrl() -> list[dict]:
    return listar_proveedores_mp_sae_model()


def eliminar_detalle_mp_inventario_ctrl(ids_detalle: list[int]) -> tuple[int, int]:
    """Elimina uno o más renglones (ids de compras_solicitudes_mp_inventario_detalle)
    — solo aplica si la solicitud dueña sigue en 'captura'. Retorna (ok, fallidos)."""
    ok_count = 0
    fail_count = 0
    for id_det in ids_detalle:
        ok = eliminar_detalle_mp_inventario_model(int(id_det))
        if ok:
            ok_count += 1
        else:
            fail_count += 1
    return ok_count, fail_count


def enviar_lineas_mp_inventario_ctrl(ids_detalle: list[int], token=None) -> tuple[bool, str]:
    """Envía a autorización (o autoriza sola, según las reglas) solo las
    líneas marcadas con el checkbox en Pendientes — no toda la solicitud
    ("tablero de control de compras": se van enviando línea por línea hasta
    vaciar la cola de captura). Agrupa por línea (unidad de negocio) porque
    cada una puede resolver a una regla distinta. Cuando ya no queda ningún
    renglón en 'captura' para la solicitud dueña, su cabecera pasa a
    'enviada'."""
    if not ids_detalle:
        return False, "no hay líneas seleccionadas"

    df_det = obtener_detalle_mp_inventario_por_ids_model(ids_detalle)
    if df_det.empty:
        return False, "no se encontraron las líneas seleccionadas"

    ids_solicitud = sorted({int(i) for i in df_det["id_solicitud_compra"].tolist()})
    if len(ids_solicitud) != 1:
        return False, "las líneas seleccionadas deben pertenecer a una sola solicitud"
    id_solicitud_compra = ids_solicitud[0]

    cab = get_cabecera_solicitud_compra_model(id_solicitud_compra)
    if not cab or str(cab.get("estatus") or "").strip().lower() != "captura":
        return False, "la solicitud ya no está en captura"

    usuario_solicita_id = resolver_usuario_id_por_nombre_ctrl(cab.get("solicitante"))
    id_tipo_compra = cab.get("id_tipo_compra")
    nombre_solicitante = cab.get("solicitante", "")
    tipo_cambio = obtener_tipo_cambio_usd_ctrl().get("tipo_cambio") or 1.0

    filas = df_det.to_dict("records")
    lineas_presentes = list({(str(f.get("linea") or "").strip() or None) for f in filas})

    n_autorizadas = 0
    n_enviadas = 0
    receptor_ids_notificar: set[int] = set()
    for linea in lineas_presentes:
        ids_linea = [
            int(f["id_detalle_mp_inv"]) for f in filas
            if (str(f.get("linea") or "").strip() or None) == linea
        ]
        if not ids_linea:
            continue
        resultado = evaluar_autorizacion_ctrl(
            usuario_solicita_id=usuario_solicita_id, id_tipo_compra=id_tipo_compra,
            linea=linea, monto_mxn=_monto_mp_inventario_mxn(df_det, linea, tipo_cambio),
            nombre_solicitante=nombre_solicitante,
        )
        nuevo_estatus = "autorizada" if not resultado["requiere_autorizacion"] else "enviada"
        marcar_lineas_mp_inventario_model(
            ids_detalle=ids_linea, nuevo_estatus=nuevo_estatus,
            id_regla_aplicada=resultado.get("id_regla"),
            requiere_autorizacion=resultado["requiere_autorizacion"],
            motivo=resultado.get("motivo", ""),
            receptor_ids=resultado.get("receptor_ids") or [],
        )
        if nuevo_estatus == "autorizada":
            n_autorizadas += len(ids_linea)
        else:
            n_enviadas += len(ids_linea)
            receptor_ids_notificar.update(resultado.get("receptor_ids") or [])

    if not hay_lineas_captura_mp_inventario_model(id_solicitud_compra):
        cambiar_estatus_solicitud_compra_model(id_solicitud_compra, "enviada")

    partes = []
    if n_autorizadas:
        partes.append(f"{n_autorizadas} línea(s) autorizada(s) automáticamente")
    if n_enviadas:
        partes.append(f"{n_enviadas} línea(s) enviada(s) a autorización")
    mensaje = ", ".join(partes) or "sin cambios"

    if n_enviadas:
        correos = _correos_por_usuario_ids(sorted(receptor_ids_notificar))
        if not correos:
            correos = list({
                *get_correos_usuarios_por_rol_ctrl("SuperAdmin"),
                *get_correos_usuarios_por_rol_ctrl("forecastAdmin"),
            })
        if correos:
            asunto = f"líneas de materia prima enviadas a autorización — solicitud #{id_solicitud_compra}"
            cuerpo_html = f"""
            <div style="font-family:arial,sans-serif;font-size:14px;line-height:1.4">
              <p>se enviaron {n_enviadas} línea(s) de materia prima a autorización.</p>
              <p>
                <b>solicitud:</b> #{id_solicitud_compra}<br>
                <b>solicitante:</b> {cab.get('solicitante', '')}
              </p>
            </div>
            """
            destinatario = ", ".join(correos)
            remitente = str((st.session_state.get("usuario") or {}).get("email") or "").strip()
            enviar_correo(
                destinatario=destinatario, asunto=asunto, cuerpo_html=cuerpo_html,
                token=token, remitente=remitente,
            )

    return True, mensaje


def _resolver_cabecera_tras_lineas_mp_inventario(ids_detalle: list[int]) -> None:
    """Una vez que un conjunto de líneas quedó autorizada/rechazada, revisa
    si a su(s) solicitud(es) dueña(s) ya no les queda nada pendiente — si es
    así, fija el estatus final de la cabecera (autorizada si al menos una
    línea quedó autorizada, si no rechazada) para que el resto de la app
    (ej. "generar en SAE") siga funcionando a nivel solicitud."""
    df = obtener_detalle_mp_inventario_por_ids_model(ids_detalle)
    if df.empty:
        return
    for id_solicitud_compra in sorted({int(i) for i in df["id_solicitud_compra"].tolist()}):
        if hay_lineas_pendientes_mp_inventario_model(id_solicitud_compra):
            continue
        nuevo_estatus = (
            "autorizada" if hay_linea_autorizada_mp_inventario_model(id_solicitud_compra) else "rechazada"
        )
        cambiar_estatus_solicitud_compra_model(id_solicitud_compra, nuevo_estatus)


def autorizar_lineas_mp_inventario_ctrl(ids_detalle: list[int], usuario_nombre: str) -> tuple[bool, str]:
    if not ids_detalle:
        return False, "no hay líneas seleccionadas"
    ok = cambiar_estatus_lineas_mp_inventario_model(ids_detalle, "autorizada")
    if not ok:
        return False, "no se pudo autorizar — revisa que las líneas sigan enviadas"
    _resolver_cabecera_tras_lineas_mp_inventario(ids_detalle)
    return True, f"{len(ids_detalle)} línea(s) autorizada(s) por {usuario_nombre}"


def rechazar_lineas_mp_inventario_ctrl(ids_detalle: list[int], usuario_nombre: str, motivo: str = "") -> tuple[bool, str]:
    if not ids_detalle:
        return False, "no hay líneas seleccionadas"
    ok = cambiar_estatus_lineas_mp_inventario_model(ids_detalle, "rechazada")
    if not ok:
        return False, "no se pudo rechazar — revisa que las líneas sigan enviadas"
    _resolver_cabecera_tras_lineas_mp_inventario(ids_detalle)
    return True, f"{len(ids_detalle)} línea(s) rechazada(s) por {usuario_nombre}" + (f" — {motivo}" if motivo else "")


def obtener_detalle_mp_inventario_por_ids_ctrl(ids_detalle: list[int]):
    return obtener_detalle_mp_inventario_por_ids_model(ids_detalle)


def obtener_receptores_asignados_linea_ctrl(id_detalle_mp_inv: int) -> list[int]:
    return obtener_receptores_asignados_linea_model(id_detalle_mp_inv)


def obtener_lineas_mp_inventario_pendientes_autorizar_ctrl(usuario_id: int | None, ver_todas: bool):
    df = obtener_lineas_mp_inventario_pendientes_autorizar_model()
    if df.empty or ver_todas:
        return df
    mask = df["id_detalle_mp_inv"].apply(
        lambda i: usuario_id is not None and usuario_id in (obtener_receptores_asignados_linea_model(int(i)) or [])
    )
    return df[mask]