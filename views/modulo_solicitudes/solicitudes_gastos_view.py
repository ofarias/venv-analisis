# views/modulo_solicitudes/solicitudes_gastos_view.py

from __future__ import annotations

import streamlit as st
import pandas as pd
from datetime import datetime, date, time, timedelta

from controllers.solicitudes_controller import (
    get_usuarios_activos_ctrl,
    crear_solicitud_ctrl,
    actualizar_cabecera_ctrl,
    listar_solicitudes_ctrl,
    get_solicitud_ctrl,
    get_detalle_ctrl,
    guardar_detalle_ctrl,
    cambiar_estatus_ctrl,
)


def _to_time(v):
    if v is None or v == "":
        return None
    if isinstance(v, time):
        return v
    if isinstance(v, datetime):
        return v.time()
    if isinstance(v, timedelta):
        total = int(v.total_seconds())
        hh = (total // 3600) % 24
        mm = (total % 3600) // 60
        ss = total % 60
        return time(hh, mm, ss)
    if isinstance(v, str):
        s = v.strip()
        try:
            parts = s.split(":")
            hh = int(parts[0])
            mm = int(parts[1]) if len(parts) > 1 else 0
            ss = int(parts[2]) if len(parts) > 2 else 0
            return time(hh, mm, ss)
        except Exception:
            return None
    return None


def _get_usuario_actual():
    u = st.session_state.get("usuario")
    if not u:
        return None
    return u


def _hora_default(hh: int, mm: int) -> time:
    return time(hour=hh, minute=mm)


def mostrar_modulo_solicitudes_gastos():
    st.subheader("solicitudes de gastos")

    usuario = _get_usuario_actual()
    if not usuario:
        st.warning("no hay sesión de usuario en st.session_state['usuario']")
        return

    st.session_state.setdefault("sg_selected_id", None)

    # 1) modo/cabecera (primero)
    selected_id = st.session_state.get("sg_selected_id") or None

    modo_widget = st.radio("modo", options=["crear", "editar"], horizontal=True, key="sg_modo_widget")
    modo = "editar" if selected_id else modo_widget

    solicitud = None
    if modo == "editar" and selected_id:
        solicitud = get_solicitud_ctrl(int(selected_id))
        if solicitud and usuario.get("rol") != "Admin":
            if int(solicitud.get("empleado_id") or 0) != int(usuario["id"]):
                st.session_state["sg_selected_id"] = None
                st.warning("no tienes acceso a esa solicitud")
                st.rerun()

    usuarios = get_usuarios_activos_ctrl()
    usuarios_map = {u["id"]: u for u in usuarios}

    st.caption("cabecera")

    if modo == "editar" and solicitud:
        st.text_input("folio", value=solicitud["folio"], disabled=True)
        st.text_input("estatus", value=solicitud["estatus"], disabled=True)
    else:
        st.text_input("folio", value="(se genera al guardar)", disabled=True)

    empleado_default = solicitud["empleado_id"] if solicitud else (usuario["id"] if usuario else None)
    ids_usuarios = [u["id"] for u in usuarios]
    idx_default = ids_usuarios.index(empleado_default) if empleado_default in ids_usuarios else 0

    empleado_id = st.selectbox(
        "empleado",
        options=ids_usuarios,
        format_func=lambda _id: f"{usuarios_map[_id]['nombre']} ({usuarios_map[_id]['rol']})",
        index=idx_default,
        key="sg_empleado_id"
    )
    empleado_nombre = usuarios_map[empleado_id]["nombre"]

    c3, c4 = st.columns(2)
    with c3:
        clientes = st.text_input("cliente(s)", value=(solicitud["clientes"] or "") if solicitud else "", key="sg_clientes")
        ciudades = st.text_input("ciudad(es)", value=(solicitud["ciudades"] or "") if solicitud else "", key="sg_ciudades")
        objetivo = st.text_area("objetivo", value=(solicitud["objetivo"] or "") if solicitud else "", height=120, key="sg_objetivo")
    with c4:
        fecha_inicio = st.date_input("fecha inicio", value=(solicitud["fecha_inicio"] if solicitud else date.today()), key="sg_fecha_ini")
        fecha_fin = st.date_input("fecha fin", value=(solicitud["fecha_fin"] if solicitud else date.today()), key="sg_fecha_fin")

        hs = _to_time(solicitud["hora_salida"]) if solicitud else None
        hr = _to_time(solicitud["hora_regreso"]) if solicitud else None

        hora_salida = st.time_input("hora salida", value=(hs if hs else _hora_default(5, 0)), key="sg_hora_salida")
        hora_regreso = st.time_input("hora regreso", value=(hr if hr else _hora_default(19, 0)), key="sg_hora_regreso")

    if fecha_inicio > fecha_fin:
        st.error("fecha inicio no puede ser mayor a fecha fin")
        return

    cbtn1, cbtn2, cbtn3, cbtn4 = st.columns([2, 2, 2, 2])

    if modo == "crear":
        if cbtn1.button("guardar cabecera", use_container_width=True):
            solicitud_id, folio = crear_solicitud_ctrl(
                empleado_id=int(empleado_id),
                empleado_nombre=empleado_nombre,
                clientes=clientes.strip() or None,
                ciudades=ciudades.strip() or None,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                hora_salida=hora_salida,
                hora_regreso=hora_regreso,
                objetivo=objetivo.strip() or None,
                usuario_id=int(usuario["id"])
            )
            st.success(f"solicitud creada: {folio} (id {solicitud_id})")
            st.session_state["sg_selected_id"] = int(solicitud_id)
            st.rerun()
    else:
        if selected_id:
            if cbtn1.button("guardar cambios cabecera", use_container_width=True):
                actualizar_cabecera_ctrl(
                    solicitud_id=int(selected_id),
                    empleado_id=int(empleado_id),
                    empleado_nombre=empleado_nombre,
                    clientes=clientes.strip() or None,
                    ciudades=ciudades.strip() or None,
                    fecha_inicio=fecha_inicio,
                    fecha_fin=fecha_fin,
                    hora_salida=hora_salida,
                    hora_regreso=hora_regreso,
                    objetivo=objetivo.strip() or None,
                    usuario_id=int(usuario["id"])
                )
                st.success("cabecera actualizada")
                st.rerun()

            estatus_actual = solicitud["estatus"] if solicitud else ""

            if cbtn2.button("enviar", use_container_width=True, disabled=(estatus_actual not in ("captura", "rechazada"))):
                cambiar_estatus_ctrl(int(selected_id), "enviada", int(usuario["id"]))
                st.success("estatus actualizado: enviada")
                st.rerun()

            if cbtn3.button("autorizar", use_container_width=True,
                            disabled=(usuario.get("rol") != "Admin" or estatus_actual != "enviada")):
                cambiar_estatus_ctrl(int(selected_id), "autorizada", int(usuario["id"]))
                st.success("estatus actualizado: autorizada")
                st.rerun()

            if cbtn4.button("rechazar", use_container_width=True,
                            disabled=(usuario.get("rol") != "Admin" or estatus_actual != "enviada")):
                cambiar_estatus_ctrl(int(selected_id), "rechazada", int(usuario["id"]))
                st.success("estatus actualizado: rechazada")
                st.rerun()
        else:
            st.info("para editar, selecciona una solicitud abajo.")

    st.divider()

    # 2) buscar/resultados (abajo de cabecera)
    st.caption("buscar / resultados")

    b1, b2 = st.columns([2, 3])

    with b1:
        folio_like = st.text_input("folio contiene", key="sg_folio_like")
        estatus = st.selectbox(
            "estatus",
            options=["", "captura", "enviada", "autorizada", "rechazada", "cancelada", "cerrada"],
            index=0,
            key="sg_estatus"
        )
        anio = st.number_input("año", min_value=2020, max_value=2100, value=datetime.now().year, step=1, key="sg_anio")

    with b2:
        # si quieres que admin vea todo, respeta rol; si no, filtra siempre
        empleado_id_filtro = None if usuario.get("rol") == "Admin" else int(usuario["id"])

        rows = listar_solicitudes_ctrl(
            folio_like=folio_like,
            estatus=estatus,
            anio=int(anio) if anio else None,
            empleado_id=empleado_id_filtro,
            limit=200
        )
        
        df = pd.DataFrame(rows)
        if df.empty:
            st.info("sin resultados")
        else:
            st.dataframe(df, use_container_width=True, hide_index=True)

        selected_id_widget = st.number_input(
            "id solicitud seleccionada",
            min_value=0,
            value=int(st.session_state.get("sg_selected_id") or 0),
            step=1,
            key="sg_selected_id_widget"
        )

        if selected_id_widget and int(selected_id_widget) != int(st.session_state.get("sg_selected_id") or 0):
            nuevo_id = int(selected_id_widget)

            if usuario.get("rol") == "Admin":
                st.session_state["sg_selected_id"] = nuevo_id
                st.rerun()
            else:
                s = get_solicitud_ctrl(nuevo_id)
                if s and int(s.get("empleado_id") or 0) == int(usuario["id"]):
                    st.session_state["sg_selected_id"] = nuevo_id
                    st.rerun()
                else:
                    st.warning("esa solicitud no es tuya o no existe")

    st.divider()

    # 3) detalle (al final)
    selected_id = st.session_state.get("sg_selected_id") or None

    if selected_id:
        st.caption("detalle de gastos")

        detalle_rows = get_detalle_ctrl(int(selected_id))
        df_det = pd.DataFrame(detalle_rows)

        cols = [
            "id",
            "fecha_gasto",
            "tipo_gasto",
            "descripcion",
            "cantidad",
            "precio_unitario",
            "moneda",
            "proveedor",
            "uuid",
            "referencia",
            "notas",
        ]

        if df_det.empty:
            df_det = pd.DataFrame([{
                "id": None,
                "fecha_gasto": date.today(),
                "tipo_gasto": "",
                "descripcion": "",
                "cantidad": 1,
                "precio_unitario": 0,
                "moneda": "mxn",
                "proveedor": "",
                "uuid": "",
                "referencia": "",
                "notas": "",
            }])
        else:
            for c in cols:
                if c not in df_det.columns:
                    df_det[c] = None

        if st.button("agregar renglón", use_container_width=False):
            nueva = {
                "id": None,
                "fecha_gasto": date.today(),
                "tipo_gasto": "",
                "descripcion": "",
                "cantidad": 1,
                "precio_unitario": 0,
                "moneda": "mxn",
                "proveedor": "",
                "uuid": "",
                "referencia": "",
                "notas": "",
            }
            df_det = pd.concat([df_det[cols], pd.DataFrame([nueva])], ignore_index=True)

        df_edit = df_det[cols].copy()

        edited = st.data_editor(
            df_edit,
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic",
            key="sg_det_editor",
            column_config={
                "id": st.column_config.TextColumn("id", disabled=True),
                "moneda": st.column_config.SelectboxColumn("moneda", options=["mxn", "usd"], required=True),
                "cantidad": st.column_config.NumberColumn("cantidad", min_value=0.0, step=1.0),
                "precio_unitario": st.column_config.NumberColumn("precio_unitario", min_value=0.0, step=1.0),
                "uuid": st.column_config.TextColumn("uuid"),
            },
        )

        csave, cdel = st.columns([2, 1])

        with cdel:
            ids_opts = []
            if "id" in edited.columns:
                ids_opts = [
                    int(x) for x in edited["id"].dropna().tolist()
                    if str(x).strip() not in ("", "none", "nan")
                ]

            ids_a_borrar = st.multiselect(
                "borrar ids",
                options=ids_opts,
                default=[],
                key="sg_ids_borrar"
            )

        with csave:
            if st.button("guardar detalle", use_container_width=True):
                rows_out = edited.to_dict(orient="records")
                guardar_detalle_ctrl(
                    solicitud_id=int(selected_id),
                    rows=rows_out,
                    deleted_ids=[int(x) for x in ids_a_borrar],
                    usuario_id=int(usuario["id"])
                )
                st.success("detalle guardado")
                st.rerun()
    else:
        st.info("selecciona una solicitud para capturar detalle.")