from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FastAPI-Mail configuration (native async via aiosmtplib)
# ---------------------------------------------------------------------------

mail_conf = ConnectionConfig(
    MAIL_USERNAME=settings.MAIL_USERNAME,
    MAIL_PASSWORD=settings.MAIL_PASSWORD,
    MAIL_FROM=settings.MAIL_FROM,
    MAIL_PORT=settings.MAIL_PORT,
    MAIL_SERVER=settings.MAIL_SERVER,
    MAIL_FROM_NAME=settings.MAIL_FROM_NAME,
    MAIL_STARTTLS=settings.MAIL_STARTTLS,
    MAIL_SSL_TLS=settings.MAIL_SSL_TLS,
    USE_CREDENTIALS=settings.USE_CREDENTIALS,
    VALIDATE_CERTS=settings.VALIDATE_CERTS,
)

fm = FastMail(mail_conf)


async def _send_html_email(to_email: str, subject: str, html_body: str):
    """Send an HTML email using FastAPI-Mail (async, production-ready)."""
    message = MessageSchema(
        subject=subject,
        recipients=[to_email],
        body=html_body,
        subtype=MessageType.html,
    )
    print(f"[EMAIL] Sending '{subject}' to {to_email} via {settings.MAIL_SERVER}:{settings.MAIL_PORT}")
    try:
        await fm.send_message(message)
        print(f"[EMAIL] Successfully sent to {to_email}")
        logger.info(f"Email sent to {to_email} (subject: {subject})")
    except Exception as e:
        print(f"[EMAIL] FAILED to send to {to_email}: {type(e).__name__}: {e}")
        logger.error(f"Failed to send email to {to_email}: {type(e).__name__}: {e}")
        raise


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
    await _send_html_email(email, subject, html_body)


async def send_reset_password_email(email: str, code: str):
    html_body = f"""<h2>Password Reset Request</h2>
        <p>Your 6-digit verification code is: <strong style="font-size: 24px; color: #8B5CF6;">{code}</strong></p>
        <p>This code will expire in 15 minutes.</p>
        <p>If you didn't request this, please ignore this email.</p>"""

    subject = "Password Reset - Verification Code"
    await _send_html_email(email, subject, html_body)
