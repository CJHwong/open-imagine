// Songs are separate records so concurrent tabs cannot overwrite one another's gallery.
let opening;
function database() {
  if (!opening) opening = new Promise((resolve, reject) => {
    const request = indexedDB.open('studio-music', 1);
    request.onupgradeneeded = () => {
      request.result.createObjectStore('songs', {keyPath: 'id'});
      request.result.createObjectStore('state');
    };
    request.onsuccess = () => { request.result.onversionchange = () => request.result.close(); resolve(request.result); };
    request.onerror = () => reject(request.error);
    request.onblocked = () => reject(new Error('Reload other Studio tabs to update Music storage.'));
  });
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
export async function clearMusic() {
  const db = await database();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(['songs', 'state'], 'readwrite');
    tx.objectStore('songs').clear();
    tx.objectStore('state').clear();
    tx.oncomplete = resolve;
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error);
  });
}
