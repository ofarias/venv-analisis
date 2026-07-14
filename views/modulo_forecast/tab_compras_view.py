from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from controllers.forecast_controller import calcular_necesidades_compra_ctrl
from controllers.compras_solicitudes_controller import (
    obtener_tipo_compra_mp_inventario_ctrl,
    crear_solicitud_mp_inventario_ctrl,
)


_MESES = {1:"ene",2:"feb",3:"mar",4:"abr",5:"may",6:"jun",
          7:"jul",8:"ago",9:"sep",10:"oct",11:"nov",12:"dic"}

_SEV_COLOR = {"alta": "🔴", "media": "🟡", "baja": "🟢"}


def _severidad(compra: float, necesidad: float) -> str:
    if necesidad <= 0:
        return "baja"
    pct = compra / necesidad if necesidad > 0 else 0
    if pct > 0.5:
        return "alta"
    if pct > 0.1:
        return "media"
    return "baja"


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


def _generar_solicitud_compra_mp(df_mp: pd.DataFrame, id_version: int, anio: int) -> None:
    tipo_mp_inv = obtener_tipo_compra_mp_inventario_ctrl()
    if not tipo_mp_inv:
        st.error(
            "no existe el tipo de compra 'Materia Prima (Inventario)'. "
            "corre la migración migration_compras_mp_inventario_v1.sql."
        )
        return

    filas = df_mp[df_mp["compra_requerida"] > 0]
    if filas.empty:
        st.warning("no hay materias primas con compra requerida > 0 para generar la solicitud")
        return

    detalle = [
        {
            "cve_mp": str(r["cve_mp"]),
            "mp_nombre": str(r["mp_nombre"]),
            "cantidad_kg": float(r["compra_requerida"]),
            "existencia_mp_kg": float(r["existencia_mp"]),
            "anio": int(r["anio"]),
            "mes": int(r["mes"]),
            "id_version_forecast": int(id_version),
            "observaciones": f"generado desde forecast versión {id_version} ({_MESES.get(int(r['mes']), r['mes']).upper()} {int(r['anio'])})",
        }
        for _, r in filas.iterrows()
    ]

    ok, mensaje = crear_solicitud_mp_inventario_ctrl(
        id_tipo_compra=int(tipo_mp_inv["id_tipo_compra"]),
        fecha_solicitud=date.today(),
        solicitante=_get_solicitante_actual(),
        observaciones_generales=f"necesidad de compra generada desde forecast versión {id_version} ({anio})",
        detalle=detalle,
    )

    if ok:
        st.success(f"{mensaje}. Ve a Compras → Pendientes para revisarla y enviarla.")
    else:
        st.error(mensaje)


def _agregar_por_mp(df: pd.DataFrame) -> pd.DataFrame:
    """Agrupa el detalle por materia prima × mes (la existencia es un stock
    compartido entre productos, por eso la compra requerida se recalcula aquí
    y no se suma directo desde el detalle)."""
    agg = df.groupby(["cve_mp", "mp_nombre", "mes", "anio"], as_index=False).agg(
        necesidad_kg=("necesidad_kg", "sum"),
        existencia_mp=("existencia_mp", "first"),
        cve_prod=("cve_prod", lambda x: ", ".join(sorted(set(x)))),
    )
    agg["compra_requerida"] = (agg["necesidad_kg"] - agg["existencia_mp"]).clip(lower=0).round(2)
    return agg


def mostrar_tab_compras(id_version: int, anio: int, meses: list[int]) -> None:
    if not meses:
        st.warning("selecciona meses en el tab de construcción")
        return

    st.caption(
        "Cruce de **forecast KG × existencias de producto terminado (almacén 18)**, "
        "netadas mes a mes para obtener lo que realmente falta producir, "
        "**× composición de materias primas (B) de cada fórmula (carrier + enzimas + "
        "auxiliares) × existencias MP (almacén 17)**. "
        "Si un producto del forecast no tiene fórmula registrada, se asume que ese "
        "producto **es** la materia prima que se requiere comprar/consumir directamente."
    )

    if st.button("🔄 calcular necesidades", type="primary", use_container_width=False, key="comp_btn_calc"):
        st.session_state["comp_calculado"] = True

    if not st.session_state.get("comp_calculado"):
        st.info("pulsa 'calcular necesidades' para iniciar el análisis")
        return

    with st.spinner("cruzando forecast × existencias PT (almacén 18) × fórmulas × existencias MP (almacén 17)…"):
        df = calcular_necesidades_compra_ctrl(
            id_version=id_version,
            anio=anio,
            meses=meses,
        )

    if df is None or df.empty:
        st.warning(
            "no se encontraron necesidades de compra. Posibles causas:\n"
            "- El forecast KG aún no tiene datos\n"
            "- Las fórmulas no tienen cve_sae ni materias primas (carrier/enzimas/auxiliares) capturadas"
        )
        return

    # ── KPIs ──────────────────────────────────────────────────────────────────
    df_mp = _agregar_por_mp(df)
    df_mp["severidad"] = df_mp.apply(
        lambda r: _severidad(float(r.get("compra_requerida") or 0), float(r.get("necesidad_kg") or 0)), axis=1
    )

    total_mp = df["cve_mp"].nunique()
    total_pt = df["cve_prod"].nunique()
    directos = df.loc[df["origen"] != "fórmula", "cve_prod"].nunique()
    criticas = (df_mp["severidad"] == "alta").sum()
    total_compra = df_mp["compra_requerida"].sum()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("materias primas analizadas", total_mp)
    c2.metric("productos terminados", f"{total_pt} ({directos} sin fórmula)")
    c3.metric("necesidades críticas (>50% descubierto)", criticas)
    c4.metric("total a comprar (kg)", f"{total_compra:,.2f}")

    if st.button("📝 generar solicitud de compra", type="primary", key="comp_btn_generar_solicitud"):
        _generar_solicitud_compra_mp(df_mp, id_version=id_version, anio=anio)

    st.divider()

    # ── vista ─────────────────────────────────────────────────────────────────
    vista = st.radio(
        "agrupar por", ["materia prima", "producto terminado", "mes"], horizontal=True, key="comp_vista"
    )

    if vista == "mes":
        for mes in sorted(meses):
            df_mes = df_mp[df_mp["mes"] == mes].copy()
            if df_mes.empty:
                continue
            con_compra = df_mes[df_mes["compra_requerida"] > 0]
            st.markdown(f"**{_MESES[mes].upper()} {anio}** — {len(con_compra)} MP a comprar")
            if not con_compra.empty:
                _tabla_compras_mp(con_compra)

    elif vista == "producto terminado":
        _vista_por_pt(df)

    else:
        # pivot: MP × mes
        df_crit = df_mp[df_mp["compra_requerida"] > 0].copy()
        if df_crit.empty:
            st.success("no se requieren compras adicionales de MP para el período")
            return

        pivot = df_crit.pivot_table(
            index=["cve_mp", "mp_nombre", "existencia_mp"],
            columns="mes",
            values="compra_requerida",
            aggfunc="sum",
            fill_value=0.0,
        ).reset_index()
        pivot.columns = [
            c if isinstance(c, str) else f"{_MESES.get(c, str(c)).upper()}"
            for c in pivot.columns
        ]
        pivot["total"] = pivot[[c for c in pivot.columns if c not in ["cve_mp", "mp_nombre", "existencia_mp"]]].sum(axis=1)
        pivot = pivot.sort_values("total", ascending=False)

        col_cfg = {
            "cve_mp": st.column_config.TextColumn("cve MP", disabled=True),
            "mp_nombre": st.column_config.TextColumn("materia prima", disabled=True),
            "existencia_mp": st.column_config.NumberColumn("existencia actual (kg)", format="%.2f", disabled=True),
            "total": st.column_config.NumberColumn("total a comprar (kg)", format="%.2f", disabled=True),
        }
        for mes in meses:
            mn = _MESES[mes].upper()
            if mn in pivot.columns:
                col_cfg[mn] = st.column_config.NumberColumn(mn, format="%.2f", disabled=True)

        st.dataframe(
            pivot,
            use_container_width=True,
            hide_index=True,
            column_config=col_cfg,
            height=min(56 + len(pivot) * 35, 600),
        )

    st.divider()

    # ── tabla completa con severidad ──────────────────────────────────────────
    with st.expander("ver detalle completo (por materia prima)"):
        _tabla_compras_mp(df_mp[df_mp["compra_requerida"] > 0])

    with st.expander("ver detalle completo (por producto terminado × materia prima)"):
        _tabla_detalle_pt(df)

    # ── descarga CSV ──────────────────────────────────────────────────────────
    if not df.empty:
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ descargar CSV (detalle PT × MP)",
            data=csv,
            file_name=f"necesidades_compra_{anio}_v{id_version}.csv",
            mime="text/csv",
            key="comp_dl_csv",
        )


def _vista_por_pt(df: pd.DataFrame) -> None:
    resumen = df.groupby(["cve_prod", "producto_pt", "origen", "mes"], as_index=False).agg(
        forecast_kg=("forecast_kg", "first"),
        existencia_pt=("existencia_pt", "first"),
        necesidad_mp_kg=("necesidad_kg", "sum"),
        materias_primas=("cve_mp", lambda x: ", ".join(sorted(set(x)))),
    )
    resumen["mes_nombre"] = resumen["mes"].map(_MESES).str.upper()
    resumen = resumen.sort_values(["producto_pt", "mes"])

    st.dataframe(
        resumen[["cve_prod", "producto_pt", "origen", "mes_nombre", "forecast_kg", "existencia_pt", "necesidad_mp_kg", "materias_primas"]],
        use_container_width=True,
        hide_index=True,
        column_config={
            "cve_prod": st.column_config.TextColumn("cve PT", disabled=True),
            "producto_pt": st.column_config.TextColumn("producto terminado", disabled=True),
            "origen": st.column_config.TextColumn("origen", disabled=True),
            "mes_nombre": st.column_config.TextColumn("mes", disabled=True),
            "forecast_kg": st.column_config.NumberColumn("forecast PT (kg)", format="%.2f", disabled=True),
            "existencia_pt": st.column_config.NumberColumn("existencia PT alm.18 (kg)", format="%.2f", disabled=True),
            "necesidad_mp_kg": st.column_config.NumberColumn("materia prima requerida (kg)", format="%.2f", disabled=True),
            "materias_primas": st.column_config.TextColumn("materias primas (cve)", disabled=True),
        },
        height=min(56 + len(resumen) * 35, 600),
    )


def _tabla_detalle_pt(df: pd.DataFrame) -> None:
    cols_mostrar = [c for c in [
        "cve_prod", "producto_pt", "origen", "cve_mp", "mp_nombre",
        "mes", "forecast_kg", "existencia_pt", "necesidad_kg",
    ] if c in df.columns]
    df_show = df[cols_mostrar].copy()
    if "mes" in df_show.columns:
        df_show["mes"] = df_show["mes"].map(_MESES).str.upper()

    st.dataframe(
        df_show,
        use_container_width=True,
        hide_index=True,
        column_config={
            "cve_prod": st.column_config.TextColumn("cve PT", disabled=True),
            "producto_pt": st.column_config.TextColumn("producto terminado", disabled=True),
            "origen": st.column_config.TextColumn("origen", disabled=True),
            "cve_mp": st.column_config.TextColumn("cve MP", disabled=True),
            "mp_nombre": st.column_config.TextColumn("materia prima", disabled=True),
            "mes": st.column_config.TextColumn("mes", disabled=True),
            "forecast_kg": st.column_config.NumberColumn("forecast PT (kg)", format="%.2f", disabled=True),
            "existencia_pt": st.column_config.NumberColumn("existencia PT alm.18 (kg)", format="%.2f", disabled=True),
            "necesidad_kg": st.column_config.NumberColumn("necesidad MP (kg)", format="%.2f", disabled=True),
        },
        height=min(56 + len(df_show) * 35, 500),
    )


def _tabla_compras_mp(df: pd.DataFrame) -> None:
    cols_mostrar = [c for c in [
        "severidad", "cve_mp", "mp_nombre", "mes", "necesidad_kg",
        "existencia_mp", "compra_requerida", "cve_prod",
    ] if c in df.columns]
    df_show = df[cols_mostrar].copy()
    if "severidad" in df_show.columns:
        df_show["🚦"] = df_show["severidad"].map(_SEV_COLOR)
        df_show = df_show.drop(columns=["severidad"])
        df_show = df_show[["🚦"] + [c for c in df_show.columns if c != "🚦"]]
    if "mes" in df_show.columns:
        df_show["mes"] = df_show["mes"].map(_MESES).str.upper()

    col_cfg = {
        "🚦": st.column_config.TextColumn("🚦", width="small", disabled=True),
        "cve_mp": st.column_config.TextColumn("cve MP", disabled=True),
        "mp_nombre": st.column_config.TextColumn("materia prima", disabled=True),
        "mes": st.column_config.TextColumn("mes", disabled=True),
        "necesidad_kg": st.column_config.NumberColumn("necesidad (kg)", format="%.2f", disabled=True),
        "existencia_mp": st.column_config.NumberColumn("existencia (kg)", format="%.2f", disabled=True),
        "compra_requerida": st.column_config.NumberColumn("a comprar (kg)", format="%.2f", disabled=True),
        "cve_prod": st.column_config.TextColumn("productos terminados", disabled=True),
    }
    st.dataframe(
        df_show,
        use_container_width=True,
        hide_index=True,
        column_config=col_cfg,
        height=min(56 + len(df_show) * 35, 500),
    )
