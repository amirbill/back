from app.core.config import settings
import logging
import smtplib
import ssl
import asyncio
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# Thread pool for running sync SMTP in background without blocking the event loop
_email_executor = ThreadPoolExecutor(max_workers=2)


def _get_ssl_context():
    """Get SSL context, optionally disabling cert validation based on settings"""
    context = ssl.create_default_context()
    if not settings.VALIDATE_CERTS:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        logger.debug("SSL certificate validation disabled")
    return context


def _build_mime_message(to_email: str, subject: str, html_body: str) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.MAIL_FROM_NAME} <{settings.MAIL_FROM}>"
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html"))
    return msg


def send_email_smtp_ssl(to_email: str, subject: str, html_body: str):
    """Send email via SMTP_SSL (port 465)"""
    msg = _build_mime_message(to_email, subject, html_body)
    context = _get_ssl_context()
    port = settings.MAIL_PORT if settings.MAIL_SSL_TLS else 465
    logger.info(f"[smtplib-SSL] Connecting to {settings.MAIL_SERVER}:{port} (validate_certs={settings.VALIDATE_CERTS})")
    with smtplib.SMTP_SSL(settings.MAIL_SERVER, port, timeout=30, context=context) as server:
        server.login(settings.MAIL_USERNAME, settings.MAIL_PASSWORD)
        server.sendmail(settings.MAIL_FROM, to_email, msg.as_string())
        logger.info(f"[smtplib-SSL] Email sent to {to_email}")


def send_email_smtp_starttls(to_email: str, subject: str, html_body: str):
    """Send email via SMTP STARTTLS (port 587)"""
    msg = _build_mime_message(to_email, subject, html_body)
    context = _get_ssl_context()
    port = settings.MAIL_PORT if settings.MAIL_STARTTLS else 587
    logger.info(f"[smtplib-STARTTLS] Connecting to {settings.MAIL_SERVER}:{port}")
    with smtplib.SMTP(settings.MAIL_SERVER, port, timeout=30) as server:
        server.ehlo()
        server.starttls(context=context)
        server.ehlo()
        server.login(settings.MAIL_USERNAME, settings.MAIL_PASSWORD)
        server.sendmail(settings.MAIL_FROM, to_email, msg.as_string())
        logger.info(f"[smtplib-STARTTLS] Email sent to {to_email}")


def send_email_smtp(to_email: str, subject: str, html_body: str):
    """Send email using the configured method (SSL or STARTTLS), with fallback"""
    if settings.MAIL_SSL_TLS:
        try:
            send_email_smtp_ssl(to_email, subject, html_body)
            return
        except Exception as e:
            logger.warning(f"[smtplib] SSL:{settings.MAIL_PORT} failed: {e}. Trying STARTTLS...")
        try:
            send_email_smtp_starttls(to_email, subject, html_body)
            return
        except Exception as e2:
            logger.error(f"[smtplib] STARTTLS also failed: {e2}")
            raise e2
    else:
        try:
            send_email_smtp_starttls(to_email, subject, html_body)
            return
        except Exception as e:
            logger.warning(f"[smtplib] STARTTLS:{settings.MAIL_PORT} failed: {e}. Trying SSL...")
        try:
            send_email_smtp_ssl(to_email, subject, html_body)
            return
        except Exception as e2:
            logger.error(f"[smtplib] SSL also failed: {e2}")
            raise e2


async def _send_email_in_thread(to_email: str, subject: str, html_body: str):
    """Run synchronous SMTP send in a thread pool so it doesn't block the event loop"""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(_email_executor, send_email_smtp, to_email, subject, html_body)


async def send_verification_email(email: str, code: str):
    html_body = f"""<div style="font-family: Arial, sans-serif; max-width: 480px; margin: 0 auto; padding: 32px; background: #f8fafc; border-radius: 16px;">
        <div style="text-align: center; margin-bottom: 24px;">
            <h2 style="color: #1e40af; margin: 0;">Bienvenue sur 1111.tn</h2>
        </div>
        <p style="color: #334155; font-size: 15px;">Votre code de v\u00e9rification est :</p>
        <div style="text-align: center; margin: 24px 0;">
            <span style="display: inline-block; font-size: 32px; font-weight: bold; letter-spacing: 8px; color: #2563eb; background: #eff6ff; padding: 16px 32px; border-radius: 12px; border: 2px solid #bfdbfe;">{code}</span>
        </div>
        <p style="color: #64748b; font-size: 13px; text-align: center;">Ce code est valable pendant 30 minutes.<br>Si vous n'avez pas cr\u00e9\u00e9 de compte, ignorez cet email.</p>
        </div>"""

    subject = "1111.tn - V\u00e9rification de votre email"
    await _send_email_in_thread(email, subject, html_body)


async def send_reset_password_email(email: str, code: str):
    html_body = f"""<h2>Password Reset Request</h2>
        <p>Your 6-digit verification code is: <strong style="font-size: 24px; color: #8B5CF6;">{code}</strong></p>
        <p>This code will expire in 15 minutes.</p>
        <p>If you didn't request this, please ignore this email.</p>"""

    subject = "Password Reset - Verification Code"
    await _send_email_in_thread(email, subject, html_body)
