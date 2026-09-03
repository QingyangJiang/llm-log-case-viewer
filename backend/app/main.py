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


DEFAULT_DECOMPOSER_PROMPT = """你是任务拆解专家。你看不到待评分的候选回复。请只把最新用户请求拆成可独立核查的任务，不要把工具、方法或格式约束单独拆成任务。结合 query 之后已经发生的 trajectory 判断进度：已完成标记为 done_before，否则为 pending。输出且只输出一个 JSON object：{\"full_goal\":\"中文目标\",\"current_stage\":\"中文阶段\",\"subtasks\":[{\"id\":1,\"desc\":\"中文任务\",\"phase\":\"done_before 或 pending\"}],\"decomposition_reasoning\":\"中文理由\"}。"""

DEFAULT_DETECTOR_PROMPT = """你是三阶段评测中的错误定位器，不负责最终评分。严格复用给定的固定子任务，不得增删或改写。结合 trajectory 判断当前回复应推进的步骤；正确的中间工具调用或等待用户不应因尚无最终结果而扣分。逐子任务输出 status（done/partial/missed/not_due）、可定位 findings 和 correct_points。每条 finding 包含 type（missing/error/irrelevant）、severity（serious/minor/none）、location 和中文 detail。输出且只输出一个 JSON object。"""

DEFAULT_VERIFIER_PROMPT = """你是三阶段评测的最终复核与评分器。先逐条复核 Stage 2 finding（confirm/overturn/adjust），再补充漏报，最后清除误报；不得重新拆解固定子任务。只按当前回复本轮应完成的 due 子任务评分，not_due 不进入分母。先定档再打整数分：Tier 1=8–10（完整完成），Tier 2=4–7（部分完成），Tier 3=1–3（未完成）。输出且只输出一个 JSON object，至少包含 subtasks、corrections、review_note、tier、score、score_rationale、reasoning、overall_comment。"""


def default_judge_config() -> dict[str, Any]:
    return {
        "protocol": "anthropic",
        "base_url": JUDGE_LOCAL_RELAY_BASE,
        "model_name": "DeepSeek-V4-Flash",
        "stage1_temperature": 0.0,
        "stage2_temperature": 0.0,
        "stage3_temperature": 0.1,
        "stage1_max_tokens": 4096,
        "stage2_max_tokens": 4096,
        "stage3_max_tokens": 4096,
        "concurrency": 2,
        "sample_count": 3,
        "adaptive_sampling": False,
        "input_limit": 0,
        "seed": 0,
        "timeout_seconds": 300,
        "max_retries": 1,
        "rubric": "Tier 1：8–10，完整完成；Tier 2：4–7，部分完成；Tier 3：1–3，未完成。",
        "decomposer_prompt": DEFAULT_DECOMPOSER_PROMPT,
        "detector_prompt": DEFAULT_DETECTOR_PROMPT,
        "verifier_prompt": DEFAULT_VERIFIER_PROMPT,
    }


class JudgeConfigBody(BaseModel):
    protocol: str = "anthropic"
    base_url: str = Field(min_length=1, max_length=2000)
    api_key: str | None = Field(default=None, max_length=10_000)
    model_name: str = Field(min_length=1, max_length=300)
    stage1_temperature: float = Field(default=0, ge=0, le=2)
    stage2_temperature: float = Field(default=0, ge=0, le=2)
    stage3_temperature: float = Field(default=0.1, ge=0, le=2)
    stage1_max_tokens: int = Field(default=4096, ge=128, le=131_072)
    stage2_max_tokens: int = Field(default=4096, ge=128, le=131_072)
    stage3_max_tokens: int = Field(default=4096, ge=128, le=131_072)
    concurrency: int = Field(default=2, ge=1, le=8)
    sample_count: int = Field(default=3, ge=1, le=9)
    adaptive_sampling: bool = False
    input_limit: int = Field(default=0, ge=0, le=2_000_000)
    seed: int = Field(default=0, ge=0, le=2_147_483_647)
    timeout_seconds: int = Field(default=300, ge=10, le=1800)
    max_retries: int = Field(default=1, ge=0, le=5)
    rubric: str = Field(default=default_judge_config()["rubric"], min_length=1, max_length=20_000)
    decomposer_prompt: str = Field(default=DEFAULT_DECOMPOSER_PROMPT, min_length=1, max_length=100_000)
    detector_prompt: str = Field(default=DEFAULT_DETECTOR_PROMPT, min_length=1, max_length=100_000)
    verifier_prompt: str = Field(default=DEFAULT_VERIFIER_PROMPT, min_length=1, max_length=100_000)


class JudgeRunBody(BaseModel):
    case_ids: list[int] = Field(default_factory=list, max_length=10_000)


class JudgeClientCandidateBody(BaseModel):
    candidate_id: str = Field(min_length=1, max_length=300)
    stage2_raw: str = Field(default="", max_length=2_000_000)
    stage3_raw: list[str] = Field(default_factory=list, max_length=11)
    error: str = Field(default="", max_length=2000)


class JudgeClientResultBody(BaseModel):
    case_id: int
    config_version: int = Field(ge=1)
    stage1_raw: str = Field(default="", max_length=2_000_000)
    candidates: list[JudgeClientCandidateBody] = Field(default_factory=list, max_length=1000)
    error: str = Field(default="", max_length=2000)


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


class PetEvolutionBody(BaseModel):
    spend: int = Field(ge=1, le=5)


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
PET_EVOLUTION_PATHS: dict[str, dict[str, Any]] = {
    "starlight": {"name": "星辉灵兽", "quality": "radiant", "traits": [["星尘额纹", "新月耳尖", "彗星小角"], ["月光羽翼", "星轨尾焰", "银河披风"], ["星环冠冕", "极光领域", "星核辉光"]]},
    "guardian": {"name": "守护机甲", "quality": "bold", "traits": [["合金耳甲", "战术目镜", "棱镜面罩"], ["折叠钢翼", "推进尾翼", "护盾肩甲"], ["量子核心", "冠军冠冕", "脉冲力场"]]},
    "forest": {"name": "森灵幻兽", "quality": "gentle", "traits": [["新芽鹿角", "苔藓耳尖", "花蕾额纹"], ["叶脉羽翼", "花藤披风", "蒲公英尾"], ["萤火光环", "古树冠冕", "四季领域"]]},
    "storm": {"name": "风暴精灵", "quality": "electric", "traits": [["闪电耳羽", "雷云额纹", "电光小角"], ["疾风羽翼", "旋风尾环", "雷霆披风"], ["风眼冠冕", "暴雨领域", "蓝电核心"]]},
    "wonky": {"name": "歪歪异变体", "quality": "awkward", "traits": [["参差尖牙", "皱皱触角", "大小眼花纹"], ["斑驳小翅膀", "歪斜尾鳍", "补丁披风"], ["倾斜纸冠", "毛边光圈", "咕嘟气泡场"]]},
}
PET_MAX_EVOLUTION_STAGE = 3


def pet_level(xp: float) -> int:
    return int((max(0, xp) / 20) ** 0.5) + 1


def get_or_create_pet(db: Session, user_id: int) -> tuple[PetProfile, PetProgressV2, PetEvolution]:
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
    level = pet_level(progress.xp_units / 5)
    evolution = db.get(PetEvolution, user_id)
    if not evolution:
        evolution = PetEvolution(user_id=user_id, available_chances=max(0, level - 1), credited_level=level)
        db.add(evolution)
        db.flush()
    elif level > evolution.credited_level:
        evolution.available_chances += level - evolution.credited_level
        evolution.credited_level = level
        evolution.updated_at = utcnow()
    return profile, progress, evolution


def pet_title(level: int) -> str:
    return next(title for required, title in reversed(PET_LEVEL_TITLES.items()) if level >= required)


def pet_dict(profile: PetProfile, progress: PetProgressV2, evolution: PetEvolution) -> dict[str, Any]:
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
        "evolution_chances": evolution.available_chances,
        "evolution_credited_level": evolution.credited_level,
        "evolution_stage": evolution.stage,
        "evolution_path": evolution.path,
        "evolution_name": PET_EVOLUTION_PATHS.get(evolution.path, {}).get("name", "未变身"),
        "evolution_quality": PET_EVOLUTION_PATHS.get(evolution.path, {}).get("quality", "base"),
        "evolution_variant": evolution.variant_seed,
        "evolution_traits": evolution.traits or [],
        "evolution_history": evolution.history or [],
    }


def grant_pet_experience(db: Session, user_id: int, reason: str, event_key: str) -> tuple[PetProfile, PetProgressV2, PetEvolution, bool, float]:
    profile, progress, evolution = get_or_create_pet(db, user_id)
    if db.scalar(select(PetExperienceEvent.id).where(PetExperienceEvent.user_id == user_id, PetExperienceEvent.event_key == event_key)):
        return profile, progress, evolution, False, 0
    units = PET_XP_UNITS[reason]
    db.add(PetExperienceEvent(user_id=user_id, event_key=event_key, reason=reason, amount=units))
    progress.xp_units += units
    progress.updated_at = utcnow()
    profile.updated_at = utcnow()
    next_level = pet_level(progress.xp_units / 5)
    if next_level > evolution.credited_level:
        evolution.available_chances += next_level - evolution.credited_level
        evolution.credited_level = next_level
        evolution.updated_at = utcnow()
    return profile, progress, evolution, True, round(units / 5, 1)


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


def project_metric_dimensions(config: dict[str, Any], cases: list[Case]) -> list[dict[str, Any]]:
    dimensions: list[dict[str, Any]] = []
    seen: set[str] = set()

    def append_dimension(value: Any) -> None:
        if not isinstance(value, dict) or not value.get("key"):
            return
        key = str(value["key"])
        if key in seen:
            return
        seen.add(key)
        dimensions.append({
            "key": key,
            "label": str(value.get("label") or key),
            "min": value.get("min", 1),
            "max": value.get("max", 10),
        })

    for item in config.get("dimensions", []):
        append_dimension(item)
    for case in cases:
        case_config = case.payload.get("annotation_config", {})
        if isinstance(case_config, dict):
            for item in case_config.get("dimensions", []):
                append_dimension(item)
    for case in cases:
        for record in case.annotations:
            for key in (record.scores or {}):
                append_dimension({"key": key, "label": key, "min": 1, "max": 10})
    if not dimensions:
        append_dimension({"key": "correctness", "label": "正确性", "min": 1, "max": 10})
    return dimensions


def project_metrics_payload(project: Project, cases: list[Case], dimension_key: str | None = None) -> dict[str, Any]:
    config = project_config(project)
    dimensions = project_metric_dimensions(config, cases)
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


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def judge_case_content(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if key not in {"candidates", "annotations", "annotation_config"} and not key.startswith("__")
    }


def judge_candidate_content(candidate: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in candidate.items() if not key.startswith("__")}


def judge_config_signature(config: dict[str, Any]) -> str:
    return canonical_hash(config)


def active_judge_config(db: Session, project_id: int) -> JudgeConfigVersion | None:
    return db.scalar(
        select(JudgeConfigVersion)
        .where(JudgeConfigVersion.project_id == project_id, JudgeConfigVersion.active.is_(True))
        .order_by(JudgeConfigVersion.version.desc())
    )


def judge_config_payload(record: JudgeConfigVersion | None, include_details: bool = True) -> dict[str, Any]:
    if not record:
        config = default_judge_config() if include_details else {
            "protocol": default_judge_config()["protocol"],
            "model_name": default_judge_config()["model_name"],
        }
        return {**config, "configured": False, "has_api_key": False, "version": 0}
    summary = {
        "protocol": record.config.get("protocol", "anthropic"),
        "model_name": record.config.get("model_name", ""),
        "configured": True,
        "has_api_key": bool(record.api_key) if include_details else False,
        "version": record.version,
        "signature": record.signature,
        "created_at": record.created_at.isoformat(),
    }
    if not include_details:
        return summary
    return {
        **record.config,
        **summary,
    }


def text_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def judge_case_sections(payload: dict[str, Any]) -> dict[str, str]:
    messages = payload.get("messages") if isinstance(payload.get("messages"), list) else []
    last_user = -1
    for index, message in enumerate(messages):
        if isinstance(message, dict) and str(message.get("role", "")).lower() == "user":
            last_user = index
    if last_user >= 0:
        context = messages[:last_user]
        query = messages[last_user].get("content") if isinstance(messages[last_user], dict) else messages[last_user]
        trajectory = messages[last_user + 1:]
    else:
        context, trajectory = messages, []
        query = payload.get("query", "(未找到 user 消息)")
    refer_info = payload.get("refer_info")
    reference_answer = refer_info.get("reference_answer") if isinstance(refer_info, dict) else None
    if reference_answer is None:
        reference_answer = payload.get("reference_answer", refer_info if refer_info is not None else "(未提供)")
    return {
        "context": text_value(context) if context else "(无前置上下文)",
        "query": text_value(query),
        "trajectory": text_value(trajectory) if trajectory else "(无后续轨迹)",
        "tools": text_value(payload.get("tools", [])) if payload.get("tools") else "(未提供)",
        "reference_answer": text_value(reference_answer),
    }


def clip_judge_text(value: str, token_limit: int) -> str:
    if token_limit <= 0:
        return value
    char_limit = max(1000, token_limit * 4)
    if len(value) <= char_limit:
        return value
    head = int(char_limit * 0.7)
    tail = char_limit - head
    return f"{value[:head]}\n\n[... 输入按配置截断 ...]\n\n{value[-tail:]}"


def parse_json_object(raw: str) -> dict[str, Any]:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end <= start:
            return {"raw_output": raw, "parse_error": "模型未返回 JSON object"}
        try:
            value = json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError as exc:
            return {"raw_output": raw, "parse_error": f"JSON 解析失败：{exc}"}
    return value if isinstance(value, dict) else {"result": value, "parse_error": "模型返回的顶层不是 JSON object"}


def require_judge_object(value: dict[str, Any], stage: str) -> dict[str, Any]:
    if value.get("parse_error"):
        raise ValueError(f"{stage}结构化输出无效：{value['parse_error']}")
    return value


def redact_judge_error(error: Exception | str, api_key: str = "") -> str:
    message = str(error)
    if api_key:
        message = message.replace(api_key, "***")
    for marker in ("Authorization: Bearer ", "authorization: bearer ", "x-api-key: ", '"x-api-key":"'):
        start = message.lower().find(marker.lower())
        if start < 0:
            continue
        value_start = start + len(marker)
        value_end = len(message)
        for terminator in ('"', "'", "\n", "\r", ",", " "):
            candidate = message.find(terminator, value_start)
            if candidate >= 0:
                value_end = min(value_end, candidate)
        message = f"{message[:value_start]}***{message[value_end:]}"
    return message[:2000]


def model_endpoint(base_url: str, protocol: str) -> str:
    cleaned = base_url.strip().rstrip("/；; ")
    suffix = "/messages" if protocol == "anthropic" else "/chat/completions"
    return cleaned if cleaned.endswith(suffix) else f"{cleaned}{suffix}"


def call_judge_model(config: dict[str, Any], api_key: str, system_prompt: str, user_prompt: str, temperature: float, max_tokens: int) -> str:
    protocol = str(config.get("protocol", "anthropic")).lower()
    endpoint = model_endpoint(str(config.get("base_url", "")), protocol)
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if protocol == "anthropic":
        headers.update({"x-api-key": api_key, "anthropic-version": "2023-06-01"})
        body: dict[str, Any] = {
            "model": config["model_name"],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }
    else:
        headers["Authorization"] = f"Bearer {api_key}"
        body = {
            "model": config["model_name"],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        }
        if int(config.get("seed", 0)):
            body["seed"] = int(config["seed"])
    request = urllib.request.Request(endpoint, data=json.dumps(body, ensure_ascii=False).encode("utf-8"), headers=headers, method="POST")
    attempts = int(config.get("max_retries", 1)) + 1
    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=int(config.get("timeout_seconds", 300))) as response:
                data = json.loads(response.read().decode("utf-8"))
            if protocol == "anthropic":
                parts = data.get("content", [])
                content = "".join(str(item.get("text", "")) for item in parts if isinstance(item, dict) and item.get("type") == "text")
            else:
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                if isinstance(content, list):
                    content = "".join(str(item.get("text", "")) for item in content if isinstance(item, dict))
            if not str(content).strip():
                raise ValueError("模型返回内容为空")
            return str(content)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1500]
            last_error = RuntimeError(f"上游模型返回 HTTP {exc.code}：{detail}")
            if exc.code not in {408, 409, 429, 500, 502, 503, 504}:
                break
        except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            last_error = exc
    raise RuntimeError(str(last_error or "模型调用失败"))


def stage1_user_prompt(payload: dict[str, Any], token_limit: int) -> str:
    sections = judge_case_sections(payload)
    value = f"""请拆解以下 Case。\n\n=== CONTEXT ===\n{sections['context']}\n\n=== QUERY ===\n{sections['query']}\n\n=== TRAJECTORY ===\n{sections['trajectory']}\n\n=== TOOLS ===\n{sections['tools']}\n\n=== REFERENCE ANSWER ===\n{sections['reference_answer']}"""
    return clip_judge_text(value, token_limit)


def stage2_user_prompt(payload: dict[str, Any], candidate: dict[str, Any], stage1: dict[str, Any], token_limit: int) -> str:
    sections = judge_case_sections(payload)
    value = f"""请定位候选回复在固定子任务上的问题。\n\n=== FIXED SUBTASKS ===\n{text_value(stage1.get('subtasks', []))}\n\n=== STAGE 1 NOTES ===\n{text_value(stage1)}\n\n=== CONTEXT ===\n{sections['context']}\n\n=== QUERY ===\n{sections['query']}\n\n=== TRAJECTORY ===\n{sections['trajectory']}\n\n=== TOOLS ===\n{sections['tools']}\n\n=== REFERENCE ANSWER ===\n{sections['reference_answer']}\n\n=== CANDIDATE RESPONSE ===\n{text_value({'reasoning': candidate.get('reasoning'), 'response': candidate.get('response')})}"""
    return clip_judge_text(value, token_limit)


def stage3_user_prompt(payload: dict[str, Any], candidate: dict[str, Any], stage1: dict[str, Any], stage2: dict[str, Any], config: dict[str, Any], token_limit: int) -> str:
    sections = judge_case_sections(payload)
    value = f"""请复核错误定位并给出最终档位和整数分。\n\n=== RUBRIC ===\n{config.get('rubric')}\n\n=== FIXED SUBTASKS / STAGE 1 ===\n{text_value(stage1)}\n\n=== STAGE 2 LOCALIZATION ===\n{text_value(stage2)}\n\n=== CONTEXT ===\n{sections['context']}\n\n=== QUERY ===\n{sections['query']}\n\n=== TRAJECTORY ===\n{sections['trajectory']}\n\n=== TOOLS ===\n{sections['tools']}\n\n=== REFERENCE ANSWER ===\n{sections['reference_answer']}\n\n=== CANDIDATE RESPONSE ===\n{text_value({'reasoning': candidate.get('reasoning'), 'response': candidate.get('response')})}"""
    return clip_judge_text(value, token_limit)


def find_result_value(value: Any, keys: set[str]) -> Any:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in keys:
                return item
        for item in value.values():
            found = find_result_value(item, keys)
            if found is not None:
                return found
    return None


def aggregate_stage3(samples: list[dict[str, Any]]) -> dict[str, Any]:
    scores: list[int] = []
    tiers: list[int] = []
    for sample in samples:
        score = find_result_value(sample, {"score", "final_score"})
        tier = find_result_value(sample, {"tier", "final_tier"})
        try:
            scores.append(max(1, min(10, int(round(float(score))))))
        except (TypeError, ValueError):
            pass
        try:
            tiers.append(max(1, min(3, int(str(tier).replace("Tier", "").replace("tier", "").strip()))))
        except (TypeError, ValueError):
            pass
    final_score = sorted(scores)[len(scores) // 2] if scores else None
    if tiers:
        final_tier = max(set(tiers), key=lambda item: (tiers.count(item), -item))
    elif final_score is not None:
        final_tier = 1 if final_score >= 8 else 2 if final_score >= 4 else 3
    else:
        final_tier = None
    chosen = samples[0] if samples else {}
    if final_score is not None:
        chosen = min(samples, key=lambda sample: abs(float(find_result_value(sample, {"score", "final_score"}) or final_score) - final_score))
    parse_error_count = sum(bool(sample.get("parse_error")) for sample in samples)
    return {
        "consensus": {
            "score": final_score,
            "tier": final_tier,
            "sample_count": len(samples),
            "score_range": [min(scores), max(scores)] if scores else None,
            "stable": bool(scores) and parse_error_count == 0 and len(set(scores)) <= 1 and len(set(tiers)) <= 1,
            "parse_error_count": parse_error_count,
        },
        "final": chosen,
        "samples": samples,
    }


_judge_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="case-lens-judge")
_judge_schedule_lock = threading.Lock()
_active_judge_case_runs: set[int] = set()
_judge_config_semaphores: dict[int, threading.BoundedSemaphore] = {}


def execute_judge_case_run(case_run_id: int) -> None:
    with SessionLocal() as db:
        case_run = db.get(JudgeCaseRun, case_run_id)
        if not case_run:
            return
        case = db.get(Case, case_run.case_id)
        config_record = db.get(JudgeConfigVersion, case_run.config_id)
        if not case or not config_record:
            case_run.status = "failed"
            case_run.error = "Case 或判分配置不存在"
            case_run.completed_at = utcnow()
            db.commit()
            return
        config = config_record.config
        if canonical_hash(judge_case_content(case.payload)) != case_run.case_hash:
            case_run.status = "stale"
            case_run.error = "Case 内容已变化，本次任务已过期"
            case_run.completed_at = utcnow()
            db.commit()
            return
        case_run.started_at = case_run.started_at or utcnow()
        case_run.error = ""
        try:
            if not case_run.stage1_result:
                case_run.status = "running_stage_1"
                db.commit()
                stage1_input = stage1_user_prompt(case.payload, int(config.get("input_limit", 0)))
                raw = call_judge_model(config, config_record.api_key, str(config["decomposer_prompt"]), stage1_input, float(config["stage1_temperature"]), int(config["stage1_max_tokens"]))
                case_run.stage1_raw = raw
                case_run.stage1_result = require_judge_object(parse_json_object(raw), "阶段一")
                if not isinstance(case_run.stage1_result.get("subtasks"), list) or not case_run.stage1_result["subtasks"]:
                    raise ValueError("阶段一结构化输出缺少 subtasks")
                case_run.stage1_result["_input_truncated"] = "[... 输入按配置截断 ...]" in stage1_input
                db.commit()
        except Exception as exc:
            case_run.status = "failed"
            case_run.error = f"阶段一失败：{redact_judge_error(exc, config_record.api_key)}"
            case_run.completed_at = utcnow()
            candidate_runs = db.scalars(select(JudgeCandidateRun).where(JudgeCandidateRun.case_run_id == case_run.id)).all()
            for candidate_run in candidate_runs:
                if candidate_run.status in {"queued", "running_stage_2", "running_stage_3"}:
                    candidate_run.status = "failed"
                    candidate_run.error = case_run.error
                    candidate_run.completed_at = utcnow()
            db.commit()
            return

        candidate_map = {
            str(item.get("id")): item
            for item in case.payload.get("candidates", [])
            if isinstance(item, dict) and item.get("id") is not None
        }
        candidate_runs = db.scalars(select(JudgeCandidateRun).where(JudgeCandidateRun.case_run_id == case_run.id).order_by(JudgeCandidateRun.id)).all()
        for candidate_run in candidate_runs:
            if candidate_run.status == "succeeded":
                continue
            candidate = candidate_map.get(candidate_run.candidate_id)
            if not candidate or canonical_hash(judge_candidate_content(candidate)) != candidate_run.candidate_hash:
                candidate_run.status = "stale"
                candidate_run.error = "候选回复已变化，本次结果已过期"
                candidate_run.completed_at = utcnow()
                db.commit()
                continue
            candidate_run.started_at = candidate_run.started_at or utcnow()
            candidate_run.error = ""
            try:
                if not candidate_run.stage2_result:
                    candidate_run.status = "running_stage_2"
                    case_run.status = "running_stage_2"
                    db.commit()
                    stage2_input = stage2_user_prompt(case.payload, candidate, case_run.stage1_result or {}, int(config.get("input_limit", 0)))
                    raw = call_judge_model(config, config_record.api_key, str(config["detector_prompt"]), stage2_input, float(config["stage2_temperature"]), int(config["stage2_max_tokens"]))
                    candidate_run.stage2_raw = raw
                    candidate_run.stage2_result = require_judge_object(parse_json_object(raw), "阶段二")
                    candidate_run.stage2_result["_input_truncated"] = "[... 输入按配置截断 ...]" in stage2_input
                    db.commit()
                candidate_run.status = "running_stage_3"
                case_run.status = "running_stage_3"
                db.commit()
                samples: list[dict[str, Any]] = []
                raw_samples: list[str] = []
                stage3_input = stage3_user_prompt(case.payload, candidate, case_run.stage1_result or {}, candidate_run.stage2_result or {}, config, int(config.get("input_limit", 0)))
                for sample_index in range(int(config.get("sample_count", 3))):
                    try:
                        raw = call_judge_model(config, config_record.api_key, str(config["verifier_prompt"]), stage3_input, float(config["stage3_temperature"]), int(config["stage3_max_tokens"]))
                        raw_samples.append(raw)
                        samples.append(parse_json_object(raw))
                    except Exception as exc:
                        message = redact_judge_error(exc, config_record.api_key)
                        raw_samples.append(f"SAMPLE {sample_index + 1} FAILED: {message}")
                        samples.append({"parse_error": f"采样请求失败：{message}"})
                consensus = aggregate_stage3(samples)
                if bool(config.get("adaptive_sampling")) and not consensus["consensus"]["stable"]:
                    for _ in range(min(2, 9 - len(samples))):
                        try:
                            raw = call_judge_model(config, config_record.api_key, str(config["verifier_prompt"]), stage3_input, float(config["stage3_temperature"]), int(config["stage3_max_tokens"]))
                            raw_samples.append(raw)
                            samples.append(parse_json_object(raw))
                        except Exception as exc:
                            message = redact_judge_error(exc, config_record.api_key)
                            raw_samples.append(f"ADAPTIVE SAMPLE FAILED: {message}")
                            samples.append({"parse_error": f"追采请求失败：{message}"})
                final_aggregate = aggregate_stage3(samples)
                if final_aggregate["consensus"]["score"] is None:
                    raise ValueError("阶段三没有任何可用的结构化评分样本")
                candidate_run.stage3_raw = "\n\n--- SAMPLE ---\n\n".join(raw_samples)
                candidate_run.stage3_result = {
                    **final_aggregate,
                    "input_truncated": bool(case_run.stage1_result.get("_input_truncated"))
                    or bool(candidate_run.stage2_result.get("_input_truncated"))
                    or "[... 输入按配置截断 ...]" in stage3_input,
                }
                candidate_run.status = "succeeded"
                candidate_run.completed_at = utcnow()
                db.commit()
            except Exception as exc:
                failed_stage = "阶段二" if candidate_run.status == "running_stage_2" else "阶段三"
                candidate_run.status = "failed"
                candidate_run.error = f"{failed_stage}失败：{redact_judge_error(exc, config_record.api_key)}"
                candidate_run.completed_at = utcnow()
                db.commit()

        statuses = list(db.scalars(select(JudgeCandidateRun.status).where(JudgeCandidateRun.case_run_id == case_run.id)).all())
        succeeded = sum(status == "succeeded" for status in statuses)
        case_run.status = "succeeded" if statuses and succeeded == len(statuses) else "partial_failed" if succeeded else "failed"
        case_run.completed_at = utcnow()
        if case_run.status == "failed" and not case_run.error:
            case_run.error = "全部候选判分失败"
        db.commit()


def _judge_case_worker(case_run_id: int) -> None:
    semaphore: threading.BoundedSemaphore | None = None
    try:
        with SessionLocal() as db:
            claimed = db.execute(
                update(JudgeCaseRun)
                .where(JudgeCaseRun.id == case_run_id, JudgeCaseRun.status == "queued")
                .values(status="claimed", started_at=utcnow())
            )
            db.commit()
            if claimed.rowcount != 1:
                return
            case_run = db.get(JudgeCaseRun, case_run_id)
            config_record = db.get(JudgeConfigVersion, case_run.config_id) if case_run else None
            if config_record:
                with _judge_schedule_lock:
                    semaphore = _judge_config_semaphores.setdefault(
                        config_record.id,
                        threading.BoundedSemaphore(int(config_record.config.get("concurrency", 2))),
                    )
        if semaphore:
            semaphore.acquire()
        with SessionLocal() as db:
            claimed_run = db.get(JudgeCaseRun, case_run_id)
            if not claimed_run or claimed_run.status != "claimed":
                return
        execute_judge_case_run(case_run_id)
    finally:
        if semaphore:
            semaphore.release()
        with _judge_schedule_lock:
            _active_judge_case_runs.discard(case_run_id)


def schedule_judge_case_run(case_run_id: int) -> bool:
    with _judge_schedule_lock:
        if case_run_id in _active_judge_case_runs:
            return False
        _active_judge_case_runs.add(case_run_id)
    _judge_executor.submit(_judge_case_worker, case_run_id)
    return True


def judge_candidate_payload(record: JudgeCandidateRun) -> dict[str, Any]:
    return {
        "id": record.id,
        "candidate_id": record.candidate_id,
        "status": record.status,
        "stage2": record.stage2_result,
        "stage3": record.stage3_result,
        "stage2_raw": record.stage2_raw,
        "stage3_raw": record.stage3_raw,
        "error": record.error,
        "started_at": record.started_at.isoformat() if record.started_at else None,
        "completed_at": record.completed_at.isoformat() if record.completed_at else None,
    }


def project_judge_status_payload(db: Session, project: Project, user: User) -> dict[str, Any]:
    config_record = active_judge_config(db, project.id)
    case_query = select(Case).where(Case.project_id == project.id)
    if user.role != "admin":
        case_query = case_query.join(CaseAssignment).where(CaseAssignment.user_id == user.id)
    cases = db.scalars(case_query.order_by(Case.ordinal)).all()
    result_cases: dict[str, Any] = {}
    summary = {"not_started": 0, "queued": 0, "running": 0, "succeeded": 0, "failed": 0, "stale": 0, "cancelled": 0}
    for case in cases:
        case_hash = canonical_hash(judge_case_content(case.payload))
        case_run = None
        if config_record:
            case_run = db.scalar(
                select(JudgeCaseRun)
                .where(JudgeCaseRun.case_id == case.id, JudgeCaseRun.config_id == config_record.id, JudgeCaseRun.case_hash == case_hash)
                .order_by(JudgeCaseRun.id.desc())
            )
        candidate_payloads: dict[str, Any] = {}
        for candidate in case.payload.get("candidates", []):
            if not isinstance(candidate, dict) or candidate.get("id") is None:
                continue
            candidate_id = str(candidate["id"])
            candidate_hash = canonical_hash(judge_candidate_content(candidate))
            candidate_run = None
            if case_run:
                candidate_run = db.scalar(
                    select(JudgeCandidateRun)
                    .where(JudgeCandidateRun.case_run_id == case_run.id, JudgeCandidateRun.candidate_id == candidate_id, JudgeCandidateRun.candidate_hash == candidate_hash)
                    .order_by(JudgeCandidateRun.id.desc())
                )
            if candidate_run:
                candidate_payloads[candidate_id] = judge_candidate_payload(candidate_run)
                if candidate_run.status == "succeeded":
                    summary["succeeded"] += 1
                elif candidate_run.status in {"running_stage_2", "running_stage_3"}:
                    summary["running"] += 1
                elif candidate_run.status == "queued":
                    summary["queued"] += 1
                elif candidate_run.status == "stale":
                    summary["stale"] += 1
                elif candidate_run.status == "cancelled":
                    summary["cancelled"] += 1
                else:
                    summary["failed"] += 1
            else:
                summary["not_started"] += 1
        result_cases[str(case.id)] = {
            "case_id": case.id,
            "external_id": case.external_id,
            "status": case_run.status if case_run else "not_started",
            "stage1": case_run.stage1_result if case_run else None,
            "stage1_raw": case_run.stage1_raw if case_run else "",
            "error": case_run.error if case_run else "",
            "config_version": config_record.version if config_record else 0,
            "candidates": candidate_payloads,
        }
    return {
        # Browser-side judging needs shared prompts and runtime settings. The
        # API key is stored separately and is never returned here.
        "config": judge_config_payload(config_record, include_details=True),
        "summary": summary,
        "running": bool(summary["queued"] or summary["running"]),
        "cases": result_cases,
    }


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
        recoverable = db.scalars(
            select(JudgeCaseRun).where(JudgeCaseRun.status.in_(["queued", "claimed", "running_stage_1", "running_stage_2", "running_stage_3"]))
        ).all()
        for case_run in recoverable:
            case_run.status = "cancelled"
            case_run.completed_at = utcnow()
            case_run.error = "旧版服务端判分任务已取消；请由用户浏览器连接本机中继后重新运行"
        recoverable_candidate_ids = [case_run.id for case_run in recoverable]
        if recoverable_candidate_ids:
            for candidate_run in db.scalars(select(JudgeCandidateRun).where(JudgeCandidateRun.case_run_id.in_(recoverable_candidate_ids), JudgeCandidateRun.status.in_(["queued", "running_stage_2", "running_stage_3"]))).all():
                candidate_run.status = "cancelled"
                candidate_run.completed_at = utcnow()
                candidate_run.error = "旧版服务端判分任务已取消"
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
    profile, progress, evolution = get_or_create_pet(db, user.id)
    db.commit()
    return pet_dict(profile, progress, evolution)


@app.put("/api/pet")
def update_pet(body: PetProfileUpdate, user: CurrentUser, db: DB) -> dict[str, Any]:
    profile, progress, evolution = get_or_create_pet(db, user.id)
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
    return pet_dict(profile, progress, evolution)


@app.post("/api/pet/evolve")
def evolve_pet(body: PetEvolutionBody, user: CurrentUser, db: DB) -> dict[str, Any]:
    if body.spend not in {1, 5}:
        raise HTTPException(422, "变身只能使用 1 次或 5 次机会")
    profile, progress, evolution = get_or_create_pet(db, user.id)
    if evolution.stage >= PET_MAX_EVOLUTION_STAGE:
        raise HTTPException(422, "已经完成三次变身强化")
    if evolution.available_chances < body.spend:
        raise HTTPException(422, "可用变身机会不足")
    db.flush()
    evolution = db.scalar(
        select(PetEvolution)
        .where(PetEvolution.user_id == user.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ) or evolution
    if evolution.available_chances < body.spend:
        raise HTTPException(409, "变身机会刚刚发生变化，请刷新后重试")
    evolution.available_chances -= body.spend
    guaranteed = body.spend == 5
    success = guaranteed or secrets.randbelow(10) == 0
    trait = ""
    if success:
        if evolution.stage == 0 or evolution.path not in PET_EVOLUTION_PATHS:
            evolution.path = secrets.choice(tuple(PET_EVOLUTION_PATHS))
            evolution.variant_seed = secrets.randbelow(4)
        path = PET_EVOLUTION_PATHS[evolution.path]
        trait_pool = path["traits"][min(evolution.stage, PET_MAX_EVOLUTION_STAGE - 1)]
        trait = secrets.choice(trait_pool)
        evolution.traits = [*(evolution.traits or []), trait]
        evolution.stage += 1
    event = {
        "at": utcnow().isoformat(),
        "spent": body.spend,
        "guaranteed": guaranteed,
        "success": success,
        "stage": evolution.stage,
        "path": evolution.path,
        "trait": trait,
    }
    evolution.history = [event, *(evolution.history or [])][:50]
    evolution.updated_at = utcnow()
    db.commit()
    return {
        "profile": pet_dict(profile, progress, evolution),
        "success": success,
        "spent": body.spend,
        "guaranteed": guaranteed,
        "trait": trait,
    }


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
        profile, progress, evolution = get_or_create_pet(db, user.id)
        db.commit()
        return {"profile": pet_dict(profile, progress, evolution), "awarded": False, "amount": 0, "hourly_earned": 2, "hourly_remaining": 0}
    profile, progress, evolution, awarded, amount = grant_pet_experience(db, user.id, "pet", f"pet:{hour_key}:{hourly_count + 1}")
    db.commit()
    earned_count = hourly_count + (1 if awarded else 0)
    return {"profile": pet_dict(profile, progress, evolution), "awarded": awarded, "amount": amount, "hourly_earned": round(earned_count / 5, 1), "hourly_remaining": max(0, 10 - earned_count)}


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
    judge_case_run_ids = select(JudgeCaseRun.id).where(JudgeCaseRun.project_id == project_id)
    db.execute(delete(JudgeCandidateRun).where(JudgeCandidateRun.case_run_id.in_(judge_case_run_ids)))
    db.execute(delete(JudgeCaseRun).where(JudgeCaseRun.project_id == project_id))
    db.execute(delete(JudgeConfigVersion).where(JudgeConfigVersion.project_id == project_id))
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


@app.get("/api/projects/{project_id}/judge/config")
def get_judge_config(project_id: int, user: CurrentUser, db: DB) -> dict[str, Any]:
    ensure_project_access(project_id, user, db)
    return judge_config_payload(active_judge_config(db, project_id), include_details=True)


@app.put("/api/projects/{project_id}/judge/config")
def save_judge_config(project_id: int, body: JudgeConfigBody, admin: AdminUser, db: DB) -> dict[str, Any]:
    if not db.get(Project, project_id):
        raise HTTPException(404, "项目不存在")
    protocol = body.protocol.strip().lower()
    if protocol not in {"anthropic", "openai"}:
        raise HTTPException(422, "协议只能是 anthropic 或 openai")
    endpoint = urlsplit(body.base_url.strip().rstrip("/；; "))
    if endpoint.scheme not in {"http", "https"} or not endpoint.netloc:
        raise HTTPException(422, "Base URL 必须是完整的 HTTP(S) 地址")
    previous = active_judge_config(db, project_id)
    config = body.model_dump(exclude={"api_key"})
    config["protocol"] = protocol
    config["base_url"] = JUDGE_LOCAL_RELAY_BASE
    version = (db.scalar(select(func.max(JudgeConfigVersion.version)).where(JudgeConfigVersion.project_id == project_id)) or 0) + 1
    if previous:
        previous.active = False
    record = JudgeConfigVersion(
        project_id=project_id,
        version=version,
        config=config,
        # Each user supplies their own page-memory-only key to the local relay.
        api_key="",
        signature=judge_config_signature(config),
        active=True,
        created_by=admin.id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return judge_config_payload(record)


@app.post("/api/projects/{project_id}/judge/test")
def test_judge_config(project_id: int, _: AdminUser, db: DB) -> dict[str, Any]:
    if not db.get(Project, project_id):
        raise HTTPException(404, "项目不存在")
    record = active_judge_config(db, project_id)
    if not record:
        raise HTTPException(422, "请先保存判分配置")
    raise HTTPException(410, "模型连接必须由当前用户浏览器测试本机中继")


@app.post("/api/projects/{project_id}/judge/run")
def run_project_judge(project_id: int, body: JudgeRunBody, user: CurrentUser, db: DB) -> dict[str, Any]:
    ensure_project_access(project_id, user, db)
    raise HTTPException(410, "自动判分已改为由当前用户浏览器调用本机中继")


@app.post("/api/projects/{project_id}/judge/client-result")
def save_client_judge_result(project_id: int, body: JudgeClientResultBody, user: CurrentUser, db: DB) -> dict[str, Any]:
    ensure_project_access(project_id, user, db)
    config_record = active_judge_config(db, project_id)
    if not config_record or config_record.version != body.config_version:
        raise HTTPException(409, "判分配置已更新，请刷新后重新运行")
    case = db.get(Case, body.case_id)
    if not case or case.project_id != project_id:
        raise HTTPException(404, "Case 不存在")
    if user.role != "admin" and not db.scalar(select(CaseAssignment).where(CaseAssignment.case_id == case.id, CaseAssignment.user_id == user.id)):
        raise HTTPException(403, "无权提交该 Case 的判分结果")

    case_hash = canonical_hash(judge_case_content(case.payload))
    case_run = db.scalar(select(JudgeCaseRun).where(
        JudgeCaseRun.case_id == case.id,
        JudgeCaseRun.config_id == config_record.id,
        JudgeCaseRun.case_hash == case_hash,
    ))
    if not case_run:
        case_run = JudgeCaseRun(
            project_id=project_id,
            case_id=case.id,
            config_id=config_record.id,
            case_hash=case_hash,
            status="running_stage_1",
            triggered_by=user.id,
            started_at=utcnow(),
        )
        db.add(case_run)
        db.flush()
    else:
        case_run.triggered_by = user.id
        case_run.started_at = case_run.started_at or utcnow()

    candidate_by_id = {
        str(item["id"]): item
        for item in case.payload.get("candidates", [])
        if isinstance(item, dict) and item.get("id") is not None
    }
    request_ok = not bool(body.error)
    if body.error:
        case_run.error = body.error[:2000]
    elif body.stage1_raw:
        try:
            stage1 = require_judge_object(parse_json_object(body.stage1_raw), "阶段一")
            stage1_changed = bool(case_run.stage1_result and canonical_hash(case_run.stage1_result) != canonical_hash(stage1))
            case_run.stage1_raw = body.stage1_raw
            case_run.stage1_result = stage1
            case_run.error = ""
            if stage1_changed:
                for previous in db.scalars(select(JudgeCandidateRun).where(JudgeCandidateRun.case_run_id == case_run.id)).all():
                    previous.status = "stale"
                    previous.error = "Stage 1 已重新生成，请重新生成该模型的 Stage 2+3"
        except Exception as exc:
            request_ok = False
            case_run.error = str(exc)[:2000]
    elif not case_run.stage1_result:
        request_ok = False
        case_run.error = "请先生成 Stage 1 任务拆解"

    for submitted in body.candidates:
        candidate = candidate_by_id.get(submitted.candidate_id)
        if not candidate:
            request_ok = False
            case_run.error = f"候选 {submitted.candidate_id} 已不存在，请刷新后重试"
            continue
        candidate_hash = canonical_hash(judge_candidate_content(candidate))
        candidate_run = db.scalar(select(JudgeCandidateRun).where(
            JudgeCandidateRun.case_run_id == case_run.id,
            JudgeCandidateRun.candidate_id == submitted.candidate_id,
            JudgeCandidateRun.candidate_hash == candidate_hash,
        ))
        if not candidate_run:
            candidate_run = JudgeCandidateRun(
                case_run_id=case_run.id,
                candidate_id=submitted.candidate_id,
                candidate_hash=candidate_hash,
                status="running_stage_2",
                started_at=utcnow(),
            )
            db.add(candidate_run)
        candidate_run.stage2_raw = submitted.stage2_raw
        candidate_run.stage3_raw = "\n\n--- SAMPLE ---\n\n".join(submitted.stage3_raw)
        candidate_run.completed_at = utcnow()
        try:
            if submitted.error:
                raise ValueError(submitted.error)
            if not case_run.stage1_result:
                raise ValueError("请先生成 Stage 1 任务拆解")
            stage2 = require_judge_object(parse_json_object(submitted.stage2_raw), "阶段二")
            samples = [parse_json_object(raw) for raw in submitted.stage3_raw]
            aggregate = aggregate_stage3(samples)
            if aggregate["consensus"]["score"] is None:
                raise ValueError("阶段三没有任何可用的结构化评分样本")
            candidate_run.stage2_result = stage2
            candidate_run.stage3_result = aggregate
            candidate_run.status = "succeeded"
            candidate_run.error = ""
        except Exception as exc:
            request_ok = False
            candidate_run.status = "failed"
            candidate_run.error = str(exc)[:2000]

    current_statuses: list[str] = []
    for candidate_id, candidate in candidate_by_id.items():
        candidate_hash = canonical_hash(judge_candidate_content(candidate))
        current = db.scalar(select(JudgeCandidateRun).where(
            JudgeCandidateRun.case_run_id == case_run.id,
            JudgeCandidateRun.candidate_id == candidate_id,
            JudgeCandidateRun.candidate_hash == candidate_hash,
        ))
        current_statuses.append(current.status if current else "not_started")
    if current_statuses and all(status == "succeeded" for status in current_statuses):
        case_run.status = "succeeded"
    elif any(status == "succeeded" for status in current_statuses):
        case_run.status = "partial_succeeded"
    elif case_run.stage1_result:
        case_run.status = "stage1_succeeded"
    else:
        case_run.status = "failed"
    case_run.completed_at = utcnow()
    db.commit()
    return {"ok": request_ok, "status": case_run.status, "case_id": case.id}


@app.post("/api/projects/{project_id}/judge/cancel")
def cancel_project_judge(project_id: int, body: JudgeRunBody, user: CurrentUser, db: DB) -> dict[str, Any]:
    ensure_project_access(project_id, user, db)
    config_record = active_judge_config(db, project_id)
    if not config_record:
        return {"cancelled": 0, "running_not_cancelled": 0}
    case_query = select(Case).where(Case.project_id == project_id)
    if user.role != "admin":
        case_query = case_query.join(CaseAssignment).where(CaseAssignment.user_id == user.id)
    requested_ids = list(dict.fromkeys(body.case_ids))
    if requested_ids:
        case_query = case_query.where(Case.id.in_(requested_ids))
    cases = db.scalars(case_query).all()
    if requested_ids and len(cases) != len(requested_ids):
        raise HTTPException(403, "请求中包含无权访问或不存在的 Case")
    cancelled = running_not_cancelled = 0
    for case in cases:
        case_run = db.scalar(select(JudgeCaseRun).where(
            JudgeCaseRun.case_id == case.id,
            JudgeCaseRun.config_id == config_record.id,
            JudgeCaseRun.case_hash == canonical_hash(judge_case_content(case.payload)),
        ))
        if not case_run:
            continue
        if case_run.status in {"queued", "claimed"}:
            case_run.status = "cancelled"
            case_run.completed_at = utcnow()
            case_run.error = "任务在开始模型请求前由用户取消"
            for candidate_run in db.scalars(select(JudgeCandidateRun).where(
                JudgeCandidateRun.case_run_id == case_run.id,
                JudgeCandidateRun.status == "queued",
            )).all():
                candidate_run.status = "cancelled"
                candidate_run.completed_at = utcnow()
                candidate_run.error = "任务已取消"
                cancelled += 1
        elif case_run.status in {"running_stage_1", "running_stage_2", "running_stage_3"}:
            running_not_cancelled += 1
    db.commit()
    return {"cancelled": cancelled, "running_not_cancelled": running_not_cancelled}


@app.get("/api/projects/{project_id}/judge/status")
def get_project_judge_status(project_id: int, user: CurrentUser, db: DB) -> dict[str, Any]:
    project = ensure_project_access(project_id, user, db)
    return project_judge_status_payload(db, project, user)


@app.get("/api/projects/{project_id}/judge/history")
def get_case_judge_history(project_id: int, case_id: int, user: CurrentUser, db: DB) -> dict[str, Any]:
    ensure_project_access(project_id, user, db)
    query = select(Case).where(Case.project_id == project_id, Case.id == case_id)
    if user.role != "admin":
        query = query.join(CaseAssignment).where(CaseAssignment.user_id == user.id)
    case = db.scalar(query)
    if not case:
        raise HTTPException(404, "Case 不存在或无权访问")
    current_case_hash = canonical_hash(judge_case_content(case.payload))
    current_candidate_hashes = {
        str(candidate["id"]): canonical_hash(judge_candidate_content(candidate))
        for candidate in case.payload.get("candidates", [])
        if isinstance(candidate, dict) and candidate.get("id") is not None
    }
    runs = db.scalars(
        select(JudgeCaseRun)
        .where(JudgeCaseRun.case_id == case.id)
        .order_by(JudgeCaseRun.created_at.desc(), JudgeCaseRun.id.desc())
    ).all()
    result: list[dict[str, Any]] = []
    for case_run in runs:
        config = db.get(JudgeConfigVersion, case_run.config_id)
        trigger = db.get(User, case_run.triggered_by)
        candidate_runs = db.scalars(
            select(JudgeCandidateRun)
            .where(JudgeCandidateRun.case_run_id == case_run.id)
            .order_by(JudgeCandidateRun.id.desc())
        ).all()
        result.append({
            "id": case_run.id,
            "status": case_run.status,
            "stage1": case_run.stage1_result,
            "stage1_raw": case_run.stage1_raw,
            "error": case_run.error,
            "config_version": config.version if config else 0,
            "model_name": str(config.config.get("model_name", "")) if config else "",
            "current_case_content": case_run.case_hash == current_case_hash,
            "triggered_by": trigger.display_name if trigger else "未知用户",
            "created_at": case_run.created_at.isoformat(),
            "completed_at": case_run.completed_at.isoformat() if case_run.completed_at else None,
            "candidates": [
                {
                    **judge_candidate_payload(candidate_run),
                    "candidate_hash": candidate_run.candidate_hash,
                    "current_content": current_candidate_hashes.get(candidate_run.candidate_id) == candidate_run.candidate_hash,
                }
                for candidate_run in candidate_runs
            ],
        })
    return {"case_id": case.id, "runs": result}


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
