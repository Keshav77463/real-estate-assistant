import logging
import os
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from . import rag, llm

logger = logging.getLogger(__name__)

app = FastAPI(title="Real Estate Chatbot")
allowed_origins = [
    origin.strip().rstrip("/")
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost,http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class ChatHistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)

class Chat(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[ChatHistoryMessage] = Field(default_factory=list, max_length=12)

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/api/chat")
def chat(req: Chat):
    question = req.message.strip()
    if not question:
        raise HTTPException(status_code=422, detail="Message must not be blank.")
    try:
        ctx = rag.retrieve(question)
        if not ctx:
            return {
                "answer": "I couldn't find any properties matching your exact criteria (budget, bedrooms, currency, or location). Please try broadening your search or adjusting your filters.",
                "sources": []
            }
        history = [message.model_dump() for message in req.history[-6:]]
        answer = llm.ask(question, ctx, history)
    except Exception as exc:
        logger.exception("Chat request failed")
        raise HTTPException(
            status_code=502,
            detail="The chat service is temporarily unavailable. Please try again.",
        ) from exc
    seen, sources = set(), []
    for _, t, u, _ in ctx:
        if u not in seen:
            seen.add(u); sources.append({"title": t, "url": u})
    return {"answer": answer, "sources": sources[:8]}
