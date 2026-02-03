
import streamlit as st
import pandas as pd
from pathlib import Path
from logs.logger import registrar_log
from constants import MODULOS_ADMIN, RUTA_LOG_USUARIOS
from settings import DB_CONFIG, NOMBRE_SISTEMA



def mostrar_historial():
    usuario = st.session_state.get("usuario", {}).get("username", "desconocido")
    registrar_log("admin", "Acceso a módulo", "📄 Historial de actividad")
    st.title("📄 Historial de Actividad de Usuarios")

    log_path = Path("logs/log_usuarios.txt")
    if not log_path.exists():
        st.info("Aún no hay registros en el historial.")
        return

    with open(log_path, "r") as f:
        lines = f.readlines()

    registros = []
    for linea in lines:
        if "->" in linea and ":" in linea:
            try:
                fecha, resto = linea.split("] ")
                fecha = fecha.strip("[")
                usuario_accion, modulo = resto.split(":")
                usuario, accion = usuario_accion.split("->")
                registros.append({
                    "Fecha": fecha,
                    "Usuario": usuario.strip(),
                    "Acción": accion.strip(),
                    "Detalle": modulo.strip()
                })
            except Exception:
                continue

    df_logs = pd.DataFrame(registros)

    # Filtros
    st.subheader("🔍 Filtros")
    col1, col2 = st.columns(2)
    usuarios = df_logs["Usuario"].unique().tolist()
    usuario_filtro = col1.selectbox("Usuario", ["Todos"] + usuarios)
    fecha_filtro = col2.date_input("Fecha (opcional)", value=None)

    if usuario_filtro != "Todos":
        df_logs = df_logs[df_logs["Usuario"] == usuario_filtro]

    if fecha_filtro:
        df_logs = df_logs[df_logs["Fecha"].str.startswith(str(fecha_filtro))]

    st.subheader("📋 Resultados")
    st.dataframe(df_logs)

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
