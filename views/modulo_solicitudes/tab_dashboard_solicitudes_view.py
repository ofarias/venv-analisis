from __future__ import annotations

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

ROLES_DASHBOARD = {"financiero", "direccion", "admin"}


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



def _get_roles_usuario() -> List[str]:
    usuario = _get_usuario_actual()
    return [str(x).strip().lower() for x in (usuario.get("roles", []) or [])]



def _fmt_money(v: float) -> str:
    return f"${v:,.2f}"



def _normaliza_texto(v: Any, default: str = "sin dato") -> str:
    txt = str(v or "").strip()
    return txt if txt else default



def _monto_base_detalle(row: Dict[str, Any]) -> float:
    for key in ("total", "total_xml", "importe", "subtotal"):
        val = _safe_float(row.get(key), 0.0)
        if val != 0:
            return val
    return 0.0


@st.cache_data(show_spinner=False, ttl=120)
def _cargar_solicitudes(
    folio_like: str = "",
    estatus: str = "",
    anio: Optional[int] = None,
    limit: int = 2000,
) -> pd.DataFrame:
    rows = listar_solicitudes_ctrl(
        folio_like=folio_like,
        estatus=estatus,
        anio=anio,
        empleado_id=None,
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
def _cargar_detalle_dashboard(solicitud_ids: tuple[int, ...]) -> pd.DataFrame:
    if not solicitud_ids:
        return pd.DataFrame()

    unidades = get_unidades_negocio_ctrl() or []
    unidades_map = {int(x["id"]): x.get("nombre", f"unidad {x['id']}") for x in unidades if x.get("id") is not None}

    solicitudes = listar_solicitudes_ctrl(limit=max(3000, len(solicitud_ids) + 100)) or []
    sol_map = {int(s["id"]): s for s in solicitudes if s.get("id") is not None and int(s["id"]) in solicitud_ids}

    detalle_rows: List[Dict[str, Any]] = []
    unidades_rows: List[Dict[str, Any]] = []

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
                "estatus": cab.get("estatus"),
                "empleado_id": cab.get("empleado_id"),
                "empleado_nombre": cab.get("empleado_nombre"),
                "clientes": cab.get("clientes"),
                "ciudades": cab.get("ciudades"),
                "fecha_inicio": cab.get("fecha_inicio"),
                "fecha_fin": cab.get("fecha_fin"),
                "fecha_creacion": cab.get("fecha_creacion"),
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
                                "empleado_nombre": cab.get("empleado_nombre"),
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
                            "empleado_nombre": cab.get("empleado_nombre"),
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

    for col in ["fecha_inicio", "fecha_fin", "fecha_creacion", "fecha_gasto"]:
        if col in detalle_df.columns:
            detalle_df[col] = pd.to_datetime(detalle_df[col], errors="coerce")

    if unidades_rows:
        unidades_df = pd.DataFrame(unidades_rows)
        if not unidades_df.empty and "fecha_gasto" in unidades_df.columns:
            unidades_df["fecha_gasto"] = pd.to_datetime(unidades_df["fecha_gasto"], errors="coerce")
    else:
        unidades_df = pd.DataFrame(columns=["detalle_id", "unidad_negocio", "monto"])

    detalle_df.attrs["unidades_df"] = unidades_df
    return detalle_df



def _render_top(df: pd.DataFrame, label_col: str, monto_col: str = "monto", top_n: int = 10):
    if df.empty:
        st.info("sin información para mostrar")
        return

    show = df.head(top_n).copy()
    st.bar_chart(show.set_index(label_col)[monto_col])
    fmt = show.copy()
    fmt[monto_col] = fmt[monto_col].map(_fmt_money)
    st.dataframe(fmt, use_container_width=True, hide_index=True)



def _render_series(df: pd.DataFrame, label_col: str, monto_col: str = "monto"):
    if df.empty:
        st.info("sin información para mostrar")
        return
    st.line_chart(df.set_index(label_col)[monto_col])
    fmt = df.copy()
    fmt[monto_col] = fmt[monto_col].map(_fmt_money)
    st.dataframe(fmt, use_container_width=True, hide_index=True)



def mostrar_tab_dashboard_solicitudes():
    st.subheader("dashboard ejecutivo de solicitudes")

    roles = set(_get_roles_usuario())
    if not (roles & ROLES_DASHBOARD):
        st.warning("no tienes permisos para ver este dashboard")
        return

    with st.container(border=True):
        c1, c2, c3, c4 = st.columns([1.4, 1.1, 1.1, 0.8])
        with c1:
            folio_like = st.text_input("buscar folio", key="dash_sol_folio_like")
        with c2:
            estatus = st.selectbox("estatus", ESTATUS_OPCIONES, key="dash_sol_estatus")
        with c3:
            anio_val = st.number_input(
                "año",
                min_value=2024,
                max_value=max(date.today().year + 1, 2030),
                value=date.today().year,
                step=1,
                key="dash_sol_anio",
            )
            filtrar_por_anio = st.checkbox("filtrar por año", value=False, key="dash_sol_filtrar_anio")
        with c4:
            limit = st.number_input("límite", min_value=100, max_value=5000, value=2000, step=100, key="dash_sol_limit")

        anio = int(anio_val) if filtrar_por_anio else None
        df_sol = _cargar_solicitudes(
            folio_like=folio_like,
            estatus=estatus,
            anio=anio,
            limit=int(limit),
        )

    if df_sol.empty:
        st.info("no se encontraron solicitudes para los filtros seleccionados")
        return

    solicitud_ids = tuple(int(x) for x in df_sol["id"].dropna().astype(int).tolist())
    detalle_df = _cargar_detalle_dashboard(solicitud_ids)
    if detalle_df.empty:
        st.warning("las solicitudes encontradas no tienen detalle de gastos")
        return

    with st.container(border=True):
        f1, f2, f3, f4 = st.columns(4)
        with f1:
            usuarios_sel = st.multiselect(
                "usuarios",
                options=sorted(df_sol["empleado_nombre"].dropna().astype(str).unique().tolist()),
                default=[],
                key="dash_sol_usuarios",
            )
        with f2:
            conceptos_sel = st.multiselect(
                "conceptos",
                options=sorted(detalle_df["concepto"].dropna().astype(str).unique().tolist()),
                default=[],
                key="dash_sol_conceptos",
            )
        with f3:
            top_n = st.slider("top", min_value=5, max_value=20, value=10, step=1, key="dash_sol_top_n")
        with f4:
            estatus_panel = st.multiselect(
                "estatus en panel",
                options=sorted(df_sol["estatus"].dropna().astype(str).unique().tolist()),
                default=sorted(df_sol["estatus"].dropna().astype(str).unique().tolist()),
                key="dash_sol_estatus_panel",
            )

        panel_sol = df_sol.copy()
        panel_df = detalle_df.copy()

        if usuarios_sel:
            panel_sol = panel_sol[panel_sol["empleado_nombre"].astype(str).isin(usuarios_sel)].copy()
            panel_df = panel_df[panel_df["empleado_nombre"].astype(str).isin(usuarios_sel)].copy()

        if conceptos_sel:
            panel_df = panel_df[panel_df["concepto"].astype(str).isin(conceptos_sel)].copy()

        if estatus_panel:
            panel_sol = panel_sol[panel_sol["estatus"].astype(str).isin(estatus_panel)].copy()
            panel_df = panel_df[panel_df["estatus"].astype(str).isin(estatus_panel)].copy()

        min_fecha = panel_df["fecha_gasto"].dropna().min()
        max_fecha = panel_df["fecha_gasto"].dropna().max()
        if min_fecha is not pd.NaT and max_fecha is not pd.NaT and pd.notna(min_fecha) and pd.notna(max_fecha):
            fecha_rango = st.date_input(
                "rango de fechas del gasto",
                value=(min_fecha.date(), max_fecha.date()),
                key="dash_sol_rango_fechas",
            )
            if isinstance(fecha_rango, tuple) and len(fecha_rango) == 2:
                f_ini, f_fin = fecha_rango
                panel_df = panel_df[
                    (panel_df["fecha_gasto"].dt.date >= f_ini)
                    & (panel_df["fecha_gasto"].dt.date <= f_fin)
                ].copy()

    if panel_df.empty:
        st.info("no hay información para el dashboard con los filtros actuales")
        return

    solicitud_ids_panel = set(panel_df["solicitud_id"].dropna().astype(int).tolist())
    panel_sol = panel_sol[panel_sol["id"].astype(int).isin(solicitud_ids_panel)].copy() if not panel_sol.empty else panel_sol

    total_solicitudes = int(panel_df["solicitud_id"].nunique())
    total_partidas = int(panel_df["detalle_id"].nunique())
    total_gasto = float(panel_df["monto_base"].sum())
    ticket_prom = float(panel_df.groupby("solicitud_id")["monto_base"].sum().mean()) if total_solicitudes else 0.0

    rechazadas = int(panel_sol[panel_sol["estatus"].astype(str).str.lower() == "rechazada"]["id"].nunique()) if not panel_sol.empty else 0
    pct_rechazo = (rechazadas / total_solicitudes * 100.0) if total_solicitudes else 0.0

    pendientes_mask = panel_sol["estatus"].astype(str).str.lower().isin([
        "captura", "enviada", "autorizada ventas", "dispersion", "contabilidad", "revision ventas", "poliza", "revision comprobacion"
    ]) if not panel_sol.empty else pd.Series(dtype=bool)
    pendientes = int(panel_sol[pendientes_mask]["id"].nunique()) if not panel_sol.empty else 0

    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("gasto total", _fmt_money(total_gasto))
    k2.metric("solicitudes", f"{total_solicitudes:,}")
    k3.metric("partidas", f"{total_partidas:,}")
    k4.metric("ticket promedio", _fmt_money(ticket_prom))
    k5.metric("pendientes", f"{pendientes:,}")
    k6.metric("% rechazo", f"{pct_rechazo:,.1f}%")

    work = panel_df.copy()
    work["concepto"] = work["concepto"].apply(lambda x: _normaliza_texto(x, "sin concepto"))
    work["clientes"] = work["clientes"].apply(lambda x: _normaliza_texto(x, "sin cliente"))
    work["ciudades"] = work["ciudades"].apply(lambda x: _normaliza_texto(x, "sin ciudad"))
    work["empleado_nombre"] = work["empleado_nombre"].apply(lambda x: _normaliza_texto(x, "sin usuario"))
    work["monto_base"] = pd.to_numeric(work["monto_base"], errors="coerce").fillna(0.0)
    work["mes"] = work["fecha_gasto"].dt.to_period("M").astype(str)

    por_mes = (
        work.groupby("mes", as_index=False)["monto_base"]
        .sum()
        .rename(columns={"monto_base": "monto"})
        .sort_values("mes")
    )
    por_concepto = (
        work.groupby("concepto", as_index=False)["monto_base"]
        .sum()
        .rename(columns={"monto_base": "monto"})
        .sort_values("monto", ascending=False)
    )
    por_usuario = (
        work.groupby("empleado_nombre", as_index=False)["monto_base"]
        .sum()
        .rename(columns={"empleado_nombre": "usuario", "monto_base": "monto"})
        .sort_values("monto", ascending=False)
    )
    por_cliente = (
        work.groupby("clientes", as_index=False)["monto_base"]
        .sum()
        .rename(columns={"clientes": "cliente", "monto_base": "monto"})
        .sort_values("monto", ascending=False)
    )
    por_ciudad = (
        work.groupby("ciudades", as_index=False)["monto_base"]
        .sum()
        .rename(columns={"ciudades": "ciudad", "monto_base": "monto"})
        .sort_values("monto", ascending=False)
    )

    unidades_df = work.attrs.get("unidades_df", pd.DataFrame()).copy()
    if not unidades_df.empty:
        unidades_df = unidades_df[unidades_df["solicitud_id"].isin(solicitud_ids_panel)].copy()
        unidades_df["unidad_negocio"] = unidades_df["unidad_negocio"].apply(lambda x: _normaliza_texto(x, "sin unidad"))
        unidades_df["monto"] = pd.to_numeric(unidades_df["monto"], errors="coerce").fillna(0.0)
        por_unidad = unidades_df.groupby("unidad_negocio", as_index=False)["monto"].sum().sort_values("monto", ascending=False)
    else:
        por_unidad = pd.DataFrame(columns=["unidad_negocio", "monto"])

    por_estatus = (
        panel_sol.groupby("estatus", as_index=False)["id"]
        .nunique()
        .rename(columns={"id": "solicitudes"})
        .sort_values("solicitudes", ascending=False)
        if not panel_sol.empty else pd.DataFrame(columns=["estatus", "solicitudes"])
    )

    g1, g2 = st.columns(2)
    with g1:
        st.markdown("#### gasto por mes")
        _render_series(por_mes, "mes")
    with g2:
        st.markdown("#### solicitudes por estatus")
        if por_estatus.empty:
            st.info("sin información para mostrar")
        else:
            st.bar_chart(por_estatus.set_index("estatus")["solicitudes"])
            st.dataframe(por_estatus, use_container_width=True, hide_index=True)

    t1, t2, t3, t4, t5 = st.tabs([
        "unidad de negocio",
        "usuarios",
        "conceptos",
        "clientes / ciudades",
        "detalle",
    ])

    with t1:
        _render_top(por_unidad, "unidad_negocio", top_n=top_n)

    with t2:
        _render_top(por_usuario, "usuario", top_n=top_n)

    with t3:
        _render_top(por_concepto, "concepto", top_n=top_n)

    with t4:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### top clientes")
            _render_top(por_cliente, "cliente", top_n=top_n)
        with c2:
            st.markdown("##### top ciudades")
            _render_top(por_ciudad, "ciudad", top_n=top_n)

    with t5:
        detalle_cols = [
            "folio", "estatus", "empleado_nombre", "fecha_gasto", "concepto", "descripcion",
            "clientes", "ciudades", "proveedor", "uuid", "monto_base"
        ]
        detalle_show = work[[c for c in detalle_cols if c in work.columns]].copy()
        if "monto_base" in detalle_show.columns:
            detalle_show["monto_base"] = detalle_show["monto_base"].map(_fmt_money)
        st.dataframe(detalle_show, use_container_width=True, hide_index=True)
