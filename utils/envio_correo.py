import smtplib
from email.message import EmailMessage
import os
from dotenv import load_dotenv
#from email_validator import validate_email, EmailNotValidError
from models.usuario_model import obtener_emails_usuarios, obtener_todos_usuarios
import requests
import json
import streamlit as st
# Carga las variables del archivo .env
load_dotenv()

## token= st.session_state["microsoft_token"]


def enviar_correo(destinatario, asunto, cuerpo_html, token, remitente="sysadmin@biotecsamexico.onmicrosoft.com"):
    #token = os.getenv("MICROSOFT_GRAPH_TOKEN")
    if not token:
        return False, "❌ No se encontró el token de Microsoft Graph."

    if isinstance(destinatario, list):
        to_list = [{"emailAddress": {"address": email}} for email in destinatario]
    else:
        to_list = [{"emailAddress": {"address": destinatario}}]


    url = f"https://graph.microsoft.com/v1.0/users/{remitente}/sendMail"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    mensaje = {
        "message": {
            "subject": asunto,
            "body": {
                "contentType": "HTML",
                "content": cuerpo_html
            },
            "toRecipients": to_list
        }
    }

    response = requests.post(url, headers=headers, data=json.dumps(mensaje))

    if response.status_code == 202:
        return True, "✅ Correo enviado correctamente."
    else:
        return False, f"❌ Error al enviar el correo: {response.status_code} - {response.text}"

def enviar_mail_graph(token, destinatario, asunto, cuerpo, remitente="sysadmin@biotecsamexico.onmicrosoft.com"):
    url = "https://graph.microsoft.com/v1.0/users/{}/sendMail".format(remitente)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    mensaje = {
        "message": {
            "subject": asunto,
            "body": {
                "contentType": "HTML",
                "content": cuerpo
            },
            "toRecipients": [
                {"emailAddress": {"address": destinatario}}
            ]
        }
    }

    response = requests.post(url, headers=headers, data=json.dumps(mensaje))
    return response.status_code, response.text


def enviar_correo_a_usuarios(asunto, cuerpo_html, archivo_bytes, nombre_archivo, mimetype):
    from_email = "notificaciones@tuapp.com"
    usuarios = obtener_todos_usuarios()  # debe devolver correos válidos
    token = st.session_state.get("microsoft_token")

    for u in usuarios:
        user = obtener_emails_usuarios(u)
        if not user or "email" not in user:
            continue
        enviar_correo(
            destinatario=user["email"],
            asunto=asunto,
            cuerpo_html=cuerpo_html,
            archivo_adjunto=(archivo_bytes, nombre_archivo, mimetype),
            token=token
        )