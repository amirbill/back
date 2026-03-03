from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
from app.core.config import settings
from pathlib import Path
import logging

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

async def send_verification_email(email: str, code: str):
    try:
        logger.info(f"Sending verification email to {email}")
        message = MessageSchema(
            subject="1111.tn - Vérification de votre email",
            recipients=[email],
            body=f"""<div style="font-family: Arial, sans-serif; max-width: 480px; margin: 0 auto; padding: 32px; background: #f8fafc; border-radius: 16px;">
        <div style="text-align: center; margin-bottom: 24px;">
            <h2 style="color: #1e40af; margin: 0;">Bienvenue sur 1111.tn</h2>
        </div>
        <p style="color: #334155; font-size: 15px;">Votre code de vérification est :</p>
        <div style="text-align: center; margin: 24px 0;">
            <span style="display: inline-block; font-size: 32px; font-weight: bold; letter-spacing: 8px; color: #2563eb; background: #eff6ff; padding: 16px 32px; border-radius: 12px; border: 2px solid #bfdbfe;">{code}</span>
        </div>
        <p style="color: #64748b; font-size: 13px; text-align: center;">Ce code est valable pendant 30 minutes.<br>Si vous n'avez pas créé de compte, ignorez cet email.</p>
        </div>""",
            subtype=MessageType.html
        )
        fm = FastMail(conf)
        await fm.send_message(message)
        logger.info(f"Verification email sent successfully to {email}")
    except Exception as e:
        logger.error(f"Failed to send verification email to {email}: {e}")

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
