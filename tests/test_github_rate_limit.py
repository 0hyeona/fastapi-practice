from unittest.mock import patch

import httpx
import pytest
from fastapi import HTTPException

from app.services import github_rate_limit as policy
from app.services.project_github import GitHubClient


@pytest.fixture(autouse=True)
def clear_cooldowns():
    policy._cooldowns.clear()
    yield
    policy._cooldowns.clear()


def test_exhausted_anonymous_budget_blocks_other_repositories_until_reset():
    response = httpx.Response(403, headers={'x-ratelimit-remaining': '0', 'x-ratelimit-reset': '1600'})
    with patch.object(policy.time, 'time', return_value=1000), patch('httpx.Client.get', return_value=response) as get:
        with pytest.raises(HTTPException) as error:
            GitHubClient('acme/demo', 1).get()
        assert error.value.headers['Retry-After'] == '600'
        with pytest.raises(HTTPException):
            GitHubClient('another/repo', 2).get()
        assert get.call_count == 1
    with patch.object(policy.time, 'time', return_value=1601):
        policy.check({})


def test_personal_credentials_have_separate_budgets_and_are_not_stored_as_keys():
    first = {'Authorization': 'Bearer private-one'}
    second = {'Authorization': 'Bearer private-two'}
    with patch.object(policy.time, 'time', return_value=1000):
        with pytest.raises(HTTPException):
            policy.record(first, {'retry-after': '120'})
        with pytest.raises(HTTPException):
            policy.check(first)
        policy.check(second)
        policy.check({})
    assert 'private-one' not in repr(policy._cooldowns)


def test_secondary_limit_without_reset_waits_at_least_a_minute():
    with patch.object(policy.time, 'time', return_value=1000):
        with pytest.raises(HTTPException) as error:
            policy.record({}, {})
        assert error.value.headers['Retry-After'] == '60'
