import {uuid} from './uuid.js';
// The kept images: the browser's own store, and the tab that hears about it.
//
// The server keeps no image after it answers, so the browser keeps them, with
// their facts, until Clear all. Each one and its facts go to IndexedDB, so a
// reload or a new tab brings them back; localStorage holds about 5 MB, a few
// images. The store belongs to this address and port. Every change goes out on
// a channel, so each open tab shows the same strip.
//
// Two things stay the page's, and both are read before this module can be
// fetched. The keep setting is one: the page's strip note and its leave warning
// read it while the page is still parsing. The gallery array is the other: a
// run's answer lands in it, and this module only asks for it. So this module
// owns the database and the channel, and the page owns the setting and the
// array.
//
// The page's own script is still a classic script, so it cannot import this
// module and has no other way to put a record in. The listener is registered
// while the markup is parsed and this fires while the module is evaluated:
// after the markup, before any interaction. This door closes when the inline
// script is gone.

import { t } from './i18n.js';

// The fields a stored record carries besides its two pictures. A record is read
// back into a gallery entry, so the list is the shape both ends agree on.
const KEPT_FIELDS = ['id', 'number', 'operationId', 'nativeMetadata', 'seed', 'width', 'height', 'steps', 'elapsed', 'position', 'mode', 'prompt',
  'typed', 'look', 'negative', 'sources', 'backend', 'backendId', 'precision', 'at'];

const channel = new BroadcastChannel('studio-gallery');

// The page's own, handed over on the door.
let page = null;

// The handle is opened once and kept: a browser that refuses one is only
// reachable at that first moment.
let database = null;
let videoDatabase = null;
// The tombstones that hide a deleted item from another tab. They are read once and
// kept: a scan asks about every record, and parsing the same list for each one is
// work the page pays for nothing. A write from another tab arrives as a channel
// message or a storage event, and either way the cache is read once more.
function mediaRemovals(kind) {
  const removedIds = new Set();
  // An item an archive brought back stays back, even when the delete-all time would
  // otherwise hide it. The exception is saved beside the tombstones, so a reload and
  // every other tab agree about it.
  const restoredIds = new Set();
  let clearedAt = 0;
  let loaded = false;
  const removedKey = 'studio-removed-' + kind;
  const restoredKey = 'studio-restored-' + kind;
  const clearedKey = 'studio-' + kind + '-cleared-at';
  function remember(set, id) {
    set.delete(id);
    set.add(id);
    if (set.size > 2048) set.delete(set.values().next().value);
  }
  function read() {
    if (loaded) return;
    loaded = true;
    try {
      JSON.parse(localStorage.getItem(removedKey) || '[]').forEach(id => remember(removedIds, String(id)));
      JSON.parse(localStorage.getItem(restoredKey) || '[]').forEach(id => remember(restoredIds, String(id)));
      clearedAt = Math.max(clearedAt, Number(localStorage.getItem(clearedKey)) || 0);
    } catch (error) {
      console.warn('Media removals were not read:', error);
    }
  }
  function save() {
    try {
      localStorage.setItem(removedKey, JSON.stringify(Array.from(removedIds)));
      localStorage.setItem(restoredKey, JSON.stringify(Array.from(restoredIds)));
      localStorage.setItem(clearedKey, String(clearedAt));
    } catch (error) {
      console.warn('Media removals were not saved:', error);
    }
  }
  // Another tab wrote one of these keys. The next question re-reads them, and only
  // that one question pays for the parse.
  window.addEventListener('storage', function (event) {
    if (event.key === null || event.key === removedKey || event.key === restoredKey || event.key === clearedKey) {
      loaded = false;
    }
  });
  function wasRemoved(entry) {
    read();
    const id = String(entry.id);
    if (restoredIds.has(id)) return false;
    const completedAt = entry.at || entry.createdAt;
    return removedIds.has(id) || Boolean(clearedAt && (!completedAt || completedAt <= clearedAt));
  }
  function markRemoved(message) {
    read();
    if (message.kind.endsWith('remove')) {
      const id = String(message.id);
      restoredIds.delete(id);
      remember(removedIds, id);
    }
    if (message.kind.endsWith('clear')) {
      (message.ids || []).forEach(id => {
        const key = String(id);
        restoredIds.delete(key);
        remember(removedIds, key);
      });
      message.clearedAt = message.clearedAt || Date.now();
      clearedAt = Math.max(clearedAt, message.clearedAt);
    }
    save();
  }
  // An imported archive is the user's own choice, so it clears the tombstone of each
  // item it brings back. Cross-tab replication keeps asking `wasRemoved`; an explicit
  // restore is the one caller that answers for the item itself.
  function forget(id) {
    read();
    const key = String(id);
    removedIds.delete(key);
    remember(restoredIds, key);
    save();
  }
  return {wasRemoved, markRemoved, forget};
}
const {wasRemoved, markRemoved, forget: forgetImage} = mediaRemovals('images');
const {wasRemoved: videoWasRemoved, markRemoved: markVideoRemoved, forget: forgetVideo} = mediaRemovals('videos');

function keepPreferred(media, record, removed) {
  if (!page.keeping() || removed(record)) return;
  const request = media.get(record.id);
  request.onsuccess = function () {
    if (!page.keeping() || removed(record)) return;
    if (!request.result) media.add(record);
    else if (record.nativeMetadata && !request.result.nativeMetadata) media.put(record);
  };
  return request;
}

function clearRemoved(media, removed) {
  const request = media.openCursor();
  request.onsuccess = function () {
    const cursor = request.result;
    if (!cursor) return;
    if (removed(cursor.value)) cursor.delete();
    cursor.continue();
  };
  return request;
}

function openStore() {
  if (!database) {
    database = new Promise(function (resolve, reject) {
      const request = indexedDB.open('studio', 1);
      request.onupgradeneeded = function () {
        if (!request.result.objectStoreNames.contains('images')) request.result.createObjectStore('images', { keyPath: 'id' });
      };
      request.onsuccess = function () {
        // Another tab upgraded or removed the database: open it again on the next call.
        request.result.onversionchange = function () { request.result.close(); database = null; };
        resolve(request.result);
      };
      request.onerror = function () { database = null; reject(request.error); };
      request.onblocked = function () { database = null; reject(new Error(t('store.error.imageStorageBlocked'))); };
    });
    // A failed open must not poison every later read.
    database.catch(function () { database = null; });
  }
  return database;
}

// Run one request on the images store. It settles when the transaction ends,
// so a write has landed before any other tab hears of it.
function inStore(access, work) {
  return openStore().then(function (store) {
    return new Promise(function (resolve, reject) {
      const transaction = store.transaction('images', access);
      const request = work(transaction.objectStore('images'));
      transaction.oncomplete = function () { resolve(request ? request.result : undefined); };
      transaction.onabort = function () { reject(transaction.error); };
    });
  });
}

function openVideoStore() {
  if (!videoDatabase) {
    videoDatabase = new Promise(function (resolve, reject) {
      const request = indexedDB.open('studio-video-gallery', 1);
      request.onupgradeneeded = function () {
        if (!request.result.objectStoreNames.contains('clips')) request.result.createObjectStore('clips', { keyPath: 'id' });
      };
      request.onsuccess = function () {
        request.result.onversionchange = function () { request.result.close(); videoDatabase = null; };
        resolve(request.result);
      };
      request.onerror = function () { videoDatabase = null; reject(request.error); };
      request.onblocked = function () { videoDatabase = null; reject(new Error(t('store.error.videoStorageBlocked'))); };
    });
    videoDatabase.catch(function () { videoDatabase = null; });
  }
  return videoDatabase;
}

function inVideoStore(access, work) {
  return openVideoStore().then(function (store) {
    return new Promise(function (resolve, reject) {
      const transaction = store.transaction('clips', access);
      const request = work(transaction.objectStore('clips'));
      transaction.oncomplete = function () { resolve(request ? request.result : undefined); };
      transaction.onabort = function () { reject(transaction.error); };
    });
  });
}

function blobOf(url) {
  return fetch(url).then(function (response) { return response.blob(); });
}

// A stored record as the live entry the strip draws. Each image is shown by a
// blob URL, because as a data URL every img that showed it made the browser
// parse megabytes of base64 text again.
// Metadata is browsable without retaining the original PNG or its before image.
function liveEntry(record) {
  const entry = {stored: true, hasBefore: Boolean(record.before)};
  KEPT_FIELDS.forEach(field => { entry[field] = record[field]; });
  entry.loadMedia = () => inStore('readonly', images => images.get(entry.id));
  return entry;
}
const loadedImages = new Map();
let retainingImages = false;
function releaseImage(entry) {
  page.release(entry);
  delete entry.src; delete entry.before; delete entry.b64;
}
async function hydrate(entry) {
  if (entry.src) return entry;
  if (!entry.loading) entry.loading = entry.loadMedia().then(record => {
    if (!record || wasRemoved(entry)) throw new Error(t('store.error.imageGone'));
    entry.src = URL.createObjectURL(record.png);
    entry.before = record.before && URL.createObjectURL(record.before);
    loadedImages.delete(entry.id); loadedImages.set(entry.id, entry);
    for (const [id, other] of loadedImages) {
      if (retainingImages || forgetPins.size || !page.keeping() || loadedImages.size <= 2) break;
      if (!other.stored || id === entry.id || id === page.selected?.()) continue;
      releaseImage(other); loadedImages.delete(id);
    }
    return entry;
  }).finally(() => { delete entry.loading; });
  return entry.loading;
}

// Read bounded pages, yielding between transactions. Cursor values are discarded after
// metadata extraction; no getAll of original media, decoding, or object URLs on restore.
async function scanRecords(open, name, visit) {
  let after;
  while (true) {
    const db = await open();
    const result = await new Promise((resolve, reject) => {
      const transaction = db.transaction(name, 'readonly');
      const request = transaction.objectStore(name).openCursor(after === undefined ? null : IDBKeyRange.lowerBound(after, true));
      let count = 0, last;
      request.onsuccess = () => {
        const cursor = request.result;
        if (!cursor) return;
        visit(cursor.value); last = cursor.key;
        if (++count < 32) cursor.continue();
      };
      transaction.oncomplete = () => resolve({count, last});
      transaction.onabort = () => reject(transaction.error);
    });
    if (result.count < 32) break;
    after = result.last;
    await new Promise(resolve => setTimeout(resolve, 0));
  }
}

function keep(entry) {
  if (!page.keeping() || wasRemoved(entry) || (entry.stored && !entry.src)) return Promise.resolve();
  return Promise.all([blobOf(entry.src), entry.before ? blobOf(entry.before) : null]).then(function ([png, before]) {
    const record = { png: png, before: before };
    KEPT_FIELDS.forEach(function (field) { record[field] = entry[field]; });
    return inStore('readwrite', function (images) {
      if (!page.keeping() || wasRemoved(entry)) return;
      if (!entry.operationId) return images.add(record);
      return keepPreferred(images, record, wasRemoved);
    });
  }).then(function () {
    if (!page.keeping() || wasRemoved(entry)) return;
    entry.stored = true; entry.hasBefore = Boolean(entry.before);
    entry.loadMedia = () => inStore('readonly', images => images.get(entry.id));
    // A retained image does not need a second base64 copy in memory.
    delete entry.b64;
    loadedImages.set(entry.id, entry);
    for (const [id, other] of loadedImages) {
      if (retainingImages || forgetPins.size || !page.keeping() || loadedImages.size <= 2) break;
      if (!other.stored || id === entry.id || id === page.selected?.()) continue;
      releaseImage(other); loadedImages.delete(id);
    }
    channel.postMessage({ kind: 'add', id: entry.id });
  }).catch(function (error) {
    page.notify('error', t('store.error.keepImage', {
      number: page.frameNumber(entry.id), message: error.message,
    }));
  });
}

function keepVideo(clip, mp4, thumbnail) {
  if (!page.keeping() || videoWasRemoved(clip)) return Promise.resolve(false);
  const record = {
    id: clip.id,
    name: clip.name,
    duration: clip.duration,
    metadata: clip.metadata,
    createdAt: clip.createdAt,
    nativeMetadata: clip.nativeMetadata,
    mp4: mp4,
    thumbnail: thumbnail || null,
  };
  return inVideoStore('readwrite', function (clips) { return keepPreferred(clips, record, videoWasRemoved); }).then(function () {
    channel.postMessage({kind: 'video-add', id: clip.id});
    return true;
  }).catch(function (error) {
    page.notify('error', t('store.error.keepVideo', {name: clip.name, message: error.message}));
    return false;
  });
}

function keepVideoThumbnail(id, thumbnail) {  if (!page.keeping()) return Promise.resolve(false);
  return inVideoStore('readwrite', function (clips) {
    const request = clips.get(id);
    request.onsuccess = function () {
      if (!request.result) return;
      request.result.thumbnail = thumbnail;
      clips.put(request.result);
    };
    return request;
  }).then(function () {
    return true;
  }).catch(function (error) {
    page.notify('error', t('store.error.keepThumbnail', {video: id, message: error.message}));
    return false;
  });
}

async function loadVideos() {
  if (!page.keeping()) return [];
  const records = [];
  try {
    await scanRecords(openVideoStore, 'clips', record => {
      if (videoWasRemoved(record)) return;
      const {mp4, thumbnail, ...metadata} = record;
      records.push(metadata);
    });
    return records.sort((first, second) => first.createdAt - second.createdAt);
  } catch (error) { page.notify('error', t('store.error.loadVideos', {message: error.message})); return []; }
}

function removeVideo(id) {
  const message = {kind: 'video-remove', id: id};
  markVideoRemoved(message);
  channel.postMessage(message);
  if (!page.keeping()) return Promise.resolve(true);
  return inVideoStore('readwrite', function (clips) { return clips.delete(id); }).then(function () {
    return true;
  }).catch(function (error) {
    page.notify('error', t('store.error.removeVideo', {video: id, message: error.message}));
    return false;
  });
}

function clearVideos(ids = []) {
  const message = {kind: 'video-clear', ids: ids};
  markVideoRemoved(message);
  channel.postMessage(message);
  if (!page.keeping()) return Promise.resolve(true);
  return inVideoStore('readwrite', function (clips) { return clearRemoved(clips, videoWasRemoved); }).then(function () {
    return true;
  }).catch(function (error) {
    page.notify('error', t('store.error.clearVideos', {message: error.message}));
    return false;
  });
}

// Delete from the store, then tell the other tabs. The work is the caller's,
// because what goes is the caller's to name. With keeping off there is nothing
// stored, and each tab's strip is its own.
function forget(work, message) {
  markRemoved(message);
  if (!page.keeping()) return;
  inStore('readwrite', message.kind === 'clear' ? images => clearRemoved(images, wasRemoved) : work).then(function () {
    channel.postMessage(message);
  }).catch(function (error) {
    page.notify('error', t('store.error.removeImage', {message: error.message}));
  });
}

async function load() {
  if (!page.keeping()) return;
  try {
    await scanRecords(openStore, 'images', record => { if (!wasRemoved(record)) page.admit(liveEntry(record)); });
    page.showNewest();
  } catch (error) { page.notify('error', t('store.error.loadImages', {message: error.message})); }
}

// Off empties the store at once; the images stay in the open tabs until a
// reload. On keeps what the tab shows now, which is the page's to walk and this
// module's to write, one image at a time.
// Before disabling persistence, every open tab materializes its own lazy records.
// Discovery/acknowledgement finishes before any shared store is cleared.
const forgetting = new Map();
const forgetPins = new Set();
function pinForget(token) { forgetPins.add(token); page.pinMedia(true); }
function unpinForget(token) { forgetPins.delete(token); page.pinMedia(Boolean(forgetPins.size)); }

const tabId = uuid();
const tabLockName = 'studio-gallery-tab-';
let releaseMembership;
let membership = null;
function registerTab() {
  if (navigator.locks) {
    membership = new Promise(resolve => {
      navigator.locks.request(tabLockName + tabId, async () => {
        resolve(); await new Promise(release => { releaseMembership = release; });
      });
    });
  } else {
    localStorage.setItem(tabLockName + tabId, 'open');
    membership = Promise.resolve();
  }
}
registerTab();
window.addEventListener('pagehide', () => {
  releaseMembership?.(); localStorage.removeItem(tabLockName + tabId);
});
window.addEventListener('pageshow', event => { if (event.persisted) registerTab(); });
async function openTabs() {
  await membership;
  if (navigator.locks) {
    const {held} = await navigator.locks.query();
    return held.filter(lock => lock.name.startsWith(tabLockName)).map(lock => lock.name.slice(tabLockName.length));
  }
  return Object.keys(localStorage).filter(key => key.startsWith(tabLockName)).map(key => key.slice(tabLockName.length));
}
let retainingPage;
function retainPage() {
  if (!retainingPage) retainingPage = Promise.resolve().then(() => page.retainMedia()).finally(() => { retainingPage = null; });
  return retainingPage;
}
async function retainImages(entries) {
  retainingImages = true;
  try {
    for (const entry of entries) if (!entry.src) await hydrate(entry);
    for (const entry of entries) { entry.stored = false; delete entry.loadMedia; }
  } finally { retainingImages = false; }
}
async function prepareForget() {
  const token = uuid(), peers = new Map((await openTabs()).filter(id => id !== tabId).map(id => [id, 'waiting']));
  forgetting.set(token, peers);
  pinForget(token);
  channel.postMessage({kind: 'prepare-forget', token});
  try {
    await retainPage();
    await new Promise(resolve => setTimeout(resolve, 250));
    const deadline = Date.now() + 15000;
    while (Array.from(peers.values()).some(value => value === 'waiting')) {
      if (Date.now() > deadline) throw new Error(t('store.error.prepareForget'));
      const live = new Set(await openTabs());
      for (const id of peers.keys()) if (!live.has(id)) peers.delete(id);
      await new Promise(resolve => setTimeout(resolve, 50));
    }
    if (Array.from(peers.values()).some(value => value !== 'ready')) throw new Error(t('store.error.retainMedia'));
  } catch (error) {
    channel.postMessage({kind: 'forget-abort', token}); unpinForget(token); throw error;
  } finally { forgetting.delete(token); }
}
function announce(on) {
  channel.postMessage({ kind: 'keep', on: on });
  if (on) return;
  for (const token of forgetPins) unpinForget(token);
  Promise.all([
    inStore('readwrite', function (images) { return images.clear(); }),
    inVideoStore('readwrite', function (clips) { return clips.clear(); }),
  ]).catch(function (error) {
    page.notify('error', t('store.error.clearMedia', {message: error.message}));
  });
}

// A message from another tab. The one kind that carries an image is read back
// out of the store here, because the picture is too big to travel; the rest say
// what another tab did to the strip, and they are the page's to carry out.
channel.addEventListener('message', function (event) {
  const message = event.data;
  if (message.kind === 'forget-participant' || message.kind === 'forget-ready') {
    const peers = forgetting.get(message.token);
    if (peers && (message.kind === 'forget-ready' || !peers.has(message.tab))) peers.set(message.tab, message.state || 'waiting');
    return;
  }
  if (message.kind === 'forget-abort') { unpinForget(message.token); return; }
  if (message.kind === 'prepare-forget') {
    pinForget(message.token);
    channel.postMessage({kind: 'forget-participant', token: message.token, tab: tabId});
    retainPage().then(() => {
      channel.postMessage({kind: 'forget-ready', token: message.token, tab: tabId, state: 'ready'});
    }).catch(() => channel.postMessage({kind: 'forget-ready', token: message.token, tab: tabId, state: 'failed'}));
    return;
  }
  if (message.kind === 'remove' || message.kind === 'clear') markRemoved(message);
  if (message.kind === 'video-remove' || message.kind === 'video-clear') markVideoRemoved(message);
  if (message.kind !== 'add') {
    page.heard(message);
    if (message.kind === 'keep' && !message.on) for (const token of forgetPins) unpinForget(token);
    return;
  }
  if (!page.keeping()) return;
  inStore('readonly', function (images) { return images.get(message.id); }).then(function (record) {
    if (!record || wasRemoved(record)) return;
    page.admit(liveEntry(record));
    page.showNewest();
  }).catch(function (error) {
    page.notify('error', t('store.error.otherTabImage', {message: error.message}));
  });
});

// Best-effort storage can be evicted, and a saved video that vanishes is worse than the
// question. Ask once for durable storage; Chrome grants it by its own rules, and a refusal
// is worth one line rather than silence, because the next eviction is invisible.
let durable = null;
let durableAsked = false;

function askForDurableStorage() {
  if (durableAsked) return Promise.resolve(durable);
  durableAsked = true;
  if (!navigator.storage || typeof navigator.storage.persist !== 'function') {
    durable = false;
    return Promise.resolve(false);
  }
  return navigator.storage.persisted()
    .then(function (already) { return already || navigator.storage.persist(); })
    .then(function (granted) { durable = granted; return granted; })
    .catch(function () { durable = false; return false; });
}

// The gallery file. These read and write the records themselves, so an import
// lands in storage before any tab hears about it. Records carry their media as
// Blobs; lib/gallery-bundle.js turns those into base64 for the file.
function imageItem(record) {
  return {workspace: 'image', id: record.id, at: record.at || 0,
    record: withoutMedia(record, ['png', 'before']),
    media: [{role: 'png', blob: record.png}, ...(record.before ? [{role: 'before', blob: record.before}] : [])]};
}

function videoItem(record) {
  return {workspace: 'video', id: record.id, at: record.createdAt || 0,
    record: withoutMedia(record, ['mp4', 'thumbnail']),
    media: [{role: 'mp4', blob: record.mp4}, ...(record.thumbnail ? [{role: 'thumbnail', blob: record.thumbnail}] : [])]};
}

// The export walks the same bounded pages the gallery loader takes. `getAll()` asks
// one database for every record in a single result, and a gallery of large clips
// stalls the page there before the archive exists. A page is 32 records, and the
// media stays a Blob handle until the writer reads it, not bytes held here.
async function collectBundle() {
  const items = [];
  await scanRecords(openStore, 'images', record => items.push(imageItem(record)));
  await scanRecords(openVideoStore, 'clips', record => items.push(videoItem(record)));
  return items;
}

// What each workspace's record must carry to be drawn and deleted as one.
const IMPORT_MEDIA = {image: 'png', video: 'mp4'};

function validImport(item) {
  if (!item || typeof item !== 'object' || Array.isArray(item)) return false;
  const role = IMPORT_MEDIA[item.workspace];
  if (!role) return false;
  // An image carries its number, a clip its uuid, so the id is a number or a string.
  const named = typeof item.id === 'string' ? item.id.length > 0
    : typeof item.id === 'number' && Number.isFinite(item.id);
  if (!named) return false;
  const record = item.record;
  if (!record || typeof record !== 'object' || Array.isArray(record)) return false;
  // The record's own key path has to match the item that carries it, or the store
  // keeps a row the gallery cannot open by the id it shows.
  if (record.id !== item.id) return false;
  const media = Array.isArray(item.media) ? item.media : [];
  const entry = media.find(one => one && one.role === role && one.blob instanceof Blob);
  if (!entry) return false;
  const type = String(entry.blob.type || entry.mime || '').toLowerCase();
  // A bundle older than version 3 stored no type; it is taken as it stands.
  return !type || type.startsWith(item.workspace === 'image' ? 'image/' : 'video/');
}

// Everything is checked before one store is touched, so a malformed file changes
// nothing. A record put twice under the same id is one write, which makes a retried
// import the same as the first one.
function planRestore(items) {
  const plan = {images: [], videos: [], refused: 0};
  const seen = new Set();
  for (const item of Array.isArray(items) ? items : []) {
    if (!validImport(item)) {
      plan.refused += 1;
      continue;
    }
    const key = item.workspace + '/' + item.id;
    if (seen.has(key)) {
      plan.refused += 1;
      continue;
    }
    seen.add(key);
    if (item.workspace === 'image') plan.images.push(rebuildImage(item));
    else plan.videos.push(rebuildVideo(item));
  }
  return plan;
}

function writeCounted(write, count) {
  return write().then(
    () => ({written: count, failed: 0}),
    error => ({written: 0, failed: count, error}),
  );
}

// The image database and the video database are two transactions, and neither can
// roll the other back. Each one settles on its own, and the counts say which records
// landed and which did not. The refused items are counted apart from a failed write,
// because only a failed write is worth another try.
async function restoreBundle(items) {
  const plan = planRestore(items);
  const total = plan.images.length + plan.videos.length;
  if (!page.keeping()) return {imported: 0, skipped: total + plan.refused, failed: 0};
  const [images, videos] = await Promise.all([
    writeCounted(() => inStore('readwrite', store => { plan.images.forEach(record => store.put(record)); }), plan.images.length),
    writeCounted(() => inVideoStore('readwrite', store => { plan.videos.forEach(record => store.put(record)); }), plan.videos.length),
  ]);
  // The tombstones go for what landed, so a later cross-tab write cannot delete what
  // the user just chose to bring back.
  if (images.written) plan.images.forEach(record => forgetImage(record.id));
  if (videos.written) plan.videos.forEach(record => forgetVideo(record.id));
  await load();
  if (videos.written) page.heard({kind: 'video-add'});
  return {
    imported: images.written + videos.written,
    skipped: plan.refused,
    failed: images.failed + videos.failed,
  };
}

function withoutMedia(record, fields) {
  const copy = {...record};
  fields.forEach(field => delete copy[field]);
  return copy;
}

function restoreMedia(item) {
  const media = {};
  for (const entry of item.media || []) if (entry.blob instanceof Blob) media[entry.role] = entry.blob;
  return media;
}

function rebuildImage(item) {
  const media = restoreMedia(item);
  const record = {...item.record, png: media.png};
  if (media.before) record.before = media.before;
  return record;
}

function rebuildVideo(item) {
  const media = restoreMedia(item);
  const record = {...item.record, mp4: media.mp4};
  if (media.thumbnail) record.thumbnail = media.thumbnail;
  return record;
}

const handle = {
  prepareForget, retainImages,
  hydrate: hydrate,
  videoRecord: id => inVideoStore('readonly', clips => clips.get(id)),
  keep: keep,
  keepVideo: keepVideo,
  keepVideoThumbnail: keepVideoThumbnail,
  collectBundle: collectBundle,
  restoreBundle: restoreBundle,
  forget: forget,
  load: load,
  loadVideos: loadVideos,
  removeVideo: removeVideo,
  clearVideos: clearVideos,
  announce: announce,
  blobOf: blobOf,
  fields: function () { return KEPT_FIELDS; },
  persisted: function () { return durable; },
  askForDurableStorage: askForDurableStorage,
  wasRemoved: wasRemoved,
  videoWasRemoved: videoWasRemoved,
};

document.dispatchEvent(new CustomEvent('store-ready', {
  detail: {
    configure: function (helpers) {
      page = helpers;
      return handle;
    },
  },
}));
