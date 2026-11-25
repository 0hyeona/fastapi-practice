"""Process-local cooldown by credential. No access tokens are retained as keys."""
import hashlib
import math
import threading
import time
from collections import OrderedDict
from email.utils import parsedate_to_datetime

from fastapi import HTTPException

_cooldowns = OrderedDict()
_lock = threading.Lock()


def credential_key(headers):
    return hashlib.sha256(headers.get('Authorization', 'anonymous').encode()).hexdigest()


def limited(until):
    seconds = max(1, math.ceil(until - time.time()))
    return HTTPException(503, f'GitHub 요청 한도를 초과했습니다. 약 {math.ceil(seconds / 60)}분 뒤 다시 시도하세요. GitHub로 로그인하면 개인 인증 한도를 사용할 수 있어요.',
                         headers={'Retry-After': str(seconds), 'X-RateLimit-Reset': str(math.ceil(until))})


def check(headers):
    key = credential_key(headers)
    with _lock:
        until = _cooldowns.get(key, 0)
        if until <= time.time():
            _cooldowns.pop(key, None)
            return
    raise limited(until)


def record(headers, response_headers):
    now = time.time()
    until = now + 60
    retry = response_headers.get('retry-after', '')
    if retry.isdigit():
        until = max(until, now + int(retry))
    elif retry:
        try:
            until = max(until, parsedate_to_datetime(retry).timestamp())
        except (ValueError, TypeError, OverflowError):
            pass
    reset = response_headers.get('x-ratelimit-reset', '')
    if response_headers.get('x-ratelimit-remaining') == '0' and reset.isdigit():
        until = max(until, int(reset))
    # Bound both memory and malformed upstream reset values.
    until = min(until, now + 86400)
    with _lock:
        key = credential_key(headers)
        _cooldowns[key] = max(_cooldowns.get(key, 0), until)
        _cooldowns.move_to_end(key)
        while len(_cooldowns) > 512:
            _cooldowns.popitem(last=False)
    raise limited(until)
