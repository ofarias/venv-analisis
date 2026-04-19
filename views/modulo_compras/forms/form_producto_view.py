from datetime import date
import pandas as pd
import streamlit as st

from controllers.compras_solicitudes_controller import (
    crear_solicitud_producto_ctrl,
    get_unidades_empaque_ctrl,
    buscar_productos_sae_ctrl,
)
from controllers.solicitudes_controller import (
    buscar_clientes_sae_ctrl,
)


def _fila_vacia():
    return {
        "cliente": "",
        "cliente_sae": "",
        "numero_pedido": "",
        "persona_solicita": "",
        "producto": "",
        "producto_sae": "",
        "cantidad": None,
        "unidad_empaque": "",
        "fecha_entrega": None,
        "direccion_entrega": "",
        "observaciones": "",
    }


def _get_usuario_actual():
    return st.session_state.get("usuario") or {}


def _get_solicitante_actual() -> str:
    usuario = _get_usuario_actual()
    return (
        str(usuario.get("nombre") or "").strip()
        or str(usuario.get("username") or "").strip()
        or str(usuario.get("email") or "").strip()
        or ""
    )


def _init_form_producto_state():
    if "scp_observaciones_generales" not in st.session_state:
        st.session_state.scp_observaciones_generales = ""

    if "scp_detalle_productos" not in st.session_state:
        st.session_state.scp_detalle_productos = pd.DataFrame([_fila_vacia()])

    if "scp_limpiar_pendiente" not in st.session_state:
        st.session_state.scp_limpiar_pendiente = False

    if "scp_editor_nonce" not in st.session_state:
        st.session_state.scp_editor_nonce = 0


def _limpiar_form():
    st.session_state.scp_observaciones_generales = ""
    st.session_state.scp_detalle_productos = pd.DataFrame([_fila_vacia()])
    st.session_state.scp_limpiar_pendiente = False
    st.session_state.scp_editor_nonce += 1


def _aplicar_limpieza():
    if st.session_state.get("scp_limpiar_pendiente", False):
        _limpiar_form()


def _normalizar_df_guardado(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    cols = [
        "cliente",
        "cliente_sae",
        "numero_pedido",
        "persona_solicita",
        "producto",
        "producto_sae",
        "cantidad",
        "unidad_empaque",
        "fecha_entrega",
        "direccion_entrega",
        "observaciones",
    ]
    for col in cols:
        if col not in df.columns:
            df[col] = None if col in ("cantidad", "fecha_entrega") else ""

    df["cantidad"] = pd.to_numeric(df["cantidad"], errors="coerce")

    def _to_date(v):
        if pd.isna(v) or v in ("", None):
            return None
        try:
            return pd.to_datetime(v).date()
        except Exception:
            return None

    df["fecha_entrega"] = df["fecha_entrega"].apply(_to_date)

    for col in [
        "cliente",
        "cliente_sae",
        "numero_pedido",
        "persona_solicita",
        "producto",
        "producto_sae",
        "unidad_empaque",
        "direccion_entrega",
        "observaciones",
    ]:
        df[col] = df[col].apply(lambda x: "" if pd.isna(x) else str(x).strip())

    return df


def _get_opciones_clientes_sae() -> list[str]:
    try:
        rows = buscar_clientes_sae_ctrl("") or []
    except Exception:
        rows = []

    opciones = []
    vistos = set()

    for r in rows:
        clave = str(
            r.get("clave")
            or r.get("CLAVE")
            or r.get("cve_clpv")
            or r.get("CVE_CLPV")
            or ""
        ).strip()

        nombre = str(
            r.get("nombre")
            or r.get("NOMBRE")
            or r.get("cliente")
            or r.get("CLIENTE")
            or ""
        ).strip()

        valor = f"{clave} - {nombre}".strip(" -")
        if valor and valor not in vistos:
            vistos.add(valor)
            opciones.append(valor)

    return opciones


def _get_opciones_productos_sae() -> list[str]:
    try:
        rows = buscar_productos_sae_ctrl("") or []
    except Exception:
        rows = []

    opciones = []
    vistos = set()

    for r in rows:
        clave = str(
            r.get("clave")
            or r.get("CLAVE")
            or r.get("cve_art")
            or r.get("CVE_ART")
            or r.get("codigo")
            or r.get("CODIGO")
            or ""
        ).strip()

        nombre = str(
            r.get("descr")
            or r.get("DESCR")
            or r.get("nombre")
            or r.get("NOMBRE")
            or r.get("producto")
            or r.get("PRODUCTO")
            or r.get("descripcion")
            or r.get("DESCRIPCION")
            or ""
        ).strip()

        valor = f"{clave} - {nombre}".strip(" -")
        if valor and valor not in vistos:
            vistos.add(valor)
            opciones.append(valor)

    return opciones


def mostrar_formulario_compra_materias_primas(id_tipo_compra: int):
    _init_form_producto_state()
    _aplicar_limpieza()

    solicitante_actual = _get_solicitante_actual()
    fecha_hoy = date.today()

    st.markdown("### formato de pedidos - materias primas")

    c1, c2 = st.columns([2, 1])

    with c1:
        st.text_input(
            "solicitante interno",
            value=solicitante_actual,
            disabled=True,
            key="scp_solicitante_mostrar",
        )

    with c2:
        st.date_input(
            "fecha solicitud",
            value=fecha_hoy,
            disabled=True,
            format="DD/MM/YYYY",
            key="scp_fecha_solicitud_mostrar",
        )

    st.text_area(
        "observaciones generales",
        key="scp_observaciones_generales",
        height=80,
    )

    st.divider()
    st.markdown("### detalle de materias primas")

    unidades = get_unidades_empaque_ctrl() or []
    opciones_unidades = [
        str(u.get("nombre") or "").strip()
        for u in unidades
        if str(u.get("nombre") or "").strip()
    ]

    opciones_clientes_sae = _get_opciones_clientes_sae()
    opciones_productos_sae = _get_opciones_productos_sae()

    if (
        "scp_detalle_productos" not in st.session_state
        or not isinstance(st.session_state.scp_detalle_productos, pd.DataFrame)
        or st.session_state.scp_detalle_productos.empty
    ):
        st.session_state.scp_detalle_productos = pd.DataFrame([_fila_vacia()])

    df_base = st.session_state.scp_detalle_productos.copy()
    editor_key = f"scp_editor_productos_{st.session_state.scp_editor_nonce}"

    df_edit = st.data_editor(
        df_base,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key=editor_key,
        column_config={
            "cliente": st.column_config.TextColumn("cliente"),
            "cliente_sae": st.column_config.SelectboxColumn(
                "cliente SAE",
                options=opciones_clientes_sae,
                required=False,
            ),
            "numero_pedido": st.column_config.TextColumn("pedido"),
            "persona_solicita": st.column_config.TextColumn("persona solicita"),
            "producto": st.column_config.TextColumn("materia prima"),
            "producto_sae": st.column_config.SelectboxColumn(
                "producto SAE",
                options=opciones_productos_sae,
                required=False,
            ),
            "cantidad": st.column_config.NumberColumn(
                "cantidad",
                min_value=0.0,
                step=1.0,
                format="%.2f",
            ),
            "unidad_empaque": st.column_config.SelectboxColumn(
                "unidad de empaque",
                options=opciones_unidades,
            ),
            "fecha_entrega": st.column_config.DateColumn(
                "fecha entrega",
                format="DD/MM/YYYY",
            ),
            "direccion_entrega": st.column_config.TextColumn("dirección de entrega"),
            "observaciones": st.column_config.TextColumn("observaciones del pedido"),
        },
    )

    st.divider()

    c3, c4 = st.columns(2)

    with c3:
        if st.button("guardar solicitud", use_container_width=True):
            df_det = _normalizar_df_guardado(df_edit)

            mask_vacias = (
                df_det["cliente"].eq("")
                & df_det["cliente_sae"].eq("")
                & df_det["numero_pedido"].eq("")
                & df_det["producto"].eq("")
                & df_det["producto_sae"].eq("")
                & df_det["cantidad"].isna()
            )
            df_det = df_det[~mask_vacias].copy()

            if df_det.empty:
                st.warning("agrega al menos un renglón con datos")
                return

            errores = []
            detalle_final = []

            for idx, row in df_det.reset_index(drop=True).iterrows():
                fila = idx + 1

                cliente = row["cliente"]
                cliente_sae = row["cliente_sae"]
                numero_pedido = row["numero_pedido"]
                persona_solicita = row["persona_solicita"]
                producto = row["producto"]
                producto_sae = row["producto_sae"]
                cantidad = row["cantidad"]
                unidad_empaque = row["unidad_empaque"]
                fecha_entrega = row["fecha_entrega"]
                direccion_entrega = row["direccion_entrega"]
                observaciones = row["observaciones"]

                if not cliente and not cliente_sae:
                    errores.append(f"fila {fila}: falta cliente o cliente SAE")
                if not numero_pedido:
                    errores.append(f"fila {fila}: falta número pedido")
                if not producto and not producto_sae:
                    errores.append(f"fila {fila}: falta materia prima o producto SAE")
                if pd.isna(cantidad) or float(cantidad) <= 0:
                    errores.append(f"fila {fila}: cantidad inválida")

                detalle_final.append({
                    "cliente": cliente,
                    "cliente_sae": cliente_sae,
                    "numero_pedido": numero_pedido,
                    "persona_solicita": persona_solicita,
                    "producto": producto,
                    "producto_sae": producto_sae,
                    "cantidad": float(cantidad) if not pd.isna(cantidad) else None,
                    "unidad_empaque": unidad_empaque,
                    "fecha_entrega": fecha_entrega.isoformat() if fecha_entrega else None,
                    "direccion_entrega": direccion_entrega,
                    "observaciones": observaciones,
                })

            if errores:
                st.error("no se puede guardar:\n\n" + "\n".join(errores[:15]))
                return

            ok, mensaje = crear_solicitud_producto_ctrl(
                id_tipo_compra=id_tipo_compra,
                fecha_solicitud=fecha_hoy,
                solicitante=solicitante_actual,
                observaciones_generales=st.session_state.scp_observaciones_generales,
                detalle=detalle_final,
            )

            if ok:
                st.success(mensaje)
                st.session_state.scp_limpiar_pendiente = True
                st.rerun()
            else:
                st.error(mensaje)

    with c4:
        if st.button("limpiar formulario", use_container_width=True):
            st.session_state.scp_limpiar_pendiente = True
            st.rerun()