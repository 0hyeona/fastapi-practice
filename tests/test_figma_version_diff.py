import copy
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import select

from app.models.project_activity import ProjectActivity
from app.services import external_sync as api
from app.services.figma_version_diff import PREFIX, describe, flatten
import test_external_sync


def document(version='2', text='로그인', color=0, x=10):
    return {'version': version, 'name': 'MOEUM', 'lastModified': f'2026-11-0{version}T00:00:00Z',
            'document': {'id': '0:0', 'type': 'DOCUMENT', 'name': 'MOEUM', 'children': [
                {'id': '1:1', 'type': 'CANVAS', 'name': '화면', 'children': [
                    {'id': '2:1', 'type': 'FRAME', 'name': '로그인 화면',
                     'absoluteBoundingBox': {'x': x, 'y': 0, 'width': 400, 'height': 800},
                     'children': [{'id': '3:1', 'type': 'TEXT', 'name': '버튼 문구',
                                   'characters': text, 'style': {'fontSize': 16},
                                   'fills': [{'type': 'SOLID', 'color': {'r': color, 'g': 0, 'b': 0}}],
                                   'absoluteBoundingBox': {'x': x + 10, 'y': 5, 'width': 100, 'height': 24}}]}
                ]}]}}


class DifferenceTests(unittest.TestCase):
    def test_actual_text_and_color_before_after(self):
        result = describe(document('1'), document('2', '시작하기', 1))
        self.assertIn('로그인 화면 / 버튼 문구', result)
        self.assertIn('텍스트: 로그인 → 시작하기', result)
        self.assertIn('#000000 → #FF0000', result)
        self.assertIn('수정 1개', result)

    def test_move_parent_does_not_report_every_child(self):
        result = describe(document('1'), document('2', x=50))
        self.assertIn('수정 1개', result)
        self.assertIn('위치: [10, 0] → [50, 0]', result)

    def test_add_delete_and_size(self):
        before = document('1')
        after = document('2')
        frame = after['document']['children'][0]['children'][0]
        frame['children'] = [{'id': '4:1', 'name': '새 버튼', 'type': 'RECTANGLE'}]
        frame['absoluteBoundingBox']['width'] = 480
        result = describe(before, after)
        self.assertIn('추가 1개 · 삭제 1개 · 수정 1개', result)
        self.assertIn('새 버튼', result)
        self.assertIn('크기: [400, 800] → [480, 800]', result)

    def test_no_change_does_not_claim_untracked_pixels_equal(self):
        result = describe(document(), document())
        self.assertIn('차이가 발견되지 않았어요', result)
        self.assertIn('벡터 경로', result)

    def test_partial_or_duplicate_document_rejected(self):
        with self.assertRaises(KeyError):
            flatten({'version': '1'})
        malformed = document()
        malformed['document']['children'].append(copy.deepcopy(malformed['document']['children'][0]))
        with self.assertRaises(ValueError):
            flatten(malformed)


class CollectionTests(unittest.TestCase):
    setUp = test_external_sync.IntegrationTests.setUp
    tearDown = test_external_sync.IntegrationTests.tearDown

    def versions(self, count=2, next_page=None):
        return {'versions': [{'id': str(i), 'created_at': f'2026-11-0{i}T00:00:00Z',
                              'label': '', 'description': ''} for i in range(count, 0, -1)],
                'pagination': {'next_page': next_page} if next_page else {}}

    def collect(self, history, docs):
        calls = []
        def fetch(source, url, headers, params=None):
            calls.append((url, params))
            if url.endswith('/versions') or 'before=' in url:
                return history
            if params == {'depth': 1}:
                current = docs[str(max(map(int, docs)))]
                metadata = copy.deepcopy(current)
                for canvas in metadata['document']['children']:
                    canvas.pop('children', None)
                return metadata
            return docs[params['version']]
        with patch.object(api, 'fetch_json', side_effect=fetch):
            result = api.sync_external(self.db, self.project, 'figma')
        return result, calls

    def test_existing_activities_enriched_once_without_duplicates(self):
        docs = {'1': document('1'), '2': document('2', '시작하기')}
        # Old metadata-only records already exist, as on the deployed project.
        history = self.versions()
        with patch('app.services.figma_version_diff.enrich'):
            self.collect(history, docs)
        ids = self.db.scalars(select(ProjectActivity.id)).all()
        result, calls = self.collect(history, docs)
        self.assertEqual(result['created'], 0)
        rows = self.db.scalars(select(ProjectActivity)).all()
        self.assertEqual([row.id for row in rows], ids)
        self.assertTrue(all(row.description.startswith(PREFIX) for row in rows))
        self.assertTrue(any('로그인 → 시작하기' in row.description for row in rows))
        _, calls = self.collect(history, docs)
        self.assertEqual(len(calls), 2)  # metadata only; no version reread

    def test_request_budget_and_progressive_backfill(self):
        docs = {str(i): document(str(i), str(i)) for i in range(1, 5)}
        _, calls = self.collect(self.versions(4), docs)
        self.assertEqual(len([p for _, p in calls if p and 'version' in p]), 3)
        _, calls = self.collect(self.versions(4), docs)
        self.assertEqual(len([p for _, p in calls if p and 'version' in p]), 2)

    def test_failed_detail_request_preserves_cached_descriptions(self):
        docs = {'1': document('1'), '2': document('2', '시작하기')}
        with patch('app.services.figma_version_diff.enrich'):
            self.collect(self.versions(), docs)
        old = [(row.id, row.description) for row in self.db.scalars(select(ProjectActivity))]
        def fetch(source, url, headers, params=None):
            if url.endswith('/versions'):
                return self.versions()
            if params == {'depth': 1}:
                return {k: v for k, v in docs['2'].items() if k != 'document'}
            raise HTTPException(429, 'limited', headers={'Retry-After': '30'})
        with patch.object(api, 'fetch_json', side_effect=fetch), self.assertRaises(HTTPException):
            api.sync_external(self.db, self.project, 'figma')
        self.assertEqual(old, [(row.id, row.description) for row in self.db.scalars(select(ProjectActivity))])

    def test_organized_activities_preserved(self):
        docs = {'1': document('1'), '2': document('2', '시작하기')}
        with patch('app.services.figma_version_diff.enrich'):
            self.collect(self.versions(), docs)
        from app.models.story import Story
        story = Story(project_id=self.project.id, title='Already written', content='User content')
        self.db.add(story)
        self.db.flush()
        for row in self.db.scalars(select(ProjectActivity)):
            row.story_id = story.id
        self.db.commit()
        _, calls = self.collect(self.versions(), docs)
        self.assertEqual(len(calls), 2)
        self.assertEqual(story.content, 'User content')

    def test_partial_version_response_rolls_back(self):
        docs = {'1': document('1'), '2': document('2')}
        docs['1'].pop('document')
        with self.assertRaises(HTTPException) as error:
            self.collect(self.versions(), docs)
        self.assertEqual(error.exception.status_code, 502)
        self.assertEqual(self.db.scalars(select(ProjectActivity)).all(), [])

    def test_page_boundary_is_not_claimed_as_first_version(self):
        cursor = 'https://api.figma.com/v1/files/ABC123/versions?before=1'
        docs = {'1': document('1')}
        self.collect(self.versions(1, cursor), docs)
        row = self.db.scalar(select(ProjectActivity))
        self.assertNotIn('최초 기록', row.description or '')
