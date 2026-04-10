# controllers/auth_controller.py

import streamlit as st
import msal

# --- Carga configuración desde secrets.toml ---
config = st.secrets["msal"]

CLIENT_ID = config["client_id"]
CLIENT_SECRET = config["client_secret"]
REDIRECT_URI = config["redirect_uri"]
AUTHORITY = config.get("authority", "https://login.microsoftonline.com/common")
SCOPES = config.get("scopes", ["User.Read"])

def _get_msal_app():
    return msal.ConfidentialClientApplication(
        client_id=CLIENT_ID,
        client_credential=CLIENT_SECRET,
        authority=AUTHORITY
    )

def get_login_url(state: str = None):
    """Genera y retorna la URL de autenticación como string.

    state: string opcional que Microsoft regresa intacto en el redirect
           (?code=...&state=...), útil para preservar deeplink params.
    """
    msal_app = _get_msal_app()
    kwargs = dict(scopes=SCOPES, redirect_uri=REDIRECT_URI)
    if state:
        kwargs["state"] = state
    auth_request_url = msal_app.get_authorization_request_url(**kwargs)
    return auth_request_url  # <-- es string, no dict

def handle_redirect(auth_code):
    """Intercambia el código de autorización por un token y devuelve también el access_token."""
    msal_app = _get_msal_app()
    try:
        token_response = msal_app.acquire_token_by_authorization_code(
            code=auth_code,
            scopes=SCOPES,
            redirect_uri=REDIRECT_URI
        )

        if "access_token" not in token_response:
            st.error("❌ No se pudo obtener access_token.")
            return None

        # Devuelve tanto los datos del usuario como el access_token
        return {
            "access_token": token_response["access_token"],
            "preferred_username": token_response["id_token_claims"].get("preferred_username"),
            "name": token_response["id_token_claims"].get("name")
        }
    except Exception as e:
        st.error(f"❌ Error al adquirir el token: {e}")
        return None