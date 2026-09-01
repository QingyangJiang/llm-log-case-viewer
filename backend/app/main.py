from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Annotated

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine, delete, func, select
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
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    password: str | None = Field(default=None, min_length=8, max_length=200)
    active: bool | None = None


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=240)
    annotation_config: dict[str, Any] = Field(default_factory=dict)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=240)
    archived: bool | None = None


class AnnotationBody(BaseModel):
    scores: dict[str, int] = Field(default_factory=dict)
    badcase: bool = False
    badcase_tags: list[str] = Field(default_factory=list)
    note: str = ""
    status: str = "draft"
    revision: int | None = None


class ProjectSettingsBody(BaseModel):
    blind_mode: bool = True
    lock_submitted: bool = False
    dimensions: list[dict[str, Any]] | None = None
    badcase_tags: list[str] | None = None
    model_order: list[str] | None = None


class ProjectMembersBody(BaseModel):
    user_ids: list[int] = Field(default_factory=list)


class ExplicitAssignmentBody(BaseModel):
    user_id: int
    external_ids: list[str] = Field(min_length=1, max_length=10_000)
    replace_existing: bool = False


class RandomAssignmentBody(BaseModel):
    user_id: int
    quantity: int = Field(ge=1, le=100_000)
    allow_overlap: bool = False
    replace_existing: bool = False


class AssignmentRemovalBody(BaseModel):
    user_id: int | None = None
    external_ids: list[str] = Field(default_factory=list, max_length=10_000)
    delete_annotations: bool = False


class PetProfileUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=20)
    color: str = Field(max_length=20)
    accessory: str = Field(max_length=20)


def user_dict(user: User) -> dict[str, Any]:
    return {"id": str(user.id), "username": user.username, "display_name": user.display_name, "role": user.role, "active": user.active}


def annotation_dict(annotation: Annotation) -> dict[str, Any]:
    return {
        "annotation_id": str(annotation.id),
        "annotator": {"id": str(annotation.user_id), "name": annotation.user.display_name},
        "candidate_id": annotation.candidate_id,
        "scores": annotation.scores,
        "badcase": annotation.badcase,
        "badcase_tags": annotation.badcase_tags,
        "note": annotation.note,
        "status": annotation.status,
        "revision": annotation.revision,
        "created_at": annotation.created_at.isoformat(),
        "updated_at": annotation.updated_at.isoformat(),
    }


def project_config(project: Project) -> dict[str, Any]:
    return {"blind_mode": True, "lock_submitted": False, "archived": False, **(project.annotation_config or {})}


PET_COLORS = {"lime": 1, "aqua": 2, "peach": 3, "lavender": 4, "sky": 5, "coral": 6, "gold": 8, "midnight": 10}
PET_ACCESSORIES = {"none": 1, "leaf": 2, "bow": 3, "glasses": 4, "star": 5, "headphones": 6, "cap": 7, "crown": 8, "halo": 10, "medal": 12}
# One unit is 0.2 EXP, which keeps fractional petting rewards exact in the database.
PET_XP_UNITS = {"pet": 1, "annotation": 30, "badcase": 20}
PET_LEVEL_TITLES = {1: "实习搭子", 2: "认真观察员", 4: "Badcase 侦探", 6: "质量守门员", 8: "评测专家", 10: "首席标注官", 12: "传奇质检师"}


def pet_level(xp: float) -> int:
    return int((max(0, xp) / 20) ** 0.5) + 1


def get_or_create_pet(db: Session, user_id: int) -> tuple[PetProfile, PetProgressV2]:
    profile = db.get(PetProfile, user_id)
    if not profile:
        profile = PetProfile(user_id=user_id)
        db.add(profile)
        db.flush()
    progress = db.get(PetProgressV2, user_id)
    if not progress:
        progress = PetProgressV2(user_id=user_id, xp_units=max(0, int((profile.xp or 0) * 5)))
        db.add(progress)
        db.flush()
    return profile, progress


def pet_title(level: int) -> str:
    return next(title for required, title in reversed(PET_LEVEL_TITLES.items()) if level >= required)


def pet_dict(profile: PetProfile, progress: PetProgressV2) -> dict[str, Any]:
    xp = round(progress.xp_units / 5, 1)
    level = pet_level(xp)
    return {
        "name": profile.name,
        "color": profile.color,
        "accessory": profile.accessory,
        "xp": xp,
        "level": level,
        "title": pet_title(level),
        "current_level_xp": 20 * (level - 1) ** 2,
        "next_level_xp": 20 * level ** 2,
    }


def grant_pet_experience(db: Session, user_id: int, reason: str, event_key: str) -> tuple[PetProfile, PetProgressV2, bool, float]:
    profile, progress = get_or_create_pet(db, user_id)
    if db.scalar(select(PetExperienceEvent.id).where(PetExperienceEvent.user_id == user_id, PetExperienceEvent.event_key == event_key)):
        return profile, progress, False, 0
    units = PET_XP_UNITS[reason]
    db.add(PetExperienceEvent(user_id=user_id, event_key=event_key, reason=reason, amount=units))
    progress.xp_units += units
    progress.updated_at = utcnow()
    profile.updated_at = utcnow()
    return profile, progress, True, round(units / 5, 1)


def user_case_progress(cases: list[Case], user_id: int) -> tuple[int, int]:
    completed = 0
    in_progress = 0
    for case in cases:
        candidate_ids = {str(item.get("id")) for item in case.payload.get("candidates", []) if isinstance(item, dict) and item.get("id") is not None}
        mine = [record for record in case.annotations if record.user_id == user_id]
        if candidate_ids and all(any(record.candidate_id == candidate_id and record.status == "submitted" for record in mine) for candidate_id in candidate_ids):
            completed += 1
        elif mine:
            in_progress += 1
    return completed, in_progress


def metric_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def metric_model_summary(model: str, points: list[dict[str, Any]]) -> dict[str, Any]:
    values = [float(point["score"]) for point in points]
    count = len(values)
    if not count:
        return {
            "model": model, "n": 0, "avg": 0, "median": 0, "std": 0,
            "tiers": {"tier_1": {"count": 0, "pct": 0}, "tier_2": {"count": 0, "pct": 0}, "tier_3": {"count": 0, "pct": 0}},
            "badcase_rate": 0, "manual_badcase_rate": 0, "score_hist": [0] * 10, "out_of_range_count": 0,
        }
    average = sum(values) / count
    ordered = sorted(values)
    midpoint = count // 2
    median = ordered[midpoint] if count % 2 else (ordered[midpoint - 1] + ordered[midpoint]) / 2
    std = math.sqrt(sum((value - average) ** 2 for value in values) / count) if count >= 2 else 0
    tier_1 = sum(value >= 8 for value in values)
    tier_2 = sum(4 <= value < 8 for value in values)
    tier_3 = sum(value < 4 for value in values)
    histogram = [0] * 10
    out_of_range = 0
    for value in values:
        rounded = int(math.floor(value + 0.5))
        if 1 <= rounded <= 10:
            histogram[rounded - 1] += 1
        else:
            out_of_range += 1
    percent = lambda value: round(value / count * 100, 1)
    return {
        "model": model,
        "n": count,
        "avg": round(average, 2),
        "median": round(median, 1),
        "std": round(std, 2),
        "tiers": {
            "tier_1": {"count": tier_1, "pct": percent(tier_1)},
            "tier_2": {"count": tier_2, "pct": percent(tier_2)},
            "tier_3": {"count": tier_3, "pct": percent(tier_3)},
        },
        "badcase_rate": percent(tier_2 + tier_3),
        "manual_badcase_rate": percent(sum(bool(point["badcase"]) for point in points)),
        "score_hist": histogram,
        "out_of_range_count": out_of_range,
    }


def metric_scope(cases: list[Case], models: list[str], dimension_key: str, user_id: int | None, label: str) -> dict[str, Any]:
    model_set = set(models)
    points = {model: [] for model in models}
    candidate_complete = 0
    attempted = 0
    complete = 0
    if not models:
        return {
            "id": "overall" if user_id is None else f"annotator:{user_id}",
            "label": label,
            "annotator_id": str(user_id) if user_id is not None else None,
            "candidate_complete_case_count": 0,
            "attempted_case_count": 0,
            "complete_case_count": 0,
            "dropped_case_count": 0,
            "complete_rate": 0,
            "models": [],
        }
    for case in cases:
        candidates = case.payload.get("candidates", [])
        candidate_to_model = {
            str(candidate.get("id")): str(candidate.get("model") or candidate.get("id"))
            for candidate in candidates
            if isinstance(candidate, dict) and candidate.get("id") is not None
        }
        if not model_set.issubset(set(candidate_to_model.values())):
            continue
        candidate_complete += 1
        grouped: dict[str, list[tuple[float, bool]]] = {model: [] for model in models}
        for record in case.annotations:
            if record.status != "submitted" or (user_id is not None and record.user_id != user_id):
                continue
            model = candidate_to_model.get(record.candidate_id)
            score = metric_number((record.scores or {}).get(dimension_key))
            if model in grouped and score is not None:
                grouped[model].append((score, bool(record.badcase)))
        if any(grouped[model] for model in models):
            attempted += 1
        if not all(grouped[model] for model in models):
            continue
        complete += 1
        for model in models:
            rows = grouped[model]
            points[model].append({
                "score": sum(row[0] for row in rows) / len(rows),
                "badcase": sum(row[1] for row in rows) * 2 >= len(rows),
            })
    return {
        "id": "overall" if user_id is None else f"annotator:{user_id}",
        "label": label,
        "annotator_id": str(user_id) if user_id is not None else None,
        "candidate_complete_case_count": candidate_complete,
        "attempted_case_count": attempted,
        "complete_case_count": complete,
        "dropped_case_count": max(0, attempted - complete),
        "complete_rate": round(complete / attempted * 100, 1) if attempted else 0,
        "models": [metric_model_summary(model, points[model]) for model in models],
    }


def project_metrics_payload(project: Project, cases: list[Case], dimension_key: str | None = None) -> dict[str, Any]:
    config = project_config(project)
    dimensions = [item for item in config.get("dimensions", []) if isinstance(item, dict) and item.get("key")]
    if not dimensions:
        dimensions = [{"key": "correctness", "label": "正确性", "min": 1, "max": 10}]
    selected = next((item for item in dimensions if item["key"] == dimension_key), None) if dimension_key else dimensions[0]
    if selected is None:
        raise HTTPException(422, "未知的评分维度")
    discovered: list[str] = []
    for case in cases:
        for candidate in case.payload.get("candidates", []):
            if not isinstance(candidate, dict) or candidate.get("id") is None:
                continue
            model = str(candidate.get("model") or candidate.get("id"))
            if model not in discovered:
                discovered.append(model)
    configured = [str(value) for value in config.get("model_order", []) if str(value) in discovered]
    models = [*configured, *(model for model in discovered if model not in configured)]
    annotators: dict[int, str] = {}
    for case in cases:
        for record in case.annotations:
            if record.status == "submitted" and metric_number((record.scores or {}).get(str(selected["key"]))) is not None:
                annotators[record.user_id] = record.user.display_name
    scopes = [metric_scope(cases, models, str(selected["key"]), None, "总体")]
    scopes.extend(metric_scope(cases, models, str(selected["key"]), user_id, label) for user_id, label in sorted(annotators.items(), key=lambda item: item[1]))
    return {
        "dimension": {"key": str(selected["key"]), "label": str(selected.get("label") or selected["key"]), "min": selected.get("min", 1), "max": selected.get("max", 10)},
        "dimensions": [{"key": str(item["key"]), "label": str(item.get("label") or item["key"]), "min": item.get("min", 1), "max": item.get("max", 10)} for item in dimensions],
        "models": models,
        "total_case_count": len(cases),
        "scopes": scopes,
    }


def ensure_project_access(project_id: int, user: User, db: Session) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    if user.role != "admin" and project_config(project)["archived"]:
        raise HTTPException(403, "项目已归档")
    if user.role != "admin" and not db.scalar(select(ProjectMember.id).where(ProjectMember.project_id == project_id, ProjectMember.user_id == user.id)):
        raise HTTPException(403, "你不是该项目成员")
    return project


def ensure_case_access(case: Case, user: User, db: Session) -> None:
    if user.role == "admin":
        return
    if project_config(case.project)["archived"]:
        raise HTTPException(403, "项目已归档")
    if not db.scalar(select(ProjectMember.id).where(ProjectMember.project_id == case.project_id, ProjectMember.user_id == user.id)):
        raise HTTPException(403, "你不是该项目成员")
    if not db.scalar(select(CaseAssignment.id).where(CaseAssignment.case_id == case.id, CaseAssignment.user_id == user.id)):
        raise HTTPException(403, "该 Case 未分配给你")


def ensure_assignable_user(project_id: int, user_id: int, db: Session) -> User:
    user = db.get(User, user_id)
    if not user or not user.active or user.role != "annotator":
        raise HTTPException(422, "只能分配给有效标注员")
    if not db.scalar(select(ProjectMember.id).where(ProjectMember.project_id == project_id, ProjectMember.user_id == user_id)):
        raise HTTPException(422, "请先将该用户加入项目成员")
    return user


def current_user(request: Request, db: DB) -> User:
    token = request.cookies.get("case_lens_session")
    if not token:
        raise HTTPException(401, "未登录")
    login = db.scalar(select(LoginSession).where(LoginSession.token_hash == session_hash(token)))
    if not login or login.expires_at.replace(tzinfo=timezone.utc) <= utcnow() or not login.user.active:
        raise HTTPException(401, "登录已失效")
    return login.user


CurrentUser = Annotated[User, Depends(current_user)]


def require_admin(user: CurrentUser) -> User:
    if user.role != "admin":
        raise HTTPException(403, "需要管理员权限")
    return user


AdminUser = Annotated[User, Depends(require_admin)]


def validate_annotation(case: Case, body: AnnotationBody) -> None:
    if body.status not in {"draft", "submitted"}:
        raise HTTPException(422, "status 只能是 draft 或 submitted")
    candidate_ids = {str(item.get("id")) for item in case.payload.get("candidates", []) if isinstance(item, dict)}
    if not candidate_ids:
        raise HTTPException(422, "该 Case 没有 candidates")
    dimensions = case.payload.get("annotation_config", {}).get("dimensions", [])
    for dimension in dimensions:
        if not isinstance(dimension, dict) or dimension.get("key") not in body.scores:
            continue
        key = str(dimension["key"])
        score = body.scores[key]
        minimum = int(dimension.get("min", 1))
        maximum = int(dimension.get("max", 5))
        if isinstance(score, bool) or not isinstance(score, int) or score < minimum or score > maximum:
            raise HTTPException(422, f"{key} 评分必须是 {minimum}–{maximum} 的整数")
    if body.status == "submitted":
        required = [item.get("key") for item in dimensions if isinstance(item, dict) and item.get("required", True)]
        missing = [key for key in required if key not in body.scores]
        if missing:
            raise HTTPException(422, f"缺少必填评分：{', '.join(missing)}")


def candidate_model_map(payload: dict[str, Any]) -> dict[str, str]:
    return {
        str(item.get("id")): str(item.get("model", "")).strip()
        for item in payload.get("candidates", [])
        if isinstance(item, dict) and item.get("id") is not None
    }


def annotation_candidate_remaps(case: Case, next_payload: dict[str, Any]) -> list[tuple[Annotation, str]]:
    """Map annotations to the updated candidate IDs without silently changing model identity."""
    previous_candidates = candidate_model_map(case.payload)
    next_candidates = candidate_model_map(next_payload)
    next_ids_by_model: dict[str, list[str]] = {}
    for candidate_id, model in next_candidates.items():
        next_ids_by_model.setdefault(model, []).append(candidate_id)

    remaps: list[tuple[Annotation, str]] = []
    target_keys: set[tuple[int, str]] = set()
    for record in case.annotations:
        previous_model = previous_candidates.get(record.candidate_id)
        if previous_model is None:
            raise ValueError(f"历史标注引用了未知 candidate_id：{record.candidate_id}")
        if record.candidate_id in next_candidates:
            if next_candidates[record.candidate_id] != previous_model:
                raise ValueError(
                    f"candidate_id {record.candidate_id} 的模型由 {previous_model} 变为 {next_candidates[record.candidate_id]}，无法安全保留标注"
                )
            target_id = record.candidate_id
        else:
            model_matches = next_ids_by_model.get(previous_model, [])
            if len(model_matches) != 1:
                raise ValueError(
                    f"已标注候选 {record.candidate_id}（{previous_model}）在新文件中没有唯一对应项；请保持 candidate_id 不变"
                )
            target_id = model_matches[0]
        target_key = (record.user_id, target_id)
        if target_key in target_keys:
            raise ValueError(f"候选迁移后会产生重复标注：{target_id}")
        target_keys.add(target_key)
        if target_id != record.candidate_id:
            remaps.append((record, target_id))
    return remaps


app = FastAPI(title="Case Lens API", version="1.0.0", docs_url="/api/docs", openapi_url="/api/openapi.json")


@app.on_event("startup")
def startup() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "uploads").mkdir(exist_ok=True)
    (DATA_DIR / "exports").mkdir(exist_ok=True)
    Base.metadata.create_all(engine)
    username = os.getenv("ADMIN_USERNAME", "admin")
    password = os.getenv("ADMIN_PASSWORD")
    with SessionLocal() as db:
        if not db.scalar(select(User).where(User.username == username)):
            if not password:
                raise RuntimeError("首次启动必须设置 ADMIN_PASSWORD")
            db.add(User(username=username, display_name=os.getenv("ADMIN_DISPLAY_NAME", "管理员"), password_hash=hash_password(password), role="admin"))
            db.commit()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/auth/login")
def login(body: LoginBody, response: Response, db: DB) -> dict[str, Any]:
    user = db.scalar(select(User).where(User.username == body.username))
    if not user or not user.active or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "用户名或密码错误")
    token = secrets.token_urlsafe(32)
    db.add(LoginSession(token_hash=session_hash(token), user_id=user.id, expires_at=utcnow() + timedelta(hours=SESSION_HOURS)))
    db.commit()
    response.set_cookie("case_lens_session", token, max_age=SESSION_HOURS * 3600, httponly=True, samesite="strict", secure=SECURE_COOKIES, path="/")
    return {"user": user_dict(user)}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response, db: DB) -> dict[str, bool]:
    token = request.cookies.get("case_lens_session")
    if token:
        db.execute(delete(LoginSession).where(LoginSession.token_hash == session_hash(token)))
        db.commit()
    response.delete_cookie("case_lens_session", path="/")
    return {"ok": True}


@app.get("/api/auth/me")
def me(user: CurrentUser) -> dict[str, Any]:
    return {"user": user_dict(user)}


@app.get("/api/pet")
def get_pet(user: CurrentUser, db: DB) -> dict[str, Any]:
    profile, progress = get_or_create_pet(db, user.id)
    db.commit()
    return pet_dict(profile, progress)


@app.put("/api/pet")
def update_pet(body: PetProfileUpdate, user: CurrentUser, db: DB) -> dict[str, Any]:
    profile, progress = get_or_create_pet(db, user.id)
    level = pet_level(progress.xp_units / 5)
    if body.color not in PET_COLORS:
        raise HTTPException(422, "未知的宠物颜色")
    if body.accessory not in PET_ACCESSORIES:
        raise HTTPException(422, "未知的宠物配饰")
    if PET_COLORS[body.color] > level or PET_ACCESSORIES[body.accessory] > level:
        raise HTTPException(422, "该装扮尚未解锁")
    profile.name = body.name.strip()
    profile.color = body.color
    profile.accessory = body.accessory
    profile.updated_at = utcnow()
    db.commit()
    return pet_dict(profile, progress)


@app.post("/api/pet/pet")
def pet_companion(user: CurrentUser, db: DB) -> dict[str, Any]:
    now = utcnow()
    hour_start = now.replace(minute=0, second=0, microsecond=0)
    hour_key = now.strftime("%Y-%m-%dT%H")
    hourly_event_keys = db.scalars(select(PetExperienceEvent.event_key).where(
        PetExperienceEvent.user_id == user.id,
        PetExperienceEvent.reason == "pet",
        PetExperienceEvent.created_at >= hour_start,
    )).all()
    # Legacy hourly pet events awarded 1 EXP, equivalent to five new touches.
    hourly_count = sum(5 if key == f"pet:{hour_key}" else 1 for key in hourly_event_keys)
    if hourly_count >= 10:
        profile, progress = get_or_create_pet(db, user.id)
        db.commit()
        return {"profile": pet_dict(profile, progress), "awarded": False, "amount": 0, "hourly_earned": 2, "hourly_remaining": 0}
    profile, progress, awarded, amount = grant_pet_experience(db, user.id, "pet", f"pet:{hour_key}:{hourly_count + 1}")
    db.commit()
    earned_count = hourly_count + (1 if awarded else 0)
    return {"profile": pet_dict(profile, progress), "awarded": awarded, "amount": amount, "hourly_earned": round(earned_count / 5, 1), "hourly_remaining": max(0, 10 - earned_count)}


@app.get("/api/users")
def list_users(_: AdminUser, db: DB) -> list[dict[str, Any]]:
    return [user_dict(user) for user in db.scalars(select(User).order_by(User.created_at)).all()]


@app.post("/api/users")
def create_user(body: UserCreate, _: AdminUser, db: DB) -> dict[str, Any]:
    if body.role not in {"admin", "annotator"}:
        raise HTTPException(422, "role 只能是 admin 或 annotator")
    if db.scalar(select(User).where(User.username == body.username)):
        raise HTTPException(409, "用户名已存在")
    user = User(username=body.username, display_name=body.display_name, password_hash=hash_password(body.password), role=body.role)
    db.add(user)
    db.commit()
    return user_dict(user)


@app.patch("/api/users/{user_id}")
def update_user(user_id: int, body: UserUpdate, admin: AdminUser, db: DB) -> dict[str, Any]:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "账号不存在")
    if body.active is False and user.id == admin.id:
        raise HTTPException(422, "不能停用当前登录的管理员账号")
    if body.display_name is not None:
        user.display_name = body.display_name.strip()
    if body.password is not None:
        user.password_hash = hash_password(body.password)
        db.execute(delete(LoginSession).where(LoginSession.user_id == user.id))
    if body.active is not None:
        user.active = body.active
        if not body.active:
            db.execute(delete(LoginSession).where(LoginSession.user_id == user.id))
            project_case_ids = select(Case.id).where(Case.project_id.in_(select(ProjectMember.project_id).where(ProjectMember.user_id == user.id)))
            db.execute(delete(CaseAssignment).where(CaseAssignment.user_id == user.id, CaseAssignment.case_id.in_(project_case_ids)))
    db.commit()
    return user_dict(user)


@app.get("/api/projects")
def list_projects(user: CurrentUser, db: DB) -> list[dict[str, Any]]:
    query = select(Project).order_by(Project.created_at.desc())
    if user.role != "admin":
        query = query.join(ProjectMember).where(ProjectMember.user_id == user.id)
    projects = db.scalars(query).all()
    if user.role != "admin":
        projects = [project for project in projects if not project_config(project)["archived"]]
    result = []
    for project in projects:
        if user.role == "admin":
            total = db.scalar(select(func.count(Case.id)).where(Case.project_id == project.id)) or 0
        else:
            total = db.scalar(select(func.count(Case.id)).join(CaseAssignment).where(Case.project_id == project.id, CaseAssignment.user_id == user.id)) or 0
        if user.role == "admin":
            progress_cases = db.scalars(select(Case).where(Case.project_id == project.id)).all()
        else:
            progress_cases = db.scalars(select(Case).join(CaseAssignment).where(Case.project_id == project.id, CaseAssignment.user_id == user.id)).all()
        submitted, _ = user_case_progress(progress_cases, user.id)
        result.append({"id": project.id, "name": project.name, "archived": project_config(project)["archived"], "annotation_config": project_config(project), "case_count": total, "my_submitted_count": submitted, "created_at": project.created_at.isoformat()})
    return result


@app.post("/api/projects")
def create_project(body: ProjectCreate, user: AdminUser, db: DB) -> dict[str, Any]:
    config = {"blind_mode": True, "lock_submitted": False, "archived": False, **body.annotation_config}
    project = Project(name=body.name, annotation_config=config, created_by=user.id)
    db.add(project)
    db.commit()
    return {"id": project.id, "name": project.name, "annotation_config": project_config(project)}


@app.patch("/api/projects/{project_id}")
def update_project(project_id: int, body: ProjectUpdate, _: AdminUser, db: DB) -> dict[str, Any]:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    if body.name is not None:
        project.name = body.name.strip()
    if body.archived is not None:
        project.annotation_config = {**(project.annotation_config or {}), "archived": body.archived}
    db.commit()
    return {"id": project.id, "name": project.name, "archived": project_config(project)["archived"], "annotation_config": project_config(project)}


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: int, _: AdminUser, db: DB, confirm_name: str = Query(min_length=1)) -> dict[str, bool]:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    if confirm_name != project.name:
        raise HTTPException(422, "项目名称确认不匹配")
    case_ids = select(Case.id).where(Case.project_id == project_id)
    db.execute(delete(Annotation).where(Annotation.case_id.in_(case_ids)))
    db.execute(delete(CaseAssignment).where(CaseAssignment.case_id.in_(case_ids)))
    db.execute(delete(ProjectMember).where(ProjectMember.project_id == project_id))
    db.execute(delete(Case).where(Case.project_id == project_id))
    db.delete(project)
    db.commit()
    return {"ok": True}


@app.patch("/api/projects/{project_id}/settings")
def update_project_settings(project_id: int, body: ProjectSettingsBody, _: AdminUser, db: DB) -> dict[str, Any]:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    next_config = {**(project.annotation_config or {}), "blind_mode": body.blind_mode, "lock_submitted": body.lock_submitted}
    if body.dimensions is not None:
        if not body.dimensions:
            raise HTTPException(422, "至少保留一个评分维度")
        keys = [str(item.get("key", "")).strip() for item in body.dimensions]
        if any(not key for key in keys) or len(keys) != len(set(keys)):
            raise HTTPException(422, "评分维度 key 不能为空或重复")
        for item in body.dimensions:
            minimum = item.get("min", 1)
            maximum = item.get("max", 5)
            if not isinstance(minimum, int) or isinstance(minimum, bool) or not isinstance(maximum, int) or isinstance(maximum, bool) or minimum < 0 or maximum <= minimum or maximum - minimum > 10:
                raise HTTPException(422, "评分维度的 min/max 必须是合理整数范围")
        next_config["dimensions"] = body.dimensions
    if body.badcase_tags is not None:
        tags = list(dict.fromkeys(tag.strip() for tag in body.badcase_tags if tag.strip()))
        if not tags:
            raise HTTPException(422, "至少保留一个 Badcase 标签")
        next_config["badcase_tags"] = tags
    if body.model_order is not None:
        model_order = list(dict.fromkeys(value.strip() for value in body.model_order if value.strip()))
        if len(model_order) > 1000 or any(len(value) > 240 for value in model_order):
            raise HTTPException(422, "模型展示顺序最多 1000 项，且每项不能超过 240 个字符")
        next_config["model_order"] = model_order
    project.annotation_config = next_config
    for case in db.scalars(select(Case).where(Case.project_id == project_id)).all():
        case.payload = {**case.payload, "annotation_config": next_config}
    db.commit()
    return {"annotation_config": project_config(project)}


@app.get("/api/projects/{project_id}/members")
def project_members(project_id: int, _: AdminUser, db: DB) -> list[dict[str, Any]]:
    if not db.get(Project, project_id):
        raise HTTPException(404, "项目不存在")
    member_ids = set(db.scalars(select(ProjectMember.user_id).where(ProjectMember.project_id == project_id)).all())
    users = db.scalars(select(User).where(User.role == "annotator", User.active.is_(True)).order_by(User.display_name)).all()
    return [{**user_dict(user), "member": user.id in member_ids} for user in users]


@app.put("/api/projects/{project_id}/members")
def replace_project_members(project_id: int, body: ProjectMembersBody, _: AdminUser, db: DB) -> dict[str, Any]:
    if not db.get(Project, project_id):
        raise HTTPException(404, "项目不存在")
    requested = set(body.user_ids)
    valid = set(db.scalars(select(User.id).where(User.id.in_(requested), User.role == "annotator", User.active.is_(True))).all()) if requested else set()
    if valid != requested:
        raise HTTPException(422, "成员列表包含无效或非标注员账号")
    current = set(db.scalars(select(ProjectMember.user_id).where(ProjectMember.project_id == project_id)).all())
    removed = current - valid
    if removed:
        project_case_ids = select(Case.id).where(Case.project_id == project_id)
        db.execute(delete(CaseAssignment).where(CaseAssignment.case_id.in_(project_case_ids), CaseAssignment.user_id.in_(removed)))
        db.execute(delete(ProjectMember).where(ProjectMember.project_id == project_id, ProjectMember.user_id.in_(removed)))
    for user_id in valid - current:
        db.add(ProjectMember(project_id=project_id, user_id=user_id))
    db.commit()
    return {"member_count": len(valid), "removed_assignments_for_users": len(removed)}


@app.post("/api/projects/{project_id}/upload")
def upload_jsonl(project_id: int, _: AdminUser, db: DB, file: UploadFile = File(...), replace: bool = Form(False)) -> dict[str, Any]:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    safe_name = f"{project_id}-{utcnow().strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(4)}-{Path(file.filename or 'dataset.jsonl').name}"
    destination = DATA_DIR / "uploads" / safe_name
    max_bytes = MAX_UPLOAD_MB * 1024 * 1024
    uploaded_bytes = 0
    try:
        with destination.open("wb") as target:
            while chunk := file.file.read(1024 * 1024):
                uploaded_bytes += len(chunk)
                if uploaded_bytes > max_bytes:
                    raise HTTPException(413, f"文件超过 {MAX_UPLOAD_MB}MB 限制")
                target.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    parsed: list[tuple[int, str, dict[str, Any]]] = []
    errors: list[str] = []
    seen: set[str] = set()
    try:
        with destination.open("r", encoding="utf-8") as source:
            for line_number, line in enumerate(source, 1):
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                    if not isinstance(payload, dict):
                        raise ValueError("不是 JSON object")
                    external_id = str(payload.get("id") or f"line-{line_number}")
                    if external_id in seen:
                        raise ValueError("文件内 id 重复")
                    seen.add(external_id)
                    candidates = payload.get("candidates", [])
                    if not isinstance(candidates, list) or any(not isinstance(item, dict) for item in candidates):
                        raise ValueError("candidates 必须是 object 数组")
                    candidate_ids = [str(item.get("id", "")).strip() for item in candidates]
                    if any(not candidate_id for candidate_id in candidate_ids):
                        raise ValueError("candidate id 不能为空")
                    if len(candidate_ids) != len(set(candidate_ids)):
                        raise ValueError("candidate id 重复")
                    if not candidates:
                        raise ValueError("缺少 candidates，无法进行模型标注")
                    if any(not str(item.get("model", "")).strip() for item in candidates):
                        raise ValueError("candidate model 不能为空")
                    if any("response" not in item for item in candidates):
                        raise ValueError("candidate 缺少 response")
                    if "annotation_config" not in payload and project.annotation_config:
                        payload["annotation_config"] = project.annotation_config
                    payload.pop("annotations", None)
                    payload.pop("__server_case_id", None)
                    payload.pop("__assigned_user_ids", None)
                    parsed.append((line_number, external_id, payload))
                except (json.JSONDecodeError, TypeError, ValueError) as exc:
                    errors.append(f"第 {line_number} 行：{exc}")
                    if len(errors) >= 100:
                        break
    except UnicodeError as exc:
        destination.unlink(missing_ok=True)
        raise HTTPException(422, {"message": "文件编码错误：请上传 UTF-8 编码的 JSONL", "errors": [str(exc)]}) from exc
    if not parsed and not errors:
        errors.append("文件中没有可导入的 JSONL 数据")
    if errors:
        destination.unlink(missing_ok=True)
        raise HTTPException(422, {"message": "文件校验失败，旧项目数据未修改", "errors": errors})
    if not replace:
        existing_ids = set(db.scalars(select(Case.external_id).where(Case.project_id == project_id, Case.external_id.in_([item[1] for item in parsed]))).all())
        if existing_ids:
            destination.unlink(missing_ok=True)
            raise HTTPException(409, f"项目中已存在 {len(existing_ids)} 个相同 Case ID，旧项目数据未修改")
    existing_cases: dict[str, Case] = {}
    remap_plan: list[tuple[Annotation, str]] = []
    compatibility_errors: list[str] = []
    preserved_annotations = 0
    preserved_assignments = 0
    if replace:
        existing = db.scalars(
            select(Case)
            .where(Case.project_id == project_id)
            .options(selectinload(Case.annotations))
            .order_by(Case.ordinal)
        ).all()
        existing_cases = {case.external_id: case for case in existing}
        preserved_annotations = sum(len(case.annotations) for case in existing)
        preserved_assignments = db.scalar(
            select(func.count(CaseAssignment.id)).join(Case).where(Case.project_id == project_id)
        ) or 0
        for _, external_id, payload in parsed:
            case = existing_cases.get(external_id)
            if not case:
                continue
            try:
                remap_plan.extend(annotation_candidate_remaps(case, payload))
            except ValueError as exc:
                compatibility_errors.append(f"Case {external_id}：{exc}")
        if compatibility_errors:
            destination.unlink(missing_ok=True)
            raise HTTPException(
                409,
                {
                    "message": "更新文件与历史标注无法安全匹配，旧项目数据未修改",
                    "errors": compatibility_errors[:100],
                },
            )

    inserted = 0
    updated = 0
    unchanged = 0
    parsed_ids = {external_id for _, external_id, _ in parsed}
    retained = [case for external_id, case in existing_cases.items() if external_id not in parsed_ids]
    try:
        if replace:
            for record, target_id in remap_plan:
                record.candidate_id = target_id
            for line_number, external_id, payload in parsed:
                case = existing_cases.get(external_id)
                if case:
                    if case.payload == payload and case.ordinal == line_number:
                        unchanged += 1
                    else:
                        case.payload = payload
                        case.ordinal = line_number
                        updated += 1
                else:
                    db.add(Case(project_id=project_id, external_id=external_id, ordinal=line_number, payload=payload))
                    inserted += 1
            for offset, case in enumerate(retained, len(parsed) + 1):
                case.ordinal = offset
        else:
            for line_number, external_id, payload in parsed:
                db.add(Case(project_id=project_id, external_id=external_id, ordinal=line_number, payload=payload))
                inserted += 1
        db.commit()
    except Exception as exc:
        db.rollback()
        destination.unlink(missing_ok=True)
        raise HTTPException(409, f"写入失败，已回滚，旧项目数据保持不变：{exc}") from exc
    return {
        "inserted": inserted,
        "updated": updated,
        "unchanged": unchanged,
        "retained_not_in_file": len(retained),
        "preserved_annotations": preserved_annotations,
        "remapped_annotations": len(remap_plan),
        "preserved_assignments": preserved_assignments,
        "errors": [],
        "source_file": safe_name,
    }


@app.get("/api/projects/{project_id}/cases")
def project_cases(project_id: int, user: CurrentUser, db: DB, offset: int = 0, limit: int = 1000) -> dict[str, Any]:
    project = ensure_project_access(project_id, user, db)
    limit = min(max(limit, 1), 10_000)
    query = select(Case).where(Case.project_id == project_id)
    count_query = select(func.count(Case.id)).where(Case.project_id == project_id)
    if user.role != "admin":
        query = query.join(CaseAssignment).where(CaseAssignment.user_id == user.id)
        count_query = count_query.join(CaseAssignment).where(CaseAssignment.user_id == user.id)
    total = db.scalar(count_query) or 0
    cases = db.scalars(query.order_by(Case.ordinal).offset(offset).limit(limit)).all()
    config = project_config(project)
    items = []
    for case in cases:
        payload = dict(case.payload)
        payload["__server_case_id"] = case.id
        visible_annotations = case.annotations if user.role == "admin" or not config["blind_mode"] else [record for record in case.annotations if record.user_id == user.id]
        payload["annotations"] = [annotation_dict(record) for record in visible_annotations]
        if user.role == "admin":
            payload["__assigned_user_ids"] = [str(value) for value in db.scalars(select(CaseAssignment.user_id).where(CaseAssignment.case_id == case.id)).all()]
        items.append(payload)
    return {"items": items, "total": total, "offset": offset, "limit": limit, "blind_mode": config["blind_mode"]}


@app.get("/api/projects/{project_id}/metrics")
def project_metrics(project_id: int, user: CurrentUser, db: DB, dimension: str | None = Query(default=None, max_length=200)) -> dict[str, Any]:
    project = ensure_project_access(project_id, user, db)
    cases = db.scalars(
        select(Case)
        .where(Case.project_id == project_id)
        .options(selectinload(Case.annotations).selectinload(Annotation.user))
        .order_by(Case.ordinal)
    ).all()
    return project_metrics_payload(project, cases, dimension)


@app.get("/api/projects/{project_id}/assignment-overview")
def assignment_overview(project_id: int, _: AdminUser, db: DB) -> dict[str, Any]:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    total = db.scalar(select(func.count(Case.id)).where(Case.project_id == project_id)) or 0
    assigned_unique = db.scalar(select(func.count(func.distinct(CaseAssignment.case_id))).join(Case).where(Case.project_id == project_id)) or 0
    submitted_total = db.scalar(select(func.count(Annotation.id)).join(Case).where(Case.project_id == project_id, Annotation.status == "submitted")) or 0
    draft_total = db.scalar(select(func.count(Annotation.id)).join(Case).where(Case.project_id == project_id, Annotation.status == "draft")) or 0
    members = []
    rows = db.execute(select(ProjectMember.user_id, User.username, User.display_name).join(User, User.id == ProjectMember.user_id).where(ProjectMember.project_id == project_id).order_by(User.display_name)).all()
    for user_id, username, display_name in rows:
        assigned_rows = db.execute(select(Case.id, Case.external_id).join(CaseAssignment).where(Case.project_id == project_id, CaseAssignment.user_id == user_id).order_by(Case.ordinal)).all()
        assigned_ids = [row[0] for row in assigned_rows]
        assigned_cases = db.scalars(select(Case).where(Case.id.in_(assigned_ids))).all() if assigned_ids else []
        submitted, drafts = user_case_progress(assigned_cases, user_id)
        members.append({"id": str(user_id), "username": username, "display_name": display_name, "assigned_count": len(assigned_rows), "submitted_count": submitted, "draft_count": drafts, "external_ids": [row[1] for row in assigned_rows]})
    return {"total_cases": total, "assigned_cases": assigned_unique, "unassigned_cases": max(0, total - assigned_unique), "submitted_annotations": submitted_total, "draft_annotations": draft_total, "members": members, "settings": project_config(project)}


@app.post("/api/projects/{project_id}/assignments/explicit")
def assign_explicit(project_id: int, body: ExplicitAssignmentBody, admin: AdminUser, db: DB) -> dict[str, Any]:
    if not db.get(Project, project_id):
        raise HTTPException(404, "项目不存在")
    ensure_assignable_user(project_id, body.user_id, db)
    external_ids = list(dict.fromkeys(value.strip() for value in body.external_ids if value.strip()))
    cases = db.scalars(select(Case).where(Case.project_id == project_id, Case.external_id.in_(external_ids))).all()
    found = {case.external_id for case in cases}
    missing = [value for value in external_ids if value not in found]
    if body.replace_existing and missing:
        raise HTTPException(422, f"替换操作已取消：有 {len(missing)} 个 Case ID 不存在")
    if body.replace_existing:
        project_case_ids = select(Case.id).where(Case.project_id == project_id)
        db.execute(delete(CaseAssignment).where(CaseAssignment.case_id.in_(project_case_ids), CaseAssignment.user_id == body.user_id))
    current = set(db.scalars(select(CaseAssignment.case_id).where(CaseAssignment.user_id == body.user_id, CaseAssignment.case_id.in_([case.id for case in cases]))).all()) if cases else set()
    for case in cases:
        if case.id not in current:
            db.add(CaseAssignment(case_id=case.id, user_id=body.user_id, assigned_by=admin.id))
    db.commit()
    assigned = db.scalar(select(func.count(CaseAssignment.id)).join(Case).where(Case.project_id == project_id, CaseAssignment.user_id == body.user_id)) or 0
    return {"added_count": len(cases) - len(current), "assigned_count": assigned, "missing_external_ids": missing}


@app.post("/api/projects/{project_id}/assignments/random")
def assign_random(project_id: int, body: RandomAssignmentBody, admin: AdminUser, db: DB) -> dict[str, Any]:
    if not db.get(Project, project_id):
        raise HTTPException(404, "项目不存在")
    ensure_assignable_user(project_id, body.user_id, db)
    project_case_ids = select(Case.id).where(Case.project_id == project_id)
    if body.replace_existing:
        db.execute(delete(CaseAssignment).where(CaseAssignment.case_id.in_(project_case_ids), CaseAssignment.user_id == body.user_id))
        db.flush()
    own_assigned = select(CaseAssignment.case_id).where(CaseAssignment.user_id == body.user_id)
    query = select(Case).where(Case.project_id == project_id, Case.id.not_in(own_assigned))
    if not body.allow_overlap:
        any_assigned = select(CaseAssignment.case_id)
        query = query.where(Case.id.not_in(any_assigned))
    cases = db.scalars(query.order_by(func.random()).limit(body.quantity)).all()
    for case in cases:
        db.add(CaseAssignment(case_id=case.id, user_id=body.user_id, assigned_by=admin.id))
    db.commit()
    assigned = db.scalar(select(func.count(CaseAssignment.id)).join(Case).where(Case.project_id == project_id, CaseAssignment.user_id == body.user_id)) or 0
    return {"requested_count": body.quantity, "added_count": len(cases), "assigned_count": assigned, "available_shortfall": max(0, body.quantity - len(cases))}


@app.post("/api/projects/{project_id}/assignments/remove")
def remove_assignments(project_id: int, body: AssignmentRemovalBody, _: AdminUser, db: DB) -> dict[str, int]:
    if not db.get(Project, project_id):
        raise HTTPException(404, "项目不存在")
    case_query = select(Case.id).where(Case.project_id == project_id)
    external_ids = list(dict.fromkeys(value.strip() for value in body.external_ids if value.strip()))
    if external_ids:
        case_query = case_query.where(Case.external_id.in_(external_ids))
    case_ids = list(db.scalars(case_query).all())
    if external_ids and len(case_ids) != len(external_ids):
        raise HTTPException(422, "取消失败：列表中包含不存在的 Case ID")
    assignment_query = select(CaseAssignment.id).where(CaseAssignment.case_id.in_(case_ids))
    if body.user_id is not None:
        assignment_query = assignment_query.where(CaseAssignment.user_id == body.user_id)
    assignment_ids = list(db.scalars(assignment_query).all()) if case_ids else []
    if assignment_ids:
        db.execute(delete(CaseAssignment).where(CaseAssignment.id.in_(assignment_ids)))
    deleted_annotations = 0
    if body.delete_annotations and case_ids:
        annotation_query = select(Annotation.id).where(Annotation.case_id.in_(case_ids))
        if body.user_id is not None:
            annotation_query = annotation_query.where(Annotation.user_id == body.user_id)
        annotation_ids = list(db.scalars(annotation_query).all())
        deleted_annotations = len(annotation_ids)
        if annotation_ids:
            db.execute(delete(Annotation).where(Annotation.id.in_(annotation_ids)))
    db.commit()
    return {"removed_assignments": len(assignment_ids), "deleted_annotations": deleted_annotations}


@app.put("/api/cases/{case_id}/annotations/{candidate_id}")
def save_annotation(case_id: int, candidate_id: str, body: AnnotationBody, user: CurrentUser, db: DB) -> dict[str, Any]:
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(404, "Case 不存在")
    ensure_case_access(case, user, db)
    candidate_ids = {str(item.get("id")) for item in case.payload.get("candidates", []) if isinstance(item, dict)}
    if candidate_id not in candidate_ids:
        raise HTTPException(404, "候选模型不存在")
    validate_annotation(case, body)
    record = db.scalar(select(Annotation).where(Annotation.case_id == case_id, Annotation.candidate_id == candidate_id, Annotation.user_id == user.id))
    if record and record.status == "submitted" and project_config(case.project)["lock_submitted"] and user.role != "admin":
        raise HTTPException(423, "该标注已提交并锁定，请联系管理员退回")
    if record and body.revision is not None and record.revision != body.revision:
        raise HTTPException(409, {"message": "标注已被其他页面更新", "current": annotation_dict(record)})
    if not record:
        record = Annotation(case_id=case_id, candidate_id=candidate_id, user_id=user.id)
        db.add(record)
    record.scores = body.scores
    record.badcase = body.badcase
    record.badcase_tags = body.badcase_tags if body.badcase else []
    record.note = body.note
    record.status = body.status
    record.revision = (record.revision or 0) + 1
    record.updated_at = utcnow()
    if body.status == "submitted":
        event_suffix = f"{case_id}:{candidate_id}"
        grant_pet_experience(db, user.id, "annotation", f"annotation:{event_suffix}")
        if body.badcase:
            grant_pet_experience(db, user.id, "badcase", f"badcase:{event_suffix}")
    db.commit()
    db.refresh(record)
    return annotation_dict(record)


@app.post("/api/annotations/{annotation_id}/return")
def return_annotation(annotation_id: int, _: AdminUser, db: DB) -> dict[str, Any]:
    record = db.get(Annotation, annotation_id)
    if not record:
        raise HTTPException(404, "标注记录不存在")
    record.status = "draft"
    record.revision = (record.revision or 0) + 1
    record.updated_at = utcnow()
    db.commit()
    db.refresh(record)
    return annotation_dict(record)


@app.get("/api/projects/{project_id}/progress")
def progress(project_id: int, user: CurrentUser, db: DB) -> dict[str, Any]:
    project = ensure_project_access(project_id, user, db)
    if user.role == "admin":
        progress_cases = db.scalars(select(Case).where(Case.project_id == project_id)).all()
    else:
        progress_cases = db.scalars(select(Case).join(CaseAssignment).where(Case.project_id == project_id, CaseAssignment.user_id == user.id)).all()
    total = len(progress_cases)
    submitted_cases, draft_cases = user_case_progress(progress_cases, user.id)
    badcase_query = select(func.count(func.distinct(Annotation.case_id))).join(Case).where(Case.project_id == project_id, Annotation.badcase.is_(True))
    if user.role != "admin" and project_config(project)["blind_mode"]:
        badcase_query = badcase_query.where(Annotation.user_id == user.id)
    badcases = db.scalar(badcase_query) or 0
    return {"total_cases": total, "my_submitted_cases": submitted_cases, "my_draft_cases": draft_cases, "badcase_count": badcases}


@app.get("/api/projects/{project_id}/export")
def export_project(project_id: int, _: AdminUser, db: DB, include_drafts: bool = True, view: str = Query(default="full", pattern="^(full|records)$")):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")

    def generate():
        for case in db.scalars(select(Case).where(Case.project_id == project_id).order_by(Case.ordinal)).all():
            records = [record for record in case.annotations if include_drafts or record.status == "submitted"]
            if view == "records":
                for record in records:
                    yield json.dumps({"project_id": project_id, "project_name": project.name, "case_id": case.external_id, **annotation_dict(record)}, ensure_ascii=False, separators=(",", ":")) + "\n"
                continue
            payload = dict(case.payload)
            payload["schema_version"] = payload.get("schema_version", "case-lens.annotation.v1")
            payload["annotations"] = [annotation_dict(record) for record in records]
            yield json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"

    filename = f"project-{project_id}-{'annotations' if view == 'records' else 'annotated'}.jsonl"
    return StreamingResponse(generate(), media_type="application/x-ndjson", headers={"Content-Disposition": f'attachment; filename="{filename}"'})
