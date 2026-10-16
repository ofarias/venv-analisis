from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, DataReturnMode, GridOptionsBuilder, JsCode

from controllers.forecast_controller import (
    generar_propuesta_ctrl,
    guardar_forecast_fila_ctrl,
    obtener_forecast_detalle_ctrl,
    obtener_precio_venta_presupuesto_ctrl,
    _compras_historicas_sae,
    _ventas_historicas_sae,
    _existencias_sae,
)
from controllers.forecast_autorizacion_controller import (
    cambiar_estatus_forecast_mes_ctrl,
    obtener_forecast_mes_estatus_ctrl,
)
from controllers.presupuesto_ventas_controller import (
    obtener_cargas_presupuesto_ventas_ctrl,
    obtener_catalogo_productos_pv_ctrl,
)
from controllers.presupuesto_compras_controller import (
    obtener_cargas_presupuesto_compras_ctrl,
)
from controllers.solicitudes_controller import get_correos_usuarios_por_rol_ctrl
from utils.deeplink_tokens import build_links_autorizacion_forecast
from utils.envio_correo import enviar_correo


_MESES = {1:"ene",2:"feb",3:"mar",4:"abr",5:"may",6:"jun",
          7:"jul",8:"ago",9:"sep",10:"oct",11:"nov",12:"dic"}

_TABS_SEC = [
    ("KG México",        "KG",  "MEXICO"),
]

_TIPOS = [
    ("venta",  "🟢 Venta (Forecast)"),
    ("compra", "🔵 Compra (Demand Plan)"),
]

_METODOS_LABEL_VENTA = {
    "manual": "Manual",
}
_METODOS_LABEL_COMPRA = {
    "manual": "Manual",
    "pc_anio": "Presupuesto Compras (todas las cargas)",
}

# resalta en verde los valores positivos y en rojo los negativos; 0 sin color
# — mismo criterio y colores que presupuesto_ventas_view.py / presupuesto_compras_view.py
_CELL_STYLE_VALORES = JsCode("""
function(params) {
    if (params.value > 0) {
        return {backgroundColor: '#d4edda', color: '#155724'};
    }
    if (params.value < 0) {
        return {backgroundColor: '#f8d7da', color: '#721c24'};
    }
    return null;
}
""")

# ventana de urgencia de Forecast (Venta y Compra): mes actual + 2 siguientes
# — todas las celdas en amarillo, sin importar el valor
_CELL_STYLE_VENTANA_AMARILLO = JsCode("""
function(params) {
    return {backgroundColor: '#fff3cd', color: '#856404'};
}
""")

# ventana de urgencia de Forecast (Venta y Compra): los 2 meses siguientes a
# la ventana amarilla — en rojo solo si la celda tiene valor mayor a 0
_CELL_STYLE_VENTANA_ROJA = JsCode("""
function(params) {
    if (params.value > 0) {
        return {backgroundColor: '#f8d7da', color: '#721c24'};
    }
    return null;
}
""")

# resalta la fila de totales pinneada al fondo del grid
_ROW_STYLE_TOTAL = JsCode("""
function(params) {
    if (params.node.rowPinned) {
        return {fontWeight: 'bold', backgroundColor: '#e9ecef'};
    }
    return null;
}
""")


def _cell_style_real_vs_dp_js(mes_col: str) -> JsCode:
    """cellStyle de una columna "Real <mes>": compara contra el DP (forecast)
    del mismo mes (columna `mes_col`) en la misma fila.
    - DP > 0 y real = DP           → verde
    - DP > 0 y real < DP (incl. 0) → rojo
    - real > DP (incl. DP = 0)     → azul
    - DP = 0 y real = 0            → sin color (nada que comparar)"""
    return JsCode(f"""
    function(params) {{
        if (params.value === null || params.value === undefined) return null;
        var real = params.value;
        var dp = params.data ? params.data['{mes_col}'] : null;
        if (dp === null || dp === undefined) dp = 0;
        if (dp === 0 && real === 0) return null;
        if (real === dp) return {{backgroundColor: '#d4edda', color: '#155724'}};
        if (real < dp) return {{backgroundColor: '#f8d7da', color: '#721c24'}};
        return {{backgroundColor: '#cce5ff', color: '#004085'}};
    }}
    """)


def _value_formatter_js(decimales: int) -> JsCode:
    return JsCode(f"""
    function(params) {{
        if (params.value === null || params.value === undefined || params.value === '') return '';
        return Number(params.value).toFixed({decimales});
    }}
    """)


def _value_formatter_miles_js(decimales: int) -> JsCode:
    """Con separador de miles — mismo criterio que presupuesto_compras_view.py."""
    return JsCode(f"""
    function(params) {{
        if (params.value === null || params.value === undefined || params.value === '') return '';
        return Number(params.value).toLocaleString('en-US', {{minimumFractionDigits: {decimales}, maximumFractionDigits: {decimales}}});
    }}
    """)


def _etiqueta_carga(r: dict) -> str:
    """Etiqueta de una carga de presupuesto (ventas o compras, mismo
    esquema) para el selector de método — usa el comentario (ahí indican de
    qué industria es) y cae a nombre de archivo + año si no hay comentario."""
    comentario = str(r.get("comentarios") or "").strip()
    if comentario:
        return comentario
    nombre = str(r.get("nombre_archivo") or "").strip()
    anio_carga = r.get("anio")
    return f"{nombre} [{anio_carga}]" if nombre else f"carga #{r.get('id_carga')}"


def _metodos_opciones(usuario_datos_id: int, tipo: str) -> dict:
    """Opciones del selector de método, según el tipo del sub-tab activo:
    - compra: manual + "todas las cargas del año" + una opción por cada
      carga de presupuesto de compras del dueño de la versión.
    - venta: manual + una opción por cada carga de presupuesto de ventas del
      dueño de la versión, identificada por su comentario/industria.

    SuperAdmin ve además el presupuesto autorizado de cualquier usuario (no
    solo el propio o el del usuario elegido en el panel de soporte), para no
    tener que cambiar de "actuar como" solo para vincular un presupuesto."""
    es_superadmin = _tiene_rol((st.session_state.get("usuario") or {}).get("roles"), "superadmin")

    if tipo == "compra":
        opciones = dict(_METODOS_LABEL_COMPRA)
        try:
            if es_superadmin:
                df_cargas_pc = obtener_cargas_presupuesto_compras_ctrl(limit=200, solo_autorizados=True)
            else:
                df_cargas_pc = obtener_cargas_presupuesto_compras_ctrl(limit=50, usuario_id=usuario_datos_id)
        except Exception:
            df_cargas_pc = None
        if df_cargas_pc is not None and not df_cargas_pc.empty:
            for r in df_cargas_pc.to_dict("records"):
                id_carga = int(r["id_carga"])
                etiqueta = _etiqueta_carga(r)
                if es_superadmin and r.get("propietario"):
                    etiqueta = f"{etiqueta} — {r['propietario']}"
                opciones[f"pc_carga:{id_carga}"] = f"Presupuesto Compras — {etiqueta}"
        return opciones

    opciones = dict(_METODOS_LABEL_VENTA)
    try:
        if es_superadmin:
            df_cargas_pv = obtener_cargas_presupuesto_ventas_ctrl(limit=200, solo_autorizados=True)
        else:
            df_cargas_pv = obtener_cargas_presupuesto_ventas_ctrl(limit=50, usuario_id=usuario_datos_id)
    except Exception:
        df_cargas_pv = None
    if df_cargas_pv is not None and not df_cargas_pv.empty:
        for r in df_cargas_pv.to_dict("records"):
            id_carga = int(r["id_carga"])
            etiqueta = _etiqueta_carga(r)
            if es_superadmin and r.get("propietario"):
                etiqueta = f"{etiqueta} — {r['propietario']}"
            opciones[f"pv_carga:{id_carga}"] = f"Presupuesto Ventas — {etiqueta}"
    return opciones


def _usuario_real_id() -> int:
    u = st.session_state.get("usuario") or {}
    return int(u.get("id") or u.get("id_usuario") or 0)


def _get_usuario_id() -> int:
    """Igual que `forecast_view.py::_get_usuario_id` — respeta el modo
    soporte SuperAdmin (`fc_soporte_usuario_id`) para que quede registrado
    como autor de cada fila capturada mientras se le da soporte."""
    usuario = st.session_state.get("usuario") or {}
    soporte_id = st.session_state.get("fc_soporte_usuario_id")
    if soporte_id and _tiene_rol(usuario.get("roles"), "superadmin"):
        return int(soporte_id)
    return _usuario_real_id()


def _norm_roles_list(values) -> list[str]:
    if not values:
        return []
    if isinstance(values, str):
        values = [values]
    return [str(v).strip().lower() for v in values if str(v or "").strip()]


def _tiene_rol(roles: list[str], *objetivos: str) -> bool:
    roles_set = set(_norm_roles_list(roles))
    objetivos_set = set(_norm_roles_list(objetivos))
    return bool(roles_set.intersection(objetivos_set))


def _puede_editar_sin_restriccion() -> bool:
    usuario = st.session_state.get("usuario") or {}
    if usuario.get("rol") == "Admin":
        return True
    return _tiene_rol(usuario.get("roles"), "admin", "superadmin", "forecastadmin")


# ── autorización mensual — misma cascada que presupuesto de ventas/compras ───
# (ver views/modulo_presupuesto_ventas/presupuesto_compras_view.py), sin
# matices nuevos, confirmado con el usuario.

def _tipo_autorizacion_linea() -> str:
    usuario = st.session_state.get("usuario") or {}
    roles = usuario.get("roles")
    if _tiene_rol(roles, "gerente de ventas", "gerente ventas"):
        return "sin_autorizacion"
    if _tiene_rol(roles, "jefe de ventas", "supervisor de ventas"):
        return "autoriza_gerente_ventas"
    return "autoriza_jefe_ventas"


def _rol_autorizador_linea() -> str:
    tipo = _tipo_autorizacion_linea()
    if tipo == "autoriza_gerente_ventas":
        return "Gerente de Ventas"
    if tipo == "autoriza_jefe_ventas":
        return "Jefe de Ventas"
    return ""


def _enviar_notificacion_autorizador_forecast(
    *, id_version: int, tipo: str, anio: int, mes: int, totales: dict,
    nombre_rol: str, token, remitente: str,
) -> tuple[bool, str]:
    """Correo al rol autorizador — calco de
    `_enviar_notificacion_autorizador_compras` (presupuesto_compras_view.py),
    adaptado a totales mensuales de forecast en vez de líneas de Excel."""
    destinatarios = sorted({
        str(e).strip() for e in (get_correos_usuarios_por_rol_ctrl(nombre_rol) or []) if str(e or "").strip()
    })
    if not destinatarios:
        return False, f"no hay correos configurados para el rol \"{nombre_rol}\""

    mes_nombre = _MESES.get(mes, str(mes)).upper()
    etiqueta_tipo = "venta" if tipo == "venta" else "compra (DP)"
    filas_html = "".join(
        f"<tr><td>{k}</td><td>{v:,.2f}</td></tr>" for k, v in totales.items()
    )
    links = build_links_autorizacion_forecast(
        id_version=id_version, tipo=tipo, anio=anio, mes=mes, nombre_rol=nombre_rol,
    )
    if links.get("ok"):
        links_html = f"""
        <p style="margin:14px 0">
          <a href="{links['approve']}"
             style="display:inline-block;padding:10px 14px;background:#16a34a;color:#fff;text-decoration:none;border-radius:6px;font-weight:700">
            autorizar
          </a>
          <a href="{links['reject']}"
             style="display:inline-block;margin-left:10px;padding:10px 14px;background:#dc2626;color:#fff;text-decoration:none;border-radius:6px;font-weight:700">
            rechazar
          </a>
        </p>
        """
    else:
        links_html = ""
    asunto = f"Forecast de {etiqueta_tipo} {mes_nombre} {anio} — solicitud de autorización"
    cuerpo_html = f"""
    <div style="font-family: Arial, sans-serif; font-size: 14px; color: #111;">
        <p>Se solicitó autorización para el forecast de {etiqueta_tipo} de
        <b>{mes_nombre} {anio}</b> (versión {id_version}).</p>
        <table border="1" cellpadding="6" cellspacing="0" style="border-collapse: collapse;">
            <tr style="background:#1F4E78; color:#fff;"><th>Concepto</th><th>Total</th></tr>
            {filas_html}
        </table>
        {links_html}
        <p>O entra a la app, módulo <b>Forecast → ✅ Autorizaciones</b>, para autorizar o rechazar.</p>
    </div>
    """
    return enviar_correo(
        destinatario=destinatarios, asunto=asunto, cuerpo_html=cuerpo_html,
        token=token, remitente=remitente,
    )


def _mes_editable_forecast(anio: int, mes: int) -> bool:
    """Regla de los 3 meses (Venta y Compra por igual): el mes actual y los 2
    siguientes quedan bloqueados (3 meses en total, misma ventana que se
    resalta en amarillo) — si estamos en octubre, octubre/noviembre/diciembre
    quedan bloqueados y enero del año siguiente en adelante (incluido
    cualquier año futuro) queda editable."""
    hoy = date.today()
    idx_hoy = hoy.year * 12 + hoy.month
    idx_celda = int(anio) * 12 + int(mes)
    return idx_celda >= idx_hoy + 3


def _offset_mes_actual(anio: int, mes: int) -> int:
    """Diferencia en meses entre (anio, mes) y el mes actual — 0 = mes
    actual, 1 = mes siguiente, etc. (puede ser negativo). Usado para la
    ventana de colores de urgencia de Forecast (Venta y Compra): mes actual +
    2 siguientes en amarillo, los 2 siguientes a esos en rojo (si hay valor)."""
    hoy = date.today()
    idx_hoy = hoy.year * 12 + hoy.month
    idx_celda = int(anio) * 12 + int(mes)
    return idx_celda - idx_hoy


def _mes_editable(tipo: str, anio: int, mes: int) -> bool:
    """Misma regla de los 3 meses para Venta y Compra."""
    return _mes_editable_forecast(anio, mes)


def _real_sae_map(df_sae: pd.DataFrame, seccion: str, anio: int, meses: list[int]) -> dict[str, float]:
    """cve_art → total real (ventas o compras, según qué df_sae se pase) de
    SAE, sumado sobre los meses seleccionados del año en curso — mismo
    criterio que la columna "Real (SAE)" de la pantalla Real vs Forecast."""
    if df_sae is None or df_sae.empty or "cve_art" not in df_sae.columns:
        return {}
    df = df_sae.copy()
    df["anio"] = pd.to_numeric(df["anio"], errors="coerce")
    df["mes"] = pd.to_numeric(df["mes"], errors="coerce")
    df = df[(df["anio"] == int(anio)) & (df["mes"].isin(meses))]
    if df.empty:
        return {}
    col = "cantidad" if seccion == "KG" else "importe"
    if col not in df.columns:
        return {}
    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    grp = df.groupby("cve_art", as_index=False)[col].sum()
    return dict(zip(grp["cve_art"].astype(str).str.strip(), grp[col]))


def _pivot_forecast(
    df: pd.DataFrame,
    meses: list[int],
    precio_map: dict | None = None,
    real_map: dict | None = None,
    real_col: str | None = None,
    real_map_por_mes: dict[int, dict] | None = None,
    real_col_prefix: str | None = None,
) -> pd.DataFrame:
    """Convierte detalle long → wide con columnas de meses. "precio" es el
    precio de venta que el propio vendedor capturó en su Presupuesto de
    Ventas (promedio ponderado por kg, ver
    obtener_precio_venta_presupuesto_ctrl) — ya no el precio público de
    catálogo ni el de facturas SAE; "total_kg" es la suma de los meses
    mostrados; "total_usd" la convierte a dólares con ese precio de venta.

    real_map (cve_prod → total real SAE de los meses seleccionados) se agrega
    como `real_col` cuando se pasan ambos — un solo total acumulado de los
    meses mostrados.

    real_map_por_mes (mes → {cve_prod: total real SAE de ESE mes}) agrega,
    en cambio, una columna `{real_col_prefix}_{mes}` por cada mes con datos,
    colocada justo antes de la columna de forecast de ese mismo mes — permite
    comparar mes a mes ("Real Ene" junto a "Ene") en vez de un solo total
    agregado; ver _mostrar_construccion_tipo (venta y compra por igual)."""
    if df is None or df.empty:
        return pd.DataFrame()
    cols_id = ["cve_prod", "producto_excel"]
    ref_cols = ["venta_real_mes_ant"]

    wide = df.pivot_table(
        index=cols_id,
        columns="mes",
        values="forecast",
        aggfunc="sum",
        fill_value=0.0,
    ).reset_index()
    wide.columns = [c if isinstance(c, str) else _MESES.get(c, str(c)) for c in wide.columns]

    ref = df.groupby(cols_id, as_index=False)[ref_cols].mean()
    wide = wide.merge(ref, on=cols_id, how="left")

    meses_cols = [_MESES[m] for m in meses if _MESES[m] in wide.columns]
    wide["total_kg"] = wide[meses_cols].sum(axis=1) if meses_cols else 0.0

    precio_map = precio_map or {}
    precio_prod = wide["cve_prod"].astype(str).str.strip().map(precio_map).fillna(0.0)
    wide["precio"] = precio_prod
    wide["total_usd"] = wide["total_kg"] * precio_prod

    ref_cols_out = list(ref_cols)
    if real_map and real_col:
        wide[real_col] = wide["cve_prod"].astype(str).str.strip().map(real_map).fillna(0.0)
        ref_cols_out.append(real_col)

    # columnas mes a mes: si hay real por mes, la columna "real_<mes>" va
    # justo antes de la columna de forecast de ese mismo mes
    meses_cols_out: list[str] = []
    for m in meses:
        mn = _MESES.get(m)
        if real_map_por_mes and real_col_prefix and m in real_map_por_mes:
            real_mes_col = f"{real_col_prefix}_{mn}"
            wide[real_mes_col] = wide["cve_prod"].astype(str).str.strip().map(real_map_por_mes[m]).fillna(0.0)
            meses_cols_out.append(real_mes_col)
        if mn in wide.columns:
            meses_cols_out.append(mn)

    col_order = cols_id + ["precio", "total_kg", "total_usd"] + ref_cols_out + meses_cols_out
    return wide[[c for c in col_order if c in wide.columns]]


def _grafica_rendimiento(
    fila_total: dict, meses_sel: list[int], real_col_prefix: str | None,
    forecast_label: str, real_label: str,
) -> pd.DataFrame:
    """Forecast/presupuesto vs Real, una columna por serie (en vez de pares
    de filas) para que `st.bar_chart` las pinte con colores distintos — a
    partir de los totales ya sumados en `fila_total` (fila TOTAL pinneada
    del grid). `real_label` solo tiene valor en los meses que tienen esa
    columna (mes actual y anteriores; ver _mostrar_construccion_tipo)."""
    filas: list[dict] = []
    for m in sorted(meses_sel):
        mn = _MESES[m]
        if mn not in fila_total:
            continue
        fila = {"categoria": mn.capitalize(), forecast_label: fila_total[mn]}
        if real_col_prefix:
            real_mes_col = f"{real_col_prefix}_{mn}"
            if real_mes_col in fila_total:
                fila[real_label] = fila_total[real_mes_col]
        filas.append(fila)
    if not filas:
        return pd.DataFrame()
    df = pd.DataFrame(filas)
    # categórica ordenada: preserva el orden cronológico en vez del orden
    # alfabético que usaría el eje X por defecto
    df["categoria"] = pd.Categorical(df["categoria"], categories=df["categoria"].tolist(), ordered=True)
    return df.set_index("categoria")


def mostrar_tab_construccion(
    id_version: int, id_carga_pv: int | None, anio: int, metodo_default: str, usuario_datos_id: int,
) -> None:
    usuario_id = _get_usuario_id()
    es_admin = _puede_editar_sin_restriccion()

    # selector de meses a proyectar — compartido entre Venta y Compra
    mes_opciones = list(_MESES.items())
    meses_sel = st.multiselect(
        "meses a proyectar",
        options=[m for m, _ in mes_opciones],
        default=list(range(1, 13)),
        format_func=lambda m: _MESES[m].upper(),
        key="fc_meses_sel",
    )
    if not meses_sel:
        st.warning("selecciona al menos un mes")
        return

    st.divider()

    # ventas y compras reales SAE — compartidas entre ambos sub-tabs, cada
    # uno usa la que le corresponde (venta → "Venta Real", compra → "Compra Real")
    with st.spinner("cargando ventas SAE…"):
        df_ventas_sae = _ventas_historicas_sae(int(anio))
    with st.spinner("cargando compras SAE…"):
        df_compras_sae = _compras_historicas_sae(int(anio))

    tipo_tabs = st.tabs([label for _, label in _TIPOS])
    for tab_ui, (tipo, _label) in zip(tipo_tabs, _TIPOS):
        with tab_ui:
            _mostrar_construccion_tipo(
                tipo=tipo,
                id_version=id_version,
                id_carga_pv=id_carga_pv,
                anio=anio,
                metodo_default=metodo_default,
                usuario_datos_id=usuario_datos_id,
                usuario_id=usuario_id,
                es_admin=es_admin,
                meses_sel=meses_sel,
                df_ventas_sae=df_ventas_sae,
                df_compras_sae=df_compras_sae,
            )


def _mostrar_construccion_tipo(
    tipo: str,
    id_version: int,
    id_carga_pv: int | None,
    anio: int,
    metodo_default: str,
    usuario_datos_id: int,
    usuario_id: int,
    es_admin: bool,
    meses_sel: list[int],
    df_ventas_sae: pd.DataFrame,
    df_compras_sae: pd.DataFrame,
) -> None:
    # regla de meses editables — igual para Venta y Compra (Admin/SuperAdmin/
    # forecastAdmin sin restricción en ambas): se ven todos los meses
    # seleccionados, pero los bloqueados quedan de solo lectura en la tabla y
    # no se tocan al generar propuesta ni al agregar un producto manualmente.
    # Regla de los 3 meses: el mes actual y los 2 siguientes bloqueados.
    meses_editables = [m for m in meses_sel if es_admin or _mes_editable(tipo, anio, m)]
    if not es_admin and len(meses_editables) < len(meses_sel):
        st.caption(
            "🔒 el mes actual y los 2 siguientes están bloqueados — solo se puede mover "
            "el forecast a partir del 4º mes en adelante"
        )

    # estatus de autorización por mes de este tipo — un mes sin fila es
    # 'borrador' implícito. Editar y guardar un mes 'autorizada' lo reenvía
    # automáticamente a 'enviada' (ver _guardar_cambios_pivot más abajo).
    df_estatus = obtener_forecast_mes_estatus_ctrl(id_version=id_version, tipo=tipo, anio=anio)
    estatus_map: dict[int, str] = {}
    if df_estatus is not None and not df_estatus.empty:
        estatus_map = dict(zip(df_estatus["mes"].astype(int), df_estatus["estatus"]))

    # botón generar propuesta automática
    metodos_opciones = _metodos_opciones(usuario_datos_id, tipo)
    # "presupuesto" (guardado en metodo_default) no es una clave de este
    # selector — si la versión quedó vinculada a una carga puntual
    # (id_carga_pv), se preselecciona esa opción "pv_carga:<id>" — solo
    # aplica al sub-tab de venta, que es el único ligado a presupuesto de ventas
    metodo_default_ui = metodo_default if tipo == "venta" else "manual"
    if tipo == "venta" and metodo_default == "presupuesto" and id_carga_pv:
        candidato = f"pv_carga:{int(id_carga_pv)}"
        if candidato in metodos_opciones:
            metodo_default_ui = candidato

    col_m, col_btn = st.columns([2, 1])
    with col_m:
        metodo = st.selectbox(
            "método automático",
            list(metodos_opciones.keys()),
            index=list(metodos_opciones.keys()).index(metodo_default_ui) if metodo_default_ui in metodos_opciones else 0,
            format_func=lambda k: metodos_opciones[k],
            key=f"fc_metodo_auto_{tipo}",
        )
    with col_btn:
        st.write("")
        st.write("")
        if st.button("⚡ generar propuesta", use_container_width=True, key=f"fc_btn_generar_{tipo}"):
            if not meses_editables:
                st.warning("los meses seleccionados están dentro de la ventana bloqueada (mes actual + 2 siguientes)")
            else:
                with st.spinner("calculando propuesta…"):
                    for _, seccion, region in _TABS_SEC:
                        generar_propuesta_ctrl(
                            id_version=id_version,
                            id_carga_pv=id_carga_pv,
                            anio=anio,
                            meses=meses_editables,
                            seccion=seccion,
                            region=region,
                            metodo=metodo,
                            usuario_id=usuario_id,
                            usuario_datos_id=usuario_datos_id,
                            tipo=tipo,
                        )
                st.success("propuesta generada — revisa y ajusta los valores")
                st.rerun()

    st.divider()

    sub_tabs = st.tabs([t[0] for t in _TABS_SEC])

    for tab_ui, (label, seccion, region) in zip(sub_tabs, _TABS_SEC):
        with tab_ui:
            df_det = obtener_forecast_detalle_ctrl(
                id_version=id_version, seccion=seccion, region=region, tipo=tipo
            )

            if df_det is None or df_det.empty:
                st.info(f"sin datos para {label} — usa 'generar propuesta' o carga manualmente")
                _panel_carga_manual(id_version, seccion, region, anio, meses_editables, usuario_id, tipo)
                continue

            df_det["mes"] = pd.to_numeric(df_det["mes"], errors="coerce").astype(int)
            for _c in ("forecast", "presupuesto_valor", "venta_real_mes_ant", "venta_real_prom_3m"):
                if _c in df_det.columns:
                    df_det[_c] = pd.to_numeric(df_det[_c], errors="coerce").fillna(0.0)
            df_det = df_det[df_det["mes"].isin(meses_sel)]

            if df_det.empty:
                st.info(f"sin datos para los meses seleccionados en {label}")
                _panel_carga_manual(id_version, seccion, region, anio, meses_editables, usuario_id, tipo)
                continue

            df_real_sae = df_ventas_sae if tipo == "venta" else df_compras_sae
            real_col = "venta_real_sae" if tipo == "venta" else "compra_real_sae"
            real_label = "Venta Real KG" if tipo == "venta" else "Compra Real KG"

            precio_map = obtener_precio_venta_presupuesto_ctrl(anio=anio, usuario_id=usuario_datos_id)

            # además del total acumulado de siempre, real mes a mes junto a
            # cada columna de forecast del mismo mes (venta y compra por
            # igual) — solo para el mes actual y anteriores, ya que los
            # meses futuros todavía no tienen real (SAE) que mostrar.
            real_map = _real_sae_map(df_real_sae, seccion, anio, meses_sel)
            real_map_por_mes = {
                m: _real_sae_map(df_real_sae, seccion, anio, [m])
                for m in meses_sel
                if _offset_mes_actual(anio, m) <= 0
            }
            real_col_prefix = real_col

            pivot_orig = _pivot_forecast(
                df_det, meses_sel, precio_map,
                real_map=real_map, real_col=real_col,
                real_map_por_mes=real_map_por_mes, real_col_prefix=real_col_prefix,
            )
            decimales = 0 if seccion == "KG" else 2

            gb = GridOptionsBuilder.from_dataframe(pivot_orig)
            gb.configure_default_column(editable=False, resizable=True, width=100)
            # panel lateral nativo de AG Grid para mostrar/ocultar columnas —
            # mismo criterio que Tabla Presupuesto (presupuesto_ventas_view.py)
            gb.configure_side_bar()

            gb.configure_column("cve_prod", headerName="cve prod", editable=False, width=130, pinned="left")
            gb.configure_column("producto_excel", headerName="producto", editable=False, width=220, pinned="left")
            gb.configure_column(
                "precio", headerName="Precio Venta", editable=False, width=110, pinned="left",
                type=["numericColumn"], valueFormatter=_value_formatter_js(4),
            )
            gb.configure_column(
                "total_kg", headerName="Total KG", editable=False, width=110, pinned="left",
                type=["numericColumn"], valueFormatter=_value_formatter_js(0),
            )
            gb.configure_column(
                "total_usd", headerName="Total USD", editable=False, width=120, pinned="left",
                type=["numericColumn"], valueFormatter=_value_formatter_miles_js(2),
            )
            gb.configure_column(
                "venta_real_mes_ant", headerName="vta año ant (Kg)", editable=False, width=130, pinned="left",
                type=["numericColumn"], valueFormatter=_value_formatter_js(2),
            )
            if real_col in pivot_orig.columns:
                gb.configure_column(
                    real_col, headerName=real_label, editable=False, width=110, pinned="left",
                    type=["numericColumn"], valueFormatter=_value_formatter_js(2),
                )
            for m in meses_sel:
                mn = _MESES[m]
                real_mes_col = f"{real_col_prefix}_{mn}" if real_col_prefix else None
                if real_mes_col and real_mes_col in pivot_orig.columns:
                    gb.configure_column(
                        real_mes_col,
                        headerName=f"Real {mn.capitalize()}",
                        editable=False, width=110,
                        type=["numericColumn"], valueFormatter=_value_formatter_js(decimales),
                        cellStyle=_cell_style_real_vs_dp_js(mn),
                    )
                if mn not in pivot_orig.columns:
                    continue
                editable_mes = es_admin or _mes_editable(tipo, anio, m)
                estatus_mes = estatus_map.get(m)

                # ventana de urgencia (Venta y Compra por igual): mes actual
                # + 2 siguientes en amarillo (toda la columna), los 2
                # siguientes a esos en rojo (solo celdas con valor > 0); el
                # resto conserva el criterio normal verde/rojo por signo
                cell_style_mes = _CELL_STYLE_VALORES
                offset = _offset_mes_actual(anio, m)
                if 0 <= offset <= 2:
                    cell_style_mes = _CELL_STYLE_VENTANA_AMARILLO
                elif offset in (3, 4):
                    cell_style_mes = _CELL_STYLE_VENTANA_ROJA

                if not editable_mes:
                    header_mes = f"🔒 {mn.upper()}"
                elif estatus_mes == "autorizada":
                    header_mes = f"✅ {mn.upper()}"
                elif estatus_mes == "enviada":
                    header_mes = f"⏳ {mn.upper()}"
                else:
                    header_mes = mn.upper()

                gb.configure_column(
                    mn,
                    headerName=header_mes,
                    editable=editable_mes,
                    width=90,
                    type=["numericColumn"],
                    cellEditor="agNumberCellEditor",
                    cellStyle=cell_style_mes,
                    valueFormatter=_value_formatter_js(decimales),
                )

            # fila de totales pinneada al fondo: suma de todos los productos
            # por mes (columnas ene..dic, incluyendo real_<mes> si aplica) y
            # en el año (Total KG/Total USD)
            fila_total: dict = {"cve_prod": "TOTAL", "producto_excel": ""}
            for c in ("total_kg", "total_usd", real_col, "venta_real_mes_ant"):
                if c in pivot_orig.columns:
                    fila_total[c] = float(pd.to_numeric(pivot_orig[c], errors="coerce").fillna(0.0).sum())
            for m in meses_sel:
                mn = _MESES[m]
                real_mes_col = f"{real_col_prefix}_{mn}" if real_col_prefix else None
                if real_mes_col and real_mes_col in pivot_orig.columns:
                    fila_total[real_mes_col] = float(pd.to_numeric(pivot_orig[real_mes_col], errors="coerce").fillna(0.0).sum())
                if mn in pivot_orig.columns:
                    fila_total[mn] = float(pd.to_numeric(pivot_orig[mn], errors="coerce").fillna(0.0).sum())
            gb.configure_grid_options(pinnedBottomRowData=[fila_total], getRowStyle=_ROW_STYLE_TOTAL)

            st.caption(
                "🟩 valor positivo  |  🟥 valor negativo  |  🔒 mes bloqueado (regla de los 3 meses)  "
                "|  ⏳ enviado a autorización  |  ✅ autorizado (editable; si lo cambias se "
                "reenvía solo)  |  fila TOTAL = suma de todos los productos"
            )

            grid_response = AgGrid(
                pivot_orig,
                gridOptions=gb.build(),
                update_on=[("cellValueChanged", 600)],
                data_return_mode=DataReturnMode.AS_INPUT,
                fit_columns_on_grid_load=False,
                allow_unsafe_jscode=True,
                enable_enterprise_modules=True,
                height=min(56 + len(pivot_orig) * 35, 680),
                key=f"fc_editor_{tipo}_{seccion}_{region}_{id_version}",
            )
            edited = pd.DataFrame(grid_response.get("data", []))

            if st.button("💾 guardar cambios", type="primary",
                         use_container_width=True,
                         key=f"fc_save_{tipo}_{seccion}_{region}_{id_version}"):
                cambios, meses_tocados = _guardar_cambios_pivot(
                    pivot_orig, edited, df_det, id_version, seccion, region, anio, meses_sel, usuario_id, es_admin, tipo,
                )
                if cambios:
                    # mes editado/guardado que ya estaba 'autorizada' — se
                    # permite el cambio, pero se reenvía solo a autorización
                    # (instrucción del usuario: no hace falta un paso extra).
                    meses_reenviados = sorted(m for m in meses_tocados if estatus_map.get(m) == "autorizada")
                    usuario_sesion = st.session_state.get("usuario") or {}
                    for mes_r in meses_reenviados:
                        cambiar_estatus_forecast_mes_ctrl(
                            id_version=id_version, tipo=tipo, anio=anio, mes=mes_r,
                            estatus_nuevo="enviada", usuario_id=usuario_id,
                            usuario_nombre=usuario_sesion.get("nombre"),
                            usuario_email=usuario_sesion.get("email"),
                            comentario="reenvío automático por edición",
                        )
                        nombre_rol = _rol_autorizador_linea()
                        if nombre_rol:
                            mn_r = _MESES[mes_r]
                            _enviar_notificacion_autorizador_forecast(
                                id_version=id_version, tipo=tipo, anio=anio, mes=mes_r,
                                totales={"total forecast": float(fila_total.get(mn_r) or 0.0)},
                                nombre_rol=nombre_rol,
                                token=st.session_state.get("microsoft_token"),
                                remitente=str(usuario_sesion.get("email") or "").strip(),
                            )
                    st.success(f"{cambios} registros guardados")
                    if meses_reenviados:
                        meses_txt = ", ".join(_MESES[m].upper() for m in meses_reenviados)
                        st.toast(f"📤 se reenvió a autorización automáticamente: {meses_txt}")
                    st.rerun()
                else:
                    st.info("sin cambios detectados")

            _panel_solicitar_autorizacion(
                id_version=id_version, tipo=tipo, anio=anio,
                meses_editables=meses_editables, estatus_map=estatus_map,
                fila_total=fila_total, usuario_id=usuario_id,
                key_suffix=f"{tipo}_{seccion}_{region}_{id_version}",
            )

            forecast_label = "Presupuesto" if tipo == "venta" else "DP"
            titulo_grafica = (
                "📊 mostrar gráfica de rendimiento (presupuesto vs venta real por mes)"
                if tipo == "venta" else
                "📊 mostrar gráfica de rendimiento (DP vs Real por mes)"
            )
            mostrar_grafica = st.checkbox(
                titulo_grafica,
                value=True,
                key=f"fc_show_grafica_{tipo}_{seccion}_{region}_{id_version}",
            )
            if mostrar_grafica:
                df_grafica = _grafica_rendimiento(
                    fila_total, meses_sel, real_col_prefix, forecast_label, real_label,
                )
                if not df_grafica.empty:
                    st.bar_chart(
                        df_grafica, use_container_width=True, height=300,
                        color=["#4C78A8", "#2ca02c"],
                    )
                else:
                    st.info("sin datos suficientes para la gráfica")

            _panel_carga_manual(id_version, seccion, region, anio, meses_editables, usuario_id, tipo)


def _guardar_cambios_pivot(
    orig: pd.DataFrame,
    edited: pd.DataFrame,
    df_det: pd.DataFrame,
    id_version: int,
    seccion: str,
    region: str | None,
    anio: int,
    meses_sel: list[int],
    usuario_id: int,
    es_admin: bool,
    tipo: str,
) -> tuple[int, set[int]]:
    cambios = 0
    meses_tocados: set[int] = set()
    for i in range(len(orig)):
        cve_prod = str(orig.iloc[i].get("cve_prod") or "").strip()
        prod_excel = str(orig.iloc[i].get("producto_excel") or "").strip()

        # referencias guardadas
        mask = df_det["cve_prod"].astype(str).str.strip() == cve_prod
        ref_row = df_det[mask].iloc[0] if mask.any() else pd.Series()

        for mes in meses_sel:
            # defensa adicional: la columna ya viene bloqueada en la UI
            # (editable=False), esto solo evita persistir un cambio si de
            # todas formas llegara uno para un mes bloqueado
            if not es_admin and not _mes_editable(tipo, anio, mes):
                continue
            mn = _MESES[mes]
            if mn not in orig.columns or i >= len(edited):
                continue
            val_orig = float(orig.iloc[i].get(mn) or 0)
            val_edit = float(edited.iloc[i].get(mn) or 0)
            if abs(val_edit - val_orig) < 1e-4:
                continue
            guardar_forecast_fila_ctrl(
                id_version=id_version,
                seccion=seccion,
                region=region,
                cve_prod=cve_prod or None,
                producto_excel=prod_excel or None,
                anio=anio,
                mes=mes,
                forecast=val_edit,
                justificacion=None,
                metodo="manual",
                usuario_id=usuario_id,
                venta_real_mes_ant=float(ref_row.get("venta_real_mes_ant") or 0) if not ref_row.empty else 0.0,
                venta_real_prom_3m=float(ref_row.get("venta_real_prom_3m") or 0) if not ref_row.empty else 0.0,
                presupuesto_valor=float(ref_row.get("presupuesto_valor") or 0) if not ref_row.empty else 0.0,
                tipo=tipo,
            )
            cambios += 1
            meses_tocados.add(mes)
    return cambios, meses_tocados


_ESTATUS_BADGE_MES = {
    None: "🔵 borrador",
    "borrador": "🔵 borrador",
    "enviada": "⏳ enviada",
    "autorizada": "✅ autorizada",
    "rechazada": "🔴 rechazada",
}


def _panel_solicitar_autorizacion(
    *,
    id_version: int,
    tipo: str,
    anio: int,
    meses_editables: list[int],
    estatus_map: dict[int, str],
    fila_total: dict,
    usuario_id: int,
    key_suffix: str,
) -> None:
    """Botón "solicitar autorización" por mes individual — granularidad
    recomendada en el plan: rara vez hay más de 2-3 meses editables
    simultáneos (la regla de los 3 meses solo deja entrar un mes nuevo por
    vez), y así el autorizador ve exactamente qué mes está aprobando."""
    if not meses_editables:
        return

    opciones = {
        f"{_MESES[m].upper()} — {_ESTATUS_BADGE_MES.get(estatus_map.get(m), '🔵 borrador')}": m
        for m in meses_editables
    }
    col_sel, col_btn = st.columns([2, 1])
    with col_sel:
        etiqueta_sel = st.selectbox(
            "mes a enviar a autorización",
            list(opciones.keys()),
            key=f"fc_auth_mes_{key_suffix}",
        )
    mes_sel = opciones[etiqueta_sel]
    estatus_actual = estatus_map.get(mes_sel)
    etiqueta_btn = "🔁 reenviar autorización" if estatus_actual == "enviada" else "📤 solicitar autorización"

    with col_btn:
        st.write("")
        if st.button(etiqueta_btn, use_container_width=True, key=f"fc_auth_btn_{key_suffix}"):
            usuario_sesion = st.session_state.get("usuario") or {}
            nombre_rol = _rol_autorizador_linea()
            if not nombre_rol:
                cambiar_estatus_forecast_mes_ctrl(
                    id_version=id_version, tipo=tipo, anio=anio, mes=mes_sel,
                    estatus_nuevo="autorizada", usuario_id=usuario_id,
                    usuario_nombre=usuario_sesion.get("nombre"),
                    usuario_email=usuario_sesion.get("email"),
                    comentario="autoaprobado (Gerente de Ventas)",
                )
                st.success("autorizado automáticamente (tu rol no requiere autorización adicional)")
            else:
                cambiar_estatus_forecast_mes_ctrl(
                    id_version=id_version, tipo=tipo, anio=anio, mes=mes_sel,
                    estatus_nuevo="enviada", usuario_id=usuario_id,
                    usuario_nombre=usuario_sesion.get("nombre"),
                    usuario_email=usuario_sesion.get("email"),
                )
                mn_sel = _MESES[mes_sel]
                ok, msg = _enviar_notificacion_autorizador_forecast(
                    id_version=id_version, tipo=tipo, anio=anio, mes=mes_sel,
                    totales={"total forecast": float(fila_total.get(mn_sel) or 0.0)},
                    nombre_rol=nombre_rol,
                    token=st.session_state.get("microsoft_token"),
                    remitente=str(usuario_sesion.get("email") or "").strip(),
                )
                if ok:
                    st.success(f"solicitud enviada a {nombre_rol}")
                else:
                    st.warning(f"se guardó la solicitud, pero el correo no se pudo enviar: {msg}")
            st.rerun()


def _panel_carga_manual(
    id_version: int,
    seccion: str,
    region: str | None,
    anio: int,
    meses_sel: list[int],
    usuario_id: int,
    tipo: str,
) -> None:
    """Formulario para agregar manualmente una fila al forecast."""
    with st.expander("➕ agregar producto manualmente"):
        try:
            df_cat = obtener_catalogo_productos_pv_ctrl()
        except Exception:
            df_cat = pd.DataFrame()

        nom_key = f"fc_man_nom_{tipo}_{seccion}_{region}"

        if df_cat is not None and not df_cat.empty:
            sel_key = f"fc_man_prod_{tipo}_{seccion}_{region}"
            opciones_prod = {"(escribe cve_prod)": ""} | {
                f"{r['cve_prod']}  {r['descr']}": r['cve_prod']
                for r in df_cat.to_dict("records")
            }
            cve_a_descr = {
                str(r["cve_prod"]).strip(): str(r.get("descr") or "").strip()
                for r in df_cat.to_dict("records")
            }

            def _autofill_nombre_producto() -> None:
                cve_sel = opciones_prod.get(st.session_state.get(sel_key), "")
                if cve_sel:
                    st.session_state[nom_key] = cve_a_descr.get(cve_sel, "")

            sel_prod = st.selectbox(
                "producto SAE", list(opciones_prod.keys()), key=sel_key,
                on_change=_autofill_nombre_producto,
            )
            cve_prod = opciones_prod[sel_prod]
        else:
            cve_prod = st.text_input("cve_prod", key=f"fc_man_cve_{tipo}_{seccion}_{region}")

        prod_excel = st.text_input("nombre producto (opcional)", key=nom_key)

        # se arma en bloques de hasta 6 columnas por fila, creando un st.columns()
        # nuevo por cada fila: así el orden real (y el tab-order) queda
        # ene→feb→mar→…→dic en vez de agruparse por columna (ene, jul, feb, ago, …)
        valores: dict[int, float] = {}
        CHUNK = 6
        for inicio in range(0, len(meses_sel), CHUNK):
            fila_meses = meses_sel[inicio:inicio + CHUNK]
            cols = st.columns(len(fila_meses))
            for col, mes in zip(cols, fila_meses):
                with col:
                    valores[mes] = st.number_input(
                        _MESES[mes].upper(), min_value=0.0, value=0.0, format="%.4f",
                        key=f"fc_man_val_{tipo}_{seccion}_{region}_{mes}"
                    )

        if st.button("agregar", key=f"fc_man_btn_{tipo}_{seccion}_{region}"):
            if not cve_prod.strip():
                st.error("ingresa cve_prod")
                return
            for mes, val in valores.items():
                guardar_forecast_fila_ctrl(
                    id_version=id_version, seccion=seccion, region=region,
                    cve_prod=cve_prod.strip(), producto_excel=prod_excel.strip() or None,
                    anio=anio, mes=mes, forecast=val,
                    justificacion=None, metodo="manual", usuario_id=usuario_id,
                    tipo=tipo,
                )
            st.success("producto agregado")
            st.rerun()
