from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import secrets
import threading
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from itertools import product
from pathlib import Path
from typing import Any, Annotated
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine, delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, selectinload, sessionmaker


if os.getenv("DATABASE_URL"):
    DATABASE_URL: str | URL = os.environ["DATABASE_URL"]
elif os.getenv("DB_HOST"):
    DATABASE_URL = URL.create(
        "postgresql+psycopg",
        username=os.getenv("DB_USER", "case_lens"),
        password=os.getenv("DB_PASSWORD", ""),
        host=os.getenv("DB_HOST", "postgres"),
        port=int(os.getenv("DB_PORT", "5432")),
        database=os.getenv("DB_NAME", "case_lens"),
    )
else:
    DATABASE_URL = "sqlite:////data/dev.db"
DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
SESSION_HOURS = int(os.getenv("SESSION_HOURS", "24"))
SECURE_COOKIES = os.getenv("SECURE_COOKIES", "false").lower() == "true"
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "2048"))
JUDGE_LOCAL_RELAY_BASE = "http://127.0.0.1:19001/v1"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(30), default="annotator")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(240), index=True)
    annotation_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    cases: Mapped[list[Case]] = relationship(back_populates="project", cascade="all, delete-orphan")


class ProjectMember(Base):
    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "user_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Case(Base):
    __tablename__ = "cases"
    __table_args__ = (UniqueConstraint("project_id", "external_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(300), index=True)
    ordinal: Mapped[int] = mapped_column(Integer, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    project: Mapped[Project] = relationship(back_populates="cases")
    annotations: Mapped[list[Annotation]] = relationship(back_populates="case", cascade="all, delete-orphan")


class CaseAssignment(Base):
    __tablename__ = "case_assignments"
    __table_args__ = (UniqueConstraint("case_id", "user_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    assigned_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Annotation(Base):
    __tablename__ = "annotations"
    __table_args__ = (UniqueConstraint("case_id", "candidate_id", "user_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    candidate_id: Mapped[str] = mapped_column(String(300), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    scores: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    badcase: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    badcase_tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    note: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    case: Mapped[Case] = relationship(back_populates="annotations")
    user: Mapped[User] = relationship()


class LoginSession(Base):
    __tablename__ = "login_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    user: Mapped[User] = relationship()


class PetProfile(Base):
    __tablename__ = "pet_profiles"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    name: Mapped[str] = mapped_column(String(20), default="小镜")
    color: Mapped[str] = mapped_column(String(20), default="lime")
    accessory: Mapped[str] = mapped_column(String(20), default="none")
    xp: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class PetExperienceEvent(Base):
    __tablename__ = "pet_experience_events"
    __table_args__ = (UniqueConstraint("user_id", "event_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    event_key: Mapped[str] = mapped_column(String(500))
    reason: Mapped[str] = mapped_column(String(30))
    amount: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PetProgressV2(Base):
    """Stores experience in 0.2 EXP units without altering existing deployments."""
    __tablename__ = "pet_progress_v2"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    xp_units: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class PetEvolution(Base):
    __tablename__ = "pet_evolutions"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    available_chances: Mapped[int] = mapped_column(Integer, default=0)
    credited_level: Mapped[int] = mapped_column(Integer, default=1)
    stage: Mapped[int] = mapped_column(Integer, default=0)
    path: Mapped[str] = mapped_column(String(30), default="")
    variant_seed: Mapped[int] = mapped_column(Integer, default=0)
    traits: Mapped[list[str]] = mapped_column(JSON, default=list)
    history: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class PetCollection(Base):
    __tablename__ = "pet_collections"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    # Legacy rows store item_id -> count. New rows keep count, level, affixes and
    # synthesis pity in the same JSON column so no destructive migration is needed.
    inventory: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    equipped: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    skills: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    active_skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    drop_history: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    pity: Mapped[int] = mapped_column(Integer, default=0)
    total_drops: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class PetTicketGift(Base):
    __tablename__ = "pet_ticket_gifts"
    id: Mapped[int] = mapped_column(primary_key=True)
    sender_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    recipient_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    amount: Mapped[int] = mapped_column(Integer)
    note: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PetWheelGrant(Base):
    __tablename__ = "pet_wheel_grants"
    id: Mapped[int] = mapped_column(primary_key=True)
    sender_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    recipient_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    amount: Mapped[int] = mapped_column(Integer)
    note: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class JudgeConfigVersion(Base):
    __tablename__ = "judge_config_versions"
    __table_args__ = (UniqueConstraint("project_id", "version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    api_key: Mapped[str] = mapped_column(Text, default="")
    signature: Mapped[str] = mapped_column(String(64), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class JudgeConfigPreference(Base):
    __tablename__ = "judge_config_preferences"
    __table_args__ = (UniqueConstraint("project_id", "user_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    config_id: Mapped[int] = mapped_column(ForeignKey("judge_config_versions.id"), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class JudgeCaseRun(Base):
    __tablename__ = "judge_case_runs"
    __table_args__ = (UniqueConstraint("case_id", "config_id", "case_hash"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    config_id: Mapped[int] = mapped_column(ForeignKey("judge_config_versions.id"), index=True)
    case_hash: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(40), default="queued", index=True)
    stage1_result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    stage1_raw: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str] = mapped_column(Text, default="")
    triggered_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class JudgeCandidateRun(Base):
    __tablename__ = "judge_candidate_runs"
    __table_args__ = (UniqueConstraint("case_run_id", "candidate_id", "candidate_hash"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    case_run_id: Mapped[int] = mapped_column(ForeignKey("judge_case_runs.id"), index=True)
    candidate_id: Mapped[str] = mapped_column(String(300), index=True)
    candidate_hash: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(40), default="queued", index=True)
    stage2_result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    stage2_raw: Mapped[str] = mapped_column(Text, default="")
    stage3_result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    stage3_raw: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class JudgeSelfCheck(Base):
    __tablename__ = "judge_self_checks"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    config_id: Mapped[int] = mapped_column(ForeignKey("judge_config_versions.id"), index=True)
    case_hash: Mapped[str] = mapped_column(String(64), index=True)
    annotation_hash: Mapped[str] = mapped_column(String(64), index=True)
    result: Mapped[dict[str, Any]] = mapped_column(JSON)
    raw_output: Mapped[str] = mapped_column(Text, default="")
    triggered_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


connect_args = {"check_same_thread": False} if str(DATABASE_URL).startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600_000)
    return f"pbkdf2_sha256$600000${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        _, rounds, salt_hex, digest_hex = encoded.split("$", 3)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(rounds))
        return hmac.compare_digest(actual.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def session_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DB = Annotated[Session, Depends(get_db)]


class LoginBody(BaseModel):
    username: str
    password: str


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=100)
    display_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=200)
    role: str = "annotator"


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_l