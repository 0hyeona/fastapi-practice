"""Persist attempts and commit successful activities and history atomically."""
import logging
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from app.models.project_sync_run import ProjectSyncRun

logger = logging.getLogger(__name__)


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def record_sync(db, project, source, collect, pagination=False):
    if source == 'figma':
        from app.services.figma_sync_policy import guard
        try:
            guard(db, project.id, pagination)
        except Exception:
            db.rollback()
            raise
    run = ProjectSyncRun(project_id=project.id, source=source, status="running", started_at=utcnow())
    try:
        db.add(run)
        db.commit()
        run_id = run.id
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(503, "Cannot initialize sync history. Check database and project_sync_runs migration.") from None
    progress = {"fetched": 0}
    try:
        result = collect(progress)
        run.status = "success"
        run.finished_at = utcnow()
        for key in ("fetched", "created", "existing"):
            setattr(run, key, result[key])
        db.commit()
        return result
    except Exception as error:
        db.rollback()
        # Never persist exception text: it may contain tokens, URLs or SQL values.
        code = error.status_code if isinstance(error, HTTPException) else 500
        messages = {
            400: "Invalid collection request.", 401: "Authentication required.",
            403: "Collection access denied.", 404: "Collection resource not found.",
            409: "Project connection changed during collection.",
            422: "Invalid connection or collection parameters.",
            429: "External service rate limit reached.",
            502: "External service request or response failed.",
            503: "Collection configuration or service unavailable.",
            504: "External service timed out.",
        }
        try:
            failed = db.get(ProjectSyncRun, run_id)
            if failed is not None:
                failed.status = "failed"
                failed.finished_at = utcnow()
                failed.fetched = progress["fetched"]
                failed.created = 0
                failed.existing = 0
                failed.error_code = code
                failed.error_message = messages.get(code, "Collection failed; check server configuration and logs.")
                if source == 'figma' and code == 429:
                    from app.services.figma_sync_policy import rate_limit_message
                    failed.error_message = rate_limit_message(error)
                db.commit()
        except Exception:
            db.rollback()
            logger.error("Unable to finalize sync run %s", run_id)
        raise
