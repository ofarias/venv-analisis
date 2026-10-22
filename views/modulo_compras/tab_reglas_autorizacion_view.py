import pandas as pd
import streamlit as st

from controllers.compras_reglas_autorizacion_controller import (
    crear_regla_ctrl,
    obtener_reglas_ctrl,
    obtener_receptores_regla_ctrl,
    actualizar_regla_ctrl,
    cambiar_estatus_regla_ctrl,
    eliminar_regla_ctrl,
    obtener_tipo_cambio_usd_ctrl,
)
from controllers.compras_catalogos_controller import obtener_tipos_compra_ctrl
from controllers.solicitudes_controller import get_usuarios_activos_ctrl
from controllers.forecast_controller import _catalogo_productos_sae

_CUALQUIERA = "— cualquiera —"


def _init_state():
    defaults = {
        "cra_id": None,
        "cra_usuario_solicita": _CUALQUIERA,
        "cra_tipo": _CUALQUIERA,
        "cra_linea": _CUALQUIERA,
        "cra_monto_usd": 0.0,
        "cra_monto_mxn": 0.0,
        "cra_limite_mensual_usd": 0.0,
        "cra_limite_mensual_mxn": 0.0,
        "cra_usuarios_recibe": [],
        "cra_activo": True,
        "cra_cargar": None,
        "cra_limpiar": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _aplicar_pendientes():
    if st.session_state.get("cra_limpiar", False):
        st.session_state.cra_id = None
        st.session_state.cra_usuario_solicita = _CUALQUIERA
        st.session_state.cra_tipo = _CUALQUIERA
        st.session_state.cra_linea = _CUALQUIERA
        st.session_state.cra_monto_usd = 0.0
        st.session_state.cra_monto_mxn = 0.0
        st.session_state.cra_limite_mensual_usd = 0.0
        st.session_state.cra_limite_mensual_mxn = 0.0
        st.session_state.cra_usuarios_recibe = []
        st.session_state.cra_activo = True
        st.session_state.cra_cargar = None
        st.session_state.cra_limpiar = False

    data = st.session_state.get("cra_cargar")
    if data:
        st.session_state.cra_id = data["id"]
        st.session_state.cra_usuario_solicita = data["usuario_solicita"]
        st.session_state.cra_tipo = data["tipo"]
        st.session_state.cra_linea = data["linea"]
        st.session_state.cra_monto_usd = data["monto_usd"]
        st.session_state.cra_monto_mxn = data["monto_mxn"]
        st.session_state.cra_limite_mensual_usd = data["limite_mensual_usd"]
        st.session_state.cra_limite_mensual_mxn = data["limite_mensual_mxn"]
        st.session_state.cra_usuarios_recibe = data["usuarios_recibe"]
        st.session_state.cra_activo = data["activo"]
        st.session_state.cra_cargar = None


def _preparar_edicion(row, nombre_por_usuario_id: dict, nombre_por_tipo_id: dict):
    receptores_ids = obtener_receptores_regla_ctrl(int(row["id_regla"]))
    st.session_state.cra_cargar = {
        "id": int(row["id_regla"]),
        "usuario_solicita": (
            nombre_por_usuario_id.get(int(row["usuario_solicita_id"]), _CUALQUIERA)
            if pd.notna(row["usuario_solicita_id"]) else _CUALQUIERA
        ),
        "tipo": (
            nombre_por_tipo_id.get(int(row["id_tipo_compra"]), _CUALQUIERA)
            if pd.notna(row["id_tipo_compra"]) else _CUALQUIERA
        ),
        "linea": str(row["linea"]).strip() if pd.notna(row["linea"]) and str(row["linea"]).strip() else _CUALQUIERA,
        "monto_usd": float(row["monto_limite_usd"]) if pd.notna(row["monto_limite_usd"]) else 0.0,
        "monto_mxn": float(row["monto_limite_mxn"]) if pd.notna(row["monto_limite_mxn"]) else 0.0,
        "limite_mensual_usd": float(row["limite_mensual_usd"]) if pd.notna(row["limite_mensual_usd"]) else 0.0,
        "limite_mensual_mxn": float(row["limite_mensual_mxn"]) if pd.notna(row["limite_mensual_mxn"]) else 0.0,
        "usuarios_recibe": [
            nombre_por_usuario_id[uid] for uid in receptores_ids if uid in nombre_por_usuario_id
        ],
        "activo": bool(row["activo"]),
    }


def _sync_desde_usd(tipo_cambio: float):
    st.session_state.cra_monto_mxn = round(float(st.session_state.cra_monto_usd or 0) * tipo_cambio, 2)


def _sync_desde_mxn(tipo_cambio: float):
    st.session_state.cra_monto_usd = (
        round(float(st.session_state.cra_monto_mxn or 0) / tipo_cambio, 2) if tipo_cambio else 0.0
    )


def _sync_mensual_desde_usd(tipo_cambio: float):
    st.session_state.cra_limite_mensual_mxn = round(float(st.session_state.cra_limite_mensual_usd or 0) * tipo_cambio, 2)


def _sync_mensual_desde_mxn(tipo_cambio: float):
    st.session_state.cra_limite_mensual_usd = (
        round(float(st.session_state.cra_limite_mensual_mxn or 0) / tipo_cambio, 2) if tipo_cambio else 0.0
    )


def mostrar_tab_reglas_autorizacion():
    _init_state()
    _aplicar_pendientes()

    st.subheader("reglas de autorización — solicitudes de compra")
    st.caption(
        "Define quién recibe una solicitud de compra según quién la crea, el tipo, la unidad de "
        "negocio (línea) y un monto límite — por debajo del límite se autoriza sola, igual o por "
        "arriba se envía a los usuarios que reciben. Deja \"cualquiera\" en un campo para que la "
        "regla no filtre por ese dato. Para armar una cascada de montos (ej. Jefe hasta $10,000, "
        "Gerente sin límite) crea varias reglas con el mismo usuario/tipo/línea y distinto "
        "límite/receptores."
    )

    tc_info = obtener_tipo_cambio_usd_ctrl()
    tipo_cambio = tc_info.get("tipo_cambio") or 1.0
    fecha_tc = tc_info.get("fecha")
    fecha_tc_txt = fecha_tc.strftime("%d/%m/%Y") if fecha_tc else "—"

    df_usuarios = pd.DataFrame(get_usuarios_activos_ctrl() or [])
    nombres_usuarios = sorted(df_usuarios["nombre"].dropna().tolist()) if not df_usuarios.empty else []
    id_por_usuario = (
        dict(zip(df_usuarios["nombre"], df_usuarios["id"].astype(int))) if not df_usuarios.empty else {}
    )
    nombre_por_usuario_id = {v: k for k, v in id_por_usuario.items()}

    df_tipos = obtener_tipos_compra_ctrl()
    nombres_tipos = sorted(df_tipos["nombre"].dropna().tolist()) if not df_tipos.empty else []
    id_por_tipo = (
        dict(zip(df_tipos["nombre"], df_tipos["id_tipo_compra"].astype(int))) if not df_tipos.empty else {}
    )
    nombre_por_tipo_id = {v: k for k, v in id_por_tipo.items()}

    try:
        df_cat = _catalogo_productos_sae()
        lineas_disponibles = (
            sorted(df_cat["linea"].dropna().astype(str).str.strip().unique())
            if df_cat is not None and not df_cat.empty and "linea" in df_cat.columns else []
        )
    except Exception:
        lineas_disponibles = []

    c1, c2 = st.columns([1, 2])

    with c1:
        st.markdown("### captura / edición")
        st.selectbox(
            "usuario que crea la solicitud",
            options=[_CUALQUIERA] + nombres_usuarios,
            key="cra_usuario_solicita",
        )
        st.selectbox(
            "tipo de solicitud",
            options=[_CUALQUIERA] + nombres_tipos,
            key="cra_tipo",
        )
        st.selectbox(
            "unidad de negocio (línea)",
            options=[_CUALQUIERA] + lineas_disponibles,
            key="cra_linea",
        )

        st.caption(f"💱 tipo de cambio SAE (USD→MXN): **{tipo_cambio:,.4f}** — actualizado {fecha_tc_txt}")
        m1, m2 = st.columns(2)
        with m1:
            st.number_input(
                "monto límite USD", min_value=0.0, step=100.0, format="%.2f",
                key="cra_monto_usd", on_change=_sync_desde_usd, args=(tipo_cambio,),
            )
        with m2:
            st.number_input(
                "monto límite MXN", min_value=0.0, step=100.0, format="%.2f",
                key="cra_monto_mxn", on_change=_sync_desde_mxn, args=(tipo_cambio,),
            )

        st.caption(
            "límite mensual acumulado (opcional) — si se llega a este monto sumando lo YA "
            "autorizado en el mes, se requiere autorización aunque la solicitud individual esté "
            "por debajo del límite de arriba. Déjalo en 0 para no aplicar límite mensual."
        )
        mm1, mm2 = st.columns(2)
        with mm1:
            st.number_input(
                "límite mensual USD", min_value=0.0, step=100.0, format="%.2f",
                key="cra_limite_mensual_usd", on_change=_sync_mensual_desde_usd, args=(tipo_cambio,),
            )
        with mm2:
            st.number_input(
                "límite mensual MXN", min_value=0.0, step=100.0, format="%.2f",
                key="cra_limite_mensual_mxn", on_change=_sync_mensual_desde_mxn, args=(tipo_cambio,),
            )

        st.multiselect(
            "usuario(s) que van a recibir la solicitud *",
            options=nombres_usuarios,
            key="cra_usuarios_recibe",
        )
        st.checkbox("activa", key="cra_activo")

        b1, b2 = st.columns(2)
        with b1:
            if st.session_state.cra_id is None:
                if st.button("guardar regla", use_container_width=True, type="primary"):
                    ok, mensaje = crear_regla_ctrl(
                        usuario_solicita_id=id_por_usuario.get(st.session_state.cra_usuario_solicita),
                        id_tipo_compra=id_por_tipo.get(st.session_state.cra_tipo),
                        linea=(
                            None if st.session_state.cra_linea == _CUALQUIERA
                            else st.session_state.cra_linea
                        ),
                        monto_limite_usd=st.session_state.cra_monto_usd,
                        monto_limite_mxn=st.session_state.cra_monto_mxn,
                        limite_mensual_usd=st.session_state.cra_limite_mensual_usd,
                        limite_mensual_mxn=st.session_state.cra_limite_mensual_mxn,
                        usuario_recibe_ids=[
                            id_por_usuario[n] for n in st.session_state.cra_usuarios_recibe
                            if n in id_por_usuario
                        ],
                        activo=1 if st.session_state.cra_activo else 0,
                    )
                    if ok:
                        st.success(mensaje)
                        st.session_state.cra_limpiar = True
                        st.rerun()
                    else:
                        st.error(mensaje)
            else:
                if st.button("actualizar regla", use_container_width=True, type="primary"):
                    ok, mensaje = actualizar_regla_ctrl(
                        id_regla=st.session_state.cra_id,
                        usuario_solicita_id=id_por_usuario.get(st.session_state.cra_usuario_solicita),
                        id_tipo_compra=id_por_tipo.get(st.session_state.cra_tipo),
                        linea=(
                            None if st.session_state.cra_linea == _CUALQUIERA
                            else st.session_state.cra_linea
                        ),
                        monto_limite_usd=st.session_state.cra_monto_usd,
                        monto_limite_mxn=st.session_state.cra_monto_mxn,
                        limite_mensual_usd=st.session_state.cra_limite_mensual_usd,
                        limite_mensual_mxn=st.session_state.cra_limite_mensual_mxn,
                        usuario_recibe_ids=[
                            id_por_usuario[n] for n in st.session_state.cra_usuarios_recibe
                            if n in id_por_usuario
                        ],
                        activo=1 if st.session_state.cra_activo else 0,
                    )
                    if ok:
                        st.success(mensaje)
                        st.session_state.cra_limpiar = True
                        st.rerun()
                    else:
                        st.error(mensaje)

        with b2:
            if st.button("limpiar", use_container_width=True):
                st.session_state.cra_limpiar = True
                st.rerun()

        if st.session_state.cra_id is not None:
            st.caption(f"editando id: {st.session_state.cra_id}")

    with c2:
        st.markdown("### reglas existentes")
        df = obtener_reglas_ctrl()

        if df.empty:
            st.info("no hay reglas de autorización registradas.")
            return

        df_show = df.copy()
        df_show["usuario_solicita_nombre"] = df_show["usuario_solicita_nombre"].fillna(_CUALQUIERA)
        df_show["tipo_compra_nombre"] = df_show["tipo_compra_nombre"].fillna(_CUALQUIERA)
        df_show["linea"] = df_show["linea"].fillna(_CUALQUIERA)
        df_show["usuarios_recibe_nombres"] = df_show["usuarios_recibe_nombres"].fillna("—")
        df_show["activo"] = df_show["activo"].map({1: "activa", 0: "inactiva"})
        df_show["monto_limite_usd"] = df_show["monto_limite_usd"].apply(lambda v: f"${float(v):,.2f}")
        df_show["monto_limite_mxn"] = df_show["monto_limite_mxn"].apply(lambda v: f"${float(v):,.2f}")
        df_show["limite_mensual_usd"] = df_show["limite_mensual_usd"].apply(
            lambda v: f"${float(v):,.2f}" if float(v or 0) > 0 else "sin límite"
        )
        df_show["limite_mensual_mxn"] = df_show["limite_mensual_mxn"].apply(
            lambda v: f"${float(v):,.2f}" if float(v or 0) > 0 else "sin límite"
        )

        st.dataframe(
            df_show[[
                "id_regla", "usuario_solicita_nombre", "tipo_compra_nombre", "linea",
                "monto_limite_usd", "monto_limite_mxn",
                "limite_mensual_usd", "limite_mensual_mxn",
                "usuarios_recibe_nombres", "activo",
            ]].rename(columns={
                "usuario_solicita_nombre": "usuario que solicita",
                "tipo_compra_nombre": "tipo",
                "linea": "línea",
                "monto_limite_usd": "monto límite USD",
                "monto_limite_mxn": "monto límite MXN",
                "limite_mensual_usd": "límite mensual USD",
                "limite_mensual_mxn": "límite mensual MXN",
                "usuarios_recibe_nombres": "usuario(s) que reciben",
            }),
            use_container_width=True,
            hide_index=True,
        )

        opciones = {
            f'{int(row["id_regla"])} - {row["usuario_solicita_nombre"] or _CUALQUIERA} / '
            f'{row["tipo_compra_nombre"] or _CUALQUIERA} / {row["linea"] or _CUALQUIERA} '
            f'→ {row["usuarios_recibe_nombres"] or "—"}': int(row["id_regla"])
            for _, row in df.iterrows()
        }
        seleccion = st.selectbox("selecciona una regla", options=list(opciones.keys()), key="cra_sel")
        id_sel = opciones[seleccion]
        row_sel = df[df["id_regla"] == id_sel].iloc[0]

        x1, x2, x3 = st.columns(3)
        with x1:
            if st.button("editar", use_container_width=True):
                _preparar_edicion(row_sel, nombre_por_usuario_id, nombre_por_tipo_id)
                st.rerun()
        with x2:
            nuevo_estatus = 0 if int(row_sel["activo"]) == 1 else 1
            texto = "desactivar" if int(row_sel["activo"]) == 1 else "activar"
            if st.button(texto, use_container_width=True):
                ok, mensaje = cambiar_estatus_regla_ctrl(int(row_sel["id_regla"]), nuevo_estatus)
                if ok:
                    st.success(mensaje)
                    if st.session_state.cra_id == int(row_sel["id_regla"]):
                        st.session_state.cra_limpiar = True
                    st.rerun()
                else:
                    st.error(mensaje)
        with x3:
            if st.button("🗑️ eliminar", use_container_width=True):
                ok, mensaje = eliminar_regla_ctrl(int(row_sel["id_regla"]))
                if ok:
                    st.success(mensaje)
                    if st.session_state.cra_id == int(row_sel["id_regla"]):
                        st.session_state.cra_limpiar = True
                    st.rerun()
                else:
                    st.error(mensaje)
