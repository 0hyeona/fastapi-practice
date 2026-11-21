/* Plain JavaScript: Figma runs this file directly, without npm or a build. */
figma.showUI(__html__, { width: 390, height: 540, themeColors: true });

const FIELDS = [
  'name', 'type', 'characters', 'fills', 'strokes', 'strokeWeight', 'cornerRadius',
  'rectangleCornerRadii', 'opacity', 'visible', 'effects', 'layoutMode', 'itemSpacing',
  'paddingLeft', 'paddingRight', 'paddingTop', 'paddingBottom',
  'primaryAxisAlignItems', 'counterAxisAlignItems', 'componentProperties',
  'rotation', 'constraints', 'absoluteBoundingBox',
];
const TEXT_FIELDS = [
  'fontName', 'fontSize', 'textCase', 'textDecoration', 'letterSpacing', 'lineHeight',
  'textAlignHorizontal', 'textAlignVertical', 'paragraphSpacing', 'paragraphIndent',
];
let active = false;
let listening = false;
let timer;

function plain(value) {
  if (typeof value === 'symbol' || value === undefined) return undefined;
  return JSON.parse(JSON.stringify(value));
}

function documentSnapshot() {
  let count = 0;
  function visit(node, depth) {
    if (++count > 100000 || depth > 100) throw new Error('파일이 너무 크거나 요소가 너무 깊게 중첩되어 있어요.');
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
    if ('children' in node) result.children = node.children.map(child => visit(child, depth + 1));
    return result;
  }
  return { name: figma.root.name.slice(0, 255), document: visit(figma.root, 0) };
}

function capture() {
  if (!active) return;
  try {
    const snapshot = documentSnapshot();
    const size = JSON.stringify(snapshot).length;
    if (size > 4 * 1024 * 1024) throw new Error('파일 전송 크기를 초과했어요. 기존 변경사항은 유지돼요.');
    figma.ui.postMessage({ type: 'snapshot', snapshot });
  } catch (error) {
    figma.ui.postMessage({ type: 'capture-error', message: error.message || '파일을 완전히 읽지 못했어요.' });
  }
}

function changed() {
  if (!active) return;
  clearTimeout(timer);
  timer = setTimeout(capture, 1000);
  figma.ui.postMessage({ type: 'changed' });
}

figma.ui.onmessage = async message => {
  if (message.type === 'start') {
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
    capture();
  } else if (message.type === 'stop') {
    active = false;
    clearTimeout(timer);
  }
};

figma.ui.postMessage({ type: 'file', name: figma.root.name });
