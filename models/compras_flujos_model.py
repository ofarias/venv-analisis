import pandas as pd
from database.conexion import obtener_conexion


def obtener_flujos_model() -> pd.DataFrame:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            select f.id_flujo, f.id_tipo_compra, t.nombre as tipo_compra, f.nombre, f.activo,
                   f.accion_final_generar_sae, f.accion_final_enviar_correo, f.id_puesto_notificar
            from compras_flujos f
            join compras_tipos t on t.id_tipo_compra = f.id_tipo_compra
            order by t.nombre, f.nombre
            """
        )
        rows = cur.fetchall() or []
        if not rows:
            return pd.DataFrame(columns=[
                "id_flujo", "id_tipo_compra", "tipo_compra", "nombre", "activo",
                "accion_final_generar_sae", "accion_final_enviar_correo", "id_puesto_notificar",
            ])
        return pd.DataFrame(rows)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def obtener_flujo_activo_por_tipo_model(id_tipo_compra: int) -> dict | None:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "select * from compras_flujos where id_tipo_compra = %s and activo = 1 order by id_flujo desc limit 1",
            (int(id_tipo_compra),),
        )
        flujo = cur.fetchone()
        if not flujo:
            return None
        cur.execute(
            "select id_nivel, orden, id_puesto, monto_desde_mxn, monto_hasta_mxn "
            "from compras_flujos_niveles where id_flujo = %s order by orden",
            (int(flujo["id_flujo"]),),
        )
        flujo["niveles"] = cur.fetchall() or []
        return flujo
    finally:
        try:
            conn.close()
        except Exception:
            pass


def obtener_niveles_de_flujo_model(id_flujo: int) -> list[dict]:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "select id_nivel, orden, id_puesto, monto_desde_mxn, monto_hasta_mxn "
            "from compras_flujos_niveles where id_flujo = %s order by orden",
            (int(id_flujo),),
        )
        return cur.fetchall() or []
    finally:
        try:
            conn.close()
        except Exception:
            pass


def guardar_flujo_model(
    id_tipo_compra: int,
    nombre: str,
    niveles: list[dict],
    accion_final_generar_sae: bool,
    accion_final_enviar_correo: bool,
    id_puesto_notificar: int | None,
    id_flujo: int | None = None,
) -> int | None:
    """Crea o actualiza un flujo (desactivando cualquier otro flujo activo
    del mismo tipo de compra, para que siempre haya a lo más uno vigente) y
    reemplaza por completo su lista de niveles."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        if id_flujo:
            cur.execute(
                "update compras_flujos set nombre=%s, accion_final_generar_sae=%s, "
                "accion_final_enviar_correo=%s, id_puesto_notificar=%s where id_flujo=%s",
                (
                    str(nombre).strip(), int(accion_final_generar_sae), int(accion_final_enviar_correo),
                    int(id_puesto_notificar) if id_puesto_notificar else None, int(id_flujo),
                ),
            )
        else:
            cur.execute(
                "update compras_flujos set activo = 0 where id_tipo_compra = %s and activo = 1",
                (int(id_tipo_compra),),
            )
            cur.execute(
                "insert into compras_flujos (id_tipo_compra, nombre, activo, accion_final_generar_sae, "
                "accion_final_enviar_correo, id_puesto_notificar) values (%s, %s, 1, %s, %s, %s)",
                (
                    int(id_tipo_compra), str(nombre).strip(), int(accion_final_generar_sae),
                    int(accion_final_enviar_correo), int(id_puesto_notificar) if id_puesto_notificar else None,
                ),
            )
            id_flujo = int(cur.lastrowid)

        cur.execute("delete from compras_flujos_niveles where id_flujo = %s", (int(id_flujo),))
        if niveles:
            cur.executemany(
                "insert into compras_flujos_niveles (id_flujo, orden, id_puesto, monto_desde_mxn, monto_hasta_mxn) "
                "values (%s, %s, %s, %s, %s)",
                [
                    (
                        int(id_flujo), int(n["orden"]), int(n["id_puesto"]),
                        float(n["monto_desde_mxn"]), (float(n["monto_hasta_mxn"]) if n.get("monto_hasta_mxn") is not None else None),
                    )
                    for n in niveles
                ],
            )
        conn.commit()
        return id_flujo
    except Exception:
        conn.rollback()
        return None
    finally:
        conn.close()


def cambiar_estatus_flujo_model(id_flujo: int, activo: int) -> bool:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("update compras_flujos set activo = %s where id_flujo = %s", (int(activo), int(id_flujo)))
        conn.commit()
        return True
    finally:
        conn.close()


# ── instancia por solicitud ─────────────────────────────────────────────

def crear_niveles_solicitud_model(id_solicitud_compra: int, id_flujo: int, niveles: list[dict]) -> bool:
    """niveles: [{"orden","id_puesto"}], ya en orden — el primero queda
    'pendiente', el resto 'en_espera'."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        filas = [
            (
                int(id_solicitud_compra), int(id_flujo), int(n["orden"]), int(n["id_puesto"]),
                "pendiente" if idx == 0 else "en_espera",
            )
            for idx, n in enumerate(niveles)
        ]
        cur.executemany(
            "insert into compras_solicitudes_niveles (id_solicitud_compra, id_flujo, orden, id_puesto, estatus) "
            "values (%s, %s, %s, %s, %s)",
            filas,
        )
        cur.execute(
            "update compras_solicitudes set id_flujo_aplicado = %s where id_solicitud_compra = %s",
            (int(id_flujo), int(id_solicitud_compra)),
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


def obtener_niveles_solicitud_model(id_solicitud_compra: int) -> list[dict]:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "select n.*, p.nombre as puesto_nombre from compras_solicitudes_niveles n "
            "join compras_puestos p on p.id_puesto = n.id_puesto "
            "where n.id_solicitud_compra = %s order by n.orden",
            (int(id_solicitud_compra),),
        )
        return cur.fetchall() or []
    finally:
        try:
            conn.close()
        except Exception:
            pass


def obtener_nivel_pendiente_solicitud_model(id_solicitud_compra: int) -> dict | None:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "select * from compras_solicitudes_niveles "
            "where id_solicitud_compra = %s and estatus = 'pendiente' order by orden limit 1",
            (int(id_solicitud_compra),),
        )
        return cur.fetchone()
    finally:
        try:
            conn.close()
        except Exception:
            pass


def resolver_nivel_model(id: int, estatus: str, usuario_resolvio_id: int, motivo: str | None) -> bool:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute(
            "update compras_solicitudes_niveles set estatus = %s, usuario_resolvio_id = %s, "
            "fecha_resolucion = now(), motivo = %s where id = %s",
            (str(estatus), int(usuario_resolvio_id), motivo, int(id)),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def activar_siguiente_nivel_model(id_solicitud_compra: int, orden_siguiente: int) -> bool:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute(
            "update compras_solicitudes_niveles set estatus = 'pendiente' "
            "where id_solicitud_compra = %s and orden = %s",
            (int(id_solicitud_compra), int(orden_siguiente)),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def obtener_solicitudes_con_nivel_pendiente_model(usuario_id: int | None, ver_todas: bool) -> list[int]:
    """ids de solicitud con un nivel 'pendiente' cuyo puesto incluye a
    `usuario_id` — o TODAS las que tengan algún nivel pendiente, si
    ver_todas=True (respaldo SuperAdmin/forecastAdmin)."""
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        if ver_todas:
            cur.execute("select distinct id_solicitud_compra from compras_solicitudes_niveles where estatus = 'pendiente'")
        else:
            if usuario_id is None:
                return []
            cur.execute(
                "select distinct n.id_solicitud_compra from compras_solicitudes_niveles n "
                "join compras_puestos_usuarios pu on pu.id_puesto = n.id_puesto "
                "where n.estatus = 'pendiente' and pu.usuario_id = %s",
                (int(usuario_id),),
            )
        return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()


def guardar_flujo_aplicado_model(id_solicitud_compra: int, id_flujo: int) -> bool:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute(
            "update compras_solicitudes set id_flujo_aplicado = %s where id_solicitud_compra = %s",
            (int(id_flujo), int(id_solicitud_compra)),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def guardar_resultado_sae_model(id_solicitud_compra: int, cve_doc: str, folio: str) -> bool:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute(
            "update compras_solicitudes set cve_doc_sae = %s, folio_sae = %s, fecha_generado_sae = now() "
            "where id_solicitud_compra = %s",
            (str(cve_doc), str(folio), int(id_solicitud_compra)),
        )
        conn.commit()
        return True
    finally:
        conn.close()
