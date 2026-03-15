# views/modulo_solicitudes/tab_solicitud_gastos_view.py
from __future__ import annotations

import re
from typing import Optional
from datetime import datetime, date, time, timedelta
import pandas as pd
import streamlit as st
import base64
import hmac
import hashlib
import json
from pathlib import Path

from controllers.solicitudes_controller import (
    get_usuarios_activos_ctrl,
    crear_solicitud_ctrl,
    actualizar_cabecera_ctrl,
    listar_solicitudes_ctrl,
    get_solicitud_ctrl,
    get_detalle_ctrl,
    guardar_detalle_ctrl,
    cambiar_estatus_ctrl,
    get_conceptos_gasto_ctrl,
    get_datoscfd_by_uuid_ctrl,
    uuid_ya_usado_ctrl,
    get_formas_pago_usuario_ctrl,
    buscar_clientes_sae_ctrl,
    eliminar_solicitud_ctrl,
)
from controllers.datoscfd_controller import registrar_cfdi_desde_xml
from models.datoscfd_model import guardar_pdf_datoscfd, extraer_uuid_desde_pdf
from utils.envio_correo import enviar_correo
from controllers.sepomex_controller import get_sepomex_ciudades_catalogo_ctrl

def _get_app_link_cfg():
    base_url = (st.secrets.get("APP_BASE_URL", "") or "").strip()
    secret = (st.secrets.get("APP_LINK_SECRET", "") or "").strip()

    if not base_url:
        base_url = (os.getenv("APP_BASE_URL") or "").strip()
    if not secret:
        secret = (os.getenv("APP_LINK_SECRET") or "").strip()

    # normaliza base_url
    base_url = base_url.rstrip("/")

    return base_url, secret

def _get_app_base_url() -> str:
    # ejemplo en secrets.toml: APP_BASE_URL="https://tuapp.com"
    base_url, secret = _get_app_link_cfg()
    if not base_url or not secret:
        st.warning("no se pudo generar link de autorización (falta app_base_url o app_link_secret).")
    return str(st.secrets.get("APP_BASE_URL", "")).strip().rstrip("/")

def _sign_payload(payload: dict, secret: str) -> str:
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).digest()
    token = base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=") + "." + base64.urlsafe_b64encode(sig).decode("utf-8").rstrip("=")
    return token

def _verify_token(token: str, secret: str) -> dict | None:
    try:
        raw_b64, sig_b64 = token.split(".", 1)
        pad = "=" * (-len(raw_b64) % 4)
        raw = base64.urlsafe_b64decode(raw_b64 + pad)

        pad2 = "=" * (-len(sig_b64) % 4)
        sig = base64.urlsafe_b64decode(sig_b64 + pad2)

        expected = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).digest()
        if not hmac.compare_digest(sig, expected):
            return None

        payload = json.loads(raw.decode("utf-8"))
        return payload
    except Exception:
        return None

def _build_action_links(solicitud_id: int, folio: str | None = None) -> dict:
    base = _get_app_base_url()
    if not base:
        return {"ok": False, "error": "no existe APP_BASE_URL en secrets.toml"}

    secret = str(st.secrets.get("APP_LINK_SECRET", "")).strip()
    if not secret:
        return {"ok": False, "error": "no existe APP_LINK_SECRET en secrets.toml"}

    exp = int((datetime.utcnow() + timedelta(hours=72)).timestamp())

    # token incluye id + exp + (opcional) folio
    payload = {"sg_id": int(solicitud_id), "exp": exp, "folio": (folio or "")}
    t = _sign_payload(payload, secret)

    # nota: aquí NO ponemos urls directas a aprobar sin confirmación; solo “action=...”
    approve = f"{base}/?sg_id={int(solicitud_id)}&action=approve&t={t}"
    reject  = f"{base}/?sg_id={int(solicitud_id)}&action=reject&t={t}"
    view    = f"{base}/?sg_id={int(solicitud_id)}&t={t}"

    return {"ok": True, "approve": approve, "reject": reject, "view": view, "token": t}


def _split_clientes_texto(s: str) -> list[str]:
    if not s:
        return []
    parts = re.split(r"[,\n]+", str(s))
    out = []
    for p in parts:
        v = p.strip()
        if v:
            out.append(v)

    uniq = []
    seen = set()
    for x in out:
        k = x.lower()
        if k in seen:
            continue
        seen.add(k)
        uniq.append(x)
    return uniq


def _join_clientes(items: list[str]) -> str:
    items = [str(x).strip() for x in (items or []) if str(x).strip()]
    return ", ".join(items)


UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
_HYPHENS = "\u2010\u2011\u2012\u2013\u2014\u2212"


def _normaliza_texto_uuid(s: str) -> str:
    if not s:
        return ""
    s = str(s).strip()
    for h in _HYPHENS:
        s = s.replace(h, "-")
    s = re.sub(r"\s+", "", s)
    return s


def _uuid_en_texto(texto: str) -> Optional[str]:
    t = _normaliza_texto_uuid(texto)
    m = UUID_RE.search(t)
    return m.group(0).upper() if m else None


def _uuid_en_nombre(nombre: str) -> Optional[str]:
    return _uuid_en_texto(nombre or "")


def _to_time(v):
    if v is None or v == "":
        return None
    if isinstance(v, time):
        return v
    if isinstance(v, datetime):
        return v.time()
    if isinstance(v, timedelta):
        total = int(v.total_seconds())
        hh = (total // 3600) % 24
        mm = (total % 3600) // 60
        ss = total % 60
        return time(hh, mm, ss)
    if isinstance(v, str):
        s = v.strip()
        try:
            parts = s.split(":")
            hh = int(parts[0])
            mm = int(parts[1]) if len(parts) > 1 else 0
            ss = int(parts[2]) if len(parts) > 2 else 0
            return time(hh, mm, ss)
        except Exception:
            return None
    return None


def _get_usuario_actual():
    u = st.session_state.get("usuario")
    if not u:
        return None
    return u


def _hora_default(hh: int, mm: int) -> time:
    return time(hour=hh, minute=mm)


def _norm_uuid(x) -> str:
    return ("" if x is None else str(x)).strip().upper()


def _to_float(x) -> float:
    try:
        if x is None or str(x).strip() == "":
            return 0.0
        return float(x)
    except Exception:
        return 0.0


def _to_int(x) -> int:
    try:
        if x is None or str(x).strip() == "":
            return 0
        return int(float(x))
    except Exception:
        return 0


def _defaults_row():
    return {
        "id": None,
        "fecha_gasto": date.today(),
        "concepto": "",
        "uuid": "",
        "descripcion": "",
        "cantidad": 1,
        "precio_unitario": 0,
        "importe": 0,
        "usuario_forma_pago_id": None,
        "pagado_con": "",
        "proveedor": "",
        "receptor": "",
        "serie": "",
        "folio": "",
        "version": "",
        "moneda_xml": "",
        "tipo_cambio": 0,
        "estado_sat": "",
        "forma_pago": "",
        "metodo_pago": "",
        "tipo_comprobante": "",
        "uso_cfdi": "",
        "subtotal_xml": 0,
        "iva_xml": 0,
        "total_xml": 0,
    }


def _normalize_df(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    d = df.copy()

    for c in cols:
        if c not in d.columns:
            d[c] = None

    if "fecha_gasto" in d.columns:

        def _fix_date(v):
            if v is None or (isinstance(v, float) and pd.isna(v)) or (
                isinstance(v, str) and v.strip() == ""
            ):
                return date.today()
            try:
                dt = pd.to_datetime(v, errors="coerce")
                if pd.isna(dt):
                    return date.today()
                return dt.date()
            except Exception:
                return date.today()

        d["fecha_gasto"] = d["fecha_gasto"].apply(_fix_date)

    if "tipo_cambio" in d.columns:
        d["tipo_cambio"] = pd.to_numeric(d["tipo_cambio"], errors="coerce").fillna(0.0)

    for c in ["concepto", "uuid", "descripcion", "proveedor", "pagado_con"]:
        if c in d.columns:
            d[c] = d[c].apply(
                lambda x: ""
                if x is None or (isinstance(x, float) and pd.isna(x))
                else str(x)
            )

    for c in ["importe", "subtotal_xml", "iva_xml", "total_xml", "precio_unitario"]:
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0.0)

    if "cantidad" in d.columns:
        d["cantidad"] = pd.to_numeric(d["cantidad"], errors="coerce").fillna(0).astype(int)

    if "usuario_forma_pago_id" in d.columns:

        def _fix_id(v):
            if v is None or str(v).strip() in ("", "nan", "none"):
                return None
            try:
                return int(float(v))
            except Exception:
                return None

        d["usuario_forma_pago_id"] = d["usuario_forma_pago_id"].apply(_fix_id)

    return d[cols].copy()


def _tipo_comprobante_a_clave(x: str) -> str:
    s = (x or "").strip().upper()
    if not s:
        return ""
    if s[:1] in ("I", "E", "P", "T", "N"):
        return s[:1]
    mapa = {
        "INGRESO": "I",
        "EGRESO": "E",
        "PAGO": "P",
        "TRASLADO": "T",
        "NOMINA": "N",
        "NÓMINA": "N",
    }
    return mapa.get(s, "")


def _normaliza_sat_campos_en_df(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()

    if "moneda_xml" in d.columns:
        d["moneda_xml"] = d["moneda_xml"].fillna("").astype(str).str.strip().str.upper()
        if "tipo_cambio" in d.columns:
            d.loc[d["moneda_xml"] == "MXN", "tipo_cambio"] = 1

    if "estado_sat" in d.columns:
        d["estado_sat"] = d["estado_sat"].fillna("").astype(str).str.strip()
        d.loc[d["estado_sat"] == "", "estado_sat"] = "Vigente"

    if "metodo_pago" in d.columns:
        d["metodo_pago"] = d["metodo_pago"].fillna("").astype(str).str.strip().str.upper()

    if "tipo_comprobante" in d.columns:
        d["tipo_comprobante"] = d["tipo_comprobante"].fillna("").astype(str).str.strip()
        d["tipo_comprobante"] = d["tipo_comprobante"].apply(_tipo_comprobante_a_clave)

    if "uso_cfdi" in d.columns:
        d["uso_cfdi"] = d["uso_cfdi"].fillna("").astype(str).str.strip().str.upper()

    if "forma_pago" in d.columns:
        d["forma_pago"] = d["forma_pago"].fillna("").astype(str).str.strip()

    return d


def _fmt_money(x) -> str:
    try:
        v = float(x or 0)
    except Exception:
        v = 0.0
    return f"{v:,.2f}"


def _monto_para_correo(r: dict) -> float:
    total_xml = _to_float(r.get("total_xml"))
    if total_xml > 0:
        return total_xml

    cant = _to_float(r.get("cantidad"))
    pu = _to_float(r.get("precio_unitario"))
    return round(cant * pu, 2)


def _get_prepago_map():
    import mysql.connector
    from database.conexion import obtener_conexion

    cn = obtener_conexion()
    out = {}
    try:
        cur = cn.cursor()
        cur.execute("select concepto, prepago from solicitud_concepto_gasto")
        for concepto, prepago in cur.fetchall():
            k = (concepto or "").strip().lower()
            out[k] = bool(prepago)
    finally:
        try:
            cn.close()
        except:
            pass
    return out


PREPAGO_MAP = _get_prepago_map()


def _detalle_gastos_a_html(rows: list[dict], conceptos_prepago: set[str]) -> str:
    if not rows:
        return "<p>sin detalle de gastos.</p>"

    def esc(s):
        s = "" if s is None else str(s)
        return (
            s.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;")
        )

    def _fecha_iso(v):
        if not v:
            return ""
        try:
            dt = pd.to_datetime(v, errors="coerce")
            return "" if pd.isna(dt) else dt.date().isoformat()
        except Exception:
            return str(v)

    cols = [
        ("fecha_gasto", "fecha"),
        ("concepto", "concepto"),
        ("uuid", "uuid"),
        ("descripcion", "observaciones"),
        ("cantidad", "cantidad"),
        ("precio_unitario", "gasto estimado"),
        ("_monto", "importe"),
        ("pagado_con", "pagado con"),
        ("proveedor", "proveedor"),
    ]

    def _render_tabla(titulo: str, filas: list[dict]) -> str:
        if not filas:
            return f"<p><b>{esc(titulo)}</b>: sin registros.</p>"

        th = "".join(
            [
                f"<th style='border:1px solid #ddd;padding:6px;text-align:left;background:#f7f7f7'>{esc(t)}</th>"
                for _, t in cols
            ]
        )

        subtotal = 0.0
        trs = []

        for r in filas:
            monto = _monto_para_correo(r)
            subtotal += monto

            tds = []
            for k, _t in cols:
                if k == "_monto":
                    v = _fmt_money(monto)
                    tds.append(
                        f"<td style='border:1px solid #ddd;padding:6px;text-align:right'>{esc(v)}</td>"
                    )
                    continue

                v = r.get(k, "")

                if k == "fecha_gasto":
                    v = _fecha_iso(v)

                if k in ("precio_unitario",):
                    v = _fmt_money(_to_float(v))
                    tds.append(
                        f"<td style='border:1px solid #ddd;padding:6px;text-align:right'>{esc(v)}</td>"
                    )
                    continue

                if k in ("cantidad",):
                    v = str(_to_int(v))
                    tds.append(
                        f"<td style='border:1px solid #ddd;padding:6px;text-align:right'>{esc(v)}</td>"
                    )
                    continue

                tds.append(f"<td style='border:1px solid #ddd;padding:6px'>{esc(v)}</td>")

            trs.append("<tr>" + "".join(tds) + "</tr>")

        colspan = len(cols) - 1
        trs.append(
            "<tr>"
            f"<td colspan='{colspan}' style='border:1px solid #ddd;padding:6px;text-align:right;background:#fafafa'><b>subtotal</b></td>"
            f"<td style='border:1px solid #ddd;padding:6px;text-align:right;background:#fafafa'><b>{esc(_fmt_money(subtotal))}</b></td>"
            "</tr>"
        )

        return (
            f"<p><b>{esc(titulo)}</b></p>"
            "<table style='border-collapse:collapse;width:100%'>"
            "<thead><tr>"
            + th
            + "</tr></thead>"
            "<tbody>"
            + "".join(trs)
            + "</tbody>"
            "</table>"
        )

    prepagados = []
    por_comprobar = []

    for r in rows:
        concepto = (r.get("concepto") or "").strip()
        if concepto and concepto in conceptos_prepago:
            prepagados.append(r)
        else:
            por_comprobar.append(r)

    html_pre = _render_tabla("detalle de gastos prepagados", prepagados)
    html_no = _render_tabla("detalle de gastos por comprobar", por_comprobar)

    total_general = sum(_monto_para_correo(r) for r in rows)
    html_total = (
        "<p style='margin-top:10px'>"
        f"<b>total general:</b> {_fmt_money(total_general)}"
        "</p>"
    )

    return html_pre + "<br>" + html_no + html_total


def mostrar_tab_solicitudes_gastos():
    st.subheader("Solicitudes de gastos")

    usuario = _get_usuario_actual()
    if not usuario:
        st.warning("no hay sesión de usuario en st.session_state['usuario']")
        return

    ###Manejador para el envio de correo electronico con el link #
    # -------------------------------------------------
    # deep-link desde correo: ?sg_id=...&action=...&t=...
    # -------------------------------------------------
    qp = st.query_params
    qp_sg_id = qp.get("sg_id", None)
    qp_action = (qp.get("action", "") or "").strip().lower()
    qp_token = (qp.get("t", "") or "").strip()

    if qp_sg_id:
        try:
            sg_id = int(qp_sg_id)
        except Exception:
            sg_id = None

        if sg_id and qp_token:
            secret = str(st.secrets.get("APP_LINK_SECRET", "")).strip()
            payload = _verify_token(qp_token, secret) if secret else None

            ok_token = False
            if payload:
                exp = int(payload.get("exp") or 0)
                if exp > 0 and int(datetime.utcnow().timestamp()) <= exp:
                    if int(payload.get("sg_id") or 0) == int(sg_id):
                        ok_token = True

            if ok_token:
                # selecciona la solicitud automáticamente
                st.session_state["sg_selected_id"] = int(sg_id)
                # guarda la acción pedida (para mostrar panel confirmación)
                if qp_action in ("approve", "reject"):
                    st.session_state["sg_pending_action"] = qp_action
            else:
                st.warning("link inválido o expirado (token).")
    
    st.session_state.setdefault("sg_pending_action", "")
    ###### Finaliza la generacion del token 

    st.session_state.setdefault("sg_selected_id", None)
    selected_id = st.session_state.get("sg_selected_id") or None

    modo_widget = st.radio(
        "modo",
        options=["crear", "editar"],
        horizontal=True,
        key="sg_modo_widget",
    )
    modo = "editar" if selected_id else modo_widget

    solicitud = None
    if modo == "editar" and selected_id:
        solicitud = get_solicitud_ctrl(int(selected_id))
        if solicitud and usuario.get("rol") != "Admin":
            if int(solicitud.get("empleado_id") or 0) != int(usuario["id"]):
                st.session_state["sg_selected_id"] = None
                st.warning("no tienes acceso a esa solicitud")
                st.rerun()

    # ---------------------------------------------
    # precarga catálogos necesarios para defaults
    # ---------------------------------------------
    sep_rows = get_sepomex_ciudades_catalogo_ctrl(limit=20000) or []
    sep_opts = [
        (r["d_codigo"], r["d_asenta"], r["d_estado"], r["d_ciudad"])
        for r in sep_rows
        if r.get("d_codigo") is not None
    ]

    def _to_store(opt):
        d_codigo, d_asenta, d_estado, d_ciudad = opt
        return f"{d_codigo} | {d_asenta} | {d_estado} | {d_ciudad}"

    def _fmt_sep(opt):
        d_codigo, d_asenta, d_estado, d_ciudad = opt
        return f"{d_codigo} | {d_asenta} | {d_estado} | {d_ciudad}"

    # -------------------------------------------------
    # cargar cabecera en session_state al cambiar solicitud
    # -------------------------------------------------
    if "sg_head_loaded_id" not in st.session_state:
        st.session_state["sg_head_loaded_id"] = None

    if solicitud and st.session_state["sg_head_loaded_id"] != int(selected_id):
        st.session_state["sg_empleado_id"] = int(solicitud.get("empleado_id") or usuario["id"])
        st.session_state["sg_clientes_texto"] = str(solicitud.get("clientes") or "")
        st.session_state["sg_objetivo"] = str(solicitud.get("objetivo") or "")

        fi = solicitud.get("fecha_inicio")
        ff = solicitud.get("fecha_fin")
        try:
            st.session_state["sg_fecha_ini"] = pd.to_datetime(fi, errors="coerce").date() if fi else date.today()
        except Exception:
            st.session_state["sg_fecha_ini"] = date.today()
        try:
            st.session_state["sg_fecha_fin"] = pd.to_datetime(ff, errors="coerce").date() if ff else st.session_state["sg_fecha_ini"]
        except Exception:
            st.session_state["sg_fecha_fin"] = st.session_state["sg_fecha_ini"]

        st.session_state["sg_hora_salida"] = _to_time(solicitud.get("hora_salida")) or _hora_default(5, 0)
        st.session_state["sg_hora_regreso"] = _to_time(solicitud.get("hora_regreso")) or _hora_default(19, 0)

        # clientes catálogo (solo ayuda)
        st.session_state["sg_clientes_sel"] = []

        # ciudades: precargar desde texto guardado en bd a lista de tuplas
        ciudades_prev = (solicitud.get("ciudades") or "")
        prev_list = [x.strip() for x in ciudades_prev.replace("\n", ",").split(",") if x.strip()]
        prev_set = set([x.upper() for x in prev_list])
        default_ciudades = [opt for opt in sep_opts if _to_store(opt).upper() in prev_set]
        st.session_state["sg_ciudades_sel"] = default_ciudades

        st.session_state["sg_head_loaded_id"] = int(selected_id)

    usuarios = get_usuarios_activos_ctrl() or []
    usuarios_map = {u["id"]: u for u in usuarios}

    st.caption("cabecera")

    if modo == "editar" and solicitud:
        st.text_input("folio", value=solicitud["folio"], disabled=True)
        st.text_input("estatus", value=solicitud["estatus"], disabled=True)
    else:
        st.text_input("folio", value="(se genera al guardar)", disabled=True)

    empleado_default = solicitud["empleado_id"] if solicitud else (usuario["id"] if usuario else None)
    ids_usuarios = [u["id"] for u in usuarios] if usuarios else []
    idx_default = ids_usuarios.index(empleado_default) if empleado_default in ids_usuarios else 0

    roles = [str(x).strip().lower() for x in (usuario.get("roles", []) or [])]
    estatus_actual = (solicitud["estatus"] if solicitud else "captura") if modo == "editar" else "captura"

    puede_editar_cabecera = estatus_actual in ("captura", "rechazada")
    puede_editar_detalle = estatus_actual in ("captura", "rechazada", "autorizada ventas")
    puede_prepagos_estimados = estatus_actual == "captura"

    empleado_id = st.selectbox(
        "empleado",
        options=ids_usuarios,
        format_func=lambda _id: f"{usuarios_map[_id]['nombre']} ({usuarios_map[_id]['rol']})",
        index=idx_default,
        disabled=not puede_editar_cabecera,
        key="sg_empleado_id",
    )
    empleado_nombre = usuarios_map[empleado_id]["nombre"]

    c3, c4, c5 = st.columns([3, 1, 1])

    with c3:
        # --- clientes: catálogo sae + libre ---
        q_cli = ""
        sae_rows = buscar_clientes_sae_ctrl(q=q_cli, limit=50) if (q_cli or "").strip() else buscar_clientes_sae_ctrl(q="", limit=50)

        sae_opts = []
        for r in (sae_rows or []):
            clave = (r.get("clave") or "").strip()
            nombre = (r.get("nombre") or "").strip()
            if clave and nombre:
                sae_opts.append(f"{clave} - {nombre}")
            elif clave:
                sae_opts.append(clave)
            elif nombre:
                sae_opts.append(nombre)

        st.multiselect(
            "clientes (selecciona del catálogo si aplica)",
            options=sae_opts,
            key="sg_clientes_sel",
            disabled=not puede_editar_cabecera,
        )

        # ciudades multiselect (tuplas estables)
        st.multiselect(
            "ciudades se muestran por (cp - asentamiento - estado - ciudad)",
            options=sep_opts,
            format_func=_fmt_sep,
            key="sg_ciudades_sel",
            disabled=not puede_editar_cabecera,
        )

        ciudades_sel = st.session_state.get("sg_ciudades_sel") or []
        ciudades = ", ".join([_to_store(opt) for opt in ciudades_sel])

        # texto libre clientes
        st.text_area(
            "clientes (texto libre, separados por coma o enter)",
            height=90,
            key="sg_clientes_texto",
            disabled=not puede_editar_cabecera,
        )

        # merge catálogo (solo ayuda) + libres
        seleccion_norm = [str(x).strip() for x in (st.session_state.get("sg_clientes_sel") or []) if str(x).strip()]
        libres = _split_clientes_texto(st.session_state.get("sg_clientes_texto", "") or "")

        merged = []
        seen = set()
        for x in seleccion_norm + libres:
            k = x.lower()
            if k in seen:
                continue
            seen.add(k)
            merged.append(x)

        clientes = _join_clientes(merged)

        st.text_area(
            "objetivo",
            height=120,
            key="sg_objetivo",
            disabled=not puede_editar_cabecera,
        )
        objetivo = st.session_state.get("sg_objetivo", "") or ""

    with c4:
        # -----------------------------
        # clamp de fechas en session_state
        # -----------------------------
        st.session_state.setdefault("sg_fecha_ini", date.today())
        st.session_state.setdefault("sg_fecha_fin", date.today())

        if puede_editar_cabecera:
            hoy = date.today()

            fi = st.session_state.get("sg_fecha_ini") or hoy
            if fi < hoy:
                fi = hoy
                st.session_state["sg_fecha_ini"] = fi

            ff = st.session_state.get("sg_fecha_fin") or fi
            if ff < fi:
                ff = fi
                st.session_state["sg_fecha_fin"] = ff

            fecha_inicio = st.date_input(
                "fecha inicio",
                key="sg_fecha_ini",
                min_value=hoy,
                disabled=not puede_editar_cabecera,
            )

            # después de elegir fecha_inicio, vuelve a asegurar fin >= inicio
            if (st.session_state.get("sg_fecha_fin") or fecha_inicio) < fecha_inicio:
                st.session_state["sg_fecha_fin"] = fecha_inicio

            fecha_fin = st.date_input(
                "fecha fin",
                key="sg_fecha_fin",
                min_value=fecha_inicio,
                disabled=not puede_editar_cabecera,
            )
        else:
            # modo consulta: sin min_value
            fecha_inicio = st.date_input(
                "fecha inicio",
                key="sg_fecha_ini",
                disabled=True,
            )
            fecha_fin = st.date_input(
                "fecha fin",
                key="sg_fecha_fin",
                disabled=True,
            )

    with c5:
        st.session_state.setdefault("sg_hora_salida", _hora_default(5, 0))
        st.session_state.setdefault("sg_hora_regreso", _hora_default(19, 0))

        hora_salida = st.time_input(
            "hora salida",
            key="sg_hora_salida",
            disabled=not puede_editar_cabecera,
        )
        hora_regreso = st.time_input(
            "hora regreso",
            key="sg_hora_regreso",
            disabled=not puede_editar_cabecera,
        )

        # validación contra fecha creación solo si se puede editar
        if puede_editar_cabecera and solicitud and solicitud.get("fecha_creacion"):
            fecha_creacion = solicitud["fecha_creacion"]
            if isinstance(fecha_creacion, str):
                fecha_creacion = datetime.fromisoformat(fecha_creacion)

            inicio_datetime = datetime.combine(st.session_state["sg_fecha_ini"], st.session_state["sg_hora_salida"])
            if inicio_datetime <= fecha_creacion:
                st.error("la fecha y hora de inicio deben ser posteriores a la fecha de creación de la solicitud.")
                st.stop()

    if fecha_inicio > fecha_fin:
        st.error("fecha inicio no puede ser mayor a fecha fin")
        return

    st.session_state.setdefault("sg_delete_armed", False)
    st.session_state.setdefault("sg_delete_target_id", None)

    cbtn1, cbtn2, cbtn3, cbtn4, cbtn5 = st.columns([2, 2, 2, 2, 2])

    if modo == "crear":
        if cbtn1.button(
            "guardar cabecera",
            use_container_width=True,
            disabled=not puede_editar_cabecera,
            key="sg_btn_save_head_create",
        ):
            solicitud_id, folio = crear_solicitud_ctrl(
                empleado_id=int(empleado_id),
                empleado_nombre=empleado_nombre,
                clientes=clientes.strip() or None,
                ciudades=ciudades.strip() or None,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                hora_salida=hora_salida,
                hora_regreso=hora_regreso,
                objetivo=objetivo.strip() or None,
                usuario_id=int(usuario["id"]),
            )

            cat = get_conceptos_gasto_ctrl(activo=1) or []

            def _ord_key(r: dict) -> int:
                v = r.get("orden", None)
                if v is None:
                    v = r.get("id", 0)
                try:
                    return int(float(v))
                except Exception:
                    return 0

            cat_sorted = sorted(cat, key=_ord_key)

            rows_auto = []
            for r in cat_sorted:
                concepto = (r.get("concepto") or "").strip()
                if not concepto:
                    continue
                row = _defaults_row()
                row["fecha_gasto"] = fecha_inicio
                row["concepto"] = concepto
                row["cantidad"] = 1
                row["precio_unitario"] = 0
                row["importe"] = 0
                row["usuario_forma_pago_id"] = None
                rows_auto.append(row)

            if rows_auto:
                for r in rows_auto:
                    r.pop("pagado_con", None)

                res_det = guardar_detalle_ctrl(
                    solicitud_id=int(solicitud_id),
                    rows=rows_auto,
                    deleted_ids=[],
                    usuario_id=int(usuario["id"]),
                )
                if not res_det.get("ok"):
                    st.warning(f"cabecera creada, pero no se pudo crear detalle automático: {res_det.get('msg','')}")

            st.success(f"solicitud creada: {folio} (id {solicitud_id})")
            st.session_state["sg_selected_id"] = int(solicitud_id)
            st.session_state["sg_head_loaded_id"] = None

            st.session_state.pop("sg_det_df", None)
            st.session_state.pop("sg_det_df_solicitud_id", None)
            st.session_state["sg_uuid_prev"] = {}
            st.session_state["sg_uuid_cache"] = {}
            st.session_state.pop("sg_det_editor", None)

            st.rerun()
    else:
        if selected_id:
            if cbtn1.button(
                "guardar cambios cabecera",
                use_container_width=True,
                disabled=not puede_editar_cabecera,
                key="sg_btn_save_head_edit",
            ):
                actualizar_cabecera_ctrl(
                    solicitud_id=int(selected_id),
                    empleado_id=int(empleado_id),
                    empleado_nombre=empleado_nombre,
                    clientes=clientes.strip() or None,
                    ciudades=ciudades.strip() or None,
                    fecha_inicio=fecha_inicio,
                    fecha_fin=fecha_fin,
                    hora_salida=hora_salida,
                    hora_regreso=hora_regreso,
                    objetivo=objetivo.strip() or None,
                    usuario_id=int(usuario["id"]),
                )
                st.success("cabecera actualizada")
                st.rerun()

            estatus_actual = solicitud["estatus"] if solicitud else ""

            if cbtn2.button(
                "enviar",
                use_container_width=True,
                disabled=(estatus_actual not in ("captura", "rechazada")),
                key="sg_btn_send",
            ):
                cambiar_estatus_ctrl(int(selected_id), "enviada", int(usuario["id"]))

                folio = str((solicitud or {}).get("folio") or "").strip()
                asunto = f"solicitud de gastos enviada {folio}".strip() if folio else "solicitud de gastos enviada"

                detalle_rows_mail = get_detalle_ctrl(int(selected_id)) or []
                cat_conceptos_mail = get_conceptos_gasto_ctrl(activo=1) or []
                #### Incliusion del token 
                links = _build_action_links(int(selected_id), folio=folio)
                links_html = ""
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
                      <a href="{links['view']}"
                         style="display:inline-block;margin-left:10px;padding:10px 14px;background:#2563eb;color:#fff;text-decoration:none;border-radius:6px;font-weight:700">
                        ver solicitud
                      </a>
                    </p>
                    """
                else:
                    # si no hay secrets configurados, al menos manda texto
                    links_html = "<p><i>no se pudo generar link de autorización (falta APP_BASE_URL o APP_LINK_SECRET).</i></p>"
                ####
                conceptos_prepago = set()
                for x in cat_conceptos_mail:
                    c = (x.get("concepto") or "").strip()
                    if not c:
                        continue
                    if int(x.get("prepago") or 0) == 1:
                        conceptos_prepago.add(c)

                cuerpo_html = f"""
                <div style="font-family:arial,sans-serif;font-size:14px;line-height:1.4">
                <p>se envió una solicitud de gastos.</p>
                {links_html}
                <p>
                    <b>empleado:</b> {empleado_nombre}<br>
                    <b>clientes:</b> {clientes}<br>
                    <b>ciudades:</b> {ciudades}<br>
                    <b>fecha inicio:</b> {fecha_inicio.isoformat()}<br>
                    <b>fecha fin:</b> {fecha_fin.isoformat()}<br>
                    <b>hora salida:</b> {hora_salida.strftime("%H:%M")}<br>
                    <b>hora regreso:</b> {hora_regreso.strftime("%H:%M")}<br>
                    <b>folio:</b> {folio}
                </p>

                <p><b>detalle de gastos</b></p>
                {_detalle_gastos_a_html(detalle_rows_mail, conceptos_prepago)}
                </div>
                """

                token = st.session_state.get("microsoft_token")
                ok_mail, msg_mail = enviar_correo(
                    destinatario="ofarias@ftcenlinea.com",
                    asunto=asunto,
                    cuerpo_html=cuerpo_html,
                    token=token,
                )

                if ok_mail:
                    st.success("estatus actualizado: enviada y correo enviado")
                else:
                    st.warning(f"estatus actualizado: enviada, pero no se pudo enviar correo. {msg_mail}")

                st.rerun()

            if cbtn3.button(
                "autorizar",
                use_container_width=True,
                disabled=(usuario.get("rol") != "Admin" or estatus_actual != "enviada"),
                key="sg_btn_approve",
            ):
                cambiar_estatus_ctrl(int(selected_id), "autorizada", int(usuario["id"]))
                st.success("estatus actualizado: autorizada")
                st.rerun()

            if cbtn4.button(
                "rechazar",
                use_container_width=True,
                disabled=(usuario.get("rol") != "Admin" or estatus_actual != "enviada"),
                key="sg_btn_reject",
            ):
                cambiar_estatus_ctrl(int(selected_id), "rechazada", int(usuario["id"]))
                st.success("estatus actualizado: rechazada")
                st.rerun()

            puede_eliminar = bool(selected_id) and (str(estatus_actual).strip().lower() == "captura")

            cbtn5.checkbox(
                "confirmo eliminar",
                key="sg_confirm_delete",
                disabled=not puede_eliminar,
            )

            with cbtn5:
                disabled_delete = (not selected_id or estatus_actual != "captura")

                if not st.session_state.get("sg_delete_armed"):
                    if st.button(
                        "eliminar solicitud",
                        use_container_width=True,
                        disabled=disabled_delete,
                        key="sg_btn_delete_arm",
                    ):
                        st.session_state["sg_delete_armed"] = True
                        st.session_state["sg_delete_target_id"] = int(selected_id)
                        st.rerun()
                else:
                    if st.session_state.get("sg_delete_target_id") != int(selected_id):
                        st.session_state["sg_delete_armed"] = False
                        st.session_state["sg_delete_target_id"] = None
                        st.rerun()

                    st.warning("confirmar eliminación: esta acción no se puede deshacer.")

                    cdel1, cdel2 = st.columns(2)
                    with cdel1:
                        if st.button("confirmar", use_container_width=True, key="sg_btn_delete_confirm"):
                            eliminar_solicitud_ctrl(int(selected_id), int(usuario["id"]))
                            st.success("solicitud eliminada")

                            st.session_state["sg_selected_id"] = None
                            st.session_state["sg_head_loaded_id"] = None
                            st.session_state["sg_delete_armed"] = False
                            st.session_state["sg_delete_target_id"] = None

                            st.session_state.pop("sg_det_df", None)
                            st.session_state.pop("sg_det_df_solicitud_id", None)

                            st.rerun()

                    with cdel2:
                        if st.button("cancelar", use_container_width=True, key="sg_btn_delete_cancel"):
                            st.session_state["sg_delete_armed"] = False
                            st.session_state["sg_delete_target_id"] = None
                            st.rerun()
        else:
            st.info("para editar, selecciona una solicitud abajo.")

    # ---------------------------------------------------------------------
    # desde aquí tu archivo sigue igual (buscar/resultados, importar xml/pdf, detalle, etc.)
    # ---------------------------------------------------------------------

    st.divider()
    st.caption("buscar / resultados")

    b1, b2 = st.columns([2, 3])

    with b1:
        folio_like = st.text_input("folio contiene", key="sg_folio_like")
        estatus = st.selectbox(
            "estatus",
            options=["", "captura", "enviada", "autorizada", "rechazada", "cancelada", "cerrada"],
            index=0,
            key="sg_estatus",
        )
        anio = st.number_input(
            "año",
            min_value=2020,
            max_value=2100,
            value=datetime.now().year,
            step=1,
            key="sg_anio",
        )

    with b2:
        empleado_id_filtro = None if usuario.get("rol") == "Admin" else int(usuario["id"])

        rows = listar_solicitudes_ctrl(
            folio_like=folio_like,
            estatus=estatus,
            anio=int(anio) if anio else None,
            empleado_id=empleado_id_filtro,
            limit=200,
        )

        df = pd.DataFrame(rows)

        def _estatus_badge(e):
            e = (e or "").strip().lower()
            if e == "captura":
                return "🟡 captura"
            if e == "enviada":
                return "🔵 enviada"
            if e == "autorizada":
                return "🟢 autorizada"
            if e == "rechazada":
                return "🔴 rechazada"
            if e == "eliminada":
                return "⚫ eliminada"
            if e == "cerrada":
                return "🟣 cerrada"
            return e

        if not df.empty and "estatus" in df.columns:
            df.insert(0, "estatus_visual", df["estatus"].apply(_estatus_badge))

        if df.empty:
            st.info("sin resultados")
        else:
            st.dataframe(df, use_container_width=True, hide_index=True)

        selected_id_widget = st.number_input(
            "id solicitud seleccionada",
            min_value=0,
            value=int(st.session_state.get("sg_selected_id") or 0),
            step=1,
            key="sg_selected_id_widget",
        )

        if selected_id_widget and int(selected_id_widget) != int(st.session_state.get("sg_selected_id") or 0):
            nuevo_id = int(selected_id_widget)

            if usuario.get("rol") == "Admin":
                st.session_state["sg_selected_id"] = nuevo_id
                st.rerun()
            else:
                s = get_solicitud_ctrl(nuevo_id)
                if s and int(s.get("empleado_id") or 0) == int(usuario["id"]):
                    st.session_state["sg_selected_id"] = nuevo_id
                    st.rerun()
                else:
                    st.warning("esa solicitud no es tuya o no existe")

    st.divider()

    selected_id = st.session_state.get("sg_selected_id") or None
    if not selected_id:
        st.info("selecciona una solicitud para capturar detalle.")
        return

    # ---------------------------------------------------------------------
    # importar xml/pdf a datoscfd (global)
    # ---------------------------------------------------------------------
    st.subheader("importar xml/pdf a mysql (datoscfd)")

    up_files = st.file_uploader(
        "selecciona uno o varios archivos (xml o pdf)",
        type=["xml", "pdf"],
        accept_multiple_files=True,
        key="sg_uploader_archivos",
    )

    user = st.session_state.get("usuario", {}) or {}
    username = user.get("username") or st.session_state.get("username") or "admin"

    cimp1, cimp2 = st.columns([1.2, 3.0])
    cimp1.text_input("usuario", username, disabled=True, key="sg_show_user_import")

    btn_importar = cimp2.button(
        "importar archivo(s)",
        use_container_width=True,
        key="sg_btn_importar_archivos",
        disabled=(not up_files),
    )

    if btn_importar and up_files:
        xml_inserted = xml_duplicated = xml_updated = 0
        pdf_guardados = 0
        errores = []

        xml_files = [f for f in up_files if (f.name or "").lower().endswith(".xml")]
        pdf_files = [f for f in up_files if (f.name or "").lower().endswith(".pdf")]

        uuid_par = None

        if len(xml_files) == 1 and len(pdf_files) == 1:
            try:
                rxml = registrar_cfdi_desde_xml(xml_bytes=xml_files[0].getvalue(), username=username)
                if rxml.get("ok"):
                    stt = rxml.get("status")
                    if stt == "inserted":
                        xml_inserted += 1
                    elif stt == "updated":
                        xml_updated += 1
                    else:
                        xml_duplicated += 1
                    uuid_par = (rxml.get("uuid") or "").strip().upper() or None
                else:
                    errores.append(f"{xml_files[0].name}: {rxml.get('error') or 'error xml'}")
            except Exception as e:
                errores.append(f"{xml_files[0].name}: {e}")

            try:
                rpdf = guardar_pdf_datoscfd(
                    pdf_bytes=pdf_files[0].getvalue(),
                    nombre_archivo=pdf_files[0].name,
                    usuario=username,
                    uuid=uuid_par,
                    id_doctodig=None,
                    metodo_uuid="par_xml_pdf" if uuid_par else "par_xml_pdf_sin_uuid",
                    status="cargado",
                )
                if rpdf.get("ok"):
                    pdf_guardados += 1
                else:
                    errores.append(f"{pdf_files[0].name}: {rpdf.get('error') or 'error pdf'}")
            except Exception as e:
                errores.append(f"{pdf_files[0].name}: {e}")

            xml_files = []
            pdf_files = []

        for f in xml_files:
            try:
                rxml = registrar_cfdi_desde_xml(xml_bytes=f.getvalue(), username=username)
                if rxml.get("ok"):
                    stt = rxml.get("status")
                    if stt == "inserted":
                        xml_inserted += 1
                    elif stt == "updated":
                        xml_updated += 1
                    else:
                        xml_duplicated += 1
                else:
                    errores.append(f"{f.name}: {rxml.get('error') or 'error xml'}")
            except Exception as e:
                errores.append(f"{f.name}: {e}")

        for f in pdf_files:
            try:
                b = f.getvalue()

                uuid_pdf_raw = extraer_uuid_desde_pdf(b)
                uuid_pdf = _uuid_en_texto(uuid_pdf_raw or "")
                metodo = "pdf_texto" if uuid_pdf else None

                if not uuid_pdf:
                    uuid_pdf = _uuid_en_nombre(f.name)
                    if uuid_pdf:
                        metodo = "nombre_archivo"

                if not uuid_pdf:
                    metodo = "sin_uuid"

                rpdf = guardar_pdf_datoscfd(
                    pdf_bytes=b,
                    nombre_archivo=f.name,
                    usuario=username,
                    uuid=uuid_pdf,
                    id_doctodig=None,
                    metodo_uuid=metodo,
                    status="cargado",
                )

                if rpdf.get("ok"):
                    pdf_guardados += 1
                else:
                    errores.append(f"{f.name}: {rpdf.get('error') or 'error pdf'}")

            except Exception as e:
                errores.append(f"{f.name}: {e}")

        msg = (
            f"xml insertados: {xml_inserted} | xml duplicados: {xml_duplicated} | "
            f"xml actualizados: {xml_updated} | pdf guardados: {pdf_guardados}"
        )

        if errores:
            st.warning(msg + f" | errores: {len(errores)}")
            st.text("\n".join(errores))
        else:
            st.success(msg)

    st.divider()

    # ---------------------------------------------------------------------
    # detalle (tu bloque original sigue aquí)
    # ---------------------------------------------------------------------
    st.caption("detalle de gastos")

    detalle_rows = get_detalle_ctrl(int(selected_id))
    df_det = pd.DataFrame(detalle_rows)

    cols = [
        "id",
        "fecha_gasto",
        "concepto",
        "uuid",
        "descripcion",
        "cantidad",
        "precio_unitario",
        "importe",
        "usuario_forma_pago_id",
        "pagado_con",
        "proveedor",
        "receptor",
        "serie",
        "folio",
        "version",
        "moneda_xml",
        "tipo_cambio",
        "estado_sat",
        "forma_pago",
        "metodo_pago",
        "tipo_comprobante",
        "uso_cfdi",
        "subtotal_xml",
        "iva_xml",
        "total_xml",
    ]

    if df_det.empty:
        df_det = pd.DataFrame([_defaults_row()])

    df_edit = _normalize_df(df_det, cols)
    df_edit = _normaliza_sat_campos_en_df(df_edit)

    if st.session_state.get("sg_det_df_solicitud_id") != int(selected_id):
        st.session_state["sg_det_df"] = df_edit.copy()
        st.session_state["sg_det_df_solicitud_id"] = int(selected_id)
        st.session_state["sg_uuid_prev"] = {}
        st.session_state["sg_uuid_cache"] = {}

    st.session_state.setdefault("sg_det_df", df_edit.copy())

    cat_conceptos = get_conceptos_gasto_ctrl(activo=1)
    conceptos_opts = [
        str(r.get("concepto", "")).strip()
        for r in (cat_conceptos or [])
        if str(r.get("concepto", "")).strip()
    ]
    valores_actuales = sorted(
        {
            str(x).strip()
            for x in st.session_state["sg_det_df"]["concepto"].dropna().tolist()
            if str(x).strip() != ""
        }
    )
    extras = [v for v in valores_actuales if v not in set(conceptos_opts)]
    conceptos_opts_final = conceptos_opts + extras

    formas = get_formas_pago_usuario_ctrl(int(empleado_id))
    id_to_label = {
        int(x["id"]): str(x.get("etiqueta") or "").strip()
        for x in (formas or [])
        if x.get("id") is not None
    }
    label_to_id = {v: k for k, v in id_to_label.items()}

    formas_opts = list(label_to_id.keys())
    if not formas_opts:
        formas_opts = ["(sin formas de pago activas)"]

    def _id_to_lbl(v):
        if v is None or str(v).strip() in ("", "nan", "none"):
            return ""
        try:
            return id_to_label.get(int(v), "")
        except Exception:
            return ""

    def _lbl_to_id(lbl: str):
        s = (lbl or "").strip()
        if not s or s == "(sin formas de pago activas)":
            return None
        return int(label_to_id.get(s)) if s in label_to_id else None

    df_base = st.session_state["sg_det_df"].copy()
    if "usuario_forma_pago_id" not in df_base.columns:
        df_base["usuario_forma_pago_id"] = None
    df_base["pagado_con"] = df_base["usuario_forma_pago_id"].apply(_id_to_lbl)
    st.session_state["sg_det_df"] = df_base

    if st.button("agregar renglón", use_container_width=False, key="sg_add_row"):
        df_tmp = st.session_state["sg_det_df"].copy()
        df_tmp = pd.concat([df_tmp, pd.DataFrame([_defaults_row()])], ignore_index=True)
        df_tmp = _normalize_df(df_tmp, cols)
        df_tmp = _normaliza_sat_campos_en_df(df_tmp)
        df_tmp["pagado_con"] = df_tmp["usuario_forma_pago_id"].apply(_id_to_lbl)
        st.session_state["sg_det_df"] = df_tmp
        st.session_state["sg_uuid_prev"] = {}
        st.rerun()

    edited = st.data_editor(
        st.session_state["sg_det_df"],
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        key="sg_det_editor",
        column_config={
            "id": st.column_config.TextColumn("id", disabled=True),
            "concepto": st.column_config.SelectboxColumn("concepto", options=conceptos_opts_final, required=True),
            "uuid": st.column_config.TextColumn("uuid"),
            "descripcion": st.column_config.TextColumn("observaciones"),
            "pagado_con": st.column_config.SelectboxColumn("pagado con", options=formas_opts, required=False),
            "proveedor": st.column_config.TextColumn("proveedor", disabled=True),
            "fecha_gasto": st.column_config.DateColumn("fecha", disabled=True),
            "cantidad": st.column_config.NumberColumn("cantidad", min_value=0.0, step=1.0),
            "precio_unitario": st.column_config.NumberColumn("gasto estimado", min_value=0.0, step=1.0),
            "importe": st.column_config.NumberColumn("importe", disabled=True),
            "receptor": st.column_config.TextColumn("receptor", disabled=True),
            "serie": st.column_config.TextColumn("serie", disabled=True),
            "folio": st.column_config.TextColumn("folio", disabled=True),
            "version": st.column_config.TextColumn("versión", disabled=True),
            "moneda_xml": st.column_config.TextColumn("moneda xml", disabled=True),
            "tipo_cambio": st.column_config.NumberColumn("tipo cambio", disabled=True),
            "estado_sat": st.column_config.TextColumn("estado sat", disabled=True),
            "forma_pago": st.column_config.TextColumn("forma pago", disabled=True),
            "metodo_pago": st.column_config.TextColumn("método pago", disabled=True),
            "tipo_comprobante": st.column_config.TextColumn("tipo comprobante", disabled=True),
            "uso_cfdi": st.column_config.TextColumn("uso cfdi", disabled=True),
            "subtotal_xml": st.column_config.NumberColumn("subtotal xml", disabled=True),
            "iva_xml": st.column_config.NumberColumn("iva xml", disabled=True),
            "total_xml": st.column_config.NumberColumn("total xml", disabled=True),
        },
    )

    edited["usuario_forma_pago_id"] = edited["pagado_con"].apply(_lbl_to_id)

    st.session_state.setdefault("sg_uuid_cache", {})
    st.session_state.setdefault("sg_uuid_prev", {})

    changed = False

    for i, r in edited.iterrows():
        uuid_now = _norm_uuid(r.get("uuid"))
        uuid_prev = st.session_state["sg_uuid_prev"].get(i, "")

        if not uuid_now:
            st.session_state["sg_uuid_prev"][i] = ""
            continue

        uuid_ok = bool(UUID_RE.fullmatch(uuid_now))
        if not uuid_ok:
            continue

        falta_datos = (_to_float(r.get("importe")) == 0.0) and (str(r.get("proveedor") or "").strip() == "")

        if uuid_now != uuid_prev or falta_datos:
            if uuid_now in st.session_state["sg_uuid_cache"]:
                cfd = st.session_state["sg_uuid_cache"][uuid_now]
            else:
                cfd = get_datoscfd_by_uuid_ctrl(uuid_now)
                st.session_state["sg_uuid_cache"][uuid_now] = cfd

            if not cfd:
                st.warning(f"uuid no encontrado en datoscfd: {uuid_now}")
            else:
                proveedor = (
                    cfd.get("NOMBRE_EMISOR")
                    or cfd.get("nombre_emisor")
                    or cfd.get("NOMBRE")
                    or cfd.get("nombre")
                    or ""
                )
                fecha = cfd.get("FECHA_EMISION") or cfd.get("fecha_emision")

                importe = cfd.get("IMPORTE") or cfd.get("importe") or cfd.get("TOTAL") or cfd.get("total")
                cantidad = cfd.get("CANTIDAD") or cfd.get("cantidad") or 1
                precio_unitario = cfd.get("PRECIO_UNITARIO") or cfd.get("precio_unitario") or 0

                receptor = cfd.get("NOMBRE_RECEPTOR") or cfd.get("nombre_receptor") or ""
                folio = cfd.get("FOLIO") or cfd.get("folio") or ""
                serie = cfd.get("SERIE") or cfd.get("serie") or ""
                version = cfd.get("VERSION") or cfd.get("version") or ""
                moneda_xml = cfd.get("MONEDA") or cfd.get("moneda") or ""
                tipo_cambio = cfd.get("TIPOCAMBIO") or cfd.get("tipocambio") or 0

                estado_sat = cfd.get("ESTADO_SAT") or cfd.get("estado_sat") or ""
                forma_pago = cfd.get("FORMAPAGO") or cfd.get("formapago") or ""
                metodo_pago = cfd.get("METODOPAGO") or cfd.get("metodopago") or ""
                tipo_comprobante = cfd.get("TIPOCOMPROBANTE") or cfd.get("tipocomprobante") or ""
                uso_cfdi = cfd.get("USOCFDI") or cfd.get("usocfdi") or ""

                total_xml = cfd.get("TOTAL") or cfd.get("total") or 0
                subtotal_xml = cfd.get("SUBTOTAL") or cfd.get("subtotal") or 0
                iva_xml = cfd.get("IVA") or cfd.get("iva") or 0

                edited.at[i, "proveedor"] = str(proveedor).strip()

                if fecha is not None and str(fecha).strip() != "":
                    dt = pd.to_datetime(fecha, errors="coerce")
                    if not pd.isna(dt):
                        edited.at[i, "fecha_gasto"] = dt.date()

                edited.at[i, "importe"] = _to_float(importe)
                edited.at[i, "cantidad"] = _to_int(cantidad)
                edited.at[i, "precio_unitario"] = _to_float(precio_unitario)

                edited.at[i, "receptor"] = str(receptor).strip()
                edited.at[i, "folio"] = str(folio).strip()
                edited.at[i, "serie"] = str(serie).strip()
                edited.at[i, "version"] = str(version).strip()
                edited.at[i, "moneda_xml"] = str(moneda_xml).strip().upper()

                if str(moneda_xml).strip().upper() == "MXN":
                    edited.at[i, "tipo_cambio"] = 1
                else:
                    edited.at[i, "tipo_cambio"] = _to_float(tipo_cambio)

                est = str(estado_sat).strip()
                edited.at[i, "estado_sat"] = est if est else "Vigente"

                edited.at[i, "forma_pago"] = str(forma_pago).strip()
                edited.at[i, "metodo_pago"] = str(metodo_pago).strip().upper()
                edited.at[i, "tipo_comprobante"] = _tipo_comprobante_a_clave(str(tipo_comprobante))
                edited.at[i, "uso_cfdi"] = str(uso_cfdi).strip().upper()

                edited.at[i, "total_xml"] = _to_float(total_xml)
                edited.at[i, "subtotal_xml"] = _to_float(subtotal_xml)
                edited.at[i, "iva_xml"] = _to_float(iva_xml)

                changed = True

            usado = uuid_ya_usado_ctrl(uuid_now, exclude_solicitud_id=int(selected_id))
            if usado:
                st.warning(
                    f"este uuid ya fue usado en otra solicitud: "
                    f"folio {usado.get('folio','')} (solicitud_id {usado.get('solicitud_id','')}), "
                    f"estatus {usado.get('estatus','')}, empleado {usado.get('empleado_nombre','')}"
                )

            st.session_state["sg_uuid_prev"][i] = uuid_now

    if changed:
        st.session_state["sg_det_df"] = edited
        st.rerun()

    csave, cdel = st.columns([2, 1])

    with cdel:
        ids_opts = []
        if "id" in edited.columns:
            ids_opts = [
                int(x)
                for x in edited["id"].dropna().tolist()
                if str(x).strip() not in ("", "none", "nan")
            ]

        ids_a_borrar = st.multiselect(
            "borrar ids",
            options=ids_opts,
            default=[],
            key="sg_ids_borrar",
        )

    with csave:
        if st.button("guardar detalle", use_container_width=True, key="sg_btn_guardar_detalle"):
            rows_out = edited.to_dict(orient="records")
            for r in rows_out:
                r.pop("pagado_con", None)

            res = guardar_detalle_ctrl(
                solicitud_id=int(selected_id),
                rows=rows_out,
                deleted_ids=[int(x) for x in ids_a_borrar],
                usuario_id=int(usuario["id"]),
            )

            if res.get("ok"):
                st.success(res.get("msg", "detalle guardado"))

                st.session_state.pop("sg_det_df", None)
                st.session_state.pop("sg_det_df_solicitud_id", None)
                st.session_state["sg_uuid_prev"] = {}
                st.session_state["sg_uuid_cache"] = {}
                st.session_state.pop("sg_det_editor", None)

                st.rerun()
            else:
                msg = res.get("msg", "")
                if "uuid" in msg.lower() and "ya fue usado" in msg.lower():
                    st.warning(msg)
                else:
                    st.error(msg or "no se pudo guardar el detalle")