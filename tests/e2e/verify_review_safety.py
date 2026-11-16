"""Check imported archives and waveform tails against a fresh stub server.

Run: uv run --with playwright python tests/e2e/verify_review_safety.py <port>
"""

import base64
import io
import json
import struct
import sys
import warnings
import zipfile

from PIL import Image
from playwright.sync_api import sync_playwright


def archive(entries, compression=zipfile.ZIP_STORED):
    output = io.BytesIO()
    with warnings.catch_warnings(), zipfile.ZipFile(output, "w", compression=compression) as bundle:
        warnings.simplefilter("ignore", UserWarning)
        for name, content in entries:
            bundle.writestr(name, content)
    return output.getvalue()


picture = io.BytesIO()
Image.new("RGB", (16, 16), "red").save(picture, format="PNG")
backend = '<img data-import-injected src="invalid:" onerror="&#118;&#111;&#105;&#100;(0)">'
manifest = {
    "format": "studio-gallery",
    "version": 3,
    "items": [
        {
            "workspace": "image",
            "id": "review-import",
            "at": 1,
            "record": {
                "id": "review-import",
                "number": 1,
                "width": 16,
                "height": 16,
                "prompt": "Imported image",
                "backend": backend,
                "at": 1,
            },
            "media": [{"role": "png", "mime": "image/png", "file": "media/image.png"}],
        }
    ],
}
entries = [("gallery.json", json.dumps(manifest)), ("media/image.png", picture.getvalue())]
valid = archive(entries)
corrupt = bytearray(valid)
corrupt[valid.index(picture.getvalue()) + 20] ^= 1
unsafe_zip64 = bytearray(valid[:-22])
locator = struct.pack("<IIQI", 0x07064B50, 0, 2**63, 1)
end = bytearray(valid[-22:])
struct.pack_into("<H", end, 10, 0xFFFF)
unsafe_zip64 += locator + end
huge_manifest = bytearray(valid)
central = huge_manifest.index(b"PK\x01\x02")
struct.pack_into("<I", huge_manifest, central + 24, 17 * 1024 * 1024)
bomb = bytearray(archive([(entries[0][0], entries[0][1] + " " * (17 * 1024 * 1024)), entries[1]], zipfile.ZIP_DEFLATED))
struct.pack_into("<I", bomb, bomb.index(b"PK\x01\x02") + 24, 1)
cases = {
    "stored archive": (valid, False),
    "compressed archive": (archive(entries, zipfile.ZIP_DEFLATED), False),
    "corrupt media": (corrupt, True),
    "duplicate manifest": (archive([*entries, entries[0]]), True),
    "path traversal": (archive([*entries, ("../escape", b"x")]), True),
    "unsafe ZIP64 offset": (unsafe_zip64, True),
    "oversized manifest": (huge_manifest, True),
    "decompression budget": (bomb, True),
    "repeated references": (
        archive(
            [
                (
                    "gallery.json",
                    json.dumps(
                        {
                            **manifest,
                            "items": [{**manifest["items"][0], "media": manifest["items"][0]["media"] * 10001}],
                        }
                    ),
                ),
                entries[1],
            ]
        ),
        True,
    ),
    "invalid item list": (archive([("gallery.json", json.dumps({**manifest, "items": 1}))]), True),
}
failures = []
with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    page = browser.new_page()
    page.goto(f"http://127.0.0.1:{sys.argv[1]}/")
    page.wait_for_function("typeof window.restoreStudioBundle === 'function'")
    for name, (content, rejected) in cases.items():
        outcome = page.evaluate(
            """async encoded => {
            const {decodeBundle} = await import('/page/lib/gallery-bundle.js');
            const bytes = Uint8Array.from(atob(encoded), character => character.charCodeAt(0));
            try { return {items: (await decodeBundle(new Blob([bytes]))).length}; }
            catch (error) { return {rejected: Boolean(error.bundle)}; }
        }""",
            base64.b64encode(content).decode(),
        )
        passed = outcome.get("rejected") is True if rejected else outcome.get("items") == 1
        print(("PASS " if passed else "FAIL ") + name, flush=True)
        if not passed:
            failures.append(name)
    page.evaluate(
        """async encoded => {
        const {decodeBundle} = await import('/page/lib/gallery-bundle.js');
        const bytes = Uint8Array.from(atob(encoded), character => character.charCodeAt(0));
        await window.restoreStudioBundle(await decodeBundle(new Blob([bytes])));
    }""",
        base64.b64encode(valid).decode(),
    )
    page.wait_for_selector(".edge")
    safe_label = page.locator(".edge [data-import-injected]").count() == 0
    safe_label = safe_label and backend.upper().replace("-", " ") in page.locator(".edge").inner_text()
    print(("PASS " if safe_label else "FAIL ") + "imported label remains text", flush=True)
    if not safe_label:
        failures.append("imported label remains text")
    peaks = page.evaluate("""async () => {
        const {audioPeaks} = await import('/page/lib/voice-audio.js');
        return [79, 80, 81, 159, 160].map(length => {
            const samples = new Float32Array(length);
            samples[length - 1] = 1;
            return audioPeaks(samples).at(-1);
        });
    }""")
    passed = peaks == [1] * 5
    print(("PASS " if passed else "FAIL ") + "waveform includes every sample tail", flush=True)
    if not passed:
        failures.append("waveform includes every sample tail")
    browser.close()

if failures:
    raise SystemExit("Failed: " + ", ".join(failures))
