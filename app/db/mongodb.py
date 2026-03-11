from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings
import logging

class MongoDB:
    client: AsyncIOMotorClient = None
    db_name: str = settings.DB_NAME

db = MongoDB()

async def connect_to_mongo():
    try:
        db.client = AsyncIOMotorClient(settings.MONGO_URI)
        # Verify connection
        await db.client.admin.command('ping')
        print("[OK] Database connected successfully!")
        logging.info("Connected to MongoDB")
    except Exception as e:
        print(f"[ERROR] Database connection failed: {e}")
        logging.error(f"Could not connect to MongoDB: {e}")
        raise e

async def close_mongo_connection():
    if db.client:
        db.client.close()
        logging.info("Closed MongoDB connection")

def get_database():
    return db.client[db.db_name]

def get_auth_database():
    return db.client[settings.AUTH_DB_NAME]
