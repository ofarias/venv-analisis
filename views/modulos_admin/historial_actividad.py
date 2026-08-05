
import streamlit as st
import pandas as pd
from database.conexion import obtener_conexion
from logs.logger import registrar_log


def _obtener_usuarios_distintos() -> list[str]:
    conn = obtener_conexion()
    try:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT usuario FROM login_activity ORDER BY usuario")
        return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


def _obtener_registros(usuario_filtro: str | None, fecha_filtro) -> pd.DataFrame:
    conn = obtener_conexion()
    try:
        cur = conn.cursor(dictionary=True)
        sql = "SELECT usuario, accion, detalle, creado_en FROM login_activity WHERE 1 = 1"
        params: list = []
        if usuario_filtro and usuario_filtro != "Todos":
            sql += " AND usuario = %s"
            params.append(usuario_filtro)
        if fecha_filtro:
            sql += " AND DATE(creado_en) = %s"
            params.append(fecha_filtro)
        sql += " ORDER BY creado_en DESC"
        cur.execute(sql, tuple(params))
        rows = cur.fetchall() or []
    finally:
        conn.close()

    if not rows:
        return pd.DataFrame(columns=["Fecha", "Usuario", "Acción", "Detalle"])

    df = pd.DataFrame(rows)
    df["creado_en"] = df["creado_en"].astype(str)
    return df.rename(columns={
        "creado_en": "Fecha", "usuario": "Usuario", "accion": "Acción", "detalle": "Detalle",
    })


def mostrar_historial():
    registrar_log("admin", "Acceso a módulo", "📄 Historial de actividad")
    st.title("📄 Historial de Actividad de Usuarios")

    # Filtros
    st.subheader("🔍 Filtros")
    col1, col2 = st.columns(2)
    usuarios = _obtener_usuarios_distintos()
    usuario_filtro = col1.selectbox("Usuario", ["Todos"] + usuarios)
    fecha_filtro = col2.date_input("Fecha (opcional)", value=None)

    df_logs = _obtener_registros(usuario_filtro, fecha_filtro)

    st.subheader("📋 Resultados")
    if df_logs.empty:
        st.info("Aún no hay registros en el historial.")
        return

    st.dataframe(df_logs, use_container_width=True, hide_index=True)

    # Descargar como Excel
    excel_path = "logs/historial_actividad.xlsx"
    df_logs.to_excel(excel_path, index=False)

    with open(excel_path, "rb") as f:
        st.download_button(
            label="📥 Descargar historial en Excel",
            data=f,
            file_name="historial_actividad.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
