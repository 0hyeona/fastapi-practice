import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const ts = require('typescript');
const moduleUrl = source => 'data:text/javascript;base64,' + Buffer.from(ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText).toString('base64');
const react = moduleUrl(`
export const useState = (...args) => globalThis.__figmaRefreshTest.useState(...args);
export const useRef = (...args) => globalThis.__figmaRefreshTest.useRef(...args);
export const useCallback = fn => fn;
export const useEffect = () => {};
`);
const api = moduleUrl(`
export const loadExternalActivities = (...args) => globalThis.__figmaRefreshTest.load(...args);
export const refreshFigmaPage = (...args) => globalThis.__figmaRefreshTest.sync(...args);
`);
const data = moduleUrl(`export const replaceServiceChanges = (project, service, incoming) => ({...project, changes: incoming});`);
// This test is stored beside the hook in the handoff folder, or under tests/ in the frontend.
const hookFile = new URL(import.meta.url.includes('/tests/') ? '../src/state/useFigmaActivities.ts' : './useFigmaActivities.ts', import.meta.url);
const source = (await readFile(hookFile, 'utf8')).replace("'react'", JSON.stringify(react))
  .replace("'../api/externalActivities'", JSON.stringify(api)).replace("'../data/activity'", JSON.stringify(data));
const { useFigmaActivities } = await import(moduleUrl(source));

function harness() {
  const slots = [];
  let index = 0;
  let projects = [{ id: '7', urls: { Figma: 'https://figma.com/design/ABC/Test' }, changes: [] }];
  const h = {
    load: async () => [], sync: async () => ({ nextCursor: null }),
    useState(initial) {
      const slot = index++;
      if (!(slot in slots)) slots[slot] = typeof initial === 'function' ? initial() : initial;
      return [slots[slot], update => { slots[slot] = typeof update === 'function' ? update(slots[slot]) : update; }];
    },
    useRef(initial) {
      const slot = index++;
      if (!(slot in slots)) slots[slot] = { current: initial };
      return slots[slot];
    },
    render(project = projects[0], userId = 2) {
      globalThis.__figmaRefreshTest = h;
      index = 0;
      return useFigmaActivities(userId, project, update => { projects = update(projects); });
    },
    get projects() { return projects; },
  };
  return h;
}

test('provider waiting never blocks cached refresh or displays a countdown', async () => {
  const h = harness();
  let reads = 0, syncs = 0;
  h.load = async () => [{ title: 'Cached ' + ++reads }];
  h.sync = async () => { syncs++; return { message: 'rate limited', retryAt: Date.now() + 60000 }; };
  await h.render().refresh();
  let view = h.render();
  assert.equal(view.refreshDisabled, false);
  assert.equal(view.retryAt, undefined);
  assert.equal(view.notice, undefined);
  await view.refresh();
  assert.equal(reads, 2);
  assert.equal(syncs, 1);
  assert.equal(h.projects[0].changes[0].title, 'Cached 2');
});

test('successful refresh displays cached records first then new records and requests newest page', async () => {
  const h = harness();
  const sequence = [];
  h.load = async () => { sequence.push('read'); return [{ title: sequence.length === 1 ? 'Cached' : 'Fresh' }]; };
  h.sync = async (id, cursor) => { sequence.push('sync'); assert.equal(id, '7'); assert.equal(cursor, null); return { nextCursor: 'older-page' }; };
  await h.render().refresh();
  assert.deepEqual(sequence, ['read', 'sync', 'read']);
  assert.equal(h.projects[0].changes[0].title, 'Fresh');
  assert.equal(h.render().hasMore, false);
});

test('duplicate clicks do not launch overlapping provider requests', async () => {
  const h = harness();
  let resolve, calls = 0;
  h.sync = () => { calls++; return new Promise(done => { resolve = done; }); };
  const first = h.render().refresh();
  await Promise.resolve(); await Promise.resolve();
  await h.render().refresh();
  assert.equal(calls, 1);
  resolve({ nextCursor: null });
  await first;
});

test('provider deadline is scoped to user, project and file', async () => {
  const h = harness();
  let calls = 0;
  h.sync = async () => { calls++; return { message: 'limited', retryAt: Date.now() + 60000 }; };
  await h.render().refresh();
  await h.render({ id: '7', urls: { Figma: 'https://figma.com/design/OTHER/Test' } }).refresh();
  assert.equal(calls, 2);
});

test('real connection errors remain visible while cached records survive', async () => {
  const h = harness();
  h.load = async () => [{ title: 'Cached' }];
  h.sync = async () => { throw new Error('Connection unavailable'); };
  await h.render().refresh();
  assert.equal(h.projects[0].changes[0].title, 'Cached');
  assert.equal(h.render().error, 'Connection unavailable');
  assert.equal(h.render().refreshDisabled, false);
});
