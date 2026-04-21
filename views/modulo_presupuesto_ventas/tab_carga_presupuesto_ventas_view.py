from __future__ import annotations

import io
from typing import Optional

import pandas as pd
import streamlit as st

from controllers.presupuesto_ventas_controller import (
    cargar_excel_a_staging_presupuesto_ventas_ctrl,
    confirmar_importacion_presupuesto_ventas_ctrl,
    obtener_cargas_presupuesto_ventas_ctrl,
    obtener_preview_presupuesto_ventas_ctrl,
    obtener_resumen_staging_presupuesto_ventas_ctrl,
    obtener_staging_presupuesto_ventas_ctrl,
)


def _get_usuario_id() -> int:
    usuario = st.session_state.get("usuario") or {}
    return int(usuario.get("id") or usuario.get("id_usuario") or 0)


def _mostrar_preview_df(df: pd.DataFrame, alto: int = 350) -> None:
    if df is None or df.empty:
        st.info("no hay datos para mostrar")
        return

    st.dataframe(df, use_container_width=True, height=alto)


def _subir_archivo_excel():
    return st.file_uploader(
        "sube el archivo de presupuesto ventas",
        type=["xlsx", "xls"],
        key="pv_archivo_excel",
    )


def _obtener_hojas_excel(archivo) -> list[str]:
    if archivo is None:
        return []

    try:
        archivo.seek(0)
        xls = pd.ExcelFile(archivo)
        return xls.sheet_names or []
    except Exception:
        return []


def _form_cargar_staging() -> None:
    archivo = _subir_archivo_excel()

    if archivo is None:
        return

    hojas = _obtener_hojas_excel(archivo)
    if not hojas:
        st.error("no fue posible leer las hojas del archivo")
        return

    col1, col2, col3, col4 = st.columns([2, 1, 1, 2])

    with col1:
        hoja = st.selectbox(
            "hoja",
            options=hojas,
            index=0,
            key="pv_hoja_excel",
        )

    with col2:
        anio = st.number_input(
            "año",
            min_value=2020,
            max_value=2100,
            value=2026,
            step=1,
            key="pv_anio_excel",
        )

    with col3:
        header = st.number_input(
            "fila encabezado",
            min_value=0,
            max_value=20,
            value=0,
            step=1,
            key="pv_header_excel",
        )

    with col4:
        version = st.text_input(
            "versión",
            value="v1",
            key="pv_version_excel",
        )

    comentarios = st.text_input(
        "comentarios carga",
        value="",
        key="pv_comentarios_excel",
    )

    colp1, colp2 = st.columns([1, 1])

    with colp1:
        if st.button("previsualizar excel", use_container_width=True):
            try:
                archivo.seek(0)
                preview = obtener_preview_presupuesto_ventas_ctrl(
                    archivo=archivo,
                    hoja=hoja,
                    header=int(header),
                    limit=50,
                )
                st.session_state["pv_preview_excel"] = preview
                st.success("previsualización generada")
            except Exception as e:
                st.error(f"error al previsualizar: {e}")

    with colp2:
        if st.button("cargar a staging", use_container_width=True, type="primary"):
            usuario_id = _get_usuario_id()
            if usuario_id <= 0:
                st.error("no se encontró el usuario en sesión")
                return

            try:
                archivo.seek(0)
                resultado = cargar_excel_a_staging_presupuesto_ventas_ctrl(
                    archivo=archivo,
                    nombre_archivo=archivo.name,
                    anio=int(anio),
                    usuario_id=usuario_id,
                    hoja=hoja,
                    header=int(header),
                    version=version or None,
                    comentarios=comentarios or None,
                    limpiar_staging=True,
                )
                st.session_state["pv_id_carga_actual"] = int(resultado["id_carga"])
                st.success(
                    f"staging cargado correctamente. "
                    f"id_carga={resultado['id_carga']} | "
                    f"registros={resultado['total_registros_staging']}"
                )
            except Exception as e:
                st.error(f"error al cargar staging: {e}")

    preview = st.session_state.get("pv_preview_excel")
    if preview:
        st.divider()
        st.markdown("#### preview del excel")

        colx1, colx2 = st.columns(2)

        with colx1:
            st.write("columnas detectadas")
            st.json(preview.get("columnas_base", {}))

        with colx2:
            st.write("columnas mes detectadas")
            columnas_mes = preview.get("columnas_mes", [])
            if columnas_mes:
                st.dataframe(pd.DataFrame(columnas_mes), use_container_width=True, height=220)
            else:
                st.info("no se detectaron columnas de meses")

        df_preview = preview.get("preview")
        if isinstance(df_preview, pd.DataFrame):
            _mostrar_preview_df(df_preview)
        else:
            st.info("no hay preview disponible")


def _selector_carga_actual() -> Optional[int]:
    cargas = obtener_cargas_presupuesto_ventas_ctrl(limit=50)

    if cargas is None or cargas.empty:
        st.info("aún no hay cargas registradas")
        return None

    cargas_rows = cargas.to_dict(orient="records")

    opciones = {
        f"{c['id_carga']} | {c['nombre_archivo']} | {c['anio']} | {c['estatus']}": int(c["id_carga"])
        for c in cargas_rows
    }

    labels = list(opciones.keys())
    if not labels:
        st.info("aún no hay cargas registradas")
        return None

    valor_default = st.session_state.get("pv_id_carga_actual")
    index_default = 0

    if valor_default is not None:
        for i, lbl in enumerate(labels):
            if opciones[lbl] == valor_default:
                index_default = i
                break

    label = st.selectbox(
        "carga",
        options=labels,
        index=index_default,
        key="pv_select_carga_actual",
    )

    id_carga = int(opciones[label])
    st.session_state["pv_id_carga_actual"] = id_carga
    return id_carga


def _panel_resumen_staging(id_carga: int) -> None:
    st.markdown("#### resumen staging")

    resumen = obtener_resumen_staging_presupuesto_ventas_ctrl(id_carga=id_carga)

    if resumen is None or resumen.empty:
        st.info("no hay resumen de staging para mostrar")
        return

    st.dataframe(resumen, use_container_width=True, height=220)


def _panel_staging(id_carga: int) -> None:
    st.markdown("#### staging")

    col1, col2, col3 = st.columns([1, 1, 1])

    with col1:
        estatus_match = st.selectbox(
            "estatus match",
            options=["todos", "pendiente", "completo", "error", "ok"],
            index=0,
            key="pv_staging_estatus_match",
        )

    with col2:
        mes = st.selectbox(
            "mes",
            options=["todos"] + list(range(1, 13)),
            index=0,
            key="pv_staging_mes",
        )

    with col3:
        limit = st.number_input(
            "límite",
            min_value=50,
            max_value=50000,
            value=1000,
            step=50,
            key="pv_staging_limit",
        )

    estatus_final = None if estatus_match == "todos" else estatus_match
    mes_final = None if mes == "todos" else int(mes)

    rows = obtener_staging_presupuesto_ventas_ctrl(
        id_carga=id_carga,
        estatus_match=estatus_final,
        mes=mes_final,
        limit=int(limit),
    )

    if rows is None or rows.empty:
        st.info("no hay registros en staging para esos filtros")
        return

    st.dataframe(rows, use_container_width=True, height=420)


def _panel_confirmar_importacion(id_carga: int) -> None:
    st.markdown("#### confirmar importación")

    reemplazar = st.checkbox(
        "reemplazar existentes con la misma llave",
        value=False,
        key="pv_reemplazar_existentes",
    )

    if st.button("confirmar importación a definitivo", type="primary", use_container_width=True):
        usuario_id = _get_usuario_id()
        if usuario_id <= 0:
            st.error("no se encontró el usuario en sesión")
            return

        try:
            resultado = confirmar_importacion_presupuesto_ventas_ctrl(
                id_carga=id_carga,
                usuario_id=usuario_id,
                reemplazar_existentes=reemplazar,
            )
            st.success(
                f"importación completada. total_insertados={resultado['total_insertados']}"
            )
        except Exception as e:
            st.error(f"error al confirmar importación: {e}")


def mostrar_tab_carga_presupuesto_ventas() -> None:
    st.subheader("carga presupuesto ventas")

    with st.container(border=True):
        _form_cargar_staging()

    st.divider()

    id_carga = _selector_carga_actual()
    if id_carga is None:
        return

    with st.container(border=True):
        _panel_resumen_staging(id_carga=id_carga)

    with st.container(border=True):
        _panel_staging(id_carga=id_carga)

    with st.container(border=True):
        _panel_confirmar_importacion(id_carga=id_carga)