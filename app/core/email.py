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

# Optionally try fastapi-mail, but don't make it required
try:
    from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
    conf = ConnectionConfig(
        MAIL_USERNAME=settings.MAIL_USERNAME,
        MAIL_PASSWORD=settings.MAIL_PASSWORD,
        MAIL_FROM=settings.MAIL_FROM,
        MAIL_PORT=settings.MAIL_PORT,
        MAIL_SERVER=settings.MAIL_SERVER,
        MAIL_FROM_NAME=settings.MAIL_FROM_NAME,
        MAIL_STARTTLS=settings.MAIL_STARTTLS,
        MAIL_SSL_TLS=settings.MAIL_SSL_TLS,
        USE_CREDENTIALS=settings.USE_CREDENTIALS,
        VALIDATE_CERTS=settings.VALIDATE_CERTS
    )
    HAS_FASTAPI_MAIL = True
except Exception:
    HAS_FASTAPI_MAIL = False
    logger.warning("fastapi-mail not available, using smtplib only")


def _build_mime_message(to_email: str, subject: str, html_body: str) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.MAIL_FROM_NAME} <{settings.MAIL_FROM}>"
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html"))
    return msg


def send_email_smtp_starttls(to_email: str, subject: str, html_body: str):
    """Send email via SMTP STARTTLS on port 587"""
    msg = _build_mime_message(to_email, subject, html_body)
    logger.info(f"[smtplib-STARTTLS] Connecting to {settings.MAIL_SERVER}:587")
    with smtplib.SMTP(settings.MAIL_SERVER, 587, timeout=30) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(settings.MAIL_USERNAME, settings.MAIL_PASSWORD)
        server.sendmail(settings.MAIL_FROM, to_email, msg.as_string())
        logger.info(f"[smtplib-STARTTLS] Email sent to {to_email}")


def send_email_smtp_ssl(to_email: str, subject: str, html_body: str):
    """Send email via SMTP SSL on port 465 (fallback when 587 is blocked)"""
    msg = _build_mime_message(to_email, subject, html_body)
    context = ssl.create_default_context()
    logger.info(f"[smtplib-SSL] Connecting to {settings.MAIL_SERVER}:465")
    with smtplib.SMTP_SSL(settings.MAIL_SERVER, 465, timeout=30, context=context) as server:
        server.login(settings.MAIL_USERNAME, settings.MAIL_PASSWORD)
        server.sendmail(settings.MAIL_FROM, to_email, msg.as_string())
        logger.info(f"[smtplib-SSL] Email sent to {to_email}")


def send_email_smtp(to_email: str, subject: str, html_body: str):
    """Send email trying STARTTLS first, then SSL fallback"""
    # Attempt 1: STARTTLS on port 587
    try:
        send_email_smtp_starttls(to_email, subject, html_body)
        return
    except Exception as e:
        logger.warning(f"[smtplib] STARTTLS:587 failed for {to_email}: {e}")

    # Attempt 2: SSL on port 465
    try:
        send_email_smtp_ssl(to_email, subject, html_body)
        return
    except Exception as e2:
        logger.error(f"[smtplib] SSL:465 also failed for {to_email}: {e2}")
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
        <p style="color: #334155; font-size: 15px;">Votre code de vérification est :</p>
        <div style="text-align: center; margin: 24px 0;">
            <span style="display: inline-block; font-size: 32px; font-weight: bold; letter-spacing: 8px; color: #2563eb; background: #eff6ff; padding: 16px 32px; border-radius: 12px; border: 2px solid #bfdbfe;">{code}</span>
        </div>
        <p style="color: #64748b; font-size: 13px; text-align: center;">Ce code est valable pendant 30 minutes.<br>Si vous n'avez pas créé de compte, ignorez cet email.</p>
        </div>"""

    subject = "1111.tn - Vérification de votre email"

    # Try fastapi-mail first (async native)
    if HAS_FASTAPI_MAIL:
        try:
            logger.info(f"Sending verification email to {email} via fastapi-mail")
            message = MessageSchema(
                subject=subject,
                recipients=[email],
                body=html_body,
                subtype=MessageType.html
            )
            fm = FastMail(conf)
            await fm.send_message(message)
            logger.info(f"Verification email sent to {email} via fastapi-mail")
            return
        except Exception as e:
            logger.warning(f"fastapi-mail failed for {email}: {e}. Falling back to smtplib...")

    # Fallback: smtplib in thread pool (STARTTLS then SSL)
    try:
        await _send_email_in_thread(email, subject, html_body)
    except Exception as e2:
        logger.error(f"All email methods failed for {email}: {e2}")
        raise e2


async def send_reset_password_email(email: str, code: str):
    html_body = f"""<h2>Password Reset Request</h2>
        <p>Your 6-digit verification code is: <strong style="font-size: 24px; color: #8B5CF6;">{code}</strong></p>
        <p>This code will expire in 15 minutes.</p>
        <p>If you didn't request this, please ignore this email.</p>"""

    subject = "Password Reset - Verification Code"

    if HAS_FASTAPI_MAIL:
        try:
            message = MessageSchema(
                subject=subject,
                recipients=[email],
                body=html_body,
                subtype=MessageType.html
            )
            fm = FastMail(conf)
            await fm.send_message(message)
            return
        except Exception as e:
            logger.warning(f"fastapi-mail failed for reset email {email}: {e}")

    await _send_email_in_thread(email, subject, html_body)
