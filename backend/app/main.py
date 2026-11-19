from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from . import rag, llm

app = FastAPI(title="Real Estate Chatbot")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class Chat(BaseModel):
    message: str
    history: list[dict] = []

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/api/chat")
def chat(req: Chat):
    try:
        ctx = rag.retrieve(req.message)
        if not ctx:
            return {
                "answer": "I couldn't find any properties matching your exact criteria (budget, bedrooms, currency, or location). Please try broadening your search or adjusting your filters.",
                "sources": []
            }
        answer = llm.ask(req.message, ctx, req.history[-6:])
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Upstream error: {e}")
    seen, sources = set(), []
    for _, t, u, _ in ctx:
        if u not in seen:
            seen.add(u); sources.append({"title": t, "url": u})
    return {"answer": answer, "sources": sources[:8]}
