from datetime import date
import pandas as pd
import streamlit as st

from controllers.compras_solicitudes_controller import (
    crear_solicitud_mp_inventario_ctrl,
)

_MESES = {1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
          7: "jul", 8: "ago", 9: "sep", 10: "oct", 11: "nov", 12: "dic"}


def _fila_vacia_mp_inv():
    return {
        "cve_mp": "",
        "mp_nombre": "",
        "cantidad_kg": None,
        "anio": date.today().year,
        "mes": date.today().month,
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


def _init_form_mp_inv_state():
    if "smpi_observaciones" not in st.session_state:
        st.session_state.smpi_observaciones = ""

    if "smpi_detalle" not in st.session_state:
        st.session_state.smpi_detalle = pd.DataFrame([_fila_vacia_mp_inv()])

    if "smpi_limpiar_pendiente" not in st.session_state:
        st.session_state.smpi_limpiar_pendiente = False

    if "smpi_editor_nonce" not in st.session_state:
        st.session_state.smpi_editor_nonce = 0


def _limpiar_form_mp_inv():
    st.session_state.smpi_observaciones = ""
    st.session_state.smpi_detalle = pd.DataFrame([_fila_vacia_mp_inv()])
    st.session_state.smpi_limpiar_pendiente = False
    st.session_state.smpi_editor_nonce += 1


def _aplicar_limpieza_mp_inv():
    if st.session_state.get("smpi_limpiar_pendiente", False):
        _limpiar_form_mp_inv()


def _normalizar_df_mp_inv(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    cols = ["cve_mp", "mp_nombre", "cantidad_kg", "anio", "mes", "observaciones"]
    for col in cols:
        if col not in df.columns:
            df[col] = None if col in ("cantidad_kg", "anio", "mes") else ""

    for col in ["cantidad_kg", "anio", "mes"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    for col in ["cve_mp", "mp_nombre", "observaciones"]:
        df[col] = df[col].apply(lambda x: "" if pd.isna(x) else str(x).strip())

    return df


def mostrar_formulario_compra_mp_inventario(id_tipo_compra: int):
    _init_form_mp_inv_state()
    _aplicar_limpieza_mp_inv()

    solicitante_actual = _get_solicitante_actual()
    fecha_hoy = date.today()

    st.markdown("### solicitud de compra - materia prima (inventario)")

    c1, c2 = st.columns([2, 1])

    with c1:
        st.text_input(
            "solicitante interno",
            value=solicitante_actual,
            disabled=True,
            key="smpi_solicitante_mostrar",
        )

    with c2:
        st.date_input(
            "fecha solicitud",
            value=fecha_hoy,
            disabled=True,
            format="DD/MM/YYYY",
            key="smpi_fecha_mostrar",
        )

    st.text_area(
        "observaciones generales",
        key="smpi_observaciones",
        height=80,
    )

    st.divider()
    st.markdown("### detalle de materias primas")

    if (
        "smpi_detalle" not in st.session_state
        or not isinstance(st.session_state.smpi_detalle, pd.DataFrame)
        or st.session_state.smpi_detalle.empty
    ):
        st.session_state.smpi_detalle = pd.DataFrame([_fila_vacia_mp_inv()])

    df_base = st.session_state.smpi_detalle.copy()
    editor_key = f"smpi_editor_{st.session_state.smpi_editor_nonce}"

    df_edit = st.data_editor(
        df_base,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key=editor_key,
        column_config={
            "cve_mp": st.column_config.TextColumn("cve MP"),
            "mp_nombre": st.column_config.TextColumn("materia prima"),
            "cantidad_kg": st.column_config.NumberColumn(
                "cantidad (kg)", min_value=0.0, step=1.0, format="%.2f"
            ),
            "anio": st.column_config.NumberColumn("año", min_value=2000, step=1, format="%d"),
            "mes": st.column_config.NumberColumn("mes", min_value=1, max_value=12, step=1, format="%d"),
            "observaciones": st.column_config.TextColumn("observaciones del renglón"),
        },
    )

    st.divider()

    b1, b2 = st.columns(2)

    with b1:
        if st.button("guardar solicitud", use_container_width=True, key="smpi_btn_guardar"):
            df_det = _normalizar_df_mp_inv(df_edit)

            mask_vacias = (
                df_det["cve_mp"].eq("")
                & df_det["mp_nombre"].eq("")
                & df_det["cantidad_kg"].isna()
            )
            df_det = df_det[~mask_vacias].copy()

            if df_det.empty:
                st.warning("agrega al menos un renglón con datos")
                return

            errores = []
            detalle_final = []

            for idx, row in df_det.reset_index(drop=True).iterrows():
                fila = idx + 1

                cve_mp = row["cve_mp"]
                mp_nombre = row["mp_nombre"]
                cantidad_kg = row["cantidad_kg"]
                anio = row["anio"]
                mes = row["mes"]
                observaciones = row["observaciones"]

                if not cve_mp and not mp_nombre:
                    errores.append(f"fila {fila}: falta clave o nombre de la materia prima")
                if pd.isna(cantidad_kg) or float(cantidad_kg) <= 0:
                    errores.append(f"fila {fila}: cantidad inválida")

                detalle_final.append({
                    "cve_mp": cve_mp,
                    "mp_nombre": mp_nombre,
                    "cantidad_kg": float(cantidad_kg) if not pd.isna(cantidad_kg) else None,
                    "existencia_mp_kg": None,
                    "anio": int(anio) if not pd.isna(anio) else None,
                    "mes": int(mes) if not pd.isna(mes) else None,
                    "id_version_forecast": None,
                    "observaciones": observaciones,
                })

            if errores:
                st.error("no se puede guardar:\n\n" + "\n".join(errores[:15]))
                return

            ok, mensaje = crear_solicitud_mp_inventario_ctrl(
                id_tipo_compra=id_tipo_compra,
                fecha_solicitud=fecha_hoy,
                solicitante=solicitante_actual,
                observaciones_generales=st.session_state.smpi_observaciones,
                detalle=detalle_final,
            )

            if ok:
                st.success(mensaje)
                st.session_state.smpi_limpiar_pendiente = True
                st.rerun()
            else:
                st.error(mensaje)

    with b2:
        if st.button("limpiar formulario", use_container_width=True, key="smpi_btn_limpiar"):
            st.session_state.smpi_limpiar_pendiente = True
            st.rerun()
