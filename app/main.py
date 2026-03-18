from fastapi import FastAPI
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.v1.api import api_router
from app.db.mongodb import connect_to_mongo, close_mongo_connection
from prometheus_fastapi_instrumentator import Instrumentator

@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_mongo()
    yield
    await close_mongo_connection()

app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)

# Set all CORS enabled origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

app.include_router(api_router, prefix=settings.API_V1_STR)

Instrumentator().instrument(app).expose(app)

@app.get("/api/v1/health")
async def health_check():
    """Health check endpoint for Render"""
    return {"status": "ok"}
