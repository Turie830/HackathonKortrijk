"""PARALLAX: a local evidence workbench for the SD Worx challenge."""
from contextlib import asynccontextmanager
from datetime import date
import os
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

import knowledge
from model import rephrase


@asynccontextmanager
async def lifespan(app):
    knowledge.initialize(app.state.database)
    yield


app = FastAPI(title="PARALLAX · SD Worx challenge", lifespan=lifespan, docs_url=None, redoc_url=None)
app.state.database = knowledge.DATABASE
allowed_hosts = ["127.0.0.1", "localhost", "[::1]", "testserver"]
allowed_hosts.extend(host.strip() for host in os.getenv("PARALLAX_ALLOWED_HOSTS", "").split(",") if host.strip())
app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
app.mount("/static", StaticFiles(directory=knowledge.ROOT / "static"), name="static")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Question(StrictModel):
    question: str = Field(min_length=3, max_length=1000)
    country: Literal["BE", "NL"] = "BE"
    client_id: Literal["demo-acme"] | None = None
    as_of: date = Field(default_factory=date.today)

    @field_validator("question")
    @classmethod
    def meaningful_question(cls, value):
        if not any(char.isalpha() for char in value):
            raise ValueError("Stel een vraag met woorden.")
        return value

    @model_validator(mode="after")
    def client_scope(self):
        if self.client_id == "demo-acme" and self.country != "BE":
            raise ValueError("Demo Acme hoort bij België. Kies algemene procedures voor Nederland.")
        return self


class ReviewRequest(StrictModel):
    assessment_id: str = Field(pattern=r"^PX-[A-F0-9]{12}$")


class Resolution(StrictModel):
    citation: str = Field(min_length=3, max_length=150)
    rationale: str = Field(min_length=20, max_length=2000)
    demo_acknowledged: Literal[True]


def database(request):
    return request.app.state.database


def check_origin(request: Request):
    origin = request.headers.get("origin")
    if origin and origin != str(request.base_url).rstrip("/"):
        raise HTTPException(403, "Deze actie vereist dezelfde origin als de app.")
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403, "Cross-site verzoeken zijn niet toegestaan.")


@app.middleware("http")
async def security_headers(request, call_next):
    if request.method in ("POST", "PUT", "PATCH"):
        if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
            return Response("Alleen JSON wordt aanvaard.", status_code=415)
        content = bytearray()
        async for chunk in request.stream():
            content.extend(chunk)
            if len(content) > 16384:
                return Response("Aanvraag is te groot.", status_code=413)
        request._body = bytes(content)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
        "base-uri 'none'; form-action 'self'; object-src 'none'"
    )
    return response


@app.exception_handler(LookupError)
async def not_found(request, exc):
    from fastapi.responses import JSONResponse
    return JSONResponse({"detail": str(exc)}, status_code=404)


@app.exception_handler(ValueError)
async def invalid_action(request, exc):
    from fastapi.responses import JSONResponse
    return JSONResponse({"detail": str(exc)}, status_code=409)


@app.get("/")
def home():
    return FileResponse(knowledge.ROOT / "static" / "index.html")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(knowledge.ROOT / "static" / "favicon.svg", media_type="image/svg+xml")


@app.post("/api/ask")
def ask(question: Question, request: Request):
    check_origin(request)
    result = knowledge.answer_question(**question.model_dump(), database=database(request))
    result = rephrase(question.question, result)
    return knowledge.save_assessment(result, database(request))


@app.get("/api/sources")
def list_sources(request: Request):
    return knowledge.sources(database(request))


@app.post("/api/reviews", status_code=201)
def request_review(payload: ReviewRequest, request: Request):
    check_origin(request)
    return knowledge.request_assessment_review(payload.assessment_id, database(request))


@app.get("/api/reviews")
def list_reviews(request: Request):
    return knowledge.reviews(database(request))


@app.post("/api/reviews/{review_id}/resolve")
def resolve(review_id: int, payload: Resolution, request: Request):
    check_origin(request)
    return knowledge.resolve_review(review_id, payload.citation, payload.rationale, database(request))


@app.get("/api/assessments/{assessment_id}/compare")
def compare(assessment_id: str, request: Request):
    return knowledge.compare_contexts(assessment_id, database(request))


@app.get("/api/assessments/{assessment_id}/receipt")
def receipt(assessment_id: str, request: Request):
    content = knowledge.receipt_markdown(assessment_id, database(request))
    # Use the stored identifier for the filename, never user-supplied header text.
    stored = knowledge.get_assessment(assessment_id, database(request))["assessment_id"]
    return Response(content, media_type="text/markdown; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{stored}.md"'})
