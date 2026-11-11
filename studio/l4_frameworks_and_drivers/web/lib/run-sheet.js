// The run sheet: what the page sent, while the operation still goes.
//
// Every workspace shows a Details action on its generating card. They all open
// this sheet, so a run reads the same in Image, Video, Voice and Music. The rows
// come from the request the page sent, never from server state: a private run
// shows only what its own caller wrote, and nothing about another caller's run
// can reach it.
//
// The live block refreshes while the sheet is open. The result's own facts, the
// duration, the output size and the final hash, stay with the finished entry,
// which is the only place that can prove them.

import {t} from './i18n.js';
import {openSheet} from './sheet.js';

const LABELS = {
  model: 'run.field.model',
  mode: 'run.field.mode',
  prompt: 'run.field.prompt',
  negative: 'run.field.negative',
  size: 'run.field.size',
  steps: 'run.field.steps',
  guidance: 'run.field.guidance',
  seed: 'run.field.seed',
  references: 'run.field.references',
  style: 'run.field.style',
  lyrics: 'run.field.lyrics',
  planning: 'run.field.planning',
  text: 'run.field.text',
  instruction: 'run.field.instruction',
  voice: 'run.field.voice',
  seconds: 'run.field.seconds',
  template: 'run.field.template',
  reference: 'run.field.reference',
  frames: 'run.field.frames',
  duration: 'run.field.duration',
  look: 'run.field.look',
  pipeline: 'run.field.pipeline',
  count: 'run.field.count',
};

function shown(value) {
  return value !== undefined && value !== null && String(value).trim() !== '';
}

function sizeOf(request) {
  const width = Number(request.width) || 0;
  const height = Number(request.height) || 0;
  if (width > 0 && height > 0) return width + ' × ' + height;
  const named = String(request.size || '');
  return /^\d+x\d+$/.test(named) ? named.replace('x', ' × ') : named;
}

function referenceCount(request) {
  if (Array.isArray(request.references)) return request.references.length;
  return '';
}

function seedOf(request) {
  if (shown(request.seed)) return String(request.seed);
  const first = Array.isArray(request.items) ? request.items[0] : null;
  return first && shown(first.seed) ? String(first.seed) : '';
}

// The fields the request carries for one kind. A blank field is left out: the
// engine's own default stands for it, and naming it would claim a value the
// request never sent.
function requestRows(kind, request) {
  const rows = [];
  const add = (name, value) => { if (shown(value)) rows.push([LABELS[name], String(value)]); };
  add('prompt', request.prompt);
  add('negative', request.negative);
  add('style', request.style);
  add('lyrics', request.lyrics);
  add('text', request.text);
  add('instruction', request.instruction);
  add('voice', request.voice);
  add('template', request.template);
  add('reference', request.reference_name || request.reference?.name);
  add('size', sizeOf(request));
  add('frames', request.numFrames ?? request.num_frames);
  add('seconds', request.seconds);
  if (typeof request.duration === 'number' && request.duration > 0) add('duration', request.duration.toFixed(1) + ' s');
  add('planning', request.cot);
  add('steps', request.steps);
  add('guidance', request.cfg_scale ?? request.guidance);
  add('seed', seedOf(request));
  add('references', referenceCount(request));
  add('look', request.look);
  add('pipeline', request.pipeline);
  const count = Number(request.count);
  if (kind === 'image' && count > 1) add('count', count);
  return rows;
}

function liveRows(live) {
  if (!live) return [];
  const state = live() || {};
  const rows = [];
  if (shown(state.status)) rows.push([t('run.field.status'), t('run.status.' + state.status)]);
  // The stage is the status's own word during most of a run. Keep it only when it
  // names a different step, so the live block does not say the same thing twice.
  if (shown(state.stage) && state.stage !== state.status) rows.push([t('run.field.stage'), state.stage]);
  if (shown(state.step)) {
    rows.push([t('run.field.step'), state.total > 0 ? state.step + ' / ' + state.total : String(state.step)]);
  }
  if (state.elapsedSeconds >= 0) rows.push([t('run.field.elapsed'), clock(state.elapsedSeconds)]);
  return rows;
}

function clock(seconds) {
  const whole = Math.max(0, Math.floor(Number(seconds) || 0));
  return Math.floor(whole / 60) + ':' + String(whole % 60).padStart(2, '0');
}

function listFor(rows, longValues) {
  const list = document.createElement('dl');
  rows.forEach(function ([name, value]) {
    const term = document.createElement('dt');
    term.textContent = t(name);
    const detail = document.createElement('dd');
    detail.textContent = value;
    if (longValues) detail.className = 'long';
    list.append(term, detail);
  });
  return list;
}

export function openRunSheet({kind, model, mode, request = {}, live = null, id = 'run-sheet'}) {
  const body = document.createElement('div');
  body.className = 'run-sheet';
  const head = requestRows(kind, request);
  if (shown(model)) head.unshift([LABELS.model, model]);
  if (shown(mode)) head.unshift([LABELS.mode, mode]);
  body.append(listFor(head, true));

  const liveList = document.createElement('dl');
  liveList.className = 'run-live';
  const liveHead = document.createElement('h3');
  liveHead.textContent = t('run.live');
  const note = document.createElement('p');
  note.className = 'run-note';
  note.textContent = t('run.sheet.note');
  body.append(liveHead, liveList, note);

  const paintLive = function () {
    const rows = liveRows(live);
    liveList.replaceChildren(...Array.from(listFor(rows).children));
    liveHead.hidden = rows.length === 0;
    liveList.hidden = rows.length === 0;
  };
  paintLive();

  const timer = live ? setInterval(paintLive, 1000) : null;
  return openSheet({
    id,
    title: t('run.sheet.title'),
    label: t('run.sheet.title'),
    closeLabel: t('run.sheet.close'),
    body,
    className: 'run-sheet-dialog',
    onClose: function () { if (timer) clearInterval(timer); },
  });
}

export function openResultSheet({kind, model, mode, request, elapsed, trigger}) {
  const rows = requestRows(kind, request);
  if (request.fastMode) rows.push(['page.video.fastMode', t('music.common.yes')]);
  if (typeof request.loras === 'string' && request.loras) rows.push(['run.field.addons', request.loras]);
  if (shown(model)) rows.unshift([LABELS.model, model]);
  if (shown(mode)) rows.unshift([LABELS.mode, mode]);
  if (Number.isFinite(elapsed)) rows.push(['run.field.elapsed', clock(elapsed)]);
  return openSheet({
    id: 'result-details-sheet',
    title: t('run.details'),
    closeLabel: t('run.sheet.close'),
    body: listFor(rows, true),
    className: 'result-sheet-dialog',
    onClose: () => { if (trigger?.isConnected) trigger.focus(); },
  });
}
