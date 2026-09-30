"""Local demo app. Run: python -m uvicorn app:app --host 127.0.0.1 --port 8000."""
from contextlib import asynccontextmanager
from datetime import date
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import knowledge
from model import rephrase


@asynccontextmanager
async def lifespan(app):
    knowledge.initialize()
    yield


app = FastAPI(title="Knowledge Within · SD Worx demo", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=knowledge.ROOT / "static"), name="static")


class Question(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    country: Literal["BE", "NL"] = "BE"
    client_id: Literal["demo-acme"] | None = None
    as_of: date = Field(default_factory=date.today)


def check_origin(request: Request):
    """Reject cross-origin mutations of this local demo."""
    origin = request.headers.get("origin")
    if origin and origin != str(request.base_url).rstrip("/"):
        raise HTTPException(403, "Deze actie vereist dezelfde origin als de app.")


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
    )
    return response


@app.get("/")
def home():
    return FileResponse(knowledge.ROOT / "static" / "index.html")


@app.post("/api/ask")
def ask(question: Question, request: Request):
    check_origin(request)
    result = knowledge.answer_question(**question.model_dump())
    return rephrase(question.question, result)


@app.get("/api/sources")
def list_sources():
    return knowledge.sources()


@app.post("/api/reviews", status_code=201)
def request_review(question: Question, request: Request):
    check_origin(request)
    result = knowledge.answer_question(**question.model_dump())
    return knowledge.create_review(**question.model_dump(), result=result)


@app.get("/api/reviews")
def list_reviews():
    return knowledge.reviews()
