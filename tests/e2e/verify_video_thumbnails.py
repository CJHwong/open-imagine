"""Video strips and gallery cards keep a static thumbnail when motion is disabled.

Run against a fresh CPU stub; the clip is a locally generated test pattern.
"""

import base64
import io
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image
from playwright.sync_api import expect, sync_playwright

BASE = "http://127.0.0.1:" + sys.argv[1]


def ready_image(page, selector):
    page.wait_for_function(
        "selector => [...document.querySelectorAll(selector)].some(image => image.complete && image.naturalWidth && image.getBoundingClientRect().height > 0)",
        arg=selector,
    )


def main():
    with tempfile.TemporaryDirectory() as scratch:
        path = Path(scratch) / "clip.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "testsrc2=size=256x144:rate=12",
                "-t",
                "2",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(path),
            ],
            check=True,
        )
        encoded = base64.b64encode(path.read_bytes()).decode()
    poster = io.BytesIO()
    Image.new("RGB", (128, 72), "orange").save(poster, format="PNG")
    poster_data = base64.b64encode(poster.getvalue()).decode()
    with sync_playwright() as tool:
        browser = tool.chromium.launch()
        for motion, stored in (("no-preference", False), ("reduce", False), ("reduce", True)):
            context = browser.new_context(viewport={"width": 1440, "height": 1000}, reduced_motion=motion)
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error, errors=errors: errors.append(str(error)))
            page.goto(BASE + "/api/v1/openapi.json")
            page.evaluate(
                """async ({encoded, poster}) => {
              const mp4 = new Blob([Uint8Array.from(atob(encoded), c => c.charCodeAt(0))], {type:'video/mp4'});
              const db = await new Promise((resolve, reject) => {
                const request = indexedDB.open('studio-video-gallery',1);
                request.onupgradeneeded = () => request.result.createObjectStore('clips',{keyPath:'id'});
                request.onsuccess = () => resolve(request.result); request.onerror = () => reject(request.error);
              });
              await new Promise((resolve, reject) => {
                const tx = db.transaction('clips','readwrite');
                tx.objectStore('clips').put({id:'thumbnail-test', name:'Synthetic thumbnail test', mp4,
                  duration:2, thumbnail:poster ? new Blob([Uint8Array.from(atob(poster), c => c.charCodeAt(0))],{type:'image/png'}) : null, createdAt:Date.now(), metadata:{prompt:'Synthetic test pattern', width:256,height:144,modelName:'Test'}});
                tx.oncomplete=resolve; tx.onerror=reject;
              }); db.close();
            }""",
                {"encoded": encoded, "poster": poster_data if stored else ""},
            )
            page.goto(BASE + "/?workspace=video&lang=en")
            strip = "#video-gallery .video-clip video-gallery-preview"
            page.locator(strip).wait_for(state="visible")
            if motion == "no-preference":
                page.wait_for_function("selector => Boolean(document.querySelector(selector)?.sheet)", arg=strip)
                page.emulate_media(reduced_motion="reduce")
            ready_image(page, strip + " img")
            expect(page.locator(strip + " .video-gallery-sheet")).to_have_count(0)
            if stored:
                assert page.locator(strip).evaluate("preview => Boolean(preview.poster)")
            page.emulate_media(reduced_motion="no-preference")
            page.wait_for_function("selector => Boolean(document.querySelector(selector)?.sheet)", arg=strip)
            held = []
            page.route("**/video/generate", lambda route, request, held=held: held.append(route))
            page.locator("#video-prompt").fill("A synthetic scene for the thumbnail regression.")
            with page.expect_request("**/video/generate"):
                page.locator("#video-generate").click()
            ready_image(page, strip + " img")
            expect(page.locator(strip + " .video-gallery-sheet")).to_have_count(0)
            held[0].abort()
            page.wait_for_function("!videoStudio.pendingRender")
            page.emulate_media(reduced_motion="reduce")
            page.locator('gallery-browser[workspace="video"] .gallery-browse-toggle').click()
            ready_image(page, 'gallery-browser[workspace="video"] .gallery-card video-gallery-preview img')
            assert not errors, errors
            print(
                f"PASS {motion}, stored poster={stored}: restored strip, preference changes, generation and expanded gallery keep thumbnails",
                flush=True,
            )
            context.close()
        browser.close()


if __name__ == "__main__":
    main()
