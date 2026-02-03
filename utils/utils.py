
import streamlit as st
from logs.logger import registrar_log


def registrar_acceso_modulo(nombre_modulo: str):
    usuario = st.session_state.get("usuario", {}).get("username", "desconocido")
    registrar_log(usuario, "Acceso a módulo", nombre_modulo)


def colorear_estatus(estatus):
    colores = {
        "Activo": "🟢",
        "Suspendido": "🟡",
        "Baja": "🔴"
    }
    return f"{colores.get(estatus, '⚪')} {estatus}"

