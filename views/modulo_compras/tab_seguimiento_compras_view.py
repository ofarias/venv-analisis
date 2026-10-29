import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, DataReturnMode, GridOptionsBuilder, JsCode

from controllers.compras_solicitudes_controller import (
    obtener_solicitudes_pendientes_usuario_ctrl,
    obtener_cabecera_solicitud_compra_ctrl,
    obtener_tipo_compra_mp_inventario_ctrl,
    obtener_receptores_asignados_ctrl,
    obtener_receptores_asignados_linea_ctrl,
    obtener_detalle_solicitud_mp_inventario_ctrl,
)
from controllers.solicitudes_controller import get_usuarios_activos_ctrl

_ETIQUETA_ESTATUS = {
    "captura": "📝 captura", "enviada": "📤 enviada",
    "autorizada": "✅ autorizada", "rechazada": "❌ rechazada",
}
_ETAPAS = ["captura", "enviada", "final"]

_CELL_STYLE_ESTATUS_JS = JsCode("""
function(params) {
    var v = (params.value || '').toLowerCase();
    if (v.indexOf('autorizada') >= 0) return {backgroundColor:'#e6f4ea', color:'#1b5e20'};
    if (v.indexOf('rechazada') >= 0) return {backgroundColor:'#fbe9e9', color:'#7f0000'};
    if (v.indexOf('enviada') >= 0) return {backgroundColor:'#fdf1dd', color:'#4e342e'};
    return {backgroundColor:'#eceeec', color:'#263238'};
}
""")


def _nombres_por_usuario_ids(ids: list[int], nombre_por_id: dict) -> str:
    nombres = [nombre_por_id[i] for i in ids if i in nombre_por_id]
    return ", ".join(sorted(set(nombres))) if nombres else ""


def _resumen_mp_inventario(id_solicitud: int, nombre_por_id: dict) -> tuple[str, str]:
    """Para Materia Prima (Inventario), que se autoriza por línea: regresa
    (estatus_visual, esperando) resumiendo todas sus líneas — ej. "2 de 5
    líneas enviadas" y quién las tiene atoradas."""
    detalle = obtener_detalle_solicitud_mp_inventario_ctrl(id_solicitud)
    if detalle.empty or "estatus_linea" not in detalle.columns:
        return "—", ""

    conteo = detalle["estatus_linea"].fillna("captura").value_counts().to_dict()
    total = len(detalle)
    partes = [f"{conteo.get(e, 0)} {_ETIQUETA_ESTATUS.get(e, e)}" for e in ("captura", "enviada", "autorizada", "rechazada") if conteo.get(e, 0)]
    estatus_visual = f"{' · '.join(partes)} (de {total})"

    ids_enviadas = detalle.loc[detalle["estatus_linea"] == "enviada", "id_detalle_mp_inv"].tolist()
    receptor_ids = set()
    for id_det in ids_enviadas:
        receptor_ids.update(obtener_receptores_asignados_linea_ctrl(int(id_det)) or [])
    esperando = _nombres_por_usuario_ids(list(receptor_ids), nombre_por_id)
    if ids_enviadas and not esperando:
        esperando = "SuperAdmin / forecastAdmin"
    return estatus_visual, esperando


def _resumen_whole(id_solicitud: int, estatus: str, nombre_por_id: dict) -> tuple[str, str]:
    estatus_visual = _ETIQUETA_ESTATUS.get(estatus, estatus)
    if estatus != "enviada":
        return estatus_visual, ""
    receptor_ids = obtener_receptores_asignados_ctrl(id_solicitud) or []
    esperando = _nombres_por_usuario_ids(receptor_ids, nombre_por_id)
    if not esperando:
        esperando = "Compras MP / Compras Admin"
    return estatus_visual, esperando


def _stepper_html(etapa_actual: str) -> str:
    """Captura -> Enviada -> Autorizada/Rechazada, con flechas, resaltando
    la etapa en la que va — pedido explícito: "ponerlo con flechas"."""
    es_rechazada = etapa_actual == "rechazada"
    etapa_final_idx = 2
    idx_actual = {"captura": 0, "enviada": 1, "autorizada": 2, "rechazada": 2}.get(etapa_actual, 0)

    etiquetas = ["Captura", "Enviada", "Rechazada" if es_rechazada else "Autorizada"]
    colores_fondo = ["#eceeec", "#fdf1dd", "#fbe9e9" if es_rechazada else "#e6f4ea"]
    colores_texto = ["#263238", "#4e342e", "#7f0000" if es_rechazada else "#1b5e20"]

    cajas = []
    for i, etiqueta in enumerate(etiquetas):
        activa = i == idx_actual
        pasada = i < idx_actual
        opacidad = "1" if (activa or pasada) else "0.35"
        borde = "2px solid #37474f" if activa else "1px solid transparent"
        cajas.append(
            f'<div style="background:{colores_fondo[i]};color:{colores_texto[i]};opacity:{opacidad};'
            f'border:{borde};border-radius:8px;padding:8px 16px;font-weight:600;font-size:13px;'
            f'white-space:nowrap;">{etiqueta}</div>'
        )
        if i < etapa_final_idx:
            cajas.append('<div style="font-size:18px;color:#9aa5a0;padding:0 4px;">→</div>')

    return (
        '<div style="display:flex;align-items:center;gap:2px;flex-wrap:wrap;">' + "".join(cajas) + "</div>"
    )


def mostrar_tab_seguimiento_compras():
    st.subheader("🟢 seguimiento de autorización")
    st.caption(
        "En qué paso va cada solicitud de compra y con quién está esperando — para dar "
        "seguimiento sin tener que entrar a Pendientes o Autorizaciones."
    )

    df = obtener_solicitudes_pendientes_usuario_ctrl("", ver_todas=True)
    if df.empty:
        st.info("no hay solicitudes de compra registradas.")
        return

    usuarios = get_usuarios_activos_ctrl() or []
    nombre_por_id = {int(u["id"]): u["nombre"] for u in usuarios}

    tipo_mp_inv = obtener_tipo_compra_mp_inventario_ctrl()
    nombre_tipo_mp_inv = str((tipo_mp_inv or {}).get("nombre") or "").strip()

    c1, c2 = st.columns(2)
    with c1:
        tipos_disp = sorted(df["tipo_compra"].dropna().unique().tolist())
        tipos_sel = st.multiselect("tipo de compra", options=tipos_disp, default=tipos_disp, key="seg_compras_tipos")
    with c2:
        estatus_disp = sorted(df["estatus"].dropna().str.lower().unique().tolist())
        estatus_sel = st.multiselect("estatus", options=estatus_disp, default=estatus_disp, key="seg_compras_estatus")

    df_f = df[df["tipo_compra"].isin(tipos_sel) & df["estatus"].str.lower().isin(estatus_sel)]
    if df_f.empty:
        st.info("no hay solicitudes con esos filtros.")
        return

    filas = []
    for _, row in df_f.iterrows():
        id_sol = int(row["id_solicitud_compra"])
        estatus = str(row["estatus"]).strip().lower()
        es_mp_inv = str(row["tipo_compra"]).strip() == nombre_tipo_mp_inv

        if es_mp_inv:
            estatus_visual, esperando = _resumen_mp_inventario(id_sol, nombre_por_id)
        else:
            estatus_visual, esperando = _resumen_whole(id_sol, estatus, nombre_por_id)

        filas.append({
            "folio": id_sol,
            "tipo": row["tipo_compra"],
            "solicitante": row["solicitante"],
            "fecha": row["fecha_solicitud"],
            "estatus": estatus_visual,
            "esperando a": esperando or "—",
        })

    df_show = pd.DataFrame(filas)

    gb = GridOptionsBuilder.from_dataframe(df_show)
    gb.configure_grid_options(autoSizeStrategy=None)
    gb.configure_default_column(editable=False, resizable=True, filter=True, sortable=True)
    gb.configure_column("folio", pinned="left", width=90)
    gb.configure_column("estatus", width=220, cellStyle=_CELL_STYLE_ESTATUS_JS)
    gb.configure_column("esperando a", width=220)
    gb.configure_selection(selection_mode="single", use_checkbox=False)

    grid_resp = AgGrid(
        df_show,
        gridOptions=gb.build(),
        data_return_mode=DataReturnMode.AS_INPUT,
        fit_columns_on_grid_load=False,
        allow_unsafe_jscode=True,
        height=min(56 + len(df_show) * 35, 450),
        key="seg_compras_grid",
    )

    seleccionadas = grid_resp.get("selected_rows")
    if isinstance(seleccionadas, pd.DataFrame) and not seleccionadas.empty:
        folio_sel = int(seleccionadas.iloc[0]["folio"])
        cab_sel = obtener_cabecera_solicitud_compra_ctrl(folio_sel)
        estatus_sel = str(cab_sel.get("estatus") or "").strip().lower()

        st.divider()
        st.markdown(f"#### solicitud #{folio_sel} — {cab_sel.get('tipo_compra', '')}")
        st.markdown(_stepper_html(estatus_sel), unsafe_allow_html=True)

        fila_sel = df_show[df_show["folio"] == folio_sel].iloc[0]
        if fila_sel["esperando a"] != "—":
            st.caption(f"⏳ esperando autorización de: **{fila_sel['esperando a']}**")
        if cab_sel.get("motivo_autorizacion"):
            st.caption(f"📋 {cab_sel.get('motivo_autorizacion')}")
