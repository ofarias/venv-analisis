from __future__ import annotations

import re
from datetime import date
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

from controllers.solicitudes_controller import (
    get_detalle_ctrl,
    get_detalle_unidades_ctrl,
    get_unidades_negocio_ctrl,
    listar_solicitudes_ctrl,
)


ESTATUS_OPCIONES = [
    "",
    "captura",
    "enviada",
    "rechazada",
    "autorizada ventas",
    "dispersion",
    "contabilidad",
    "revision ventas",
    "poliza",
    "revision comprobacion",
    "cerrada",
    "eliminada",
]


# =========================
# helpers
# =========================

def _safe_int(v: Any) -> Optional[int]:
    try:
        if v in (None, "", "None"):
            return None
        return int(v)
    except Exception:
        return None



def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        if v in (None, ""):
            return default
        return float(v)
    except Exception:
        return default



def _get_usuario_actual() -> dict:
    return st.session_state.get("usuario") or {}



def _get_usuario_id() -> Optional[int]:
    usuario = _get_usuario_actual()
    for key in ("id", "usuario_id", "id_usuario", "user_id", "empleado_id"):
        val = _safe_int(usuario.get(key))
        if val is not None:
            return val
    return None



def _get_usuario_nombre() -> str:
    usuario = _get_usuario_actual()
    for key in ("nombre", "name", "username"):
        val = str(usuario.get(key) or "").strip()
        if val:
            return val
    return "usuario"



def _to_date(v: Any):
    try:
        return pd.to_datetime(v).date() if v not in (None, "") else None
    except Exception:
        return None



def _monto_base_detalle(row: Dict[str, Any]) -> float:
    for key in ("total", "total_xml", "importe", "subtotal"):
        val = _safe_float(row.get(key), 0.0)
        if val != 0:
            return val
    return 0.0



def _fmt_money(v: float) -> str:
    return f"${v:,.2f}"



def _normaliza_texto(v: Any, default: str = "sin dato") -> str:
    txt = str(v or "").strip()
    return txt if txt else default


@st.cache_data(show_spinner=False, ttl=120)
def _cargar_solicitudes_usuario(
    empleado_id: int,
    folio_like: str = "",
    estatus: str = "",
    anio: Optional[int] = None,
    limit: int = 1000,
) -> pd.DataFrame:
    rows = listar_solicitudes_ctrl(
        folio_like=folio_like,
        estatus=estatus,
        anio=anio,
        empleado_id=empleado_id,
        limit=limit,
    )
    df = pd.DataFrame(rows or [])
    if df.empty:
        return df

    for col in ["fecha_inicio", "fecha_fin", "fecha_creacion"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


@st.cache_data(show_spinner=False, ttl=120)
def _cargar_detalle_enriquecido(solicitud_ids: tuple[int, ...]) -> pd.DataFrame:
    if not solicitud_ids:
        return pd.DataFrame()

    unidades = get_unidades_negocio_ctrl() or []
    unidades_map = {int(x["id"]): x.get("nombre", f"unidad {x['id']}") for x in unidades if x.get("id") is not None}

    detalle_rows: List[Dict[str, Any]] = []
    unidades_rows: List[Dict[str, Any]] = []

    solicitudes = listar_solicitudes_ctrl(limit=max(1000, len(solicitud_ids) + 50)) or []
    sol_map = {int(s["id"]): s for s in solicitudes if s.get("id") is not None and int(s["id"]) in solicitud_ids}

    for solicitud_id in solicitud_ids:
        cab = sol_map.get(int(solicitud_id), {"id": solicitud_id})
        detalle = get_detalle_ctrl(int(solicitud_id)) or []

        for d in detalle:
            detalle_id = _safe_int(d.get("id"))
            base = _monto_base_detalle(d)
            row = {
                "solicitud_id": int(solicitud_id),
                "detalle_id": detalle_id,
                "folio": cab.get("folio"),
                "anio": cab.get("anio"),
                "empleado_nombre": cab.get("empleado_nombre"),
                "clientes": cab.get("clientes"),
                "ciudades": cab.get("ciudades"),
                "estatus": cab.get("estatus"),
                "fecha_inicio": cab.get("fecha_inicio"),
                "fecha_fin": cab.get("fecha_fin"),
                "fecha_gasto": d.get("fecha_gasto"),
                "concepto": d.get("concepto"),
                "descripcion": d.get("descripcion"),
                "proveedor": d.get("proveedor"),
                "uuid": d.get("uuid"),
                "moneda": d.get("moneda"),
                "importe": _safe_float(d.get("importe")),
                "subtotal": _safe_float(d.get("subtotal")),
                "total": _safe_float(d.get("total")),
                "total_xml": _safe_float(d.get("total_xml")),
                "monto_base": base,
            }
            detalle_rows.append(row)

            if detalle_id is not None:
                uds = get_detalle_unidades_ctrl(detalle_id) or []
                if uds:
                    for u in uds:
                        pct = _safe_float(u.get("porcentaje"))
                        monto = round(base * (pct / 100.0), 2)
                        unidades_rows.append(
                            {
                                "solicitud_id": int(solicitud_id),
                                "detalle_id": detalle_id,
                                "folio": cab.get("folio"),
                                "fecha_gasto": d.get("fecha_gasto"),
                                "concepto": d.get("concepto"),
                                "id_unidad": _safe_int(u.get("id_unidad")),
                                "unidad_negocio": unidades_map.get(_safe_int(u.get("id_unidad")), "sin unidad"),
                                "porcentaje": pct,
                                "monto": monto,
                            }
                        )
                else:
                    unidades_rows.append(
                        {
                            "solicitud_id": int(solicitud_id),
                            "detalle_id": detalle_id,
                            "folio": cab.get("folio"),
                            "fecha_gasto": d.get("fecha_gasto"),
                            "concepto": d.get("concepto"),
                            "id_unidad": None,
                            "unidad_negocio": "sin unidad",
                            "porcentaje": 100.0,
                            "monto": round(base, 2),
                        }
                    )

    detalle_df = pd.DataFrame(detalle_rows)
    if detalle_df.empty:
        return detalle_df

    for col in ["fecha_inicio", "fecha_fin", "fecha_gasto"]:
        if col in detalle_df.columns:
            detalle_df[col] = pd.to_datetime(detalle_df[col], errors="coerce")

    if unidades_rows:
        unidades_df = pd.DataFrame(unidades_rows)
        if not unidades_df.empty:
            unidades_df["fecha_gasto"] = pd.to_datetime(unidades_df["fecha_gasto"], errors="coerce")
    else:
        unidades_df = pd.DataFrame(columns=["detalle_id", "unidad_negocio", "monto"])

    merged = detalle_df.copy()
    merged.attrs["unidades_df"] = unidades_df
    return merged



def _preparar_agregados(df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    if df.empty:
        return {
            "por_concepto": pd.DataFrame(),
            "por_cliente": pd.DataFrame(),
            "por_ciudad": pd.DataFrame(),
            "por_mes": pd.DataFrame(),
            "por_anio": pd.DataFrame(),
            "por_unidad": pd.DataFrame(),
        }

    work = df.copy()
    work["concepto"] = work["concepto"].apply(lambda x: _normaliza_texto(x, "sin concepto"))
    work["clientes"] = work["clientes"].apply(lambda x: _normaliza_texto(x, "sin cliente"))
    work["ciudades"] = work["ciudades"].apply(lambda x: _normaliza_texto(x, "sin ciudad"))
    work["monto_base"] = pd.to_numeric(work["monto_base"], errors="coerce").fillna(0.0)
    work["anio_gasto"] = work["fecha_gasto"].dt.year.fillna(work["fecha_inicio"].dt.year)
    work["mes"] = work["fecha_gasto"].dt.to_period("M").astype(str)

    por_concepto = (
        work.groupby("concepto", dropna=False, as_index=False)["monto_base"]
        .sum()
        .rename(columns={"monto_base": "monto"})
        .sort_values("monto", ascending=False)
    )

    por_cliente = (
        work.groupby("clientes", dropna=False, as_index=False)["monto_base"]
        .sum()
        .rename(columns={"clientes": "cliente", "monto_base": "monto"})
        .sort_values("monto", ascending=False)
    )

    por_ciudad = (
        work.groupby("ciudades", dropna=False, as_index=False)["monto_base"]
        .sum()
        .rename(columns={"ciudades": "ciudad", "monto_base": "monto"})
        .sort_values("monto", ascending=False)
    )

    por_mes = (
        work.groupby("mes", dropna=False, as_index=False)["monto_base"]
        .sum()
        .rename(columns={"monto_base": "monto"})
        .sort_values("mes")
    )

    por_anio = (
        work.groupby("anio_gasto", dropna=False, as_index=False)["monto_base"]
        .sum()
        .rename(columns={"anio_gasto": "anio", "monto_base": "monto"})
        .sort_values("anio")
    )

    unidades_df = work.attrs.get("unidades_df", pd.DataFrame()).copy()
    if not unidades_df.empty:
        unidades_df["unidad_negocio"] = unidades_df["unidad_negocio"].apply(lambda x: _normaliza_texto(x, "sin unidad"))
        unidades_df["monto"] = pd.to_numeric(unidades_df["monto"], errors="coerce").fillna(0.0)
        por_unidad = (
            unidades_df.groupby("unidad_negocio", dropna=False, as_index=False)["monto"]
            .sum()
            .sort_values("monto", ascending=False)
        )
    else:
        por_unidad = pd.DataFrame(columns=["unidad_negocio", "monto"])

    return {
        "por_concepto": por_concepto,
        "por_cliente": por_cliente,
        "por_ciudad": por_ciudad,
        "por_mes": por_mes,
        "por_anio": por_anio,
        "por_unidad": por_unidad,
    }



def _render_top(df: pd.DataFrame, label_col: str, monto_col: str = "monto", top_n: int = 10):
    if df.empty:
        st.info("sin información para mostrar")
        return

    show = df.head(top_n).copy()
    st.bar_chart(show.set_index(label_col)[monto_col])

    fmt = show.copy()
    fmt[monto_col] = fmt[monto_col].map(_fmt_money)
    st.dataframe(fmt, use_container_width=True, hide_index=True)


# =========================
# vista
# =========================

def mostrar_tab_mis_solicitudes():
    st.subheader("mis solicitudes")

    usuario_id = _get_usuario_id()
    usuario_nombre = _get_usuario_nombre()

    if usuario_id is None:
        st.error("no fue posible identificar al usuario actual en session_state['usuario']")
        return

    with st.container(border=True):
        c1, c2, c3, c4 = st.columns([1.4, 1.1, 1.1, 0.8])
        with c1:
            folio_like = st.text_input("buscar folio", key="mis_sol_folio_like")
        with c2:
            estatus = st.selectbox("estatus", ESTATUS_OPCIONES, key="mis_sol_estatus")
        with c3:
            anio_val = st.number_input(
                "año",
                min_value=2024,
                max_value=max(date.today().year + 1, 2030),
                value=date.today().year,
                step=1,
                key="mis_sol_anio",
            )
            filtrar_por_anio = st.checkbox("filtrar por año", value=False, key="mis_sol_filtrar_anio")
        with c4:
            limit = st.number_input("límite", min_value=50, max_value=5000, value=1000, step=50, key="mis_sol_limit")

        anio = int(anio_val) if filtrar_por_anio else None
        df_sol = _cargar_solicitudes_usuario(
            empleado_id=usuario_id,
            folio_like=folio_like,
            estatus=estatus,
            anio=anio,
            limit=int(limit),
        )

    st.caption(f"usuario: {usuario_nombre} · id: {usuario_id}")

    if df_sol.empty:
        st.info("no se encontraron solicitudes para los filtros seleccionados")
        return

    df_show = df_sol.copy()
    cols_preferidas = [
        "id", "folio", "empleado_nombre", "clientes", "ciudades",
        "fecha_inicio", "fecha_fin", "estatus", "fecha_creacion"
    ]
    cols_visibles = [c for c in cols_preferidas if c in df_show.columns]
    st.dataframe(df_show[cols_visibles], use_container_width=True, hide_index=True)

    solicitud_ids = tuple(int(x) for x in df_sol["id"].dropna().astype(int).tolist())
    detalle_df = _cargar_detalle_enriquecido(solicitud_ids)

    if detalle_df.empty:
        st.warning("las solicitudes encontradas no tienen detalle de gastos")
        return

    min_fecha = detalle_df["fecha_gasto"].dropna().min()
    max_fecha = detalle_df["fecha_gasto"].dropna().max()

    with st.container(border=True):
        st.markdown("#### panel dinámico")
        a1, a2, a3 = st.columns([1.3, 1.2, 1])

        with a1:
            alcance = st.selectbox(
                "analizar",
                ["todo lo filtrado"] + df_sol["folio"].astype(str).tolist(),
                key="mis_sol_alcance",
            )
        with a2:
            top_n = st.slider("top", min_value=5, max_value=30, value=10, step=1, key="mis_sol_top_n")
        with a3:
            solo_estatus = st.multiselect(
                "estatus en panel",
                options=sorted(df_sol["estatus"].dropna().astype(str).unique().tolist()),
                default=sorted(df_sol["estatus"].dropna().astype(str).unique().tolist()),
                key="mis_sol_estatus_panel",
            )

        panel_df = detalle_df.copy()

        if alcance != "todo lo filtrado":
            panel_df = panel_df[panel_df["folio"].astype(str) == str(alcance)].copy()

        if solo_estatus:
            panel_df = panel_df[panel_df["estatus"].astype(str).isin(solo_estatus)].copy()

        if min_fecha is not pd.NaT and max_fecha is not pd.NaT and pd.notna(min_fecha) and pd.notna(max_fecha):
            fecha_rango = st.date_input(
                "rango de fechas del gasto",
                value=(min_fecha.date(), max_fecha.date()),
                key="mis_sol_rango_fechas",
            )
            if isinstance(fecha_rango, tuple) and len(fecha_rango) == 2:
                f_ini, f_fin = fecha_rango
                panel_df = panel_df[
                    (panel_df["fecha_gasto"].dt.date >= f_ini) &
                    (panel_df["fecha_gasto"].dt.date <= f_fin)
                ].copy()

    if panel_df.empty:
        st.info("no hay detalle para el panel con los filtros actuales")
        return

    total_solicitudes = int(panel_df["solicitud_id"].nunique())
    total_detalles = int(panel_df["detalle_id"].nunique())
    total_gasto = float(panel_df["monto_base"].sum())
    ticket_prom = float(panel_df.groupby("solicitud_id")["monto_base"].sum().mean()) if total_solicitudes else 0.0

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("solicitudes", f"{total_solicitudes:,}")
    k2.metric("partidas", f"{total_detalles:,}")
    k3.metric("gasto total", _fmt_money(total_gasto))
    k4.metric("ticket promedio", _fmt_money(ticket_prom))

    agregados = _preparar_agregados(panel_df)

    t1, t2, t3, t4, t5 = st.tabs([
        "unidad de negocio",
        "mes / año",
        "clientes",
        "ciudades",
        "concepto",
    ])

    with t1:
        _render_top(agregados["por_unidad"], "unidad_negocio", top_n=top_n)

    with t2:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### gasto por mes")
            _render_top(agregados["por_mes"], "mes", top_n=max(top_n, 12))
        with c2:
            st.markdown("##### gasto por año")
            _render_top(agregados["por_anio"], "anio", top_n=max(top_n, 10))

    with t3:
        _render_top(agregados["por_cliente"], "cliente", top_n=top_n)

    with t4:
        _render_top(agregados["por_ciudad"], "ciudad", top_n=top_n)

    with t5:
        _render_top(agregados["por_concepto"], "concepto", top_n=top_n)

    with st.expander("ver detalle de gastos analizados", expanded=False):
        detalle_cols = [
            "folio", "estatus", "fecha_gasto", "concepto", "descripcion",
            "clientes", "ciudades", "proveedor", "uuid", "monto_base"
        ]
        detalle_show = panel_df[[c for c in detalle_cols if c in panel_df.columns]].copy()
        if "monto_base" in detalle_show.columns:
            detalle_show["monto_base"] = detalle_show["monto_base"].map(_fmt_money)
        st.dataframe(detalle_show, use_container_width=True, hide_index=True)
