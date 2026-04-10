#login_view.py

from models.usuario_model import obtener_usuario_y_roles
import os
import json
import base64
import streamlit as st
from controllers.auth_controller import handle_redirect, get_login_url
from logs.logger import registrar_log
from settings import LOGO_PATH, NOMBRE_SISTEMA
from PIL import Image
from models.politicas_model import obtener_politicas_pendientes_usuario


def _encode_state(data: dict) -> str:
    """Serializa un dict como base64 para pasarlo en el state de OAuth."""
    raw = json.dumps(data, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _decode_state(state_str: str) -> dict:
    """Recupera el dict del state base64 que regresa Microsoft."""
    try:
        pad = "=" * (-len(state_str) % 4)
        raw = base64.urlsafe_b64decode(state_str + pad)
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {}

def mostrar_login():
    
    # Logo y título igual que antes
    if os.path.exists(LOGO_PATH):
        imagen = Image.open(LOGO_PATH)
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.image(imagen, width=800)
            st.markdown(f"<h2 style='text-align: center; color: #2E86C1'>{NOMBRE_SISTEMA}</h2>", unsafe_allow_html=True)
    else:
        st.title("❌ No se encontró el logo")
        st.caption(f"Ruta buscada: {LOGO_PATH}")    
    ## nuevo codigo para autorizaciones
    query_params = st.query_params

    # --- Recuperar deeplink desde state que regresa Microsoft ---
    # (sobrevive el redirect aunque el session_state se haya perdido)
    state_raw = (query_params.get("state") or "").strip()
    if state_raw and not st.session_state.get("usuario"):
        state_data = _decode_state(state_raw)
        if state_data.get("sg_id") and state_data.get("t"):
            st.session_state["deeplink_params"] = {
                "sg_id": str(state_data["sg_id"]),
                "action": str(state_data.get("action") or ""),
                "t": str(state_data["t"]),
            }

    # guardar deeplink original antes de ir a Microsoft
    if not st.session_state.get("usuario"):
        sg_id = (query_params.get("sg_id") or "").strip()
        action = (query_params.get("action") or "").strip()
        token = (query_params.get("t") or "").strip()

        if sg_id and token:
            st.session_state["deeplink_params"] = {
                "sg_id": sg_id,
                "action": action,
                "t": token,
            }

    ## finaliza el codigo para autorizaciones
    # --- Paso 1: detectar si se recibió código de Microsoft ---
    auth_code = query_params.get("code")
    
    if auth_code and not st.session_state.get("usuario"):
        user_data_from_microsoft = handle_redirect(auth_code)
        ## st.write("Datos Microsoft:", user_data_from_microsoft)
        if user_data_from_microsoft:
            username = user_data_from_microsoft.get('preferred_username')
            nombre = user_data_from_microsoft.get('name')
            access_token = user_data_from_microsoft.get('access_token')  # <-- ⬅️ extrae el token
            st.warning(f"Correo recibido desde Microsoft: {username}")
            usuario_db = obtener_usuario_y_roles(username)
            
            if usuario_db:
                # Si está registrado en tu BD
                st.session_state["usuario"] = {
                    "id": usuario_db["id"],
                    "username": usuario_db["username"],
                    "nombre": usuario_db["nombre"],
                    "email": username,
                    "roles": usuario_db["roles"] or [] 
                }
                st.session_state["roles"] = usuario_db["roles"] or []
                st.session_state["username"] = usuario_db["username"]
                st.session_state["microsoft_token"] = access_token
                
                ### Para Conrtrol de politicas 
                username = usuario_db["username"]
                pendientes = obtener_politicas_pendientes_usuario(username)

                st.session_state["avisos_politicas"] = pendientes  # guardar para mostrar al cargar

                registrar_log(usuario_db["username"], "Inicio de sesión con Microsoft", "-")

                ### codigo para autorizaciones
                deeplink = st.session_state.get("deeplink_params") or {}
                if deeplink.get("sg_id") and deeplink.get("t"):
                    st.session_state["modulo_forzado"] = "solicitudesConta"
                ## finaliza codigo para autorizaciones
                
                st.query_params.clear()
                st.rerun()
            else:
                st.error(f"⛔ El usuario {username} no está registrado o está inactivo.")
                st.stop()
        else:
            st.error("❌ No se pudo autenticar con Microsoft.")
            st.stop()

    # --- Paso 2: si no está autenticado, muestra botón de inicio ---
    if "usuario" not in st.session_state or st.session_state["usuario"] is None:
        st.title("🔐 Inicia sesión")

        # Si hay deeplink pendiente, lo codificamos en el state de OAuth
        # para que Microsoft lo regrese intacto en la URL de redirect
        deeplink = st.session_state.get("deeplink_params") or {}
        if deeplink.get("sg_id") and deeplink.get("t"):
            oauth_state = _encode_state(deeplink)
            login_url = get_login_url(state=oauth_state)
        else:
            login_url = get_login_url()

        st.link_button("Entrar con Microsoft", login_url)
        st.stop()
    else:
        st.rerun()

    # Aquí continúa la app si ya está autenticado   