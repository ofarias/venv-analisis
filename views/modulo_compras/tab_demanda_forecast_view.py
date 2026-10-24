from __future__ import annotations

import math
import os
from datetime import date, datetime
from io import BytesIO

import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, DataReturnMode, GridOptionsBuilder, JsCode

from controllers.forecast_controller import (
    obtener_forecast_versiones_ctrl,
    clientes_por_producto_ctrl,
    _catalogo_productos_sae,
)
from controllers.forecast_autorizacion_controller import (
    calcular_necesidad_compra_consolidada_ctrl,
    desglosar_necesidad_mp_ctrl,
)
from controllers.compras_solicitudes_controller import (
    obtener_tipo_compra_mp_inventario_ctrl,
    crear_solicitud_mp_inventario_ctrl,
    obtener_mp_con_solicitud_ctrl,
)
from settings import BASE_DIR


_MESES = {1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
          7: "jul", 8: "ago", 9: "sep", 10: "oct", 11: "nov", 12: "dic"}

_ORIGEN_BADGE = {
    "autorizado": "✅ autorizado",
    "presupuesto (fallback)": "🟡 presupuesto (pendiente de autorizar)",
}
# mismo texto sin emoji — ReportLab/Helvetica no trae glifos de emoji, salen
# como un cuadro negro en el PDF
_ORIGEN_LABEL_PDF = {
    "autorizado": "Autorizado",
    "presupuesto (fallback)": "Presupuesto (pendiente de autorizar)",
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

# por cada mes se repiten estas 5 columnas. Resultado = Stock - Forecast + DP
# (sin acotar a 0, puede quedar negativo) y ES el Stock del mes siguiente —
# el arrastre real. "DP" es solo informativo (lo que ya está planeado/
# cubierto por forecast de compra o presupuesto autorizado); "Orden Sugerida"
# es el valor accionable para Compras (ver utils/forecast_engine.py::
# calcular_necesidad_compra_dp_producto para el faltante mes a mes). Ninguno
# de los dos participa en el arrastre, que siempre usa Resultado.
_SUFIJOS_MES = [
    ("Stock", "existencia_inicio"),
    ("Forecast", "venta_forecast"),
    ("DP (info)", "compra_cubierta"),
    ("Resultado", "resultado"),
    ("Orden Sugerida", "necesidad"),
]


def _meses_cobertura_resurtido(tiempo_resurtido) -> int:
    """Cuántos meses hacia adelante cubre un pedido colocado hoy, según el
    tiempo de resurtido del producto (SAE, días) — redondeado hacia arriba a
    meses completos. Sin dato o 0, se asume 1 mes (el actual nada más)."""
    if tiempo_resurtido is None or pd.isna(tiempo_resurtido) or tiempo_resurtido <= 0:
        return 1
    return max(1, math.ceil(float(tiempo_resurtido) / 30))

_VALUE_FORMATTER_MILES_JS = JsCode("""
function(params) {
    if (params.value === null || params.value === undefined || params.value === '') return '';
    return Number(params.value).toLocaleString('en-US', {minimumFractionDigits: 0, maximumFractionDigits: 0});
}
""")

_VALUE_FORMATTER_USD_JS = JsCode("""
function(params) {
    if (params.value === null || params.value === undefined || params.value === '') return '';
    return '$' + Number(params.value).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
}
""")

# resalta en rojo un Resultado negativo (déficit arrastrado) y en verde uno
# positivo — igual criterio verde/rojo que el resto de la app
_CELL_STYLE_RESULTADO_JS = JsCode("""
function(params) {
    if (params.value < 0) {
        return {backgroundColor: '#f8d7da', color: '#721c24', fontWeight: 'bold'};
    }
    if (params.value > 0) {
        return {backgroundColor: '#d4edda', color: '#155724'};
    }
    return null;
}
""")


def _construir_tabla_mensual(df_f: pd.DataFrame, meses_sel: list[int]) -> pd.DataFrame:
    """Pivotea el detalle largo (cve_prod × mes) a una fila por producto, con
    5 columnas por cada mes seleccionado (arrastre ya resuelto por el motor)
    y una columna final de necesidad total del período.

    "Orden Sugerida" solo se muestra en el primer mes (el actual): un pedido
    colocado hoy tarda `tiempo_resurtido` días en llegar, así que debe cubrir
    no solo el faltante de este mes sino el de los meses siguientes que
    transcurran mientras llega — se suma el faltante (columna "necesidad") de
    esos meses y se coloca todo en el mes actual; los meses siguientes
    quedan en 0 en esta columna (ya están cubiertos por ese pedido)."""
    base = (
        df_f.drop_duplicates("cve_prod")
        .set_index("cve_prod")[["producto", "tiempo_resurtido", "linea", "origen_forecast", "vendedores"]]
    )
    necesidad_total_por_prod = df_f.groupby("cve_prod")["necesidad"].sum()
    meses_ordenados = sorted(meses_sel)

    filas = []
    for cve, info in base.iterrows():
        fila = {
            "cve_prod": cve,
            "producto": info["producto"],
            "tiempo_resurtido": info["tiempo_resurtido"],
            "linea": info["linea"],
            "origen": _ORIGEN_BADGE.get(info["origen_forecast"], info["origen_forecast"]),
            "vendedores": info["vendedores"],
        }
        sub = df_f[df_f["cve_prod"] == cve].set_index("mes")

        meses_cobertura = _meses_cobertura_resurtido(info["tiempo_resurtido"])
        meses_orden_sugerida = set(meses_ordenados[:meses_cobertura])
        orden_sugerida_total = sum(
            float(sub.loc[m, "necesidad"]) for m in meses_orden_sugerida if m in sub.index
        )
        mes_actual = meses_ordenados[0] if meses_ordenados else None

        for mes in meses_sel:
            mn = _MESES[mes].upper()
            fila_mes = sub.loc[mes] if mes in sub.index else None
            for etiqueta, campo in _SUFIJOS_MES:
                if etiqueta == "Orden Sugerida":
                    valor = orden_sugerida_total if mes == mes_actual else 0.0
                else:
                    valor = float(fila_mes[campo]) if fila_mes is not None else 0.0
                fila[f"{mn} {etiqueta}"] = valor
        fila["Necesidad total"] = float(necesidad_total_por_prod.get(cve, 0.0))
        filas.append(fila)

    return pd.DataFrame(filas)


def _construir_tabla_necesidad_mensual(df_f: pd.DataFrame, meses_sel: list[int]) -> pd.DataFrame:
    """Necesidad (faltante proyectado) por producto × mes, SIN la
    concentración en el mes actual que aplica "Orden Sugerida" en la tabla
    principal — para el reporte se quiere ver el faltante real de cada mes
    individual, con su total y de dónde sale cada número (origen/vendedores).

    "Stock hoy" es la existencia real (SAE, almacén 17) con la que arrancó
    el cálculo — el mismo valor que usa el motor como `existencia_inicio`
    del primer mes seleccionado; un producto puede dar Total 0 con toda
    normalidad si ese stock ya alcanza para cubrir la venta proyectada de
    todo el período (sin que haga falta comprar nada todavía) — esos
    productos se excluyen del reporte: solo se listan los que sí hay que
    solicitar.

    Se ordena por línea (unidad de negocio) y, dentro de cada línea,
    alfabéticamente por producto — así el reporte PDF puede agrupar una
    tabla por línea en ese mismo orden."""
    cols_base = ["producto", "linea", "tiempo_resurtido", "origen_forecast", "vendedores"]
    base = (
        df_f.drop_duplicates("cve_prod")
        .set_index("cve_prod")[[c for c in cols_base if c in df_f.columns]]
    )
    mes_actual = min(meses_sel) if meses_sel else None
    filas = []
    for cve, info in base.iterrows():
        sub = df_f[df_f["cve_prod"] == cve].set_index("mes")
        stock_hoy = float(sub.loc[mes_actual, "existencia_inicio"]) if mes_actual in sub.index else 0.0
        linea = str(info.get("linea") or "").strip() or "(sin línea SAE)"
        tiempo_resurtido = info.get("tiempo_resurtido")
        fila = {
            "cve_prod": cve, "producto": info["producto"], "linea": linea,
            "tiempo_resurtido": tiempo_resurtido, "Stock hoy": stock_hoy,
        }
        total = 0.0
        for mes in meses_sel:
            mn = _MESES[mes].upper()
            valor = float(sub.loc[mes, "necesidad"]) if mes in sub.index else 0.0
            fila[mn] = valor
            total += valor
        fila["Total"] = total
        fila["origen"] = info["origen_forecast"]
        fila["vendedores"] = info["vendedores"]
        if total > 0:
            filas.append(fila)
    if not filas:
        return pd.DataFrame(columns=["cve_prod", "producto", "linea", "tiempo_resurtido", "Stock hoy", "Total", "origen", "vendedores"])
    return (
        pd.DataFrame(filas)
        .sort_values(["linea", "producto"], key=lambda s: s.astype(str).str.upper())
        .reset_index(drop=True)
    )


def _generar_reporte_necesidad_pdf(
    tabla_nec: pd.DataFrame, meses_sel: list[int], anio_sel: int,
    kpis: dict, filtros_resumen: str,
) -> bytes:
    """Reporte de necesidad de compra por mes (una fila por producto), con
    total del período, origen del forecast y vendedor(es) — para compartir
    con Compras/dirección sin tener que leer la tabla completa en pantalla."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(letter),
        leftMargin=1.0 * cm, rightMargin=1.0 * cm, topMargin=1.2 * cm, bottomMargin=1.2 * cm,
    )
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=18, spaceAfter=2)
    meta = ParagraphStyle("meta", parent=styles["Normal"], fontSize=8.5, textColor=colors.HexColor("#4a505c"), spaceAfter=10)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=12.5, spaceBefore=10, spaceAfter=6)
    celda = ParagraphStyle("celda", parent=styles["Normal"], fontSize=7.5, leading=9)
    celda_header = ParagraphStyle("celda_header", parent=celda, textColor=colors.white)

    GRIS_HDR = colors.HexColor("#12151a")
    GRIS_LINEA = colors.HexColor("#e3e6ea")

    titulo = [
        Paragraph("Reporte de Necesidad de Compra — Demanda (Forecast)", h1),
        Paragraph(
            f"Generado: <b>{datetime.now().strftime('%d/%m/%Y %H:%M')}</b> &nbsp;·&nbsp; "
            f"Año {anio_sel} &nbsp;·&nbsp; Filtros: {filtros_resumen or 'sin filtros adicionales'}",
            meta,
        ),
    ]

    logo_path = os.path.join(BASE_DIR, "assets", "biotecsaicon.png")
    if os.path.exists(logo_path):
        try:
            from PIL import Image as PILImage
            with PILImage.open(logo_path) as im:
                im.thumbnail((300, 300))
                ancho_px, alto_px = im.size
                buf_logo = BytesIO()
                im.convert("RGBA").save(buf_logo, format="PNG")
                buf_logo.seek(0)
            alto_logo = 2.0 * cm
            ancho_logo = alto_logo * (ancho_px / alto_px)
            encabezado = Table(
                [[Image(buf_logo, width=ancho_logo, height=alto_logo), titulo]],
                colWidths=[ancho_logo + 0.4 * cm, None],
            )
            encabezado.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (0, 0), 0),
                ("RIGHTPADDING", (0, 0), (0, 0), 0),
            ]))
            story = [encabezado]
        except Exception:
            story = titulo
    else:
        story = titulo

    story.append(Spacer(1, 6))

    kpi_data = [
        ["Productos", "Necesidad total (kg)", "Productos con algún mes sin autorizar"],
        [
            f"{kpis['productos']:,}", f"{kpis['necesidad_total']:,.0f}",
            f"{kpis['productos_fallback']:,}",
        ],
    ]
    t_kpi = Table(kpi_data, colWidths=[7 * cm] * 3)
    t_kpi.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GRIS_HDR),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("FONTSIZE", (0, 1), (-1, 1), 12),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("BOX", (0, 0), (-1, -1), 0.5, GRIS_LINEA),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, GRIS_LINEA),
    ]))
    story += [t_kpi, Spacer(1, 4)]

    story.append(Paragraph("Necesidad por mes", h2))
    story.append(Paragraph(
        "Solo se listan los productos que sí hay que solicitar (Total &gt; 0) — los que ya están "
        "cubiertos por su \"Stock hoy\" (existencia real SAE, almacén 17, al momento de generar el "
        "reporte) quedan fuera. Una tabla por unidad de negocio (línea), productos en orden alfabético.",
        meta,
    ))
    if tabla_nec.empty:
        story.append(Paragraph("No hay productos pendientes de solicitar con los filtros aplicados.", styles["Normal"]))
        doc.build(story)
        return buf.getvalue()

    meses_labels = [_MESES[m].upper() for m in meses_sel]
    idx_total = 4 + len(meses_labels)
    idx_origen = idx_total + 1
    idx_vend = idx_origen + 1

    ancho_cve = 2.0 * cm
    ancho_prod = 4.0 * cm
    ancho_resurtido = 1.6 * cm
    ancho_stock = 1.6 * cm
    ancho_total = 1.8 * cm
    ancho_origen = 3.6 * cm
    ancho_vend = 3.6 * cm
    ancho_fijo = ancho_cve + ancho_prod + ancho_resurtido + ancho_stock + ancho_total + ancho_origen + ancho_vend
    ancho_mes = (doc.width - ancho_fijo) / max(len(meses_labels), 1)
    col_widths = (
        [ancho_cve, ancho_prod, ancho_resurtido, ancho_stock] + [ancho_mes] * len(meses_labels)
        + [ancho_total, ancho_origen, ancho_vend]
    )

    h_linea = ParagraphStyle("h_linea", parent=styles["Heading3"], fontSize=10.5, spaceBefore=10, spaceAfter=4)
    header = (
        [
            Paragraph("Cve Prod", celda_header), Paragraph("Producto", celda_header),
            Paragraph("T. Resurtido (días)", celda_header), Paragraph("Stock hoy", celda_header),
        ]
        + [Paragraph(m, celda_header) for m in meses_labels]
        + [Paragraph("Total", celda_header), Paragraph("Origen", celda_header), Paragraph("Vendedor(es)", celda_header)]
    )

    # tabla_nec ya viene ordenada por línea y producto (ver
    # _construir_tabla_necesidad_mensual) — se agrupa preservando ese orden,
    # sin volver a ordenar las líneas, así el reporte respeta el mismo
    # criterio alfabético en ambos niveles.
    for linea_val in tabla_nec["linea"].drop_duplicates():
        df_linea = tabla_nec[tabla_nec["linea"] == linea_val]
        story.append(Paragraph(f"{linea_val} ({len(df_linea)} producto(s))", h_linea))

        data = [header]
        for r in df_linea.to_dict("records"):
            tiempo_resurtido = r.get("tiempo_resurtido")
            resurtido_txt = f"{float(tiempo_resurtido):,.0f}" if pd.notna(tiempo_resurtido) else "—"
            fila = [
                Paragraph(str(r["cve_prod"]), celda), Paragraph(str(r["producto"]), celda),
                Paragraph(resurtido_txt, celda), Paragraph(f"{float(r['Stock hoy']):,.0f}", celda),
            ]
            for mn in meses_labels:
                valor = float(r.get(mn) or 0.0)
                fila.append(Paragraph(f"{valor:,.0f}", celda) if valor else "")
            fila.append(Paragraph(f"{float(r['Total']):,.0f}", celda))
            fila.append(Paragraph(_ORIGEN_LABEL_PDF.get(r["origen"], str(r["origen"])), celda))
            fila.append(Paragraph(str(r["vendedores"] or ""), celda))
            data.append(fila)

        t = Table(data, colWidths=col_widths, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), GRIS_HDR),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("ALIGN", (2, 0), (idx_total, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("GRID", (0, 0), (-1, -1), 0.3, GRIS_LINEA),
            ("FONTNAME", (idx_total, 1), (idx_total, -1), "Helvetica-Bold"),
            ("BACKGROUND", (idx_total, 1), (idx_total, -1), GRIS_LINEA),
        ]))
        story += [t, Spacer(1, 2)]

    doc.build(story)
    return buf.getvalue()


def _renderizar_desglose_mp(desglose: dict, cve_mp: str, nombre_producto: str) -> None:
    """Pinta el desglose de `desglosar_necesidad_mp_ctrl`: mes a mes, venta
    directa (si la hay) + cada producto terminado que explica la demanda vía
    fórmula, con de dónde sale la venta consolidada de ESE PT (vendedor,
    autorizado/fallback, y si es fallback qué líneas de Presupuesto de
    Ventas lo arman)."""
    st.markdown(f"#### 🔍 {cve_mp} — {nombre_producto}")
    meses = desglose.get("meses", [])
    if not meses:
        st.info("sin meses para desglosar")
        return

    for mes in meses:
        directo = desglose["directo"].get(mes, [])
        formula = desglose["formula"].get(mes, [])
        total_directo = sum(f["valor"] for f in directo)
        total_formula = sum(f["aporte"] for f in formula)
        total_mes = total_directo + total_formula

        with st.expander(
            f"{_MESES[mes].upper()} — Forecast total: {total_mes:,.2f} kg",
            expanded=(mes == meses[0]),
        ):
            if not directo and not formula:
                st.caption("sin demanda este mes.")
                continue

            if directo:
                st.markdown("**venta directa de este producto**")
                st.dataframe(
                    pd.DataFrame([
                        {"vendedor": f["vendedor"], "origen": f["origen"], "kg": f["valor"]}
                        for f in directo
                    ]),
                    hide_index=True, use_container_width=True,
                )

            if formula:
                st.markdown(
                    "**vía fórmula** — producto terminado que usa esta materia prima como insumo, "
                    "cruzado contra su propia venta consolidada y su existencia (almacén 18)"
                )
                st.dataframe(
                    pd.DataFrame([
                        {
                            "PT": f["cve_pt"], "producto": f["producto_pt"], "rol en fórmula": f["rol"],
                            "%": f["pct"], "venta forecast consolidada (kg)": f["venta_consolidada"],
                            "stock PT inicio mes (kg)": f["existencia_pt_inicio"],
                            "a producir (kg)": f["a_producir"], "aporte a esta MP (kg)": f["aporte"],
                        }
                        for f in formula
                    ]),
                    hide_index=True, use_container_width=True,
                )

                for f in formula:
                    if not f["fuentes"]:
                        continue
                    st.caption(f"**{f['cve_pt']} ({f['producto_pt']})** — de dónde sale esa venta consolidada:")
                    for fu in f["fuentes"]:
                        st.caption(f"- {fu['vendedor']} · {fu['origen']} · {fu['valor']:,.2f} kg")
                        if fu.get("lineas"):
                            st.dataframe(
                                pd.DataFrame(fu["lineas"]).rename(columns={
                                    "cliente": "cliente", "cve_clie": "cve cliente", "cantidad_kg": "kg",
                                }),
                                hide_index=True, use_container_width=True,
                            )


def mostrar_tab_demanda_forecast() -> None:
    st.caption(
        "Necesidad de **materia prima** consolidada de todos los vendedores — los productos "
        "terminados (con fórmula registrada) se cruzan contra su fórmula y su existencia de "
        "PT (almacén 18) para traducir su venta en materia prima requerida; esta tabla solo "
        "muestra materia prima (cve_prod que inicia con \"B\"), nunca producto terminado. "
        "Usa el forecast de venta/compra ya autorizado de cada vendedor para el mes (o su "
        "presupuesto ya autorizado si todavía no autoriza ese mes), contra la existencia "
        "real de materia prima (almacén 17)."
    )

    hoy = date.today()
    df_versiones = obtener_forecast_versiones_ctrl(usuario_id=0, ver_todas=True)
    anios_disponibles = sorted(
        {int(a) for a in df_versiones["anio"].dropna().unique()} if df_versiones is not None and not df_versiones.empty else set(),
        reverse=True,
    )
    if not anios_disponibles:
        anios_disponibles = [hoy.year]
    elif hoy.year not in anios_disponibles:
        anios_disponibles = sorted(set(anios_disponibles) | {hoy.year}, reverse=True)

    idx_anio_actual = anios_disponibles.index(hoy.year)

    col_anio, col_meses = st.columns([1, 3])
    with col_anio:
        anio_sel = st.selectbox("año", anios_disponibles, index=idx_anio_actual, key="comp_fc_anio")
    with col_meses:
        # necesidad del mes actual en adelante por defecto — sin meses ya
        # pasados que no aportan nada a la compra
        meses_default = [m for m in range(1, 13) if anio_sel > hoy.year or m >= hoy.month]
        meses_sel = st.multiselect(
            "meses", options=list(range(1, 13)), default=meses_default,
            format_func=lambda m: _MESES[m].upper(), key="comp_fc_meses",
        )

    if anio_sel == hoy.year:
        meses_sel = [m for m in meses_sel if m >= hoy.month]
    meses_sel = sorted(meses_sel)
    if not meses_sel:
        st.info("no hay meses vigentes (mes actual en adelante) entre los meses seleccionados")
        return

    with st.spinner("consolidando necesidad de compra de todos los vendedores…"):
        df = calcular_necesidad_compra_consolidada_ctrl(anio=int(anio_sel), meses=meses_sel)

    if df is None or df.empty:
        st.warning(
            "no se encontró necesidad de compra consolidada. Posibles causas:\n"
            "- Ningún vendedor tiene forecast o presupuesto autorizado para ese año\n"
            "- No hay forecast_versiones creadas para ese año"
        )
        return

    # línea (unidad de negocio) y tiempo de resurtido (SAE inve01.tiem_surt,
    # en días) por producto, vía catálogo SAE
    try:
        df_cat = _catalogo_productos_sae()
    except Exception:
        df_cat = pd.DataFrame()
    mapa_linea: dict = {}
    mapa_resurtido: dict = {}
    if df_cat is not None and not df_cat.empty and "cve_art" in df_cat.columns:
        cve_cat = df_cat["cve_art"].astype(str).str.strip()
        if "linea" in df_cat.columns:
            mapa_linea = dict(zip(cve_cat, df_cat["linea"].astype(str).str.strip()))
        if "tiem_surt" in df_cat.columns:
            mapa_resurtido = dict(zip(cve_cat, pd.to_numeric(df_cat["tiem_surt"], errors="coerce")))
    df = df.copy()
    df["linea"] = df["cve_prod"].astype(str).str.strip().map(mapa_linea).fillna("")
    df["tiempo_resurtido"] = df["cve_prod"].astype(str).str.strip().map(mapa_resurtido)

    # cliente(s) por producto, vía líneas autorizadas de presupuesto de ventas
    # del año/meses seleccionados (mismo criterio que Forecast → MDI/Necesidades)
    df_clientes = clientes_por_producto_ctrl(int(anio_sel), meses=tuple(meses_sel))
    clientes_por_prod: dict[str, set] = {}
    if df_clientes is not None and not df_clientes.empty:
        for r in df_clientes.to_dict("records"):
            cve = str(r.get("cve_prod") or "").strip()
            cliente = str(r.get("cliente_excel") or "").strip()
            if cve and cliente:
                clientes_por_prod.setdefault(cve, set()).add(cliente)

    # vendedor(es) por producto — ya viene como texto "A, B" en la columna
    # "vendedores" del consolidado (una fila por mes, el valor se repite)
    vendedores_por_prod: dict[str, set] = {
        str(r["cve_prod"]).strip(): {v.strip() for v in str(r.get("vendedores") or "").split(",") if v.strip()}
        for r in df.drop_duplicates("cve_prod").to_dict("records")
    }

    col_cve, col_prod, col_linea = st.columns(3)
    with col_cve:
        cve_sel = st.multiselect(
            "cve prod", options=sorted(df["cve_prod"].unique()), default=[], key="comp_fc_cve",
        )
    with col_prod:
        prod_sel = st.multiselect(
            "producto", options=sorted(df["producto"].unique()), default=[], key="comp_fc_prod",
        )
    with col_linea:
        lineas_disponibles = sorted({l for l in df["linea"].unique() if l})
        linea_sel = st.multiselect(
            "unidad de negocio (línea)", options=lineas_disponibles, default=[], key="comp_fc_linea",
        )

    col_cliente, col_vendedor, col_origen = st.columns(3)
    with col_cliente:
        clientes_disponibles = sorted({c for cs in clientes_por_prod.values() for c in cs})
        cliente_sel = st.multiselect(
            "cliente", options=clientes_disponibles, default=[], key="comp_fc_cliente",
        )
    with col_vendedor:
        vendedores_disponibles = sorted({v for vs in vendedores_por_prod.values() for v in vs})
        vendedor_sel = st.multiselect(
            "vendedor", options=vendedores_disponibles, default=[], key="comp_fc_vendedor",
        )
    with col_origen:
        origen_sel = st.multiselect(
            "origen", options=["autorizado", "presupuesto (fallback)"],
            default=[], key="comp_fc_origen",
            format_func=lambda o: _ORIGEN_BADGE.get(o, o),
        )

    df_f = df
    if cve_sel:
        df_f = df_f[df_f["cve_prod"].isin(cve_sel)]
    if prod_sel:
        df_f = df_f[df_f["producto"].isin(prod_sel)]
    if linea_sel:
        df_f = df_f[df_f["linea"].isin(linea_sel)]
    if cliente_sel:
        cve_match_cliente = {cve for cve, cs in clientes_por_prod.items() if cs & set(cliente_sel)}
        df_f = df_f[df_f["cve_prod"].isin(cve_match_cliente)]
    if vendedor_sel:
        cve_match_vendedor = {cve for cve, vs in vendedores_por_prod.items() if vs & set(vendedor_sel)}
        df_f = df_f[df_f["cve_prod"].isin(cve_match_vendedor)]
    if origen_sel:
        df_f = df_f[df_f["origen_forecast"].isin(origen_sel)]

    if df_f.empty:
        st.info("sin resultados para los filtros seleccionados")
        return

    productos_fallback = df_f.loc[df_f["origen_forecast"] == "presupuesto (fallback)", "cve_prod"].nunique()
    necesidad_total = float(df_f["necesidad"].sum())
    c1, c2, c3 = st.columns(3)
    c1.metric("productos", df_f["cve_prod"].nunique())
    c2.metric("necesidad total del período (kg)", f"{necesidad_total:,.0f}")
    c3.metric("productos con algún mes sin autorizar", productos_fallback)

    filtros_partes = [f"Año {anio_sel}", f"Meses {', '.join(_MESES[m].upper() for m in meses_sel)}"]
    if cve_sel:
        filtros_partes.append(f"Cve prod: {', '.join(cve_sel)}")
    if prod_sel:
        filtros_partes.append(f"Producto: {', '.join(prod_sel)}")
    if linea_sel:
        filtros_partes.append(f"Línea: {', '.join(linea_sel)}")
    if cliente_sel:
        filtros_partes.append(f"Cliente: {', '.join(cliente_sel)}")
    if vendedor_sel:
        filtros_partes.append(f"Vendedor: {', '.join(vendedor_sel)}")
    if origen_sel:
        filtros_partes.append(f"Origen: {', '.join(_ORIGEN_BADGE.get(o, o) for o in origen_sel)}")
    filtros_resumen = " · ".join(filtros_partes)

    pdf_key = f"comp_fc_pdf_bytes_{anio_sel}"
    if st.button("📄 preparar reporte de necesidad por mes (PDF)", key="comp_fc_btn_pdf"):
        with st.spinner("generando PDF…"):
            # solo productos que sí hay que solicitar (Total > 0) — los que
            # ya están cubiertos por su stock actual se excluyen del reporte
            tabla_nec = _construir_tabla_necesidad_mensual(df_f, meses_sel)
            productos_fallback_nec = (
                int((tabla_nec["origen"] == "presupuesto (fallback)").sum()) if not tabla_nec.empty else 0
            )
            st.session_state[pdf_key] = _generar_reporte_necesidad_pdf(
                tabla_nec, meses_sel, int(anio_sel),
                {
                    "productos": int(len(tabla_nec)),
                    "necesidad_total": float(tabla_nec["Total"].sum()) if not tabla_nec.empty else 0.0,
                    "productos_fallback": productos_fallback_nec,
                },
                filtros_resumen,
            )
    pdf_bytes = st.session_state.get(pdf_key)
    if pdf_bytes:
        st.download_button(
            "⬇️ descargar reporte de necesidad (PDF)",
            data=pdf_bytes,
            file_name=f"necesidad_compra_por_mes_{anio_sel}.pdf",
            mime="application/pdf",
            key="comp_fc_pdf_dl",
        )

    st.divider()
    st.markdown("### 🛒 generar solicitud de compra")
    meses_ventana = sorted(meses_sel)[:3]
    meses_ventana_txt = ", ".join(_MESES[m].upper() for m in meses_ventana)
    st.caption(
        "Arma una Solicitud de Compra (tipo *Materia Prima (Inventario)*) con la necesidad "
        f"calculada arriba, acotada a los próximos {len(meses_ventana)} meses "
        f"({meses_ventana_txt} — lo que tarda en llegar un pedido). Desmarca lo que no quieras "
        "incluir y ajusta la **Cant. a Solicitar** de cada mes antes de guardar; lo que ya tiene "
        "solicitud pendiente no se vuelve a proponer."
    )

    preview_key = f"comp_fc_solicitud_preview_{anio_sel}"
    obs_key = f"comp_fc_solicitud_obs_{anio_sel}"
    if st.button("🛒 generar solicitud de compra", key="comp_fc_btn_generar_solicitud"):
        df_nec = df_f[
            (pd.to_numeric(df_f["necesidad"], errors="coerce") > 0)
            & (df_f["mes"].isin(meses_ventana))
        ].copy()

        df_pend_existente = obtener_mp_con_solicitud_ctrl(int(anio_sel), meses_ventana)
        ya_pedidos = set()
        if df_pend_existente is not None and not df_pend_existente.empty:
            ya_pedidos = {
                (str(r["cve_mp"]).strip(), int(r["mes"]))
                for r in df_pend_existente.to_dict("records")
            }
        excluidos = 0
        if ya_pedidos and not df_nec.empty:
            mask_ya = df_nec.apply(
                lambda r: (str(r["cve_prod"]).strip(), int(r["mes"])) in ya_pedidos, axis=1,
            )
            excluidos = int(mask_ya.sum())
            df_nec = df_nec[~mask_ya]

        if df_nec.empty:
            st.session_state.pop(preview_key, None)
            st.session_state.pop(obs_key, None)
            if excluidos:
                st.warning(
                    f"los {excluidos} renglón(es) con necesidad en {meses_ventana_txt} ya tienen "
                    "una solicitud de compra pendiente — no se vuelven a proponer."
                )
            else:
                st.warning(f"no hay productos con necesidad > 0 en {meses_ventana_txt} para generar una solicitud")
        else:
            filas_por_prod: dict[str, dict] = {}
            obs_por_prod: dict[str, dict[int, str]] = {}
            for r in df_nec.to_dict("records"):
                cve = r["cve_prod"]
                mes = int(r["mes"])
                mn = _MESES[mes].upper()
                origen_txt = _ORIGEN_LABEL_PDF.get(r["origen_forecast"], str(r["origen_forecast"]))
                linea_txt = str(r.get("linea") or "").strip() or "(sin línea SAE)"
                if cve not in filas_por_prod:
                    fila_nueva = {
                        "cve_mp": cve,
                        "mp_nombre": r["producto"],
                        "linea": linea_txt,
                        "tiempo_resurtido": r.get("tiempo_resurtido"),
                        "precio_usd": 0.0,
                    }
                    # columnas de mes pre-sembradas en orden cronológico —
                    # si no, la columna queda insertada en el dict (y luego
                    # en el DataFrame) en el orden en que aparece cada fila
                    # de df_nec, no en orden de mes (ej. OCT se corre al
                    # final si un producto no tenía necesidad en OCT pero sí
                    # en NOV/DIC y esas filas se procesan primero)
                    for m in meses_ventana:
                        mn2 = _MESES[m].upper()
                        fila_nueva[f"{mn2} Cant. Requerida"] = 0.0
                        fila_nueva[f"{mn2} Cant. a Solicitar"] = 0.0
                    filas_por_prod[cve] = fila_nueva
                    obs_por_prod[cve] = {}
                necesidad_val = round(float(r["necesidad"]), 2)
                filas_por_prod[cve][f"{mn} Cant. Requerida"] = necesidad_val
                filas_por_prod[cve][f"{mn} Cant. a Solicitar"] = necesidad_val
                obs_por_prod[cve][mes] = (
                    f"{mn}: Línea {linea_txt} · Origen {origen_txt} · "
                    f"Vendedor(es) {r.get('vendedores') or '-'}"
                )

            filas_propuesta = []
            for cve, fila in filas_por_prod.items():
                for m in meses_ventana:
                    mn = _MESES[m].upper()
                    fila.setdefault(f"{mn} Cant. Requerida", 0.0)
                    fila.setdefault(f"{mn} Cant. a Solicitar", 0.0)
                fila["Total Requerido"] = round(
                    sum(fila[f"{_MESES[m].upper()} Cant. Requerida"] for m in meses_ventana), 2,
                )
                fila["Total a Solicitar"] = round(
                    sum(fila[f"{_MESES[m].upper()} Cant. a Solicitar"] for m in meses_ventana), 2,
                )
                fila["Costo Total USD"] = round(fila["Total a Solicitar"] * float(fila.get("precio_usd") or 0.0), 2)
                fila["Trazabilidad"] = " | ".join(
                    obs_por_prod[cve][m] for m in meses_ventana if m in obs_por_prod[cve]
                )
                filas_propuesta.append(fila)

            st.session_state[preview_key] = pd.DataFrame(filas_propuesta)
            st.session_state[obs_key] = obs_por_prod
            if excluidos:
                st.info(
                    f"{excluidos} renglón(es) con necesidad ya tenían solicitud pendiente y se "
                    "excluyeron automáticamente de esta propuesta."
                )

    df_preview = st.session_state.get(preview_key)
    if df_preview is not None and not df_preview.empty:
        col_req = [f"{_MESES[m].upper()} Cant. Requerida" for m in meses_ventana]
        col_sol = [f"{_MESES[m].upper()} Cant. a Solicitar" for m in meses_ventana]

        gb = GridOptionsBuilder.from_dataframe(df_preview)
        gb.configure_grid_options(autoSizeStrategy=None)
        gb.configure_default_column(
            editable=False, resizable=True, filter=True, sortable=True,
            wrapHeaderText=True, autoHeaderHeight=True,
        )
        gb.configure_side_bar()
        gb.configure_selection(
            selection_mode="multiple", use_checkbox=True, header_checkbox=True,
            # pre_select_all_rows es código muerto en esta versión de
            # st_aggrid (está comentado en la librería) — hay que usar
            # pre_selected_rows con los índices explícitos para que todas
            # las filas arranquen incluidas por default.
            pre_selected_rows=list(range(len(df_preview))),
        )
        gb.configure_column("cve_mp", headerName="cve MP", pinned="left", width=110)
        gb.configure_column("mp_nombre", headerName="Materia Prima", pinned="left", width=220)
        gb.configure_column("linea", headerName="línea", pinned="left", width=130)
        gb.configure_column(
            "tiempo_resurtido", headerName="tiempo resurtido (días)", width=130,
            type=["numericColumn"], valueFormatter=_VALUE_FORMATTER_MILES_JS,
        )
        gb.configure_column(
            "precio_usd", headerName="Precio USD (por kg)", pinned="left", width=140,
            type=["numericColumn"], editable=True, cellEditor="agNumberCellEditor",
            valueFormatter=_VALUE_FORMATTER_USD_JS,
            cellStyle=JsCode("function(p){return {backgroundColor:'#fff8e1'};}"),
        )
        for c in col_req:
            gb.configure_column(c, type=["numericColumn"], width=120, valueFormatter=_VALUE_FORMATTER_MILES_JS)
        for c in col_sol:
            gb.configure_column(
                c, type=["numericColumn"], width=120, editable=True,
                cellEditor="agNumberCellEditor", valueFormatter=_VALUE_FORMATTER_MILES_JS,
                cellStyle=JsCode("function(p){return {backgroundColor:'#fff8e1'};}"),
            )
        gb.configure_column(
            "Total Requerido", type=["numericColumn"], width=130, valueFormatter=_VALUE_FORMATTER_MILES_JS,
        )
        # suma calculada en el navegador — se recalcula sola al editar
        # cualquier "Cant. a Solicitar" del mes, sin ida y vuelta a Python
        _suma_col_sol_js = " + ".join(f"(Number(params.data['{c}']) || 0)" for c in col_sol)
        gb.configure_column(
            "Total a Solicitar", type=["numericColumn"], width=130, valueFormatter=_VALUE_FORMATTER_MILES_JS,
            valueGetter=JsCode(f"""
            function(params) {{
                return Math.round(({_suma_col_sol_js}) * 100) / 100;
            }}
            """),
        )
        # Costo Total USD se recalcula en el navegador (como Total a
        # Solicitar) a partir de las Cant. a Solicitar vigentes × Precio USD
        # — no se puede leer el campo "Total a Solicitar" porque ese es él
        # mismo un valueGetter (no se escribe de vuelta en params.data al
        # editar), así que se vuelve a sumar aquí para no quedar atrás de un
        # render.
        gb.configure_column(
            "Costo Total USD", type=["numericColumn"], width=150, valueFormatter=_VALUE_FORMATTER_USD_JS,
            valueGetter=JsCode(f"""
            function(params) {{
                var total_kg = {_suma_col_sol_js};
                var precio = Number(params.data['precio_usd']) || 0;
                return Math.round(total_kg * precio * 100) / 100;
            }}
            """),
        )
        gb.configure_column("Trazabilidad", width=320, wrapText=True, autoHeight=True)

        cols_orden_preview = (
            ["cve_mp", "mp_nombre", "linea", "tiempo_resurtido", "precio_usd"]
            + [c for par in zip(col_req, col_sol) for c in par]
            + ["Total Requerido", "Total a Solicitar", "Costo Total USD", "Trazabilidad"]
        )

        grid_resp = AgGrid(
            df_preview[cols_orden_preview],
            gridOptions=gb.build(),
            update_on=[("cellValueChanged", 600)],
            data_return_mode=DataReturnMode.AS_INPUT,
            fit_columns_on_grid_load=False,
            allow_unsafe_jscode=True,
            enable_enterprise_modules=True,
            height=min(56 + len(df_preview) * 35, 500),
            key=f"comp_fc_solicitud_grid_{anio_sel}",
        )

        df_actual = pd.DataFrame(grid_resp.get("data", []))
        if not df_actual.empty:
            st.session_state[preview_key] = df_actual

        # AgGridReturn.selected_rows: None si no hay nada seleccionado, si no
        # un DataFrame (nunca una lista de dicts, pese a lo que sugiere el
        # nombre) — ver st_aggrid/AgGridReturn.py
        seleccionadas = grid_resp.get("selected_rows")
        cves_incluidos = (
            set(seleccionadas["cve_mp"].astype(str)) if isinstance(seleccionadas, pd.DataFrame) else set()
        )

        col_g1, col_g2 = st.columns(2)
        with col_g1:
            if st.button(
                "💾 guardar solicitud", type="primary", use_container_width=True,
                key=f"comp_fc_btn_guardar_solicitud_{anio_sel}",
            ):
                df_incluidas = df_actual[df_actual["cve_mp"].astype(str).isin(cves_incluidos)] if not df_actual.empty else df_actual
                obs_por_prod = st.session_state.get(obs_key) or {}
                detalle = []
                for _, r in df_incluidas.iterrows():
                    cve = str(r["cve_mp"])
                    precio_usd = float(r.get("precio_usd") or 0.0)
                    for m in meses_ventana:
                        mn = _MESES[m].upper()
                        cantidad = float(r.get(f"{mn} Cant. a Solicitar") or 0.0)
                        if cantidad <= 0:
                            continue
                        cantidad_requerida = float(r.get(f"{mn} Cant. Requerida") or 0.0)
                        obs = (obs_por_prod.get(cve) or {}).get(m, f"{mn}: generado desde Demanda (Forecast)")
                        detalle.append({
                            "cve_mp": cve,
                            "mp_nombre": str(r["mp_nombre"]),
                            "linea": str(r.get("linea") or ""),
                            "cantidad_kg": cantidad,
                            "cantidad_requerida_kg": cantidad_requerida,
                            "precio_usd": precio_usd if precio_usd > 0 else None,
                            "existencia_mp_kg": None,
                            "anio": int(anio_sel),
                            "mes": m,
                            "id_version_forecast": None,
                            "observaciones": obs,
                        })

                if not detalle:
                    st.warning("no hay renglones incluidos con cantidad a solicitar > 0")
                else:
                    tipo_mp_inv = obtener_tipo_compra_mp_inventario_ctrl()
                    if not tipo_mp_inv:
                        st.error(
                            "no existe el tipo de compra 'Materia Prima (Inventario)' activo — "
                            "revisa Compras → Catálogos."
                        )
                    else:
                        ok, mensaje = crear_solicitud_mp_inventario_ctrl(
                            id_tipo_compra=int(tipo_mp_inv["id_tipo_compra"]),
                            fecha_solicitud=date.today(),
                            solicitante=_get_solicitante_actual(),
                            observaciones_generales=(
                                "Solicitud generada desde Compras → Demanda (Forecast) — "
                                f"año {anio_sel}, meses {meses_ventana_txt}"
                            ),
                            detalle=detalle,
                        )
                        if ok:
                            st.success(
                                f"{mensaje}. Ve a Solicitudes → Pendientes para revisarla y "
                                "enviarla a autorización."
                            )
                            st.session_state.pop(preview_key, None)
                            st.session_state.pop(obs_key, None)
                            st.rerun()
                        else:
                            st.error(mensaje)
        with col_g2:
            if st.button(
                "cancelar", use_container_width=True,
                key=f"comp_fc_btn_cancelar_solicitud_{anio_sel}",
            ):
                st.session_state.pop(preview_key, None)
                st.session_state.pop(obs_key, None)
                st.rerun()

    st.divider()
    st.caption(
        "🔒 cve prod, producto, tiempo de resurtido y línea quedan fijos al hacer scroll — "
        "Resultado = Stock - Forecast + DP (si queda en rojo/negativo, se arrastra "
        "como déficit al mes siguiente) — DP (info) es solo informativo (lo ya planeado). "
        "**Orden Sugerida solo aparece en el mes actual**: suma el faltante de ese mes y de "
        "los siguientes que transcurran mientras llega el pedido, según el tiempo de "
        "resurtido del producto (ej. 60 días = 2 meses) — los meses siguientes quedan en 0, "
        "ya cubiertos por ese pedido."
    )
    tabla = _construir_tabla_mensual(df_f, meses_sel).sort_values("Necesidad total", ascending=False)

    # qué (producto, mes) ya tiene una solicitud de compra viva (cualquier
    # estatus salvo rechazada) — evita proponerla otra vez/duplicarla; si ya
    # se generó en SAE (cve_doc_sae) se muestra el folio en vez del estatus
    df_con_solicitud = obtener_mp_con_solicitud_ctrl(int(anio_sel), meses_sel)
    solicitudes_por_prod: dict[str, list[str]] = {}
    if df_con_solicitud is not None and not df_con_solicitud.empty:
        for r in df_con_solicitud.to_dict("records"):
            cve = str(r.get("cve_mp") or "").strip()
            mn = _MESES.get(int(r.get("mes") or 0), "").upper()
            folio = str(r.get("folio_sae") or "").strip()
            estatus = str(r.get("estatus") or "").strip()
            id_sol = r.get("id_solicitud_compra")
            if folio:
                etiqueta = f"{mn} (SAE folio {folio})"
            else:
                etiqueta = f"{mn} ({estatus}, sol. #{id_sol})"
            if cve and mn:
                solicitudes_por_prod.setdefault(cve, []).append(etiqueta)
    tabla["🛒 solicitud"] = tabla["cve_prod"].map(
        lambda c: ", ".join(solicitudes_por_prod.get(str(c).strip(), []))
    )

    cols_orden = ["cve_prod", "producto", "tiempo_resurtido", "linea"]
    cols_numericas = ["Necesidad total"]
    cols_resultado = set()
    for mes in meses_sel:
        mn = _MESES[mes].upper()
        for etiqueta, _campo in _SUFIJOS_MES:
            col = f"{mn} {etiqueta}"
            cols_orden.append(col)
            cols_numericas.append(col)
            if etiqueta == "Resultado":
                cols_resultado.add(col)
    cols_orden += ["Necesidad total", "origen", "vendedores", "🛒 solicitud"]

    tabla["tiempo_resurtido"] = pd.to_numeric(tabla["tiempo_resurtido"], errors="coerce")
    for col in cols_numericas:
        tabla[col] = pd.to_numeric(tabla[col], errors="coerce").round(0)

    tabla = tabla[cols_orden].reset_index(drop=True)

    gb = GridOptionsBuilder.from_dataframe(tabla)
    gb.configure_default_column(editable=False, resizable=True, width=110)
    gb.configure_column("cve_prod", headerName="cve prod", pinned="left", width=110)
    gb.configure_column("producto", headerName="producto", pinned="left", width=200)
    gb.configure_column(
        "tiempo_resurtido", headerName="tiempo resurtido (días)", pinned="left", width=140,
        type=["numericColumn"], valueFormatter=_VALUE_FORMATTER_MILES_JS,
    )
    gb.configure_column("linea", headerName="línea", pinned="left", width=120)
    gb.configure_column("origen", headerName="origen del forecast", width=200)
    gb.configure_column("vendedores", headerName="vendedor(es)", width=220)
    gb.configure_column("🛒 solicitud", headerName="🛒 solicitud", width=220)
    for col in cols_numericas:
        cell_style = _CELL_STYLE_RESULTADO_JS if col in cols_resultado else None
        gb.configure_column(
            col, type=["numericColumn"],
            valueFormatter=_VALUE_FORMATTER_MILES_JS,
            cellStyle=cell_style,
        )

    AgGrid(
        tabla,
        gridOptions=gb.build(),
        update_on=[],
        data_return_mode=DataReturnMode.AS_INPUT,
        fit_columns_on_grid_load=False,
        allow_unsafe_jscode=True,
        enable_enterprise_modules=True,
        height=min(56 + len(tabla) * 35, 650),
        key=f"comp_fc_grid_{anio_sel}",
    )

    csv = tabla[cols_orden].to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ descargar CSV",
        data=csv,
        file_name=f"demanda_forecast_consolidada_{anio_sel}.csv",
        mime="text/csv",
        key="comp_fc_dl_csv",
    )

    st.divider()
    st.markdown("### 🔍 desglosar un producto")
    st.caption(
        "Elige una materia prima para ver, mes a mes, de dónde sale su 'Forecast': venta directa "
        "(si la vende alguien tal cual) y/o la venta consolidada del producto terminado que la usa "
        "en su fórmula — cruzada contra la existencia de ese PT — con el vendedor y origen "
        "(autorizado o presupuesto/fallback) de cada cifra, y las líneas de cliente que la arman."
    )
    opciones_desglose = {
        f"{r['cve_prod']} - {r['producto']}": r["cve_prod"]
        for r in tabla.sort_values("producto").to_dict("records")
    }
    if opciones_desglose:
        col_sel, col_btn = st.columns([3, 1])
        with col_sel:
            label_sel = st.selectbox(
                "producto a desglosar", options=list(opciones_desglose.keys()), key="comp_fc_desglose_sel",
            )
        with col_btn:
            st.write("")
            st.write("")
            desglosar_click = st.button(
                "🔍 desglosar", use_container_width=True, key="comp_fc_desglose_btn",
            )

        desglose_key = f"comp_fc_desglose_{anio_sel}"
        if desglosar_click:
            cve_mp_sel = opciones_desglose[label_sel]
            nombre_sel = label_sel.split(" - ", 1)[1] if " - " in label_sel else label_sel
            with st.spinner("calculando desglose…"):
                desglose = desglosar_necesidad_mp_ctrl(cve_mp_sel, int(anio_sel), meses_sel)
            st.session_state[desglose_key] = {
                "cve_mp": cve_mp_sel, "nombre": nombre_sel, "data": desglose,
            }

        desglose_guardado = st.session_state.get(desglose_key)
        if desglose_guardado:
            _renderizar_desglose_mp(
                desglose_guardado["data"], desglose_guardado["cve_mp"], desglose_guardado["nombre"],
            )
