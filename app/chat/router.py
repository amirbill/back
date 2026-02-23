"""
Chatbot Router — Groq-powered chatbot API for 1111.tn
"""

from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel

from app.chat.service import get_chat_response

router = APIRouter()


class MessageItem(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: Optional[list[MessageItem]] = None


class ChatResponse(BaseModel):
    reply: str


@router.post("/message", response_model=ChatResponse)
async def chat_message(payload: ChatRequest):
    """Process a user message through Groq and return a response."""
    history = None
    if payload.history:
        history = [{"role": m.role, "content": m.content} for m in payload.history]

    reply = await get_chat_response(payload.message, history)
    return ChatResponse(reply=reply)
