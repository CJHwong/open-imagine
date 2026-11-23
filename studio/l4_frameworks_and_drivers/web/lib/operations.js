import './fetch-limits.js';
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
// A result that fails to load is retried with a widening gap. The server keeps it for
// minutes, and marking it imported hid a result the person could still have had.
const importFailures = new Map();
const importRetryAt = new Map();
const openedAt = performance.timeOrigin / 1000;
try {
  JSON.parse(sessionStorage.getItem('studio-seen-operations') || '[]').forEach(id => imported.add(id));
  JSON.parse(sessionStorage.getItem('studio-operation-owners') || '[]').forEach(id => owners.add(id));
  JSON.parse(sessionStorage.getItem('studio-observed-operations') || '[]').forEach(id => observed.add(id));
} catch (error) {
  console.warn('Completed operations were not read:', error);
}
// The tab's lists above do not survive an app that Android restarts mid-run: the new page
// skipped its own clip as another page's, until the studio dropped it. So the library also
// keeps its clients and the runs its tabs took, in localStorage. A video run that ended
// before this page opened, made by a client of this library and taken by no tab, is this
// page's to import. Video only: its follower marks every outcome taken, so a taken run never
// comes back, where an image run its own tab made is not always marked.
const libraryOwners = new Set();
const libraryImported = new Set();
const LIBRARY_LISTS = {
  'studio-library-owners': [libraryOwners, 64],
  'studio-library-imported': [libraryImported, 256],
};
function libraryKey(name) {
  return name + ':' + page.libraryId;
}
// Another tab may have written since this one read, so a read merges and a write reads first.
function readLibrary(name) {
  try {
    JSON.parse(localStorage.getItem(libraryKey(name)) || '[]').forEach(id => LIBRARY_LISTS[name][0].add(id));
  } catch (error) {
    console.warn('The library list ' + name + ' was not read:', error);
  }
}
function writeLibrary(name, change) {
  // Before configure names the library there is nothing to write under.
  if (!page.libraryId) return;
  const [values, limit] = LIBRARY_LISTS[name];
  readLibrary(name);
  change(values);
  try {
    localStorage.setItem(libraryKey(name), JSON.stringify(Array.from(values).slice(-limit)));
  } catch (error) {
    console.warn('The library list ' + name + ' was not saved:', error);
  }
}
function addToLibrary(name, id) {
  writeLibrary(name, values => { values.delete(id); values.add(id); });
}
function remember(id) {
  if (!id) return;
  imported.add(id);
  try {
    sessionStorage.setItem('studio-seen-operations', JSON.stringify(Array.from(imported).slice(-256)));
  } catch (error) {
    console.warn('Completed operations were not saved:', error);
  }
  addToLibrary('studio-library-imported', id);
}
document.addEventListener('operation-imported', function (event) { remember(event.detail); });
let active = null;
let polling = false;
let pollTimer = null;
let studioRevision = '';
let refreshPending = false;
let serverBusy = false;
let localBusy = false;
let stopped = false;
let lastFailure = '';
// A state read that times out or loses its connection is sent again at once, on a fresh
// request. Only this many misses in a row count as the studio being out of reach.
const POLL_MISSES = 3;
let pollMisses = 0;
// A miss that does not count (`studioReadCounts`) is asked again after this pause. An offline
// read fails at once, so asking again at once would spin.
const QUIET_RETRY_MS = 1000;
let quietRetry = false;
// The one notice that the studio is out of reach. It closes on the next state that arrives,
// and while it is open, or after a person closed it, a further loss adds no second one.
let lostNotice = null;
function lostRead(error) {
  return error instanceof TypeError || error?.name === 'TimeoutError' || error?.name === 'AbortError';
}
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

// The bar's clock ticks on its own between polls, so a poll that is slow, or lost on a
// phone's pipe, does not stop it.
let shown = null;
let clockTimer = null;
function showElapsed() {
  const seconds = Math.floor(elapsed(shown));
  document.getElementById('shared-operation-elapsed').textContent = t('operation.detail.elapsed', {time: Math.floor(seconds / 60) + ':' + String(seconds % 60).padStart(2, '0')});
}
function tick(operation) {
  shown = operation;
  if (!operation) {
    window.clearInterval(clockTimer);
    clockTimer = null;
    return;
  }
  showElapsed();
  if (!clockTimer) clockTimer = window.setInterval(showElapsed, 1000);
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
    tick(null);
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
  tick(operation);
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
    const response = await studioStallFetch(item.result_url, {cache: 'no-store'});
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
  // A deferred import has not succeeded. The caller must not read this as one, or the
  // retry deadline is cleared and the next poll starts the backoff over.
  if (Date.now() < (importRetryAt.get(operation.id) || 0)) return 'deferred';
  // A rewrite this tab made before this page opened is already in the box and the draft.
  // A refresh gives the page a new client id, so the tab's saved owners carry it.
  const appliedRewrite = operation.kind === 'rewrite' && operation.source === 'ui'
    && owners.has(operation.client_id) && (operation.finished_at || 0) < openedAt;
  // The page imports its own video run only while it follows it. A run it stopped following,
  // because the start's answer or the result read was lost on the way, is imported here.
  const ownedHere = operation.kind === 'video' ? operation.id === page.followingVideo?.()
    : operation.client_id === page.clientId && !['voice', 'music'].includes(operation.kind)
      && !(operation.kind === 'image' && operation.batch_total);
  if (imported.has(operation.id) || appliedRewrite || ownedHere) return;
  if (operation.source === 'ui' && operation.library_id !== page.libraryId && !owners.has(operation.client_id)) return;
  // Completed history is not replayed into a page that opens later, so an unkept result
  // stays gone; a video run that no tab of this library took is the exception.
  if (operation.source === 'ui' && !owners.has(operation.client_id) && !observed.has(operation.id)
      && operation.started_at < openedAt && (operation.finished_at || 0) < openedAt) {
    const leftOver = operation.kind === 'video' && operation.finished_at && libraryOwners.has(operation.client_id);
    return leftOver ? adopt(operation) : undefined;
  }
  return deliver(operation);
}

// Two tabs that open together both find a left-over run. A Web Lock, where the page has one,
// lets one of them read the library's list and import while the other waits for a later poll.
// Without one, as on a plain-http LAN address, the list alone decides, which is best effort.
async function adopt(operation) {
  if (!navigator.locks) return takeLeftOver(operation);
  return navigator.locks.request('studio-import:' + operation.id, {ifAvailable: true},
    lock => (lock ? takeLeftOver(operation) : 'deferred'));
}

async function takeLeftOver(operation) {
  readLibrary('studio-library-imported');
  if (libraryImported.has(operation.id)) return;
  return deliver(operation);
}

async function deliver(operation) {
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
  const answer = await studioStallFetch(operation.result_url, {cache: 'no-store'});
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
    // During a run the page polls fast, and the studio block, most of each answer, comes back
    // only when it differs from the one this page holds. An idle poll takes the whole block,
    // so a model choice this page drew ahead of the studio is still put right.
    const fast = serverBusy || localBusy;
    const known = fast && studioRevision ? '?studio=' + encodeURIComponent(studioRevision) : '';
    let answer;
    let state = null;
    const startedAt = performance.now();
    try {
      // The limit covers the body too, so the answer is read here, inside it.
      answer = await studioStatusFetch('/api/v1/state' + known, {cache: 'no-store'});
      if (answer.ok) state = await answer.json();
    } catch (error) {
      if (lostRead(error) && !studioReadCounts(startedAt)) { quietRetry = true; return; }
      pollMisses += 1;
      if (!lostRead(error) || pollMisses >= POLL_MISSES) { pollMisses = 0; throw error; }
      refreshPending = true;
      return;
    }
    pollMisses = 0;
    lostNotice?.close();
    lostNotice = null;
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
      if (state.studio) {
        page.syncModels(state.studio);
        studioRevision = state.studio_revision || '';
      }
      page.setActive(active);
    } finally { if (page.afterState) page.afterState(); }
    if (active && active.kind === 'video' && active.id !== page.followingVideo?.()) {
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
        const outcome = await importResult(operation);
        if (outcome !== 'deferred') {
          importFailures.delete(operation.id);
          importRetryAt.delete(operation.id);
        }
      } catch (error) {
        // One result that will not load must not hold the page on "Cancel" or hide the
        // results behind it. It is not imported though, so it stays visible and the page
        // tries again after a widening gap instead of hiding it for the session.
        const failures = (importFailures.get(operation.id) || 0) + 1;
        importFailures.set(operation.id, failures);
        importRetryAt.set(operation.id, Date.now() + Math.min(60000, 2000 * 2 ** Math.min(failures, 5)));
        const message = error instanceof SyntaxError ? t('operation.error.result')
          : (error.message || t('operation.error.result'));
        // Which operation failed matters when several tabs and a phone share one studio.
        // A private operation keeps its id to itself.
        const where = operation.private ? '' : ` (${operation.kind} ${String(operation.id).slice(0, 8)})`;
        importFailure = message + where;
        // The notice names the operation, so two failures with the same words are two
        // notices, not one repeated.
        if (lastFailure !== message + where) page.notify('error', message + where);
        lastFailure = message + where;
      }
      page.finishImageOperation(operation);
    }
    if (!importFailure) lastFailure = '';
  } catch (error) {
    serverBusy = false;
    awake.set(false);
    if (lostRead(error)) {
      if (!lostNotice) lostNotice = page.notify('error', t('operation.error.lostContact'));
      lastFailure = t('operation.error.lostContact');
      return;
    }
    const message = error instanceof SyntaxError
      ? t('operation.error.status') : (error.message || t('operation.error.status'));
    if (lastFailure !== message) page.notify('error', message);
    lastFailure = message;
  } finally {
    polling = false;
    if (refreshPending) { refreshPending = false; poll(); }
    else if (quietRetry) { quietRetry = false; clearPollTimer(); pollTimer = window.setTimeout(poll, QUIET_RETRY_MS); }
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
    addToLibrary('studio-library-owners', page.clientId);
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
