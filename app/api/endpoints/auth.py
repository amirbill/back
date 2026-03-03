from fastapi import APIRouter, Depends, HTTPException, status, Body, BackgroundTasks
from fastapi.security import OAuth2PasswordBearer
from app.db.mongodb import get_auth_database
from app.models.user import User
from app.schemas.auth import UserCreate, Token, EmailSchema, PasswordReset, UserLogin, UserProfileUpdate, ChangePassword, GoogleLogin
from bson import ObjectId
from app.core.security import get_password_hash, verify_password, create_access_token
from app.core.email import send_verification_email, send_reset_password_email, send_email_smtp
from app.core.config import settings
from datetime import timedelta, datetime
from jose import JWTError, jwt
import secrets
import random
import logging
import asyncio
from typing import Optional

logger = logging.getLogger(__name__)

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/signin")

async def get_current_user(token: str = Depends(oauth2_scheme), db=Depends(get_auth_database)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = await db.users.find_one({"email": email})
    if user is None:
        raise credentials_exception
    return User(**user)

@router.post("/signup", response_model=User)
async def signup(user: UserCreate, db=Depends(get_auth_database)):
    existing_user = await db.users.find_one({"email": user.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    verification_code = str(random.randint(100000, 999999))
    user_dict = user.dict()
    # Force role to be client for public signup
    user_dict["role"] = "client"
    user_dict["password_hash"] = get_password_hash(user.password)
    del user_dict["password"]
    user_dict["verification_code"] = verification_code
    user_dict["is_verified"] = False
    
    new_user = User(**user_dict)
    user_to_insert = new_user.dict(by_alias=True)
    if "_id" in user_to_insert and user_to_insert["_id"] is None:
        del user_to_insert["_id"]
    await db.users.insert_one(user_to_insert)
    
    # Fire-and-forget email sending so the response returns immediately
    asyncio.create_task(_send_verification_safe(user.email, verification_code))

    return new_user

async def _send_verification_safe(email: str, code: str):
    """Send verification email in background, logging any errors"""
    try:
        await send_verification_email(email, code)
    except Exception as e:
        logger.error(f"Failed to send verification email to {email}: {e}")

@router.get("/test-email")
async def test_email():
    """Diagnostic endpoint to test SMTP connection on Render"""
    import smtplib
    results = {
        "mail_username": settings.MAIL_USERNAME,
        "mail_server": settings.MAIL_SERVER,
        "mail_port": settings.MAIL_PORT,
        "mail_starttls": settings.MAIL_STARTTLS,
        "mail_ssl_tls": settings.MAIL_SSL_TLS,
        "password_length": len(settings.MAIL_PASSWORD),
        "password_has_spaces": " " in settings.MAIL_PASSWORD,
    }
    
    # Test SMTP connection
    try:
        server = smtplib.SMTP(settings.MAIL_SERVER, settings.MAIL_PORT, timeout=15)
        server.ehlo()
        results["smtp_connect"] = "OK"
        
        server.starttls()
        results["smtp_starttls"] = "OK"
        
        server.login(settings.MAIL_USERNAME, settings.MAIL_PASSWORD)
        results["smtp_login"] = "OK"
        
        server.quit()
        results["smtp_quit"] = "OK"
    except Exception as e:
        results["smtp_error"] = str(e)
        results["smtp_error_type"] = type(e).__name__
    
    return results

@router.post("/signin", response_model=Token)
async def signin(user_credentials: UserLogin, db=Depends(get_auth_database)):
    user = await db.users.find_one({"email": user_credentials.email})
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    
    if not verify_password(user_credentials.password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    
    if not user.get("is_verified", False):
         raise HTTPException(status_code=400, detail="Email not verified")

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        subject=user["email"], expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer", "role": user["role"]}

@router.post("/verify-email")
async def verify_email(email: str = Body(...), code: str = Body(...), db=Depends(get_auth_database)):
    user = await db.users.find_one({"email": email})
    if not user:
         raise HTTPException(status_code=400, detail="User not found")
        
    if user.get("verification_code") != code:
        raise HTTPException(status_code=400, detail="Invalid verification code")
    
    await db.users.update_one({"email": email}, {"$set": {"is_verified": True, "verification_code": ""}})
    return {"message": "Email verified successfully"}

@router.post("/resend-verification")
async def resend_verification(email: str = Body(..., embed=True), db=Depends(get_auth_database)):
    user = await db.users.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=400, detail="User not found")
    
    if user.get("is_verified", False):
        raise HTTPException(status_code=400, detail="Email already verified")
    
    new_code = str(random.randint(100000, 999999))
    await db.users.update_one({"email": email}, {"$set": {"verification_code": new_code}})
    
    # Fire-and-forget email sending
    asyncio.create_task(_send_verification_safe(email, new_code))
    return {"message": "Verification code resent"}

@router.post("/forgot-password")
async def forgot_password(email: EmailSchema, background_tasks: BackgroundTasks, db=Depends(get_auth_database)):
    user = await db.users.find_one({"email": email.email})
    if not user:
        # Don't reveal valid emails
        return {"message": "If email exists, a verification code will be sent"}
    
    # Generate 6-digit code
    reset_code = str(random.randint(100000, 999999))
    # Code expires in 15 minutes
    expires_at = datetime.utcnow() + timedelta(minutes=15)
    
    await db.users.update_one(
        {"email": email.email}, 
        {"$set": {"reset_code": reset_code, "reset_code_expires": expires_at}}
    )
    
    background_tasks.add_task(send_reset_password_email, email.email, reset_code)
        
    return {"message": "If email exists, a verification code will be sent"}

@router.post("/reset-password")
async def reset_password(reset_data: PasswordReset, db=Depends(get_auth_database)):
    user = await db.users.find_one({"email": reset_data.email})
    if not user:
        raise HTTPException(status_code=400, detail="Invalid email or verification code")
    
    # Check if code exists and matches
    if not user.get("reset_code") or user.get("reset_code") != reset_data.code:
        raise HTTPException(status_code=400, detail="Invalid email or verification code")
    
    # Check if code has expired
    if not user.get("reset_code_expires") or user.get("reset_code_expires") < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Verification code has expired")
    
    new_hash = get_password_hash(reset_data.new_password)
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"password_hash": new_hash, "reset_code": None, "reset_code_expires": None}}
    )
    return {"message": "Password reset successfully"}

@router.get("/me", response_model=User)
async def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user

@router.put("/profile", response_model=User)
async def update_profile(
    profile_data: UserProfileUpdate,
    current_user: User = Depends(get_current_user),
    db=Depends(get_auth_database)
):
    update_data = profile_data.dict(exclude_unset=True)
    
    try:
        user_id = ObjectId(current_user.id)
    except Exception as e:
        print(f"DEBUG: Invalid user id format: {current_user.id}")
        raise HTTPException(status_code=400, detail="Invalid user ID format")

    if "email" in update_data and update_data["email"] != current_user.email:
        existing_user = await db.users.find_one({"email": update_data["email"]})
        if existing_user:
            raise HTTPException(status_code=400, detail="Email already registered")
            
    update_data["updated_at"] = datetime.utcnow()
    
    result = await db.users.update_one(
        {"_id": user_id},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    
    updated_user = await db.users.find_one({"_id": user_id})
    if not updated_user:
        raise HTTPException(status_code=404, detail="User data not found after update")
    return User(**updated_user)

@router.put("/change-password")
async def change_password(
    password_data: ChangePassword,
    current_user: User = Depends(get_current_user),
    db=Depends(get_auth_database)
):
    user_id = ObjectId(current_user.id)
    # Verify current password
    user_in_db = await db.users.find_one({"_id": user_id})
    if not verify_password(password_data.current_password, user_in_db["password_hash"]):
        raise HTTPException(status_code=400, detail="Incorrect current password")
    
    
    # Hash and update new password
    new_hash = get_password_hash(password_data.new_password)
    await db.users.update_one(
        {"_id": user_id},
        {"$set": {"password_hash": new_hash, "updated_at": datetime.utcnow()}}
    )
    
    return {"message": "Password updated successfully"}

@router.post("/google", response_model=Token)
async def google_login(login_data: GoogleLogin, db=Depends(get_auth_database)):
    from google.oauth2 import id_token
    from google.auth.transport import requests as google_requests

    try:
        # Verify the token
        id_info = id_token.verify_oauth2_token(
            login_data.credential, 
            google_requests.Request(), 
            settings.GOOGLE_CLIENT_ID
        )

        email = id_info['email']
        google_id = id_info['sub']
        picture = id_info.get('picture')
        name = id_info.get('name')
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid Google token: {str(e)}")

    # Check if user exists
    user = await db.users.find_one({"email": email})
    
    print(f"DEBUG: Login with email: '{email}'")
    print(f"DEBUG: Settings Admin Email: '{settings.MAIL_USERNAME}'")

    if not user:
        # Create new user
        role = "client"
        if email == settings.MAIL_USERNAME:
            role = "admin"
            print("DEBUG: Promoting NEW user to ADMIN")
            
        new_user = {
            "email": email,
            "google_id": google_id,
            "picture": picture,
            "full_name": name,
            "role": role,
            "is_verified": True,  # Google emails are verified
            "password_hash": get_password_hash(secrets.token_urlsafe(16)), # Random password
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        result = await db.users.insert_one(new_user)
        user = await db.users.find_one({"_id": result.inserted_id})
    else:
        # Update existing user with google info if missing
        update_data = {}
        if not user.get("google_id"):
            update_data["google_id"] = google_id
        if not user.get("picture") and picture:
            update_data["picture"] = picture
        if not user.get("is_verified"):
            update_data["is_verified"] = True
        
        # Auto-promote to admin if email matches
        if email == settings.MAIL_USERNAME:
            if user.get("role") != "admin":
                update_data["role"] = "admin"
                print("DEBUG: Promoting EXISTING user to ADMIN")
            else:
                print("DEBUG: User is already ADMIN")
        else:
             print("DEBUG: Email does not match Admin Email")
            
        if update_data:
            await db.users.update_one({"_id": user["_id"]}, {"$set": update_data})
            user = await db.users.find_one({"_id": user["_id"]})

    # Create access token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        subject=user["email"], expires_delta=access_token_expires
    )
    
    print(f"DEBUG: Final Role in Token Response: {user['role']}")
    
    return {"access_token": access_token, "token_type": "bearer", "role": user["role"]}
