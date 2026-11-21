import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';

const code = await readFile(new URL('../code.js', import.meta.url), 'utf8');
const ui = (await readFile(new URL('../ui.html', import.meta.url), 'utf8')).match(/<script>([\s\S]*)<\/script>/)[1];

function editor() {
  const messages = [];
  const timers = new Map();
  const events = new Map();
  const text = { id: '1:1', type: 'TEXT', name: 'Text', characters: 'Before',
    fontName: Symbol('mixed'), getStyledTextSegments: () => [{ characters: text.characters, start: 0, end: text.characters.length, fontSize: 16 }] };
  const instance = { id: '1:2', type: 'INSTANCE', name: 'Instance', componentProperties: {},
    get mainComponent() { throw new Error('dynamic-page mainComponent cannot be read'); } };
  const figma = {
    root: { id: '0:0', type: 'DOCUMENT', name: 'Demo', children: [
      { id: '0:1', type: 'CANVAS', name: 'Page', children: [text, instance] }] },
    ui: { postMessage: value => messages.push(value) }, showUI() {},
    async loadAllPagesAsync() { events.set('pages-loaded', true); },
    on(name, callback) { assert.equal(events.get('pages-loaded'), true); events.set(name, callback); },
  };
  vm.runInNewContext(code, { figma, __html__: '', setTimeout: fn => { const id = {}; timers.set(id, fn); return id; },
    clearTimeout: id => timers.delete(id) });
  return { figma, text, messages, events, timers };
}

test('plugin loads every page before baseline and captures mixed text styles without REST', async () => {
  const h = editor();
  await h.figma.ui.onmessage({ type: 'start' });
  const snapshot = h.messages.find(message => message.type === 'snapshot').snapshot;
  assert.equal(snapshot.document.children[0].children[0].characters, 'Before');
  assert.equal(snapshot.document.children[0].children[0].style.segments[0].fontSize, 16);
  assert.equal(snapshot.document.children[0].children[1].type, 'INSTANCE');
  assert.equal(h.messages.some(message => message.type === 'capture-error'), false);
});

test('document edits debounce and closing a connection stops later captures', async () => {
  const h = editor();
  await h.figma.ui.onmessage({ type: 'start' });
  h.messages.length = 0;
  h.text.characters = 'After';
  h.events.get('documentchange')();
  h.events.get('documentchange')();
  assert.equal(h.timers.size, 1);
  [...h.timers.values()][0]();
  assert.equal(h.messages.filter(message => message.type === 'snapshot').length, 1);
  await h.figma.ui.onmessage({ type: 'stop' });
  h.messages.length = 0;
  h.events.get('documentchange')();
  assert.equal(h.messages.length, 0);
});

function iframe() {
  const nodes = new Map();
  const calls = [];
  const elements = id => {
    if (!nodes.has(id)) nodes.set(id, { value: '', hidden: false, disabled: false, dataset: {}, textContent: '' });
    return nodes.get(id);
  };
  const window = {};
  const parent = { postMessage() {} };
  let responder = async () => ({ created: 0, baseline: true, received_at: '2026-11-21T15:00:00Z' });
  const context = {
    document: { getElementById: elements }, window, parent, Intl, Date, AbortSignal,
    setTimeout, clearTimeout,
    fetch: async (url, options) => {
      calls.push({ url, body: JSON.parse(options.body), headers: options.headers });
      const result = await responder(calls.at(-1));
      return { ok: true, json: async () => result };
    },
  };
  vm.runInNewContext(ui, context);
  return { elements, calls, parent, window, respond(fn) { responder = fn; },
    capture(text) { window.onmessage({ source: parent, data: { pluginMessage: { type: 'snapshot', snapshot: {
      name: 'Demo', document: { type: 'DOCUMENT', name: text },
    } } } }); } };
}

const settle = () => new Promise(resolve => setImmediate(resolve));
async function pairIframe(h) {
  h.elements('code').value = 'one-time-code';
  h.elements('file-url').value = 'https://www.figma.com/design/FILE123/Test';
  h.respond(async () => ({ token: 'scoped-token', project_name: 'Demo' }));
  await h.elements('pair-form').onsubmit({ preventDefault() {} });
}

test('plugin upload queue serializes snapshots and always uses increasing sequence numbers', async () => {
  const h = iframe();
  await pairIframe(h);
  let release;
  h.respond(() => new Promise(resolve => { release = resolve; }));
  h.capture('Before');
  h.capture('After');
  assert.equal(h.calls.length, 2); // Pair plus only one upload in flight.
  h.respond(async () => ({ created: 1, baseline: false, received_at: '2026-11-21T15:00:01Z' }));
  release({ created: 0, baseline: true, received_at: '2026-11-21T15:00:00Z' });
  await settle();
  assert.deepEqual(h.calls.slice(1).map(call => call.body.sequence), [1, 2]);
  assert.equal(h.calls[2].body.document.name, 'After');
  assert.ok(h.calls.every(call => call.url.startsWith('https://fastapi-practice-jwse.onrender.com/api/figma-plugin/')));
  assert.equal(h.calls[1].headers.Authorization, 'Bearer scoped-token');
});

test('a failed upload retries the same sequence before sending newer contents', async () => {
  const h = iframe();
  await pairIframe(h);
  h.respond(async () => { throw new Error('network failed'); });
  h.capture('Before');
  await settle();
  h.respond(async () => ({ created: 0, baseline: false, received_at: '2026-11-21T15:00:00Z' }));
  h.capture('After');
  await settle();
  assert.deepEqual(h.calls.slice(1).map(call => call.body.sequence), [1, 1, 2]);
  assert.equal(h.calls[2].body.document.name, 'Before');
  assert.equal(h.calls[3].body.document.name, 'After');
});
