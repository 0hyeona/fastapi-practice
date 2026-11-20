from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from app.schemas.story import StoryAnalysisRequest
from app.services import story_analysis as rules


SHA = 'a' * 40


@pytest.fixture
def context():
    rules._cache.clear()
    db = MagicMock()
    project = SimpleNamespace(github_url='https://github.com/example/repo', owner_id=1)
    activity = SimpleNamespace(source='github', title='fix: login', description='Handle expired sessions',
                               external_id=f'example/repo:{SHA}', branch_name='main')
    with patch.object(rules, 'require_project', return_value=project), \
         patch.object(rules, 'selected_activities', return_value=[activity]), \
         patch.object(rules, 'GitHubClient') as client_type:
        client = client_type.return_value
        client.repository = 'example/repo'
        client.headers = {'Authorization': 'Bearer fake-test-only'}
        client.get.return_value = ({'files': [
            {'filename': 'auth.py', 'status': 'modified', 'additions': 1, 'deletions': 1,
             'patch': '@@ -1 +1 @@\n-old()\n+new()'},
            {'filename': 'icon.png', 'status': 'added', 'additions': 0, 'deletions': 0},
        ]}, False)
        yield db, activity, client


def run(db, **changes):
    return rules.analyze(db, StoryAnalysisRequest(project_id=1, activity_ids=[1], **changes), 1)


def test_code_diff_without_openai_key(context, monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    db, _, client = context
    with patch('httpx.post', side_effect=AssertionError('No AI request allowed')):
        result = run(db, mode='code')
    assert 'old()' in result.before and 'new()' not in result.before
    assert 'new()' in result.after and 'old()' not in result.after
    assert 'auth.py' in result.summary and 'icon.png' in result.summary
    assert 'diff' in result.summary
    client.get.assert_called_once_with(f'/commits/{SHA}', {'per_page': 100})
    db.rollback.assert_called_once()


def test_modes_and_cache(context):
    db, _, client = context
    semantic = run(db).summary
    balanced = run(db, mode='balanced').summary
    assert 'auth.py' not in semantic and 'auth.py' in balanced
    assert client.get.call_count == 1
    client.headers = {'Authorization': 'Bearer different-test-user'}
    run(db)
    assert client.get.call_count == 2


def test_github_limit_preserves_stored_evidence(context):
    db, _, client = context
    client.get.side_effect = HTTPException(503, 'GitHub rate limit')
    result = run(db, mode='code')
    assert result.title == 'fix: login'
    assert 'GitHub rate limit' in result.summary
    assert 'Handle expired sessions' in result.summary
    assert result.before is None and result.after is None


def test_old_repository_record_is_never_fetched_from_new_repo(context):
    db, activity, client = context
    activity.external_id = f'other/repo:{SHA}'
    result = run(db)
    client.get.assert_not_called()
    assert result.before is None


def test_partial_and_invalid_github_response(context):
    db, _, client = context
    data, _ = client.get.return_value
    client.get.return_value = (data, True)
    assert '100' in run(db).summary
    rules._cache.clear()
    client.get.return_value = ({'files': [{'filename': 'bad.py', 'additions': 'bad'}]}, False)
    assert run(db).before is None


def test_notions_do_not_invent_code_or_make_github_requests(context):
    db, activity, client = context
    activity.source, activity.description = 'notion', '추가된 내용: 프로젝트 설명'
    result = run(db)
    assert '프로젝트 설명' in result.summary
    assert result.before is None and result.after is None
    client.get.assert_not_called()


def test_output_limits_and_section_regeneration(context):
    db, activity, _ = context
    activity.title, activity.description = 't' * 200, 'x' * 15000
    result = run(db, mode='code')
    assert len(result.title) <= 200 and len(result.summary) <= 3000
    result = run(db, section='before')
    assert result.model_fields_set == {'before'}


@pytest.fixture
def database():
    from datetime import datetime
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.database.database import Base
    from app.models.user import User
    from app.models.project import Project
    from app.models.project_activity import ProjectActivity
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(User(id=1, user_id='owner', name='Owner', email='owner@example.invalid', password_hash='test'))
        db.add(Project(id=1, owner_id=1, project_name='Test'))
        db.add(Project(id=2, owner_id=2, project_name='Other'))
        db.add(ProjectActivity(id=1, project_id=1, source='notion', activity_type='update',
                               title='프로젝트 설명 수정', description='설명에 사용 방법 추가', occurred_at=datetime.now()))
        db.add(ProjectActivity(id=2, project_id=2, source='notion', activity_type='update',
                               title='Private record', occurred_at=datetime.now()))
        db.commit()
        yield db
    engine.dispose()


def test_database_analysis_to_persisted_story_without_key(database, monkeypatch):
    from app.models.story import Story
    from app.models.project_activity import ProjectActivity
    from app.schemas.story import StoryCreate, StoryUpdate
    from app.services import project_content_service as service
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    analysis = run(database)
    assert '사용 방법 추가' in analysis.summary
    story = service.create(database, Story, StoryCreate(project_id=1, activity_ids=[1],
                           title=analysis.title, ai_analysis=analysis.model_dump()), 1)
    story_id = story.id
    service.update(database, Story, story_id, 1, StoryUpdate(story_status='published'))
    database.expire_all()
    restored = service.get(database, Story, story_id, 1)
    assert restored.story_status == 'published'
    assert restored.ai_analysis['summary'] == analysis.summary
    assert database.get(ProjectActivity, 1).story_id == story_id


def test_database_foreign_project_and_activity_are_rejected(database):
    with pytest.raises(HTTPException) as denied:
        rules.analyze(database, StoryAnalysisRequest(project_id=1, activity_ids=[1]), 2)
    assert denied.value.status_code == 404
    with pytest.raises(HTTPException) as denied:
        rules.analyze(database, StoryAnalysisRequest(project_id=1, activity_ids=[2]), 1)
    assert denied.value.status_code == 404


def test_selection_validation():
    from pydantic import ValidationError
    for fields in ({'activity_ids': []}, {'activity_ids': [1] * 21}, {'mode': 'invalid'}):
        with pytest.raises(ValidationError):
            StoryAnalysisRequest.model_validate({'project_id': 1, 'activity_ids': [1], **fields})
