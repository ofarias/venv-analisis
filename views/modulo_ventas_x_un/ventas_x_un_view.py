# views/modulo_ventas_x_un/ventas_x_un_view.py
"""Migración del reporte legado en PHP "Ventas por Unidad de Negocio"
(index.php?action=vxun). El PHP hacía una consulta SQL por unidad de
negocio en un loop y metía filas literales "Total documento"/"Total por
cliente" en la tabla de detalle; aquí se trae todo en una sola consulta
(ver models/ventas_x_un_model.py) y los subtotales por unidad/cliente/
factura se resuelven con agrupamiento nativo de AgGrid."""
from __future__ import annotations

from datetime import date
from io import BytesIO

import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder, JsCode

from controllers.ventas_x_un_controller import (
    obtener_ventas_x_un_ctrl,
    obtener_vendedores_ventas_x_un_ctrl,
    resolver_cve_vend_por_correo_ctrl,
)

_ROLES_ACCESO = {
    "ventas", "jefe de ventas", "supervisor de ventas",
    "gerente de ventas", "admin", "superadmin",
}
_ROLES_VER_TODOS = {
    "jefe de ventas", "supervisor de ventas", "gerente de ventas", "admin", "superadmin",
}


def _norm_roles_list(values) -> list[str]:
    if not values:
        return []
    if isinstance(values, str):
        values = [values]
    return [str(v).strip().lower() for v in values if str(v or "").strip()]


def _value_formatter_js(decimales: int) -> JsCode:
    return JsCode(f"""
    function(params) {{
        if (params.value === null || params.value === undefined || params.value === '') return '';
        return Number(params.value).toLocaleString('en-US',
            {{minimumFractionDigits: {decimales}, maximumFractionDigits: {decimales}}});
    }}
    """)


def _exportar_excel(df: pd.DataFrame) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="ventas_x_un")
    return output.getvalue()


def mostrar_modulo_ventas_x_un() -> None:
    st.title("📊 Ventas por Unidad de Negocio")
    st.caption(
        "Migrado del reporte legado en PHP — detalle de ventas facturadas en SAE, agrupado "
        "por unidad de negocio, cliente y factura."
    )

    usuario = st.session_state.get("usuario") or {}
    roles = set(_norm_roles_list(usuario.get("roles")))

    if not (roles & _ROLES_ACCESO):
        st.info(
            "esta pantalla es para los roles Ventas, Jefe de Ventas, Supervisor de Ventas, "
            "Gerente de Ventas, Admin o SuperAdmin."
        )
        return

    ve_todos = bool(roles & _ROLES_VER_TODOS)

    cve_vend_propio: list[str] = []
    if not ve_todos:
        correo = str(usuario.get("email") or "").strip()
        cve_vend_propio = resolver_cve_vend_por_correo_ctrl(correo)
        if not cve_vend_propio:
            st.warning(
                "no se encontró un vendedor de SAE con tu correo — pide a soporte que "
                "revise el campo CORREOE en VEND01 para tu usuario."
            )
            return

    col1, col2, col3 = st.columns(3)
    with col1:
        f_desde = st.date_input(
            "fecha desde", value=date.today().replace(day=1), format="YYYY-MM-DD", key="vxun_f_desde",
        )
    with col2:
        f_hasta = st.date_input("fecha hasta", value=date.today(), format="YYYY-MM-DD", key="vxun_f_hasta")
    with col3:
        if ve_todos:
            df_vend = obtener_vendedores_ventas_x_un_ctrl()
            opciones = {"(todos)": None}
            if df_vend is not None and not df_vend.empty:
                for r in df_vend.to_dict("records"):
                    opciones[f"{r['cve_vend']} - {r['nombre']}"] = r["cve_vend"]
            label = st.selectbox("vendedor", list(opciones.keys()), key="vxun_vendedor")
            cve_vend_sel = opciones[label]
        else:
            st.text_input("vendedor", value="(tus propias ventas)", disabled=True, key="vxun_vendedor_fijo")
            cve_vend_sel = cve_vend_propio

    if f_desde > f_hasta:
        st.error("la fecha 'desde' no puede ser mayor a 'hasta'.")
        return

    if not st.button("🔍 consultar", type="primary", key="vxun_btn_consultar"):
        st.info("configura los filtros y pulsa 'consultar'.")
        return

    with st.spinner("consultando SAE..."):
        df = obtener_ventas_x_un_ctrl(fecha_desde=f_desde, fecha_hasta=f_hasta, cve_vend=cve_vend_sel)

    if df is None or df.empty:
        st.info("sin resultados para los filtros seleccionados.")
        return

    for c in ("cantidad", "precio_mn", "precio_usd", "subtotal", "iva", "total"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)

    # ── KPIs generales ──────────────────────────────────────────────────
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Cantidad Kg", f"{df['cantidad'].sum():,.2f}")
    k2.metric("Subtotal USD", f"$ {df['precio_usd'].sum():,.2f}")
    k3.metric("IVA", f"$ {df['iva'].sum():,.2f}")
    k4.metric("Total", f"$ {df['total'].sum():,.2f}")

    # ── resumen por Unidad de Negocio ───────────────────────────────────
    st.subheader("resumen por unidad de negocio")
    resumen = (
        df.groupby(["un", "un_desc"], dropna=False)
        .agg(
            cantidad_kg=("cantidad", "sum"),
            subtotal_mn=("precio_mn", "sum"),
            subtotal_usd=("precio_usd", "sum"),
            subtotal=("subtotal", "sum"),
            iva=("iva", "sum"),
            total=("total", "sum"),
        )
        .reset_index()
        .sort_values("total", ascending=False)
    )
    resumen_fmt = resumen.rename(columns={
        "un": "UN", "un_desc": "Descripción", "cantidad_kg": "Cantidad Kg",
        "subtotal_mn": "Subtotal MN", "subtotal_usd": "Subtotal USD",
        "subtotal": "Subtotal", "iva": "IVA", "total": "Total",
    })
    st.dataframe(
        resumen_fmt.style.format({
            "Cantidad Kg": "{:,.2f}", "Subtotal MN": "$ {:,.2f}", "Subtotal USD": "$ {:,.2f}",
            "Subtotal": "$ {:,.2f}", "IVA": "$ {:,.2f}", "Total": "$ {:,.2f}",
        }),
        use_container_width=True, hide_index=True,
    )

    # ── detalle agrupado (UN > Cliente > Factura) ───────────────────────
    st.subheader("detalle de facturas")
    st.caption("agrupado por unidad de negocio, cliente y factura — expande cada nivel para ver el subtotal.")

    detalle = df.copy()
    detalle["cliente"] = detalle["clave_cliente"].fillna("") + " - " + detalle["nombre_cliente"].fillna("")

    cols_mostrar = [
        "un_desc", "cliente", "factura", "fecha_factura", "elaborada_el", "remision", "estado",
        "clave_articulo", "producto", "lote", "cantidad", "precio_mn", "moneda", "tc",
        "precio_usd", "subtotal", "iva", "total", "pedimento", "partida",
    ]
    cols_mostrar = [c for c in cols_mostrar if c in detalle.columns]
    detalle = detalle[cols_mostrar]

    encabezados = {
        "un_desc": "Unidad de Negocio", "cliente": "Cliente", "factura": "Factura",
        "fecha_factura": "Fecha Factura", "elaborada_el": "Elaborada El", "remision": "Remisión",
        "estado": "Estado", "clave_articulo": "Clave", "producto": "Producto", "lote": "Lote",
        "cantidad": "Cantidad Kg", "precio_mn": "Precio MN", "moneda": "Moneda", "tc": "TC",
        "precio_usd": "Precio USD", "subtotal": "Subtotal", "iva": "IVA", "total": "Total",
        "pedimento": "Pedimento", "partida": "Partida",
    }
    detalle = detalle.rename(columns=encabezados)

    gb = GridOptionsBuilder.from_dataframe(detalle)
    gb.configure_default_column(resizable=True, filter=True, sortable=True)
    for col in ("Unidad de Negocio", "Cliente", "Factura"):
        if col in detalle.columns:
            gb.configure_column(col, rowGroup=True, hide=True)
    for col, decimales in (
        ("Cantidad Kg", 2), ("Precio MN", 2), ("TC", 4),
        ("Precio USD", 2), ("Subtotal", 2), ("IVA", 2), ("Total", 2),
    ):
        if col in detalle.columns:
            gb.configure_column(
                col, type=["numericColumn"], aggFunc="sum", valueFormatter=_value_formatter_js(decimales),
            )
    gb.configure_grid_options(
        groupDefaultExpanded=0,
        autoGroupColumnDef={"headerName": "Unidad de Negocio / Cliente / Factura", "minWidth": 300},
    )

    AgGrid(
        detalle,
        gridOptions=gb.build(),
        allow_unsafe_jscode=True,
        fit_columns_on_grid_load=False,
        height=600,
        key="vxun_detalle_grid",
    )

    xlsx_bytes = _exportar_excel(df)
    st.download_button(
        "⬇️ descargar Excel (detalle plano)",
        data=xlsx_bytes,
        file_name=f"ventas_x_un_{f_desde}_{f_hasta}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="vxun_dl_excel",
    )
