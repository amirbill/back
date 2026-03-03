from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
from app.core.config import settings
from pathlib import Path
import logging
import smtplib
import asyncio
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

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

def send_email_smtp(to_email: str, subject: str, html_body: str):
    """Fallback: send email using smtplib directly"""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.MAIL_FROM_NAME} <{settings.MAIL_FROM}>"
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html"))

    logger.info(f"[smtplib] Connecting to {settings.MAIL_SERVER}:{settings.MAIL_PORT}")
    with smtplib.SMTP(settings.MAIL_SERVER, settings.MAIL_PORT, timeout=10) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        logger.info(f"[smtplib] Logging in as {settings.MAIL_USERNAME}")
        server.login(settings.MAIL_USERNAME, settings.MAIL_PASSWORD)
        server.sendmail(settings.MAIL_FROM, to_email, msg.as_string())
        logger.info(f"[smtplib] Email sent successfully to {to_email}")

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

    # Try fastapi-mail first, fall back to smtplib
    try:
        logger.info(f"Sending verification email to {email} via fastapi-mail")
        message = MessageSchema(
            subject="1111.tn - Vérification de votre email",
            recipients=[email],
            body=html_body,
            subtype=MessageType.html
        )
        fm = FastMail(conf)
        await fm.send_message(message)
        logger.info(f"Verification email sent successfully to {email} via fastapi-mail")
    except Exception as e:
        logger.warning(f"fastapi-mail failed for {email}: {e}. Trying smtplib fallback...")
        try:
            send_email_smtp(email, "1111.tn - Vérification de votre email", html_body)
        except Exception as e2:
            logger.error(f"smtplib also failed for {email}: {e2}")
            raise e2

async def send_reset_password_email(email: str, code: str):
    message = MessageSchema(
        subject="Password Reset - Verification Code",
        recipients=[email],
        body=f"""\u003ch2\u003ePassword Reset Request\u003c/h2\u003e
        \u003cp\u003eYour 6-digit verification code is: \u003cstrong style="font-size: 24px; color: #8B5CF6;"\u003e{code}\u003c/strong\u003e\u003c/p\u003e
        \u003cp\u003eThis code will expire in 15 minutes.\u003c/p\u003e
        \u003cp\u003eIf you didn't request this, please ignore this email.\u003c/p\u003e""",
        subtype=MessageType.html
    )
    fm = FastMail(conf)
    await fm.send_message(message)
