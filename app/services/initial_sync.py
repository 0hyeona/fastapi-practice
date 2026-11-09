"""Best-effort initial collection after project link saves; retry via POST sync."""
import logging
from fastapi import HTTPException
from app.database.database import SessionLocal
from app.models.project import Project
from app.services.external_sync import connection_state, sync_external

logger = logging.getLogger(__name__)


def initial_sync(project_id, owner_id, sources):
    for source in sources:
        try:
            with SessionLocal() as db:
                project = db.get(Project, project_id)
                if project is None or project.owner_id != owner_id:
                    return
                if not connection_state(project, source)['configured']:
                    continue
                sync_external(db, project, source)
        except HTTPException as error:
            logger.warning('Initial sync failed: project=%s source=%s status=%s', project_id, source, error.status_code)
        except Exception:
            # Do not log tokens, upstream response bodies or private page content.
            logger.error('Initial sync failed: project=%s source=%s', project_id, source)


def queue_initial_sync(background_tasks, project, sources):
    sources = tuple(source for source in sources if source != 'figma' and getattr(project, source + '_url'))
    if sources:
        background_tasks.add_task(initial_sync, project.id, project.owner_id, sources)
