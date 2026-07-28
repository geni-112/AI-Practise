from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from threading import Lock
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    select,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


APP_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SQLITE_PATH = APP_ROOT / "runtime" / "sat-control.db"
SECRET_KEY_PATTERN = re.compile(
    r"(access[_-]?key|secret[_-]?key|password|passwd|private[_-]?key|security[_-]?token|authorization)",
    re.IGNORECASE,
)
TERMINAL_EXECUTION_STATES = frozenset({"succeeded", "failed", "cancelled"})
ACTIVE_EXECUTION_STATES = frozenset(
    {"execution_requested", "queued", "running", "cancel_requested"}
)


class Base(DeclarativeBase):
    pass


class ArtifactApprovalRecord(Base):
    __tablename__ = "sat_artifact_approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(96), index=True)
    artifact_name: Mapped[str] = mapped_column(String(255))
    artifact_hash: Mapped[str] = mapped_column(String(64))
    decision: Mapped[str] = mapped_column(String(24))
    actor: Mapped[str] = mapped_column(String(255))
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ReleaseRecord(Base):
    __tablename__ = "sat_releases"
    __table_args__ = (UniqueConstraint("run_id", "release_hash"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(96), index=True)
    release_hash: Mapped[str] = mapped_column(String(64), index=True)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON)
    released_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ExecutionRequestRecord(Base):
    __tablename__ = "sat_execution_requests"
    __table_args__ = (UniqueConstraint("idempotency_key"),)

    request_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(96), index=True)
    release_hash: Mapped[str] = mapped_column(String(64), index=True)
    target: Mapped[str] = mapped_column(String(32))
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON)
    idempotency_key: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(32), index=True)
    requested_by: Mapped[str] = mapped_column(String(255))
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cloud_job_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error_message: Mapped[str] = mapped_column(Text, default="")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ExecutionEventRecord(Base):
    __tablename__ = "sat_execution_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sat_execution_requests.request_id"),
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(64))
    actor: Mapped[str] = mapped_column(String(255))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def database_url() -> str:
    configured = os.getenv("SAT_DATABASE_URL", "").strip()
    if configured:
        return configured
    DEFAULT_SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{DEFAULT_SQLITE_PATH.as_posix()}"


def canonical_release_hash(manifest: dict[str, Any]) -> str:
    artifact_hashes = manifest.get("artifact_hashes", {})
    files = [
        {"name": item.get("name", ""), "sha256": item.get("sha256", "")}
        for item in manifest.get("files", [])
        if item.get("name") != "release_manifest.json"
    ]
    payload = {
        "schema": "sat.release.v1",
        "run_id": manifest.get("run_id", ""),
        "approved_artifacts": sorted(manifest.get("approved_artifacts", [])),
        "artifact_hashes": {
            name: artifact_hashes[name]
            for name in sorted(artifact_hashes)
        },
        "files": sorted(files, key=lambda item: item["name"]),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def ensure_safe_parameters(value: Any, path: str = "parameters") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if SECRET_KEY_PATTERN.search(str(key)):
                raise ValueError(f"Secret-like execution parameter is forbidden: {path}.{key}")
            ensure_safe_parameters(nested, f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, nested in enumerate(value):
            ensure_safe_parameters(nested, f"{path}[{index}]")
        return
    if isinstance(value, str) and "-----BEGIN " in value and "PRIVATE KEY-----" in value:
        raise ValueError(f"Private key material is forbidden: {path}")


def allowed_execution_targets() -> frozenset[str]:
    value = os.getenv("SAT_ALLOWED_EXECUTION_TARGETS", "mrs,dataarts")
    return frozenset(item.strip() for item in value.split(",") if item.strip())


def execution_profiles() -> list[dict[str, Any]]:
    raw = os.getenv("SAT_EXECUTION_PROFILES_JSON", "[]").strip() or "[]"
    try:
        profiles = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("SAT_EXECUTION_PROFILES_JSON is not valid JSON.") from exc
    if not isinstance(profiles, list):
        raise ValueError("SAT_EXECUTION_PROFILES_JSON must be a JSON array.")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in profiles:
        if not isinstance(item, dict):
            raise ValueError("Each execution profile must be a JSON object.")
        profile_id = str(item.get("id", "")).strip()
        target = str(item.get("target", "")).strip()
        parameters = item.get("parameters", {})
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{1,63}", profile_id):
            raise ValueError("Execution profile id is invalid.")
        if profile_id in seen:
            raise ValueError(f"Duplicate execution profile id: {profile_id}")
        if target not in allowed_execution_targets():
            raise ValueError(f"Execution profile target is not allowlisted: {target}")
        if not isinstance(parameters, dict):
            raise ValueError("Execution profile parameters must be an object.")
        ensure_safe_parameters(parameters)
        seen.add(profile_id)
        result.append(
            {
                "id": profile_id,
                "label": str(item.get("label") or profile_id),
                "description": str(item.get("description") or ""),
                "target": target,
                "parameters": parameters,
            }
        )
    return result


def public_execution_profiles() -> list[dict[str, str]]:
    return [
        {
            "id": item["id"],
            "label": item["label"],
            "description": item["description"],
            "target": item["target"],
        }
        for item in execution_profiles()
    ]


def resolve_execution_profile(profile_id: str) -> dict[str, Any]:
    for profile in execution_profiles():
        if profile["id"] == profile_id:
            return profile
    raise ValueError(f"Execution profile not found: {profile_id}")


class ProductionControlStore:
    def __init__(self, url: str | None = None) -> None:
        self.url = url or database_url()
        connect_args = {"check_same_thread": False} if self.url.startswith("sqlite") else {}
        self.engine = create_engine(
            self.url,
            future=True,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        Base.metadata.create_all(self.engine)

    def record_artifact_approval(
        self,
        *,
        run_id: str,
        artifact_name: str,
        artifact_hash: str,
        decision: str,
        actor: str,
        note: str,
    ) -> dict[str, Any]:
        record = ArtifactApprovalRecord(
            run_id=run_id,
            artifact_name=artifact_name,
            artifact_hash=artifact_hash,
            decision=decision,
            actor=actor,
            note=note,
            created_at=now_utc(),
        )
        with Session(self.engine) as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            return self._approval_dict(record)

    def record_release(
        self,
        *,
        run_id: str,
        manifest: dict[str, Any],
        actor: str,
    ) -> dict[str, Any]:
        calculated_hash = canonical_release_hash(manifest)
        supplied_hash = str(manifest.get("release_hash") or "")
        if supplied_hash and supplied_hash != calculated_hash:
            raise ValueError("Release manifest hash does not match its canonical contents.")
        release_hash = supplied_hash or calculated_hash
        artifact_hashes = manifest.get("artifact_hashes")
        if not isinstance(artifact_hashes, dict) or not artifact_hashes:
            raise ValueError("Release manifest must contain approved artifact hashes.")
        with Session(self.engine) as session:
            mismatches: list[str] = []
            for artifact_name, artifact_hash in artifact_hashes.items():
                approval = session.scalar(
                    select(ArtifactApprovalRecord)
                    .where(
                        ArtifactApprovalRecord.run_id == run_id,
                        ArtifactApprovalRecord.artifact_name == str(artifact_name),
                    )
                    .order_by(ArtifactApprovalRecord.id.desc())
                    .limit(1)
                )
                if (
                    approval is None
                    or approval.decision != "approved"
                    or approval.artifact_hash != str(artifact_hash)
                ):
                    mismatches.append(str(artifact_name))
            if mismatches:
                raise ValueError(
                    "Release artifacts do not match the latest persisted approvals: "
                    + ", ".join(sorted(mismatches))
                )
            existing = session.scalar(
                select(ReleaseRecord).where(
                    ReleaseRecord.run_id == run_id,
                    ReleaseRecord.release_hash == release_hash,
                )
            )
            if existing:
                return self._release_dict(existing)
            record = ReleaseRecord(
                run_id=run_id,
                release_hash=release_hash,
                manifest=manifest,
                released_by=actor,
                created_at=now_utc(),
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return self._release_dict(record)

    def latest_release(self, run_id: str) -> dict[str, Any] | None:
        with Session(self.engine) as session:
            record = session.scalar(
                select(ReleaseRecord)
                .where(ReleaseRecord.run_id == run_id)
                .order_by(ReleaseRecord.id.desc())
                .limit(1)
            )
            return self._release_dict(record) if record else None

    def create_execution_request(
        self,
        *,
        run_id: str,
        release_hash: str,
        target: str,
        parameters: dict[str, Any],
        idempotency_key: str,
        actor: str,
    ) -> dict[str, Any]:
        if target not in allowed_execution_targets():
            raise ValueError(f"Execution target is not allowlisted: {target}")
        ensure_safe_parameters(parameters)
        created_at = now_utc()
        record = ExecutionRequestRecord(
            request_id=str(uuid.uuid4()),
            run_id=run_id,
            release_hash=release_hash,
            target=target,
            parameters=parameters,
            idempotency_key=idempotency_key,
            status="execution_requested",
            requested_by=actor,
            approved_by=None,
            cloud_job_id=None,
            evidence={},
            error_message="",
            requested_at=created_at,
            approved_at=None,
            started_at=None,
            finished_at=None,
            updated_at=created_at,
        )
        with Session(self.engine) as session:
            session.add(record)
            try:
                session.flush()
            except IntegrityError:
                session.rollback()
                existing = session.scalar(
                    select(ExecutionRequestRecord).where(
                        ExecutionRequestRecord.idempotency_key == idempotency_key
                    )
                )
                if existing is None:
                    raise
                if (
                    existing.run_id != run_id
                    or existing.release_hash != release_hash
                    or existing.target != target
                    or existing.parameters != parameters
                ):
                    raise ValueError(
                        "The idempotency key is already used for a different execution request."
                    )
                return self._execution_dict(existing)
            self._append_event(
                session,
                record.request_id,
                "execution_requested",
                actor,
                {"target": target, "release_hash": release_hash},
            )
            session.commit()
            session.refresh(record)
            return self._execution_dict(record)

    def approve_execution(self, request_id: str, actor: str, note: str) -> dict[str, Any]:
        with Session(self.engine) as session:
            record = session.get(ExecutionRequestRecord, request_id)
            if record is None:
                raise KeyError(request_id)
            if record.status != "execution_requested":
                raise ValueError(f"Execution request is not awaiting approval: {record.status}")
            if record.requested_by == actor:
                raise ValueError("Four-eyes control requires a different execution approver.")
            approved_at = now_utc()
            record.status = "queued"
            record.approved_by = actor
            record.approved_at = approved_at
            record.updated_at = approved_at
            self._append_event(
                session,
                request_id,
                "approved_for_execution",
                actor,
                {"note": note},
            )
            session.commit()
            session.refresh(record)
            return self._execution_dict(record)

    def cancel_execution(self, request_id: str, actor: str, note: str) -> dict[str, Any]:
        with Session(self.engine) as session:
            record = session.get(ExecutionRequestRecord, request_id)
            if record is None:
                raise KeyError(request_id)
            if record.status in TERMINAL_EXECUTION_STATES:
                return self._execution_dict(record)
            changed_at = now_utc()
            record.status = "cancel_requested" if record.status == "running" else "cancelled"
            if record.status == "cancelled":
                record.finished_at = changed_at
            record.updated_at = changed_at
            self._append_event(
                session,
                request_id,
                record.status,
                actor,
                {"note": note},
            )
            session.commit()
            session.refresh(record)
            return self._execution_dict(record)

    def claim_next_execution(self, worker_id: str) -> dict[str, Any] | None:
        with Session(self.engine) as session:
            with session.begin():
                record = session.scalar(
                    select(ExecutionRequestRecord)
                    .where(ExecutionRequestRecord.status == "queued")
                    .order_by(ExecutionRequestRecord.requested_at.asc())
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
                if record is None:
                    return None
                started_at = now_utc()
                record.status = "running"
                record.started_at = started_at
                record.updated_at = started_at
                self._append_event(
                    session,
                    record.request_id,
                    "execution_started",
                    worker_id,
                    {},
                )
            session.refresh(record)
            return self._execution_dict(record)

    def update_execution(
        self,
        request_id: str,
        *,
        status: str,
        actor: str,
        cloud_job_id: str | None = None,
        evidence: dict[str, Any] | None = None,
        error_message: str = "",
    ) -> dict[str, Any]:
        with Session(self.engine) as session:
            record = session.get(ExecutionRequestRecord, request_id)
            if record is None:
                raise KeyError(request_id)
            updated_at = now_utc()
            record.status = status
            record.updated_at = updated_at
            if cloud_job_id:
                record.cloud_job_id = cloud_job_id
            if evidence is not None:
                ensure_safe_parameters(evidence, "evidence")
                record.evidence = evidence
            record.error_message = error_message[:4000]
            if status in TERMINAL_EXECUTION_STATES:
                record.finished_at = updated_at
            self._append_event(
                session,
                request_id,
                status,
                actor,
                {
                    "cloud_job_id": cloud_job_id or record.cloud_job_id or "",
                    "error": bool(error_message),
                },
            )
            session.commit()
            session.refresh(record)
            return self._execution_dict(record)

    def execution_request(self, request_id: str) -> dict[str, Any] | None:
        with Session(self.engine) as session:
            record = session.get(ExecutionRequestRecord, request_id)
            return self._execution_dict(record) if record else None

    def run_control_status(self, run_id: str) -> dict[str, Any]:
        with Session(self.engine) as session:
            approvals = list(
                session.scalars(
                    select(ArtifactApprovalRecord)
                    .where(ArtifactApprovalRecord.run_id == run_id)
                    .order_by(ArtifactApprovalRecord.id.asc())
                )
            )
            releases = list(
                session.scalars(
                    select(ReleaseRecord)
                    .where(ReleaseRecord.run_id == run_id)
                    .order_by(ReleaseRecord.id.desc())
                )
            )
            executions = list(
                session.scalars(
                    select(ExecutionRequestRecord)
                    .where(ExecutionRequestRecord.run_id == run_id)
                    .order_by(ExecutionRequestRecord.requested_at.desc())
                )
            )
            state = "draft"
            latest_approvals: dict[str, ArtifactApprovalRecord] = {}
            for approval in approvals:
                latest_approvals[approval.artifact_name] = approval
            if latest_approvals and all(
                item.decision == "approved" for item in latest_approvals.values()
            ):
                state = "reviewed"
            if releases:
                state = "released"
            if executions:
                state = executions[0].status
            return {
                "run_id": run_id,
                "state": state,
                "latest_release": self._release_dict(releases[0]) if releases else None,
                "approvals": [self._approval_dict(item) for item in approvals],
                "executions": [self._execution_dict(item) for item in executions],
            }

    @staticmethod
    def _append_event(
        session: Session,
        request_id: str,
        event_type: str,
        actor: str,
        payload: dict[str, Any],
    ) -> None:
        session.add(
            ExecutionEventRecord(
                request_id=request_id,
                event_type=event_type,
                actor=actor,
                payload=payload,
                created_at=now_utc(),
            )
        )

    @staticmethod
    def _approval_dict(record: ArtifactApprovalRecord) -> dict[str, Any]:
        return {
            "id": record.id,
            "run_id": record.run_id,
            "artifact_name": record.artifact_name,
            "artifact_hash": record.artifact_hash,
            "decision": record.decision,
            "actor": record.actor,
            "note": record.note,
            "created_at": record.created_at.isoformat(),
        }

    @staticmethod
    def _release_dict(record: ReleaseRecord) -> dict[str, Any]:
        return {
            "id": record.id,
            "run_id": record.run_id,
            "release_hash": record.release_hash,
            "manifest": record.manifest,
            "released_by": record.released_by,
            "created_at": record.created_at.isoformat(),
        }

    @staticmethod
    def _execution_dict(record: ExecutionRequestRecord) -> dict[str, Any]:
        return {
            "request_id": record.request_id,
            "run_id": record.run_id,
            "release_hash": record.release_hash,
            "target": record.target,
            "parameters": record.parameters,
            "idempotency_key": record.idempotency_key,
            "status": record.status,
            "requested_by": record.requested_by,
            "approved_by": record.approved_by,
            "cloud_job_id": record.cloud_job_id,
            "evidence": record.evidence or {},
            "error_message": record.error_message,
            "requested_at": record.requested_at.isoformat(),
            "approved_at": record.approved_at.isoformat() if record.approved_at else None,
            "started_at": record.started_at.isoformat() if record.started_at else None,
            "finished_at": record.finished_at.isoformat() if record.finished_at else None,
            "updated_at": record.updated_at.isoformat(),
        }


_STORE: ProductionControlStore | None = None
_STORE_URL = ""
_STORE_LOCK = Lock()


def get_production_store() -> ProductionControlStore:
    global _STORE, _STORE_URL
    current_url = database_url()
    if _STORE is not None and _STORE_URL == current_url:
        return _STORE
    with _STORE_LOCK:
        if _STORE is None or _STORE_URL != current_url:
            _STORE = ProductionControlStore(current_url)
            _STORE_URL = current_url
    return _STORE


def reset_production_store_for_tests() -> None:
    global _STORE, _STORE_URL
    with _STORE_LOCK:
        if _STORE is not None:
            _STORE.engine.dispose()
        _STORE = None
        _STORE_URL = ""
