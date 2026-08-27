from __future__ import annotations

import secrets as _secrets
from datetime import date
from io import BytesIO
from typing import Optional

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from controllers.presupuesto_ventas_controller import (
    guardar_reporte_ventas_ctrl,
    obtener_cargas_presupuesto_ventas_ctrl,
    obtener_presupuesto_ventas_ctrl,
    obtener_reporte_ventas_ctrl,
    obtener_ventas_reales_sae_pv_ctrl,
)
from controllers.solicitudes_controller import get_correos_usuarios_por_rol_ctrl
from utils.envio_correo import enviar_correo

_MESES_ABR = {1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr", 5: "May", 6: "Jun",
              7: "Jul", 8: "Ago", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic"}


# ── cálculo de los datos (una sola fuente de verdad para HTML, PDF y correo) ──

def _calcular_datos_reporte(id_carga: int, anio: int) -> Optional[dict]:
    """Presupuesto capturado (id_carga) vs venta real de Aspel SAE, cruzando
    por cliente + producto SAE — mismo criterio que usa el panel de
    comparación de la tabla de captura. Solo se compara contra los meses ya
    transcurridos del año (los futuros no tienen real que mostrar)."""
    df = obtener_presupuesto_ventas_ctrl(id_carga=id_carga)
    if df is None or df.empty:
        return None

    df = df.copy()
    df["mes"] = pd.to_numeric(df["mes"], errors="coerce").fillna(0).astype(int)
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce").fillna(0.0)
    df["importe"] = pd.to_numeric(df["importe"], errors="coerce").fillna(0.0)
    df["cve_clie"] = df["cliente_excel"].astype(str).str.split(" - ", n=1).str[0].str.strip()
    df["cliente_nombre"] = (
        df["cliente_excel"].astype(str).str.split(" - ", n=1).str[1]
        .fillna(df["cliente_excel"]).astype(str).str.strip()
    )

    real = obtener_ventas_reales_sae_pv_ctrl(int(anio))
    if real is None:
        real = pd.DataFrame(columns=["cve_art", "cve_clie", "mes", "cantidad", "importe"])
    real = real.copy()
    if not real.empty:
        real["cve_art"] = real["cve_art"].astype(str).str.strip()
        real["cve_clie"] = real["cve_clie"].astype(str).str.strip()
        real["mes"] = pd.to_numeric(real["mes"], errors="coerce").fillna(0).astype(int)

    # el real se acota a los códigos (producto/cliente) que sí aparecen en el
    # presupuesto — evita traer ventas SAE ajenas a esta carga
    codigos_art = set(df["cve_prod"].dropna().astype(str).str.strip()) - {""}
    codigos_clie = set(df["cve_clie"].dropna()) - {""}
    if not real.empty and (codigos_art or codigos_clie):
        real_f = real[real["cve_art"].isin(codigos_art) & real["cve_clie"].isin(codigos_clie)]
    else:
        real_f = real.iloc[0:0]

    hoy = date.today()
    meses_transc = [m for m in range(1, 13) if (int(anio), m) <= (hoy.year, hoy.month)]

    por_mes = df.groupby("mes", as_index=False).agg(usd=("importe", "sum"))
    real_por_mes = (
        real_f.groupby("mes", as_index=False).agg(usd=("importe", "sum"))
        if not real_f.empty else pd.DataFrame(columns=["mes", "usd"])
    )

    meses_data = []
    for m in range(1, 13):
        p = por_mes[por_mes["mes"] == m]
        r = real_por_mes[real_por_mes["mes"] == m]
        meses_data.append({
            "mes": _MESES_ABR[m],
            "presupuesto_usd": round(float(p["usd"].iloc[0]), 2) if not p.empty else 0.0,
            "real_usd": round(float(r["usd"].iloc[0]), 2) if (not r.empty and m in meses_transc) else None,
            "transcurrido": m in meses_transc,
        })

    grp_cli = df.groupby(["cve_clie", "cliente_nombre"], as_index=False).agg(
        pres_kg=("valor", "sum"), pres_usd=("importe", "sum"),
    )
    real_cli = (
        real_f[real_f["mes"].isin(meses_transc)].groupby("cve_clie", as_index=False).agg(
            real_kg=("cantidad", "sum"), real_usd=("importe", "sum"),
        ) if not real_f.empty else pd.DataFrame(columns=["cve_clie", "real_kg", "real_usd"])
    )
    top_cli = grp_cli.merge(real_cli, on="cve_clie", how="left").fillna({"real_kg": 0.0, "real_usd": 0.0})
    top_cli["cumpl"] = (top_cli["real_usd"] / top_cli["pres_usd"].replace(0, pd.NA) * 100).round(1)
    top_cli = top_cli.sort_values("pres_usd", ascending=False)

    grp_prod = df.groupby(["cve_prod", "producto_excel"], as_index=False).agg(
        pres_kg=("valor", "sum"), pres_usd=("importe", "sum"),
    )
    real_prod = (
        real_f[real_f["mes"].isin(meses_transc)].groupby("cve_art", as_index=False).agg(
            real_kg=("cantidad", "sum"), real_usd=("importe", "sum"),
        ) if not real_f.empty else pd.DataFrame(columns=["cve_art", "real_kg", "real_usd"])
    )
    top_prod = grp_prod.merge(real_prod, left_on="cve_prod", right_on="cve_art", how="left").fillna({"real_kg": 0.0, "real_usd": 0.0})
    top_prod["cumpl"] = (top_prod["real_usd"] / top_prod["pres_usd"].replace(0, pd.NA) * 100).round(1)
    top_prod = top_prod.sort_values("pres_usd", ascending=False)

    pres_transc_usd = float(df[df["mes"].isin(meses_transc)]["importe"].sum())
    real_transc_usd = float(real_f[real_f["mes"].isin(meses_transc)]["importe"].sum()) if not real_f.empty else 0.0

    cargas = obtener_cargas_presupuesto_ventas_ctrl(id_carga=id_carga, limit=1)
    carga_row = cargas.to_dict("records")[0] if cargas is not None and not cargas.empty else {}

    return {
        "generado": hoy.isoformat(),
        "mes_actual_label": _MESES_ABR[hoy.month],
        "mes_actual_num": hoy.month,
        "carga": carga_row,
        "kpi": {
            "total_presupuesto_usd": round(float(df["importe"].sum()), 2),
            "total_presupuesto_kg": round(float(df["valor"].sum()), 2),
            "pres_transc_usd": round(pres_transc_usd, 2),
            "real_transc_usd": round(real_transc_usd, 2),
            "cumplimiento_pct": round(real_transc_usd / pres_transc_usd * 100, 1) if pres_transc_usd else None,
            "num_clientes": int(df["cve_clie"].nunique()),
            "num_productos": int(df["cve_prod"].nunique()),
            "meses_transcurridos": [_MESES_ABR[m] for m in meses_transc],
        },
        "meses": meses_data,
        "top_clientes": top_cli[["cliente_nombre", "pres_kg", "pres_usd", "real_kg", "real_usd", "cumpl"]].round(2).to_dict("records"),
        "top_productos": top_prod[["producto_excel", "pres_kg", "pres_usd", "real_kg", "real_usd", "cumpl"]].round(2).to_dict("records"),
    }


def _fmt_usd(v, decimals=0) -> str:
    if v is None:
        return "—"
    return f"${v:,.{decimals}f}"


def _fmt_kg(v) -> str:
    if v is None:
        return "—"
    return f"{v:,.0f} kg"


def _fmt_pct(v) -> str:
    if v is None:
        return "—"
    return f"{v:,.1f}%"


def _pill_class(v) -> str:
    if v is None:
        return "pill-none"
    if v >= 90:
        return "pill-good"
    if v >= 60:
        return "pill-warn"
    return "pill-crit"


def _pill_label(v) -> str:
    if v is None:
        return "sin real"
    if v >= 90:
        return "en línea"
    if v >= 60:
        return "atención"
    return "crítico"


# ── HTML ────────────────────────────────────────────────────────────────────

def _generar_reporte_ventas_html(datos: dict) -> str:
    KPI, MESES = datos["kpi"], datos["meses"]
    CLIENTES, PRODUCTOS, CARGA = datos["top_clientes"], datos["top_productos"], datos["carga"]

    presupuestos_validos = [m["presupuesto_usd"] for m in MESES if m["presupuesto_usd"]]
    reales_validos = [m["real_usd"] for m in MESES if m["real_usd"]]
    chart_max_raw = max(presupuestos_validos + reales_validos + [1.0])
    # redondea el techo del eje a un escalón "limpio" (1/2/5 × 10^n) con margen
    import math
    exp = math.floor(math.log10(chart_max_raw))
    for base in (1, 2, 2.5, 5, 10):
        techo = base * (10 ** exp)
        if techo >= chart_max_raw * 1.12:
            chart_max = techo
            break
    else:
        chart_max = chart_max_raw * 1.15
    ticks = [round(chart_max * f) for f in (0, 0.25, 0.5, 0.75)]
    chart_h = 220

    def bar_h(v):
        return 0 if v is None else round(v / chart_max * chart_h, 1)

    meses_html = []
    for m in MESES:
        p_h = bar_h(m["presupuesto_usd"])
        if m["transcurrido"] and m["real_usd"] is not None:
            real_bar = (
                f'<div class="bar bar-real" style="height:{bar_h(m["real_usd"])}px" '
                f'data-tip="Real {m["mes"]}: {_fmt_usd(m["real_usd"])}"></div>'
            )
        else:
            real_bar = '<div class="bar bar-future" title="mes aún no transcurrido"></div>'
        meses_html.append(f'''
      <div class="month-col">
        <div class="bars">
          <div class="bar bar-pres" style="height:{p_h}px" data-tip="Presupuesto {m["mes"]}: {_fmt_usd(m["presupuesto_usd"])}"></div>
          {real_bar}
        </div>
        <div class="month-label">{m["mes"]}</div>
      </div>''')

    ticks_html = "".join(
        f'<div class="tick" style="bottom:{round(t / chart_max * chart_h, 1)}px"><span>{t // 1000:,}K</span></div>'
        for t in ticks
    )

    def fila(nombre_col, r):
        return f'''
        <tr>
          <td class="col-name">{r[nombre_col]}</td>
          <td class="num">{_fmt_usd(r["pres_usd"])}</td>
          <td class="num muted">{_fmt_kg(r["pres_kg"])}</td>
          <td class="num">{_fmt_usd(r["real_usd"])}</td>
          <td class="num muted">{_fmt_kg(r["real_kg"])}</td>
          <td class="num"><span class="pill {_pill_class(r["cumpl"])}">{_fmt_pct(r["cumpl"])}</span></td>
        </tr>'''

    filas_clientes = "".join(fila("cliente_nombre", r) for r in CLIENTES)
    filas_productos = "".join(fila("producto_excel", r) for r in PRODUCTOS)

    cumpl_pill = _pill_class(KPI["cumplimiento_pct"])
    cumpl_label = _pill_label(KPI["cumplimiento_pct"])

    return f'''<!doctype html>
<title>Avance de Ventas {CARGA.get("anio", "")}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  :root {{
    --page: #f6f7f9; --surface: #ffffff; --surface-2: #f0f2f5;
    --ink: #12151a; --ink-soft: #4a505c; --ink-mute: #868d99; --hairline: #e3e6ea;
    --accent-pres: #2a78d6; --accent-real: #eb6834;
    --good: #0ca30c; --good-bg: #e5f6e5; --warn: #b3790a; --warn-bg: #fdf0d6;
    --crit: #d03b3b; --crit-bg: #fbe4e4; --none-bg: #eef0f3; --none-ink: #767c87;
    --shadow: 0 1px 2px rgba(18,21,26,0.04), 0 8px 24px -12px rgba(18,21,26,0.10);
  }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      --page: #101214; --surface: #17191d; --surface-2: #1e2126;
      --ink: #f3f4f6; --ink-soft: #c1c6cf; --ink-mute: #868d99; --hairline: #2a2d33;
      --accent-pres: #3987e5; --accent-real: #d95926;
      --good: #0ca30c; --good-bg: #123319; --warn: #fab219; --warn-bg: #3a2c0c;
      --crit: #e66767; --crit-bg: #3a1616; --none-bg: #24272c; --none-ink: #9aa0aa;
      --shadow: 0 1px 2px rgba(0,0,0,0.3), 0 8px 24px -12px rgba(0,0,0,0.5);
    }}
  }}
  :root[data-theme="dark"] {{
    --page: #101214; --surface: #17191d; --surface-2: #1e2126;
    --ink: #f3f4f6; --ink-soft: #c1c6cf; --ink-mute: #868d99; --hairline: #2a2d33;
    --accent-pres: #3987e5; --accent-real: #d95926;
    --good: #0ca30c; --good-bg: #123319; --warn: #fab219; --warn-bg: #3a2c0c;
    --crit: #e66767; --crit-bg: #3a1616; --none-bg: #24272c; --none-ink: #9aa0aa;
    --shadow: 0 1px 2px rgba(0,0,0,0.3), 0 8px 24px -12px rgba(0,0,0,0.5);
  }}
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; padding: 0; }}
  body {{ background: var(--page); color: var(--ink); font-family: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif; -webkit-font-smoothing: antialiased; }}
  .wrap {{ max-width: 1080px; margin: 0 auto; padding: 40px 24px 80px; display: flex; flex-direction: column; gap: 28px; }}
  .mono {{ font-family: "IBM Plex Mono", ui-monospace, monospace; }}
  header {{ display: flex; flex-direction: column; gap: 6px; padding-bottom: 20px; border-bottom: 1px solid var(--hairline); }}
  .eyebrow {{ font-size: 12px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: var(--ink-mute); }}
  h1 {{ margin: 0; font-size: 32px; font-weight: 700; letter-spacing: -0.01em; text-wrap: balance; }}
  .meta {{ display: flex; flex-wrap: wrap; gap: 4px 18px; font-size: 13px; color: var(--ink-soft); }}
  .meta b {{ color: var(--ink); font-weight: 600; }}
  .estado-chip {{ display: inline-flex; align-items: center; gap: 6px; padding: 2px 10px; border-radius: 999px; background: var(--surface-2); font-size: 12px; font-weight: 600; color: var(--ink-soft); }}
  .estado-chip::before {{ content: ""; width: 6px; height: 6px; border-radius: 50%; background: var(--accent-pres); }}
  .kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; }}
  .kpi {{ background: var(--surface); border: 1px solid var(--hairline); border-radius: 10px; padding: 16px 18px; display: flex; flex-direction: column; gap: 6px; box-shadow: var(--shadow); }}
  .kpi .label {{ font-size: 12px; color: var(--ink-mute); font-weight: 500; }}
  .kpi .value {{ font-size: 24px; font-weight: 600; letter-spacing: -0.01em; }}
  .kpi .sub {{ font-size: 12px; color: var(--ink-soft); }}
  .pill {{ display: inline-flex; align-items: center; padding: 2px 9px; border-radius: 999px; font-size: 12px; font-weight: 600; font-family: "IBM Plex Mono", ui-monospace, monospace; }}
  .pill-good {{ background: var(--good-bg); color: var(--good); }}
  .pill-warn {{ background: var(--warn-bg); color: var(--warn); }}
  .pill-crit {{ background: var(--crit-bg); color: var(--crit); }}
  .pill-none {{ background: var(--none-bg); color: var(--none-ink); }}
  section {{ background: var(--surface); border: 1px solid var(--hairline); border-radius: 12px; padding: 22px 24px 24px; box-shadow: var(--shadow); }}
  .section-head {{ display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin-bottom: 4px; flex-wrap: wrap; }}
  h2 {{ margin: 0; font-size: 17px; font-weight: 600; }}
  .section-note {{ font-size: 12.5px; color: var(--ink-mute); }}
  .legend {{ display: flex; gap: 18px; font-size: 12.5px; color: var(--ink-soft); margin: 10px 0 18px; }}
  .legend-item {{ display: flex; align-items: center; gap: 6px; }}
  .swatch {{ width: 10px; height: 10px; border-radius: 2px; }}
  .swatch-pres {{ background: var(--accent-pres); }}
  .swatch-real {{ background: var(--accent-real); }}
  .swatch-future {{ background: var(--surface-2); border: 1px dashed var(--hairline); }}
  .chart {{ display: flex; gap: 8px; overflow-x: auto; }}
  .chart-axis {{ position: relative; width: 40px; height: {chart_h}px; flex: none; }}
  .chart-axis .tick {{ position: absolute; left: 0; right: 0; }}
  .chart-axis .tick span {{ position: absolute; right: 6px; transform: translateY(50%); font-size: 10.5px; color: var(--ink-mute); font-family: "IBM Plex Mono", ui-monospace, monospace; }}
  .chart-plot {{ position: relative; flex: 1; display: flex; gap: 2px; align-items: flex-end; height: {chart_h}px; border-bottom: 1px solid var(--hairline); min-width: 640px; }}
  .chart-plot::before {{ content: ""; position: absolute; left: 0; right: 0; top: 0; bottom: 0; background-image: repeating-linear-gradient(to top, var(--hairline) 0, var(--hairline) 1px, transparent 1px, transparent {round(chart_h / 3.5)}px); opacity: 0.6; pointer-events: none; }}
  .month-col {{ flex: 1; display: flex; flex-direction: column; align-items: center; gap: 8px; min-width: 44px; }}
  .bars {{ display: flex; align-items: flex-end; gap: 2px; height: {chart_h}px; position: relative; }}
  .bar {{ width: 15px; border-radius: 4px 4px 0 0; position: relative; cursor: default; }}
  .bar-pres {{ background: var(--accent-pres); }}
  .bar-real {{ background: var(--accent-real); }}
  .bar-future {{ height: 4px; align-self: flex-end; background: repeating-linear-gradient(135deg, var(--hairline), var(--hairline) 2px, transparent 2px, transparent 5px); border-radius: 2px; }}
  .bar[data-tip]:hover::after {{ content: attr(data-tip); position: absolute; bottom: calc(100% + 8px); left: 50%; transform: translateX(-50%); background: var(--ink); color: var(--page); font-family: "IBM Plex Mono", ui-monospace, monospace; font-size: 11px; padding: 5px 8px; border-radius: 6px; white-space: nowrap; box-shadow: var(--shadow); z-index: 5; }}
  .bar[data-tip]:hover::before {{ content: ""; position: absolute; bottom: calc(100% + 3px); left: 50%; transform: translateX(-50%); border: 5px solid transparent; border-top-color: var(--ink); z-index: 5; }}
  .month-label {{ font-size: 11.5px; color: var(--ink-soft); font-family: "IBM Plex Mono", ui-monospace, monospace; }}
  .table-wrap {{ overflow-x: auto; margin-top: 6px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13.5px; min-width: 620px; }}
  thead th {{ text-align: right; font-size: 11px; font-weight: 600; letter-spacing: 0.03em; text-transform: uppercase; color: var(--ink-mute); padding: 0 10px 8px; border-bottom: 1px solid var(--hairline); white-space: nowrap; }}
  thead th.col-name {{ text-align: left; }}
  tbody td {{ padding: 9px 10px; border-bottom: 1px solid var(--hairline); font-family: "IBM Plex Mono", ui-monospace, monospace; font-variant-numeric: tabular-nums; }}
  tbody td.col-name {{ font-family: "IBM Plex Sans", sans-serif; font-variant-numeric: normal; color: var(--ink); font-weight: 500; }}
  td.num {{ text-align: right; }}
  td.muted {{ color: var(--ink-mute); }}
  tbody tr:last-child td {{ border-bottom: none; }}
  tbody tr:hover td {{ background: var(--surface-2); }}
  footer {{ font-size: 12px; color: var(--ink-mute); line-height: 1.6; padding-top: 8px; }}
  footer p {{ margin: 0 0 6px; }}
  @media print {{ body {{ background: #fff; }} section, .kpi {{ box-shadow: none; break-inside: avoid; }} }}
</style>
<div class="wrap">
  <header>
    <div class="eyebrow">Biotecsa · Presupuesto de Ventas</div>
    <h1>Avance de Ventas {CARGA.get("anio", "")}</h1>
    <div class="meta">
      <span>Carga: <b>{CARGA.get("nombre_archivo", "—")}</b> (#{CARGA.get("id_carga", "—")})</span>
      <span>Generado: <b>{datos["generado"]}</b></span>
      <span>Corte de ventas reales: <b>hasta {datos["mes_actual_label"]} {CARGA.get("anio", "")}</b></span>
      <span class="estado-chip">estatus: {CARGA.get("estatus", "—")}</span>
    </div>
  </header>
  <div class="kpis">
    <div class="kpi">
      <div class="label">Presupuesto del año</div>
      <div class="value mono">{_fmt_usd(KPI["total_presupuesto_usd"])}</div>
      <div class="sub">{_fmt_kg(KPI["total_presupuesto_kg"])} · 12 meses</div>
    </div>
    <div class="kpi">
      <div class="label">Avance a la fecha ({datos["mes_actual_label"]})</div>
      <div class="value mono">{_fmt_usd(KPI["real_transc_usd"])}</div>
      <div class="sub">de {_fmt_usd(KPI["pres_transc_usd"])} presupuestados Ene–{datos["mes_actual_label"]}</div>
    </div>
    <div class="kpi">
      <div class="label">Cumplimiento acumulado</div>
      <div class="value mono">{_fmt_pct(KPI["cumplimiento_pct"])}</div>
      <div class="sub"><span class="pill {cumpl_pill}">{cumpl_label}</span></div>
    </div>
    <div class="kpi">
      <div class="label">Clientes con presupuesto</div>
      <div class="value mono">{KPI["num_clientes"]}</div>
      <div class="sub">{KPI["num_productos"]} productos distintos</div>
    </div>
  </div>
  <section>
    <div class="section-head"><h2>Presupuesto vs. venta real por mes</h2><div class="section-note">USD · Aspel SAE, cruzado por cliente + producto</div></div>
    <div class="legend">
      <div class="legend-item"><span class="swatch swatch-pres"></span>Presupuesto</div>
      <div class="legend-item"><span class="swatch swatch-real"></span>Real (SAE)</div>
      <div class="legend-item"><span class="swatch swatch-future"></span>Mes aún no transcurrido</div>
    </div>
    <div class="chart">
      <div class="chart-axis">{ticks_html}</div>
      <div class="chart-plot">{"".join(meses_html)}</div>
    </div>
  </section>
  <section>
    <div class="section-head"><h2>Por cliente</h2><div class="section-note">{len(CLIENTES)} clientes · ordenado por presupuesto USD</div></div>
    <div class="table-wrap">
      <table>
        <thead><tr><th class="col-name">Cliente</th><th>Presupuesto USD</th><th>Presupuesto kg</th><th>Real USD (a la fecha)</th><th>Real kg</th><th>Cumplimiento</th></tr></thead>
        <tbody>{filas_clientes}</tbody>
      </table>
    </div>
  </section>
  <section>
    <div class="section-head"><h2>Por producto</h2><div class="section-note">{len(PRODUCTOS)} productos · ordenado por presupuesto USD</div></div>
    <div class="table-wrap">
      <table>
        <thead><tr><th class="col-name">Producto</th><th>Presupuesto USD</th><th>Presupuesto kg</th><th>Real USD (a la fecha)</th><th>Real kg</th><th>Cumplimiento</th></tr></thead>
        <tbody>{filas_productos}</tbody>
      </table>
    </div>
  </section>
  <footer>
    <p><b>Metodología:</b> "Real" es venta facturada en Aspel SAE, cruzada por cliente + producto contra las líneas del presupuesto capturado. Solo se compara contra los meses ya transcurridos del año ({", ".join(KPI["meses_transcurridos"])}) — los meses futuros no tienen venta real todavía y compararlos daría un cumplimiento falso.</p>
    <p><b>Cumplimiento:</b> 🟢 en línea (≥90%) · 🟡 atención (60–89%) · 🔴 crítico (&lt;60%) · gris = sin venta real que cruce en el periodo.</p>
    <p>Fuente: presupuesto de ventas (carga #{CARGA.get("id_carga", "—")}) + ventas reales Aspel SAE. No incluye stock ni órdenes de compra pendientes.</p>
  </footer>
</div>
'''


# ── PDF (reportlab) ────────────────────────────────────────────────────────

def _generar_reporte_ventas_pdf(datos: dict) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
    )

    KPI, MESES = datos["kpi"], datos["meses"]
    CLIENTES, PRODUCTOS, CARGA = datos["top_clientes"], datos["top_productos"], datos["carga"]

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        leftMargin=1.8 * cm, rightMargin=1.8 * cm, topMargin=1.6 * cm, bottomMargin=1.6 * cm,
    )
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=20, spaceAfter=2)
    meta = ParagraphStyle("meta", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#4a505c"), spaceAfter=10)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=13, spaceBefore=14, spaceAfter=6)
    nota = ParagraphStyle("nota", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#767c87"), spaceBefore=2)

    AZUL = colors.HexColor("#2a78d6")
    GRIS_HDR = colors.HexColor("#12151a")
    GRIS_LINEA = colors.HexColor("#e3e6ea")

    def pill_color(v):
        if v is None:
            return colors.HexColor("#767c87")
        if v >= 90:
            return colors.HexColor("#0ca30c")
        if v >= 60:
            return colors.HexColor("#b3790a")
        return colors.HexColor("#d03b3b")

    story = [
        Paragraph(f"Avance de Ventas {CARGA.get('anio', '')}", h1),
        Paragraph(
            f"Carga: <b>{CARGA.get('nombre_archivo', '—')}</b> (#{CARGA.get('id_carga', '—')}) &nbsp;·&nbsp; "
            f"Generado: <b>{datos['generado']}</b> &nbsp;·&nbsp; "
            f"Corte de ventas reales: hasta <b>{datos['mes_actual_label']} {CARGA.get('anio', '')}</b>",
            meta,
        ),
    ]

    kpi_data = [
        ["Presupuesto del año", "Avance a la fecha", "Cumplimiento", "Clientes / productos"],
        [
            f"{_fmt_usd(KPI['total_presupuesto_usd'])}",
            f"{_fmt_usd(KPI['real_transc_usd'])} de {_fmt_usd(KPI['pres_transc_usd'])}",
            f"{_fmt_pct(KPI['cumplimiento_pct'])}",
            f"{KPI['num_clientes']} / {KPI['num_productos']}",
        ],
    ]
    t_kpi = Table(kpi_data, colWidths=[4.4 * cm] * 4)
    t_kpi.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GRIS_HDR),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("FONTSIZE", (0, 1), (-1, 1), 11),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("BOX", (0, 0), (-1, -1), 0.5, GRIS_LINEA),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, GRIS_LINEA),
    ]))
    story += [t_kpi, Spacer(1, 4)]

    story.append(Paragraph("Presupuesto vs. real por mes (USD)", h2))
    mes_data = [["Mes", "Presupuesto", "Real", "Estatus"]]
    for m in MESES:
        estatus = "—" if not m["transcurrido"] else ("sin cruce" if m["real_usd"] is None else "")
        mes_data.append([
            m["mes"], _fmt_usd(m["presupuesto_usd"]),
            _fmt_usd(m["real_usd"]) if m["real_usd"] is not None else "—",
            "futuro" if not m["transcurrido"] else estatus,
        ])
    t_mes = Table(mes_data, colWidths=[3 * cm, 4 * cm, 4 * cm, 3 * cm], repeatRows=1)
    t_mes.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GRIS_HDR),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ALIGN", (3, 0), (3, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, GRIS_LINEA),
    ]))
    story += [t_mes, Spacer(1, 4)]

    def tabla_ranking(titulo, filas, nombre_col):
        elementos = [Paragraph(titulo, h2)]
        data = [["", "Presup. USD", "Presup. kg", "Real USD", "Real kg", "Cumpl."]]
        estilos_extra = []
        for i, r in enumerate(filas, start=1):
            data.append([
                Paragraph(str(r[nombre_col]), styles["Normal"]),
                _fmt_usd(r["pres_usd"]), _fmt_kg(r["pres_kg"]),
                _fmt_usd(r["real_usd"]), _fmt_kg(r["real_kg"]),
                _fmt_pct(r["cumpl"]),
            ])
            estilos_extra.append(("TEXTCOLOR", (5, i), (5, i), pill_color(r["cumpl"])))
            estilos_extra.append(("FONTNAME", (5, i), (5, i), "Helvetica-Bold"))
        t = Table(data, colWidths=[5.2 * cm, 2.7 * cm, 2.3 * cm, 2.7 * cm, 2.3 * cm, 1.8 * cm], repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), GRIS_HDR),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LINEBELOW", (0, 0), (-1, -2), 0.4, GRIS_LINEA),
            *estilos_extra,
        ]))
        elementos.append(t)
        return elementos

    story += tabla_ranking(f"Por cliente ({len(CLIENTES)})", CLIENTES, "cliente_nombre")
    story.append(PageBreak())
    story += tabla_ranking(f"Por producto ({len(PRODUCTOS)})", PRODUCTOS, "producto_excel")

    story += [
        Spacer(1, 10),
        Paragraph(
            "Metodología: \"Real\" es venta facturada en Aspel SAE, cruzada por cliente + producto contra el "
            f"presupuesto capturado. Solo se compara contra los meses ya transcurridos "
            f"({', '.join(KPI['meses_transcurridos'])}) — los meses futuros no tienen venta real todavía.",
            nota,
        ),
        Paragraph("Cumplimiento: en línea ≥90% · atención 60–89% · crítico &lt;60%.", nota),
    ]

    doc.build(story)
    return buf.getvalue()


# ── panel: botón para el vendedor ──────────────────────────────────────────

def mostrar_panel_reporte_gerente(id_carga: int, anio: int) -> None:
    """Botón "reporte para gerencia": genera el mismo reporte (KPIs, avance
    mensual, ranking por cliente/producto) y lo deja listo para compartir por
    link, descargar en PDF o enviar por correo al rol "Gerente de Ventas"."""
    usuario = st.session_state.get("usuario") or {}
    usuario_id = int(usuario.get("id") or usuario.get("id_usuario") or 0)
    usuario_nombre = str(usuario.get("nombre") or usuario.get("username") or "").strip()
    usuario_email = str(usuario.get("email") or "").strip()

    with st.expander("📄 Reporte para gerencia", expanded=False):
        st.caption(
            "genera un reporte de avance (presupuesto vs. venta real de Aspel SAE) para "
            "compartir con el Gerente de Ventas — mes con mes"
        )

        datos_key = f"rv_datos_{id_carga}_{anio}"
        if st.button("🔄 generar reporte", key=f"rv_generar_{id_carga}_{anio}"):
            with st.spinner("calculando…"):
                datos = _calcular_datos_reporte(id_carga, anio)
            if datos is None:
                st.warning("sin datos de presupuesto en esta carga todavía")
            else:
                st.session_state[datos_key] = datos

        datos = st.session_state.get(datos_key)
        if not datos:
            return

        st.success(
            f"reporte listo — presupuesto {_fmt_usd(datos['kpi']['total_presupuesto_usd'])}, "
            f"cumplimiento acumulado {_fmt_pct(datos['kpi']['cumplimiento_pct'])}"
        )

        col_link, col_pdf, col_mail = st.columns(3)

        with col_link:
            if st.button("🔗 generar link para compartir", key=f"rv_link_{id_carga}_{anio}"):
                html = _generar_reporte_ventas_html(datos)
                token = guardar_reporte_ventas_ctrl(
                    id_carga=id_carga, anio=anio, mes_generado=date.today().month,
                    usuario_id=usuario_id, usuario_nombre=usuario_nombre, html_contenido=html,
                )
                base_url = str(st.secrets.get("APP_BASE_URL", "") or "").strip().rstrip("/")
                if base_url:
                    st.session_state[f"rv_link_url_{id_carga}_{anio}"] = f"{base_url}/?rv={token}"
                else:
                    st.session_state[f"rv_link_url_{id_carga}_{anio}"] = f"?rv={token}"
                    st.warning("falta APP_BASE_URL en secrets.toml — el link generado es relativo")

            link_url = st.session_state.get(f"rv_link_url_{id_carga}_{anio}")
            if link_url:
                st.text_input("link (sin login)", value=link_url, key=f"rv_link_show_{id_carga}_{anio}")

        with col_pdf:
            pdf_key = f"rv_pdf_{id_carga}_{anio}"
            if st.button("⬇️ preparar PDF", key=f"rv_pdf_btn_{id_carga}_{anio}"):
                with st.spinner("generando PDF…"):
                    st.session_state[pdf_key] = _generar_reporte_ventas_pdf(datos)
            pdf_bytes = st.session_state.get(pdf_key)
            if pdf_bytes:
                st.download_button(
                    "descargar PDF",
                    data=pdf_bytes,
                    file_name=f"avance_ventas_{datos['carga'].get('anio', anio)}_carga{id_carga}.pdf",
                    mime="application/pdf",
                    key=f"rv_pdf_dl_{id_carga}_{anio}",
                )

        with col_mail:
            if st.button("✉️ enviar al Gerente de Ventas", key=f"rv_mail_{id_carga}_{anio}"):
                destinatarios = sorted({
                    str(e).strip() for e in (get_correos_usuarios_por_rol_ctrl("Gerente de Ventas") or [])
                    if str(e or "").strip()
                })
                if not destinatarios:
                    st.error("no hay correos configurados para el rol \"Gerente de Ventas\"")
                else:
                    token = guardar_reporte_ventas_ctrl(
                        id_carga=id_carga, anio=anio, mes_generado=date.today().month,
                        usuario_id=usuario_id, usuario_nombre=usuario_nombre,
                        html_contenido=_generar_reporte_ventas_html(datos),
                    )
                    base_url = str(st.secrets.get("APP_BASE_URL", "") or "").strip().rstrip("/")
                    link_html = f'<p><a href="{base_url}/?rv={token}">Ver reporte completo</a></p>' if base_url else ""
                    K = datos["kpi"]
                    cuerpo_html = f"""
                    <div style="font-family: Arial, sans-serif; font-size: 14px; color: #111;">
                        <p>{usuario_nombre or "Un vendedor"} comparte el avance de ventas de la carga
                        <b>{datos['carga'].get('nombre_archivo', '')}</b> ({datos['carga'].get('anio', anio)}).</p>
                        <ul>
                            <li>Presupuesto del año: <b>{_fmt_usd(K['total_presupuesto_usd'])}</b></li>
                            <li>Avance a la fecha ({datos['mes_actual_label']}): <b>{_fmt_usd(K['real_transc_usd'])}</b>
                                de {_fmt_usd(K['pres_transc_usd'])} presupuestados</li>
                            <li>Cumplimiento acumulado: <b>{_fmt_pct(K['cumplimiento_pct'])}</b></li>
                        </ul>
                        {link_html}
                    </div>
                    """
                    ok_mail, msg_mail = enviar_correo(
                        destinatario=destinatarios,
                        asunto=f"Avance de Ventas {datos['carga'].get('anio', anio)} — {datos['mes_actual_label']}",
                        cuerpo_html=cuerpo_html,
                        token=st.session_state.get("microsoft_token"),
                        remitente=usuario_email,
                    )
                    if ok_mail:
                        st.success(f"correo enviado a {', '.join(destinatarios)}")
                    else:
                        st.error(f"no se pudo enviar: {msg_mail}")


# ── vista pública (deeplink ?rv=<token>, sin login) ────────────────────────

def mostrar_reporte_publico() -> None:
    token = (st.query_params.get("rv") or "").strip()
    if not token:
        st.error("link de reporte inválido")
        return

    reporte = obtener_reporte_ventas_ctrl(token)
    if not reporte:
        st.error("este reporte ya no está disponible")
        return

    components.html(reporte["html_contenido"], height=2400, scrolling=True)
