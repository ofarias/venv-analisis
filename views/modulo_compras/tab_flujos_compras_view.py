import pandas as pd
import streamlit as st

from controllers.compras_flujos_controller import (
    obtener_flujos_ctrl,
    obtener_flujo_activo_ctrl,
    guardar_flujo_ctrl,
    cambiar_estatus_flujo_ctrl,
)
from controllers.compras_catalogos_controller import obtener_tipos_compra_ctrl
from controllers.compras_puestos_controller import obtener_puestos_ctrl

_SIN_TOPE = float("inf")


def mostrar_tab_flujos_compras() -> None:
    st.subheader("⚙️ flujos de autorización")
    st.caption(
        "Por cada tipo de compra se define UN flujo con niveles secuenciales (N1 → N2 → N3...) "
        "ligados a un puesto (ver pestaña Puestos) — el monto de la solicitud decide cuántos "
        "niveles de la cadena aplican. Cada nivel cubre desde su 'monto desde' hasta el "
        "'monto desde' del siguiente nivel; el último nivel siempre queda sin tope. Si el monto "
        "de la solicitud queda por debajo del nivel 1, se autoriza sola."
    )

    df_tipos = obtener_tipos_compra_ctrl()
    if df_tipos.empty:
        st.warning("no hay tipos de compra activos — crea uno primero en Catálogos.")
        return
    df_puestos = obtener_puestos_ctrl()
    if df_puestos.empty:
        st.warning("no hay puestos creados todavía — ve primero a la pestaña 🧑‍💼 Puestos.")
        return

    opciones_tipo = {str(r["nombre"]): int(r["id_tipo_compra"]) for r in df_tipos.to_dict("records")}
    opciones_puesto = {str(r["nombre"]): int(r["id_puesto"]) for r in df_puestos.to_dict("records")}

    tipo_sel_nombre = st.selectbox("tipo de compra", options=list(opciones_tipo.keys()), key="flujo_tipo_sel")
    id_tipo_compra = opciones_tipo[tipo_sel_nombre]

    flujo_actual = obtener_flujo_activo_ctrl(id_tipo_compra)

    nombre_puesto_por_id = {v: k for k, v in opciones_puesto.items()}
    if flujo_actual:
        niveles_iniciales = [
            {
                "orden": n["orden"],
                "puesto": nombre_puesto_por_id.get(int(n["id_puesto"]), ""),
                "monto_desde_mxn": float(n["monto_desde_mxn"]),
            }
            for n in flujo_actual["niveles"]
        ]
    else:
        niveles_iniciales = [{"orden": 1, "puesto": list(opciones_puesto.keys())[0], "monto_desde_mxn": 0.0}]

    st.markdown(f"#### niveles del flujo — {tipo_sel_nombre}")
    df_niveles = st.data_editor(
        pd.DataFrame(niveles_iniciales),
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "orden": st.column_config.NumberColumn("orden", min_value=1, step=1, required=True),
            "puesto": st.column_config.SelectboxColumn("puesto", options=list(opciones_puesto.keys()), required=True),
            "monto_desde_mxn": st.column_config.NumberColumn("monto desde (MXN)", min_value=0.0, step=100.0, required=True),
        },
        key=f"flujo_niveles_editor_{id_tipo_compra}",
    )

    st.markdown("#### al finalizar (último nivel autorizado)")
    c1, c2, c3 = st.columns(3)
    with c1:
        generar_sae = st.checkbox(
            "generar Requisición en SAE", value=bool(flujo_actual.get("accion_final_generar_sae")) if flujo_actual else False,
            key=f"flujo_sae_{id_tipo_compra}",
        )
    with c2:
        enviar_correo = st.checkbox(
            "enviar correo de cierre", value=bool(flujo_actual.get("accion_final_enviar_correo")) if flujo_actual else False,
            key=f"flujo_correo_{id_tipo_compra}",
        )
    with c3:
        opciones_notificar = ["— solicitante —"] + list(opciones_puesto.keys())
        default_notificar = (
            nombre_puesto_por_id.get(flujo_actual.get("id_puesto_notificar"), "— solicitante —")
            if flujo_actual and flujo_actual.get("id_puesto_notificar") else "— solicitante —"
        )
        puesto_notificar_nombre = st.selectbox(
            "notificar al puesto", options=opciones_notificar,
            index=opciones_notificar.index(default_notificar) if default_notificar in opciones_notificar else 0,
            disabled=not enviar_correo, key=f"flujo_puesto_notificar_{id_tipo_compra}",
        )

    nombre_flujo = st.text_input(
        "nombre del flujo", value=(flujo_actual.get("nombre") if flujo_actual else f"flujo {tipo_sel_nombre}"),
        key=f"flujo_nombre_{id_tipo_compra}",
    )

    if st.button("💾 guardar flujo", type="primary", key=f"flujo_btn_guardar_{id_tipo_compra}"):
        filas = df_niveles.sort_values("orden").to_dict("records")
        niveles_payload = []
        for idx, fila in enumerate(filas):
            monto_hasta = float(filas[idx + 1]["monto_desde_mxn"]) if idx + 1 < len(filas) else None
            niveles_payload.append({
                "orden": idx + 1,
                "id_puesto": opciones_puesto.get(str(fila["puesto"])),
                "monto_desde_mxn": float(fila["monto_desde_mxn"]),
                "monto_hasta_mxn": monto_hasta,
            })

        id_puesto_notificar = opciones_puesto.get(puesto_notificar_nombre) if enviar_correo else None

        ok, mensaje = guardar_flujo_ctrl(
            id_tipo_compra=id_tipo_compra, nombre=nombre_flujo, niveles=niveles_payload,
            accion_final_generar_sae=generar_sae, accion_final_enviar_correo=enviar_correo,
            id_puesto_notificar=id_puesto_notificar,
            id_flujo=flujo_actual["id_flujo"] if flujo_actual else None,
        )
        (st.success if ok else st.error)(mensaje)
        if ok:
            st.rerun()

    st.divider()
    st.markdown("### flujos existentes")
    df_flujos = obtener_flujos_ctrl()
    if df_flujos.empty:
        st.caption("todavía no hay ningún flujo guardado.")
        return

    st.dataframe(
        df_flujos[["tipo_compra", "nombre", "activo", "accion_final_generar_sae", "accion_final_enviar_correo"]].rename(columns={
            "tipo_compra": "tipo de compra", "nombre": "flujo", "activo": "activo",
            "accion_final_generar_sae": "genera SAE", "accion_final_enviar_correo": "envía correo",
        }),
        hide_index=True, use_container_width=True,
    )
