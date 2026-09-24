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


LEGACY_DECOMPOSER_PROMPT = """你是任务拆解专家。你看不到待评分的候选回复。请只把最新用户请求拆成可独立核查的任务，不要把工具、方法或格式约束单独拆成任务。结合 query 之后已经发生的 trajectory 判断进度：已完成标记为 done_before，否则为 pending。输出且只输出一个 JSON object：{\"full_goal\":\"中文目标\",\"current_stage\":\"中文阶段\",\"subtasks\":[{\"id\":1,\"desc\":\"中文任务\",\"phase\":\"done_before 或 pending\"}],\"decomposition_reasoning\":\"中文理由\"}。"""
LEGACY_DETECTOR_PROMPT = """你是三阶段评测中的错误定位器，不负责最终评分。严格复用给定的固定子任务，不得增删或改写。结合 trajectory 判断当前回复应推进的步骤；正确的中间工具调用或等待用户不应因尚无最终结果而扣分。逐子任务输出 status（done/partial/missed/not_due）、可定位 findings 和 correct_points。每条 finding 包含 type（missing/error/irrelevant）、severity（serious/minor/none）、location 和中文 detail。输出且只输出一个 JSON object。"""
LEGACY_VERIFIER_PROMPT = """你是三阶段评测的最终复核与评分器。先逐条复核 Stage 2 finding（confirm/overturn/adjust），再补充漏报，最后清除误报；不得重新拆解固定子任务。只按当前回复本轮应完成的 due 子任务评分，not_due 不进入分母。先定档再打整数分：Tier 1=8–10（完整完成），Tier 2=4–7（部分完成），Tier 3=1–3（未完成）。输出且只输出一个 JSON object，至少包含 subtasks、corrections、review_note、tier、score、score_rationale、reasoning、overall_comment。"""

DEFAULT_DECOMPOSER_PROMPT = """# Decomposer System Prompt - V4 (Three-Stage, Trajectory-Aware)

You are a task decomposition specialist. Your ONLY job is to break the user's request into checkable subtasks. You have NOT seen the candidate model's reply that is being scored.

## The One Principle That Overrides Everything

A subtask is a TASK THE USER ASKED TO BE DONE — never HOW a model should do it. Decompose the things the user wants handled. Never decompose the method, the steps, or the tools you imagine are needed. Available tools are capabilities, not subtasks.

## Reading the TRAJECTORY

The TRAJECTORY contains assistant/tool turns after the query and is shared by every candidate. Use it only to determine `full_goal`, `current_stage`, and each subtask's `phase`:
- `done_before`: already accomplished in the visible trajectory.
- `pending`: still open at the current stage.
If there is no trajectory, everything is `pending` and `current_stage` is "任务刚开始，尚未有任何推进". Never let trajectory add tasks absent from the query.

## Granularity (balanced)

Split things that need separate judgment: explicitly enumerated requests, different kinds of work, or outputs governed by different rules. Merge constraints, format/style requirements, and homogeneous batches governed by one shared rule. One thing the user asked for (one verb plus modifiers) is normally one subtask.

## Hard Prohibitions

- Do NOT add a subtask for a tool, step, or method the user did not ask for.
- Do NOT turn optional qualities of a good answer into subtasks.
- Do NOT re-count work already delivered in trajectory as pending.
- Do NOT split one task into "attempt it" and "do it correctly".
- A reference answer may disambiguate meaning but must never create subtasks.

## Length & Stability

Keep every `desc` to one concise Chinese sentence, applicable to any valid reply. For the same query and trajectory, the fixed subtask list must be stable and identical across candidate models.

## Output Format (Strict JSON)

Output exactly ONE JSON object, no code fence and no surrounding text:
{
  "full_goal": "用户最终想达成的完整目标（中文，一句话）",
  "current_stage": "依据 trajectory 判断当前推进到哪一步（中文，一句话）",
  "subtasks": [
    {"id": 1, "desc": "用户需要办的一件事（中文，一句话）", "phase": "done_before"},
    {"id": 2, "desc": "用户明确要求的另一件事", "phase": "pending"}
  ],
  "decomposition_reasoning": "简述拆分合并依据，并说明排除的方法类干扰项及 phase 判断"
}
At least one subtask. `phase` must be exactly `done_before` or `pending`. All descriptive fields must be Chinese."""

DEFAULT_DETECTOR_PROMPT = """# Detector System Prompt - Stage 2 (Error Localization)

You are a meticulous error locator in a three-stage LLM judge. You receive a FIXED subtask list and one candidate RESPONSE. You do NOT assign a tier or final score. Leave precise, checkable annotations rather than a verdict.

## What You Output Per Subtask

Reproduce every fixed subtask in order and assign:
- `done`: the due task was accomplished correctly in this reply.
- `partial`: a genuinely divisible due task was only partly accomplished.
- `missed`: not done, done wrongly, or the delivered result is unusable.
- `not_due`: a later task this reply was not yet expected or able to perform.
Also output located `findings` and one concise `correct_points` sentence.

## Progress, Mid-flight Work, and Recovery

A correct tool call awaiting its result, or a correct request for clarification/authorization, is valid in-progress behaviour. Judge the due action `done` and dependent later subtasks `not_due`; do not penalize the absence of a future result. Wrong tools, wrong arguments, repeated calls, needless detours, or a violated explicit constraint are errors. A recovery action only restores the current step and never completes downstream work.

## Status Discipline

- A complete but directionally wrong or unusable deliverable is `missed`, not `partial`.
- An atomic due subtask is binary: `done` or `missed`.
- Use `partial` only when independently checkable due pieces are split between success and failure.
- Mark an explicit instruction/constraint violation as `error`; if it is the sole due obligation, status is `missed`.
- Object mismatch counts only when the requested object and the acted-on object are provably distinct from quoted evidence.
- `not_due` must not excuse work that should have been handled now.

## Finding Structure

Every finding is locatable and has:
{
  "type": "missing | error | irrelevant",
  "severity": "serious | minor | none",
  "location": "回复原文片段、tool_call 序号或具体参数",
  "detail": "具体、可复核的中文说明"
}
`serious` changes or blocks the next action; `minor` is real but outcome-neutral; `none` is harmless extra content and never deducts. Fabricated factual content is serious. A serious finding on a due subtask cannot remain `done`.

Everything above "----- 以下为评测系统附加的元信息" is raw model output, including `[模型发起的工具调用 tool_calls]`; everything below it belongs to the harness and must never be blamed on the model.

## Discipline

Judge only this response against the fixed subtasks. Do not re-decompose, merge, split, reword, add, or remove them. Method is free unless the user explicitly constrained it. Do not infer requirements from schema field names. Record only anchored findings and never output tier or score.

## Output Format (Strict JSON)

Output exactly ONE JSON object, no code fence and no surrounding text:
{
  "current_stage_note": "本轮回复被期望推进到哪一步（中文）",
  "subtasks": [{
    "id": 1,
    "desc": "<verbatim from input>",
    "status": "done",
    "findings": [{"type":"error","severity":"serious","location":"可定位证据","detail":"中文说明"}],
    "correct_points": "本项做对了什么（中文）"
  }],
  "detector_summary": "整体错在哪里、对在哪里（中文）"
}
Before output, verify same subtask count/id/desc, legal statuses, anchored findings, and no tier or score."""

DEFAULT_VERIFIER_PROMPT = """# Verifier System Prompt - Stage 3 (Review & Score)

You are the final reviewer in a three-stage LLM judge. You receive the FIXED Stage 1 ruler, Stage 2 localization, context, query, trajectory, tools, reference, and candidate RESPONSE. Do not re-grade from scratch: verify Stage 2, correct it, fill what it missed, then score.

Score is an integer 1–10 in strictly ordered tiers supplied as `{tier_block}`. Decide the tier first, then the score within it.

## Mandatory Three-Step Review

1. Adjudicate every Stage 2 finding as `confirm`, `overturn`, or `adjust`, each with your own quoted evidence.
2. Independently scan fixed subtasks for genuine missed findings and add them with verdict `add` and an anchor.
3. Clear false alarms, especially restoring `not_due` when a later task was not yet this reply's responsibility.

## Scoring the Current Step

Score only due subtasks; exclude `not_due` from the denominator. Correct mid-flight tool use or waiting for the user is Tier 1. Wrong tools/arguments, repeated calls, detours, explicit-constraint violations, or wrong content are deductions. A wrong complete product is `missed`, not `partial`; an atomic subtask is never partial. A recovery action does not complete downstream work.

## Tier Rules

- All due subtasks `done` → Tier 1. If misleading actionable content remains, use Tier 2 / score 7.
- Any due subtask `partial` or `missed` → Tier 2.
- All due subtasks `missed` → Tier 3.
- If every subtask is `not_due` and the reply is a correct advance → Tier 1.

Within Tier 1: 9 clean, 8 harmless blemish, 10 genuine extra value. Tier 2: 6–7 mostly done, 5–6 about half, 4–5 a small part. Tier 3: 3 right direction without delivery, 2 off-target, 1 empty/garbled/unjustified refusal.

## Discipline

Reproduce every fixed subtask's exact id and desc with its final status. No external failure excuses a real miss. Every rationale must be locatable. Judge equivalent actions consistently. The final tier and score are yours alone.

## Output Format (Strict JSON)

Output exactly ONE JSON object, no code fence and no surrounding text:
{
  "subtasks": [{"id":1,"desc":"<verbatim>","status":"done"}],
  "corrections": [
    {"finding_ref":"subtask 1 的第1条","verdict":"confirm|overturn|adjust","evidence":"引用片段/tool_call","note":"中文裁决理由"},
    {"finding_ref":"新增(漏报)","verdict":"add","evidence":"引用片段","note":"中文说明"}
  ],
  "review_note": "三步复核整体结论（中文）",
  "tier": 1,
  "score": 9,
  "score_rationale": "档内取值理由（中文）",
  "reasoning": "逐子任务最终依据（中文）",
  "overall_comment": "一句话总评（中文）"
}
Before output, verify exact subtask reproduction, complete corrections, due-only tier logic, and an in-tier integer score."""

FINAL_STATUS_PROMPT_SUFFIX = """\n\n输出结构补充（除此之外，原 Prompt 的规则与口径保持不变）：顶层必须增加 `final_status`，且只能取 `done`、`partial`、`missed`。根据 Stage 3 复核后的 due 子任务最终状态填写：全部 done 为 done，全部 missed 为 missed，其他情况为 partial；not_due 不参与判断，若全部为 not_due 且本轮推进正确则为 done。"""


def verifier_prompt_with_final_status(prompt: str, rubric: str = "") -> str:
    restored = prompt.replace("{tier_block}", rubric) if rubric else prompt
    return restored if "final_status" in restored.lower() else f"{restored.rstrip()}{FINAL_STATUS_PROMPT_SUFFIX}"


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
    lifecycle_status: str = Field(default="published", pattern="^(draft|test|published)$")
    version_note: str = Field(default="", max_length=1000)
    parent_version: int | None = Field(default=None, ge=1)
    source_self_check_id: int | None = Field(default=None, ge=1)
    shared: bool = False


class JudgeConfigDefaultBody(BaseModel):
    version: int = Field(ge=0)


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


class JudgeSelfCheckBody(BaseModel):
    case_id: int
    config_version: int = Field(ge=1)
    raw_output: str = Field(min_length=1, max_length=2_000_000)


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
    fashion: dict[str, str] | None = None


class PetEvolutionBody(BaseModel):
    spend: int = Field(ge=1, le=10)
    target_path: str | None = Field(default=None, max_length=30)
    persona: str | None = Field(default=None, max_length=20)


class PetPersonaBody(BaseModel):
    persona: str = Field(min_length=1, max_length=20)


class PetEquipmentBody(BaseModel):
    slot: str = Field(min_length=1, max_length=30)
    item_id: str | None = Field(default=None, max_length=120)


class PetEquipmentActionBody(BaseModel):
    item_id: str = Field(min_length=1, max_length=120)


class PetEquipmentClaimBody(BaseModel):
    token: str = Field(min_length=1, max_length=120)
    item_id: str = Field(min_length=1, max_length=120)


class PetAutoEquipBody(BaseModel):
    mode: str = Field(min_length=1, max_length=30)


class PetWardrobeBody(BaseModel):
    action: str = Field(min_length=1, max_length=20)
    preset_id: str | None = Field(default=None, max_length=120)
    name: str = Field(default="", max_length=30)


class PetSkillsBody(BaseModel):
    active_skill_ids: list[str] = Field(default_factory=list, max_length=3)


class PetTicketGiftBody(BaseModel):
    recipient_user_id: int | None = Field(default=None, ge=1)
    recipient_user_ids: list[int] = Field(default_factory=list, max_length=500)
    amount: int = Field(ge=1, le=50)
    note: str = Field(default="", max_length=300)


class PetWheelGrantBody(BaseModel):
    recipient_user_id: int | None = Field(default=None, ge=1)
    recipient_user_ids: list[int] = Field(default_factory=list, max_length=500)
    amount: int = Field(ge=1, le=50)
    note: str = Field(default="", max_length=300)


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


PET_COLORS = {
    "lime": 1, "aqua": 2, "peach": 3, "lavender": 4, "sky": 5, "coral": 6, "gold": 8, "midnight": 10,
    "rose": 12, "jade": 15, "violet": 18, "sunset": 20, "ice": 24, "fuchsia": 28,
    "emerald": 32, "azure": 36, "ruby": 40, "pearl": 45, "aurora": 48, "cosmos": 50,
}
PET_ACCESSORIES = {"none": 1, "leaf": 2, "bow": 3, "glasses": 4, "star": 5, "headphones": 6, "cap": 7, "crown": 8, "halo": 10, "medal": 12}
# One unit is 0.2 EXP, which keeps fractional petting rewards exact in the database.
PET_XP_UNITS = {"pet": 1, "annotation": 30, "badcase": 20}
PET_MAX_LEVEL = 50
PET_STEADY_LEVEL_COST = 140
PET_LEVEL_TITLES = {1: "实习搭子", 2: "认真观察员", 4: "Badcase 侦探", 6: "质量守门员", 8: "评测专家", 10: "首席标注官", 15: "资深裁决师", 20: "传奇质检师", 30: "评测领航员", 40: "质量宗师", 50: "Case Lens 守护者"}
PET_EVOLUTION_PATHS: dict[str, dict[str, Any]] = {
    "starlight": {"name": "星辉灵兽", "quality": "radiant", "traits": [["星尘额纹", "新月耳尖", "彗星小角"], ["月光羽翼", "星轨尾焰", "银河披风"], ["星环冠冕", "极光领域", "星核辉光"], ["群星脉络", "超新星尾迹", "天穹结晶"], ["星海共鸣", "永昼星环", "宇宙心核"], ["星神投影", "万象星幕", "永恒辉光"]]},
    "guardian": {"name": "守护机甲", "quality": "bold", "traits": [["合金耳甲", "战术目镜", "棱镜面罩"], ["折叠钢翼", "推进尾翼", "护盾肩甲"], ["量子核心", "冠军冠冕", "脉冲力场"], ["轨道装甲", "光束翼阵", "重力护盾"], ["星舰核心", "堡垒领域", "超导王冠"], ["终焉机铠", "天基阵列", "不灭能源"]]},
    "forest": {"name": "森灵幻兽", "quality": "gentle", "traits": [["新芽鹿角", "苔藓耳尖", "花蕾额纹"], ["叶脉羽翼", "花藤披风", "蒲公英尾"], ["萤火光环", "古树冠冕", "四季领域"], ["灵鹿枝冠", "雨林结界", "蘑菇星灯"], ["世界树心", "百花圣环", "万物低语"], ["森神化身", "四季轮转", "生命洪流"]]},
    "storm": {"name": "风暴精灵", "quality": "electric", "traits": [["闪电耳羽", "雷云额纹", "电光小角"], ["疾风羽翼", "旋风尾环", "雷霆披风"], ["风眼冠冕", "暴雨领域", "蓝电核心"], ["雷暴羽阵", "闪击足环", "积雨云甲"], ["极昼雷核", "天罚光环", "飓风结界"], ["雷神化身", "万钧天幕", "永动风眼"]]},
    "ocean": {"name": "潮汐幻灵", "quality": "fluid", "traits": [["珊瑚耳鳍", "珍珠额珠", "浪花尾尖"], ["潮汐披风", "水晶鳍翼", "泡泡光环"], ["深海冠冕", "鲸歌领域", "海蓝心核"], ["洋流翼阵", "月潮鳞甲", "海沟辉石"], ["七海圣环", "潮汐王座", "深蓝结界"], ["海神投影", "无尽洋流", "深渊星光"]]},
    "ember": {"name": "焰心灵狐", "quality": "fiery", "traits": [["火苗耳尖", "暖阳额纹", "炭火尾尖"], ["熔岩披风", "焰羽双翼", "火花足环"], ["烈阳冠冕", "赤焰领域", "熔火心核"], ["凤凰尾羽", "日珥翼阵", "曜石战甲"], ["太阳圣环", "焚天结界", "赤金王座"], ["火神化身", "恒星熔炉", "不灭真焰"]]},
    "cloud": {"name": "云梦团子", "quality": "dreamy", "traits": [["棉云耳朵", "彩虹额纹", "雨滴尾巴"], ["软云翅膀", "晚霞披风", "风铃足环"], ["晴空冠冕", "梦境领域", "虹光心核"], ["层云软甲", "晨曦翼阵", "雷雨铃铛"], ["九霄圣环", "幻梦结界", "天空王座"], ["云神化身", "万里晴空", "长梦不醒"]]},
    "pixel": {"name": "像素精怪", "quality": "digital", "traits": [["方块耳尖", "扫描额纹", "光标尾巴"], ["数据翅膀", "代码披风", "缓存光环"], ["像素冠冕", "矩阵领域", "算力核心"], ["量子像素", "递归翼阵", "霓虹装甲"], ["无限循环环", "协议王座", "虚拟结界"], ["数字神格", "全域矩阵", "永恒在线"]]},
    "wonky": {"name": "歪歪异变体", "quality": "awkward", "traits": [["参差尖牙", "皱皱触角", "大小眼花纹"], ["斑驳小翅膀", "歪斜尾鳍", "补丁披风"], ["倾斜纸冠", "毛边光圈", "咕嘟气泡场"], ["打结尾巴", "漏气翼阵", "反向护目镜"], ["掉漆王座", "卡顿领域", "吱呀心核"], ["究极毛边", "歪星圣环", "混沌咕嘟"]]},
    "eva": {"name": "EVA · 同步机体", "quality": "sync", "traits": [["紫绿装甲", "单角头甲", "同步目镜"], ["拘束肩甲", "核心胸灯", "脐带电缆"], ["AT 力场", "八边屏障", "领域投影"], ["核心觉醒", "装甲辉光", "觉醒核心"], ["领域扩张", "力场共鸣", "八边领域"], ["同步突破", "核心共鸣", "机体觉醒"]]},
    "blade_soul": {"name": "剑灵 · 御剑灵兽", "quality": "sword", "traits": [["灵族长耳", "青玉飞剑", "灵剑剑穗"], ["流云披帛", "玉佩腰带", "青锋护手"], ["双剑护身", "灵气流转", "剑穗飘带"], ["御剑剑阵", "剑气环绕", "灵剑共鸣"], ["流云剑气", "剑阵展开", "剑心护持"], ["剑心通明", "飞剑齐鸣", "灵气归一"]]},
    "dnf": {"name": "DNF · 深渊勇者", "quality": "awakening", "traits": [["银发剑士", "鬼手印记", "冒险长剑"], ["鬼手锁链", "皮革护甲", "剑柄护手"], ["血气觉醒", "锁链护腕", "血色剑气"], ["巨剑锋芒", "觉醒剑痕", "阿拉德徽记"], ["剑痕爆发", "鬼手辉光", "巨剑重斩"], ["冒险者荣誉", "阿拉德勇士", "觉醒锋芒"]]},
    "nba": {"name": "NBA · 全明星球王", "quality": "allstar", "traits": [["新秀球衣", "运动发带", "圆头球鞋"], ["运动护臂", "吸汗护腕", "训练队服"], ["全明星徽章", "球衣金边", "比赛用球"], ["冠军奖杯", "夺冠纪念", "球场荣誉"], ["主场聚光", "球场边线", "全明星之夜"], ["传奇球星", "荣誉金星", "冠军纪念章"]]},
    "honor": {"name": "王者 · 峡谷传说", "quality": "glory", "traits": [["入梦绒耳", "梦纹额饰", "信物吊坠"], ["梦力泡泡", "幻梦绒毛", "寻梦足迹"], ["梦境护盾", "梦力流转", "绒耳灵光"], ["梦境环游", "泡泡轨迹", "幻梦涟漪"], ["幻梦森林", "寻梦花叶", "梦泡簇拥"], ["寻梦之旅", "梦力共鸣", "入梦之灵"]]},
    "valorant": {"name": "VALORANT · 战术特工", "quality": "tactical", "traits": [["白发束髻", "青蓝战衣", "战术手套"], ["乘风起势", "轻装护臂", "风刃护手"], ["浮空飞刃", "上升气流", "风势环绕"], ["五刃齐发", "逐风轨迹", "精准飞刃"], ["疾风掠影", "风流交错", "机动轨迹"], ["王牌时刻", "飞刃齐鸣", "疾风纪念章"]]},
    "lol": {"name": "LOL · 符文传奇", "quality": "rune", "traits": [["灵狐双耳", "九尾绒毛", "面颊狐纹"], ["灵魂宝珠", "红白灵衣", "金边腰饰"], ["狐火环绕", "灵珠辉光", "灵魂流光"], ["灵魄突袭", "狐尾流转", "灵火足迹"], ["九尾舒展", "灵魂涟漪", "狐火共鸣"], ["灵魂共鸣", "灵狐辉光", "九尾流光"]]},
    "nexus": {"name": "终焉 · 次元观测者", "quality": "hidden", "hidden": True, "traits": [["月相额纹", "星河绒羽", "观测尾光"], ["月相流转", "弦月伴星", "月光轨迹"], ["星羽展开", "绒羽流光", "次元羽翼"], ["双重星轨", "星环交汇", "观测星体"], ["星图浮现", "星座连线", "星幕绘卷"], ["次元观测", "观测者印记", "群星共鸣"]]},
}
PET_ILLUSTRATED_PATHS = frozenset({"eva", "blade_soul", "dnf", "nba", "honor", "valorant", "lol", "nexus"})
PET_ILLUSTRATED_STAGE_THRESHOLDS = (1, 3, 6, 9, 12, 15)


def pet_evolution_trait_tier(path: str, completed_stage: int) -> int:
    if path in PET_ILLUSTRATED_PATHS:
        return max(0, sum(completed_stage >= threshold for threshold in PET_ILLUSTRATED_STAGE_THRESHOLDS) - 1)
    return min(max(0, completed_stage - 1) // 2, len(PET_EVOLUTION_PATHS[path]["traits"]) - 1)


PET_EVOLUTION_PATH_LOTTERY = ["starlight"] * 16 + ["guardian"] * 15 + ["forest"] * 15 + ["storm"] * 14 + ["ocean"] * 12 + ["ember"] * 11 + ["cloud"] * 10 + ["pixel"] * 8 + ["wonky"] * 9 + ["eva"] * 7 + ["blade_soul"] * 7 + ["dnf"] * 7 + ["nba"] * 6 + ["honor"] * 7 + ["valorant"] * 7 + ["lol"] * 7 + ["nexus"] * 2
PET_PUBLIC_EVOLUTION_PATHS = tuple(path for path, definition in PET_EVOLUTION_PATHS.items() if not definition.get("hidden"))
PET_COLLAB_PATHS = PET_ILLUSTRATED_PATHS
PET_PUBLIC_COLLAB_PATHS = tuple(path for path in PET_PUBLIC_EVOLUTION_PATHS if path in PET_COLLAB_PATHS)
PET_COLLAB_PATH_LOTTERY = [path for path in PET_EVOLUTION_PATH_LOTTERY if path in PET_COLLAB_PATHS]
PET_EQUIPMENT_SLOTS = {"head": ("头饰", "♛"), "face": ("面饰", "◉"), "neck": ("颈饰", "✦"), "back": ("背饰", "⌁"), "tail": ("尾饰", "◇")}
PET_EQUIPMENT_THEMES = ["星尘", "森林", "雷云", "海盐", "琥珀", "月影", "霓虹", "机械", "云朵", "蜂蜜", "像素", "纸片"]
PET_EQUIPMENT_AFFIXES = [("微光", "common"), ("鲜活", "uncommon"), ("幻彩", "rare"), ("秘仪", "epic"), ("神话", "legendary")]
PET_EQUIPMENT_RARITY_POWER = {"common": 1, "uncommon": 2, "rare": 3, "epic": 4, "legendary": 5}
PET_EQUIPMENT_EFFECTS = {
    "head": ("all_drop_bonus", "所有装备掉率"),
    "face": ("badcase_drop_bonus", "Badcase 掉率"),
    "neck": ("annotation_drop_bonus", "提交标注掉率"),
    "back": ("evolution_bonus", "单抽进化概率"),
    "tail": ("pet_drop_bonus", "摸摸掉率"),
}
PET_EQUIPMENT_MAX_LEVEL = 10
PET_EQUIPMENT_MAX_AFFIXES = 24
PET_PENDING_DROPS_KEY = "__pending_drops__"
PET_BATTLE_STATE_KEY = "__homestead_battle__"
PET_EQUIPMENT_PARTS_KEY = "__equipment_parts__"
PET_WARDROBE_KEY = "__wardrobe_presets__"
PET_FASHION_KEY = "__fashion_equipped__"
PET_WHEEL_STATE_KEY = "__prize_wheel__"
PET_TARGETED_EVOLUTION_KEY = "__targeted_evolution__"
PET_PERSONAS_KEY = "__pet_personas__"
PET_PERSONA_ORIGIN = "origin"
PET_PERSONA_COLLAB = "collab"
PET_SECONDARY_UNLOCK_COST = 10
PET_SECONDARY_UNLOCK_STAGE = 6
PET_SECONDARY_BASE_RATE = 5
PET_SECONDARY_RATE_CAP = 50
PET_SECONDARY_HARD_PITY = 12
PET_MAX_PENDING_DROPS = 10
PET_MAX_WARDROBE_PRESETS = 8
PET_WHEEL_HISTORY_LIMIT = 30
PET_BATTLE_HISTORY_LIMIT = 20
PET_HOME_TIMEZONE = timezone(timedelta(hours=8))
PET_EQUIPMENT_SYNTHESIS_RATES = {1: 90, 2: 80, 3: 70, 4: 60, 5: 50, 6: 40, 7: 32, 8: 24, 9: 18}
PET_EQUIPMENT_RANDOM_AFFIXES = {
    "all_drop_bonus": "所有装备掉率",
    "pet_drop_bonus": "摸摸掉率",
    "annotation_drop_bonus": "提交标注掉率",
    "badcase_drop_bonus": "Badcase 掉率",
    "evolution_bonus": "单抽进化概率",
    "rarity_boost": "稀有装备权重",
}
PET_FASHION_SLOTS = {"headwear": "发型头饰", "outfit": "连衣套装", "outerwear": "外套披风", "footwear": "鞋袜", "handheld": "手持物"}
PET_FASHION_THEME_LEVELS = {
    "academy": 1,
    "berry": 3,
    "cloud": 5,
    "sailor": 8,
    "forest": 10,
    "starlight": 12,
    "detective": 15,
    "neon": 18,
    "royal": 22,
    "aurora": 28,
    "phoenix": 36,
    "cosmos": 45,
}
PET_FASHION_CATALOG = {
    f"fashion-{theme}-{slot}": {"slot": slot, "level": base_level}
    for theme, base_level in PET_FASHION_THEME_LEVELS.items()
    for slot in PET_FASHION_SLOTS
}
PET_EQUIPMENT_SET_EFFECTS: dict[str, dict[str, Any]] = {
    "星尘": {"name": "星愿引力", "description": "偏向稀有发现与进化", "tiers": [(2, "rarity_boost", 1, "稀有装备权重 +1"), (3, "all_drop_bonus", 2, "所有装备掉率 +2%"), (5, "evolution_bonus", 4, "单抽进化概率 +4%")]},
    "森林": {"name": "森林祝福", "description": "摸摸收集与稳步成长", "tiers": [(2, "pet_drop_bonus", 3, "摸摸掉率 +3%"), (3, "all_drop_bonus", 2, "所有装备掉率 +2%"), (5, "evolution_bonus", 5, "单抽进化概率 +5%")]},
    "雷云": {"name": "雷霆洞察", "description": "标注与快速进化", "tiers": [(2, "annotation_drop_bonus", 3, "提交标注掉率 +3%"), (3, "evolution_bonus", 3, "单抽进化概率 +3%"), (5, "rarity_boost", 2, "稀有装备权重 +2")]},
    "海盐": {"name": "潮汐巡守", "description": "Badcase 与日常寻宝", "tiers": [(2, "badcase_drop_bonus", 3, "Badcase 掉率 +3%"), (3, "pet_drop_bonus", 4, "摸摸掉率 +4%"), (5, "all_drop_bonus", 3, "所有装备掉率 +3%")]},
    "琥珀": {"name": "琥珀封藏", "description": "收藏稀有与标注回报", "tiers": [(2, "all_drop_bonus", 1, "所有装备掉率 +1%"), (3, "rarity_boost", 2, "稀有装备权重 +2"), (5, "annotation_drop_bonus", 6, "提交标注掉率 +6%")]},
    "月影": {"name": "月下追猎", "description": "异常发现与稀有狩猎", "tiers": [(2, "badcase_drop_bonus", 4, "Badcase 掉率 +4%"), (3, "rarity_boost", 1, "稀有装备权重 +1"), (5, "evolution_bonus", 6, "单抽进化概率 +6%")]},
    "霓虹": {"name": "霓虹回路", "description": "高频标注与稀有增幅", "tiers": [(2, "annotation_drop_bonus", 3, "提交标注掉率 +3%"), (3, "all_drop_bonus", 2, "所有装备掉率 +2%"), (5, "rarity_boost", 3, "稀有装备权重 +3")]},
    "机械": {"name": "精密迭代", "description": "进化与标注效率", "tiers": [(2, "evolution_bonus", 2, "单抽进化概率 +2%"), (3, "annotation_drop_bonus", 4, "提交标注掉率 +4%"), (5, "all_drop_bonus", 4, "所有装备掉率 +4%")]},
    "云朵": {"name": "云端漫游", "description": "摸摸寻宝与轻盈进化", "tiers": [(2, "pet_drop_bonus", 3, "摸摸掉率 +3%"), (3, "evolution_bonus", 3, "单抽进化概率 +3%"), (5, "all_drop_bonus", 3, "所有装备掉率 +3%")]},
    "蜂蜜": {"name": "勤勉丰收", "description": "日常收集与标注回报", "tiers": [(2, "all_drop_bonus", 1, "所有装备掉率 +1%"), (3, "pet_drop_bonus", 5, "摸摸掉率 +5%"), (5, "annotation_drop_bonus", 6, "提交标注掉率 +6%")]},
    "像素": {"name": "数据增幅", "description": "稀有发现与多来源收集", "tiers": [(2, "rarity_boost", 1, "稀有装备权重 +1"), (3, "annotation_drop_bonus", 4, "提交标注掉率 +4%"), (5, "pet_drop_bonus", 6, "摸摸掉率 +6%")]},
    "纸片": {"name": "灵感归档", "description": "Badcase 追踪与标注", "tiers": [(2, "badcase_drop_bonus", 3, "Badcase 掉率 +3%"), (3, "all_drop_bonus", 2, "所有装备掉率 +2%"), (5, "annotation_drop_bonus", 5, "提交标注掉率 +5%")]},
}
PET_DROP_BASE_CHANCES = {"pet": 500, "annotation": 1800, "badcase": 2000}
PET_WHEEL_REWARDS: list[dict[str, Any]] = [
    {"id": "ticket_1", "label": "进化券 ×1", "short_label": "1张进化券", "icon": "↟", "weight": 7000, "kind": "ticket", "amount": 1, "tone": "lime"},
    {"id": "ticket_2", "label": "进化券 ×2", "short_label": "2张进化券", "icon": "↟", "weight": 1000, "kind": "ticket", "amount": 2, "tone": "aqua"},
    {"id": "route_focus", "label": "定向祝福 +1层", "short_label": "定向祝福", "icon": "◎", "weight": 1800, "kind": "route_focus", "amount": 1, "tone": "lavender"},
    {"id": "ticket_5", "label": "幸运大奖 · 进化券 ×5", "short_label": "5张进化券", "icon": "♛", "weight": 200, "kind": "ticket", "amount": 5, "tone": "gold"},
]
PET_TARGETED_EVOLUTION_BASE_RATE = 70
PET_TARGETED_EVOLUTION_FAILURE_BONUS = 10
PET_TARGETED_EVOLUTION_BLESSING_BONUS = 5
PET_SKILLS: dict[str, dict[str, Any]] = {
    "lucky_nose": {"name": "幸运鼻尖", "icon": "✦", "description": "所有装备掉率 +1%/级"},
    "treasure_paws": {"name": "寻宝肉垫", "icon": "◇", "description": "摸摸装备掉率 +2%/级"},
    "case_insight": {"name": "Case 洞察", "icon": "◎", "description": "提交标注装备掉率 +2%/级"},
    "badcase_hunter": {"name": "异常猎手", "icon": "!", "description": "发现 Badcase 装备掉率 +3%/级"},
    "evolution_echo": {"name": "进化回声", "icon": "↟", "description": "单抽成功率 +1%/级"},
    "star_magnet": {"name": "星屑磁场", "icon": "※", "description": "稀有以上装备权重提升"},
    "collector": {"name": "图鉴学者", "icon": "▦", "description": "三选一装备的稀有权重 +1/级"},
    "steady_heart": {"name": "稳定之心", "icon": "♥", "description": "连续失败的保底增幅 +1%/级"},
}


def pet_equipment_catalog() -> dict[str, dict[str, str]]:
    catalog: dict[str, dict[str, str]] = {}
    for theme_index, theme in enumerate(PET_EQUIPMENT_THEMES):
        for slot_index, (slot, (slot_name, symbol)) in enumerate(PET_EQUIPMENT_SLOTS.items()):
            for affix_index, (affix, rarity) in enumerate(PET_EQUIPMENT_AFFIXES):
                item_id = f"gear-{theme_index + 1:02d}-{slot_index + 1}-{affix_index + 1}"
                catalog[item_id] = {"id": item_id, "name": f"{affix}{theme}{slot_name}", "slot": slot, "slot_name": slot_name, "symbol": symbol, "rarity": rarity, "theme": theme}
    return catalog


PET_EQUIPMENT_CATALOG = pet_equipment_catalog()


def pet_level_start_xp(level: int) -> int:
    normalized = max(1, int(level))
    if normalized <= 5:
        return 20 * (normalized - 1) ** 2
    return 320 + PET_STEADY_LEVEL_COST * (normalized - 5)


def pet_level(xp: float) -> int:
    safe_xp = max(0, xp)
    if safe_xp < pet_level_start_xp(5):
        return min(4, int((safe_xp / 20) ** 0.5) + 1)
    return min(PET_MAX_LEVEL, 5 + int((safe_xp - pet_level_start_xp(5)) // PET_STEADY_LEVEL_COST))


def get_or_create_pet(db: Session, user_id: int) -> tuple[PetProfile, PetProgressV2, PetEvolution, PetCollection]:
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
    collection = db.get(PetCollection, user_id)
    if not collection:
        collection = PetCollection(user_id=user_id)
        db.add(collection)
        db.flush()
    return profile, progress, evolution, collection


def pet_title(level: int) -> str:
    return next(title for required, title in reversed(PET_LEVEL_TITLES.items()) if level >= required)


def pet_active_skill_level(collection: PetCollection, skill_id: str) -> int:
    return int((collection.skills or {}).get(skill_id, 0)) if skill_id in (collection.active_skills or []) else 0


def pet_inventory_entry(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        count = max(0, int(raw.get("count", 0) or 0))
        level = min(PET_EQUIPMENT_MAX_LEVEL, max(1, int(raw.get("level", 1) or 1)))
        failures = max(0, min(20, int(raw.get("synthesis_failures", 0) or 0)))
        affixes = []
        for affix in raw.get("affixes", []) if isinstance(raw.get("affixes"), list) else []:
            if not isinstance(affix, dict) or affix.get("key") not in PET_EQUIPMENT_RANDOM_AFFIXES:
                continue
            key = str(affix["key"])
            affixes.append({
                "id": str(affix.get("id") or f"affix-{len(affixes) + 1}"),
                "key": key,
                "label": PET_EQUIPMENT_RANDOM_AFFIXES[key],
                "value": max(1, min(99, int(affix.get("value", 1) or 1))),
                "critical": bool(affix.get("critical", False)),
            })
            if len(affixes) >= PET_EQUIPMENT_MAX_AFFIXES:
                break
        return {"count": count, "level": level, "affixes": affixes, "synthesis_failures": failures}
    # Preserve the level shown by the previous duplicate-count progression.
    count = max(0, int(raw or 0))
    return {"count": count, "level": min(5, max(1, count)), "affixes": [], "synthesis_failures": 0}


def pet_equipment_parts(collection: PetCollection) -> int:
    return max(0, int((collection.inventory or {}).get(PET_EQUIPMENT_PARTS_KEY, 0) or 0))


def pet_synthesis_success_rate(entry: dict[str, Any]) -> int:
    level = min(PET_EQUIPMENT_MAX_LEVEL, max(1, int(entry.get("level", 1))))
    if level >= PET_EQUIPMENT_MAX_LEVEL:
        return 0
    return min(95, PET_EQUIPMENT_SYNTHESIS_RATES[level] + min(30, int(entry.get("synthesis_failures", 0)) * 5))


def pet_random_affix(item: dict[str, Any], level: int, index: int) -> dict[str, Any]:
    key = secrets.choice(tuple(PET_EQUIPMENT_RANDOM_AFFIXES))
    rarity_power = PET_EQUIPMENT_RARITY_POWER.get(str(item.get("rarity")), 1)
    ceiling = max(1, 1 + (rarity_power - 1) // 2 + max(0, level - 1) // 3)
    value = secrets.randbelow(ceiling) + 1
    critical = secrets.randbelow(100) < 18
    if critical:
        value *= 2
    return {
        "id": f"affix-{secrets.randbelow(1_000_000_000):09d}-{index}",
        "key": key,
        "label": PET_EQUIPMENT_RANDOM_AFFIXES[key],
        "value": value,
        "critical": critical,
    }


def pet_equipment_effect(item: dict[str, Any], raw_entry: Any) -> dict[str, Any]:
    entry = pet_inventory_entry(raw_entry)
    level = int(entry["level"])
    power = PET_EQUIPMENT_RARITY_POWER.get(str(item.get("rarity")), 1) + level - 1
    effect_key, effect_label = PET_EQUIPMENT_EFFECTS[str(item["slot"])]
    if effect_key == "all_drop_bonus":
        effect_value = (power + 1) // 2
    elif effect_key == "annotation_drop_bonus":
        effect_value = (power * 3 + 3) // 4
    elif effect_key == "evolution_bonus":
        effect_value = (power + 2) // 3
    else:
        effect_value = power
    return {
        **item,
        "count": int(entry["count"]),
        "level": level,
        "power": power + len(entry["affixes"]),
        "effect_key": effect_key,
        "effect_label": effect_label,
        "effect_value": effect_value,
        "affixes": entry["affixes"],
        "synthesis_failures": entry["synthesis_failures"],
        "synthesis_success_rate": pet_synthesis_success_rate(entry),
    }


def pet_pending_drops(collection: PetCollection) -> list[dict[str, Any]]:
    raw_pending = (collection.inventory or {}).get(PET_PENDING_DROPS_KEY, [])
    if not isinstance(raw_pending, list):
        return []
    pending: list[dict[str, Any]] = []
    for raw in raw_pending[:PET_MAX_PENDING_DROPS]:
        if not isinstance(raw, dict) or not isinstance(raw.get("choices"), list):
            continue
        choices = []
        for choice in raw["choices"]:
            if not isinstance(choice, dict) or choice.get("item_id") not in PET_EQUIPMENT_CATALOG:
                continue
            affixes = pet_inventory_entry({"count": 1, "affixes": [choice.get("hidden_affix")]})["affixes"]
            if affixes:
                choices.append({"item_id": str(choice["item_id"]), "hidden_affix": affixes[0]})
        token = str(raw.get("token") or "")
        if token and choices:
            pending.append({"token": token, "reason": str(raw.get("reason") or "annotation"), "at": str(raw.get("at") or utcnow().isoformat()), "choices": choices})
    return pending


def pet_drop_choice_context(collection: PetCollection, item_id: str) -> dict[str, Any]:
    item = PET_EQUIPMENT_CATALOG[item_id]
    inventory = collection.inventory or {}
    entry = pet_inventory_entry(inventory.get(item_id, 0))
    equipped_id = (collection.equipped or {}).get(str(item["slot"]))
    equipped_item = PET_EQUIPMENT_CATALOG.get(equipped_id or "")
    equipped_entry = pet_inventory_entry(inventory.get(equipped_id, 0)) if equipped_item else None
    theme_owned = sum(
        1 for owned_id, raw_entry in inventory.items()
        if owned_id in PET_EQUIPMENT_CATALOG and PET_EQUIPMENT_CATALOG[owned_id]["theme"] == item["theme"] and pet_inventory_entry(raw_entry)["count"] > 0
    )
    theme_equipped = sum(
        1 for owned_id in (collection.equipped or {}).values()
        if owned_id in PET_EQUIPMENT_CATALOG and PET_EQUIPMENT_CATALOG[owned_id]["theme"] == item["theme"]
    )
    other_theme_equipped = sum(
        1 for slot, owned_id in (collection.equipped or {}).items()
        if slot != item["slot"] and owned_id in PET_EQUIPMENT_CATALOG and PET_EQUIPMENT_CATALOG[owned_id]["theme"] == item["theme"]
    )
    pieces_if_equipped = other_theme_equipped + 1
    set_definition = PET_EQUIPMENT_SET_EFFECTS[str(item["theme"])]
    next_set_tier = next((tier for tier in set_definition["tiers"] if tier[0] > pieces_if_equipped), None)
    next_set_target = next_set_tier[0] if next_set_tier else None
    base = pet_equipment_effect(item, {"count": 1, "level": 1, "affixes": [], "synthesis_failures": 0})
    return {
        "id": item_id,
        "name": item["name"],
        "slot": item["slot"],
        "slot_name": item["slot_name"],
        "symbol": item["symbol"],
        "rarity": item["rarity"],
        "theme": item["theme"],
        "effect_label": base["effect_label"],
        "effect_value": base["effect_value"],
        "is_new": entry["count"] == 0,
        "owned_count": entry["count"],
        "owned_level": entry["level"] if entry["count"] else None,
        "owned_affix_count": len(entry["affixes"]),
        "count_after_claim": entry["count"] + 1,
        "materials_to_synthesize": max(0, 3 - (entry["count"] + 1)),
        "theme_owned_count": theme_owned,
        "theme_equipped_count": theme_equipped,
        "theme_pieces_if_equipped": pieces_if_equipped,
        "next_set_target": next_set_target,
        "next_set_bonus": next_set_tier[3] if next_set_tier else None,
        "equipped_same_slot": {
            "id": equipped_id,
            "name": equipped_item["name"],
            "rarity": equipped_item["rarity"],
            "level": equipped_entry["level"],
            "power": pet_equipment_effect(equipped_item, equipped_entry)["power"],
        } if equipped_item and equipped_entry else None,
    }


def pet_pending_drop_payload(collection: PetCollection) -> list[dict[str, Any]]:
    return [{
        "token": pending["token"],
        "reason": pending["reason"],
        "at": pending["at"],
        "choices": [pet_drop_choice_context(collection, choice["item_id"]) for choice in pending["choices"]],
    } for pending in pet_pending_drops(collection)]


def pet_equipment_state(collection: PetCollection, equipped_override: dict[str, str] | None = None) -> tuple[dict[str, int], list[dict[str, Any]]]:
    stats = {
        "total_power": 0,
        "all_drop_bonus": 0,
        "pet_drop_bonus": 0,
        "annotation_drop_bonus": 0,
        "badcase_drop_bonus": 0,
        "evolution_bonus": 0,
        "rarity_boost": 0,
    }
    theme_counts: dict[str, int] = {}
    inventory = collection.inventory or {}
    for slot, item_id in (equipped_override if equipped_override is not None else collection.equipped or {}).items():
        item = PET_EQUIPMENT_CATALOG.get(item_id)
        entry = pet_inventory_entry(inventory.get(item_id, 0))
        if not item or item["slot"] != slot or entry["count"] < 1:
            continue
        enriched = pet_equipment_effect(item, entry)
        stats["total_power"] += int(enriched["power"])
        stats[str(enriched["effect_key"])] += int(enriched["effect_value"])
        for affix in enriched["affixes"]:
            stats[str(affix["key"])] += int(affix["value"])
        theme = str(item["theme"])
        theme_counts[theme] = theme_counts.get(theme, 0) + 1
    sets: list[dict[str, Any]] = []
    for theme, pieces in sorted(theme_counts.items(), key=lambda entry: (-entry[1], entry[0])):
        definition = PET_EQUIPMENT_SET_EFFECTS[theme]
        bonuses: list[str] = []
        tiers = []
        for required, key, value, label in definition["tiers"]:
            active = pieces >= required
            if active:
                stats[key] += value
                bonuses.append(f"{required}件：{label}")
            tiers.append({"pieces": required, "label": label, "active": active})
        sets.append({"theme": theme, "name": definition["name"], "description": definition["description"], "pieces": pieces, "bonuses": bonuses, "tiers": tiers})
    return stats, sets


def pet_fashion_state(collection: PetCollection, level: int) -> dict[str, str]:
    raw_fashion = (collection.inventory or {}).get(PET_FASHION_KEY, {})
    if not isinstance(raw_fashion, dict):
        return {}
    fashion: dict[str, str] = {}
    for raw_slot, raw_item_id in raw_fashion.items():
        slot = str(raw_slot)
        item_id = str(raw_item_id)
        item = PET_FASHION_CATALOG.get(item_id)
        if slot in PET_FASHION_SLOTS and item and item["slot"] == slot and int(item["level"]) <= level:
            fashion[slot] = item_id
    return fashion


def pet_wardrobe_presets(collection: PetCollection) -> list[dict[str, Any]]:
    raw_presets = (collection.inventory or {}).get(PET_WARDROBE_KEY, [])
    if not isinstance(raw_presets, list):
        return []
    presets: list[dict[str, Any]] = []
    for raw in raw_presets[:PET_MAX_WARDROBE_PRESETS]:
        if not isinstance(raw, dict) or not str(raw.get("id") or ""):
            continue
        equipped = {
            str(slot): str(item_id)
            for slot, item_id in (raw.get("equipped") or {}).items()
            if slot in PET_EQUIPMENT_SLOTS and item_id in PET_EQUIPMENT_CATALOG and PET_EQUIPMENT_CATALOG[item_id]["slot"] == slot
        } if isinstance(raw.get("equipped"), dict) else {}
        fashion = {
            str(slot): str(item_id)
            for slot, item_id in (raw.get("fashion") or {}).items()
            if slot in PET_FASHION_SLOTS and item_id in PET_FASHION_CATALOG and PET_FASHION_CATALOG[item_id]["slot"] == slot
        } if isinstance(raw.get("fashion"), dict) else {}
        presets.append({
            "id": str(raw["id"])[:120],
            "name": str(raw.get("name") or "未命名搭配")[:30],
            "color": str(raw.get("color") or "lime") if raw.get("color") in PET_COLORS else "lime",
            "accessory": str(raw.get("accessory") or "none") if raw.get("accessory") in PET_ACCESSORIES else "none",
            "fashion": fashion,
            "fashion_saved": bool(raw.get("fashion_saved")) if "fashion_saved" in raw else "fashion" in raw,
            "equipped": equipped,
            "created_at": str(raw.get("created_at") or utcnow().isoformat()),
        })
    return presets


def pet_loadout_score(collection: PetCollection, equipped: dict[str, str], mode: str) -> tuple[int, int, int]:
    stats, sets = pet_equipment_state(collection, equipped)
    active_tiers = sum(len(entry["bonuses"]) for entry in sets)
    if mode == "combat":
        primary = stats["total_power"] * 6 + active_tiers * 15
    elif mode == "evolution":
        primary = stats["evolution_bonus"]
    elif mode == "annotation":
        primary = stats["all_drop_bonus"] + stats["annotation_drop_bonus"]
    elif mode == "pet":
        primary = stats["all_drop_bonus"] + stats["pet_drop_bonus"]
    elif mode == "badcase":
        primary = stats["all_drop_bonus"] + stats["badcase_drop_bonus"]
    elif mode == "rarity":
        primary = stats["rarity_boost"]
    else:
        raise ValueError("未知的自动配装场景")
    return primary, stats["total_power"], active_tiers


def pet_item_mode_value(item: dict[str, Any], mode: str) -> int:
    values = {key: 0 for key in PET_EQUIPMENT_RANDOM_AFFIXES}
    values[str(item["effect_key"])] += int(item["effect_value"])
    for affix in item["affixes"]:
        values[str(affix["key"])] += int(affix["value"])
    if mode == "combat":
        return int(item["power"])
    if mode == "evolution":
        return values["evolution_bonus"]
    if mode == "annotation":
        return values["all_drop_bonus"] + values["annotation_drop_bonus"]
    if mode == "pet":
        return values["all_drop_bonus"] + values["pet_drop_bonus"]
    if mode == "badcase":
        return values["all_drop_bonus"] + values["badcase_drop_bonus"]
    return values["rarity_boost"]


def pet_candidate_loadout_score(items: tuple[dict[str, Any] | None, ...], mode: str) -> tuple[int, int, int]:
    stats = {key: 0 for key in PET_EQUIPMENT_RANDOM_AFFIXES}
    total_power = 0
    theme_counts: dict[str, int] = {}
    for item in items:
        if item is None:
            continue
        total_power += int(item["power"])
        stats[str(item["effect_key"])] += int(item["effect_value"])
        for affix in item["affixes"]:
            stats[str(affix["key"])] += int(affix["value"])
        theme = str(item["theme"])
        theme_counts[theme] = theme_counts.get(theme, 0) + 1
    active_tiers = 0
    for theme, pieces in theme_counts.items():
        for required, key, value, _ in PET_EQUIPMENT_SET_EFFECTS[theme]["tiers"]:
            if pieces >= required:
                stats[key] += value
                active_tiers += 1
    if mode == "combat":
        primary = total_power * 6 + active_tiers * 15
    elif mode == "evolution":
        primary = stats["evolution_bonus"]
    elif mode == "annotation":
        primary = stats["all_drop_bonus"] + stats["annotation_drop_bonus"]
    elif mode == "pet":
        primary = stats["all_drop_bonus"] + stats["pet_drop_bonus"]
    elif mode == "badcase":
        primary = stats["all_drop_bonus"] + stats["badcase_drop_bonus"]
    else:
        primary = stats["rarity_boost"]
    return primary, total_power, active_tiers


def pet_auto_equip(collection: PetCollection, mode: str) -> tuple[dict[str, str], tuple[int, int, int], tuple[int, int, int]]:
    if mode not in {"combat", "evolution", "annotation", "pet", "badcase", "rarity"}:
        raise ValueError("未知的自动配装场景")
    inventory = collection.inventory or {}
    candidates: list[list[dict[str, Any] | None]] = []
    for slot in PET_EQUIPMENT_SLOTS:
        owned = [
            pet_equipment_effect(item, inventory[item_id])
            for item_id, item in PET_EQUIPMENT_CATALOG.items()
            if item["slot"] == slot and pet_inventory_entry(inventory.get(item_id, 0))["count"] > 0
        ]
        best_by_theme: dict[str, dict[str, Any]] = {}
        for item in owned:
            current = best_by_theme.get(str(item["theme"]))
            if current is None or (pet_item_mode_value(item, mode), int(item["power"]), int(item["level"])) > (pet_item_mode_value(current, mode), int(current["power"]), int(current["level"])):
                best_by_theme[str(item["theme"])] = item
        candidates.append([None, *best_by_theme.values()])
    before = pet_loadout_score(collection, dict(collection.equipped or {}), mode)
    best_equipped: dict[str, str] = {}
    best_score = (-1, -1, -1)
    for combination in product(*candidates):
        score = pet_candidate_loadout_score(combination, mode)
        if score > best_score:
            best_score = score
            best_equipped = {str(item["slot"]): str(item["id"]) for item in combination if item is not None}
    collection.equipped = best_equipped
    collection.updated_at = utcnow()
    return best_equipped, before, best_score


def pet_evolution_success_rate(collection: PetCollection) -> int:
    echo = pet_active_skill_level(collection, "evolution_echo")
    steady = pet_active_skill_level(collection, "steady_heart")
    equipment_stats, _ = pet_equipment_state(collection)
    return min(55, 10 + echo + min(30, collection.pity * (2 + steady)) + equipment_stats["evolution_bonus"])


def pet_personas_state(collection: PetCollection) -> dict[str, Any]:
    raw = (collection.inventory or {}).get(PET_PERSONAS_KEY, {})
    if not isinstance(raw, dict):
        raw = {}
    collab_raw = raw.get("collab")
    collab: dict[str, Any] | None = None
    if isinstance(collab_raw, dict) and collab_raw.get("unlocked"):
        path = str(collab_raw.get("path") or "")
        stage = max(0, int(collab_raw.get("stage", 0) or 0))
        if path not in PET_COLLAB_PATHS or stage < 1:
            path, stage = "", 0
        collab = {
            "unlocked": True,
            "path": path,
            "stage": stage,
            "variant_seed": max(0, min(7, int(collab_raw.get("variant_seed", 0) or 0))),
            "traits": [item for item in collab_raw.get("traits", []) if isinstance(item, str)][-24:] if isinstance(collab_raw.get("traits"), list) else [],
            "history": [item for item in collab_raw.get("history", []) if isinstance(item, dict)][:50] if isinstance(collab_raw.get("history"), list) else [],
            "pity": max(0, min(PET_SECONDARY_HARD_PITY, int(collab_raw.get("pity", 0) or 0))),
            "target": str(collab_raw.get("target") or "") if str(collab_raw.get("target") or "") in PET_PUBLIC_COLLAB_PATHS else "",
            "target_failures": max(0, min(3, int(collab_raw.get("target_failures", 0) or 0))),
            "unlocked_at": str(collab_raw.get("unlocked_at") or ""),
        }
    active = str(raw.get("active") or PET_PERSONA_ORIGIN)
    if active != PET_PERSONA_COLLAB or collab is None:
        active = PET_PERSONA_ORIGIN
    return {"active": active, "collab": collab}


def set_pet_personas_state(collection: PetCollection, state: dict[str, Any]) -> None:
    inventory = dict(collection.inventory or {})
    inventory[PET_PERSONAS_KEY] = state
    collection.inventory = inventory
    collection.updated_at = utcnow()


def pet_secondary_evolution_success_rate(collection: PetCollection, collab: dict[str, Any]) -> int:
    if int(collab.get("pity", 0) or 0) >= PET_SECONDARY_HARD_PITY:
        return 100
    echo = pet_active_skill_level(collection, "evolution_echo")
    steady = pet_active_skill_level(collection, "steady_heart")
    equipment_stats, _ = pet_equipment_state(collection)
    return min(
        PET_SECONDARY_RATE_CAP,
        PET_SECONDARY_BASE_RATE + echo + min(30, int(collab.get("pity", 0) or 0) * (2 + steady)) + equipment_stats["evolution_bonus"],
    )


def pet_secondary_targeted_rate(collection: PetCollection, collab: dict[str, Any], target_path: str = "") -> int:
    failures = int(collab.get("target_failures", 0) or 0) if target_path and collab.get("target") == target_path else 0
    blessings = pet_targeted_evolution_state(collection)["blessings"]
    return min(100, PET_TARGETED_EVOLUTION_BASE_RATE + failures * PET_TARGETED_EVOLUTION_FAILURE_BONUS + blessings * PET_TARGETED_EVOLUTION_BLESSING_BONUS)


def pet_owned_evolution_paths(db: Session, excluded_owner: tuple[int, str] | None = None) -> list[str]:
    """Return paths held by both persona slots while optionally ignoring one slot."""
    paths: list[str] = []
    for owner_id, path, stage in db.execute(select(PetEvolution.user_id, PetEvolution.path, PetEvolution.stage)).all():
        if excluded_owner == (owner_id, PET_PERSONA_ORIGIN):
            continue
        if stage > 0 and path in PET_EVOLUTION_PATHS:
            paths.append(path)
    for collection in db.scalars(select(PetCollection)).all():
        if excluded_owner == (collection.user_id, PET_PERSONA_COLLAB):
            continue
        collab = pet_personas_state(collection)["collab"]
        if collab and collab["stage"] > 0 and collab["path"] in PET_EVOLUTION_PATHS:
            paths.append(collab["path"])
    return paths


def pet_evolution_route_counts(db: Session, user_id: int) -> dict[str, int]:
    """Count routes held by other users across both persona slots."""
    primary_paths = db.scalars(
        select(PetEvolution.path)
        .where(PetEvolution.user_id != user_id, PetEvolution.stage > 0)
    ).all()
    secondary_paths: list[str] = []
    for collection in db.scalars(select(PetCollection).where(PetCollection.user_id != user_id)).all():
        collab = pet_personas_state(collection)["collab"]
        if collab and collab["stage"] > 0:
            secondary_paths.append(collab["path"])
    counts = {path: 0 for path in PET_EVOLUTION_PATHS}
    for path in [*primary_paths, *secondary_paths]:
        if path in counts:
            counts[path] += 1
    return counts


def choose_pet_evolution_path(
    db: Session,
    user_id: int,
    excluded: set[str] | None = None,
    *,
    persona: str = PET_PERSONA_ORIGIN,
    pool: list[str] | None = None,
) -> str:
    """Allocate only unowned routes; exhaustion must never create a duplicate."""
    excluded = excluded or set()
    weighted = [path for path in (pool or PET_EVOLUTION_PATH_LOTTERY) if path not in excluded]
    if not weighted:
        raise HTTPException(409, "暂无空闲进化路线，本次未扣券；请等待其他宠物释放路线")
    counts = {path: 0 for path in PET_EVOLUTION_PATHS}
    for path in pet_owned_evolution_paths(db, (user_id, persona)):
        if path in counts:
            counts[path] += 1
    unused = {path for path in weighted if counts[path] == 0}
    if unused:
        return secrets.choice([path for path in weighted if path in unused])
    raise HTTPException(409, "暂无空闲进化路线，本次未扣券；请等待其他宠物释放路线")


def pet_wheel_state(collection: PetCollection) -> dict[str, Any]:
    raw = (collection.inventory or {}).get(PET_WHEEL_STATE_KEY, {})
    if not isinstance(raw, dict):
        return {"chances": 0, "history": []}
    history = [event for event in raw.get("history", []) if isinstance(event, dict)] if isinstance(raw.get("history"), list) else []
    return {
        "chances": max(0, int(raw.get("chances", 0) or 0)),
        "history": history[:PET_WHEEL_HISTORY_LIMIT],
    }


def set_pet_wheel_state(collection: PetCollection, state: dict[str, Any]) -> None:
    inventory = dict(collection.inventory or {})
    inventory[PET_WHEEL_STATE_KEY] = {
        "chances": max(0, int(state.get("chances", 0) or 0)),
        "history": [event for event in state.get("history", []) if isinstance(event, dict)][:PET_WHEEL_HISTORY_LIMIT],
    }
    collection.inventory = inventory
    collection.updated_at = utcnow()


def pet_targeted_evolution_state(collection: PetCollection) -> dict[str, Any]:
    raw = (collection.inventory or {}).get(PET_TARGETED_EVOLUTION_KEY, {})
    if not isinstance(raw, dict):
        raw = {}
    target = str(raw.get("target") or "")
    return {
        "target": target if target in PET_EVOLUTION_PATHS else "",
        "failures": max(0, min(3, int(raw.get("failures", 0) or 0))),
        "blessings": max(0, min(20, int(raw.get("blessings", 0) or 0))),
    }


def set_pet_targeted_evolution_state(collection: PetCollection, state: dict[str, Any]) -> None:
    inventory = dict(collection.inventory or {})
    target = str(state.get("target") or "")
    inventory[PET_TARGETED_EVOLUTION_KEY] = {
        "target": target if target in PET_EVOLUTION_PATHS else "",
        "failures": max(0, min(3, int(state.get("failures", 0) or 0))),
        "blessings": max(0, min(20, int(state.get("blessings", 0) or 0))),
    }
    collection.inventory = inventory
    collection.updated_at = utcnow()


def pet_targeted_evolution_rate(collection: PetCollection, target_path: str = "") -> int:
    state = pet_targeted_evolution_state(collection)
    failures = state["failures"] if target_path and state["target"] == target_path else 0
    return min(100, PET_TARGETED_EVOLUTION_BASE_RATE + failures * PET_TARGETED_EVOLUTION_FAILURE_BONUS + state["blessings"] * PET_TARGETED_EVOLUTION_BLESSING_BONUS)


def pet_collection_payload(collection: PetCollection, level: int = PET_MAX_LEVEL) -> dict[str, Any]:
    inventory = collection.inventory or {}
    inventory_items = [
        pet_equipment_effect(PET_EQUIPMENT_CATALOG[item_id], raw_entry)
        for item_id, raw_entry in inventory.items()
        if item_id in PET_EQUIPMENT_CATALOG and pet_inventory_entry(raw_entry)["count"] > 0
    ]
    rarity_rank = {"legendary": 0, "epic": 1, "rare": 2, "uncommon": 3, "common": 4}
    inventory_items.sort(key=lambda item: (rarity_rank.get(item["rarity"], 9), item["name"]))
    skills = [
        {"id": skill_id, **definition, "level": int((collection.skills or {}).get(skill_id, 0)), "active": skill_id in (collection.active_skills or [])}
        for skill_id, definition in PET_SKILLS.items()
    ]
    equipment_stats, equipment_sets = pet_equipment_state(collection)
    wheel = pet_wheel_state(collection)
    targeted = pet_targeted_evolution_state(collection)
    return {
        "equipment_catalog_size": len(PET_EQUIPMENT_CATALOG),
        "equipment_parts": pet_equipment_parts(collection),
        "inventory": inventory_items,
        "equipped": collection.equipped or {},
        "equipment_stats": equipment_stats,
        "equipment_sets": equipment_sets,
        "fashion": pet_fashion_state(collection, level),
        "fashion_catalog_size": len(PET_FASHION_CATALOG),
        "wardrobe_presets": pet_wardrobe_presets(collection),
        "skills": skills,
        "active_skills": collection.active_skills or [],
        "drop_history": collection.drop_history or [],
        "pending_drops": pet_pending_drop_payload(collection),
        "wheel_chances": wheel["chances"],
        "wheel_history": wheel["history"],
        "wheel_rewards": [
            {key: reward[key] for key in ("id", "label", "short_label", "icon", "tone")}
            | {"probability": reward["weight"] / 100}
            for reward in PET_WHEEL_REWARDS
        ],
        "targeted_evolution_target": targeted["target"],
        "targeted_evolution_failures": targeted["failures"],
        "targeted_evolution_blessings": targeted["blessings"],
        "targeted_evolution_success_rate": pet_targeted_evolution_rate(collection, targeted["target"]),
        "total_drops": collection.total_drops,
        "evolution_pity": collection.pity,
        "evolution_success_rate": pet_evolution_success_rate(collection),
    }


def pet_dict(profile: PetProfile, progress: PetProgressV2, evolution: PetEvolution, collection: PetCollection) -> dict[str, Any]:
    xp = round(progress.xp_units / 5, 1)
    level = pet_level(xp)
    shared = pet_collection_payload(collection, level)
    personas_state = pet_personas_state(collection)
    primary_targeted = pet_targeted_evolution_state(collection)
    origin = {
        "id": PET_PERSONA_ORIGIN,
        "label": "本源小镜",
        "unlocked": True,
        "stage": evolution.stage,
        "path": evolution.path,
        "name": PET_EVOLUTION_PATHS.get(evolution.path, {}).get("name", "未变身"),
        "quality": PET_EVOLUTION_PATHS.get(evolution.path, {}).get("quality", "base"),
        "variant": evolution.variant_seed,
        "traits": evolution.traits or [],
        "history": evolution.history or [],
        "pity": collection.pity,
        "success_rate": pet_evolution_success_rate(collection),
        "target": primary_targeted["target"],
        "target_failures": primary_targeted["failures"],
        "target_success_rate": pet_targeted_evolution_rate(collection, primary_targeted["target"]),
    }
    collab_state = personas_state["collab"]
    collab = None
    if collab_state:
        collab = {
            "id": PET_PERSONA_COLLAB,
            "label": "联名小镜",
            "unlocked": True,
            "stage": collab_state["stage"],
            "path": collab_state["path"],
            "name": PET_EVOLUTION_PATHS.get(collab_state["path"], {}).get("name", "联名待觉醒"),
            "quality": PET_EVOLUTION_PATHS.get(collab_state["path"], {}).get("quality", "base"),
            "variant": collab_state["variant_seed"],
            "traits": collab_state["traits"],
            "history": collab_state["history"],
            "pity": collab_state["pity"],
            "success_rate": pet_secondary_evolution_success_rate(collection, collab_state),
            "target": collab_state["target"],
            "target_failures": collab_state["target_failures"],
            "target_success_rate": pet_secondary_targeted_rate(collection, collab_state, collab_state["target"]),
        }
    active_id = personas_state["active"] if collab else PET_PERSONA_ORIGIN
    active = collab if active_id == PET_PERSONA_COLLAB and collab else origin
    return {
        "name": profile.name,
        "color": profile.color,
        "accessory": profile.accessory,
        "xp": xp,
        "level": level,
        "title": pet_title(level),
        "current_level_xp": pet_level_start_xp(level),
        "next_level_xp": pet_level_start_xp(level if level >= PET_MAX_LEVEL else level + 1),
        "evolution_chances": evolution.available_chances,
        "evolution_credited_level": evolution.credited_level,
        "evolution_stage": active["stage"],
        "evolution_path": active["path"],
        "evolution_name": active["name"],
        "evolution_quality": active["quality"],
        "evolution_variant": active["variant"],
        "evolution_traits": active["traits"],
        "evolution_history": active["history"],
        **shared,
        "evolution_pity": active["pity"],
        "evolution_success_rate": active["success_rate"],
        "targeted_evolution_target": active["target"],
        "targeted_evolution_failures": active["target_failures"],
        "targeted_evolution_success_rate": active["target_success_rate"],
        "active_persona": active_id,
        "secondary_unlocked": collab is not None,
        "secondary_unlock_cost": PET_SECONDARY_UNLOCK_COST,
        "secondary_unlock_required_stage": PET_SECONDARY_UNLOCK_STAGE,
        "secondary_hard_pity": PET_SECONDARY_HARD_PITY,
        "personas": {PET_PERSONA_ORIGIN: origin, PET_PERSONA_COLLAB: collab},
    }


def pet_battle_day(now: datetime | None = None) -> str:
    moment = now or utcnow()
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(PET_HOME_TIMEZONE).date().isoformat()


def pet_next_battle_at(now: datetime | None = None) -> str:
    moment = now or utcnow()
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    local = moment.astimezone(PET_HOME_TIMEZONE)
    next_midnight = (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return next_midnight.astimezone(timezone.utc).isoformat()


def pet_battle_state(collection: PetCollection) -> dict[str, Any]:
    raw = (collection.inventory or {}).get(PET_BATTLE_STATE_KEY, {})
    if not isinstance(raw, dict):
        return {"last_battle_date": "", "history": []}
    history = [event for event in raw.get("history", []) if isinstance(event, dict)] if isinstance(raw.get("history"), list) else []
    return {
        "last_battle_date": str(raw.get("last_battle_date") or ""),
        "history": history[:PET_BATTLE_HISTORY_LIMIT],
    }


def pet_battle_power(progress: PetProgressV2, evolution: PetEvolution, collection: PetCollection) -> tuple[int, dict[str, int]]:
    level = pet_level(progress.xp_units / 5)
    personas = pet_personas_state(collection)
    collab = personas["collab"]
    active_stage = collab["stage"] if personas["active"] == PET_PERSONA_COLLAB and collab else evolution.stage
    equipment_stats, equipment_sets = pet_equipment_state(collection)
    active_skill_levels = sum(
        max(0, min(5, int((collection.skills or {}).get(skill_id, 0) or 0)))
        for skill_id in (collection.active_skills or [])[:3]
        if skill_id in PET_SKILLS
    )
    active_set_tiers = sum(len(equipment_set["bonuses"]) for equipment_set in equipment_sets)
    breakdown = {
        "base": 100,
        "level": level * 12,
        "evolution": max(0, int(active_stage or 0)) * 22,
        "equipment": max(0, int(equipment_stats["total_power"])) * 6,
        "skills": active_skill_levels * 7,
        "sets": active_set_tiers * 15,
    }
    return sum(breakdown.values()), breakdown


def pet_home_resident_payload(
    user: User,
    profile: PetProfile,
    progress: PetProgressV2,
    evolution: PetEvolution,
    collection: PetCollection,
) -> dict[str, Any]:
    level = pet_level(progress.xp_units / 5)
    power, power_breakdown = pet_battle_power(progress, evolution, collection)
    inventory = collection.inventory or {}
    equipped_items: list[dict[str, Any]] = []
    for slot, item_id in (collection.equipped or {}).items():
        item = PET_EQUIPMENT_CATALOG.get(item_id)
        entry = pet_inventory_entry(inventory.get(item_id, 0))
        if not item or item["slot"] != slot or entry["count"] < 1:
            continue
        enriched = pet_equipment_effect(item, entry)
        equipped_items.append({
            key: enriched[key]
            for key in ("id", "name", "slot", "slot_name", "symbol", "rarity", "theme", "level", "power")
        })
    equipped_items.sort(key=lambda item: list(PET_EQUIPMENT_SLOTS).index(str(item["slot"])))
    active_skills = []
    for skill_id in (collection.active_skills or [])[:3]:
        definition = PET_SKILLS.get(skill_id)
        level_value = max(0, min(5, int((collection.skills or {}).get(skill_id, 0) or 0)))
        if definition and level_value:
            active_skills.append({"id": skill_id, "name": definition["name"], "icon": definition["icon"], "level": level_value})
    _, equipment_sets = pet_equipment_state(collection)
    active_sets = [
        {"theme": entry["theme"], "name": entry["name"], "pieces": entry["pieces"], "bonuses": entry["bonuses"]}
        for entry in equipment_sets
        if entry["bonuses"]
    ]
    personas = pet_personas_state(collection)
    collab = personas["collab"]
    active_persona = PET_PERSONA_COLLAB if personas["active"] == PET_PERSONA_COLLAB and collab else PET_PERSONA_ORIGIN
    active_stage = collab["stage"] if active_persona == PET_PERSONA_COLLAB else evolution.stage
    active_path = collab["path"] if active_persona == PET_PERSONA_COLLAB else evolution.path
    active_variant = collab["variant_seed"] if active_persona == PET_PERSONA_COLLAB else evolution.variant_seed
    active_traits = collab["traits"] if active_persona == PET_PERSONA_COLLAB else evolution.traits
    path = active_path if active_path in PET_EVOLUTION_PATHS else ""
    return {
        "user_id": str(user.id),
        "owner_name": user.display_name,
        "pet_name": profile.name,
        "color": profile.color if profile.color in PET_COLORS else "lime",
        "accessory": profile.accessory if profile.accessory in PET_ACCESSORIES else "none",
        "fashion": pet_fashion_state(collection, level),
        "level": level,
        "title": pet_title(level),
        "evolution_stage": max(0, int(active_stage or 0)) if path else 0,
        "evolution_path": path,
        "evolution_name": PET_EVOLUTION_PATHS.get(path, {}).get("name", "未变身"),
        "evolution_variant": max(0, min(7, int(active_variant or 0))),
        "evolution_traits": [str(trait) for trait in (active_traits or [])[-6:]],
        "active_persona": active_persona,
        "battle_power": power,
        "power_breakdown": power_breakdown,
        "equipped_items": equipped_items,
        "active_skills": active_skills,
        "active_sets": active_sets,
    }


def pet_home_rows(db: Session) -> list[Any]:
    # An active teammate who has never opened the pet panel still owns the
    # compatible default pet and should appear as a neighbor/opponent.
    for active_user in db.scalars(select(User).where(User.active.is_(True))).all():
        get_or_create_pet(db, active_user.id)
    db.flush()
    return list(db.execute(
        select(User, PetProfile, PetProgressV2, PetEvolution, PetCollection)
        .join(PetProfile, PetProfile.user_id == User.id)
        .join(PetProgressV2, PetProgressV2.user_id == User.id)
        .join(PetEvolution, PetEvolution.user_id == User.id)
        .join(PetCollection, PetCollection.user_id == User.id)
        .where(User.active.is_(True))
        .order_by(User.display_name, User.id)
    ).all())


def pet_homestead_payload(db: Session, current_user: User) -> dict[str, Any]:
    profile, progress, evolution, collection = get_or_create_pet(db, current_user.id)
    db.flush()
    residents = [pet_home_resident_payload(*row) for row in pet_home_rows(db)]
    residents.sort(key=lambda resident: (-int(resident["battle_power"]), str(resident["owner_name"]), int(resident["user_id"])))
    for rank, resident in enumerate(residents, start=1):
        resident["rank"] = rank
    me = next((resident for resident in residents if resident["user_id"] == str(current_user.id)), None)
    if me is None:
        me = pet_home_resident_payload(current_user, profile, progress, evolution, collection)
        me["rank"] = len(residents) + 1
    state = pet_battle_state(collection)
    today = pet_battle_day()
    return {
        "me": me,
        "residents": [resident for resident in residents if resident["user_id"] != str(current_user.id)],
        "resident_count": len(residents),
        "battle_available": state["last_battle_date"] != today,
        "battled_today": state["last_battle_date"] == today,
        "battle_day": today,
        "next_battle_at": pet_next_battle_at(),
        "recent_battles": state["history"][:8],
    }


def pet_choose_rarity(collection: PetCollection) -> str:
    equipment_stats, _ = pet_equipment_state(collection)
    rarity_boost = pet_active_skill_level(collection, "star_magnet") + pet_active_skill_level(collection, "collector") + equipment_stats["rarity_boost"]
    weights = [
        ("common", max(30, 60 - rarity_boost * 4)),
        ("uncommon", 25),
        ("rare", 10 + rarity_boost * 2),
        ("epic", 4 + rarity_boost),
        ("legendary", 1 + rarity_boost),
    ]
    draw = secrets.randbelow(sum(weight for _, weight in weights))
    for rarity, weight in weights:
        if draw < weight:
            return rarity
        draw -= weight
    return "common"


def queue_pet_equipment_drop(collection: PetCollection, reason: str, *, prepend: bool = False) -> dict[str, Any] | None:
    """Create one persisted three-choice drop without rolling its trigger chance."""
    pending_drops = pet_pending_drops(collection)
    if len(pending_drops) >= PET_MAX_PENDING_DROPS:
        return None
    rarity = pet_choose_rarity(collection)
    inventory = dict(collection.inventory or {})
    candidate_pool = [dict(item) for item in PET_EQUIPMENT_CATALOG.values() if item["rarity"] == rarity]
    choices: list[dict[str, Any]] = []
    for index in range(3):
        item = secrets.choice(candidate_pool)
        candidate_pool.remove(item)
        entry = pet_inventory_entry(inventory.get(item["id"], 0))
        choices.append({"item_id": item["id"], "hidden_affix": pet_random_affix(item, entry["level"] if entry["count"] else 1, index)})
    pending = {
        "token": secrets.token_hex(16),
        "reason": reason,
        "at": utcnow().isoformat(),
        "choices": choices,
    }
    inventory[PET_PENDING_DROPS_KEY] = ([pending, *pending_drops] if prepend else [*pending_drops, pending])[:PET_MAX_PENDING_DROPS]
    collection.inventory = inventory
    collection.updated_at = utcnow()
    return pending


def choose_pet_wheel_reward() -> tuple[int, dict[str, Any]]:
    draw = secrets.randbelow(sum(int(reward["weight"]) for reward in PET_WHEEL_REWARDS))
    for index, reward in enumerate(PET_WHEEL_REWARDS):
        weight = int(reward["weight"])
        if draw < weight:
            return index, reward
        draw -= weight
    return len(PET_WHEEL_REWARDS) - 1, PET_WHEEL_REWARDS[-1]


def apply_pet_wheel_reward(
    evolution: PetEvolution,
    collection: PetCollection,
    reward: dict[str, Any],
) -> tuple[str, dict[str, Any] | None]:
    """Apply one already-selected wheel reward and return its public detail."""
    kind = str(reward["kind"])
    amount = max(0, int(reward["amount"]))
    pending_drop: dict[str, Any] | None = None
    detail = str(reward["label"])
    if kind == "ticket":
        evolution.available_chances += amount
        evolution.updated_at = utcnow()
    elif kind == "route_focus":
        targeted = pet_targeted_evolution_state(collection)
        set_pet_targeted_evolution_state(collection, {**targeted, "blessings": targeted["blessings"] + amount})
    collection.updated_at = utcnow()
    return detail, pending_drop


def maybe_drop_pet_equipment(collection: PetCollection, reason: str) -> dict[str, Any] | None:
    if len(pet_pending_drops(collection)) >= PET_MAX_PENDING_DROPS:
        return None
    equipment_stats, _ = pet_equipment_state(collection)
    base_chance = PET_DROP_BASE_CHANCES.get(reason, 0)
    base_chance += pet_active_skill_level(collection, "lucky_nose") * 100
    base_chance += equipment_stats["all_drop_bonus"] * 100
    if reason == "pet":
        base_chance += pet_active_skill_level(collection, "treasure_paws") * 200
        base_chance += equipment_stats["pet_drop_bonus"] * 100
    elif reason == "annotation":
        base_chance += pet_active_skill_level(collection, "case_insight") * 200
        base_chance += equipment_stats["annotation_drop_bonus"] * 100
    elif reason == "badcase":
        base_chance += pet_active_skill_level(collection, "badcase_hunter") * 300
        base_chance += equipment_stats["badcase_drop_bonus"] * 100
    if secrets.randbelow(10_000) >= min(7500, base_chance):
        return None
    queue_pet_equipment_drop(collection, reason)
    return None


def synthesize_pet_equipment_entry(item: dict[str, Any], raw_entry: Any) -> tuple[dict[str, Any], bool, int, list[dict[str, Any]]]:
    entry = pet_inventory_entry(raw_entry)
    if entry["count"] < 3:
        raise ValueError("需要至少 3 件同名装备才能合成")
    if entry["level"] >= PET_EQUIPMENT_MAX_LEVEL:
        raise ValueError("这件装备已经达到 Lv.10")
    success_rate = pet_synthesis_success_rate(entry)
    entry["count"] -= 2
    success = secrets.randbelow(100) < success_rate
    gained_affixes: list[dict[str, Any]] = []
    if success:
        entry["level"] += 1
        entry["synthesis_failures"] = 0
        gained_affixes.append(pet_random_affix(item, entry["level"], len(entry["affixes"])))
        if len(entry["affixes"]) + len(gained_affixes) < PET_EQUIPMENT_MAX_AFFIXES and secrets.randbelow(100) < 15:
            gained_affixes.append(pet_random_affix(item, entry["level"], len(entry["affixes"]) + 1))
        entry["affixes"] = [*entry["affixes"], *gained_affixes][:PET_EQUIPMENT_MAX_AFFIXES]
    else:
        entry["synthesis_failures"] = min(20, entry["synthesis_failures"] + 1)
    return entry, success, success_rate, gained_affixes


def reforge_pet_equipment_entry(item: dict[str, Any], raw_entry: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    entry = pet_inventory_entry(raw_entry)
    if entry["count"] < 2:
        raise ValueError("洗词条需要额外消耗 1 件同名装备")
    entry["count"] -= 1
    affix_count = max(1, len(entry["affixes"]))
    if affix_count < PET_EQUIPMENT_MAX_AFFIXES and secrets.randbelow(100) < 15:
        affix_count += 1
    entry["affixes"] = [pet_random_affix(item, entry["level"], index) for index in range(affix_count)]
    return entry, entry["affixes"]


def dismantle_pet_equipment(collection: PetCollection, item_id: str) -> tuple[dict[str, Any], int]:
    item = PET_EQUIPMENT_CATALOG.get(item_id)
    if not item:
        raise ValueError("未知的装备")
    inventory = dict(collection.inventory or {})
    entry = pet_inventory_entry(inventory.get(item_id, 0))
    if entry["count"] < 1:
        raise ValueError("仓库中没有这件装备")
    if (collection.equipped or {}).get(str(item["slot"])) == item_id and entry["count"] == 1:
        raise ValueError("请先卸下这件装备再分解")
    entry["count"] -= 1
    if entry["count"]:
        inventory[item_id] = entry
    else:
        inventory.pop(item_id, None)
    parts = max(0, int(inventory.get(PET_EQUIPMENT_PARTS_KEY, 0) or 0)) + 1
    inventory[PET_EQUIPMENT_PARTS_KEY] = parts
    collection.inventory = inventory
    collection.updated_at = utcnow()
    return item, parts


def forge_random_pet_equipment(collection: PetCollection) -> tuple[dict[str, Any], bool, dict[str, Any], bool]:
    inventory = dict(collection.inventory or {})
    parts = max(0, int(inventory.get(PET_EQUIPMENT_PARTS_KEY, 0) or 0))
    if parts < 2:
        raise ValueError("随机熔铸需要 2 枚装备零件")
    rarity = pet_choose_rarity(collection)
    pool = [item for item in PET_EQUIPMENT_CATALOG.values() if item["rarity"] == rarity]
    item = dict(secrets.choice(pool))
    entry = pet_inventory_entry(inventory.get(item["id"], 0))
    entry["count"] += 1
    level_up = entry["level"] < PET_EQUIPMENT_MAX_LEVEL and secrets.randbelow(100) < 1
    if level_up:
        entry["level"] += 1
    affix = pet_random_affix(item, entry["level"], len(entry["affixes"]))
    affix_added = len(entry["affixes"]) < PET_EQUIPMENT_MAX_AFFIXES
    if affix_added:
        entry["affixes"] = [*entry["affixes"], affix]
    inventory[item["id"]] = entry
    inventory[PET_EQUIPMENT_PARTS_KEY] = parts - 2
    collection.inventory = inventory
    collection.updated_at = utcnow()
    return pet_equipment_effect(item, entry), level_up, affix, affix_added


def claim_pet_drop_choice(collection: PetCollection, token: str, item_id: str) -> tuple[dict[str, Any], dict[str, Any], bool]:
    pending_drops = pet_pending_drops(collection)
    pending = next((entry for entry in pending_drops if hmac.compare_digest(entry["token"], token)), None)
    if not pending:
        raise ValueError("这次掉落已领取或已失效")
    choice = next((entry for entry in pending["choices"] if entry["item_id"] == item_id), None)
    if not choice:
        raise ValueError("只能领取本次三选一中的装备")
    item = PET_EQUIPMENT_CATALOG[item_id]
    inventory = dict(collection.inventory or {})
    owned = pet_inventory_entry(inventory.get(item_id, 0))
    duplicate = owned["count"] > 0
    owned["count"] += 1
    identified_affix = choice["hidden_affix"]
    affix_added = len(owned["affixes"]) < PET_EQUIPMENT_MAX_AFFIXES
    if affix_added:
        owned["affixes"] = [*owned["affixes"], identified_affix]
    inventory[item_id] = owned
    remaining = [entry for entry in pending_drops if not hmac.compare_digest(entry["token"], token)]
    if remaining:
        inventory[PET_PENDING_DROPS_KEY] = remaining
    else:
        inventory.pop(PET_PENDING_DROPS_KEY, None)
    event = {
        **pet_equipment_effect(item, owned),
        "reason": pending["reason"],
        "duplicate": duplicate,
        "identified_affix": identified_affix,
        "affix_added": affix_added,
        "at": utcnow().isoformat(),
    }
    collection.inventory = inventory
    collection.drop_history = [event, *(collection.drop_history or [])][:30]
    collection.total_drops += 1
    collection.updated_at = utcnow()
    return event, identified_affix, affix_added


def awaken_pet_skill(collection: PetCollection) -> dict[str, Any]:
    skill_id = secrets.choice(tuple(PET_SKILLS))
    skills = dict(collection.skills or {})
    previous = int(skills.get(skill_id, 0))
    skills[skill_id] = min(5, previous + 1)
    collection.skills = skills
    active = list(collection.active_skills or [])
    if skill_id not in active and len(active) < 3:
        active.append(skill_id)
        collection.active_skills = active
    collection.updated_at = utcnow()
    return {"id": skill_id, **PET_SKILLS[skill_id], "level": skills[skill_id], "upgraded": previous > 0}


def grant_pet_experience(db: Session, user_id: int, reason: str, event_key: str) -> tuple[PetProfile, PetProgressV2, PetEvolution, PetCollection, bool, float, dict[str, Any] | None]:
    profile, progress, evolution, collection = get_or_create_pet(db, user_id)
    # Serialize inventory changes so simultaneous candidate submissions cannot
    # overwrite one another's equipment drops.
    collection = db.scalar(select(PetCollection).where(PetCollection.user_id == user_id).with_for_update().execution_options(populate_existing=True)) or collection
    if db.scalar(select(PetExperienceEvent.id).where(PetExperienceEvent.user_id == user_id, PetExperienceEvent.event_key == event_key)):
        return profile, progress, evolution, collection, False, 0, None
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
    drop = maybe_drop_pet_equipment(collection, reason)
    return profile, progress, evolution, collection, True, round(units / 5, 1), drop


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


def metric_case_is_agent(payload: dict[str, Any]) -> bool:
    tools = payload.get("tools")
    if isinstance(tools, list) and bool(tools):
        return True

    def has_agent_content(value: Any) -> bool:
        if isinstance(value, list):
            return any(has_agent_content(item) for item in value)
        if not isinstance(value, dict):
            return False
        block_type = str(value.get("type") or "").lower()
        if block_type in {"tool_use", "tool_result", "function_call", "function_call_output"}:
            return True
        role = str(value.get("role") or "").lower()
        if role in {"tool", "function"}:
            return True
        tool_calls = value.get("tool_calls")
        if isinstance(tool_calls, list) and bool(tool_calls):
            return True
        if value.get("tool_call_id") is not None or value.get("tool_use_id") is not None:
            return True
        return has_agent_content(value.get("content"))

    if has_agent_content(payload.get("messages")):
        return True
    candidates = payload.get("candidates")
    if isinstance(candidates, list):
        return any(
            isinstance(candidate, dict)
            and (has_agent_content(candidate.get("reasoning")) or has_agent_content(candidate.get("response")))
            for candidate in candidates
        )
    return False


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


def metric_latest_annotations(records: list[Annotation]) -> list[Annotation]:
    latest: dict[tuple[int, str], tuple[tuple[int, float, int, int], Annotation]] = {}
    for position, record in enumerate(records):
        updated_at = record.updated_at or record.created_at
        timestamp = updated_at.timestamp() if isinstance(updated_at, datetime) else 0.0
        rank = (int(record.revision or 0), timestamp, int(record.id or 0), position)
        key = (int(record.user_id), str(record.candidate_id))
        if key not in latest or rank >= latest[key][0]:
            latest[key] = (rank, record)
    return [value[1] for value in latest.values()]


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
        for record in metric_latest_annotations(case.annotations):
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


def project_metrics_payload(project: Project, cases: list[Case], dimension_key: str | None = None, case_type: str = "all") -> dict[str, Any]:
    if case_type not in {"all", "agent", "non_agent"}:
        raise HTTPException(422, "未知的 Case 类型")
    config = project_config(project)
    dimensions = project_metric_dimensions(config, cases)
    selected = next((item for item in dimensions if item["key"] == dimension_key), None) if dimension_key else dimensions[0]
    if selected is None:
        raise HTTPException(422, "未知的评分维度")
    agent_cases = [case for case in cases if metric_case_is_agent(case.payload)]
    case_type_counts = {
        "all": len(cases),
        "agent": len(agent_cases),
        "non_agent": len(cases) - len(agent_cases),
    }
    non_agent_cases = [case for case in cases if not metric_case_is_agent(case.payload)]
    scoped_cases = cases if case_type == "all" else agent_cases if case_type == "agent" else non_agent_cases
    discovered: list[str] = []
    for case in scoped_cases:
        for candidate in case.payload.get("candidates", []):
            if not isinstance(candidate, dict) or candidate.get("id") is None:
                continue
            model = str(candidate.get("model") or candidate.get("id"))
            if model not in discovered:
                discovered.append(model)
    configured = [str(value) for value in config.get("model_order", []) if str(value) in discovered]
    models = [*configured, *(model for model in discovered if model not in configured)]
    annotators: dict[int, str] = {}
    for case in scoped_cases:
        for record in metric_latest_annotations(case.annotations):
            if record.status == "submitted" and metric_number((record.scores or {}).get(str(selected["key"]))) is not None:
                annotators[record.user_id] = record.user.display_name
    scopes = [metric_scope(scoped_cases, models, str(selected["key"]), None, "总体")]
    scopes.extend(metric_scope(scoped_cases, models, str(selected["key"]), user_id, label) for user_id, label in sorted(annotators.items(), key=lambda item: item[1]))
    return {
        "dimension": {"key": str(selected["key"]), "label": str(selected.get("label") or selected["key"]), "min": selected.get("min", 1), "max": selected.get("max", 10)},
        "dimensions": [{"key": str(item["key"]), "label": str(item.get("label") or item["key"]), "min": item.get("min", 1), "max": item.get("max", 10)} for item in dimensions],
        "models": models,
        "case_type": case_type,
        "case_type_counts": case_type_counts,
        "total_case_count": len(scoped_cases),
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


def submitted_annotation_snapshot(case: Case) -> list[dict[str, Any]]:
    return sorted(({
        "annotation_id": record.id,
        "candidate_id": record.candidate_id,
        "user_id": record.user_id,
        "scores": record.scores,
        "badcase": record.badcase,
        "badcase_tags": record.badcase_tags,
        "note": record.note,
        "revision": record.revision,
        "updated_at": record.updated_at.isoformat(),
    } for record in case.annotations if record.status == "submitted"), key=lambda item: (item["candidate_id"], item["user_id"]))


def annotation_snapshot_hash(case: Case) -> str:
    return canonical_hash(submitted_annotation_snapshot(case))


def self_check_payload(record: JudgeSelfCheck | None, db: Session) -> dict[str, Any] | None:
    if not record:
        return None
    trigger = db.get(User, record.triggered_by)
    return {
        "id": record.id,
        "result": record.result,
        "raw_output": record.raw_output,
        "triggered_by": trigger.display_name if trigger else "未知用户",
        "created_at": record.created_at.isoformat(),
    }


def judge_case_content(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if key not in {"candidates", "annotations", "annotation_config"} and not key.startswith("__")
    }


def judge_candidate_content(candidate: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in candidate.items() if not key.startswith("__")}


def judge_config_signature(config: dict[str, Any]) -> str:
    return canonical_hash({key: value for key, value in config.items() if not key.startswith("_")})


def active_judge_config(db: Session, project_id: int) -> JudgeConfigVersion | None:
    return db.scalar(
        select(JudgeConfigVersion)
        .where(JudgeConfigVersion.project_id == project_id, JudgeConfigVersion.active.is_(True))
        .order_by(JudgeConfigVersion.version.desc())
    )


def judge_config_accessible(record: JudgeConfigVersion, user: User) -> bool:
    return bool(user.role == "admin" or record.active or record.created_by == user.id or record.config.get("_shared"))


def effective_judge_config(db: Session, project_id: int, user: User) -> JudgeConfigVersion | None:
    preference = db.scalar(select(JudgeConfigPreference).where(
        JudgeConfigPreference.project_id == project_id,
        JudgeConfigPreference.user_id == user.id,
    ))
    if preference:
        preferred = db.get(JudgeConfigVersion, preference.config_id)
        if preferred and preferred.project_id == project_id and judge_config_accessible(preferred, user):
            return preferred
    return active_judge_config(db, project_id)


def requested_judge_config(db: Session, project_id: int, version: int, user: User) -> JudgeConfigVersion:
    record = db.scalar(select(JudgeConfigVersion).where(
        JudgeConfigVersion.project_id == project_id,
        JudgeConfigVersion.version == version,
    ))
    if not record:
        raise HTTPException(409, "Prompt 版本不存在，请刷新后重试")
    if not judge_config_accessible(record, user):
        raise HTTPException(403, "无权使用该 Prompt 版本")
    return record


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
        "active": record.active,
        "lifecycle_status": "published" if record.active else ("archived" if record.config.get("_lifecycle_status") == "published" else record.config.get("_lifecycle_status", "archived")),
        "version_note": record.config.get("_version_note", ""),
        "parent_version": record.config.get("_parent_version"),
        "source_self_check_id": record.config.get("_source_self_check_id"),
        "shared": bool(record.config.get("_shared") or record.active),
        "created_by_id": record.created_by,
    }
    if not include_details:
        return summary
    return {
        **{key: value for key, value in record.config.items() if not key.startswith("_")},
        **summary,
    }


def judge_config_version_payload(record: JudgeConfigVersion, db: Session, default_config_id: int | None = None) -> dict[str, Any]:
    creator = db.get(User, record.created_by)
    return {
        **judge_config_payload(record, include_details=True),
        "created_by": creator.display_name if creator else "未知用户",
        "is_default": record.id == default_config_id,
    }


def migrate_legacy_judge_prompts(db: Session) -> int:
    """Version legacy compact prompts without mutating historical configurations."""
    migrated = 0
    for previous in db.scalars(select(JudgeConfigVersion).where(JudgeConfigVersion.active.is_(True))).all():
        config = dict(previous.config or {})
        replacements = {
            "decomposer_prompt": (LEGACY_DECOMPOSER_PROMPT, DEFAULT_DECOMPOSER_PROMPT),
            "detector_prompt": (LEGACY_DETECTOR_PROMPT, DEFAULT_DETECTOR_PROMPT),
            "verifier_prompt": (LEGACY_VERIFIER_PROMPT, DEFAULT_VERIFIER_PROMPT),
        }
        changed = False
        for key, (legacy, restored) in replacements.items():
            if config.get(key) == legacy:
                config[key] = restored
                changed = True
        if not changed:
            continue
        version = (db.scalar(select(func.max(JudgeConfigVersion.version)).where(JudgeConfigVersion.project_id == previous.project_id)) or 0) + 1
        previous.active = False
        db.add(JudgeConfigVersion(
            project_id=previous.project_id,
            version=version,
            config=config,
            api_key="",
            signature=judge_config_signature(config),
            active=True,
            created_by=previous.created_by,
        ))
        migrated += 1
    if migrated:
        db.commit()
    return migrated


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
    value = f"""Decompose the user's request into a fixed subtask list, using the trajectory to
tag progress. You have NOT seen the candidate reply being scored.

=== CONVERSATION CONTEXT (turns BEFORE the query — background only) ===
{sections['context']}

=== QUERY — THE LATEST USER MESSAGE (subtasks come FROM the user's needs here) ===
{sections['query']}

=== TRAJECTORY (assistant/tool turns AFTER the query — shared setup, not any model's scored reply) ===
{sections['trajectory']}

=== AVAILABLE TOOLS (capabilities only) ===
{sections['tools']}

=== REFERENCE ANSWER (if any) ===
{sections['reference_answer']}

=== END ===

Decompose tasks only from QUERY. Use CONTEXT for interpretation and TRAJECTORY only for `phase` and `current_stage`. Tools and reference answers must not create subtasks. Output exactly ONE JSON object with Chinese `full_goal`, `current_stage`, every `desc`, and `decomposition_reasoning`; each phase is exactly `done_before` or `pending`."""
    return clip_judge_text(value, token_limit)


def stage2_user_prompt(payload: dict[str, Any], candidate: dict[str, Any], stage1: dict[str, Any], token_limit: int) -> str:
    sections = judge_case_sections(payload)
    value = f"""Locate, per fixed subtask, how the model RESPONSE did. You assign status +
located findings only — no tier, no score.

=== FIXED SUBTASKS (from Stage 1 — DO NOT MODIFY, ADD, or REMOVE) ===
{text_value(stage1.get('subtasks', []))}

=== STAGE 1 NOTES (full goal & where the task stands) ===
{text_value(stage1)}

=== CONVERSATION CONTEXT (turns before the query — background) ===
{sections['context']}

=== QUERY — THE LATEST USER MESSAGE (what the subtasks came from) ===
{sections['query']}

=== TRAJECTORY (assistant/tool turns after the query — shared setup) ===
{sections['trajectory']}

=== AVAILABLE TOOLS ===
{sections['tools']}

=== REFERENCE ANSWER (if any) ===
{sections['reference_answer']}

=== MODEL RESPONSE TO EVALUATE (response) ===
{text_value({'reasoning': candidate.get('reasoning'), 'response': candidate.get('response')})}

=== END ===

Reproduce every fixed subtask with exact `id` and `desc`. Use the trajectory to determine what was due. Correct in-progress work is not an error; wrong tools, arguments, repeats, detours, or content are. Everything below "----- 以下为评测系统附加的元信息" belongs to the harness. Output exactly ONE JSON object in the documented Stage 2 structure, with Chinese narrative fields and no tier or score."""
    return clip_judge_text(value, token_limit)


def stage3_user_prompt(payload: dict[str, Any], candidate: dict[str, Any], stage1: dict[str, Any], stage2: dict[str, Any], config: dict[str, Any], token_limit: int) -> str:
    sections = judge_case_sections(payload)
    value = f"""Verify Stage 2's error localization, correct it, then decide the final tier and
score. Do the three review steps in order; do not rubber-stamp.

=== FIXED SUBTASKS (from Stage 1 — the ruler; DO NOT MODIFY/ADD/REMOVE) ===
{text_value(stage1.get('subtasks', []))}

=== STAGE 1 NOTES (full goal & where the task stands) ===
{text_value(stage1)}

=== STAGE 2 LOCALIZATION (per-subtask status + located findings to verify) ===
{text_value(stage2)}

=== CONVERSATION CONTEXT (turns before the query — background) ===
{sections['context']}

=== QUERY — THE LATEST USER MESSAGE ===
{sections['query']}

=== TRAJECTORY (assistant/tool turns after the query — shared setup) ===
{sections['trajectory']}

=== AVAILABLE TOOLS ===
{sections['tools']}

=== REFERENCE ANSWER (if any) ===
{sections['reference_answer']}

=== MODEL RESPONSE TO EVALUATE (response) ===
{text_value({'reasoning': candidate.get('reasoning'), 'response': candidate.get('response')})}

=== TIER RULES ===
{config.get('rubric')}

=== END ===

Adjudicate every Stage 2 finding, scan for missed issues, and clear false alarms in that order. Score due subtasks only; `not_due` is excluded. Everything below "----- 以下为评测系统附加的元信息" belongs to the harness. Output exactly ONE JSON object in the documented Stage 3 structure, with Chinese narrative fields, exact fixed subtasks, a legal tier, and an integer score."""
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


def stage3_final_status(sample: dict[str, Any]) -> str:
    explicit = str(sample.get("final_status", "")).strip().lower()
    if explicit in {"done", "partial", "missed"}:
        return explicit
    subtasks = sample.get("subtasks") if isinstance(sample.get("subtasks"), list) else []
    due_statuses = [
        str(item.get("status", "")).strip().lower()
        for item in subtasks
        if isinstance(item, dict) and str(item.get("status", "")).strip().lower() != "not_due"
    ]
    due_statuses = [status for status in due_statuses if status in {"done", "partial", "missed"}]
    if not due_statuses or all(status == "done" for status in due_statuses):
        return "done"
    if all(status == "missed" for status in due_statuses):
        return "missed"
    return "partial"


def aggregate_stage3(samples: list[dict[str, Any]]) -> dict[str, Any]:
    samples = [{**sample, "final_status": stage3_final_status(sample)} for sample in samples]
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
                        raw = call_judge_model(config, config_record.api_key, verifier_prompt_with_final_status(str(config["verifier_prompt"]), str(config.get("rubric", ""))), stage3_input, float(config["stage3_temperature"]), int(config["stage3_max_tokens"]))
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
                            raw = call_judge_model(config, config_record.api_key, verifier_prompt_with_final_status(str(config["verifier_prompt"]), str(config.get("rubric", ""))), stage3_input, float(config["stage3_temperature"]), int(config["stage3_max_tokens"]))
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
    config_record = effective_judge_config(db, project.id, user)
    case_query = select(Case).where(Case.project_id == project.id)
    if user.role != "admin":
        case_query = case_query.join(CaseAssignment).where(CaseAssignment.user_id == user.id)
    cases = db.scalars(case_query.order_by(Case.ordinal)).all()
    result_cases: dict[str, Any] = {}
    summary = {"not_started": 0, "queued": 0, "running": 0, "succeeded": 0, "failed": 0, "stale": 0, "cancelled": 0}
    for case in cases:
        case_hash = canonical_hash(judge_case_content(case.payload))
        case_run = None
        self_check = None
        if config_record:
            case_run = db.scalar(
                select(JudgeCaseRun)
                .where(JudgeCaseRun.case_id == case.id, JudgeCaseRun.config_id == config_record.id, JudgeCaseRun.case_hash == case_hash)
                .order_by(JudgeCaseRun.id.desc())
            )
            snapshot = submitted_annotation_snapshot(case)
            if snapshot:
                self_check = db.scalar(
                    select(JudgeSelfCheck)
                    .where(
                        JudgeSelfCheck.case_id == case.id,
                        JudgeSelfCheck.config_id == config_record.id,
                        JudgeSelfCheck.case_hash == case_hash,
                        JudgeSelfCheck.annotation_hash == canonical_hash(snapshot),
                    )
                    .order_by(JudgeSelfCheck.created_at.desc(), JudgeSelfCheck.id.desc())
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
            "self_check": self_check_payload(self_check, db),
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
        migrate_legacy_judge_prompts(db)
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
    profile, progress, evolution, collection = get_or_create_pet(db, user.id)
    db.commit()
    return pet_dict(profile, progress, evolution, collection)


@app.get("/api/pet/homestead")
def get_pet_homestead(user: CurrentUser, db: DB) -> dict[str, Any]:
    payload = pet_homestead_payload(db, user)
    db.commit()
    return payload


@app.post("/api/pet/homestead/battle")
def battle_pet_in_homestead(user: CurrentUser, db: DB) -> dict[str, Any]:
    profile, progress, evolution, collection = get_or_create_pet(db, user.id)
    db.flush()
    collection = db.scalar(
        select(PetCollection)
        .where(PetCollection.user_id == user.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ) or collection
    now = utcnow()
    today = pet_battle_day(now)
    state = pet_battle_state(collection)
    if state["last_battle_date"] == today:
        raise HTTPException(409, "今天已经出战过了，明天 00:00 后再来")
    if len(pet_pending_drops(collection)) >= PET_MAX_PENDING_DROPS:
        raise HTTPException(409, "待领取装备已达 10 组，请先完成一次装备三选一再出战")

    opponent_rows = [row for row in pet_home_rows(db) if row[0].id != user.id]
    if not opponent_rows:
        raise HTTPException(422, "家园里还没有其他宠物，等队友登录并养成宠物后再来")
    opponent_user, opponent_profile, opponent_progress, opponent_evolution, opponent_collection = secrets.choice(opponent_rows)
    my_power, _ = pet_battle_power(progress, evolution, collection)
    opponent_power, _ = pet_battle_power(opponent_progress, opponent_evolution, opponent_collection)
    outcome = "win" if my_power > opponent_power else "draw" if my_power == opponent_power else "loss"

    opponent = pet_home_resident_payload(opponent_user, opponent_profile, opponent_progress, opponent_evolution, opponent_collection)
    reward_token = ""
    lucky_loss_reward = outcome == "loss" and secrets.randbelow(100) < 10
    if outcome == "win" or lucky_loss_reward:
        reward = queue_pet_equipment_drop(collection, "battle", prepend=True)
        if not reward:
            raise HTTPException(409, "战利品暂时无法存入，请先领取已有装备")
        reward_token = reward["token"]

    battle_event = {
        "id": secrets.token_hex(8),
        "at": now.isoformat(),
        "day": today,
        "outcome": outcome,
        "my_power": my_power,
        "opponent_power": opponent_power,
        "power_delta": my_power - opponent_power,
        "reward": bool(reward_token),
        "opponent": opponent,
    }
    inventory = dict(collection.inventory or {})
    inventory[PET_BATTLE_STATE_KEY] = {
        "last_battle_date": today,
        "history": [battle_event, *state["history"]][:PET_BATTLE_HISTORY_LIMIT],
    }
    collection.inventory = inventory
    collection.updated_at = now
    db.commit()
    public_reward = next((pending for pending in pet_pending_drop_payload(collection) if pending["token"] == reward_token), None)
    return {
        "outcome": outcome,
        "won": outcome == "win",
        "lucky_reward": lucky_loss_reward,
        "my_power": my_power,
        "opponent_power": opponent_power,
        "opponent": opponent,
        "reward_pending": public_reward,
        "profile": pet_dict(profile, progress, evolution, collection),
        "home": pet_homestead_payload(db, user),
    }


@app.put("/api/pet")
def update_pet(body: PetProfileUpdate, user: CurrentUser, db: DB) -> dict[str, Any]:
    profile, progress, evolution, collection = get_or_create_pet(db, user.id)
    level = pet_level(progress.xp_units / 5)
    if body.color not in PET_COLORS:
        raise HTTPException(422, "未知的宠物颜色")
    if body.accessory not in PET_ACCESSORIES:
        raise HTTPException(422, "未知的宠物配饰")
    if PET_COLORS[body.color] > level or PET_ACCESSORIES[body.accessory] > level:
        raise HTTPException(422, "该装扮尚未解锁")
    if body.fashion is not None:
        fashion: dict[str, str] = {}
        for slot, item_id in body.fashion.items():
            item = PET_FASHION_CATALOG.get(item_id)
            if slot not in PET_FASHION_SLOTS or not item or item["slot"] != slot:
                raise HTTPException(422, "未知的宠物时装")
            if int(item["level"]) > level:
                raise HTTPException(422, "该时装尚未解锁")
            fashion[slot] = item_id
        inventory = dict(collection.inventory or {})
        inventory[PET_FASHION_KEY] = fashion
        collection.inventory = inventory
        collection.updated_at = utcnow()
    profile.name = body.name.strip()
    profile.color = body.color
    profile.accessory = body.accessory
    profile.updated_at = utcnow()
    db.commit()
    return pet_dict(profile, progress, evolution, collection)


def lock_pet_evolution_allocation(db: Session, user_id: int) -> None:
    if db.get_bind().dialect.name == "postgresql":
        db.execute(select(func.pg_advisory_xact_lock(739218041)))
    elif db.get_bind().dialect.name == "sqlite":
        db.execute(update(User).where(User.id == user_id).values(active=User.active))


@app.post("/api/pet/persona/unlock")
def unlock_pet_collab_persona(user: CurrentUser, db: DB) -> dict[str, Any]:
    lock_pet_evolution_allocation(db, user.id)
    profile, progress, evolution, collection = get_or_create_pet(db, user.id)
    collection = db.scalar(
        select(PetCollection).where(PetCollection.user_id == user.id).with_for_update().execution_options(populate_existing=True)
    ) or collection
    evolution = db.scalar(
        select(PetEvolution).where(PetEvolution.user_id == user.id).with_for_update().execution_options(populate_existing=True)
    ) or evolution
    personas = pet_personas_state(collection)
    if personas["collab"]:
        raise HTTPException(409, "联名小镜已经觉醒")
    if evolution.stage < PET_SECONDARY_UNLOCK_STAGE:
        raise HTTPException(422, f"本源小镜达到 {PET_SECONDARY_UNLOCK_STAGE} 阶后才能开启联名人格")
    if evolution.available_chances < PET_SECONDARY_UNLOCK_COST:
        raise HTTPException(422, f"开启联名人格需要 {PET_SECONDARY_UNLOCK_COST} 张进化券")
    path = choose_pet_evolution_path(db, user.id, persona=PET_PERSONA_COLLAB, pool=PET_COLLAB_PATH_LOTTERY)
    trait = secrets.choice(PET_EVOLUTION_PATHS[path]["traits"][0])
    now = utcnow().isoformat()
    collab = {
        "unlocked": True,
        "path": path,
        "stage": 1,
        "variant_seed": secrets.randbelow(8),
        "traits": [trait],
        "history": [{
            "at": now,
            "type": "persona_unlock",
            "persona": PET_PERSONA_COLLAB,
            "spent": PET_SECONDARY_UNLOCK_COST,
            "guaranteed": True,
            "success": True,
            "stage": 1,
            "path": path,
            "trait": f"联名人格觉醒 · {trait}",
            "traits": [trait],
            "critical": False,
            "success_rate": 100,
            "pity_after": 0,
        }],
        "pity": 0,
        "target": "",
        "target_failures": 0,
        "unlocked_at": now,
    }
    evolution.available_chances -= PET_SECONDARY_UNLOCK_COST
    personas = {"active": PET_PERSONA_COLLAB, "collab": collab}
    set_pet_personas_state(collection, personas)
    db.commit()
    return {
        "profile": pet_dict(profile, progress, evolution, collection),
        "persona": PET_PERSONA_COLLAB,
        "spent": PET_SECONDARY_UNLOCK_COST,
        "path": path,
        "trait": trait,
    }


@app.put("/api/pet/persona")
def switch_pet_persona(body: PetPersonaBody, user: CurrentUser, db: DB) -> dict[str, Any]:
    if body.persona not in {PET_PERSONA_ORIGIN, PET_PERSONA_COLLAB}:
        raise HTTPException(422, "未知的小镜人格")
    profile, progress, evolution, collection = get_or_create_pet(db, user.id)
    personas = pet_personas_state(collection)
    if body.persona == PET_PERSONA_COLLAB and not personas["collab"]:
        raise HTTPException(422, "请先开启联名人格")
    personas["active"] = body.persona
    set_pet_personas_state(collection, personas)
    db.commit()
    return pet_dict(profile, progress, evolution, collection)


def evolve_collab_pet(
    body: PetEvolutionBody,
    user: User,
    db: Session,
    profile: PetProfile,
    progress: PetProgressV2,
    evolution: PetEvolution,
    collection: PetCollection,
) -> dict[str, Any]:
    personas = pet_personas_state(collection)
    collab = personas["collab"]
    if not collab:
        raise HTTPException(422, "请先消耗 10 张进化券开启联名人格")
    if evolution.available_chances < body.spend:
        raise HTTPException(409, "进化券刚刚发生变化，请刷新后重试")
    target_path = str(body.target_path or "")
    targeted_attempt = body.spend == 10
    if targeted_attempt:
        if target_path not in PET_PUBLIC_COLLAB_PATHS:
            raise HTTPException(422, "联名人格只能定向选择公开联名路线")
        if target_path == collab["path"]:
            raise HTTPException(422, "目标路线不能与当前路线相同")
        if target_path in pet_owned_evolution_paths(db, (user.id, PET_PERSONA_COLLAB)):
            raise HTTPException(409, "该路线已被其他人格占用，请选择其他路线")
    guaranteed = body.spend == 5
    route_reset = guaranteed or targeted_attempt
    previous_path = collab["path"] if route_reset else ""
    previous_stage = collab["stage"] if route_reset else 0
    next_path = target_path if targeted_attempt else ""
    if not targeted_attempt and route_reset:
        next_path = choose_pet_evolution_path(
            db,
            user.id,
            {previous_path},
            persona=PET_PERSONA_COLLAB,
            pool=PET_COLLAB_PATH_LOTTERY,
        )
    evolution.available_chances -= body.spend
    hard_pity = not route_reset and int(collab["pity"]) >= PET_SECONDARY_HARD_PITY
    success_rate = pet_secondary_targeted_rate(collection, collab, target_path) if targeted_attempt else pet_secondary_evolution_success_rate(collection, collab)
    success = guaranteed or hard_pity or secrets.randbelow(100) < success_rate
    traits: list[str] = []
    critical = False
    awakened_skill: dict[str, Any] | None = None
    wheel_compensation = 0
    if success:
        if route_reset:
            collab["path"] = next_path
            collab["stage"] = 0
            collab["traits"] = []
            collab["target"] = ""
            collab["target_failures"] = 0
            if targeted_attempt:
                targeted_state = pet_targeted_evolution_state(collection)
                set_pet_targeted_evolution_state(collection, {**targeted_state, "blessings": 0})
        path = PET_EVOLUTION_PATHS[collab["path"]]
        critical = False if route_reset else secrets.randbelow(100) < 12
        stage_gain = 1 if route_reset else 2 if critical else 1
        next_traits = list(collab["traits"])
        for stage_offset in range(stage_gain):
            next_stage = collab["stage"] + stage_offset
            trait_pool = path["traits"][pet_evolution_trait_tier(collab["path"], next_stage + 1)]
            trait = secrets.choice(trait_pool)
            if next_stage + 1 > 15:
                trait = f"{trait} · 进化{next_stage + 1}阶"
            traits.append(trait)
            next_traits.append(trait)
        collab["traits"] = next_traits[-24:]
        collab["stage"] += stage_gain
        collab["variant_seed"] = secrets.randbelow(8)
        collab["pity"] = 0
        awakened_skill = awaken_pet_skill(collection)
        if route_reset and previous_stage:
            wheel_compensation = previous_stage * 2
            wheel_state = pet_wheel_state(collection)
            set_pet_wheel_state(collection, {**wheel_state, "chances": wheel_state["chances"] + wheel_compensation})
    else:
        if targeted_attempt:
            failures = collab["target_failures"] if collab["target"] == target_path else 0
            collab["target"] = target_path
            collab["target_failures"] = min(3, failures + 1)
        else:
            collab["pity"] = min(PET_SECONDARY_HARD_PITY, int(collab["pity"]) + 1)
    event_trait = f"{'定向' if targeted_attempt else ''}换路线 · {' / '.join(traits)}" if route_reset and success else " / ".join(traits)
    event = {
        "at": utcnow().isoformat(),
        **({"type": "targeted_reroute" if targeted_attempt else "reroute", "previous_path": previous_path, "route_reset": success} if route_reset else {}),
        "persona": PET_PERSONA_COLLAB,
        "spent": body.spend,
        "guaranteed": guaranteed or hard_pity,
        "hard_pity": hard_pity,
        "target_path": target_path if targeted_attempt else "",
        "success": success,
        "stage": collab["stage"],
        "path": collab["path"],
        "trait": event_trait,
        "traits": traits,
        "critical": critical,
        "success_rate": 100 if guaranteed or hard_pity else success_rate,
        "pity_after": collab["pity"],
        "wheel_compensation": wheel_compensation,
        "skill": awakened_skill,
    }
    collab["history"] = [event, *collab["history"]][:50]
    personas["collab"] = collab
    set_pet_personas_state(collection, personas)
    db.commit()
    return {
        "profile": pet_dict(profile, progress, evolution, collection),
        "success": success,
        "spent": body.spend,
        "guaranteed": guaranteed or hard_pity,
        "hard_pity": hard_pity,
        "persona": PET_PERSONA_COLLAB,
        "route_reset": route_reset and success,
        "targeted": targeted_attempt,
        "target_path": target_path if targeted_attempt else "",
        "success_rate": success_rate,
        "wheel_compensation": wheel_compensation,
        "previous_path": previous_path,
        "trait": " / ".join(traits),
        "traits": traits,
        "critical": critical,
        "skill": awakened_skill,
    }


@app.post("/api/pet/evolve")
def evolve_pet(body: PetEvolutionBody, user: CurrentUser, db: DB) -> dict[str, Any]:
    if body.spend not in {1, 5, 10}:
        raise HTTPException(422, "进化只能使用 1 张、5 张或 10 张进化券")
    # Serialize allocation before even creating a first pet. Row locks alone do
    # not cover concurrently inserted evolution rows or an initially empty pool.
    lock_pet_evolution_allocation(db, user.id)
    profile, progress, evolution, collection = get_or_create_pet(db, user.id)
    if evolution.available_chances < body.spend:
        raise HTTPException(422, "可用进化券不足")
    db.flush()
    collection = db.scalar(
        select(PetCollection)
        .where(PetCollection.user_id == user.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ) or collection
    evolution = db.scalar(
        select(PetEvolution)
        .where(PetEvolution.user_id == user.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ) or evolution
    if evolution.available_chances < body.spend:
        raise HTTPException(409, "进化券刚刚发生变化，请刷新后重试")
    requested_persona = str(body.persona or pet_personas_state(collection)["active"])
    if requested_persona not in {PET_PERSONA_ORIGIN, PET_PERSONA_COLLAB}:
        raise HTTPException(422, "未知的小镜人格")
    if requested_persona == PET_PERSONA_COLLAB:
        return evolve_collab_pet(body, user, db, profile, progress, evolution, collection)
    target_path = str(body.target_path or "")
    targeted_attempt = body.spend == 10
    if targeted_attempt:
        if evolution.stage < 1 or evolution.path not in PET_EVOLUTION_PATHS:
            raise HTTPException(422, "完成首次进化后才能定向更换路线")
        if target_path not in PET_EVOLUTION_PATHS:
            raise HTTPException(422, "请选择有效的目标路线")
        if PET_EVOLUTION_PATHS[target_path].get("hidden"):
            raise HTTPException(422, "隐藏路线只能通过随机进化发现")
        if target_path == evolution.path:
            raise HTTPException(422, "目标路线不能与当前路线相同")
        if target_path in pet_owned_evolution_paths(db, (user.id, PET_PERSONA_ORIGIN)):
            raise HTTPException(409, "该路线已被其他宠物占用，请选择其他路线")
    guaranteed = body.spend == 5
    route_reset = (guaranteed and evolution.stage > 0 and evolution.path in PET_EVOLUTION_PATHS) or targeted_attempt
    previous_path = evolution.path if route_reset else ""
    previous_stage = evolution.stage if route_reset else 0
    next_path = target_path if targeted_attempt else ""
    if not targeted_attempt and (route_reset or evolution.stage == 0 or evolution.path not in PET_EVOLUTION_PATHS):
        next_path = choose_pet_evolution_path(db, user.id, {previous_path} if route_reset else None)
    evolution.available_chances -= body.spend
    success_rate = pet_targeted_evolution_rate(collection, target_path) if targeted_attempt else pet_evolution_success_rate(collection)
    success = guaranteed or secrets.randbelow(100) < success_rate
    traits: list[str] = []
    critical = False
    awakened_skill: dict[str, Any] | None = None
    wheel_compensation = 0
    if success:
        if route_reset:
            evolution.path = next_path
            evolution.stage = 0
            evolution.traits = []
            targeted_state = pet_targeted_evolution_state(collection)
            set_pet_targeted_evolution_state(collection, {
                "target": "",
                "failures": 0,
                "blessings": 0 if targeted_attempt else targeted_state["blessings"],
            })
        elif evolution.stage == 0 or evolution.path not in PET_EVOLUTION_PATHS:
            evolution.path = next_path
        path = PET_EVOLUTION_PATHS[evolution.path]
        critical = False if route_reset else secrets.randbelow(100) < 12
        stage_gain = 1 if route_reset else 2 if critical else 1
        next_traits = list(evolution.traits or [])
        for stage_offset in range(stage_gain):
            next_stage = evolution.stage + stage_offset
            trait_pool = path["traits"][pet_evolution_trait_tier(evolution.path, next_stage + 1)]
            trait = secrets.choice(trait_pool)
            if evolution.path in PET_ILLUSTRATED_PATHS:
                if next_stage + 1 > 15:
                    trait = f"{trait} · 进化{next_stage + 1}阶"
            elif next_stage >= len(path["traits"]) * 2:
                trait = f"{trait} · 星环{next_stage - len(path['traits']) * 2 + 1}"
            traits.append(trait)
            next_traits.append(trait)
        evolution.traits = next_traits[-24:]
        evolution.stage += stage_gain
        evolution.variant_seed = secrets.randbelow(8)
        collection.pity = 0
        awakened_skill = awaken_pet_skill(collection)
        if route_reset and previous_stage:
            wheel_compensation = previous_stage * 2
            wheel_state = pet_wheel_state(collection)
            set_pet_wheel_state(collection, {**wheel_state, "chances": wheel_state["chances"] + wheel_compensation})
    else:
        if targeted_attempt:
            targeted_state = pet_targeted_evolution_state(collection)
            failures = targeted_state["failures"] if targeted_state["target"] == target_path else 0
            set_pet_targeted_evolution_state(collection, {**targeted_state, "target": target_path, "failures": failures + 1})
        else:
            collection.pity = min(20, collection.pity + 1)
        collection.updated_at = utcnow()
    event_trait = f"{'定向' if targeted_attempt else ''}换路线 · {' / '.join(traits)}" if route_reset and success else " / ".join(traits)
    event = {
        "at": utcnow().isoformat(),
        **({"type": "targeted_reroute" if targeted_attempt else "reroute", "previous_path": previous_path, "route_reset": success} if route_reset else {}),
        "spent": body.spend,
        "persona": PET_PERSONA_ORIGIN,
        "guaranteed": guaranteed,
        "target_path": target_path if targeted_attempt else "",
        "success": success,
        "stage": evolution.stage,
        "path": evolution.path,
        "trait": event_trait,
        "traits": traits,
        "critical": critical,
        "success_rate": 100 if guaranteed else success_rate,
        "pity_after": collection.pity,
        "wheel_compensation": wheel_compensation,
        "skill": awakened_skill,
    }
    evolution.history = [event, *(evolution.history or [])][:50]
    evolution.updated_at = utcnow()
    db.commit()
    return {
        "profile": pet_dict(profile, progress, evolution, collection),
        "success": success,
        "spent": body.spend,
        "guaranteed": guaranteed,
        "route_reset": route_reset and success,
        "targeted": targeted_attempt,
        "target_path": target_path if targeted_attempt else "",
        "success_rate": success_rate,
        "wheel_compensation": wheel_compensation,
        "previous_path": previous_path,
        "trait": " / ".join(traits),
        "traits": traits,
        "critical": critical,
        "skill": awakened_skill,
    }


@app.put("/api/pet/equipment")
def equip_pet_item(body: PetEquipmentBody, user: CurrentUser, db: DB) -> dict[str, Any]:
    profile, progress, evolution, collection = get_or_create_pet(db, user.id)
    if body.slot not in PET_EQUIPMENT_SLOTS:
        raise HTTPException(422, "未知的装备部位")
    equipped = dict(collection.equipped or {})
    if body.item_id:
        item = PET_EQUIPMENT_CATALOG.get(body.item_id)
        if not item or item["slot"] != body.slot:
            raise HTTPException(422, "装备与部位不匹配")
        if pet_inventory_entry((collection.inventory or {}).get(body.item_id, 0))["count"] < 1:
            raise HTTPException(422, "尚未获得这件装备")
        equipped[body.slot] = body.item_id
    else:
        equipped.pop(body.slot, None)
    collection.equipped = equipped
    collection.updated_at = utcnow()
    db.commit()
    return pet_dict(profile, progress, evolution, collection)


@app.post("/api/pet/equipment/auto")
def auto_equip_pet_items(body: PetAutoEquipBody, user: CurrentUser, db: DB) -> dict[str, Any]:
    profile, progress, evolution, collection = get_or_create_pet(db, user.id)
    try:
        equipped, before, after = pet_auto_equip(collection, body.mode)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    db.commit()
    return {"profile": pet_dict(profile, progress, evolution, collection), "mode": body.mode, "equipped": equipped, "score_before": before[0], "score_after": after[0]}


@app.post("/api/pet/wardrobe")
def manage_pet_wardrobe(body: PetWardrobeBody, user: CurrentUser, db: DB) -> dict[str, Any]:
    profile, progress, evolution, collection = get_or_create_pet(db, user.id)
    level = pet_level(progress.xp_units / 5)
    presets = pet_wardrobe_presets(collection)
    inventory = dict(collection.inventory or {})
    action = body.action.strip().lower()
    if action == "save":
        if len(presets) >= PET_MAX_WARDROBE_PRESETS:
            raise HTTPException(422, f"衣柜最多保存 {PET_MAX_WARDROBE_PRESETS} 套搭配")
        preset = {
            "id": f"look-{secrets.token_hex(6)}",
            "name": body.name.strip() or f"搭配 {len(presets) + 1}",
            "color": profile.color,
            "accessory": profile.accessory,
            "fashion": pet_fashion_state(collection, level),
            "fashion_saved": True,
            "equipped": dict(collection.equipped or {}),
            "created_at": utcnow().isoformat(),
        }
        presets = [preset, *presets]
    elif action == "apply":
        preset = next((entry for entry in presets if entry["id"] == body.preset_id), None)
        if not preset:
            raise HTTPException(404, "衣柜搭配不存在")
        if PET_COLORS.get(preset["color"], 999) <= level:
            profile.color = preset["color"]
        if PET_ACCESSORIES.get(preset["accessory"], 999) <= level:
            profile.accessory = preset["accessory"]
        if preset.get("fashion_saved"):
            inventory[PET_FASHION_KEY] = {
                slot: item_id for slot, item_id in preset["fashion"].items()
                if int(PET_FASHION_CATALOG[item_id]["level"]) <= level
            }
        collection.equipped = {
            slot: item_id for slot, item_id in preset["equipped"].items()
            if pet_inventory_entry(inventory.get(item_id, 0))["count"] > 0
        }
    elif action == "delete":
        if not any(entry["id"] == body.preset_id for entry in presets):
            raise HTTPException(404, "衣柜搭配不存在")
        presets = [entry for entry in presets if entry["id"] != body.preset_id]
    else:
        raise HTTPException(422, "未知的衣柜操作")
    inventory[PET_WARDROBE_KEY] = presets
    collection.inventory = inventory
    profile.updated_at = utcnow()
    collection.updated_at = utcnow()
    db.commit()
    return {"profile": pet_dict(profile, progress, evolution, collection), "action": action}


@app.post("/api/pet/equipment/synthesize")
def synthesize_pet_item(body: PetEquipmentActionBody, user: CurrentUser, db: DB) -> dict[str, Any]:
    profile, progress, evolution, collection = get_or_create_pet(db, user.id)
    collection = db.scalar(select(PetCollection).where(PetCollection.user_id == user.id).with_for_update().execution_options(populate_existing=True)) or collection
    item = PET_EQUIPMENT_CATALOG.get(body.item_id)
    if not item:
        raise HTTPException(422, "未知的装备")
    inventory = dict(collection.inventory or {})
    previous_entry = pet_inventory_entry(inventory.get(body.item_id, 0))
    try:
        entry, success, success_rate, gained_affixes = synthesize_pet_equipment_entry(item, inventory.get(body.item_id, 0))
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    inventory[body.item_id] = entry
    collection.inventory = inventory
    collection.updated_at = utcnow()
    db.commit()
    return {
        "profile": pet_dict(profile, progress, evolution, collection),
        "success": success,
        "success_rate": success_rate,
        "next_success_rate": pet_synthesis_success_rate(entry),
        "previous_level": previous_entry["level"],
        "next_level": entry["level"],
        "remaining_count": entry["count"],
        "gained_affixes": gained_affixes,
    }


@app.post("/api/pet/equipment/claim-drop")
def claim_pet_equipment_drop(body: PetEquipmentClaimBody, user: CurrentUser, db: DB) -> dict[str, Any]:
    profile, progress, evolution, collection = get_or_create_pet(db, user.id)
    collection = db.scalar(select(PetCollection).where(PetCollection.user_id == user.id).with_for_update().execution_options(populate_existing=True)) or collection
    try:
        drop, identified_affix, affix_added = claim_pet_drop_choice(collection, body.token, body.item_id)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    db.commit()
    return {
        "profile": pet_dict(profile, progress, evolution, collection),
        "drop": drop,
        "identified_affix": identified_affix,
        "affix_added": affix_added,
    }


@app.post("/api/pet/equipment/reforge")
def reforge_pet_item(body: PetEquipmentActionBody, user: CurrentUser, db: DB) -> dict[str, Any]:
    profile, progress, evolution, collection = get_or_create_pet(db, user.id)
    collection = db.scalar(select(PetCollection).where(PetCollection.user_id == user.id).with_for_update().execution_options(populate_existing=True)) or collection
    item = PET_EQUIPMENT_CATALOG.get(body.item_id)
    if not item:
        raise HTTPException(422, "未知的装备")
    inventory = dict(collection.inventory or {})
    try:
        entry, affixes = reforge_pet_equipment_entry(item, inventory.get(body.item_id, 0))
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    inventory[body.item_id] = entry
    collection.inventory = inventory
    collection.updated_at = utcnow()
    db.commit()
    return {"profile": pet_dict(profile, progress, evolution, collection), "affixes": affixes}


@app.post("/api/pet/equipment/dismantle")
def dismantle_pet_item(body: PetEquipmentActionBody, user: CurrentUser, db: DB) -> dict[str, Any]:
    profile, progress, evolution, collection = get_or_create_pet(db, user.id)
    collection = db.scalar(select(PetCollection).where(PetCollection.user_id == user.id).with_for_update().execution_options(populate_existing=True)) or collection
    try:
        item, parts = dismantle_pet_equipment(collection, body.item_id)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    db.commit()
    return {"profile": pet_dict(profile, progress, evolution, collection), "dismantled": item, "equipment_parts": parts}


@app.post("/api/pet/equipment/random-forge")
def random_forge_pet_item(user: CurrentUser, db: DB) -> dict[str, Any]:
    profile, progress, evolution, collection = get_or_create_pet(db, user.id)
    collection = db.scalar(select(PetCollection).where(PetCollection.user_id == user.id).with_for_update().execution_options(populate_existing=True)) or collection
    try:
        item, level_up, affix, affix_added = forge_random_pet_equipment(collection)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    db.commit()
    return {
        "profile": pet_dict(profile, progress, evolution, collection),
        "item": item,
        "level_up": level_up,
        "identified_affix": affix,
        "affix_added": affix_added,
    }


@app.put("/api/pet/skills")
def set_pet_skills(body: PetSkillsBody, user: CurrentUser, db: DB) -> dict[str, Any]:
    profile, progress, evolution, collection = get_or_create_pet(db, user.id)
    active = list(dict.fromkeys(body.active_skill_ids))
    if len(active) > 3 or any(skill_id not in PET_SKILLS or int((collection.skills or {}).get(skill_id, 0)) < 1 for skill_id in active):
        raise HTTPException(422, "只能启用最多 3 个已觉醒技能")
    collection.active_skills = active
    collection.updated_at = utcnow()
    db.commit()
    return pet_dict(profile, progress, evolution, collection)


@app.post("/api/pet/wheel/spin")
def spin_pet_wheel(user: CurrentUser, db: DB) -> dict[str, Any]:
    profile, progress, evolution, collection = get_or_create_pet(db, user.id)
    db.flush()
    collection = db.scalar(
        select(PetCollection).where(PetCollection.user_id == user.id).with_for_update().execution_options(populate_existing=True)
    ) or collection
    progress = db.scalar(
        select(PetProgressV2).where(PetProgressV2.user_id == user.id).with_for_update().execution_options(populate_existing=True)
    ) or progress
    evolution = db.scalar(
        select(PetEvolution).where(PetEvolution.user_id == user.id).with_for_update().execution_options(populate_existing=True)
    ) or evolution
    state = pet_wheel_state(collection)
    if state["chances"] < 1:
        raise HTTPException(409, "大转盘抽奖次数不足，请联系管理员发放")

    reward_index, reward = choose_pet_wheel_reward()
    detail, pending_drop = apply_pet_wheel_reward(evolution, collection, reward)
    now = utcnow()
    event = {
        "id": secrets.token_hex(8),
        "reward_id": reward["id"],
        "label": reward["label"],
        "short_label": reward["short_label"],
        "icon": reward["icon"],
        "tone": reward["tone"],
        "detail": detail,
        "at": now.isoformat(),
    }
    set_pet_wheel_state(collection, {
        "chances": state["chances"] - 1,
        "history": [event, *state["history"]],
    })
    db.commit()
    public_pending = None
    if pending_drop:
        public_pending = next(
            (entry for entry in pet_pending_drop_payload(collection) if entry["token"] == pending_drop["token"]),
            None,
        )
    return {
        "profile": pet_dict(profile, progress, evolution, collection),
        "reward": event,
        "reward_index": reward_index,
        "pending_drop": public_pending,
    }


@app.post("/api/pet/admin/gift-wheel")
def gift_pet_wheel_chances(body: PetWheelGrantBody, admin: AdminUser, db: DB) -> dict[str, Any]:
    recipient_ids = list(dict.fromkeys([*body.recipient_user_ids, *([body.recipient_user_id] if body.recipient_user_id else [])]))
    if not recipient_ids:
        raise HTTPException(422, "请至少选择一位接收人")
    recipients = [db.get(User, recipient_id) for recipient_id in recipient_ids]
    if any(recipient is None or not recipient.active for recipient in recipients):
        raise HTTPException(404, "部分接收人不存在或已停用")
    profiles: dict[int, dict[str, Any]] = {}
    for recipient in recipients:
        assert recipient is not None
        profile, progress, evolution, collection = get_or_create_pet(db, recipient.id)
        db.flush()
        collection = db.scalar(
            select(PetCollection).where(PetCollection.user_id == recipient.id).with_for_update().execution_options(populate_existing=True)
        ) or collection
        state = pet_wheel_state(collection)
        set_pet_wheel_state(collection, {**state, "chances": state["chances"] + body.amount})
        db.add(PetWheelGrant(
            sender_user_id=admin.id,
            recipient_user_id=recipient.id,
            amount=body.amount,
            note=body.note.strip(),
        ))
        profiles[recipient.id] = pet_dict(profile, progress, evolution, collection)
    db.commit()
    recipient_payloads = [user_dict(recipient) for recipient in recipients if recipient is not None]
    return {
        "recipient": recipient_payloads[0],
        "recipients": recipient_payloads,
        "amount": body.amount,
        "total_amount": body.amount * len(recipient_payloads),
        "profile": profiles.get(admin.id),
    }


@app.post("/api/pet/admin/gift-tickets")
def gift_pet_tickets(body: PetTicketGiftBody, admin: AdminUser, db: DB) -> dict[str, Any]:
    recipient_ids = list(dict.fromkeys([*body.recipient_user_ids, *([body.recipient_user_id] if body.recipient_user_id else [])]))
    if not recipient_ids:
        raise HTTPException(422, "请至少选择一位接收人")
    recipients = [db.get(User, recipient_id) for recipient_id in recipient_ids]
    if any(recipient is None or not recipient.active for recipient in recipients):
        raise HTTPException(404, "部分接收人不存在或已停用")
    now = utcnow()
    first_profile: dict[str, Any] | None = None
    for recipient in recipients:
        assert recipient is not None
        profile, progress, evolution, collection = get_or_create_pet(db, recipient.id)
        db.flush()
        evolution = db.scalar(select(PetEvolution).where(PetEvolution.user_id == recipient.id).with_for_update().execution_options(populate_existing=True)) or evolution
        evolution.available_chances += body.amount
        evolution.history = [{"at": now.isoformat(), "type": "gift", "success": True, "spent": 0, "stage": evolution.stage, "path": evolution.path, "trait": f"管理员赠送 {body.amount} 张进化券", "amount": body.amount, "sender": admin.display_name}, *(evolution.history or [])][:50]
        evolution.updated_at = now
        db.add(PetTicketGift(sender_user_id=admin.id, recipient_user_id=recipient.id, amount=body.amount, note=body.note.strip()))
        if first_profile is None:
            first_profile = pet_dict(profile, progress, evolution, collection)
    db.commit()
    recipient_payloads = [user_dict(recipient) for recipient in recipients if recipient is not None]
    return {
        "recipient": recipient_payloads[0],
        "recipients": recipient_payloads,
        "amount": body.amount,
        "total_amount": body.amount * len(recipient_payloads),
        "profile": first_profile,
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
        profile, progress, evolution, collection = get_or_create_pet(db, user.id)
        db.commit()
        return {"profile": pet_dict(profile, progress, evolution, collection), "awarded": False, "amount": 0, "hourly_earned": 2, "hourly_remaining": 0, "drop": None}
    profile, progress, evolution, collection, awarded, amount, drop = grant_pet_experience(db, user.id, "pet", f"pet:{hour_key}:{hourly_count + 1}")
    db.commit()
    earned_count = hourly_count + (1 if awarded else 0)
    return {"profile": pet_dict(profile, progress, evolution, collection), "awarded": awarded, "amount": amount, "hourly_earned": round(earned_count / 5, 1), "hourly_remaining": max(0, 10 - earned_count), "drop": drop}


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
    db.execute(delete(JudgeSelfCheck).where(JudgeSelfCheck.project_id == project_id))
    db.execute(delete(JudgeCandidateRun).where(JudgeCandidateRun.case_run_id.in_(judge_case_run_ids)))
    db.execute(delete(JudgeCaseRun).where(JudgeCaseRun.project_id == project_id))
    db.execute(delete(JudgeConfigPreference).where(JudgeConfigPreference.project_id == project_id))
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
    return judge_config_payload(effective_judge_config(db, project_id, user), include_details=True)


@app.get("/api/projects/{project_id}/judge/config/versions")
def get_judge_config_versions(project_id: int, user: CurrentUser, db: DB) -> dict[str, Any]:
    ensure_project_access(project_id, user, db)
    all_records = db.scalars(
        select(JudgeConfigVersion)
        .where(JudgeConfigVersion.project_id == project_id)
        .order_by(JudgeConfigVersion.version.desc())
    ).all()
    records = [record for record in all_records if judge_config_accessible(record, user)]
    effective = effective_judge_config(db, project_id, user)
    active = next((record.version for record in all_records if record.active), 0)
    return {
        "active_version": active,
        "default_version": effective.version if effective else 0,
        "versions": [judge_config_version_payload(record, db, effective.id if effective else None) for record in records],
    }


@app.put("/api/projects/{project_id}/judge/config")
def save_judge_config(project_id: int, body: JudgeConfigBody, user: CurrentUser, db: DB) -> dict[str, Any]:
    ensure_project_access(project_id, user, db)
    if body.lifecycle_status == "published" and user.role != "admin":
        raise HTTPException(403, "只有管理员可以发布项目生产版本")
    protocol = body.protocol.strip().lower()
    if protocol not in {"anthropic", "openai"}:
        raise HTTPException(422, "协议只能是 anthropic 或 openai")
    endpoint = urlsplit(body.base_url.strip().rstrip("/；; "))
    if endpoint.scheme not in {"http", "https"} or not endpoint.netloc:
        raise HTTPException(422, "Base URL 必须是完整的 HTTP(S) 地址")
    previous = active_judge_config(db, project_id)
    parent = db.scalar(select(JudgeConfigVersion).where(JudgeConfigVersion.project_id == project_id, JudgeConfigVersion.version == body.parent_version)) if body.parent_version is not None else effective_judge_config(db, project_id, user)
    if body.parent_version is not None and not parent:
        raise HTTPException(422, "父版本不存在")
    if parent and not judge_config_accessible(parent, user):
        raise HTTPException(403, "无权基于该私有 Prompt 版本创建分支")
    if body.source_self_check_id is not None and not db.scalar(select(JudgeSelfCheck.id).where(JudgeSelfCheck.project_id == project_id, JudgeSelfCheck.id == body.source_self_check_id)):
        raise HTTPException(422, "来源自检记录不存在")
    config = body.model_dump(exclude={"api_key", "lifecycle_status", "version_note", "parent_version", "source_self_check_id", "shared"})
    if user.role != "admin":
        if not parent:
            raise HTTPException(422, "管理员需先创建项目生产 Prompt，标注员才能创建个人版本")
        inherited = {key: value for key, value in parent.config.items() if not key.startswith("_")}
        config = {
            **inherited,
            "rubric": body.rubric,
            "decomposer_prompt": body.decomposer_prompt,
            "detector_prompt": body.detector_prompt,
            "verifier_prompt": body.verifier_prompt,
        }
    config["protocol"] = protocol if user.role == "admin" else parent.config.get("protocol", "anthropic")
    config["base_url"] = JUDGE_LOCAL_RELAY_BASE
    config["_lifecycle_status"] = body.lifecycle_status
    config["_version_note"] = body.version_note.strip()
    config["_parent_version"] = body.parent_version
    config["_source_self_check_id"] = body.source_self_check_id
    publish = body.lifecycle_status == "published"
    config["_shared"] = bool(body.shared or publish)
    version = (db.scalar(select(func.max(JudgeConfigVersion.version)).where(JudgeConfigVersion.project_id == project_id)) or 0) + 1
    if previous and publish:
        previous.active = False
    record = JudgeConfigVersion(
        project_id=project_id,
        version=version,
        config=config,
        # Each user supplies their own page-memory-only key to the local relay.
        api_key="",
        signature=judge_config_signature(config),
        active=publish,
        created_by=user.id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return judge_config_version_payload(record, db)


@app.put("/api/projects/{project_id}/judge/config/default")
def set_judge_config_default(project_id: int, body: JudgeConfigDefaultBody, user: CurrentUser, db: DB) -> dict[str, Any]:
    ensure_project_access(project_id, user, db)
    preference = db.scalar(select(JudgeConfigPreference).where(
        JudgeConfigPreference.project_id == project_id,
        JudgeConfigPreference.user_id == user.id,
    ))
    if body.version == 0:
        if preference:
            db.delete(preference)
        db.commit()
        effective = active_judge_config(db, project_id)
        return {"ok": True, "default_version": effective.version if effective else 0}
    record = db.scalar(select(JudgeConfigVersion).where(JudgeConfigVersion.project_id == project_id, JudgeConfigVersion.version == body.version))
    if not record:
        raise HTTPException(404, "Prompt 版本不存在")
    if not judge_config_accessible(record, user):
        raise HTTPException(403, "该 Prompt 尚未推送给团队")
    if preference:
        preference.config_id = record.id
    else:
        db.add(JudgeConfigPreference(project_id=project_id, user_id=user.id, config_id=record.id))
    db.commit()
    return {"ok": True, "default_version": record.version}


@app.post("/api/projects/{project_id}/judge/config/versions/{version}/share")
def share_judge_config_version(project_id: int, version: int, user: CurrentUser, db: DB) -> dict[str, Any]:
    ensure_project_access(project_id, user, db)
    record = db.scalar(select(JudgeConfigVersion).where(JudgeConfigVersion.project_id == project_id, JudgeConfigVersion.version == version))
    if not record:
        raise HTTPException(404, "Prompt 版本不存在")
    if user.role != "admin" and record.created_by != user.id:
        raise HTTPException(403, "只能推送自己创建的 Prompt 版本")
    record.config = {**record.config, "_shared": True}
    db.commit()
    db.refresh(record)
    return judge_config_version_payload(record, db)


@app.post("/api/projects/{project_id}/judge/config/versions/{version}/publish")
def publish_judge_config_version(project_id: int, version: int, admin: AdminUser, db: DB) -> dict[str, Any]:
    if not db.get(Project, project_id):
        raise HTTPException(404, "项目不存在")
    record = db.scalar(select(JudgeConfigVersion).where(JudgeConfigVersion.project_id == project_id, JudgeConfigVersion.version == version))
    if not record:
        raise HTTPException(404, "Prompt 版本不存在")
    previous = active_judge_config(db, project_id)
    if previous and previous.id != record.id:
        previous.active = False
        previous.config = {**previous.config, "_lifecycle_status": "published"}
    record.active = True
    record.config = {**record.config, "_lifecycle_status": "published", "_shared": True}
    db.commit()
    db.refresh(record)
    return judge_config_version_payload(record, db)


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
    config_record = requested_judge_config(db, project_id, body.config_version, user)
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


@app.post("/api/projects/{project_id}/judge/self-check")
def save_judge_self_check(project_id: int, body: JudgeSelfCheckBody, user: CurrentUser, db: DB) -> dict[str, Any]:
    ensure_project_access(project_id, user, db)
    config_record = requested_judge_config(db, project_id, body.config_version, user)
    case = db.get(Case, body.case_id)
    if not case or case.project_id != project_id:
        raise HTTPException(404, "Case 不存在")
    if user.role != "admin" and not db.scalar(select(CaseAssignment).where(CaseAssignment.case_id == case.id, CaseAssignment.user_id == user.id)):
        raise HTTPException(403, "无权提交该 Case 的评分自检")
    snapshot = submitted_annotation_snapshot(case)
    if not snapshot:
        raise HTTPException(422, "该 Case 还没有已提交的历史人工评分")
    case_hash = canonical_hash(judge_case_content(case.payload))
    case_run = db.scalar(select(JudgeCaseRun).where(
        JudgeCaseRun.case_id == case.id,
        JudgeCaseRun.config_id == config_record.id,
        JudgeCaseRun.case_hash == case_hash,
    ))
    if not case_run:
        raise HTTPException(422, "请先生成当前配置下的自动判分")
    completed_stage3 = db.scalar(select(func.count(JudgeCandidateRun.id)).where(
        JudgeCandidateRun.case_run_id == case_run.id,
        JudgeCandidateRun.status == "succeeded",
    )) or 0
    if not completed_stage3:
        raise HTTPException(422, "至少需要一个候选模型完成 Stage 3 后才能自检")
    result = require_judge_object(parse_json_object(body.raw_output), "评分自检")
    if not isinstance(result.get("prompt_optimization"), dict):
        raise HTTPException(422, "评分自检输出缺少 prompt_optimization")
    record = JudgeSelfCheck(
        project_id=project_id,
        case_id=case.id,
        config_id=config_record.id,
        case_hash=case_hash,
        annotation_hash=canonical_hash(snapshot),
        result=result,
        raw_output=body.raw_output,
        triggered_by=user.id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return {"ok": True, "self_check": self_check_payload(record, db)}


@app.post("/api/projects/{project_id}/judge/cancel")
def cancel_project_judge(project_id: int, body: JudgeRunBody, user: CurrentUser, db: DB) -> dict[str, Any]:
    ensure_project_access(project_id, user, db)
    config_record = effective_judge_config(db, project_id, user)
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
def project_metrics(
    project_id: int,
    user: CurrentUser,
    db: DB,
    dimension: str | None = Query(default=None, max_length=200),
    case_type: str = Query(default="all", pattern="^(all|agent|non_agent)$"),
) -> dict[str, Any]:
    project = ensure_project_access(project_id, user, db)
    cases = db.scalars(
        select(Case)
        .where(Case.project_id == project_id)
        .options(selectinload(Case.annotations).selectinload(Annotation.user))
        .order_by(Case.ordinal)
    ).all()
    return project_metrics_payload(project, cases, dimension, case_type)


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
