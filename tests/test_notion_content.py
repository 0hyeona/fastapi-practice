"""Exercise snapshots and activities in real SQLite transactions, no live API/DB."""
from copy import deepcopy
from unittest.mock import patch
import unittest

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.models.project_notion_snapshot import ProjectNotionSnapshot
from app.models.project_activity import ProjectActivity
from app.models.project_sync_run import ProjectSyncRun
from app.services import external_sync as api
import test_external_sync as fixtures
from test_external_sync import NOTION


def block(number, text, kind='paragraph', children=False, **extra):
    return {'object': 'block', 'id': f'{number:032x}', 'type': kind, 'has_children': children,
            kind: {'rich_text': [{'plain_text': text}], **extra}}


def listing(*blocks, more=False, cursor=None):
    return {'object': 'list', 'results': list(blocks), 'has_more': more, 'next_cursor': cursor}


class NotionContentTests(unittest.TestCase):
    setUp = fixtures.IntegrationTests.setUp
    tearDown = fixtures.IntegrationTests.tearDown

    def sync(self, *blocks, title='Notes', responses=None):
        page = deepcopy(NOTION)
        page['properties']['Name']['title'] = [{'plain_text': title}]
        with patch.object(api, 'fetch_json', side_effect=responses or [page, listing(*blocks), page]):
            return api.sync_external(self.db, self.project, 'notion')

    def snapshot(self):
        self.db.expire_all()
        return self.db.scalar(select(ProjectNotionSnapshot))

    def activities(self):
        return self.db.scalars(select(ProjectActivity).order_by(ProjectActivity.id)).all()

    def test_baseline_then_all_change_types(self):
        self.assertEqual(self.sync(block(1, '이전'), block(2, '삭제'))['created'], 0)
        self.assertEqual(self.snapshot().revision, 1)
        result = self.sync(block(1, '수정'), block(3, '추가'), title='새 제목')
        self.assertEqual(result['created'], 4)
        rows = self.activities()
        self.assertEqual([r.activity_type for r in rows],
                         ['title_changed', 'content_updated', 'content_added', 'content_deleted'])
        self.assertIn('수정 전: 이전\n수정 후: 수정', rows[1].description)
        self.assertIn('추가', rows[2].description)
        self.assertIn('삭제', rows[3].description)
        self.assertEqual(self.snapshot().revision, 2)
        self.assertEqual(self.sync(block(1, '수정'), block(3, '추가'), title='새 제목')['created'], 0)
        self.assertEqual(len(self.activities()), 4)

    def test_empty_baseline_and_delete_everything(self):
        self.sync()
        self.assertEqual(self.sync(block(1, 'hello'))['created'], 1)
        self.assertEqual(self.sync()['created'], 1)
        self.assertEqual(self.snapshot().content['blocks'], {})

    def test_reverts_are_new_changes_even_at_same_timestamp(self):
        self.sync(block(1, 'A'))
        self.sync(block(1, 'B'))
        self.sync(block(1, 'A'))
        self.sync(block(1, 'B'))
        self.assertEqual(len({r.external_id for r in self.activities()}), 3)

    def test_pagination_nested_text_and_checkbox(self):
        responses = [NOTION, listing(block(1, 'parent', children=True), more=True, cursor='next'),
                     listing(block(2, 'child')), listing(block(3, 'todo', kind='to_do', checked=False)), NOTION]
        self.sync(responses=responses)
        self.assertEqual(len(self.snapshot().content['blocks']), 3)
        responses[3] = listing(block(3, 'todo', kind='to_do', checked=True))
        self.assertEqual(self.sync(responses=responses)['created'], 1)
        self.assertIn('[ ] todo', self.activities()[0].description)
        self.assertIn('[x] todo', self.activities()[0].description)

    def test_failure_preserves_snapshot_and_records_failure(self):
        self.sync(block(1, 'keep'))
        before = deepcopy(self.snapshot().content)
        for error in (HTTPException(503, 'limited'), HTTPException(504, 'timeout'), {},
                      listing(more=True), listing(block(1, 'a'), block(1, 'b'))):
            with self.subTest(error=error), self.assertRaises(HTTPException):
                self.sync(responses=[NOTION, error])
            self.assertEqual(self.snapshot().content, before)
            self.assertEqual(self.snapshot().revision, 1)
            self.assertEqual(self.activities(), [])
        runs = self.db.scalars(select(ProjectSyncRun).order_by(ProjectSyncRun.id)).all()
        self.assertEqual(runs[-1].status, 'failed')

    def test_later_page_failure_does_not_save_partial_content(self):
        self.sync(block(1, 'keep'))
        with self.assertRaises(HTTPException):
            self.sync(responses=[NOTION, listing(block(2, 'partial'), more=True, cursor='next'),
                                 HTTPException(502, 'failed')])
        self.assertEqual(list(self.snapshot().content['blocks']), [f'{1:032x}'])

    def test_page_changed_during_read_preserves_baseline(self):
        self.sync(block(1, 'keep'))
        changed = {**NOTION, 'last_edited_time': '2026-11-01T01:00:00Z'}
        with self.assertRaises(HTTPException) as error:
            self.sync(responses=[NOTION, listing(block(1, 'new')), changed])
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(self.snapshot().revision, 1)

    def test_commit_failure_rolls_back_both_changes_and_snapshot(self):
        self.sync(block(1, 'keep'))
        commit = self.db.commit
        calls = 0
        def failing_commit():
            nonlocal calls
            calls += 1
            if calls == 2:
                self.db.flush()
                raise SQLAlchemyError('test failure')
            return commit()
        with patch.object(self.db, 'commit', side_effect=failing_commit), self.assertRaises(SQLAlchemyError):
            self.sync(block(1, 'new'))
        self.assertEqual(self.snapshot().revision, 1)
        self.assertEqual(self.activities(), [])

    def test_new_page_has_independent_baseline(self):
        self.sync(block(1, 'keep'))
        self.project.notion_url = 'https://notion.so/' + 'b' * 32
        self.db.commit()
        page = {**NOTION, 'id': 'b' * 32}
        with patch.dict('os.environ', {'NOTION_ALLOWED_PAGE_IDS': 'b' * 32}):
            self.assertEqual(self.sync(responses=[page, listing(block(1, 'new')), page])['created'], 0)
        self.assertEqual(len(self.db.scalars(select(ProjectNotionSnapshot)).all()), 2)
