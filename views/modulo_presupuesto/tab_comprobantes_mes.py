import streamlit as st
import pandas as pd
from controllers.presupuesto_controller import get_comprobantes_por_mes
import plotly.express as px


def mostrar_tab_comprobantes_mes():
    username = st.session_state.get("username", "admin")
    df = get_comprobantes_por_mes(username)

    if df is None or df.empty:
        st.info("No se encontraron comprobantes registrados para tu usuario.")
        return

    # normalizar columnas
    df.columns = [c.strip().lower() for c in df.columns]
    if "fecha" in df.columns:
        df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    else:
        st.error("El resultado no contiene columna 'Fecha'.")
        return

    col_usuario = next((c for c in df.columns if c in ["usuario", "username", "registrado_por"]), "usuario")
    col_unidad = next((c for c in df.columns if c in ["unidad_negocio", "unidad", "unidad negocio"]), "unidad_negocio")

    # rangos base
    fecha_min, fecha_max = df["fecha"].min(), df["fecha"].max()
    hoy = pd.Timestamp.now()
    inicio_mes, fin_mes = hoy.replace(day=1), (hoy.replace(day=1) + pd.offsets.MonthEnd(1)).normalize()
    rango_defecto_ini, rango_defecto_fin = max(inicio_mes, fecha_min), min(fin_mes, fecha_max)

    # --- resumen global ---
    st.markdown("### 📊 Resumen general (sin filtros)")
    colg1, colg2 = st.columns(2)

    with colg1:
        st.markdown("**Totales por usuario (MXN / USD)**")
        st.bar_chart(df.groupby(col_usuario)[["monto_gasto_mnx", "monto_gasto_usd"]].sum())

    with colg2:
        st.markdown("**Totales por unidad de negocio (MXN / USD)**")
        st.bar_chart(df.groupby(col_unidad)[["monto_gasto_mnx", "monto_gasto_usd"]].sum())

    st.divider()

    # --- FILTROS ---
    st.markdown("### 🔎 Filtros de búsqueda")
    col1, col2, col3 = st.columns([1.2, 1.2, 2])

    usuarios = sorted(df[col_usuario].dropna().unique().tolist())
    unidades = sorted(df[col_unidad].dropna().unique().tolist())

    user_sel = col1.multiselect("Usuarios", usuarios, default=usuarios)
    uni_sel = col2.multiselect("Unidades de negocio", unidades, default=unidades)

    # rango de fechas totalmente libre
    rango_fechas = col3.date_input(
        "Rango de fechas",
        value=(df["fecha"].min().date(), df["fecha"].max().date()),
        key="rg_rango_fechas_libre",
    )

    # --- aplicar filtros ---
    df_filtrado = df[
        df[col_usuario].isin(user_sel)
        & df[col_unidad].isin(uni_sel)
        & (df["fecha"] >= pd.to_datetime(rango_fechas[0]))
        & (df["fecha"] <= pd.to_datetime(rango_fechas[1]))
    ]

    if df_filtrado.empty:
        st.warning("No hay registros con los filtros seleccionados.")
        return

    # --- GRÁFICAS FILTRADAS ---
    
    st.markdown("### 📈 Análisis gráfico (filtros aplicados)")
    colg3, colg4 = st.columns(2)

    # asegurar tipos numéricos
    for c in ["monto_gasto_mnx", "monto_gasto_usd"]:
        df_filtrado[c] = pd.to_numeric(df_filtrado[c], errors="coerce").fillna(0.0)

    # 1) sumas por usuario
    df_user = (
        df_filtrado
        .groupby(col_usuario, as_index=False)[["monto_gasto_mnx", "monto_gasto_usd"]]
        .sum()
        .sort_values("monto_gasto_mnx", ascending=False)
    )

    # 2) sumas por unidad
    df_uni = (
        df_filtrado
        .groupby(col_unidad, as_index=False)[["monto_gasto_mnx", "monto_gasto_usd"]]
        .sum()
        .sort_values("monto_gasto_mnx", ascending=False)
    )

    with colg3:
        st.markdown("**Monto total por usuario (MXN / USD)**")
        if not df_user.empty:
            fig_user = px.bar(
                df_user,
                x=col_usuario,
                y=["monto_gasto_mnx", "monto_gasto_usd"],
                barmode="group",
                title=None,
                labels={"value": "Monto", "variable": "Moneda", col_usuario: "Usuario"},
                text_auto=True,
            )
            fig_user.update_layout(yaxis_tickformat=",.2f")
            fig_user.update_traces(texttemplate="%{value:,.2f}", textposition="outside")
            st.plotly_chart(fig_user, use_container_width=True)
        else:
            st.info("Sin datos para usuarios.")

    with colg4:
        st.markdown("**Monto total por unidad de negocio (MXN / USD)**")
        if not df_uni.empty:
            fig_uni = px.bar(
                df_uni,
                x=col_unidad,
                y=["monto_gasto_mnx", "monto_gasto_usd"],
                barmode="group",
                title=None,
                labels={"value": "Monto", "variable": "Moneda", col_unidad: "Unidad de negocio"},
                text_auto=True,
            )
            fig_uni.update_layout(yaxis_tickformat=",.2f")
            fig_uni.update_traces(texttemplate="%{value:,.2f}", textposition="outside")
            st.plotly_chart(fig_uni, use_container_width=True)
        else:
            st.info("Sin datos para unidades.")


    
    ### Finaliza las graficas 

    st.divider()

    # --- TABLAS ---
    def formatear_numeros(df):
        return df.style.format({
            "monto_gasto_mnx": "${:,.2f}",
            "monto_gasto_usd": "${:,.2f}"
        })

    st.dataframe(formatear_numeros(df_filtrado), use_container_width=True, height=500)

    st.markdown("### 📊 Resumen numérico")
    resumen = (
        df_filtrado.groupby(col_unidad)[["monto_gasto_mnx", "monto_gasto_usd"]]
        .sum()
        .reset_index()
    )
    st.dataframe(formatear_numeros(resumen), use_container_width=True)