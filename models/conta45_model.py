# models/conta45_model.py
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Tuple, Union
import pandas as pd
from models.db import run_query_firebird, run_query
import fdb
import streamlit as st
from models.prorrateo_model import cargar_prorrateo_completo

_PRORRATEOS_CACHE: dict[str, Any] | None = None

_CUENTAS_MM_CACHE: dict[str, bool] = {}

def _trunc6_float(v: float) -> float:
    try:
        return int(float(v) * 1e6) / 1e6
    except Exception:
        return 0.0

def _trunc4_float(v: float) -> float:
    try:
        return int(float(v) * 1e4) / 1e4
    except Exception:
        return 0.0

def _montomov(v: float) -> float:
    return _trunc4_float(v)
    
def _group_detalle_solicitud_rows(detalle: list[dict]) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    for r in detalle or []:
        detalle_id = int(r.get("detalle_id") or 0)
        if detalle_id <= 0:
            continue
        out.setdefault(detalle_id, []).append(r)
    return out

def obtener_cuenta_costo(cve_doc: str) -> str:
    if not cve_doc:
        return "6500-060-020"  # fallback conservador
    cve = cve_doc.strip()
    # factura: inicia con letra
    if cve and cve[0].isalpha():
        return "5000-001-001"
    # remisión: inicia con 0000
    if cve.startswith("0000"):
        return "6500-060-020"
    # default (por si llega algo raro)
    return "6500-060-020"

def _get_prorr_cache():
    """carga 1 vez todo el paquete de prorrateos (maestro, detalle, etc.)."""
    global _PRORRATEOS_CACHE
    if _PRORRATEOS_CACHE is None:
        data = cargar_prorrateo_completo(None)  # todos
        maestro = data.get("maestro")
        detalle = data.get("detalle")
        if hasattr(maestro, "copy") and callable(maestro.copy):
            maestro = maestro.copy()
        if hasattr(detalle, "copy") and callable(detalle.copy):
            detalle = detalle.copy()
        _PRORRATEOS_CACHE = {"maestro": maestro, "detalle": detalle}
    return _PRORRATEOS_CACHE

def _get_prorrateo_por_id(prorrateo_id: Optional[int]) -> Dict[str, Any]:
    """
    si prorrateo_id viene:
      pide a prorrateo_model solo ese prorrateo (maestro + detalle)
    si viene None:
      usa el cache global (comportamiento anterior).
    """
    if prorrateo_id is None:
        return _get_prorr_cache()

    data = cargar_prorrateo_completo(prorrateo_id)
    maestro = data.get("maestro")
    detalle = data.get("detalle")

    if hasattr(maestro, "copy") and callable(maestro.copy):
        maestro = maestro.copy()
    if hasattr(detalle, "copy") and callable(detalle.copy):
        detalle = detalle.copy()

    return {"maestro": maestro, "detalle": detalle}

def reset_prorrateos_cache() -> None:
    global _PRORRATEOS_CACHE
    _PRORRATEOS_CACHE = None

def _es_cuenta_multimoneda(num_cta_21: str, debug: bool = False) -> bool:
    """
    consulta CATALOGO.BANDMULTI:
      BANDMULTI = 1 → NO multimoneda
      BANDMULTI = 2 → SÍ multimoneda

    intenta:
      1) TRIM(NUM_CTA) = num_cta_21
      2) si no hay match, NUM_CTA STARTING WITH primeros 10 dígitos
    cachea por NUM_CTA.
    """
    global _CUENTAS_MM_CACHE

    num = (num_cta_21 or "").strip()
    if not num:
        return False

    if num in _CUENTAS_MM_CACHE:
        return _CUENTAS_MM_CACHE[num]

    band = 0

    try:
        # 1️⃣ intento exacto
        sql = """
            SELECT FIRST 1 NUM_CTA, BANDMULTI
            FROM CUENTAS25
            WHERE TRIM(NUM_CTA) = ?
        """
        res = run_query_firebird("FIREBIRD_BIO_COI", sql, (num,))

        # 2️⃣ si no hay nada, probamos solo contra los primeros 10 dígitos
        if not res:
            base10 = num[:10]
            sql2 = """
                SELECT FIRST 1 NUM_CTA, BANDMULTI
                FROM CUENTAS25
                WHERE NUM_CTA STARTING WITH ?
            """
            res = run_query_firebird("FIREBIRD_BIO_COI", sql2, (base10,))

        if res:
            row0 = res[0]
            if isinstance(row0, dict):
                band = int(row0.get("BANDMULTI") or 0)
                num_db = str(row0.get("NUM_CTA") or "").strip()
            else:
                # asumimos orden: NUM_CTA, BANDMULTI
                num_db = str(row0[0] or "").strip()
                band = int(row0[1] or 0)
        else:
            num_db = "(sin match)"

    except Exception as e:
        if debug:
            st.write(f"[MM] error al consultar CATALOGO para {num}: {e}")
        band = 0
        num_db = "(error)"

    # regla que tú marcaste:
    #   1 → NO multimoneda
    #   2 → SÍ multimoneda
    es_multi = (band == 2)

    _CUENTAS_MM_CACHE[num] = es_multi

    if debug:
        st.write(
            f"[MM] cuenta pedida={num} | cuenta_catalogo={num_db} | "
            f"BANDMULTI={band} → multimoneda={es_multi}"
        )

    return es_multi

def _t_saldos(ejercicio: int) -> str:
    # SALDOS25 para 2025, SALDOS24 para 2024, etc.
    anio2 = int(ejercicio) % 100
    return f"SALDOS{anio2:02d}"

def _t_saldosdp(ejercicio: int) -> str:
    # SALDOSDP25 para 2025, etc.
    anio2 = int(ejercicio) % 100
    return f"SALDOSDP{anio2:02d}"

def _afectar_saldos(cur, ejercicio: int, periodo: int, partida: Dict[str, Any]) -> None:
    """
    actualiza:
      - SALDOSxx  (depto 0)
      - SALDOSDPxx (depto real de la partida)

    según:
      debe  -> CARGOnn
      haber -> ABONOnn
    nn = periodo con 2 dígitos (01..14)
    """
    try:
        num_cta = (partida.get("NUM_CTA") or "").strip()
        if not num_cta:
            return

        # depto real de la partida (para SALDOSDP)
        depto_partida = partida.get("NUMDEPTO")
        try:
            depto_partida = int(depto_partida) if depto_partida is not None else 0
        except Exception:
            depto_partida = 0

        debe_haber = (partida.get("DEBE_HABER") or "").strip().upper()
        monto = _montomov(partida.get("MONTOMOV") or 0.0)
        if monto == 0:
            return

        if not (1 <= int(periodo) <= 14):
            return

        mm = f"{int(periodo):02d}"
        col_cargo = f"CARGO{mm}"
        col_abono = f"ABONO{mm}"

        if debe_haber == "D":
            col_monto = col_cargo
        elif debe_haber == "H":
            col_monto = col_abono
        else:
            return

        tabla_saldos   = _t_saldos(ejercicio)
        tabla_saldosdp = _t_saldosdp(ejercicio)

        # 1) SALDOSxx (siempre dep 0)
        dep0 = 0
        sql_upd_saldos = f"""
            UPDATE {tabla_saldos}
               SET {col_monto} = COALESCE({col_monto}, 0) + ?
             WHERE NUM_CTA = ? AND EJERCICIO = ? 
        """
        cur.execute(sql_upd_saldos, (monto, num_cta, int(ejercicio)))

        #if cur.rowcount == 0:
        #    sql_ins_saldos = f"""
        #        INSERT INTO {tabla_saldos}
        #            (NUM_CTA, EJERCICIO, DEPTO, {col_monto})
        #        VALUES
        #            (?, ?, ?, ?)
        #    """
        #    cur.execute(sql_ins_saldos, (num_cta, int(ejercicio), dep0, monto))

        # 2) SALDOSDPxx (por departamento)
        sql_upd_saldosdp = f"""
            UPDATE {tabla_saldosdp}
               SET {col_monto} = COALESCE({col_monto}, 0) + ?
             WHERE NUM_CTA = ? AND EJERCICIO = ? AND DEPTO = ?
        """
        cur.execute(sql_upd_saldosdp, (monto, num_cta, int(ejercicio), depto_partida))

        #if cur.rowcount == 0:
        #    sql_ins_saldosdp = f"""
        #        INSERT INTO {tabla_saldosdp}
        #            (NUM_CTA, EJERCICIO, DEPTO, {col_monto})
        #        VALUES
        #            (?, ?, ?, ?)
        #    """
        #    cur.execute(sql_ins_saldosdp, (num_cta, int(ejercicio), depto_partida, monto))

    except Exception as e:
        try:
            st.write(f"[warn] error al afectar saldos: {e}")
        except Exception:
            pass

def _mk_partidas_venta(row: pd.Series) -> list[Dict[str, Any]]:
    """
    Partidas por **cada documento de venta**:
    SIN retención:
      D  Clientes (IMPORTE)
      H  Ventas (subtotal)
      H  IVA 16% (iva)
    CON retención de IVA:
      D  Clientes      (IMPORTE)
      D  IVA retención (|ret_iva|)
      H  Ventas        (subtotal)
      H  IVA 16%       (iva)
    """

    # ----------------- números base -----------------
    #importe = float(row.get("importe") or row.get("IMPORTE") or 0.0)
    #iva = float(row.get("iva") or row.get("IVA") or 0.0)
    #ieps = float(row.get("ieps") or row.get("IEPS") or 0.0)
    #ret_iva_raw = float(row.get("ret_iva") or row.get("RET_IVA") or 0.0)
    #ret_isr_raw = float(row.get("ret_isr") or row.get("RET_ISR") or 0.0)  # de momento no lo usamos
    def trunc8(v):
        return int(v * 1e6) / 1e6
    
    importe = trunc8(float(row.get("importe") or row.get("IMPORTE") or 0.0))
    iva = trunc8(float(row.get("iva") or row.get("IVA") or 0.0))
    ieps = trunc8(float(row.get("ieps") or row.get("IEPS") or 0.0))
    ret_iva_raw = trunc8(float(row.get("ret_iva") or row.get("RET_IVA") or 0.0))
    ret_isr_raw = trunc8(float(row.get("ret_isr") or row.get("RET_ISR") or 0.0))

    # en tus datos las retenciones vienen negativas
    ret_iva = abs(ret_iva_raw)
    ret_isr = abs(ret_isr_raw)

    # suponemos: IMPORTE = subtotal + IEPS + IVA - ret_iva - ret_isr
    #subtotal = importe - ieps - iva + ret_iva + ret_isr
    subtotal = trunc8(importe - ieps - iva + ret_iva + ret_isr)

    if subtotal < 0:
        subtotal = 0.0

    tcambio = float(row.get("tcambio") or row.get("TCAMBIO") or 1.0)

    nombre = str(row.get("nombre") or row.get("NOMBRE") or "").strip()
    factura = str(row.get("factura") or row.get("FACTURA") or "").strip()
    cveprov = str(row.get("cve_clpv") or row.get("CVE_CLPV") or "").strip()
    fecha = str(row.get("fecha_apli") or row.get("FECHA_APLI") or "").strip()
    concepto = f"{nombre} {cveprov} Doc. {factura}".upper()
    fecha_raw = row.get("fecha_apli") or row.get("FECHA_APLI")
    dt = pd.to_datetime(fecha_raw, errors="coerce")
    fecha_str = "" if pd.isna(dt) else dt.strftime("%d-%m-%Y")

    # ----------------- cuentas contables -----------------
    moneda_txt = str(row.get("moneda") or row.get("MONEDA") or "").lower()
    num_moned = int(row.get("num_moned") or row.get("NUM_MONED") or 1)
    
    # cuenta clientes base (de CUENTA_CONTABLE)
    cta_cliente_masked = str(
        row.get("cuenta_contable") or row.get("CUENTA_CONTABLE") or ""
    ).strip()

    # si es en dólares → cuenta especial
    #if num_moned == 2 or "dólar" in moneda_txt:
    #    cta_cliente_masked = "1150-003-002"
    # si es en dólares → cuenta especial
    if (num_moned == 2 or "dólar" in moneda_txt) and cta_cliente_masked != "1150-004-001":
        cta_cliente_masked = "1150-003-002"

    cta_cliente = _normalize_numcta_masked_to_21(cta_cliente_masked)

    # cuenta de ventas según reglas:
    # - clientes ASHLAND → 4100-005-000
    # - demás con IVA > 0 → 4100-001-000
    # - demás sin IVA      → 4100-003-000
    nombre_up = nombre.upper()
    if "ASHLAND" in nombre_up:
        cta_ventas_masked = "4100-005-000"
    else:
        if abs(iva) > 0:
            cta_ventas_masked = "4100-001-000"
        else:
            cta_ventas_masked = "4100-003-000"

    cta_ventas = _normalize_numcta_masked_to_21(cta_ventas_masked)

    # impuestos fijos que me diste
    cta_iva = _normalize_numcta_masked_to_21("2170-001-000")   # IVA 16%
    cta_iva_ret = _normalize_numcta_masked_to_21("1200-003-000")  # IVA retenido (activo)
    # cta_ret_isr = _normalize_numcta_masked_to_21("2150-007-002")  # la dejamos para después
    #depto = int(row.get("unidad_de_negocio")) or int(row.get("UNIDAD_DE_NEGOCIO")) or 0
    depto = int(row.get("unidad_de_negocio")) 
    partidas: list[Dict[str, Any]] = []

    # ------------ DEBE ------------
    # Clientes siempre por IMPORTE (total neto a cobrar)
    partidas.append({
        "NUM_CTA": cta_cliente,
        "DEBE_HABER": "D",
        "MONTOMOV": importe,
        "CONCEP_PO": concepto,
        "NUMDEPTO": 0,
        "TIPCAMBIO": tcambio,
        "CCOSTOS": None,
        "CGRUPOS": None,
    })

    # IVA retención si existe
    concepto_iva_ret = f"Retencion IVA {nombre} - {cveprov} Doc. {factura}".upper()
    if ret_iva > 0:
        partidas.append({
            "NUM_CTA": cta_iva_ret,
            "DEBE_HABER": "D",
            "MONTOMOV": ret_iva,
            "CONCEP_PO": concepto_iva_ret,
            "NUMDEPTO": 0,
            "TIPCAMBIO": tcambio,
            "CCOSTOS": None,
            "CGRUPOS": None,
        })

    # ------------ HABER ------------
    # Ventas (subtotal)
    concepto_haber = f"DOC. {factura} {fecha_str} {nombre} ".upper()
    partidas.append({
        "NUM_CTA": cta_ventas,
        "DEBE_HABER": "H",
        "MONTOMOV": subtotal,
        "CONCEP_PO": concepto_haber,
        "NUMDEPTO": depto,
        "TIPCAMBIO": tcambio,
        "CCOSTOS": None,
        "CGRUPOS": None,
    })

    # IVA 16% (solo si hay)
    concepto_iva = f"IVA 16% Doc. {factura}".upper()
    if abs(iva) > 0:
        partidas.append({
            "NUM_CTA": cta_iva,
            "DEBE_HABER": "H",
            "MONTOMOV": iva,
            "CONCEP_PO": concepto_iva,
            "NUMDEPTO": 0,
            "TIPCAMBIO": tcambio,
            "CCOSTOS": None,
            "CGRUPOS": None,
        })
    #st.write(f"[DEBUG] numero de departamente {depto} partidas para doc {factura}: {partidas}")3
    return partidas

def _mk_partidas_costo_venta(row: pd.Series) -> list[Dict[str, Any]]:
    """
    póliza de costo de venta por renglón:

      D  Costo de ventas          (costo)
      H  Inventario prod. terminado  (costo)
    """
    # costo ya viene calculado en la consulta (pf.cant * pf.cost)
    #costo = float(row.get("costo") or row.get("COSTO") or 0.0)
    costo = float(int((row.get("costo") or row.get("COSTO") or 0.0) * 1e8) / 1e8)
    ## Modificado para permitir costos 0 en costo de ventas
    #if costo <= 0:
    #    return []

    cve_doc = str(row.get("cve_doc") or row.get("CVE_DOC") or "").strip()
    cve_art = str(row.get("cve_art") or row.get("CVE_ART") or "").strip()
    cant    = float(row.get("cant") or row.get("CANT") or 0.0)
    nombre  = str(row.get("nombre") or row.get("NOMBRE") or "").strip()
    cve_clpv = str(row.get("clave") or row.get("CLAVE") or "").strip()
    articulo = str(row.get("articulo") or row.get("ARTICULO") or "").strip()
    #fecha   = str(row.get("fecha_doc") or row.get("FECHA_DOC") or "").strip()
    fecha_raw = row.get("fecha_doc") or row.get("FECHA_DOC")
    #fecha = "" if fecha_raw is None else pd.to_datetime(fecha_raw, errors="coerce").date().isoformat()  
    dt = pd.to_datetime(fecha_raw, errors="coerce")
    fecha = "" if pd.isna(dt) else dt.strftime("%d-%m-%Y")

    #st.write("fecha_raw:", fecha_raw, type(fecha_raw))
    #st.write("dt:", dt, type(dt))
    #st.write("fecha:", fecha, type(fecha))

    concepto_almacen = (
        f"DOC. {cve_doc} {fecha} {cve_art} - {articulo}".upper()
    )
    # cuenta inventario prod. terminado (de la consulta)
    cta_inv_masked = str(
        row.get("cuenta_almacen") or
        row.get("CUENTA_ALMACEN") or
        "1190-005-000"
    ).strip()

    cta_inv = _normalize_numcta_masked_to_21(cta_inv_masked)

    # cuenta de costo de ventas (ajusta a tu catálogo)
    ## cta_costo_masked = "5000-001-001"
    cta_costo_masked = obtener_cuenta_costo(cve_doc)

    cta_costo = _normalize_numcta_masked_to_21(cta_costo_masked)

    # tipo de cambio (si quisieras usar alguno después)
    tcambio = float(row.get("TCAMBIO") or 1.0)

    # por ahora lo dejo sin departamento específico
    depto = int(row.get("DEPTO") or row.get("depto") or 0)

    partidas: list[Dict[str, Any]] = []

    
    # DEBE: costo de ventas
    concepto_costo = f"COSTO DE VENTAS DOC. {cve_doc} {fecha} {cve_clpv} - {nombre}".upper()
    partidas.append({
        "NUM_CTA": cta_costo,
        "DEBE_HABER": "D",
        "MONTOMOV": costo,
        "CONCEP_PO": concepto_costo,
        "NUMDEPTO": depto,
        "TIPCAMBIO": tcambio,
        "CCOSTOS": 0,
        "CGRUPOS": 0,
    })

    # HABER: inventario de producto terminado
    partidas.append({
        "NUM_CTA": cta_inv,
        "DEBE_HABER": "H",
        "MONTOMOV": costo,
        "CONCEP_PO": concepto_almacen,
        "NUMDEPTO": 0,
        "TIPCAMBIO": tcambio,
        "CCOSTOS": 0,
        "CGRUPOS": 0,
    })

    return partidas

def _guess_cve_folio_from_row(row: pd.Series) -> Optional[str]:
    """
    intenta recuperar CVE_FOLIO desde PAGA_M01 si no viene en la fila.
    usaremos CVE_PROV + REFER como llaves principales.
    """
    try:
        cve_prov = str(row.get("CVE_PROV") or row.get("cve_prov") or "").strip()
        refer = str(row.get("REFER") or row.get("refer") or "").strip()
        #st.write(f"CLAVE PROVEEDOR {cve_prov} Y REFER {refer}")
        if not cve_prov or not refer:
            return None

        sql = """
            SELECT FIRST 1 CVE_FOLIO
            FROM PAGA_M01
            WHERE trim(CVE_PROV) = ? AND trim(REFER) = ?
            ORDER BY FECHA_APLI DESC
        """
        res = run_query_firebird("FIREBIRD_BIO_SAE", sql, (cve_prov, refer))

        if not res:
            return None

        row0 = res[0]
        if isinstance(row0, dict):
            return str(row0.get("CVE_FOLIO") or "").strip()
        else:
            return str(row0[0] or "").strip()
    except Exception as e:
        st.write(f"[WARN] _guess_cve_folio_from_row error: {e}")
        return None
    
def _detect_nivel_from_masked(numcta_masked: str) -> int:
    """
    Detecta el nivel según los segmentos diferentes de '000':
      1000-000-000 → nivel 1
      1000-001-000 → nivel 2
      1000-001-001 → nivel 3
    """
    s = (numcta_masked or "").strip()
    if "-" not in s:
        return 1
    parts = s.split("-")
    if len(parts) != 3:
        return 1
    # contamos cuántos bloques son distintos de "000"
    nivel = sum(1 for p in parts if p != "000")
    return max(1, min(3, nivel))

def _normalize_numcta_masked_to_21(numcta_masked: str) -> str:
    """
    Convierte '9999-999-999' al formato de 21 dígitos para COI:
      - quita guiones
      - forma base 10 dígitos (4+3+3)
      - rellena con ceros a la DERECHA hasta 20 dígitos
      - agrega el nivel en la posición 21
    Ejemplo:
        1000-000-000 -> 100000000000000000001
        1000-001-000 -> 100000100000000000002
        1000-001-001 -> 100000100100000000003
    """
    s = (numcta_masked or "").strip()
    if not s:
        return "0" * 20 + "1"
    nivel = _detect_nivel_from_masked(s)

    if "-" in s:
        parts = s.split("-")
        a = (parts[0] if len(parts) > 0 else "").zfill(4)
        b = (parts[1] if len(parts) > 1 else "").zfill(3)
        c = (parts[2] if len(parts) > 2 else "").zfill(3)
        base10 = f"{a}{b}{c}"
    else:
        # si viene sin guiones, asumimos 10 dígitos base
        digits = "".join(ch for ch in s if ch.isdigit())
        base10 = digits.zfill(10)

    # Rellenar a la DERECHA hasta 20 dígitos
    base20 = base10.ljust(20, "0")

    # Agregar nivel al final
    return f"{base20}{nivel}"

def _fetch_impuestos_y_cuentas_por_folio(cve_folio: str) -> dict:
    """
    Debug: lee impuestos de Firebird (FOLCXP01) y cuentas contables de MySQL (IASPEL.KSAECIT).
    Compatible con CursorResult de SQLAlchemy.
    """
    import streamlit as st
    out = {
        "IMPUESTO1": 0.0, "IMPUESTO2": 0.0, "IMPUESTO3": 0.0, "IMPUESTO4": 0.0,
        "CTA_IMP1": None, "CTA_IMP2": None, "CTA_IMP3": None, "CTA_IMP4": None,
    }

    try:
        # --- 1️⃣ impuestos desde Firebird SAE ---
        sql_imp = """
            SELECT 
                COALESCE(SUM(IMPUESTO1), 0) AS IMPUESTO1,
                COALESCE(SUM(IMPUESTO2), 0) AS IMPUESTO2,
                COALESCE(SUM(IMPUESTO3), 0) AS IMPUESTO3,
                COALESCE(SUM(IMPUESTO4), 0) AS IMPUESTO4
            FROM FOLCXP01
            WHERE CVE_FOLIO CONTAINING (?)
        """
        r = run_query_firebird("FIREBIRD_BIO_SAE", sql_imp, (str(cve_folio),))
        #st.write("📦 Resultado Firebird FOLCXP01:", r)
        #st.write("[DEBUG] Resultado Firebird FOLCXP01:", r)

        if r:
            row = r[0]
            # soporta tanto dict como tupla
            if isinstance(row, dict):
                out["IMPUESTO1"] = float(row.get("IMPUESTO1", 0) or 0)
                out["IMPUESTO2"] = float(row.get("IMPUESTO2", 0) or 0)
                out["IMPUESTO3"] = float(row.get("IMPUESTO3", 0) or 0)
                out["IMPUESTO4"] = float(row.get("IMPUESTO4", 0) or 0)
            else:
                out["IMPUESTO1"], out["IMPUESTO2"], out["IMPUESTO3"], out["IMPUESTO4"] = [float(x or 0) for x in row]

        # --- 2️⃣ cuentas desde MySQL IASPEL.KSAECIT ---
        sql_cta = """
            SELECT CDCUEIMP, DSCUENTA
            FROM iaspel.ksaecit
            WHERE CDCUEIMP IN (1,2,3,4)
        """
        cuentas = run_query("BIO", sql_cta, ())
        #st.write("📚 Resultado MySQL iaspel.ksaecit (crudo):", cuentas)
        #st.write("[DEBUG] Resultado MySQL iaspel.ksaecit (crudo):", cuentas)

        # normalizar si es CursorResult
        if hasattr(cuentas, "mappings"):
            cuentas = list(cuentas.mappings())
        elif hasattr(cuentas, "fetchall"):
            cuentas = [dict(row) for row in cuentas.fetchall()]
        elif isinstance(cuentas, tuple) or isinstance(cuentas, list):
            # si ya es lista de dict o tupla
            cuentas = [dict(row) if not isinstance(row, dict) else row for row in cuentas]
        else:
            cuentas = []

        #st.write("✅ Resultado MySQL convertido a lista de dicts:", cuentas)
        #st.write("[DEBUG] Resultado MySQL convertido a lista de dicts:", cuentas)

        # construir mapa
        mapa = {}
        for row in cuentas:
            try:
                cdcueimp = int(row.get("CDCUEIMP", 0))
                dscuenta = str(row.get("DSCUENTA", "")).strip()
                mapa[cdcueimp] = dscuenta
            except Exception as err_row:
                st.write(f"[WARN] fila con error: {row} ({err_row})")

        # aplicar normalización de cuenta
        for k, v in ((4, "CTA_IMP1"), (2, "CTA_IMP2"), (3, "CTA_IMP3"), (1, "CTA_IMP4")):
            raw = mapa.get(k)
            out[v] = _normalize_numcta_masked_to_21(raw) if raw else None

    except Exception as e:
        st.error(f"⚠️ Error en _fetch_impuestos_y_cuentas_por_folio: {e}")
        st.write(f"[ERROR] _fetch_impuestos_y_cuentas_por_folio: {e}")

    #st.write("✅ Resultado final de impuestos/cuentas:", out)
    #st.write("[DEBUG] Resultado final de impuestos/cuentas:", out)

    return out

def _mk_partidas_solicitud_gasto_desglosada(
        solicitud: dict,
        detalle: list[dict],
    ) -> list[dict]:
    partidas: list[dict] = []
 
    detalle = [
        r for r in (detalle or [])
        if int(float(r.get("prepago") or 0)) == 0
    ]

    cuenta_iva = _normalize_numcta_masked_to_21("1205-001-000")
    cuenta_isr_ret = _normalize_numcta_masked_to_21("2150-004-001")

    grupos = _group_detalle_solicitud_rows(detalle)

    for detalle_id, rows in grupos.items():
        base = rows[0]

        fecha = base.get("fecha")
        proveedor = str(base.get("proveedor") or "").strip()
        concepto = str(base.get("concepto_catalogo") or base.get("concepto") or "").strip()
        uuid = str(base.get("uuid") or "").strip()
        folio_sol = str(base.get("folio") or solicitud.get("folio") or "").strip()
        notas = str(base.get("notas") or "").strip()

        cuenta_pago_raw = str(base.get("cuenta_pago") or "").strip()
        if not cuenta_pago_raw:
            raise ValueError(
                f"el detalle {detalle_id} no tiene cuenta contable en el método de pago"
            )

        cuenta_pago = _normalize_numcta_masked_to_21(cuenta_pago_raw)

        subtotal_xml = _trunc6_float(base.get("subtotal_xml") or 0)
        iva_xml = _trunc6_float(base.get("iva_xml") or 0)
        isr_ret_xml = _trunc6_float(base.get("isr_ret_xml") or 0)
        total_xml = _trunc6_float(base.get("total_xml") or 0)
        precio_unitario = _trunc6_float(base.get("precio_unitario") or 0)

        es_fiscal = bool(uuid)

        concepto_base = f"solicitud {folio_sol} {concepto} {proveedor}".strip().upper()
        if notas:
            concepto_base = f"{concepto_base} {notas}".strip()

        if es_fiscal:
            ajuste_extra = _trunc6_float(total_xml - subtotal_xml - iva_xml + isr_ret_xml)

            # residuos mínimos por redondeo
            if abs(ajuste_extra) < 0.01:
                ajuste_extra = 0.0

            # aquí sí permitimos positivo o negativo:
            # + positivo  -> impuesto local no guardado
            # + negativo  -> descuento no guardado
            monto_gasto = _trunc6_float(subtotal_xml + ajuste_extra)
            monto_abono = total_xml

            if abs(monto_gasto) < 0.01:
                monto_gasto = 0.0

            if monto_gasto < 0:
                raise ValueError(
                    f"el detalle {detalle_id} generó un gasto negativo; revisa subtotal/iva/isr/total"
                )
        else:
            monto_gasto = precio_unitario
            monto_abono = precio_unitario

        suma_prorr = 0.0

        for r in rows:
            cuenta_gasto_raw = str(r.get("cuenta") or "").strip()
            if not cuenta_gasto_raw:
                raise ValueError(
                    f"el detalle {detalle_id} no tiene cuenta contable en solicitud_concepto_gasto"
                )

            cuenta_gasto = _normalize_numcta_masked_to_21(cuenta_gasto_raw)

            porcentaje = float(r.get("porcentaje") or 0)
            depto = int(r.get("depto") or 0)

            monto_prorr = _trunc6_float(monto_gasto * (porcentaje / 100.0))
            suma_prorr += monto_prorr

            if monto_prorr != 0:
                partidas.append({
                    "NUM_CTA": cuenta_gasto,
                    "DEBE_HABER": "D",
                    "MONTOMOV": monto_prorr,
                    "CONCEP_PO": concepto_base[:120],
                    "NUMDEPTO": depto,
                    "TIPCAMBIO": 1.0,
                    "CCOSTOS": 0,
                    "CGRUPOS": 0,
                })

        # ajuste por diferencia de redondeo
        diferencia = _trunc6_float(monto_gasto - suma_prorr)
        if diferencia != 0 and rows:
            r0 = rows[0]
            cuenta_gasto = _normalize_numcta_masked_to_21(str(r0.get("cuenta") or "").strip())
            depto = int(r0.get("depto") or 0)

            partidas.append({
                "NUM_CTA": cuenta_gasto,
                "DEBE_HABER": "D",
                "MONTOMOV": diferencia,
                "CONCEP_PO": concepto_base[:120],
                "NUMDEPTO": depto,
                "TIPCAMBIO": 1.0,
                "CCOSTOS": 0,
                "CGRUPOS": 0,
            })

        # 2) iva acreditable solo si trae uuid
        if es_fiscal and iva_xml > 0:
            partidas.append({
                "NUM_CTA": cuenta_iva,
                "DEBE_HABER": "D",
                "MONTOMOV": iva_xml,
                "CONCEP_PO": f"IVA ACREDITABLE {folio_sol} {proveedor}".strip().upper()[:120],
                "NUMDEPTO": 0,
                "TIPCAMBIO": 1.0,
                "CCOSTOS": 0,
                "CGRUPOS": 0,
            })
            
        # 2.1) isr retenido solo si trae uuid
        if es_fiscal and isr_ret_xml > 0:
            partidas.append({
                "NUM_CTA": cuenta_isr_ret,
                "DEBE_HABER": "H",
                "MONTOMOV": isr_ret_xml,
                "CONCEP_PO": f"ISR RETENIDO {folio_sol} {proveedor}".strip().upper()[:120],
                "NUMDEPTO": 0,
                "TIPCAMBIO": 1.0,
                "CCOSTOS": 0,
                "CGRUPOS": 0,
            })

        # 3) abono a método de pago
        if monto_abono > 0:
            partidas.append({
                "NUM_CTA": cuenta_pago,
                "DEBE_HABER": "H",
                "MONTOMOV": monto_abono,
                "CONCEP_PO": f"PAGO SOLICITUD {folio_sol} {proveedor}".strip().upper()[:120],
                "NUMDEPTO": 0,
                "TIPCAMBIO": 1.0,
                "CCOSTOS": 0,
                "CGRUPOS": 0,
            })

    return partidas

def _agrupar_partidas_solicitud_gasto(partidas: list[dict]) -> list[dict]:
    agrupadas: dict[tuple, dict] = {}

    cuenta_iva = _normalize_numcta_masked_to_21("1200-001-000")
    cuenta_isr_ret = _normalize_numcta_masked_to_21("2150-004-001")

    for p in partidas or []:
        num_cta = str(p.get("NUM_CTA") or "").strip()
        debe_haber = str(p.get("DEBE_HABER") or "").strip().upper()
        numdepto = int(p.get("NUMDEPTO") or 0)
        tipcambio = float(p.get("TIPCAMBIO") or 1.0)
        ccostos = int(p.get("CCOSTOS") or 0)
        cgrupos = int(p.get("CGRUPOS") or 0)
        monto = _montomov(p.get("MONTOMOV") or 0.0)

        if not num_cta or not debe_haber or monto == 0:
            continue

        key = (
            num_cta,
            debe_haber,
            numdepto,
            tipcambio,
            ccostos,
            cgrupos,
        )

        if key not in agrupadas:
            agrupadas[key] = {
                "NUM_CTA": num_cta,
                "DEBE_HABER": debe_haber,
                "MONTOMOV": monto,
                "CONCEP_PO": str(p.get("CONCEP_PO") or "").strip()[:120],
                "NUMDEPTO": numdepto,
                "TIPCAMBIO": tipcambio,
                "CCOSTOS": ccostos,
                "CGRUPOS": cgrupos,
            }
        else:
            agrupadas[key]["MONTOMOV"] = _montomov(
                agrupadas[key]["MONTOMOV"] + monto
            )

    resultado = [
        v for v in agrupadas.values()
        if _montomov(v.get("MONTOMOV") or 0.0) != 0
    ]

    def _orden_partida(p: dict):
        num_cta = str(p.get("NUM_CTA") or "").strip()
        debe_haber = str(p.get("DEBE_HABER") or "").strip().upper()
        numdepto = int(p.get("NUMDEPTO") or 0)

        # 1) gastos
        if debe_haber == "D" and num_cta not in (cuenta_iva, cuenta_isr_ret):
            grupo = 1
        # 2) impuestos
        elif num_cta in (cuenta_iva, cuenta_isr_ret):
            grupo = 2
        # 3) bancos / prepagos / formas de pago
        else:
            grupo = 3

        return (
            grupo,
            numdepto,
            num_cta,
            debe_haber,
        )

    resultado.sort(key=_orden_partida)
    return resultado


def fetch_cuenta_contable_proveedor(cve_prov: str) -> str | None:
    """
    Devuelve la cuenta contable del proveedor desde PROV01.CUENTA_CONTABLE,
    buscando por PROV01.CLAVE = cve_prov (Firebird SAE).

    Retorna la cuenta normalizada a 21 dígitos (según tu formato 999999999999999999999)
    o None si no se encuentra.
    """
    import streamlit as st

    if not cve_prov:
        st.warning("⚠️ No se proporcionó CVE_PROV para buscar la cuenta contable.")
        return None

    try:
        sql = """
            SELECT CUENTA_CONTABLE
            FROM PROV01
            WHERE CLAVE containing (?)
        """
        res = run_query_firebird("FIREBIRD_BIO_SAE", sql, (str(cve_prov).strip(),))
        #st.write(f"🔎 Resultado PROV01 para {cve_prov}:", res)

        if not res:
            st.info(f"No se encontró cuenta contable para el proveedor {cve_prov}.")
            return None

        cuenta_raw = res[0]["CUENTA_CONTABLE"] if isinstance(res[0], dict) else res[0][0]
        cuenta_norm = _normalize_numcta_masked_to_21(str(cuenta_raw).strip())

        #st.write(f"✅ Cuenta contable normalizada: {cuenta_norm}")
        return cuenta_norm

    except Exception as e:
        st.error(f"⚠️ Error al obtener cuenta contable del proveedor {cve_prov}: {e}")
        print(f"[ERROR] fetch_cuenta_contable_proveedor({cve_prov}): {e}")
        return None

def _db_name(cur) -> str:
    try:
        cur.execute("SELECT rdb$get_context('SYSTEM','DB_NAME') FROM rdb$database")
        row = cur.fetchone()
        return (row[0] if row else "") or ""
    except Exception:
        return ""

def _t_polizas(eje: int) -> str:
    return f"POLIZAS{int(eje):02d}"

def _t_aux(eje: int) -> str:
    return f"AUXILIAR{int(eje):02d}"

def obtener_opciones(eje: int):
    p = _t_polizas(eje)
    sql = f"SELECT DISTINCT TIPO_POLI AS TIPO FROM {p} ORDER BY 1"
    tipos = [r["TIPO"] for r in run_query_firebird("FIREBIRD_BIO_COI", sql)]
    periodos = list(range(1, 14))
    return {"tipos": tipos, "periodos": periodos}

def _filtros_where_y_params(f, alias_p="p", alias_a="a"):
    where, params = [], []
    if f.get("tipos"):
        ph = ",".join(["?"] * len(f["tipos"]))
        where.append(f"{alias_p}.TIPO_POLI IN ({ph})")
        params.extend(f["tipos"])
    if f.get("periodos"):
        ph = ",".join(["?"] * len(f["periodos"]))
        where.append(f"{alias_p}.PERIODO IN ({ph})")
        params.extend(f["periodos"])
    if f.get("cuenta_pref"):
        where.append(f"{alias_a}.NUM_CTA STARTING WITH ?")
        params.append(f["cuenta_pref"])
    if f.get("concepto_like"):
        where.append(f"{alias_a}.CONCEP_PO CONTAINING ?")
        params.append(f["concepto_like"])
    if f.get("fecha_desde"):
        where.append(f"{alias_p}.FECHA_POL >= ?")
        params.append(f["fecha_desde"])
    if f.get("fecha_hasta"):
        where.append(f"{alias_p}.FECHA_POL <= ?")
        params.append(f["fecha_hasta"])
    return where, params

def obtener_polizas(eje: int, filtros: dict, limit: int | None = 300, offset: int = 0):
    p, a = _t_polizas(eje), _t_aux(eje)
    where, params = _filtros_where_y_params(filtros, "p", "a")
    where_sql = " WHERE " + " AND ".join(where) if where else ""
    pag = "" if (limit is None) else f"FIRST {limit} SKIP {offset}"
    sql = f"""
        SELECT {pag}
               p.TIPO_POLI, p.NUM_POLIZ, p.PERIODO, p.FECHA_POL, p.ORIGEN,
               SUM(IIF(a.DEBE_HABER = 'D', a.MONTOMOV, 0)) AS CARGO,
               SUM(IIF(a.DEBE_HABER = 'H', a.MONTOMOV, 0)) AS ABONO,
               COUNT(*) AS PARTIDAS
        FROM {p} p
        JOIN {a} a
          ON a.TIPO_POLI = p.TIPO_POLI
         AND a.NUM_POLIZ = p.NUM_POLIZ
         AND a.PERIODO   = p.PERIODO
        {where_sql}
        GROUP BY p.TIPO_POLI, p.NUM_POLIZ, p.PERIODO, p.FECHA_POL, p.ORIGEN
        ORDER BY p.FECHA_POL, p.TIPO_POLI, p.NUM_POLIZ
    """
    return run_query_firebird("FIREBIRD_BIO_COI", sql, tuple(params))

def contar_polizas(eje: int, filtros: dict):
    p, a = _t_polizas(eje), _t_aux(eje)
    where, params = _filtros_where_y_params(filtros, "p", "a")
    where_sql = " WHERE " + " AND ".join(where) if where else ""
    sql = f"""
        SELECT COUNT(*) AS N
        FROM (
            SELECT p.TIPO_POLI, p.NUM_POLIZ, p.PERIODO
            FROM {p} p
            JOIN {a} a
              ON a.TIPO_POLI = p.TIPO_POLI
             AND a.NUM_POLIZ = p.NUM_POLIZ
             AND a.PERIODO   = p.PERIODO
            {where_sql}
            GROUP BY p.TIPO_POLI, p.NUM_POLIZ, p.PERIODO
        ) x
    """
    r = run_query_firebird("FIREBIRD_BIO_COI", sql, tuple(params))
    return int(r[0]["N"]) if r else 0

def resumen_por_periodo(eje: int, filtros: dict):
    p, a = _t_polizas(eje), _t_aux(eje)
    where, params = _filtros_where_y_params(filtros, "p", "a")
    where_sql = " WHERE " + " AND ".join(where) if where else ""
    sql = f"""
        SELECT p.PERIODO,
               SUM(IIF(a.DEBE_HABER = 'D', a.MONTOMOV, 0)) AS CARGOS,
               SUM(IIF(a.DEBE_HABER = 'H', a.MONTOMOV, 0)) AS ABONOS
        FROM {p} p
        JOIN {a} a
          ON a.TIPO_POLI = p.TIPO_POLI
         AND a.NUM_POLIZ = p.NUM_POLIZ
         AND a.PERIODO   = p.PERIODO
        {where_sql}
        GROUP BY p.PERIODO
        ORDER BY p.PERIODO
    """
    return run_query_firebird("FIREBIRD_BIO_COI", sql, tuple(params))

def partidas_de_poliza(eje: int, tipo: str, periodo: int, num_poliz):
    a = _t_aux(eje)
    sql = f"""
        SELECT NUM_PART, NUM_CTA, CONCEP_PO, DEBE_HABER, MONTOMOV, FECHA_POL
        FROM {a}
        WHERE TIPO_POLI = ? AND PERIODO = ? AND NUM_POLIZ = ?
        ORDER BY NUM_PART
    """
    return run_query_firebird("FIREBIRD_BIO_COI", sql, (tipo, periodo, num_poliz))

def resumen_por_tipo(eje: int, filtros: dict):
    p, a = _t_polizas(eje), _t_aux(eje)
    where, params = _filtros_where_y_params(filtros, "p", "a")
    where_sql = " WHERE " + " AND ".join(where) if where else ""
    sql = f"""
        SELECT p.TIPO_POLI,
               SUM(IIF(a.DEBE_HABER='D', a.MONTOMOV, 0)) AS CARGOS,
               SUM(IIF(a.DEBE_HABER='H', a.MONTOMOV, 0)) AS ABONOS
        FROM {p} p
        JOIN {a} a
          ON a.TIPO_POLI = p.TIPO_POLI
         AND a.NUM_POLIZ = p.NUM_POLIZ
         AND a.PERIODO   = p.PERIODO
        {where_sql}
        GROUP BY p.TIPO_POLI
        ORDER BY p.TIPO_POLI
    """
    return run_query_firebird("FIREBIRD_BIO_COI", sql, tuple(params))

def resumen_por_origen(eje: int, filtros: dict):
    p, a = _t_polizas(eje), _t_aux(eje)
    where, params = _filtros_where_y_params(filtros, "p", "a")
    where_sql = " WHERE " + " AND ".join(where) if where else ""
    sql = f"""
        SELECT COALESCE(p.ORIGEN, 'SIN ORIGEN') AS ORIGEN,
               SUM(IIF(a.DEBE_HABER='D', a.MONTOMOV, 0)) AS CARGOS,
               SUM(IIF(a.DEBE_HABER='H', a.MONTOMOV, 0)) AS ABONOS
        FROM {p} p
        JOIN {a} a
          ON a.TIPO_POLI = p.TIPO_POLI
         AND a.NUM_POLIZ = p.NUM_POLIZ
         AND a.PERIODO   = p.PERIODO
        {where_sql}
        GROUP BY p.ORIGEN
        ORDER BY ORIGEN
    """
    return run_query_firebird("FIREBIRD_BIO_COI", sql, tuple(params))

def resumen_conteo_por_origen(eje: int, filtros: dict):
    p, a = _t_polizas(eje), _t_aux(eje)
    where, params = _filtros_where_y_params(filtros, "p", "a")
    where_sql = " WHERE " + " AND ".join(where) if where else ""
    sql = f"""
        SELECT ORIGEN, COUNT(*) AS NUM_POLIZAS
        FROM (
            SELECT COALESCE(p.ORIGEN, 'SIN ORIGEN') AS ORIGEN,
                   p.TIPO_POLI, p.NUM_POLIZ, p.PERIODO
            FROM {p} p
            JOIN {a} a
              ON a.TIPO_POLI = p.TIPO_POLI
             AND a.NUM_POLIZ = p.NUM_POLIZ
             AND a.PERIODO   = p.PERIODO
            {where_sql}
            GROUP BY COALESCE(p.ORIGEN, 'SIN ORIGEN'),
                     p.TIPO_POLI, p.NUM_POLIZ, p.PERIODO
        ) x
        GROUP BY ORIGEN
        ORDER BY ORIGEN
    """
    return run_query_firebird("FIREBIRD_BIO_COI", sql, tuple(params))

######### INSERCIÓN POLIZAS DESDE PAGA_M01 #########

def _conn_coi_from_secrets(secrets) -> fdb.Connection:
    cfg = secrets["FIREBIRD_BIO_COI"]
    return fdb.connect(
        host=cfg.get("host", "localhost"),
        database=cfg["database"],
        user=cfg["user"],
        password=cfg["password"],
        port=int(cfg.get("port")),
        charset=cfg.get("charset", "ISO8859_1"),
    )

def _as_date(val) -> datetime:
    dt = pd.to_datetime(val, errors="coerce")
    if pd.isna(dt):
        dt = pd.Timestamp.today()
    return dt.to_pydatetime()

def _periodo_y_ejercicio(fecha: datetime) -> Tuple[int, int]:
    return fecha.month, fecha.year

def _siguiente_num_poliza(cur, tipo: str, periodo: int, ejercicio: int) -> str:
    sufijo = str(ejercicio)[-2:]
    tabla = f"POLIZAS{sufijo}"
    cur.execute(f"""
        SELECT COALESCE(MAX(CAST(NUM_POLIZ AS INTEGER)), 0)
        FROM {tabla}
        WHERE TIPO_POLI = ? AND PERIODO = ? AND EJERCICIO = ?
    """, (tipo, periodo, ejercicio))
    n = (cur.fetchone() or (0,))[0] or 0
    # ← relleno con ESPACIOS, como pediste:tipo
    return str(n + 1).rjust(5)

def _mk_concepto(row: pd.Series) -> str:
    prov = str(row.get("NOMBRE_PROV", "")).strip()
    refer = str(row.get("REFER", "")).strip()
    imp = float(pd.to_numeric(str(row.get("IMPORTE", 0)).replace(",", ""), errors="coerce") or 0)
    fecha = _as_date(row.get("FECHA_APLI"))
    descomp = str(row.get("DESCR", "")).strip()
    return f" {descomp} - {fecha.date().isoformat()} - {prov} - {refer}"

def buscar_prorrateo_en_maestro(maestro, cve_prov=None, num_cpto=None):
    """
    Devuelve: (fila_prorrateo | None, metodo_usado, diag)
    metodo_usado: 'prov+cpto' | 'prov->mas_usado' | 'sin_datos' | 'sin_match'
    """
    diag = {
        "type": str(type(maestro)),
        "cols": list(getattr(maestro, "columns", [])),
        "shape": getattr(maestro, "shape", None),
        "cve_prov_arg": cve_prov,
        "num_cpto_arg": num_cpto,
    }

    if not isinstance(maestro, pd.DataFrame) or maestro.empty:
        return None, "sin_datos", diag

    df = maestro.copy()

    def _pick(dfx, opciones):
        return next((c for c in opciones if c in dfx.columns), None)

    col_prov = _pick(df, ["cdcvepro","CVE_PROV","cve_prov","proveedor"])
    col_cpto = _pick(df, ["cdnrocon","NUM_CPTO","num_cpto","concepto"])
    diag["col_prov"] = col_prov
    diag["col_cpto"] = col_cpto

    if not col_prov:
        return None, "sin_datos", diag

    df[col_prov] = df[col_prov].astype(str).str.strip().str.rjust(10).str[-10:]
    cve = (cve_prov or "").strip().rjust(10)[-10:]

    if col_cpto:
        df[col_cpto] = pd.to_numeric(df[col_cpto], errors="coerce").astype("Int64")
        num = pd.to_numeric(num_cpto, errors="coerce")
    else:
        num = None

    # 1) prov + concepto
    if col_cpto and num is not None and not pd.isna(num):
        cand = df[(df[col_prov] == cve) & (df[col_cpto] == int(num))]
        if not cand.empty:
            orden_cols = [c for c in ["activo","fecha_alta","id","updated_at","created_at"] if c in cand.columns]
            if orden_cols:
                cand = cand.sort_values(orden_cols, ascending=[False] + [False]*(len(orden_cols)-1))
            return cand.iloc[0], "prov+cpto", diag

    # 2) más usado del proveedor
    cand = df[df[col_prov] == cve]
    if not cand.empty and col_cpto:
        moda = cand[col_cpto].mode(dropna=True)
        if not moda.empty and pd.notna(moda.iloc[0]):
            fila = cand[cand[col_cpto] == moda.iloc[0]]
            return fila.iloc[0], "prov->mas_usado", diag

    return None, "sin_match", diag

# --- helper para detectar columnas por nombre equivalente ---
def _pick_col(df: pd.DataFrame, opciones: list[str]) -> Optional[str]:
    return next((c for c in opciones if c in df.columns), None)

def _mk_partidas_desde_row(
    row: pd.Series,
    info,
    prorrateo_id: int | None = None,
) -> tuple[list[Dict[str, Any]], str, dict]:
    """
    genera partidas:
      - debe (gasto): prorrateo sobre subtotal
      - debe/haber (impuestos): por impuesto con cuenta
      - haber (proveedor): total

    si prorrateo_id viene, se usa ese idnumpon (no se hace match por proveedor/concepto).
    """

    maestro = info.get("maestro")
    detalle = info.get("detalle")

    def g(*keys, default=None):
        for k in keys:
            v = row.get(k, None)
            if v is None:
                continue
            if isinstance(v, str) and v.strip() == "":
                continue
            return v
        return default

    def trunc6(v: float) -> float:
        return int(float(v) * 1e6) / 1e6

    # normaliza dataframes
    if not isinstance(maestro, pd.DataFrame) or maestro.empty:
        maestro = None
    if not isinstance(detalle, pd.DataFrame) or detalle.empty:
        detalle = None

    cve_mov = str(g("cve_prov", "CVE_PROV", default="") or "").strip()
    cpto_mov = g("num_cpto", "NUM_CPTO", default=None)
    concepto = _mk_concepto(row)

    # total
    imp_total = trunc6(
        float(
            pd.to_numeric(
                str(g("importe", "IMPORTE", default=0)).replace(",", ""),
                errors="coerce",
            )
            or 0.0
        )
    )

    # impuestos y cuentas por folio
    cve_folio = str(g("cve_folio", "CVE_FOLIO", default="") or "").strip()
    if not cve_folio:
        cve_folio = _guess_cve_folio_from_row(row) or ""

    if cve_folio:
        imp = _fetch_impuestos_y_cuentas_por_folio(cve_folio)
    else:
        imp = {
            "IMPUESTO1": 0.0,
            "IMPUESTO2": 0.0,
            "IMPUESTO3": 0.0,
            "IMPUESTO4": 0.0,
            "CTA_IMP1": None,
            "CTA_IMP2": None,
            "CTA_IMP3": None,
            "CTA_IMP4": None,
        }

    imp1 = trunc6(float(imp.get("IMPUESTO1") or 0.0))
    imp2 = trunc6(float(imp.get("IMPUESTO2") or 0.0))
    imp3 = trunc6(float(imp.get("IMPUESTO3") or 0.0))
    imp4 = trunc6(float(imp.get("IMPUESTO4") or 0.0))

    ret_total = trunc6(imp1 + imp2 + imp3)
    iva_normal = trunc6(imp4)

    subtotal = trunc6(imp_total - iva_normal + ret_total)
    if subtotal < 0:
        subtotal = 0.0

    cta_prov = fetch_cuenta_contable_proveedor(cve_mov)

    # tcambio (corregido)
    tcambio = float(pd.to_numeric(g("tcambio", "TCAMBIO", default=1), errors="coerce") or 1.0)

    def fallback(extra: dict) -> tuple[list[Dict[str, Any]], str, dict]:
        cta_gasto = _normalize_numcta_masked_to_21(
            str(g("cta_cont_cpto", "CTA_CONT_CPTO", default="") or "").strip()
        )

        partidas_fb: list[Dict[str, Any]] = []

        # debe: gasto (subtotal)
        partidas_fb.append({
            "NUM_CTA": cta_gasto,
            "DEBE_HABER": "D",
            "MONTOMOV": subtotal,
            "CONCEP_PO": concepto,
            "NUMDEPTO": 0,
            "TIPCAMBIO": tcambio,
            "CCOSTOS": 0,
            "CGRUPOS": 0,
        })

        # impuestos
        for monto, cta, es_ret in (
            (imp1, imp.get("CTA_IMP1"), True),
            (imp2, imp.get("CTA_IMP2"), True),
            (imp3, imp.get("CTA_IMP3"), True),
            (imp4, imp.get("CTA_IMP4"), False),
        ):
            monto_r = trunc6(round(float(monto or 0.0), 2))
            if monto_r != 0 and cta:
                partidas_fb.append({
                    "NUM_CTA": cta,
                    "DEBE_HABER": "H" if es_ret else "D",
                    "MONTOMOV": monto_r,
                    "CONCEP_PO": concepto,
                    "NUMDEPTO": 0,
                    "TIPCAMBIO": tcambio,
                    "CCOSTOS": 0,
                    "CGRUPOS": 0,
                })

        # haber: proveedor
        partidas_fb.append({
            "NUM_CTA": cta_prov,
            "DEBE_HABER": "H",
            "MONTOMOV": trunc6(imp_total),
            "CONCEP_PO": concepto,
            "NUMDEPTO": 0,
            "TIPCAMBIO": tcambio,
            "CCOSTOS": 0,
            "CGRUPOS": 0,
        })

        metodo_fb = extra.pop("_metodo", None) or "fallback"
        diag_fb = extra.pop("_diag", None) or {}
        return partidas_fb, metodo_fb, {"fallback": True, **diag_fb, **extra}

    # sin detalle global -> fallback
    if detalle is None:
        return fallback({"_metodo": "sin_datos", "razon": "sin_detalle_global"})

    # ========= caso forzado por idnumpon =========
    if prorrateo_id is not None:
        det = detalle.copy()
        # detecta columna id en detalle
        col_id_detalle = _pick_col(det, ["idnumpon", "prorrateo_id", "IdProrrateo", "id_prorrateo", "id"])
        if not col_id_detalle:
            return fallback({
                "_metodo": "por_id_forzado",
                "razon": "sin_col_id_detalle",
                "idnumpon": int(prorrateo_id),
            })

        det[col_id_detalle] = pd.to_numeric(det[col_id_detalle], errors="coerce")
        det = det[det[col_id_detalle] == int(prorrateo_id)]
        if det.empty:
            return fallback({
                "_metodo": "por_id_forzado",
                "razon": "detalle_vacio_para_id",
                "idnumpon": int(prorrateo_id),
            })

        col_cta = _pick_col(det, ["dsctacon", "cuenta", "NUM_CTA", "num_cta"])
        col_depto = _pick_col(det, ["idnuevo", "NUMDEPTO", "numdepto", "departamento", "idunineg"])
        col_pct = _pick_col(det, ["flporuni", "porcentaje", "porc", "factor"])

        if not col_cta or not col_pct:
            return fallback({
                "_metodo": "por_id_forzado",
                "razon": "sin_cols_detalle",
                "idnumpon": int(prorrateo_id),
                "col_cta": col_cta,
                "col_pct": col_pct,
            })

        det["_cta"] = det[col_cta].astype(str).str.strip()
        det["_pct"] = pd.to_numeric(det[col_pct], errors="coerce").fillna(0.0)

        if col_depto:
            det["_depto"] = pd.to_numeric(det[col_depto], errors="coerce").astype("Int64")
        else:
            det["_depto"] = pd.Series([pd.NA] * len(det), index=det.index, dtype="Int64")

        partidas: list[Dict[str, Any]] = []

        # debe: gasto prorrateado
        for _, rdet in det.iterrows():
            monto = trunc6(float(rdet["_pct"]) * float(subtotal))
            if monto <= 0:
                continue
            numdepto_val = int(rdet["_depto"]) if pd.notna(rdet["_depto"]) else None
            cta_norm = _normalize_numcta_masked_to_21(rdet["_cta"])
            partidas.append({
                "NUM_CTA": cta_norm,
                "DEBE_HABER": "D",
                "MONTOMOV": monto,
                "CONCEP_PO": concepto,
                "NUMDEPTO": numdepto_val,
                "TIPCAMBIO": tcambio,
                "CCOSTOS": 0,
                "CGRUPOS": 0,
            })

        # impuestos
        for monto, cta, es_ret in (
            (imp1, imp.get("CTA_IMP1"), True),
            (imp2, imp.get("CTA_IMP2"), True),
            (imp3, imp.get("CTA_IMP3"), True),
            (imp4, imp.get("CTA_IMP4"), False),
        ):
            monto_r = trunc6(round(float(monto or 0.0), 2))
            if monto_r != 0 and cta:
                partidas.append({
                    "NUM_CTA": cta,
                    "DEBE_HABER": "H" if es_ret else "D",
                    "MONTOMOV": monto_r,
                    "CONCEP_PO": concepto,
                    "NUMDEPTO": 0,
                    "TIPCAMBIO": tcambio,
                    "CCOSTOS": 0,
                    "CGRUPOS": 0,
                })

        # haber: proveedor
        partidas.append({
            "NUM_CTA": cta_prov,
            "DEBE_HABER": "H",
            "MONTOMOV": trunc6(imp_total),
            "CONCEP_PO": concepto,
            "NUMDEPTO": 0,
            "TIPCAMBIO": tcambio,
            "CCOSTOS": 0,
            "CGRUPOS": 0,
        })

        return partidas, "por_id_forzado", {
            "fallback": False,
            "idnumpon": int(prorrateo_id),
            "subtotal": subtotal,
            "imp1": imp1, "imp2": imp2, "imp3": imp3, "imp4": imp4,
        }

    # ========= caso normal (por match) =========
    if maestro is None:
        return fallback({"_metodo": "sin_datos", "razon": "sin_maestro"})

    pror_row, metodo, diag = buscar_prorrateo_en_maestro(maestro, cve_mov, cpto_mov)
    if (pror_row is None) or (metodo in ("sin_datos", "sin_match")):
        return fallback({"_metodo": metodo, "razon": "sin_match_prov_cpto", **(diag or {})})

    try:
        pr_df = pror_row.to_frame().T
    except Exception:
        pr_df = pd.DataFrame([dict(pror_row)])

    col_id_maestro = _pick_col(pr_df, ["idnumpon", "id", "prorrateo_id", "ID", "IdProrrateo"])
    col_id_detalle = _pick_col(detalle, ["idnumpon", "prorrateo_id", "IdProrrateo", "id_prorrateo", "id"])

    if not col_id_maestro or not col_id_detalle:
        return fallback({
            "_metodo": metodo,
            "razon": "sin_cols_id",
            "col_id_maestro": col_id_maestro,
            "col_id_detalle": col_id_detalle,
        })

    try:
        idnumpon = int(pd.to_numeric(pr_df.iloc[0][col_id_maestro], errors="coerce"))
    except Exception:
        return fallback({"_metodo": metodo, "razon": "idnumpon_invalido"})

    det = detalle.copy()
    det[col_id_detalle] = pd.to_numeric(det[col_id_detalle], errors="coerce")
    det = det[det[col_id_detalle] == idnumpon]
    if det.empty:
        return fallback({"_metodo": metodo, "razon": "sin_detalle_filtrado", "idnumpon": idnumpon})

    col_cta = _pick_col(det, ["dsctacon", "cuenta", "NUM_CTA", "num_cta"])
    col_depto = _pick_col(det, ["idnuevo", "NUMDEPTO", "numdepto", "departamento", "idunineg"])
    col_pct = _pick_col(det, ["flporuni", "porcentaje", "porc", "factor"])
    if not col_cta or not col_pct:
        return fallback({"_metodo": metodo, "razon": "sin_cols_detalle", "idnumpon": idnumpon})

    det["_cta"] = det[col_cta].astype(str).str.strip()
    det["_pct"] = pd.to_numeric(det[col_pct], errors="coerce").fillna(0.0)

    if col_depto:
        det["_depto"] = pd.to_numeric(det[col_depto], errors="coerce").astype("Int64")
    else:
        det["_depto"] = pd.Series([pd.NA] * len(det), index=det.index, dtype="Int64")

    partidas: list[Dict[str, Any]] = []

    for _, rdet in det.iterrows():
        monto = trunc6(float(rdet["_pct"]) * float(subtotal))
        if monto <= 0:
            continue
        numdepto_val = int(rdet["_depto"]) if pd.notna(rdet["_depto"]) else None
        cta_norm = _normalize_numcta_masked_to_21(rdet["_cta"])
        partidas.append({
            "NUM_CTA": cta_norm,
            "DEBE_HABER": "D",
            "MONTOMOV": monto,
            "CONCEP_PO": concepto,
            "NUMDEPTO": numdepto_val,
            "TIPCAMBIO": tcambio,
            "CCOSTOS": 0,
            "CGRUPOS": 0,
        })

    for monto, cta, es_ret in (
        (imp1, imp.get("CTA_IMP1"), True),
        (imp2, imp.get("CTA_IMP2"), True),
        (imp3, imp.get("CTA_IMP3"), True),
        (imp4, imp.get("CTA_IMP4"), False),
    ):
        monto_r = trunc6(round(float(monto or 0.0), 2))
        if monto_r != 0 and cta:
            partidas.append({
                "NUM_CTA": cta,
                "DEBE_HABER": "H" if es_ret else "D",
                "MONTOMOV": monto_r,
                "CONCEP_PO": concepto,
                "NUMDEPTO": 0,
                "TIPCAMBIO": tcambio,
                "CCOSTOS": 0,
                "CGRUPOS": 0,
            })

    partidas.append({
        "NUM_CTA": cta_prov,
        "DEBE_HABER": "H",
        "MONTOMOV": trunc6(imp_total),
        "CONCEP_PO": concepto,
        "NUMDEPTO": 0,
        "TIPCAMBIO": tcambio,
        "CCOSTOS": 0,
        "CGRUPOS": 0,
    })

    return partidas, metodo, {
        "fallback": False,
        "idnumpon": idnumpon,
        "subtotal": subtotal,
        "imp1": imp1, "imp2": imp2, "imp3": imp3, "imp4": imp4,
    }

def _insert_encabezado(cur,tipo: str,num_poliz: str,periodo: int,ejercicio: int,fecha: datetime,concepto: str,uuid: Optional[str],num_partidas: int) -> None:
    sufijo = str(ejercicio)[-2:]          # 2026 -> "26"
    tabla = f"POLIZAS{sufijo}"             # POLIZAS26
    sql = f"""
        INSERT INTO {tabla}
          (TIPO_POLI, NUM_POLIZ, PERIODO, EJERCICIO, FECHA_POL, CONCEP_PO,
           NUM_PART, LOGAUDITA, CONTABILIZ, NUMPARCUA, TIENEDOCUMENTOS,
           PROCCONTAB, ORIGEN, UUID, ESPOLIZAPRIVADA, UUIDOP, DOC_SIGO)
        VALUES
          (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    cur.execute(sql, (tipo,num_poliz,periodo,ejercicio,fecha,concepto,num_partidas,"N","S",0,0,0,"OneCore",uuid or None,0,None,None))

def _insert_partidas(cur, tipo: str, num_poliz: str, periodo: int, ejercicio: int,
                     fecha: datetime, partidas: List[Dict[str, Any]]) -> None:
    """
    Inserta renglones en AUXILIARxx. NUM_PART (double) = 1.0, 2.0, …
    y afecta SALDOSxx / SALDOSDPxx.
    Optimizada sin cambiar comportamiento funcional.
    """
    sufijo = str(ejercicio)[-2:]
    tabla = f"AUXILIAR{sufijo}"

    # 1) precargar multimoneda solo una vez por cuenta única
    cuentas_unicas = {
        (p.get("NUM_CTA") or "").strip()
        for p in partidas
        if (p.get("NUM_CTA") or "").strip()
    }
    mapa_multimoneda = {
        cta: _es_cuenta_multimoneda(cta)
        for cta in cuentas_unicas
    }

    num_part = 1.0

    for p in partidas:
        numdepto_val = p.get("NUMDEPTO")
        if numdepto_val is None:
            numdepto_val = 0

        num_cta = (p.get("NUM_CTA") or "").strip()
        tc_row = float(p.get("TIPCAMBIO") or 1.0)
        monto_mov = _montomov(p.get("MONTOMOV") or 0.0)

        # si por truncado quedó en cero, no insertamos ni afectamos
        if monto_mov == 0:
            continue

        if mapa_multimoneda.get(num_cta, False):
            tipc = tc_row
        else:
            tipc = 1.0

        cur.execute(f"""
            INSERT INTO {tabla}
              (TIPO_POLI, NUM_POLIZ, NUM_PART, PERIODO, EJERCICIO,
               NUM_CTA, FECHA_POL, CONCEP_PO, DEBE_HABER, MONTOMOV,
               NUMDEPTO, TIPCAMBIO, CONTRAPAR, ORDEN, CCOSTOS, CGRUPOS,
               IDINFADIPAR, IDUUID)
            VALUES
              (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            tipo, num_poliz, num_part, periodo, ejercicio,
            num_cta, fecha, p.get("CONCEP_PO"), p.get("DEBE_HABER"),
            monto_mov,
            numdepto_val,
            tipc,
            0, int(num_part),
            p.get("CCOSTOS"), p.get("CGRUPOS"),
            -1, -1
        ))

        _afectar_saldos(cur, ejercicio, periodo, {
            "NUM_CTA": num_cta,
            "DEBE_HABER": p.get("DEBE_HABER"),
            "MONTOMOV": monto_mov,
            "NUMDEPTO": numdepto_val,
        })

        num_part += 1.0

def insertar_poliza_y_auxiliares(row: pd.Series, secrets, prorrateo_id: Optional[int] = None,debug: bool=True) -> Dict[str, Any]:
    #info = _get_prorr_cache(force_reload=True)
    info = _get_prorrateo_por_id(prorrateo_id)

    st.write(f"[INFO] Generando póliza en COI para CVE_PROV={row.get('CVE_PROV')} NUM_CPTO={row.get('NUM_CPTO')} con prorrateo_id={prorrateo_id} (método={info.get('metodo')})")

    try:
        fecha = _as_date(row.get("FECHA_APLI"))
        periodo, ejercicio = _periodo_y_ejercicio(fecha)
        tipo = "Dr"

        concepto = _mk_concepto(row)
        uuid = str(row.get("APP_UUID") or "").strip() or None
        cve_folio = _guess_cve_folio_from_row(row)
        partidas, metodo, diag = _mk_partidas_desde_row(row, info, prorrateo_id=prorrateo_id)
        idnumpon = diag.get("idnumpon") if isinstance(diag, dict) else None

        if debug:
            st.markdown("### Debug payload COI")
            st.json({
                "tipo": tipo, "periodo": periodo, "ejercicio": ejercicio,
                "fecha": fecha.isoformat(), "concepto": concepto, "uuid": uuid,
                "metodo_prorrateo": metodo,
                "idnumpon": idnumpon,
                "diag_prorrateo": diag,
                "partidas": partidas
            })
            return {"ok": True, "msg": f"DEBUG: no se insertó (método={metodo})."}

        # seguridad extra: si por alguna razón no hay partidas
        partidas = [
            p for p in partidas
            if _montomov(p.get("MONTOMOV") or 0.0) != 0
        ]

        if not partidas:
            return {"ok": False, "msg": "no se generaron partidas"}

        con = _conn_coi_from_secrets(secrets)
        cur = con.cursor()
        try:
            dbname = _db_name(cur)
            num_poliz = _siguiente_num_poliza(cur, tipo, periodo, ejercicio)
            num_partidas = len(partidas)
            _insert_encabezado(cur, tipo, num_poliz, periodo, ejercicio, fecha, concepto, uuid, num_partidas)
            _insert_partidas(cur, tipo, num_poliz, periodo, ejercicio, fecha, partidas)

            def _insert_relacion_iaspel_prorrateo(
                row: pd.Series,
                tipo: str,
                num_poliz: str,
                periodo: int,
                ejercicio: int,
                idnumpon: int | None,
                usuario: str,
            ) -> None:
                """
                inserta una fila en iaspel.relaciones después de crear la póliza
                de prorrateo en COI.
                """

                # campos origen en row (PAGA_M01)
                refer = str(row.get("REFER") or row.get("refer") or "").strip()
                ada_cfd_doc = row.get("APP_ADA_CFD_DOC") or row.get("ada_cfd_doc")

                status = "Nuevo"  # fijo, como pediste

                sql_rel = """
                    INSERT INTO iaspel.relaciones
                        (refer, t_poliza, n_poliza, p_poliza, e_poliza,
                        fecha_creacion, ada_cfd_doc, usuario, status, idnumpon)
                    VALUES
                        (:refer, :t_poliza, :n_poliza, :p_poliza, :e_poliza,
                        NOW(), :ada_cfd_doc, :usuario, :status, :idnumpon)
                """

                params_rel: Dict[str, Any] = {
                    "refer": refer,
                    "t_poliza": tipo,
                    "n_poliza": str(num_poliz).strip(),
                    "p_poliza": int(periodo),
                    "e_poliza": int(ejercicio),
                    "ada_cfd_doc": ada_cfd_doc,
                    "usuario": usuario,
                    "status": status,
                    "idnumpon": int(idnumpon) if idnumpon is not None else None,
                }

                # 👈 aquí ya va un dict (no lista/tupla), igual que en crear_prorrateo_cabecera
                run_query("BIO", sql_rel, params_rel)

            con.commit()
            # calcula el sufijo de 2 dígitos (siempre con cero a la izquierda si hiciera falta)
            suf = f"{int(ejercicio) % 100:02d}"
            tabla_polizas = f"POLIZAS{suf}"

            cur.execute(f"""
                SELECT TIPO_POLI, NUM_POLIZ, PERIODO, EJERCICIO, FECHA_POL, CONCEP_PO
                FROM {tabla_polizas}
                WHERE TIPO_POLI=? AND NUM_POLIZ=? AND PERIODO=? AND EJERCICIO=?
            """, (tipo, num_poliz, periodo, ejercicio))
            ver = cur.fetchone()

            # --- ✅ actualización de estatus en PAGA_M01 ---
            try:
                if res := ver:
                    if cve_folio:
                        sql_upd = """
                            UPDATE PAGA_M01
                            SET APP_STATUS = 'Contabilidad',
                                AFEC_COI = 'A'
                            WHERE TRIM(CVE_FOLIO) = ?
                        """
                        run_query_firebird("FIREBIRD_BIO_SAE", sql_upd, (str(cve_folio),))
                        st.write(f"[INFO] Estatus de PAGA_M01 actualizado a 'Contabilidad' para {cve_folio}")
                        # --- ✅ relación en iaspel.relaciones (prorrateos) ---
                        usuario_email = st.session_state.get("username", "")  # <-- ajusta tú

                        try:
                            _insert_relacion_iaspel_prorrateo(
                                row=row,
                                tipo=tipo,
                                num_poliz=num_poliz,
                                periodo=periodo,
                                ejercicio=ejercicio,
                                idnumpon=idnumpon,
                                usuario=usuario_email,
                            )
                        except Exception as e_rel:
                            # no rompemos la póliza; solo avisamos
                            st.write(f"no se pudo insertar en iaspel.relaciones: {e_rel}")
                        
            except Exception as e_upd:
                st.write(f"[WARN] No se pudo actualizar APP_STATUS en PAGA_M01: {e_upd}")

            if not ver:
                return {"ok": False, "msg": f"No se encontró la póliza tras commit. DB: {dbname}"}

            return {
                "ok": True,
                "msg": f"Póliza {tipo}-{num_poliz}/{periodo}-{ejercicio} creada ({metodo}). DB: {dbname}",
                "poliza": {"tipo": tipo, "num": num_poliz, "periodo": periodo, "ejercicio": ejercicio},
                "metodo_prorrateo": metodo,
                "idnumpon": idnumpon
            }

        except Exception as e:
            con.rollback()
            return {"ok": False, "msg": f"Error en inserción COI: {e}"}
        finally:
            try: cur.close()
            except: pass
            con.close()

    except Exception as e:
        return {"ok": False, "msg": f"Error preparando póliza: {e}"}
    
def inserta_poliza_ventas(data: Union[pd.DataFrame, pd.Series], secrets, debug: bool = False) -> Dict[str, Any]:
    try:
        # normalizar: si viene una sola fila (Series), lo convertimos a DataFrame
        if isinstance(data, pd.DataFrame):
            df = data.copy()
        else:
            df = pd.DataFrame([data])

        if df.empty:
            return {"ok": False, "msg": "DataFrame de ventas vacío."}

        # tomamos la fecha del primer registro (todas deberían ser del mismo día)
        if "fecha_apli" in df.columns:
            fecha_src = df["fecha_apli"].iloc[0]
        else:
            fecha_src = df["FECHA_APLI"].iloc[0]

        fecha = _as_date(fecha_src)
        fecha_str = fecha.strftime("%d-%m-%Y")

        periodo, ejercicio = _periodo_y_ejercicio(fecha)
        tipo = "Dr"  # por ahora siempre Dr, como comentaste

        # acumular TODAS las partidas de TODOS los documentos del día
        partidas: list[Dict[str, Any]] = []
        for _, row in df.iterrows():
            partes_row = _mk_partidas_venta(row)
            if partes_row:
                partidas.extend(partes_row)

        if not partidas:
            return {"ok": False, "msg": "No se generaron partidas de ventas."}

        # concepto general de la póliza diaria
        ## concepto = f"VENTAS DEL {fecha.date().isoformat()}"  cambio a formato dd-mm-yyyy
        
        concepto = f"VENTAS DEL {fecha_str}".upper()

        if debug:
            st.json({
                "tipo": tipo,
                "periodo": periodo,
                "ejercicio": ejercicio,
                "fecha": fecha.isoformat(),
                "num_docs": len(df),
                "num_partidas": len(partidas),
                "concepto": concepto,
            })
            return {"ok": True, "msg": "DEBUG ventas: no se insertó póliza."}

        con = _conn_coi_from_secrets(secrets)
        cur = con.cursor()
        try:
            dbname = _db_name(cur)
            num_poliz = _siguiente_num_poliza(cur, tipo, periodo, ejercicio)
            num_partidas = len(partidas)

            _insert_encabezado(
                cur, tipo, num_poliz, periodo, ejercicio,
                fecha, concepto, uuid=None, num_partidas=num_partidas
            )
            _insert_partidas(cur, tipo, num_poliz, periodo, ejercicio, fecha, partidas)

            con.commit()
            return {
                "ok": True,
                "msg": f"Póliza de ventas {tipo}-{num_poliz}/{periodo}-{ejercicio} creada "
                       f"({len(df)} documentos, {len(partidas)} partidas).",
                "poliza": {
                    "tipo": tipo,
                    "num": num_poliz,
                    "periodo": periodo,
                    "ejercicio": ejercicio,
                },
            }
        except Exception as e:
            con.rollback()
            return {"ok": False, "msg": f"Error en inserción COI ventas: {e}"}
        finally:
            try:
                cur.close()
            except Exception:
                pass
            con.close()
    except Exception as e:
        return {"ok": False, "msg": f"Error preparando póliza ventas: {e}"}
    
def inserta_poliza_costo_venta(
    data: Union[pd.DataFrame, pd.Series],
    secrets,
    debug: bool = False
) -> Dict[str, Any]:
    """
    genera una póliza diaria de costo de venta:
      - recibe un df (o una fila) con las columnas de obtener_costos_venta_por_fecha
      - arma una sola póliza tipo Dr por día
      - una partida D/H por cada renglón de detalle (costo)
    """
    try:
        # normalizar a DataFrame
        if isinstance(data, pd.DataFrame):
            df = data.copy()
        else:
            df = pd.DataFrame([data])

        if df.empty:
            return {"ok": False, "msg": "DataFrame de costo de venta vacío."}

        # fecha base (todas deben ser del mismo día)
        if "fecha_doc" in df.columns:
            fecha_src = df["fecha_doc"].iloc[0]
        else:
            fecha_src = df["FECHA_DOC"].iloc[0]

        fecha = _as_date(fecha_src)
        fecha_str = fecha.strftime("%d-%m-%Y")

        periodo, ejercicio = _periodo_y_ejercicio(fecha)
        tipo = "Dr"  # si luego quieres otro tipo (p.ej. 'Dv'), se cambia aquí

        partidas: list[Dict[str, Any]] = []
        for _, row in df.iterrows():
            partes_row = _mk_partidas_costo_venta(row)
            if partes_row:
                partidas.extend(partes_row)

        if not partidas:
            return {"ok": False, "msg": "No se generaron partidas de costo de venta."}

        concepto = f"COSTO DE VENTA DEL {fecha_str}".upper()

        if debug:
            st.json({
                "tipo": tipo,
                "periodo": periodo,
                "ejercicio": ejercicio,
                "fecha": fecha.isoformat(),
                "num_docs": len(df),
                "num_partidas": len(partidas),
                "concepto": concepto,
            })
            return {"ok": True, "msg": "DEBUG costo venta: no se insertó póliza."}

        con = _conn_coi_from_secrets(secrets)
        cur = con.cursor()
        try:
            dbname = _db_name(cur)
            num_poliz = _siguiente_num_poliza(cur, tipo, periodo, ejercicio)
            num_partidas = len(partidas)

            _insert_encabezado(
                cur, tipo, num_poliz, periodo, ejercicio,
                fecha, concepto, uuid=None, num_partidas=num_partidas
            )
            _insert_partidas(cur, tipo, num_poliz, periodo, ejercicio, fecha, partidas)

            con.commit()
            return {
                "ok": True,
                "msg": (
                    f"Póliza de costo de venta {tipo}-{num_poliz}/"
                    f"{periodo}-{ejercicio} creada "
                    f"({len(df)} renglones de costo, {len(partidas)} partidas)."
                ),
                "poliza": {
                    "tipo": tipo,
                    "num": num_poliz,
                    "periodo": periodo,
                    "ejercicio": ejercicio,
                },
            }
        except Exception as e:
            con.rollback()
            return {"ok": False, "msg": f"Error en inserción COI costo de venta: {e}"}
        finally:
            try:
                cur.close()
            except Exception:
                pass
            con.close()

    except Exception as e:
        return {"ok": False, "msg": f"Error preparando póliza costo de venta: {e}"}


def insertar_poliza_solicitud_gasto_desglosada(
        solicitud: dict,
        detalle: list[dict],
        secrets,
        debug: bool = False,
    ) -> dict:
    #st.write(f"Solicitud: {solicitud}")
    #st.stop()
    try:
        if not detalle:
            return {"ok": False, "msg": "no hay detalle para generar la póliza"}

        #fecha_src = detalle[0].get("fecha") or solicitud.get("fecha_inicio") or datetime.now()
        #fecha = _as_date(fecha_src)
        fecha_src = solicitud.get("fecha_inicio")
        fecha = _as_date(fecha_src)

        periodo, ejercicio = _periodo_y_ejercicio(fecha)
        tipo = "Dr"

        folio = str(solicitud.get("folio") or "").strip()
        empleado = str(solicitud.get("empleado_nombre") or "").strip()
        clientes = str(solicitud.get("clientes") or "").strip()

        concepto = (
            f"COMPROBACION VIATICOS SOL. {folio} {empleado} VISITA {clientes}"
        ).strip().upper()[:120]

        partidas_detalladas = _mk_partidas_solicitud_gasto_desglosada(
            solicitud=solicitud,
            detalle=detalle,
        )

        partidas = _agrupar_partidas_solicitud_gasto(partidas_detalladas)

        for p in partidas:
            p["CONCEP_PO"] = concepto[:120]

        if not partidas:
            return {"ok": False, "msg": "no se generaron partidas"}
        
        if debug:
            return {
                "ok": True,
                "msg": "debug: no se insertó la póliza",
                "concepto": concepto,
                "partidas": partidas,
            }

        con = _conn_coi_from_secrets(secrets)
        cur = con.cursor()
        try:
            num_poliz = _siguiente_num_poliza(cur, tipo, periodo, ejercicio)

            _insert_encabezado(
                cur,
                tipo,
                num_poliz,
                periodo,
                ejercicio,
                fecha,
                concepto,
                uuid=None,
                num_partidas=len(partidas),
            )

            _insert_partidas(
                cur,
                tipo,
                num_poliz,
                periodo,
                ejercicio,
                fecha,
                partidas,
            )

            con.commit()

            return {
                "ok": True,
                "msg": f"póliza {tipo}-{num_poliz}/{periodo}-{ejercicio} creada correctamente",
                "poliza": {
                    "tipo": tipo,
                    "num": num_poliz,
                    "periodo": periodo,
                    "ejercicio": ejercicio,
                },
            }

        except Exception as e:
            con.rollback()
            return {"ok": False, "msg": f"error en inserción COI: {e}"}
        finally:
            try:
                cur.close()
            except Exception:
                pass
            try:
                con.close()
            except Exception:
                pass

    except Exception as e:
        return {"ok": False, "msg": f"error preparando póliza de solicitud: {e}"}
    