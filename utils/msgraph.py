from msal import ConfidentialClientApplication
import requests


def obtener_archivos_onedrive(access_token):
    url = "https://graph.microsoft.com/v1.0/me/drive/root/children"
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json().get("value", [])
    else:
        return []
    
def obtener_contenido_carpeta_onedrive(token, folder_id="root"):
    """Devuelve una lista de archivos y carpetas en una carpeta de OneDrive."""
    headers = {
        "Authorization": f"Bearer {token}"
    }

    url = f"https://graph.microsoft.com/v1.0/me/drive/items/{folder_id}/children"

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data.get("value", [])
    except requests.RequestException as e:
        print(f"❌ Error al obtener contenido de OneDrive: {e}")
        return []
    