#utils/envio_correo.py

import smtplib
from email.message import EmailMessage
from email.mime.text import MIMEText
import os
from dotenv import load_dotenv
#from email_validator import validate_email, EmailNotValidError
from models.usuario_model import obtener_emails_usuarios, obtener_todos_usuarios
import requests
import json
import streamlit as st
# Carga las variables del archivo .env
load_dotenv()


def enviar_correo_sistema(*, destinatario, asunto: str, cuerpo_html: str) -> tuple[bool, str]:
    """Envía por SMTP con la cuenta de sistema (SMTP_* en secrets.toml) en
    vez de Microsoft Graph — para flujos sin sesión iniciada, como las
    acciones ejecutadas desde un link de correo firmado (ver
    utils/deeplink_tokens.py), donde no hay token de usuario disponible."""
    try:
        smtp_host = str(st.secrets.get("SMTP_HOST", "")).strip()
        smtp_port = int(st.secrets.get("SMTP_PORT", 587))
        smtp_user = str(st.secrets.get("SMTP_USER", "")).strip()
        smtp_pass = str(st.secrets.get("SMTP_PASS", "")).strip()
        smtp_from = str(st.secrets.get("SMTP_FROM", smtp_user)).strip()

        if not smtp_host or not smtp_user or not smtp_pass or not smtp_from:
            return False, "faltan credenciales SMTP en secrets.toml"

        destinatarios = destinatario if isinstance(destinatario, list) else [destinatario]
        destinatarios = [str(d).strip() for d in destinatarios if str(d or "").strip()]
        if not destinatarios:
            return False, "sin destinatario"

        msg = MIMEText(cuerpo_html, "html", "utf-8")
        msg["Subject"] = asunto
        msg["From"] = smtp_from
        msg["To"] = ", ".join(destinatarios)

        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_from, destinatarios, msg.as_string())

        return True, "correo enviado"

    except Exception as e:
        return False, str(e)

## token= st.session_state["microsoft_token"]

def enviar_correo(destinatario, asunto, cuerpo_html, token, remitente):
    if not token:
        return False, "❌ No se encontró el token de Microsoft Graph."

    if isinstance(destinatario, list):
        to_list = [{"emailAddress": {"address": str(email).strip()}} for email in destinatario if str(email).strip()]
    else:
        to_list = [{"emailAddress": {"address": str(destinatario).strip()}}]

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

    debug = {
        "url": url,
        "remitente": remitente,
        "destinatarios": to_list,
        "status_code": response.status_code,
        "response_text": response.text,
    }

    if response.status_code == 202:
        return True, f"✅ Correo enviado correctamente. DEBUG: {debug}"
    else:
        return False, f"❌ Error al enviar el correo. DEBUG: {debug}"
    
def enviar_correo_original(destinatario, asunto, cuerpo_html, token, remitente="sysadmin@biotecsamexico.onmicrosoft.com"):
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