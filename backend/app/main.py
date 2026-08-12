from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Annotated

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine, delete, func, select
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker


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


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=240)
    annotation_config: dict[str, Any] = Field(default_factory=dict)


class AnnotationBody(BaseModel):
    scores: dict[str, int] = Field(default_factory=dict)
    badcase: bool = False
    badcase_tags: list[str] = Field(default_factory=list)
    note: str = ""
    status: str = "draft"
    revision: int | None = None


def user_dict(user: User) -> dict[str, Any]:
    return {"id": str(user.id), "username": user.username, "display_name": user.display_name, "role": user.role}


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


@app.get("/api/projects")
def list_projects(user: CurrentUser, db: DB) -> list[dict[str, Any]]:
    projects = db.scalars(select(Project).order_by(Project.created_at.desc())).all()
    result = []
    for project in projects:
        total = db.scalar(select(func.count(Case.id)).where(Case.project_id == project.id)) or 0
        submitted = db.scalar(select(func.count(func.distinct(Annotation.case_id))).join(Case).where(Case.project_id == project.id, Annotation.user_id == user.id, Annotation.status == "submitted")) or 0
        result.append({"id": project.id, "name": project.name, "annotation_config": project.annotation_config, "case_count": total, "my_submitted_count": submitted, "created_at": project.created_at.isoformat()})
    return result


@app.post("/api/projects")
def create_project(body: ProjectCreate, user: AdminUser, db: DB) -> dict[str, Any]:
    project = Project(name=body.name, annotation_config=body.annotation_config, created_by=user.id)
    db.add(project)
    db.commit()
    return {"id": project.id, "name": project.name, "annotation_config": project.annotation_config}


@app.post("/api/projects/{project_id}/upload")
def upload_jsonl(project_id: int, _: AdminUser, db: DB, file: UploadFile = File(...), replace: bool = Form(False)) -> dict[str, Any]:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    safe_name = f"{project_id}-{utcnow().strftime('%Y%m%d%H%M%S')}-{Path(file.filename or 'dataset.jsonl').name}"
    destination = DATA_DIR / "uploads" / safe_name
    with destination.open("wb") as target:
        shutil.copyfileobj(file.file, target)
    if destination.stat().st_size > MAX_UPLOAD_MB * 1024 * 1024:
        destination.unlink(missing_ok=True)
        raise HTTPException(413, f"文件超过 {MAX_UPLOAD_MB}MB 限制")
    if replace:
        case_ids = select(Case.id).where(Case.project_id == project_id)
        db.execute(delete(Annotation).where(Annotation.case_id.in_(case_ids)))
        db.execute(delete(Case).where(Case.project_id == project_id))
        db.commit()
    inserted = 0
    errors: list[str] = []
    seen: set[str] = set()
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
                candidate_ids = [str(item.get("id")) for item in candidates if isinstance(item, dict)]
                if len(candidate_ids) != len(set(candidate_ids)):
                    raise ValueError("candidate id 重复")
                if "annotation_config" not in payload and project.annotation_config:
                    payload["annotation_config"] = project.annotation_config
                payload.pop("annotations", None)
                db.add(Case(project_id=project_id, external_id=external_id, ordinal=line_number, payload=payload))
                inserted += 1
                if inserted % 500 == 0:
                    db.commit()
            except Exception as exc:
                errors.append(f"第 {line_number} 行：{exc}")
                if len(errors) >= 100:
                    break
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(409, f"写入失败，可能存在重复 Case ID：{exc}") from exc
    return {"inserted": inserted, "errors": errors, "source_file": safe_name}


@app.get("/api/projects/{project_id}/cases")
def project_cases(project_id: int, _: CurrentUser, db: DB, offset: int = 0, limit: int = 1000) -> dict[str, Any]:
    limit = min(max(limit, 1), 10_000)
    total = db.scalar(select(func.count(Case.id)).where(Case.project_id == project_id)) or 0
    cases = db.scalars(select(Case).where(Case.project_id == project_id).order_by(Case.ordinal).offset(offset).limit(limit)).all()
    items = []
    for case in cases:
        payload = dict(case.payload)
        payload["__server_case_id"] = case.id
        payload["annotations"] = [annotation_dict(record) for record in case.annotations]
        items.append(payload)
    return {"items": items, "total": total, "offset": offset, "limit": limit}


@app.put("/api/cases/{case_id}/annotations/{candidate_id}")
def save_annotation(case_id: int, candidate_id: str, body: AnnotationBody, user: CurrentUser, db: DB) -> dict[str, Any]:
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(404, "Case 不存在")
    candidate_ids = {str(item.get("id")) for item in case.payload.get("candidates", []) if isinstance(item, dict)}
    if candidate_id not in candidate_ids:
        raise HTTPException(404, "候选模型不存在")
    validate_annotation(case, body)
    record = db.scalar(select(Annotation).where(Annotation.case_id == case_id, Annotation.candidate_id == candidate_id, Annotation.user_id == user.id))
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
    db.commit()
    db.refresh(record)
    return annotation_dict(record)


@app.get("/api/projects/{project_id}/progress")
def progress(project_id: int, user: CurrentUser, db: DB) -> dict[str, Any]:
    total = db.scalar(select(func.count(Case.id)).where(Case.project_id == project_id)) or 0
    mine = db.scalars(select(Annotation).join(Case).where(Case.project_id == project_id, Annotation.user_id == user.id)).all()
    submitted_cases = len({item.case_id for item in mine if item.status == "submitted"})
    draft_cases = len({item.case_id for item in mine if item.status == "draft"})
    badcases = db.scalar(select(func.count(func.distinct(Annotation.case_id))).join(Case).where(Case.project_id == project_id, Annotation.badcase.is_(True))) or 0
    return {"total_cases": total, "my_submitted_cases": submitted_cases, "my_draft_cases": draft_cases, "badcase_count": badcases}


@app.get("/api/projects/{project_id}/export")
def export_project(project_id: int, _: AdminUser, db: DB):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")

    def generate():
        for case in db.scalars(select(Case).where(Case.project_id == project_id).order_by(Case.ordinal)).all():
            payload = dict(case.payload)
            payload["schema_version"] = payload.get("schema_version", "case-lens.annotation.v1")
            payload["annotations"] = [annotation_dict(record) for record in case.annotations]
            yield json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"

    filename = f"project-{project_id}-annotated.jsonl"
    return StreamingResponse(generate(), media_type="application/x-ndjson", headers={"Content-Disposition": f'attachment; filename="{filename}"'})
