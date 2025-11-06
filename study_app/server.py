from __future__ import annotations

import datetime as dt
import sqlite3
from typing import List, Optional

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field

from .database import get_session
from .gpt import StudyGPT, build_guidance_messages
from .repository import StorageRepository, truncate_documents


class RegisterPayload(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    name: str


class LoginPayload(BaseModel):
    email: EmailStr
    password: str


class ProfilePayload(BaseModel):
    name: str = Field(..., description="Learner name")
    learning_style: str = Field("balanced", description="Preferred study approach")
    goals: str = Field("", description="Primary academic goals")
    availability: str = Field("", description="Weekly availability overview")
    tone: str = Field("encouraging", description="Preferred coaching tone")


class CoachRequest(BaseModel):
    mode: str = Field(..., description="Guidance mode to generate")
    prompt: str = Field(..., description="Custom message or question from the learner")


class TestLogRequest(BaseModel):
    topic: str
    score: str
    notes: Optional[str] = None


def get_repository(session=Depends(get_session)) -> StorageRepository:
    return StorageRepository(session)


def get_gpt() -> StudyGPT:
    return StudyGPT()


def get_current_user(
    repo: StorageRepository = Depends(get_repository),
    token: str = Header(..., alias="X-Session-Token"),
) -> sqlite3.Row:
    user = repo.get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")
    return user


def serialize_user(repo: StorageRepository, user: sqlite3.Row) -> dict:
    profile = repo.load_profile(user)
    profile.update({"email": user["email"], "id": user["id"]})
    return profile


def create_app() -> FastAPI:
    app = FastAPI(title="StudyMate", version="2.0.0", description="Personalised AI study mentor")

    app.mount("/static", StaticFiles(directory="static"), name="static")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse("static/index.html")

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------
    @app.post("/api/auth/register")
    async def register(payload: RegisterPayload, repo: StorageRepository = Depends(get_repository)) -> dict:
        try:
            user = repo.create_user(email=payload.email, password=payload.password, name=payload.name)
        except ValueError as exc:  # email already registered
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        token = repo.create_session(user)
        return {"token": token, "user": serialize_user(repo, user)}

    @app.post("/api/auth/login")
    async def login(payload: LoginPayload, repo: StorageRepository = Depends(get_repository)) -> dict:
        user = repo.authenticate(email=payload.email, password=payload.password)
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
        token = repo.create_session(user)
        return {"token": token, "user": serialize_user(repo, user)}

    @app.post("/api/auth/logout")
    async def logout(
        repo: StorageRepository = Depends(get_repository),
        token: str = Header(..., alias="X-Session-Token"),
    ) -> dict:
        repo.revoke_session(token)
        return {"status": "signed_out"}

    @app.get("/api/auth/me")
    async def current_user(
        repo: StorageRepository = Depends(get_repository),
        user: sqlite3.Row = Depends(get_current_user),
    ) -> dict:
        return serialize_user(repo, user)

    # ------------------------------------------------------------------
    # Profile & documents
    # ------------------------------------------------------------------
    @app.get("/api/profile")
    async def get_profile(
        repo: StorageRepository = Depends(get_repository),
        user: sqlite3.Row = Depends(get_current_user),
    ) -> dict:
        return repo.load_profile(user)

    @app.post("/api/profile")
    async def save_profile(
        payload: ProfilePayload,
        repo: StorageRepository = Depends(get_repository),
        user: sqlite3.Row = Depends(get_current_user),
    ) -> dict:
        repo.save_profile(user, payload.dict())
        return {"status": "ok"}

    @app.get("/api/documents")
    async def list_documents(
        repo: StorageRepository = Depends(get_repository),
        user: sqlite3.Row = Depends(get_current_user),
    ) -> dict:
        documents = repo.list_documents(user)
        for document in documents:
            document.pop("content", None)
        return {"documents": documents}

    @app.post("/api/documents")
    async def upload_document(
        file: UploadFile = File(...),
        topics: Optional[str] = Form(None),
        repo: StorageRepository = Depends(get_repository),
        user: sqlite3.Row = Depends(get_current_user),
    ) -> dict:
        raw = await file.read()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("latin-1", errors="ignore")
        topic_list: List[str] = []
        if topics:
            topic_list = [item.strip() for item in topics.split(",") if item.strip()]
        record = repo.add_document(user=user, filename=file.filename, content=text, topics=topic_list)
        record.pop("content", None)
        return {"document": record}

    # ------------------------------------------------------------------
    # Assessments & coaching
    # ------------------------------------------------------------------
    @app.post("/api/tests")
    async def log_test(
        payload: TestLogRequest,
        repo: StorageRepository = Depends(get_repository),
        user: sqlite3.Row = Depends(get_current_user),
    ) -> dict:
        repo.log_assessment(user, topic=payload.topic, score=payload.score, notes=payload.notes or "")
        return {"status": "logged"}

    @app.get("/api/tests")
    async def list_tests(
        repo: StorageRepository = Depends(get_repository),
        user: sqlite3.Row = Depends(get_current_user),
    ) -> dict:
        tests = repo.list_assessments(user)
        return {"tests": tests}

    @app.post("/api/coach")
    async def coach(
        payload: CoachRequest,
        repo: StorageRepository = Depends(get_repository),
        gpt: StudyGPT = Depends(get_gpt),
        user: sqlite3.Row = Depends(get_current_user),
    ) -> dict:
        profile = repo.load_profile(user)
        documents = truncate_documents(repo.list_documents(user))
        tests = repo.list_assessments(user)
        insights = repo.summary(user)
        messages = build_guidance_messages(
            profile=profile,
            documents=documents,
            mode=payload.mode,
            prompt=payload.prompt,
            previous_tests=tests,
            insights=insights,
        )
        output = gpt.chat(messages)
        repo.log_interaction(user, mode=payload.mode, prompt=payload.prompt, response=output)
        return {"response": output, "offline": not gpt.is_configured()}

    @app.get("/api/insights")
    async def insights(
        repo: StorageRepository = Depends(get_repository),
        user: sqlite3.Row = Depends(get_current_user),
    ) -> dict:
        return repo.summary(user)

    return app


app = create_app()
