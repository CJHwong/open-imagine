// Songs are separate records so concurrent tabs cannot overwrite one another's gallery.
// A song that came from a reference recording also points at the bytes of that recording.
// The bytes live once, keyed by their SHA-256, so ten covers of one hum keep one copy.
let opening;
function database() {
  if (!opening) {
    opening = new Promise((resolve, reject) => {
      const request = indexedDB.open('studio-music', 2);
      // The upgrade runs for every version bump, so create only what is missing. Creating
      // 'songs' again at version 2 throws ConstraintError and fails the open for good.
      request.onupgradeneeded = () => {
        const result = request.result;
        if (!result.objectStoreNames.contains('songs')) result.createObjectStore('songs', {keyPath: 'id'});
        if (!result.objectStoreNames.contains('state')) result.createObjectStore('state');
        if (!result.objectStoreNames.contains('sources')) result.createObjectStore('sources', {keyPath: 'id'});
        // The link from an operation to its source, so the tab that imports the song can
        // find the recording even when it did not start the run.
        if (!result.objectStoreNames.contains('links')) result.createObjectStore('links', {keyPath: 'id'});
      };
      request.onsuccess = () => {
        const result = request.result;
        // Another tab upgraded the database: close, and open again on the next call
        // instead of keeping a dead handle.
        result.onversionchange = () => { result.close(); opening = undefined; };
        resolve(result);
      };
      request.onerror = () => reject(request.error);
      request.onblocked = () => reject(new Error('Reload other Studio tabs to update Music storage.'));
    });
    // A rejected open must not poison every later call.
    opening.catch(() => { opening = undefined; });
  }
  return opening;
}
async function transaction(store, mode, action) {
  const db = await database();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(store, mode);
    const request = action(tx.objectStore(store));
    tx.oncomplete = () => resolve(request?.result);
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error || new Error('Music storage was interrupted.'));
  });
}
export const musicSongs = () => transaction('songs', 'readonly', store => store.getAll());
// Initial imports are insert-only and return the durable record, including any cover.
// Saving and deleting share a transaction with permanent per-id tombstones. A late
// operation importer in another tab cannot bring back a recording the user deleted.
export async function saveMusicSong(song) {
  const db = await database();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(['songs', 'state'], 'readwrite');
    const check = tx.objectStore('state').get('removed:' + song.id);
    let saved = null;
    check.onsuccess = () => {
      if (check.result) return;
      const existing = tx.objectStore('songs').get(song.id);
      existing.onsuccess = () => {
        try {
          saved = existing.result || song;
          if (!existing.result) tx.objectStore('songs').put(song);
        } catch (error) { tx.abort(); reject(error); }
      };
    };
    tx.oncomplete = () => resolve(saved);
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error || new Error('Music save was interrupted.'));
  });
}
// The delete stays synchronous on purpose: a caller that patches ObjectStore.delete
// sees its throw at once, and the card that could not be removed stays on the page.
// Unused reference recordings are removed by sweepMusicSources afterwards.
export async function deleteMusicSong(id) {
  const db = await database();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(['songs', 'state'], 'readwrite');
    try {
      tx.objectStore('state').put(true, 'removed:' + id);
      tx.objectStore('songs').delete(id);
    } catch (error) { tx.abort(); reject(error); }
    tx.oncomplete = resolve;
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error || new Error('Music deletion was interrupted.'));
  });
}
export const musicDraft = () => transaction('state', 'readonly', store => store.get('draft'));

// Conditional updates keep a late cover result from overwriting another tab's
// newer cover request, or resurrecting a recording that was deleted.
export async function updateMusicSong(id, update) {
  const db = await database();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(['songs', 'state'], 'readwrite');
    const removed = tx.objectStore('state').get('removed:' + id);
    let saved = null;
    removed.onsuccess = () => {
      if (removed.result) return;
      const request = tx.objectStore('songs').get(id);
      request.onsuccess = () => {
        if (!request.result) return;
        try {
          const next = update(request.result);
          if (next) { tx.objectStore('songs').put(next); saved = next; }
        } catch (error) { tx.abort(); reject(error); }
      };
    };
    tx.oncomplete = () => resolve(saved);
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error || new Error('Music update was interrupted.'));
  });
}
export const saveMusicDraft = draft => transaction('state', 'readwrite', store => store.put(draft, 'draft'));
export const musicSource = id => transaction('sources', 'readonly', store => store.get(id));
export const putMusicSource = source => transaction('sources', 'readwrite', store => store.put(source));
export const musicLink = id => transaction('links', 'readonly', store => store.get(id));
// A link names the source an unfinished run will claim. It carries the time it was
// written, because the sweep keeps that source alive until the link expires.
export const putMusicLink = link => transaction('links', 'readwrite', store => store.put({...link, at: Date.now()}));
export const deleteMusicLink = id => transaction('links', 'readwrite', store => store.delete(id));

// The same bytes always get the same id, so one recording is one record. crypto.subtle
// needs a secure context, which localhost and HTTPS have; outside one the id is random
// and identical recordings keep separate copies.
export async function sourceIdFor(blob) {
  if (globalThis.crypto?.subtle) {
    const digest = await crypto.subtle.digest('SHA-256', await blob.arrayBuffer());
    return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
  }
  return Date.now().toString(36) + Math.random().toString(36).slice(2);
}

// A run empties the form before it imports, so its recording has no draft and no song for
// a while. The link is the user during that window. A link older than this belongs to a
// tab that never came back, so it and its source go.
const LINK_LIFETIME = 60 * 60 * 1000;

// One transaction, so no song inserted before it started can lose its source. A write
// that lands afterwards is re-checked by the tab that made the song. The draft counts as
// a user of a source: it restores the form after a reload. The links count too, until
// they expire. Nothing is deleted before all three reads finish.
export async function sweepMusicSources() {
  const db = await database();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(['songs', 'sources', 'state', 'links'], 'readwrite');
    const linksStore = tx.objectStore('links');
    const used = new Set();
    let waiting = 3;
    const prune = () => {
      if (--waiting) return;
      const keys = tx.objectStore('sources').getAllKeys();
      keys.onsuccess = () => {
        for (const id of keys.result) if (!used.has(id)) tx.objectStore('sources').delete(id);
      };
    };
    const draft = tx.objectStore('state').get('draft');
    draft.onsuccess = () => {
      const id = draft.result?.reference?.sourceId;
      if (id) used.add(id);
      prune();
    };
    draft.onerror = prune;
    const songs = tx.objectStore('songs').getAll();
    songs.onsuccess = () => {
      for (const song of songs.result) if (song.sourceId) used.add(song.sourceId);
      prune();
    };
    songs.onerror = prune;
    const links = linksStore.getAll();
    links.onsuccess = () => {
      const now = Date.now();
      for (const link of links.result) {
        if (now - (link.at || 0) < LINK_LIFETIME) used.add(link.sourceId);
        else linksStore.delete(link.id);
      }
      prune();
    };
    links.onerror = prune;
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error || new Error('Music storage cleanup was interrupted.'));
  });
}
export async function clearMusic() {
  const db = await database();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(['songs', 'sources', 'state', 'links'], 'readwrite');
    tx.objectStore('songs').clear();
    tx.objectStore('sources').clear();
    tx.objectStore('state').clear();
    tx.objectStore('links').clear();
    tx.oncomplete = resolve;
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error);
  });
}
