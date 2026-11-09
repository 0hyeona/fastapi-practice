"""Persistent Figma gating using existing sync history (no schema migration)."""
import json
import math
import os
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select
from app.models.project import Project
from app.models.project_sync_run import ProjectSyncRun


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def retry_at(run):
    if not run or run.error_code != 429:
        return None
    try:
        return datetime.fromisoformat(json.loads(run.error_message)['retry_at'])
    except (ValueError, TypeError, KeyError):
        return None


def state(db, project_id, locked=False):
    runs = select(ProjectSyncRun).where(ProjectSyncRun.project_id == project_id,
                                      ProjectSyncRun.source == 'figma')
    if locked:
        runs = runs.with_for_update().execution_options(populate_existing=True)
    running = db.scalar(runs.where(ProjectSyncRun.status == 'running').limit(1))
    limited = db.scalar(runs.where(ProjectSyncRun.error_code == 429)
                        .order_by(ProjectSyncRun.id.desc()).limit(1))
    success = db.scalar(runs.where(ProjectSyncRun.status == 'success')
                        .order_by(ProjectSyncRun.id.desc()).limit(1))
    deadline = retry_at(limited)
    interval = max(0, int(os.getenv('FIGMA_SYNC_MIN_INTERVAL_SECONDS', '600')))
    if success and success.finished_at:
        minimum = success.finished_at + timedelta(seconds=interval)
        deadline = max(deadline, minimum) if deadline else minimum
    remaining = max(0, math.ceil((deadline - now()).total_seconds())) if deadline else 0
    return {'running': running is not None, 'can_sync': running is None and remaining == 0,
            'retry_after_seconds': remaining,
            'next_sync_at': deadline.replace(tzinfo=timezone.utc) if remaining else None,
            'last_success_at': success.finished_at.replace(tzinfo=timezone.utc) if success and success.finished_at else None}


def guard(db, project_id, pagination=False):
    # Serialize admission across workers. Commit of the running history row releases
    # this lock, before any HTTP request. A crashed run remains blocked for review.
    db.scalar(select(Project.id).where(Project.id == project_id).with_for_update())
    status = state(db, project_id, locked=True)
    if status['running']:
        raise HTTPException(409, 'Figma 수집이 이미 진행 중입니다. 저장된 변경사항을 조회하세요.')
    remaining = status['retry_after_seconds']
    if remaining:
        raise HTTPException(429, 'Figma 재수집 대기 중입니다. 저장된 변경사항을 조회하세요.',
                            headers={'Retry-After': str(remaining)})


def rate_limit_message(error):
    value = (error.headers or {}).get('Retry-After', '')
    # Missing/invalid Retry-After: conservative fallback, not an asserted reset time.
    seconds = int(value) if value.isdigit() else 3600
    seconds = max(1, seconds)
    return json.dumps({'reason': 'Figma rate limit',
                       'retry_at': (now() + timedelta(seconds=seconds)).isoformat(),
                       'retry_after_seconds': seconds}, separators=(',', ':'))
