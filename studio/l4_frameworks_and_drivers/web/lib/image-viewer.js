import {openSheet} from './sheet.js';
import {t} from './i18n.js';

function clamp(value, minimum, maximum) {
  return Math.min(maximum, Math.max(minimum, value));
}

function viewerButton(action, text, label) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'btn quiet';
  button.dataset.zoomAction = action;
  button.textContent = text;
  button.setAttribute('aria-label', label);
  return button;
}

export function zoomControls(prefix) {
  const tools = document.createElement('div');
  tools.className = prefix + '-tools';
  const output = document.createElement('output');
  output.className = prefix + '-scale num';
  output.setAttribute('aria-label', t('image.viewer.level'));
  output.setAttribute('aria-live', 'off');
  const steps = document.createElement('div');
  steps.className = 'image-zoom-steps';
  steps.append(viewerButton('out', '−', t('image.viewer.out')), viewerButton('in', '+', t('image.viewer.in')));
  const level = document.createElement('div');
  level.className = 'image-zoom-level';
  level.append(output, viewerButton('fit', t('image.viewer.fit'), t('image.viewer.fitLabel')),
    viewerButton('actual', '100%', t('image.viewer.actual')));
  tools.append(steps, level);
  return tools;
}

export function bindImageZoom(viewport, image, tools, hint, preview = null) {
  const pointers = new Map();
  const listeners = [];
  const output = tools?.querySelector('output');
  const picture = preview?.picture || image;
  const state = {scale: 1, left: 0, top: 0, width: 0, height: 0, ...preview?.state};
  const origin = {left: 0, top: 0};
  let renderedLeft = 0;
  let renderedTop = 0;
  let ownsGesture = false;
  let pinch = null;
  let tap = null;
  let lastTap = null;
  let lastTouch = -1000;
  let initialSplit = null;
  const comparison = preview?.comparing ? picture.querySelector('.compare-range') : null;

  function maximum() { return Math.max(8, image.naturalWidth * 8 / state.width || 1); }

  function listen(node, name, handler, options) {
    if (!node) return;
    node.addEventListener(name, handler, options);
    listeners.push(() => node.removeEventListener(name, handler, options));
  }

  function stopEvent(event) {
    event.preventDefault();
    if (preview) event.stopPropagation();
  }

  function draw() {
    if (!state.width || !image.naturalWidth) return;
    const horizontal = Math.max(0, (state.width * state.scale - viewport.clientWidth) / 2);
    const vertical = Math.max(0, (state.height * state.scale - viewport.clientHeight) / 2);
    const bounds = viewport.getBoundingClientRect();
    const shiftLeft = origin.left - bounds.left - bounds.width / 2;
    const shiftTop = origin.top - bounds.top - bounds.height / 2;
    state.left = horizontal ? clamp(state.left, -horizontal - shiftLeft, horizontal - shiftLeft) : 0;
    state.top = vertical ? clamp(state.top, -vertical - shiftTop, vertical - shiftTop) : 0;
    viewport.style.setProperty('--viewer-scale', state.scale);
    viewport.style.setProperty('--viewer-inverse', 1 / state.scale);
    viewport.style.setProperty('--viewer-x', state.left + 'px');
    viewport.style.setProperty('--viewer-y', state.top + 'px');
    viewport.classList.toggle('zoomed', state.scale > 1.001);
    renderedLeft = state.left;
    renderedTop = state.top;
    if (tools) {
      output.textContent = Math.round(state.scale * state.width / image.naturalWidth * 100) + '%';
      tools.querySelector('[data-zoom-action="out"]').disabled = state.scale <= 1.001;
      tools.querySelector('[data-zoom-action="in"]').disabled = state.scale >= maximum() - .001;
      tools.querySelector('[data-zoom-action="fit"]').setAttribute('aria-pressed', String(state.scale <= 1.001));
      tools.querySelector('[data-zoom-action="actual"]').setAttribute('aria-pressed',
        String(Math.abs(state.scale * state.width - image.naturalWidth) < 1));
    }
    if (!preview) return;
    const key = preview.brush ? 'image.preview.brushHelp' : preview.comparing
      ? 'image.preview.compareHelp' : state.scale > 1.001 ? 'image.preview.panHelp' : 'image.preview.help';
    hint.textContent = t(key);
  }

  function fit() {
    if (!image.naturalWidth || !viewport.clientWidth || !viewport.clientHeight) return;
    const fitted = state.scale <= 1.001;
    const displayedWidth = state.scale * state.width;
    if (preview) {
      state.width = picture.clientWidth;
      state.height = picture.clientHeight;
    } else {
      const ratio = image.naturalWidth / image.naturalHeight;
      state.width = Math.max(1, Math.min(image.naturalWidth, viewport.clientWidth - 32,
        (viewport.clientHeight - 32) * ratio));
      state.height = state.width / ratio;
      image.style.width = state.width + 'px';
      image.style.height = state.height + 'px';
    }
    if (!state.width || !state.height) return;
    const bounds = picture.getBoundingClientRect();
    origin.left = bounds.left + bounds.width / 2 - renderedLeft;
    origin.top = bounds.top + bounds.height / 2 - renderedTop;
    state.scale = fitted ? 1 : clamp(displayedWidth / state.width, 1, maximum());
    draw();
  }

  function zoom(next, anchor = {left: 0, top: 0}) {
    if (!state.width || !image.naturalWidth) return;
    const scale = clamp(next, 1, maximum());
    const factor = scale / state.scale;
    state.left = anchor.left - (anchor.left - state.left) * factor;
    state.top = anchor.top - (anchor.top - state.top) * factor;
    state.scale = scale;
    draw();
  }

  function position(event) {
    return {left: event.clientX - origin.left, top: event.clientY - origin.top};
  }

  function pair() {
    const [first, second] = [...pointers.values()];
    return {left: (first.left + second.left) / 2, top: (first.top + second.top) / 2,
      distance: Math.max(1, Math.hypot(first.left - second.left, first.top - second.top))};
  }

  function press(event) {
    if (preview?.brush) return;
    if (pointers.size >= 2 || (event.pointerType === 'mouse' && event.button !== 0)) return;
    if (!pointers.size) initialSplit = comparison?.value ?? null;
    pointers.set(event.pointerId, position(event));
    if (pointers.size === 1) ownsGesture = !preview || (state.scale > 1.001 && !preview.comparing);
    if (pointers.size === 2) ownsGesture = true;
    if (ownsGesture) {
      stopEvent(event);
      viewport.focus({preventScroll: true});
      for (const id of pointers.keys()) viewport.setPointerCapture(id);
    }
    tap = {id: event.pointerId, left: event.clientX, top: event.clientY, at: performance.now()};
    if (pointers.size !== 2) return;
    if (comparison && initialSplit !== null) {
      comparison.value = initialSplit;
      comparison.dispatchEvent(new Event('input', {bubbles: true}));
    }
    tap = null;
    lastTap = null;
    pinch = {...pair(), scale: state.scale, offsetLeft: state.left, offsetTop: state.top};
  }

  function move(event) {
    const previous = pointers.get(event.pointerId);
    if (!previous) return;
    const current = position(event);
    pointers.set(event.pointerId, current);
    if (tap && Math.hypot(event.clientX - tap.left, event.clientY - tap.top) > 8) {
      if (pointers.size === 1) initialSplit = null;
      tap = null;
      lastTap = null;
    }
    if (pointers.size === 1) {
      if (!ownsGesture) return;
      stopEvent(event);
      state.left += current.left - previous.left;
      state.top += current.top - previous.top;
      draw();
      return;
    }
    stopEvent(event);
    const currentPair = pair();
    const scale = clamp(pinch.scale * currentPair.distance / pinch.distance, 1, maximum());
    state.left = currentPair.left - (pinch.left - pinch.offsetLeft) * scale / pinch.scale;
    state.top = currentPair.top - (pinch.top - pinch.offsetTop) * scale / pinch.scale;
    state.scale = scale;
    draw();
  }

  function release(event) {
    if (!pointers.has(event.pointerId)) return;
    if (ownsGesture) stopEvent(event);
    pointers.delete(event.pointerId);
    if (!pointers.size) ownsGesture = false;
    pinch = null;
    if (event.pointerType !== 'touch') { tap = null; return; }
    lastTouch = performance.now();
    if (!tap || event.type === 'pointercancel' || lastTouch - tap.at > 350) {
      tap = null;
      lastTap = null;
      return;
    }
    const repeated = lastTap && lastTouch - lastTap.at < 320
      && Math.hypot(event.clientX - lastTap.left, event.clientY - lastTap.top) < 24;
    if (repeated) zoom(state.scale > 1.001 ? 1 : 2, position(event));
    lastTap = repeated ? null : {left: event.clientX, top: event.clientY, at: lastTouch};
    tap = null;
  }

  function key(event) {
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    if (event.target.closest('input, textarea, .region-mark')) return;
    const steps = {ArrowLeft: [40, 0], ArrowRight: [-40, 0], ArrowUp: [0, 40], ArrowDown: [0, -40]};
    const step = steps[event.key];
    if (step) {
      if (preview && (state.scale <= 1.001 || preview.comparing || preview.brush)) return;
      state.left += step[0];
      state.top += step[1];
      draw();
    } else if (event.key === '+' || event.key === '=') zoom(state.scale * 1.5);
    else if (event.key === '-') zoom(state.scale / 1.5);
    else if (event.key === '0' || event.key === 'Home') zoom(1);
    else return;
    event.preventDefault();
  }

  listen(tools, 'click', event => {
    const action = event.target.closest('[data-zoom-action]')?.dataset.zoomAction;
    if (action === 'in') zoom(state.scale * 1.5);
    if (action === 'out') zoom(state.scale / 1.5);
    if (action === 'fit') zoom(1);
    if (action === 'actual') zoom(image.naturalWidth / state.width);
  });
  listen(viewport, 'pointerdown', press, true);
  listen(viewport, 'pointermove', move, true);
  listen(viewport, 'pointerup', release, true);
  listen(viewport, 'pointercancel', release, true);
  listen(viewport, 'lostpointercapture', event => {
    if (event.target !== viewport) return;
    if (!pointers.delete(event.pointerId)) return;
    pinch = null;
    tap = null;
    lastTap = null;
  });
  listen(viewport, 'wheel', event => {
    if (preview?.brush) return;
    stopEvent(event);
    zoom(state.scale * Math.exp(-event.deltaY * .002), position(event));
  }, {passive: false});
  listen(viewport, 'dblclick', event => {
    if (preview?.brush) return;
    stopEvent(event);
    if (performance.now() - lastTouch < 600) return;
    zoom(state.scale > 1.001 ? 1 : 2, position(event));
  });
  listen(viewport, 'keydown', key);
  listen(tools, 'keydown', key);
  listen(image, 'load', fit);
  listen(image, 'error', () => {
    hint.textContent = t('image.viewer.error');
    hint.classList.remove('sr-only');
    tools?.querySelectorAll('button').forEach(button => { button.disabled = true; });
  });
  const observer = preview ? null : new ResizeObserver(fit);
  observer?.observe(viewport);
  fit();
  return {
    fit,
    snapshot: () => ({...state}),
    dispose: () => {
      observer?.disconnect();
      pointers.clear();
      listeners.forEach(remove => remove());
      viewport.classList.remove('zoomed');
      ['--viewer-scale', '--viewer-inverse', '--viewer-x', '--viewer-y'].forEach(name => viewport.style.removeProperty(name));
    },
  };
}

export function openImageViewer(entry, trigger) {
  const content = document.createElement('div');
  content.className = 'image-viewer-content';
  const tools = zoomControls('image-viewer');
  const viewport = document.createElement('div');
  viewport.className = 'image-viewer-viewport';
  viewport.tabIndex = 0;
  viewport.setAttribute('role', 'group');
  viewport.setAttribute('aria-label', t('image.viewer.surface'));
  viewport.setAttribute('aria-describedby', 'image-viewer-help');
  const image = document.createElement('img');
  image.className = 'image-viewer-image';
  image.alt = entry.prompt;
  image.draggable = false;
  viewport.append(image);
  const hint = document.createElement('p');
  hint.className = 'image-viewer-help sr-only';
  hint.id = 'image-viewer-help';
  hint.textContent = t('image.viewer.help');
  content.append(viewport, hint);
  let controller = null;
  const dialog = openSheet({id: 'image-viewer', title: t('image.viewer.title'), body: content,
    closeLabel: t('guide.sheet.close'), className: 'image-viewer-sheet',
    onClose: () => { controller?.dispose(); if (trigger?.isConnected) trigger.focus(); }});
  const header = dialog.querySelector('.sheet-head');
  header.querySelector('h2').remove();
  header.prepend(tools);
  header.querySelector('.control-label').remove();
  controller = bindImageZoom(viewport, image, tools, hint);
  image.src = entry.src;
}
