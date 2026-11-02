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

from PIL import Image
from playwright.sync_api import expect, sync_playwright

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
    page.click("#theme-toggle")


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
        # restorable archive, and the titles say so.
        assert page.locator("#download-gallery").get_attribute("title") == (
            "Save every file in this shelf to this computer, one by one. Settings are not included."
        )
        page.locator("#image-gallery-browser .gallery-browse-toggle").click()
        page.get_by_role("button", name="Select", exact=True).click()
        page.locator(".gallery-check input").first.check()
        assert page.get_by_role("button", name="Download 1", exact=True).get_attribute("title") == (
            "Save the checked files to this computer, one by one. Settings are not included."
        )
        page.get_by_role("button", name="Done", exact=True).click()
        page.locator("#image-gallery-browser .gallery-browse-toggle").click()
        open_menu(page)
        assert page.get_by_role("menuitem", name="Export", exact=True).get_attribute("title") == (
            "Save the whole gallery as one ZIP, records and media together, to restore in another browser."
        )
        with page.expect_download(timeout=60000) as download:
            page.get_by_role("menuitem", name="Export", exact=True).click()
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
            target.get_by_role("menuitem", name="Import", exact=True).click()
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
            reader.get_by_role("menuitem", name="Import", exact=True).click()
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
            reader.get_by_role("menuitem", name="Import", exact=True).click()
        chooser.value.set_files(version2)
        reader.wait_for_function("gallery.length === 2")
        print("PASS a version 2 bundle still imports.", flush=True)
        assert errors == [], errors
        older.close()
        fresh.close()
        browser.close()


if __name__ == "__main__":
    main()
