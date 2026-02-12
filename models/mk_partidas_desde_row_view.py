

def _mk_partidas_desde_row(row: pd.Series, info) -> tuple[list[Dict[str, Any]], str, dict]:
    """
    Genera partidas para el prorrateo:
      - DEBE (gasto): prorrateo sobre SUBTOTAL = IMPORTE - (imp1+imp2+imp3+imp4)
      - DEBE (impuestos): una línea por cada IMPUESTO>0 con su cuenta (IASPEL.KSAECIT)
      - HABER (proveedor): por IMPORTE total
    """
    maestro = info.get("maestro")
    detalle = info.get("detalle")

    st.write(f"detalle info {detalle}")

    def trunc8(v):
        return int(v * 1e6) / 1e6
    
    if not isinstance(maestro, pd.DataFrame) or maestro.empty:
        maestro = None
    if not isinstance(detalle, pd.DataFrame) or detalle.empty:
        detalle = None

    cve_mov  = row.get("CVE_PROV")
    cpto_mov = row.get("NUM_CPTO")
    concepto = _mk_concepto(row)

    # importe total SAE (PAGA_M01.IMPORTE)
    imp_total = trunc8(float(pd.to_numeric(str(row.get("IMPORTE", 0)).replace(",", ""), errors="coerce") or 0.0))

    # traer impuestos por CVE_FOLIO y cuentas contables --- nueva funcion desde dashboard_prorrateos.py
    cve_folio = str(row.get("CVE_FOLIO") or "").strip()
    # si viene vacío, intentamos inferirlo desde PAGA_M01
    
    if not cve_folio:
        cve_folio = _guess_cve_folio_from_row(row) or ""
    if cve_folio:
        imp = _fetch_impuestos_y_cuentas_por_folio(cve_folio)
    else:
        imp = {
            "IMPUESTO1": 0.0, "IMPUESTO2": 0.0, "IMPUESTO3": 0.0, "IMPUESTO4": 0.0,
            "CTA_IMP1": None, "CTA_IMP2": None, "CTA_IMP3": None, "CTA_IMP4": None,
        }
    
    imp1, imp2, imp3, imp4 = imp["IMPUESTO1"], imp["IMPUESTO2"], imp["IMPUESTO3"], imp["IMPUESTO4"]

    imp1 = trunc8(float(imp["IMPUESTO1"] or 0.0))
    imp2 = trunc8(float(imp["IMPUESTO2"] or 0.0))
    imp3 = trunc8(float(imp["IMPUESTO3"] or 0.0))
    imp4 = trunc8(float(imp["IMPUESTO4"] or 0.0))

    ret_total = trunc8(imp1 + imp2 + imp3)        # retenciones
    iva_normal = trunc8(imp4)                     # impuesto normal

    subtotal = trunc8(imp_total - iva_normal + ret_total)
    if subtotal < 0:
        subtotal = 0.0  # blindaje

    cta_prov = fetch_cuenta_contable_proveedor(cve_mov)

    # localizar prorrateo en maestro
    pror_row, metodo, diag = buscar_prorrateo_en_maestro(maestro, cve_mov, cpto_mov)
    tcambio = row.get("TCAMBIO" or 1)
    def fallback(extra: dict) -> tuple[list[Dict[str, Any]], str, dict]:
        # cuenta de gasto por concepto (CTA_CONT_CPTO) → normalizada a 21 dígitos
        cta_gasto = _normalize_numcta_masked_to_21(str(row.get("CTA_CONT_CPTO", "")).strip())
        partidas_fb = []

        # DEBE: gasto (SUBTOTAL)
        partidas_fb.append({
            "NUM_CTA": cta_gasto,
            "DEBE_HABER": "D",
            "MONTOMOV": subtotal,
            "CONCEP_PO": concepto,
            "NUMDEPTO": 0, "TIPCAMBIO": tcambio, "CCOSTOS": 0, "CGRUPOS": 0,
        })
        # DEBE: impuestos individuales (si > 0 y con cuenta)
        # impuestos:
        #   cta_imp1, cta_imp2, cta_imp3 = retenciones → HABER
        #   cta_imp4                     = impuesto normal → DEBE
        for monto, cta, es_ret in (
            (imp1, imp.get("CTA_IMP1"), True),
            (imp2, imp.get("CTA_IMP2"), True),
            (imp3, imp.get("CTA_IMP3"), True),
            (imp4, imp.get("CTA_IMP4"), False),
        ):
            monto_r = trunc8(round(float(monto or 0.0), 2))
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

        # HABER: proveedor por total
        partidas_fb.append({
            "NUM_CTA": cta_prov,
            "DEBE_HABER": "H",
            "MONTOMOV": trunc8(imp_total),
            "CONCEP_PO": concepto,
            "NUMDEPTO": 0, "TIPCAMBIO": tcambio, "CCOSTOS": 0, "CGRUPOS": 0,
        })

        return partidas_fb, metodo, {"fallback": True, **diag, **extra}

    # Sin maestro/match o sin detalle → fallback
    if (pror_row is None) or (metodo in ("sin_datos", "sin_match")) or (detalle is None):
        return fallback({"razon": "sin_maestro_o_detalle"})

    # Detecta columnas id de relación
    col_id_maestro = _pick_col(pror_row.to_frame().T, ["idnumpon", "id", "prorrateo_id", "ID", "IdProrrateo"])
    col_id_detalle = _pick_col(detalle,            ["idnumpon", "prorrateo_id", "IdProrrateo", "id_prorrateo", "id"])

    if not col_id_maestro or not col_id_detalle:
        return fallback({"razon": "sin_cols_id", "col_id_maestro": col_id_maestro, "col_id_detalle": col_id_detalle})

    idnumpon = pror_row[col_id_maestro]

    # filtra detalle del prorrateo
    det = detalle.copy()
    det = det[det[col_id_detalle] == idnumpon]
    if det.empty:
        return fallback({"razon": "sin_detalle_filtrado", "idnumpon": idnumpon})

    # columnas del detalle
    col_cta   = _pick_col(det, ["dsctacon", "cuenta", "NUM_CTA", "num_cta"])
    col_depto = _pick_col(det, ["idnuevo", "NUMDEPTO", "numdepto", "departamento"])
    col_pct   = _pick_col(det, ["flporuni", "porcentaje", "porc", "factor"])
    if not col_cta or not col_pct:
        return fallback({"razon": "sin_cols_detalle", "idnumpon": idnumpon})

    # normaliza valores
    det["_cta"] = det[col_cta].astype(str).str.strip()
    det["_pct"] = pd.to_numeric(det[col_pct], errors="coerce").fillna(0.0)
    if col_depto:
        det["_depto"] = pd.to_numeric(det[col_depto], errors="coerce").astype("Int64")
    else:
        det["_depto"] = pd.Series([pd.NA] * len(det), index=det.index, dtype="Int64")

    partidas: list[Dict[str, Any]] = []

    # 1) DEBE: gasto (SUBTOTAL) prorrateado
    total_debe_gasto = 0.0
    for _, rdet in det.iterrows():
        monto = trunc8(float(rdet["_pct"] * subtotal))
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
        total_debe_gasto += monto

    # 2) DEBE: impuestos individuales
    # 2) impuestos individuales
    #   cta_imp1, cta_imp2, cta_imp3 = retenciones → HABER
    #   cta_imp4                     = impuesto normal → DEBE
    for monto, cta, es_ret in (
        (imp1, imp.get("CTA_IMP1"), True),
        (imp2, imp.get("CTA_IMP2"), True),
        (imp3, imp.get("CTA_IMP3"), True),
        (imp4, imp.get("CTA_IMP4"), False),
    ):
        monto_r = trunc8(round(float(monto or 0.0), 2))
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

    # 3) HABER: proveedor por el total del documento
    partidas.append({
        "NUM_CTA": cta_prov,
        "DEBE_HABER": "H",
        "MONTOMOV": trunc8(imp_total),
        "CONCEP_PO": concepto,
        "NUMDEPTO": 0, 
        "TIPCAMBIO": tcambio, 
        "CCOSTOS": 0, 
        "CGRUPOS": 0,
    })

    return partidas, metodo, {"fallback": False, "idnumpon": idnumpon,
                              "imp1": imp1, "imp2": imp2, "imp3": imp3, "imp4": imp4,
                              "subtotal": subtotal}