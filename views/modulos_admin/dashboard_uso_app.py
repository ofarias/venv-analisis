import streamlit as st
import pandas as pd
from datetime import date, timedelta
from database.conexion import obtener_conexion
from logs.logger import registrar_log


@st.cache_data(show_spinner=False, ttl=120)
def _cargar_actividad(fecha_ini: date, fecha_fin: date) -> pd.DataFrame:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT usuario, accion, detalle, creado_en
            FROM login_activity
            WHERE DATE(creado_en) BETWEEN %s AND %s
            ORDER BY creado_en
            """,
            (fecha_ini, fecha_fin),
        )
        rows = cur.fetchall() or []
    finally:
        conn.close()

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df["creado_en"] = pd.to_datetime(df["creado_en"])
    df["fecha"] = df["creado_en"].dt.date
    df["hora"] = df["creado_en"].dt.hour
    return df


def mostrar_dashboard_uso_app():
    registrar_log("admin", "Acceso a módulo", "📊 Uso de la app")
    st.title("📊 Uso de la App")

    hoy = date.today()
    col1, col2 = st.columns(2)
    fecha_ini = col1.date_input("Desde", value=hoy - timedelta(days=30), key="uso_app_fecha_ini")
    fecha_fin = col2.date_input("Hasta", value=hoy, key="uso_app_fecha_fin")

    if fecha_ini > fecha_fin:
        st.error("La fecha inicial no puede ser mayor que la final.")
        return

    df = _cargar_actividad(fecha_ini, fecha_fin)

    if df.empty:
        st.info("No hay actividad registrada en el rango seleccionado.")
        return

    with st.container(border=True):
        f1, f2 = st.columns(2)
        usuarios_opciones = sorted(df["usuario"].dropna().astype(str).unique().tolist())
        modulos_opciones = sorted(
            df.loc[df["accion"] == "Acceso a módulo", "detalle"].dropna().astype(str).unique().tolist()
        )
        with f1:
            usuarios_sel = st.multiselect("Usuario", usuarios_opciones, default=[], key="uso_app_usuarios")
        with f2:
            modulos_sel = st.multiselect("Módulo", modulos_opciones, default=[], key="uso_app_modulos")

    if usuarios_sel:
        df = df[df["usuario"].isin(usuarios_sel)]
    if modulos_sel:
        df = df[(df["accion"] == "Acceso a módulo") & (df["detalle"].isin(modulos_sel))]

    if df.empty:
        st.info("No hay actividad para los filtros seleccionados.")
        return

    usuarios_activos = df["usuario"].nunique()
    total_eventos = len(df)
    accesos_modulo = df[df["accion"] == "Acceso a módulo"]
    logins = df[
        df["accion"].str.contains("sesi", case=False, na=False)
        & ~df["accion"].str.contains("Cerrar", case=False, na=False)
    ]
    dias_con_actividad = df["fecha"].nunique()
    promedio_diario = total_eventos / dias_con_actividad if dias_con_actividad else 0

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Usuarios activos", f"{usuarios_activos:,}")
    k2.metric("Eventos totales", f"{total_eventos:,}")
    k3.metric("Accesos a módulos", f"{len(accesos_modulo):,}")
    k4.metric("Inicios de sesión", f"{len(logins):,}")
    k5.metric("Eventos / día", f"{promedio_diario:,.1f}")

    st.markdown("#### Actividad por día")
    por_dia = df.groupby("fecha").size().rename("eventos")
    st.line_chart(por_dia)

    t1, t2, t3, t4 = st.tabs(["Usuarios", "Módulos", "Acciones", "Actividad por hora"])

    with t1:
        por_usuario = (
            df.groupby("usuario").size().rename("eventos").reset_index()
            .sort_values("eventos", ascending=False)
        )
        st.bar_chart(por_usuario.set_index("usuario")["eventos"].head(20))
        st.dataframe(por_usuario, use_container_width=True, hide_index=True)

    with t2:
        if accesos_modulo.empty:
            st.info("Sin accesos a módulos en el rango seleccionado.")
        else:
            por_modulo = (
                accesos_modulo.groupby("detalle").size().rename("accesos").reset_index()
                .sort_values("accesos", ascending=False)
            )
            st.bar_chart(por_modulo.set_index("detalle")["accesos"].head(20))
            st.dataframe(por_modulo, use_container_width=True, hide_index=True)

    with t3:
        por_accion = (
            df.groupby("accion").size().rename("eventos").reset_index()
            .sort_values("eventos", ascending=False)
        )
        st.bar_chart(por_accion.set_index("accion")["eventos"])
        st.dataframe(por_accion, use_container_width=True, hide_index=True)

    with t4:
        por_hora = df.groupby("hora").size().reindex(range(24), fill_value=0).rename("eventos")
        st.bar_chart(por_hora)
