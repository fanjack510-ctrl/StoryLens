from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from storylens_online.db.models import OnlineAnalysisJob, OnlineBookUpload
from storylens_online.services.storage import StoredUpload


class OnlineRepository:
    @staticmethod
    def create_upload(session: Session, user_id: str, stored: StoredUpload) -> OnlineBookUpload:
        upload = OnlineBookUpload(
            user_id=user_id,
            original_filename=stored.original_filename,
            storage_key=stored.storage_key,
            sha256=stored.sha256,
            file_size_bytes=stored.file_size_bytes,
        )
        session.add(upload)
        session.flush()
        return upload

    @staticmethod
    def get_upload_for_user(
        session: Session,
        upload_id: str,
        user_id: str,
    ) -> OnlineBookUpload | None:
        return session.scalar(
            select(OnlineBookUpload).where(
                OnlineBookUpload.id == upload_id,
                OnlineBookUpload.user_id == user_id,
            )
        )

    @staticmethod
    def create_or_get_job(
        session: Session,
        *,
        user_id: str,
        upload_id: str,
        idempotency_key: str,
    ) -> tuple[OnlineAnalysisJob, bool]:
        existing = session.scalar(
            select(OnlineAnalysisJob).where(
                OnlineAnalysisJob.user_id == user_id,
                OnlineAnalysisJob.idempotency_key == idempotency_key,
            )
        )
        if existing:
            return existing, False

        job = OnlineAnalysisJob(
            user_id=user_id,
            upload_id=upload_id,
            idempotency_key=idempotency_key,
            status="queued",
            progress=0,
            pipeline="phase2a_smoke",
        )
        session.add(job)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            existing = session.scalar(
                select(OnlineAnalysisJob).where(
                    OnlineAnalysisJob.user_id == user_id,
                    OnlineAnalysisJob.idempotency_key == idempotency_key,
                )
            )
            if existing is None:
                raise
            return existing, False
        return job, True

    @staticmethod
    def list_jobs(session: Session, user_id: str) -> list[OnlineAnalysisJob]:
        return list(
            session.scalars(
                select(OnlineAnalysisJob)
                .where(OnlineAnalysisJob.user_id == user_id)
                .order_by(OnlineAnalysisJob.created_at.desc())
                .limit(100)
            )
        )

    @staticmethod
    def get_job_for_user(
        session: Session,
        job_id: str,
        user_id: str,
    ) -> OnlineAnalysisJob | None:
        return session.scalar(
            select(OnlineAnalysisJob).where(
                OnlineAnalysisJob.id == job_id,
                OnlineAnalysisJob.user_id == user_id,
            )
        )

    @staticmethod
    def claim_job(
        session: Session,
        job_id: str,
        lease_seconds: int,
    ) -> tuple[OnlineAnalysisJob, OnlineBookUpload] | None:
        now = datetime.now(UTC)
        eligible = or_(
            OnlineAnalysisJob.status == "queued",
            and_(
                OnlineAnalysisJob.status == "running",
                OnlineAnalysisJob.lease_expires_at.is_not(None),
                OnlineAnalysisJob.lease_expires_at < now,
            ),
        )
        claimed = session.execute(
            update(OnlineAnalysisJob)
            .where(OnlineAnalysisJob.id == job_id, eligible)
            .values(
                status="running",
                progress=10,
                public_error_code=None,
                started_at=now,
                finished_at=None,
                lease_expires_at=now + timedelta(seconds=lease_seconds),
                attempt_count=OnlineAnalysisJob.attempt_count + 1,
            )
        )
        if claimed.rowcount != 1:
            return None
        job = session.get(OnlineAnalysisJob, job_id)
        if job is None:
            return None
        upload = session.get(OnlineBookUpload, job.upload_id)
        if upload is None or upload.user_id != job.user_id:
            OnlineRepository.mark_failed(session, job.id, "upload_not_found")
            return None
        return job, upload

    @staticmethod
    def mark_succeeded(
        session: Session,
        job_id: str,
        result: dict[str, object],
    ) -> None:
        session.execute(
            update(OnlineAnalysisJob)
            .where(OnlineAnalysisJob.id == job_id, OnlineAnalysisJob.status == "running")
            .values(
                status="succeeded",
                progress=100,
                result_json=result,
                public_error_code=None,
                finished_at=datetime.now(UTC),
                lease_expires_at=None,
            )
        )

    @staticmethod
    def mark_failed(session: Session, job_id: str, error_code: str) -> None:
        session.execute(
            update(OnlineAnalysisJob)
            .where(
                OnlineAnalysisJob.id == job_id,
                OnlineAnalysisJob.status.in_(("queued", "running")),
            )
            .values(
                status="failed",
                progress=100,
                result_json=None,
                public_error_code=error_code,
                finished_at=datetime.now(UTC),
                lease_expires_at=None,
            )
        )

    @staticmethod
    def reset_recovered_job(session: Session, job_id: str) -> None:
        session.execute(
            update(OnlineAnalysisJob)
            .where(OnlineAnalysisJob.id == job_id, OnlineAnalysisJob.status == "running")
            .values(
                status="queued",
                progress=0,
                lease_expires_at=None,
                public_error_code=None,
            )
        )
