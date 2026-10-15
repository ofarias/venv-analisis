# controllers/auth_controller.py

import streamlit as st
import msal

# --- Carga configuración desde secrets.toml ---
config = st.secrets["msal"]

CLIENT_ID = config["client_id"]
CLIENT_SECRET = config["client_secret"]
DEFAULT_REDIRECT_URI = config["redirect_uri"]
REDIRECT_URIS = config.get("redirect_uris", [DEFAULT_REDIRECT_URI])
AUTHORITY = config.get("authority", "https://login.microsoftonline.com/common")
SCOPES = config.get("scopes", ["User.Read"])

def _get_redirect_uri() -> str:
    """Elige, entre las redirect_uris registradas en Azure AD, la que
    coincide con el host por el que entró el usuario (p.ej. onecore.biotecsa.com
    u otro dominio registrado para acceso en LAN), para que Microsoft regrese
    al mismo lugar en vez de siempre a DEFAULT_REDIRECT_URI."""
    try:
        host = (st.context.headers.get("Host") or "").strip().lower()
    except Exception:
        host = ""
    if not host:
        return DEFAULT_REDIRECT_URI
    for uri in REDIRECT_URIS:
        netloc = uri.split("://", 1)[-1].lower()
        if netloc == host:
            return uri
    return DEFAULT_REDIRECT_URI

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
    kwargs = dict(scopes=SCOPES, redirect_uri=_get_redirect_uri())
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
            redirect_uri=_get_redirect_uri()
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