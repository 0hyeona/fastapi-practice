import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';

const moduleUrl = source => 'data:text/javascript;base64,' + Buffer.from(ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText).toString('base64');
let sequence = 0;

async function fixture(t, handler) {
  const saved = { fetch: globalThis.fetch, window: globalThis.window,
    storage: globalThis.sessionStorage, token: globalThis.notionTestToken };
  const storage = new Map();
  const redirects = [];
  const calls = [];
  globalThis.notionTestToken = 'moeum-login';
  globalThis.window = { location: { origin: 'http://127.0.0.1:5173', assign: url => redirects.push(url) } };
  globalThis.sessionStorage = {
    getItem: key => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, value),
    removeItem: key => storage.delete(key),
  };
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    assert.equal(new Headers(options.headers).get('Authorization'), 'Bearer moeum-login');
    assert.equal(options.cache, 'no-store');
    return handler(url, options);
  };
  t.after(() => {
    globalThis.fetch = saved.fetch;
    globalThis.window = saved.window;
    globalThis.sessionStorage = saved.storage;
    globalThis.notionTestToken = saved.token;
  });
  const client = moduleUrl((await readFile(new URL('../src/api/client.ts', import.meta.url), 'utf8'))
    .replaceAll('import.meta.env.DEV', 'true'));
  const auth = moduleUrl('export const getAccessToken = () => globalThis.notionTestToken;');
  const source = (await readFile(new URL('../src/api/notion.ts', import.meta.url), 'utf8'))
    .replace("'./client'", JSON.stringify(client)).replace("'./auth'", JSON.stringify(auth));
  const api = await import(moduleUrl(source + `\n// instance ${++sequence}`));
  return { api, storage, redirects, calls };
}

const state = 'a'.repeat(43);
const status = { connected: true, workspace_id: 'workspace', workspace_name: 'My Notes' };
const json = (body, code = 200) => new Response(JSON.stringify(body), { status: code });
const authorize = (callback = 'http://127.0.0.1:5173/auth/notion/callback') => ({
  authorization_url: 'https://api.notion.com/v1/oauth/authorize?' + new URLSearchParams({
    state, redirect_uri: callback, owner: 'user', response_type: 'code', client_id: 'client',
  }),
});

test('approval starts with login authentication and retains a safe return path', async t => {
  const { api, storage, redirects } = await fixture(t, (url, options) => {
    assert.equal(url, '/backend/api/integrations/notion/authorize');
    assert.equal(options.method, 'POST');
    return json(authorize());
  });
  await api.startNotionConnection('/dashboard');
  assert.equal(redirects.length, 1);
  assert.equal(new URL(redirects[0]).hostname, 'api.notion.com');
  assert.deepEqual(JSON.parse(storage.get('moeum.notion.pending')), { state, returnTo: '/dashboard' });
  assert.ok(!JSON.stringify([...storage]).includes('moeum-login'));
});

test('missing login does not start an authorization request', async t => {
  const { api, calls } = await fixture(t, () => { throw new Error('must not request'); });
  globalThis.notionTestToken = null;
  await assert.rejects(api.startNotionConnection(), /로그인/);
  assert.equal(calls.length, 0);
});

test('another callback origin is rejected before navigation and pending storage', async t => {
  const { api, redirects, storage } = await fixture(t, () => json(authorize('http://localhost:5173/auth/notion/callback')));
  await assert.rejects(api.startNotionConnection(), /콜백 주소/);
  assert.equal(redirects.length, 0);
  assert.equal(storage.size, 0);
});

test('an untrusted authorization host is rejected', async t => {
  const { api, redirects } = await fixture(t, () => json({ authorization_url: 'https://evil.example/v1/oauth/authorize' }));
  await assert.rejects(api.startNotionConnection(), /승인 주소/);
  assert.equal(redirects.length, 0);
});

test('StrictMode exchanges a callback only once, then clears pending state', async t => {
  const { api, storage, calls } = await fixture(t, (url, options) => {
    assert.equal(url, '/backend/api/integrations/notion/exchange');
    assert.deepEqual(JSON.parse(options.body), { code: 'one-use-code', state });
    return json(status);
  });
  storage.set('moeum.notion.pending', JSON.stringify({ state, returnTo: '/settings#notion-account' }));
  const query = '?' + new URLSearchParams({ code: 'one-use-code', state });
  const first = api.completeNotionConnection(query);
  assert.equal(first, api.completeNotionConnection(query));
  assert.deepEqual(await first, { returnTo: '/settings#notion-account' });
  assert.equal(calls.length, 1);
  assert.equal(storage.size, 0);
});

test('mismatched callback state is blocked before sending the code', async t => {
  const { api, storage, calls } = await fixture(t, () => { throw new Error('must not request'); });
  storage.set('moeum.notion.pending', JSON.stringify({ state: 'different' }));
  await assert.rejects(api.completeNotionConnection(`?code=code&state=${state}`), /연결 요청/);
  assert.equal(calls.length, 0);
});

test('user cancellation clears pending state without exchanging a code', async t => {
  const { api, storage, calls } = await fixture(t, () => { throw new Error('must not request'); });
  storage.set('moeum.notion.pending', JSON.stringify({ state }));
  await assert.rejects(api.completeNotionConnection('?error=access_denied'), /취소/);
  assert.equal(calls.length, 0);
  assert.equal(storage.size, 0);
});

test('failed code exchange is not retried with an already consumed state', async t => {
  const { api, storage, calls } = await fixture(t, () => json({ detail: '연결 승인부터 다시 진행해 주세요.' }, 502));
  storage.set('moeum.notion.pending', JSON.stringify({ state }));
  const query = `?code=code&state=${state}`;
  await assert.rejects(api.completeNotionConnection(query), /다시 진행/);
  await assert.rejects(api.completeNotionConnection(query), /다시 진행/);
  assert.equal(calls.length, 1);
  assert.equal(storage.size, 0);
});

test('external return destinations cannot redirect a successful connection off-site', async t => {
  const { api, storage } = await fixture(t, () => json(status));
  storage.set('moeum.notion.pending', JSON.stringify({ state, returnTo: 'https://evil.example/' }));
  assert.deepEqual(await api.completeNotionConnection(`?code=code&state=${state}`), { returnTo: '/settings#notion-account' });
});

test('connection status reads metadata without persisting a Notion token', async t => {
  const { api, storage } = await fixture(t, url => {
    assert.equal(url, '/backend/api/integrations/notion');
    return json(status);
  });
  assert.deepEqual(await api.getNotionConnection(), status);
  assert.equal(storage.size, 0);
});
