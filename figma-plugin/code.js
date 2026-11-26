/* Plain JavaScript: Figma runs this file directly, without npm or a build. */
figma.showUI(__html__, { width: 390, height: 540, themeColors: true });

const FIELDS = [
  'name', 'type', 'characters', 'fills', 'strokes', 'strokeWeight', 'cornerRadius',
  'rectangleCornerRadii', 'opacity', 'visible', 'effects', 'layoutMode', 'itemSpacing',
  'paddingLeft', 'paddingRight', 'paddingTop', 'paddingBottom',
  'primaryAxisAlignItems', 'counterAxisAlignItems', 'componentProperties',
  'rotation', 'constraints',
];
const TEXT_FIELDS = [
  'fontName', 'fontSize', 'textCase', 'textDecoration', 'letterSpacing', 'lineHeight',
  'textAlignHorizontal', 'textAlignVertical', 'paragraphSpacing', 'paragraphIndent',
];
let active = false;
let listening = false;
let timer;
let dirty = new Set();
let deleted = new Set();
const parents = new Map();
let capturing = false;
let fullRequired = false;
let storageKey;

function plain(value) {
  if (typeof value === 'symbol' || value === undefined) return undefined;
  return JSON.parse(JSON.stringify(value));
}

function nodeSnapshot(node) {
    const result = { id: node.id };
    for (const field of FIELDS) {
      if (!(field in node)) continue;
      const value = plain(node[field]);
      if (value !== undefined) result[field] = value;
    }
    if (node.type === 'TEXT') {
      result.style = {};
      for (const field of TEXT_FIELDS) {
        const value = plain(node[field]);
        if (value !== undefined) result.style[field] = value;
      }
      // Mixed ranges need their own styles; a node-wide `mixed` value loses edits.
      result.style.segments = plain(node.getStyledTextSegments([
        'fontName', 'fontSize', 'textCase', 'textDecoration', 'letterSpacing', 'lineHeight', 'fills',
      ]));
    }
    const styles = {};
    for (const [property, label] of [['fillStyleId', 'fill'], ['strokeStyleId', 'stroke'],
      ['textStyleId', 'text'], ['effectStyleId', 'effect']]) {
      const value = property in node ? plain(node[property]) : undefined;
      if (value !== undefined) styles[label] = value;
    }
    if (Object.keys(styles).length) result.styles = styles;
    if ('width' in node) result.size = [node.width, node.height];
    if ('x' in node) result.position = [node.x, node.y];
    result.parent = node.parent ? node.parent.id : null;
    parents.set(node.id, result.parent);
    result.children = 'children' in node ? node.children.map(child => child.id) : [];
    return result;
}

function documentSnapshot() {
  let count = 0;
  function visit(node, depth) {
    if (++count > 100000 || depth > 100) throw new Error('파일이 너무 크거나 요소가 너무 깊게 중첩되어 있어요.');
    const result = nodeSnapshot(node);
    result.children = 'children' in node ? node.children.map(child => visit(child, depth + 1)) : [];
    return result;
  }
  return { name: figma.root.name.slice(0, 255), document: visit(figma.root, 0) };
}

function capture() {
  if (!active) return;
  try {
    dirty.clear(); deleted.clear(); fullRequired = false; parents.clear();
    const snapshot = documentSnapshot();
    const size = JSON.stringify(snapshot).length;
    // The UI measures the complete UTF-8 request and compresses it before upload.
    if (size > 32 * 1024 * 1024) throw new Error('디자인 데이터가 압축 전 한도 32 MiB를 초과했어요.');
    figma.ui.postMessage({ type: 'snapshot', snapshot });
  } catch (error) {
    figma.ui.postMessage({ type: 'capture-error', message: error.message || '파일을 완전히 읽지 못했어요.' });
  }
}

function changed(event) {
  if (!active) return;
  for (const change of event.documentChanges) {
    dirty.add(change.id);
    const oldParent = parents.get(change.id);
    if (oldParent) dirty.add(oldParent);
    if (change.type === 'DELETE') deleted.add(change.id);
  }
  if (dirty.size + deleted.size > 100000) {
    fullRequired = true; dirty.clear(); deleted.clear();
  }
  figma.ui.postMessage({ type: 'changed' });
}

async function delta() {
  if (active && fullRequired) {
    fullRequired = false; dirty.clear(); deleted.clear(); capture(); return;
  }
  if (!active || capturing || (!dirty.size && !deleted.size)) {
    figma.ui.postMessage({ type: 'idle' }); return;
  }
  capturing = true;
  const ids = dirty; const removed = deleted;
  dirty = new Set(); deleted = new Set();
  try {
    const nodes = new Map();
    function add(node, subtree) {
      if (nodes.size >= 100000) throw new Error('변경 요소가 너무 많아요. 보완 수집을 다시 실행하세요.');
      nodes.set(node.id, nodeSnapshot(node));
      if (node.parent && !nodes.has(node.parent.id)) nodes.set(node.parent.id, nodeSnapshot(node.parent));
      if (subtree && 'children' in node) for (const child of node.children) add(child, true);
    }
    for (const id of ids) {
      const node = await figma.getNodeByIdAsync(id);
      if (node && !node.removed) {
        const isNew = !parents.has(id);
        add(node, isNew);
        removed.delete(id);
      } else removed.add(id);
    }
    for (const id of removed) parents.delete(id);
    figma.ui.postMessage({ type: 'delta', delta: {
      name: figma.root.name.slice(0, 255), upserts: [...nodes.values()], deleted: [...removed],
    } });
  } catch (error) {
    for (const id of ids) dirty.add(id);
    for (const id of removed) deleted.add(id);
    figma.ui.postMessage({ type: 'capture-error', message: error.message });
  } finally { capturing = false; }
}

figma.ui.onmessage = async message => {
  if (message.type === 'ready') {
    try {
      // Only a non-secret scope ID lives in the document; credentials stay local.
      let scope = figma.root.getPluginData('moeum-local-scope');
      if (!scope) {
        scope = Date.now().toString(36) + Math.random().toString(36).slice(2);
        figma.root.setPluginData('moeum-local-scope', scope);
      }
      storageKey = 'moeum-auto-v1:' + (figma.fileKey || scope);
      const stored = await figma.clientStorage.getAsync(storageKey);
      figma.ui.postMessage({ type: 'restored', stored, fileKey: figma.fileKey || null, name: figma.root.name });
    } catch (error) { figma.ui.postMessage({ type: 'capture-error', message: '연결 정보를 읽지 못했어요: ' + error.message }); }
  } else if (message.type === 'persist') {
    try {
      if (message.stored) await figma.clientStorage.setAsync(storageKey, message.stored);
      else await figma.clientStorage.deleteAsync(storageKey);
      figma.ui.postMessage({ type: 'persisted', requestId: message.requestId });
    } catch (error) { figma.ui.postMessage({ type: 'persisted', requestId: message.requestId, error: '기기 저장 공간을 확인하세요.' }); }
  } else if (message.type === 'start') {
    try {
      active = true;
      figma.ui.postMessage({ type: 'loading' });
      figma.skipInvisibleInstanceChildren = false;
      await figma.loadAllPagesAsync();
      if (!active) return;
      if (!listening) {
        figma.on('documentchange', changed);
        listening = true;
      }
      capture();
    } catch (error) {
      figma.ui.postMessage({ type: 'capture-error', message: error.message || '페이지를 읽지 못했어요.' });
    }
  } else if (message.type === 'capture') {
    clearTimeout(timer);
    dirty.clear(); deleted.clear();
    capture();
  } else if (message.type === 'delta') {
    await delta();
  } else if (message.type === 'stop') {
    active = false;
    clearTimeout(timer);
  }
};

figma.ui.postMessage({ type: 'file', name: figma.root.name });
