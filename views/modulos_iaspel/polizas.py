import altair as alt
import streamlit as st
import pandas as pd
from datetime import date
from io import BytesIO
from models.conta_model import *

def pantalla_polizas():
    st.title("polizas coi")

    # ejercicio por defecto = año actual % 100
    eje_default = date.today().year % 100
    c1, c2, c3 = st.columns([1,1,2])
    eje = c1.number_input("ejercicio (dos dígitos)", min_value=0, max_value=99, value=eje_default, step=1)
    opciones = obtener_opciones(eje)

    tipos = c2.multiselect("tipo", options=opciones["tipos"], default=opciones["tipos"])
    periodos = c3.multiselect("periodo", options=opciones["periodos"], default=opciones["periodos"])

    c4, c5, c6 = st.columns([1,1,1])
    cuenta_pref = c4.text_input("cuenta inicia con", value="")
    concepto_like = c5.text_input("concepto contiene", value="")
    rango = c6.date_input("rango de fechas", value=[], format="YYYY-MM-DD")

    fecha_desde = rango[0] if isinstance(rango, list) and len(rango)==2 else None
    fecha_hasta = rango[1] if isinstance(rango, list) and len(rango)==2 else None

    filtros = {
        "tipos": tipos,
        "periodos": periodos,
        "cuenta_pref": cuenta_pref or None,
        "concepto_like": concepto_like or None,
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,
    }

    # paginación
    op = st.selectbox("registros por página", [50, 100, 300, 1000, "Todos"], index=2)
    if op == "Todos":
        page_size, page, offset = None, 1, 0
    else:
        page_size = int(op)
        page = st.number_input("página", min_value=1, value=1, step=1)
        offset = (page - 1) * page_size

    total = contar_polizas(eje, filtros)
    st.caption(f"total registros: {total:,}")

    data = obtener_polizas(eje, filtros, limit=page_size, offset=offset)

    if not data:
        st.warning("sin resultados con los filtros actuales")
        return

    df = pd.DataFrame(data)

    # kpis
    colk1, colk2, colk3 = st.columns(3)
    cargos = float(df.get("CARGO", pd.Series([0])).sum())
    abonos = float(df.get("ABONO", pd.Series([0])).sum())
    colk1.metric("cargos", f"{cargos:,.2f}")
    colk2.metric("abonos", f"{abonos:,.2f}")
    colk3.metric("diferencia", f"{(cargos - abonos):,.2f}")

    st.dataframe(df, use_container_width=True)

    # botón de descarga
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name=f"POLIZAS{eje:02d}")
    st.download_button(
        "descargar excel",
        data=buf.getvalue(),
        file_name=f"polizas_{eje:02d}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    # resumen y gráficas
    resumen = resumen_por_periodo(eje, filtros)
    if resumen:
        dfr = pd.DataFrame(resumen)
        dfr = dfr.sort_values("PERIODO")
        st.subheader("cargos y abonos por periodo")

        # altair simple
        import altair as alt
        dfrm = dfr.melt(id_vars=["PERIODO"], value_vars=["CARGOS","ABONOS"], var_name="tipo", value_name="monto")
        chart = alt.Chart(dfrm).mark_bar().encode(
            x=alt.X("PERIODO:O", title="periodo"),
            y=alt.Y("monto:Q", title="monto"),
            color=alt.Color("tipo:N")
        ).properties(height=320, width="container")
        st.altair_chart(chart, use_container_width=True)

        # top cuentas por monto (si existe CUENTA)
        if "CUENTA" in df.columns and "CARGO" in df.columns and "ABONO" in df.columns:
            st.subheader("top 15 cuentas por monto absoluto")
            top = (
                df.assign(MONTO=(df["CARGO"].fillna(0) - df["ABONO"].fillna(0)).abs())
                  .groupby("CUENTA", as_index=False)["MONTO"].sum()
                  .sort_values("MONTO", ascending=False)
                  .head(15)
            )
            chart2 = alt.Chart(top).mark_bar().encode(
                x=alt.X("MONTO:Q"),
                y=alt.Y("CUENTA:N", sort="-x")
            ).properties(height=400, width="container")
            st.altair_chart(chart2, use_container_width=True)


        # --- por tipo ---
    rt = resumen_por_tipo(eje, filtros)
    if rt:
        dft = pd.DataFrame(rt)
        dft_m = dft.melt(id_vars=["TIPO_POLI"], value_vars=["CARGOS","ABONOS"],
                        var_name="mov", value_name="monto")
        st.subheader("Cargos y abonos por TIPO de póliza")
        chart_t = alt.Chart(dft_m).mark_bar().encode(
            x=alt.X("TIPO_POLI:N", title="Tipo"),
            y=alt.Y("monto:Q", title="Monto"),
            color="mov:N"
        ).properties(height=320)
        st.altair_chart(chart_t, use_container_width=True)

    # --- por origen ---
    ro = resumen_por_origen(eje, filtros)
    if ro:
        dfo = pd.DataFrame(ro)
        dfo_m = dfo.melt(id_vars=["ORIGEN"], value_vars=["CARGOS","ABONOS"],
                        var_name="mov", value_name="monto")
        st.subheader("Cargos y abonos por ORIGEN")
        chart_o = alt.Chart(dfo_m).mark_bar().encode(
            x=alt.X("ORIGEN:N", title="Origen"),
            y=alt.Y("monto:Q", title="Monto"),
            color="mov:N"
        ).properties(height=320)
        st.altair_chart(chart_o, use_container_width=True)
        
    rc = resumen_conteo_por_origen(eje, filtros)
    if rc:
        dfo = pd.DataFrame(rc)  # columnas: ORIGEN, NUM_POLIZAS
        st.subheader("Número de pólizas por ORIGEN")

        # controles
        altura = st.slider("Alto de la gráfica", 200, 800, 400, 50)
        grosor = st.slider("Grosor de barra", 10, 80, 30, 2)

        base = alt.Chart(dfo).encode(
            x=alt.X("ORIGEN:N", title="Origen"),
            y=alt.Y("NUM_POLIZAS:Q", title="# de pólizas")
        )

        barras = base.mark_bar(size=grosor).properties(height=altura)

        # ← Clave: calculamos la mitad del valor para centrar el texto dentro de la barra
        etiquetas = base.transform_calculate(
            mid="datum.NUM_POLIZAS / 2"
        ).mark_text(
            align="center",
            baseline="middle",   # centrado vertical respecto a y=mid
            color="white",
            fontSize=12
        ).encode(
            y="mid:Q",
            text="NUM_POLIZAS:Q"
        )

        chart = (barras + etiquetas).properties(width="container")
        st.altair_chart(chart, use_container_width=True)