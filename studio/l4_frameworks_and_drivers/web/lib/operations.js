import {screenAwake} from './screen-awake.js';
import {t} from './i18n.js';
import {navigate} from './navigation.js';
const awake = screenAwake();
// Every tab reads the same operation. Results outlive the request that made them.
const page = {};
const imported = new Set();
const owners = new Set();
const observed = new Set();
const batchItems = new Set();
const batchCounts = new Map();
// A result that fails to load gets two more polls before it is set aside.
const importFailures = new Map();
const openedAt = performance.timeOrigin / 1000;
try {
  JSON.parse(sessionStorage.getItem('studio-seen-operations') || '[]').forEach(id => imported.add(id));
  JSON.parse(sessionStorage.getItem('studio-operation-owners') || '[]').forEach(id => owners.add(id));
  JSON.parse(sessionStorage.getItem('studio-observed-operations') || '[]').forEach(id => observed.add(id));
} catch (error) {
  console.warn('Completed operations were not read:', error);
}
function remember(id) {
  if (!id) return;
  imported.add(id);
  try {
    sessionStorage.setItem('studio-seen-operations', JSON.stringify(Array.from(imported).slice(-256)));
  } catch (error) {
    console.warn('Completed operations were not saved:', error);
  }
}
document.addEventListener('operation-imported', function (event) { remember(event.detail); });
let active = null;
let polling = false;
let pollTimer = null;
let refreshPending = false;
let serverBusy = false;
let localBusy = false;
let stopped = false;
let lastFailure = '';
let progressId = null;
let overallPercent = null;
// Polls in a row that found the studio busy with no operation this page can see.
let hiddenPolls = 0;
// A press shows Stopping for a short time only. A new hidden run can start before this
// page sees an idle poll, and a lasting flag would then lock that run's Cancel.
const HIDDEN_STOP_MS = 10000;
let hiddenStopUntil = 0;

function hiddenStopping() {
  return performance.now() < hiddenStopUntil;
}

function elapsed(operation) {
  return Math.max(0, (operation.finished_at || Date.now() / 1000) - operation.started_at);
}

// Another client's private operation stays out of this page's state, but it holds the
// GPU that every client shares. The bar names nothing about it and offers only the stop.
// It waits for a second busy poll, so that a short model change does not flash it.
function renderHidden(panel, label, cancel) {
  panel.hidden = hiddenPolls < 2;
  if (panel.hidden) return;
  const stopping = hiddenStopping();
  label.textContent = stopping ? t('operation.phase.stopping') : t('operation.hidden.label');
  document.getElementById('shared-operation-detail').textContent = t('operation.hidden.detail');
  document.getElementById('shared-operation-percent').textContent = '';
  document.getElementById('shared-operation-elapsed').textContent = '';
  document.getElementById('shared-operation-details').hidden = true;
  cancel.disabled = stopping;
  cancel.querySelector('span').textContent = stopping ? t('operation.action.stopping') : t('operation.action.cancel');
  panel.dataset.operationId = '';
  panel.dataset.status = stopping ? 'stopping' : 'hidden';
}

function render(operation) {
  const panel = document.getElementById('shared-operation');
  const label = document.getElementById('shared-operation-label');
  const cancel = document.getElementById('shared-operation-cancel');
  if (!operation) {
    renderHidden(panel, label, cancel);
    return;
  }
  panel.hidden = false;
  document.getElementById('shared-operation-details').hidden = false;
  const state = operation.progress || {};
  // Music reports separate phase totals, with unknown token counts between them.
  if (progressId !== operation.id || operation.kind === 'music') { progressId = operation.id; overallPercent = null; }
  if (state.total > 0) overallPercent = Math.max(overallPercent || 0, Math.min(99, Math.floor(state.step / state.total * 100)));
  const percent = overallPercent;
  const labels = {rewrite: t('operation.label.rewrite'), video: t('operation.label.video'), music: t('operation.label.music'), voice: t('operation.label.voice'), image: t('operation.label.image')};
  const name = operation.kind === 'image' && operation.mode === 'edit' ? t('operation.label.editImage') : labels[operation.kind] || t('operation.label.media');
  const stopping = operation.status === 'stopping';
  const phase = stopping ? t('operation.phase.stopping') : state.stage === 'preparing' ? t('operation.phase.loading')
    : state.total && state.step >= state.total ? t('operation.phase.finishing') : name;
  // Music already names its model without the quantisation in its own header and stage, so
  // the shared line reads the same name rather than the longer server label beside it.
  const model = operation.kind === 'music'
    ? String(operation.model || '').replace(/\s*\(MLX Q8\)\s*$/i, '').trim()
    : operation.model;
  const detail = [model, operation.batch_total ? t('operation.detail.itemOf', {index: operation.batch_index || 1, total: operation.batch_total})
    : state.label ? t('operation.detail.image', {label: state.label}) : ''].filter(Boolean).join(', ');
  // A rewrite reports its own stages, and the first poll can land before the rewriter
  // names one, so an idle rewrite still reads as preparing.
  label.textContent = !stopping && operation.kind === 'rewrite' && ['idle', 'preparing'].includes(state.stage)
    ? t('operation.phase.preparingRewrite') : phase;
  document.getElementById('shared-operation-detail').textContent = detail;
  document.getElementById('shared-operation-percent').textContent = percent === null ? '' : percent + '%';
  const seconds = Math.floor(elapsed(operation));
  document.getElementById('shared-operation-elapsed').textContent = t('operation.detail.elapsed', {time: Math.floor(seconds / 60) + ':' + String(seconds % 60).padStart(2, '0')});
  cancel.disabled = stopping;
  cancel.querySelector('span').textContent = stopping ? t('operation.action.stopping') : t('operation.action.cancel');
  panel.dataset.operationId = operation.id;
  panel.dataset.status = operation.status;
}

async function cancelHidden() {
  if (hiddenPolls < 2 || hiddenStopping()) return;
  document.getElementById('shared-operation-cancel').disabled = true;
  try {
    const answer = await fetch('/hidden/cancel', {method: 'POST'});
    // A 409 says the hidden operation ended before the press arrived.
    if (answer.status === 409) page.notify('info', t('operation.hidden.none'));
    else if (!answer.ok) {
      const body = await answer.json().catch(() => ({}));
      throw new Error(body.error || t('operation.error.notStopped'));
    } else hiddenStopUntil = performance.now() + HIDDEN_STOP_MS;
    await poll();
  } catch (error) {
    page.notify('error', error instanceof TypeError ? t('form.error.serverSilent') : error.message);
  }
}

async function cancelActive() {
  if (!active) return cancelHidden();
  page.prepareNativeCancel(active);
  navigate('controls');
  const operationId = active.id;
  document.getElementById('shared-operation-cancel').disabled = true;
  try {
    const answer = await fetch('/api/v1/operations/' + encodeURIComponent(operationId) + '/cancel', {method: 'POST'});
    if (!answer.ok) {
      const body = await answer.json().catch(() => ({}));
      throw new Error(body.error || t('operation.error.notStopped'));
    }
    await poll();
  } catch (error) {
    page.notify('error', error instanceof TypeError ? t('form.error.serverSilent') : error.message);
  }
}

async function importVideo(operation, answer, identity = operation.id) {
  const contentType = answer.headers.get('content-type') || '';
  const settings = Object.assign({}, operation.settings, {
    operationId: identity, backend: operation.backend, modelName: operation.model,
    createdAt: (operation.completed_at || operation.finished_at) * 1000,
    prompt: operation.prompt, width: operation.width ?? operation.settings?.width,
    height: operation.height ?? operation.settings?.height,
    numFrames: operation.num_frames ?? operation.settings?.num_frames,
    frameRate: operation.frame_rate ?? operation.settings?.frame_rate,
    elapsedSeconds: elapsed(operation),
  });
  settings.duration = settings.numFrames / settings.frameRate;
  const seed = answer.headers.get('X-Studio-Seed');
  if (seed !== null) settings.seed = Number(seed);
  if (contentType.includes('video/mp4')) await page.video().addGeneratedClip(await answer.blob(), settings);
  else page.video().addStubClip(await answer.json(), settings);
}

async function importBatch(operation, answer) {
  const manifest = await answer.json();
  for (const item of manifest.items || []) {
    if (!item.result_url) continue;
    const identity = operation.id + ':' + item.index;
    if (batchItems.has(identity)) continue;
    const response = await fetch(item.result_url, {cache: 'no-store'});
    if (response.status === 404 || response.status === 410) continue;
    if (!response.ok) throw new Error(t('operation.error.batchItem'));
    const record = {...operation, ...item, id: operation.id + ':' + item.index,
      finished_at: item.completed_at || operation.finished_at};
    if (operation.kind === 'video') await importVideo(record, response, record.id);
    else if (operation.kind === 'image') {
      const result = await response.json();
      await page.addImages(record, result.images || [], item.index - 1);
    }
    batchItems.add(identity);
  }
}

async function importResult(operation) {
  // A rewrite this tab made before this page opened is already in the box and the draft.
  // A refresh gives the page a new client id, so the tab's saved owners carry it.
  const appliedRewrite = operation.kind === 'rewrite' && operation.source === 'ui'
    && owners.has(operation.client_id) && (operation.finished_at || 0) < openedAt;
  if (imported.has(operation.id) || appliedRewrite || (operation.client_id === page.clientId
      && !['voice', 'music'].includes(operation.kind)
      && !(operation.kind === 'image' && operation.batch_total))) return;
  if (operation.source === 'ui' && operation.library_id !== page.libraryId && !owners.has(operation.client_id)) return;
  if (operation.source === 'ui' && !owners.has(operation.client_id) && !observed.has(operation.id)
      && operation.started_at < openedAt && (operation.finished_at || 0) < openedAt) return;
  const terminalFailure = operation.status === 'failed' || operation.status === 'cancelled';
  if (terminalFailure && operation.kind === 'music') page.music().restoreAfterFailure?.(operation);
  const message = operation.error || (operation.status === 'cancelled' ? t('operation.error.cancelled') : t('operation.error.failed'));
  if (terminalFailure && !operation.result_url) {
    remember(operation.id);
    page.notify(operation.status === 'failed' ? 'error' : 'info', message);
    return;
  }
  const partialBatch = ['running', 'stopping'].includes(operation.status) && operation.batch_completed > 0;
  if ((!terminalFailure && operation.status !== 'succeeded' && !partialBatch) || !operation.result_url) return;
  if (partialBatch && batchCounts.get(operation.id) >= operation.batch_completed) return;
  const answer = await fetch(operation.result_url, {cache: 'no-store'});
  if (answer.status === 404 || answer.status === 410) {
    remember(operation.id);
    page.notify('info', t('operation.error.expired'));
    return;
  }
  if (!answer.ok) throw new Error(t('operation.error.result'));
  if (operation.kind === 'music') {
    await customElements.whenDefined('music-studio');
    await page.music().importOperation(operation, answer);
  } else if (operation.kind === 'voice') {
    await customElements.whenDefined('voice-studio');
    await page.voice().importOperation(operation, answer);
  } else if (operation.batch_total || Array.isArray(operation.settings?.items)) {
    await importBatch(operation, answer);
  } else if (operation.kind === 'video') {
    await importVideo(operation, answer);
  } else {
    const result = await answer.json();
    if (operation.kind === 'image') await page.addImages(operation, result.images || []);
    else page.showRewrite(operation, result);
  }
  if (terminalFailure) page.notify(operation.status === 'failed' ? 'error' : 'info', message);
  if (partialBatch) batchCounts.set(operation.id, operation.batch_completed);
  else remember(operation.id);
}

function clearPollTimer() {
  window.clearTimeout(pollTimer);
  pollTimer = null;
}

function observeLocalWork() {
  function changed() {
    const working = document.body.matches('.busy, .video-busy, .rewriting')
      || Boolean(document.querySelector('#voice-generate[data-state]:not([data-state="idle"])'))
      || Boolean(document.querySelector('#music-generate[data-state]:not([data-state="idle"])'));
    if (working === localBusy) return;
    localBusy = working;
    if (working) poll();
  }
  const observer = new MutationObserver(changed);
  observer.observe(document.body, {attributes: true, attributeFilter: ['class']});
  const voice = document.getElementById('voice-studio');
  if (voice) observer.observe(voice, {subtree: true, childList: true, attributes: true, attributeFilter: ['data-state']});
  const music = document.getElementById('music-generate');
  if (music) observer.observe(music, {attributes: true, attributeFilter: ['data-state']});
  changed();
}

function schedulePoll() {
  clearPollTimer();
  if (stopped || document.hidden) return;
  pollTimer = window.setTimeout(poll, (serverBusy || localBusy) && !lastFailure ? 350 : 5000);
}

async function poll() {
  if (stopped || document.hidden) return;
  if (polling) { refreshPending = true; return; }
  clearPollTimer();
  polling = true;
  try {
    const answer = await fetch('/api/v1/state', {cache: 'no-store'});
    if (answer.status === 404) {
      stopped = true;
      awake.set(false);
      page.notify('error', t('operation.error.updatesStopped'));
      return;
    }
    if (answer.status === 503) {
      const body = await answer.clone().json().catch(() => null);
      if (body?.error === 'The JSON API is not configured.') {
        stopped = true;
        awake.set(false);
        page.notify('error', t('operation.error.updatesStopped'));
        return;
      }
    }
    if (!answer.ok) throw new Error(t('operation.error.status'));
    const state = await answer.json();
    active = state.active;
    serverBusy = Boolean(state.busy || active);
    // This page's own model change also holds the studio with no operation.
    const hidden = Boolean(state.busy && !active) && !page.changingModel();
    hiddenPolls = hidden ? hiddenPolls + 1 : 0;
    if (!hidden) hiddenStopUntil = 0;
    awake.set(active);
    if (active && !observed.has(active.id)) {
      observed.add(active.id);
      try {
        sessionStorage.setItem('studio-observed-operations', JSON.stringify(Array.from(observed).slice(-256)));
      } catch (error) {
        console.warn('Observed operations were not saved:', error);
      }
    }
    render(active);
    if (page.beforeState) page.beforeState();
    try {
      if (state.studio) page.syncModels(state.studio);
      page.setActive(active);
    } finally { if (page.afterState) page.afterState(); }
    if (active && active.kind === 'video' && active.client_id !== page.clientId) {
      page.video().setGenerationProgress(Object.assign({running: true}, active.progress), elapsed(active), {
        width: active.width, height: active.height, modelName: active.model, prompt: active.prompt,
        numFrames: active.num_frames, frameRate: active.frame_rate,
        seed: active.settings?.seed,
        fastMode: Boolean(active.settings?.fast_mode),
        // The record's own fields, so a run another tab started still has a Details sheet.
        settings: active.settings, mode: active.mode,
      });
    }
    page.observeDrafts(state.operations || []);
    let importFailure = '';
    for (const operation of (state.operations || []).slice().reverse()) {
      try {
        await importResult(operation);
        importFailures.delete(operation.id);
      } catch (error) {
        // One result that will not load must not hold the page on "Cancel" or hide the
        // results behind it. It gets two more polls, then the poll moves on.
        const failures = (importFailures.get(operation.id) || 0) + 1;
        importFailures.set(operation.id, failures);
        if (failures >= 3) { remember(operation.id); importFailures.delete(operation.id); }
        const message = error instanceof SyntaxError ? t('operation.error.result')
          : (error.message || t('operation.error.result'));
        importFailure = message;
        if (lastFailure !== message) page.notify('error', message);
        lastFailure = message;
      }
      page.finishImageOperation(operation);
    }
    if (!importFailure) lastFailure = '';
  } catch (error) {
    serverBusy = false;
    awake.set(false);
    const message = error instanceof SyntaxError || error instanceof TypeError
      ? t('operation.error.status') : (error.message || t('operation.error.status'));
    if (lastFailure !== message) page.notify('error', message);
    lastFailure = message;
  } finally {
    polling = false;
    if (refreshPending) { refreshPending = false; poll(); }
    else schedulePoll();
  }
}

document.dispatchEvent(new CustomEvent('operations-ready', {
  detail: {configure(helpers) {
    Object.assign(page, helpers);
    owners.add(page.clientId);
    try {
      sessionStorage.setItem('studio-operation-owners', JSON.stringify(Array.from(owners).slice(-64)));
    } catch (error) {
      console.warn('Operation owners were not saved:', error);
    }
    document.getElementById('shared-operation-cancel').addEventListener('click', cancelActive);
    document.addEventListener('visibilitychange', function () {
      clearPollTimer();
      if (!document.hidden) poll();
    });
    window.addEventListener('pagehide', function () { stopped = true; clearPollTimer(); awake.set(false); });
    window.addEventListener('pageshow', function () { stopped = false; poll(); });
    observeLocalWork();
    poll();
    return {refresh: poll};
  }},
}));
