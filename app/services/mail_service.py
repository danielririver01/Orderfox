"""
mail_service.py — Envío de correos vía SMTP (Gmail).
Reemplaza el envío que antes hacía n8n (Sorpresa Velzia + recordatorios).
"""
import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from flask import current_app


def send_email(to: str, subject: str, html_body: str, text_body: str | None = None, sender_name: str = 'Velzia') -> bool:
    """
    Envía un correo HTML usando las variables MAIL_* del config.
    Devuelve True si se envió, False si faltó configuración o falló el envío.
    """
    cfg = current_app.config
    username = cfg.get('MAIL_USERNAME')
    password = cfg.get('MAIL_PASSWORD')
    server = cfg.get('MAIL_SERVER') or 'smtp.gmail.com'
    port = int(cfg.get('MAIL_PORT') or 587)
    use_tls = bool(cfg.get('MAIL_USE_TLS', True))
    sender = cfg.get('MAIL_DEFAULT_SENDER') or username

    if not username or not password:
        current_app.logger.warning(
            'MAIL_USERNAME/MAIL_PASSWORD no configurados; no se envió email a %s', to
        )
        return False

    if not text_body:
        text_body = 'Velzia\n\nEste correo contiene contenido HTML. Si no puedes verlo, visita https://www.velzia.shop'

    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = formataddr((sender_name, sender))
    msg['To'] = to
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype='html')

    try:
        with smtplib.SMTP(server, port, timeout=15) as smtp:
            if use_tls:
                smtp.starttls()
            smtp.login(username, password)
            smtp.send_message(msg)
        current_app.logger.info('Email enviado a %s: %s', to, subject)
        return True
    except Exception as e:
        current_app.logger.error('Error enviando email a %s: %s', to, e)
        return False
