import base64
import os
from unittest.mock import Mock, patch

import httpx
import pytest
from fastapi import HTTPException

from app.services import github_cache as cache, github_rate_limit as policy
from app.services.project_github import GitHubClient


@pytest.fixture(autouse=True)
def isolated_state():
    cache._entries.clear()
    policy._cooldowns.clear()
    with patch.dict(os.environ, {'GITHUB_CLIENT_ID':'public-app', 'GITHUB_CLIENT_SECRET':'app-secret',
                                 'GITHUB_TOKEN':'', 'GITHUB_TOKEN_OWNER_ID':''}):
        yield
    cache._entries.clear()
    policy._cooldowns.clear()


def test_public_reads_use_app_auth_without_any_users_personal_token():
    with patch('httpx.Client.get', return_value=httpx.Response(200, json=[])) as get:
        GitHubClient('acme/public', 99).get('/commits')
    value = get.call_args.kwargs['headers']['Authorization']
    assert value.startswith('Basic ')
    assert base64.b64decode(value[6:]).decode() == 'public-app:app-secret'
    assert get.call_args.kwargs.get('follow_redirects') is None


def test_private_personal_token_has_priority_and_is_not_shared():
    db = Mock()
    db.scalar.return_value = 'encrypted'
    with patch('app.services.project_github.decrypt_token', return_value='owner-private'):
        personal = GitHubClient('acme/private', 1, db)
    public = GitHubClient('acme/private', 2)
    assert personal.headers['Authorization'] == 'Bearer owner-private'
    assert public.headers['Authorization'].startswith('Basic ')
    assert cache.key(personal.headers, 'acme/private', '', None) != cache.key(public.headers, 'acme/private', '', None)


def test_repeated_reads_use_cache_and_revalidate_without_mutating_shared_data():
    client = GitHubClient('acme/public', 99)
    with patch.object(cache.time, 'monotonic', return_value=1000), patch('httpx.Client.get', return_value=httpx.Response(200, json=[{'sha':'a'}], headers={'etag':'"revision"', 'Link':'<https://api.github.com/repos/acme/public/commits?page=2>; rel="next"'})) as get:
        rows, _ = client.get('/commits', {'page':1})
        rows[0]['sha'] = 'mutated'
        assert client.get('/commits', {'page':1})[0] == [{'sha':'a'}]
        assert get.call_count == 1
    with patch.object(cache.time, 'monotonic', return_value=1031), patch('httpx.Client.get', return_value=httpx.Response(304)) as get:
        assert client.get('/commits', {'page':1}) == ([{'sha':'a'}], True)
        assert get.call_args.kwargs['headers']['If-None-Match'] == '"revision"'
        assert get.call_args.kwargs['headers']['Authorization'].startswith('Basic ')


def test_cache_does_not_cross_auth_repository_path_or_page_boundaries():
    key = cache.key({'Authorization':'Bearer owner'}, 'acme/private', '/commits', {'page':1})
    cache.save(key, [{'sha':'private'}], False, None)
    for headers, repo, path, params in [({},'acme/private','/commits',{'page':1}),
            ({'Authorization':'Bearer other'},'acme/private','/commits',{'page':1}),
            ({'Authorization':'Bearer owner'},'other/repo','/commits',{'page':1}),
            ({'Authorization':'Bearer owner'},'acme/private','/branches',{'page':1}),
            ({'Authorization':'Bearer owner'},'acme/private','/commits',{'page':2})]:
        assert cache.lookup(cache.key(headers, repo, path, params)) is None


def test_cooldown_can_serve_fresh_cache_but_never_mislabels_stale_data_as_fresh():
    client = GitHubClient('acme/public', 99)
    with patch.object(cache.time, 'monotonic', return_value=1000):
        cache.save(cache.key(client.headers, client.repository, '', None), {'name':'saved'}, False, None)
        with pytest.raises(HTTPException):
            policy.record(client.headers, {'retry-after':'120'})
        with patch('httpx.Client.get') as get:
            assert client.get() == ({'name':'saved'}, False)
            get.assert_not_called()
    with patch.object(cache.time, 'monotonic', return_value=1031), patch('httpx.Client.get') as get:
        with pytest.raises(HTTPException):
            client.get()
        get.assert_not_called()


def test_cache_has_entry_and_byte_limits():
    with patch.object(cache, 'MAX_ENTRIES', 2), patch.object(cache, 'MAX_BYTES', 200):
        for index in range(3):
            cache.save(('key', index), {'value':index}, False, None)
        assert len(cache._entries) == 2
        assert ('key', 0) not in cache._entries
    with patch.object(cache, 'MAX_ENTRY_BYTES', 5):
        cache.save(('too-large',), {'content':'large'}, False, None)
        assert ('too-large',) not in cache._entries


def test_old_conditional_entries_expire_after_ten_minutes():
    with patch.object(cache.time, 'monotonic', return_value=1000):
        cache.save(('old',), {'data':'saved'}, False, 'etag')
    with patch.object(cache.time, 'monotonic', return_value=1600):
        assert cache.lookup(('old',)) is None
