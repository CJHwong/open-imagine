"""The whole gallery leaves as one gzipped file and returns in a fresh browser.

Run against a fresh `uv run studio --stub --port <port>`. No model is loaded.

uv run --with playwright python tests/e2e/verify_gallery_transfer.py <port>
"""

import base64
import gzip
import io
import json
import sys
import tempfile
import wave
import zipfile
from pathlib import Path

from help_controls import visible_description
from PIL import Image
from playwright.sync_api import expect, sync_playwright
from settings_controls import open_settings

PORT = int(sys.argv[1])
URL = f"http://127.0.0.1:{PORT}"


def png_bytes():
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), (200, 80, 40)).save(buffer, format="PNG")
    return buffer.getvalue()


def wav_bytes(stereo):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as track:
        track.setnchannels(2 if stereo else 1)
        track.setsampwidth(2)
        track.setframerate(48000)
        track.writeframes(b"\x00\x00" * (48000 if stereo else 24000))
    return buffer.getvalue()


def seed(page, blobs):
    page.evaluate(
        """async ({png, wav, music, clip}) => {
          const blob = (data, type) => new Blob(
            [Uint8Array.from(atob(data), value => value.charCodeAt(0))], {type});
          const open = (name, version, stores) => new Promise((resolve, reject) => {
            const request = indexedDB.open(name, version);
            request.onupgradeneeded = () => {
              for (const [store, options] of stores) {
                if (!request.result.objectStoreNames.contains(store)) {
                  request.result.createObjectStore(store, options);
                }
              }
            };
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
          });
          const put = (db, store, value, key) => new Promise((resolve, reject) => {
            const tx = db.transaction(store, 'readwrite');
            key === undefined ? tx.objectStore(store).put(value) : tx.objectStore(store).put(value, key);
            tx.oncomplete = resolve; tx.onerror = () => reject(tx.error);
          });
          const now = Date.now();
          const images = await open('studio', 1, [['images', {keyPath: 'id'}]]);
          await put(images, 'images', {id: 101, number: 1, mode: 'generate', prompt: 'Seeded image',
            seed: 1, width: 8, height: 8, steps: 1, at: now, backend: 'Stub', backendId: 'stub',
            precision: '', png: blob(png, 'image/png')});
          images.close();
          const videos = await open('studio-video-gallery', 1, [['clips', {keyPath: 'id'}]]);
          await put(videos, 'clips', {id: 'v-1', name: 'Seeded clip', duration: 1,
            metadata: {prompt: 'Seeded clip', width: 8, height: 8, modelName: 'Stub'},
            createdAt: now, mp4: blob(clip, 'video/mp4')});
          videos.close();
          const voice = await open('studio-voice', 2, [['state', {}], ['media', {}]]);
          await put(voice, 'state', {segments: [{id: 'seg-1', text: 'Seeded take', inScript: false,
            selected: 'take-1', takes: [{id: 'take-1', text: 'Seeded take', createdAt: now, duration: 0.5,
              model: 'Stub', mode: 'generate', seed: 1, peaks: [0.1, 0.2], stored: true}]}],
            selectedId: 'take-1', removed: [], cutoff: 0}, 'project');
          await put(voice, 'media', blob(wav, 'audio/wav'), 'take-1');
          voice.close();
          const musicDb = await open('studio-music', 2, [['songs', {keyPath: 'id'}], ['state', {}],
            ['sources', {keyPath: 'id'}], ['links', {keyPath: 'id'}]]);
          await put(musicDb, 'songs', {id: 'song-1', blob: blob(music, 'audio/wav'), title: 'Seeded song',
            seconds: 0.5, seed: 1, createdAt: now, score: '', settings: {style: 'piano'},
            model: 'YuE2', metadata: {}});
          musicDb.close();
        }""",
        blobs,
    )


def open_menu(page):
    open_settings(page, "library")


def import_file(page, path, text):
    page.evaluate("document.getElementById('toasts').clear()")
    open_menu(page)
    with page.expect_file_chooser() as chooser:
        page.get_by_role("button", name="Import", exact=True).click()
        page.keyboard.press("Escape")
    chooser.value.set_files(path)
    expect(page.locator("#toasts")).to_contain_text(text)


def remove_selected(page, workspace, empty):
    page.locator(f"#media-{workspace}-mode").click()
    gallery = page.locator(f'gallery-browser[workspace="{workspace}"]')
    # The page keeps each workspace's open panel across a reload, so the toggle is
    # pressed only when it is closed and the mode is cleared only when it is on.
    if not gallery.evaluate("el => el.expanded"):
        gallery.locator(".gallery-browse-toggle").click()
    if gallery.evaluate("el => el.selecting"):
        gallery.get_by_role("button", name="Deselect", exact=True).click()
    gallery.get_by_role("button", name="Select", exact=True).click()
    gallery.locator(".gallery-check input").first.check()
    page.once("dialog", lambda dialog: dialog.accept())
    gallery.get_by_role("button", name="Remove 1", exact=True).click()
    page.wait_for_function(empty)
    page.keyboard.press("Escape")


def broken_bundle(path, png, cases):
    """A version 3 archive whose manifest items break one rule each."""
    items = []
    with zipfile.ZipFile(path, "w") as archive:
        for index, case in enumerate(cases):
            item = dict(case["item"])
            if case["role"] is None:
                item["media"] = []
            else:
                name = f"media/{index}.png"
                archive.writestr(name, png)
                item["media"] = [{"role": case["role"], "mime": case["mime"], "file": name, "size": len(png)}]
            items.append(item)
        archive.writestr(
            "gallery.json", json.dumps({"format": "studio-gallery", "version": 3, "exportedAt": 0, "items": items})
        )


def main():
    blobs = {
        "png": base64.b64encode(png_bytes()).decode(),
        "wav": base64.b64encode(wav_bytes(False)).decode(),
        "music": base64.b64encode(wav_bytes(True)).decode(),
        "clip": base64.b64encode(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64).decode(),
    }
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(URL)
        page.wait_for_function("Boolean(document.querySelector('music-studio')?.capabilities)")
        seed(page, blobs)
        page.reload()
        page.wait_for_function(
            "gallery.length === 1 && videoStudio.clips.length === 1 "
            "&& document.querySelector('voice-studio').takesCount === 1 "
            "&& document.querySelector('music-studio').songs.length === 1"
        )
        # The menu names the difference: a download gives files, Export gives the
        # restorable archive. The control's visible description states which one it writes.
        assert "Download all media as one ZIP file." in visible_description(page.locator("#download-gallery"))
        page.locator("#image-gallery-browser .gallery-browse-toggle").click()
        page.get_by_role("button", name="Select", exact=True).click()
        page.locator(".gallery-check input").first.check()
        assert "Download selected media as one ZIP file." in visible_description(
            page.get_by_role("button", name="Download 1", exact=True)
        )
        page.get_by_role("button", name="Done", exact=True).click()
        page.locator("#image-gallery-browser .gallery-browse-toggle").click()
        open_menu(page)
        assert visible_description(page.get_by_role("button", name="Export", exact=True)) == (
            "Export the whole gallery as one ZIP with records and media. Import it in another browser to restore it."
        )
        with page.expect_download(timeout=60000) as download:
            page.get_by_role("button", name="Export", exact=True).click()
            page.keyboard.press("Escape")
        saved = download.value
        assert saved.suggested_filename.startswith("studio-gallery-"), saved.suggested_filename
        assert saved.suggested_filename.endswith(".zip"), saved.suggested_filename
        # Version 3 is a ZIP: gallery.json holds the records, media/ holds the raw
        # files. Nothing is base64, and each file opens on its own.
        with zipfile.ZipFile(saved.path()) as archive:
            manifest = json.loads(archive.read("gallery.json"))
            assert manifest["format"] == "studio-gallery" and manifest["version"] == 3, manifest
            bundle_items = manifest["items"]
            workspaces = sorted(item["workspace"] for item in bundle_items)
            assert workspaces == ["image", "music", "video", "voice"], workspaces
            roles = {item["workspace"]: sorted(entry["role"] for entry in item["media"]) for item in bundle_items}
            assert roles == {"image": ["png"], "video": ["mp4"], "music": ["audio"], "voice": ["audio"]}, roles
            for item in bundle_items:
                for entry in item["media"]:
                    assert entry["file"].startswith("media/"), entry
                    body = archive.read(entry["file"])
                    assert body and len(body) == entry["size"], (entry, len(body))
            assert archive.testzip() is None
        print("PASS gallery export: one ZIP with a manifest and four workspaces of raw media.", flush=True)

        fresh = browser.new_context(viewport={"width": 1440, "height": 1000})
        target = fresh.new_page()
        target.on("pageerror", lambda error: errors.append(str(error)))
        target.goto(URL)
        target.wait_for_function("Boolean(document.querySelector('music-studio')?.capabilities)")
        # An import usually starts with no images, so the settings menu carries it
        # as well as the gallery browser does.
        open_menu(target)
        with target.expect_file_chooser() as chooser:
            target.get_by_role("button", name="Import", exact=True).click()
            target.keyboard.press("Escape")
        chooser.value.set_files(saved.path())
        expect(target.locator("#toasts")).to_contain_text("Imported 4 items")
        target.wait_for_function(
            "gallery.length === 1 && videoStudio.clips.length === 1 "
            "&& document.querySelector('voice-studio').takesCount === 1 "
            "&& document.querySelector('music-studio').songs.length === 1"
        )
        print("PASS gallery import: every workspace returns in a fresh browser.", flush=True)

        target.reload()
        target.wait_for_function(
            "gallery.length === 1 && videoStudio.clips.length === 1 "
            "&& document.querySelector('voice-studio').takesCount === 1 "
            "&& document.querySelector('music-studio').songs.length === 1"
        )
        print("PASS gallery import survives a reload from the stores.", flush=True)

        # An explicit Import is the user's own choice. The tombstones that hide a deleted
        # item from another tab must not hide it here, and they go with the import.
        remove_selected(target, "image", "gallery.length === 0")
        remove_selected(target, "video", "videoStudio.clips.length === 0")
        # The voice studio skips a take it already holds, so only the image and the clip
        # count as imported here. Its own rule is not this check's subject.
        import_file(target, saved.path(), "Imported")
        target.wait_for_function("gallery.length === 1 && videoStudio.clips.length === 1")
        target.reload()
        target.wait_for_function("gallery.length === 1 && videoStudio.clips.length === 1")
        print("PASS an explicit import brings back what this browser deleted.", flush=True)

        # A malformed record must change nothing: every item is refused before a store
        # is opened, and the toast names the count.
        fuzz = Path(tempfile.mkdtemp()) / "fuzz.zip"
        broken_bundle(
            fuzz,
            png_bytes(),
            [
                {"item": {"workspace": "image", "id": 1001, "at": 0}, "role": "png", "mime": "image/png"},
                {
                    "item": {"workspace": "image", "id": 1002, "at": 0, "record": {"id": 9999}},
                    "role": "png",
                    "mime": "image/png",
                },
                {
                    "item": {"workspace": "unknown", "id": 1003, "at": 0, "record": {"id": 1003}},
                    "role": "png",
                    "mime": "image/png",
                },
                {
                    "item": {"workspace": "image", "id": 1004, "at": 0, "record": {"id": 1004}},
                    "role": "mp4",
                    "mime": "video/mp4",
                },
                {"item": {"workspace": "image", "id": 1005, "at": 0, "record": {"id": 1005}}, "role": None, "mime": ""},
            ],
        )
        import_file(target, fuzz, "Imported 0 items, skipped 5")
        assert target.evaluate("gallery.length") == 1, "a malformed item reached the image store"
        assert target.evaluate("videoStudio.clips.length") == 1, "a malformed item reached the clip store"
        print("PASS a malformed manifest is refused before any store is touched.", flush=True)

        # The image store and the clip store are separate transactions, so one can fail
        # while the other lands. The toast says how many landed, how many did not, and the
        # same file imported again is the retry.
        remove_selected(target, "image", "gallery.length === 0")
        remove_selected(target, "video", "videoStudio.clips.length === 0")
        target.evaluate("""() => {
          window.__put = IDBObjectStore.prototype.put;
          IDBObjectStore.prototype.put = function (value, key) {
            if (this.name === 'clips') throw new DOMException('Injected write failure', 'QuotaExceededError');
            return window.__put.call(this, value, key);
          };
        }""")
        import_file(target, saved.path(), "1 failed")
        target.wait_for_function("gallery.length === 1 && videoStudio.clips.length === 0")
        target.evaluate("() => { IDBObjectStore.prototype.put = window.__put; }")
        # The image landed before the clip store failed, so this retry replaces it.
        import_file(target, saved.path(), "replaced")
        target.wait_for_function("gallery.length === 1 && videoStudio.clips.length === 1")
        print("PASS a partial import reports its counts and imports again clean.", flush=True)

        # The export pages the two gallery stores. A getAll over either one is made to
        # fail while the gallery leaves, and the archive still arrives whole.
        target.evaluate("""() => {
          window.__getAll = IDBObjectStore.prototype.getAll;
          IDBObjectStore.prototype.getAll = function () {
            if (this.name === 'images' || this.name === 'clips') throw new Error('the export must page');
            return window.__getAll.call(this);
          };
        }""")
        open_menu(target)
        with target.expect_download(timeout=60000) as paged:
            target.get_by_role("button", name="Export", exact=True).click()
            target.keyboard.press("Escape")
        target.evaluate("() => { IDBObjectStore.prototype.getAll = window.__getAll; }")
        with zipfile.ZipFile(paged.value.path()) as archive:
            packed = archive.namelist()
        assert "gallery.json" in packed, packed
        assert len([name for name in packed if name.startswith("media/")]) == 4, packed
        print("PASS the export pages both stores instead of one getAll.", flush=True)

        # Version 1 wrote one JSON object. A file from that build must still land.
        legacy = Path(tempfile.mkdtemp()) / "legacy-v1.json.gz"
        legacy.write_bytes(
            gzip.compress(
                json.dumps(
                    {
                        "format": "studio-gallery",
                        "version": 1,
                        "exportedAt": 0,
                        "items": [
                            {
                                "workspace": "image",
                                "id": 901,
                                "at": 0,
                                "record": {
                                    "id": 901,
                                    "number": 1,
                                    "mode": "generate",
                                    "prompt": "Legacy image",
                                    "seed": 1,
                                    "width": 8,
                                    "height": 8,
                                    "steps": 1,
                                    "at": 0,
                                    "backend": "Stub",
                                    "backendId": "stub",
                                    "precision": "",
                                },
                                "media": [
                                    {"role": "png", "mime": "image/png", "data": base64.b64encode(png_bytes()).decode()}
                                ],
                            }
                        ],
                    }
                ).encode()
            )
        )
        older = browser.new_context(viewport={"width": 1440, "height": 1000})
        reader = older.new_page()
        reader.on("pageerror", lambda error: errors.append(str(error)))
        reader.goto(URL)
        reader.wait_for_function("Boolean(document.querySelector('music-studio')?.capabilities)")
        open_menu(reader)
        with reader.expect_file_chooser() as chooser:
            reader.get_by_role("button", name="Import", exact=True).click()
            reader.keyboard.press("Escape")
        chooser.value.set_files(legacy)
        expect(reader.locator("#toasts")).to_contain_text("Imported 1 items")
        reader.wait_for_function("gallery.length === 1")
        print("PASS a version 1 bundle still imports.", flush=True)

        # Version 2 wrote line-delimited JSON. It must still land as well.
        version2 = Path(tempfile.mkdtemp()) / "legacy-v2.json.gz"
        item = {
            "workspace": "image",
            "id": 902,
            "at": 0,
            "record": {"id": 902, "number": 2, "at": 0},
            "media": [{"role": "png", "mime": "image/png", "data": base64.b64encode(png_bytes()).decode()}],
        }
        version2.write_bytes(
            gzip.compress(
                (
                    json.dumps({"format": "studio-gallery", "version": 2, "exportedAt": 0})
                    + "\n"
                    + json.dumps(item)
                    + "\n"
                ).encode()
            )
        )
        open_menu(reader)
        with reader.expect_file_chooser() as chooser:
            reader.get_by_role("button", name="Import", exact=True).click()
            reader.keyboard.press("Escape")
        chooser.value.set_files(version2)
        reader.wait_for_function("gallery.length === 2")
        print("PASS a version 2 bundle still imports.", flush=True)

        # A scan of many records reads the tombstone list once, not once per record:
        # another tab's write arrives as a storage event and re-reads it a single time.
        target.evaluate("""async () => {
          const open = () => new Promise((resolve, reject) => {
            const request = indexedDB.open('studio', 1);
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
          });
          const database = await open();
          await new Promise((resolve, reject) => {
            const transaction = database.transaction('images', 'readwrite');
            const png = new Blob([new Uint8Array(8)], {type: 'image/png'});
            for (let id = 5000; id < 5064; id++) {
              transaction.objectStore('images').put({id, number: id, at: 1, png});
            }
            transaction.oncomplete = resolve;
            transaction.onerror = () => reject(transaction.error);
          });
          database.close();
          localStorage.setItem('studio-removed-images',
            JSON.stringify(Array.from({length: 2048}, (_, index) => 'gone-' + index)));
          localStorage.setItem('studio-images-cleared-at', '0');
          window.dispatchEvent(new StorageEvent('storage', {key: 'studio-removed-images'}));
          window.__tombstoneReads = 0;
          const getItem = Storage.prototype.getItem;
          Storage.prototype.getItem = function (key) {
            const name = String(key);
            if (name.startsWith('studio-removed-') || name.startsWith('studio-restored-')
              || name.endsWith('-cleared-at')) window.__tombstoneReads += 1;
            return getItem.call(this, key);
          };
          try { await kept.load(); } finally { Storage.prototype.getItem = getItem; }
          localStorage.removeItem('studio-removed-images');
          localStorage.removeItem('studio-images-cleared-at');
        }""")
        reads = target.evaluate("window.__tombstoneReads")
        assert reads <= 6, f"the tombstone list was read {reads} times for 64 records"
        print(f"PASS a 64 record scan reads the tombstones {reads} times, not 64.", flush=True)
        assert errors == [], errors
        older.close()
        fresh.close()
        browser.close()


if __name__ == "__main__":
    main()
