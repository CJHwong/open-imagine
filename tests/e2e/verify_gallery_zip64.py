"""A gallery past 65535 entries writes and reads a ZIP64 archive; no GPU.

The count is the trigger that can be built quickly. The size and offset fields take the
same extra records, and a 4 GB file is not something this suite can make.
uv run --with playwright python tests/e2e/verify_gallery_zip64.py <port>
"""

import os
import sys
import zipfile

from playwright.sync_api import sync_playwright

COUNT = 65_536
BASE = f"http://127.0.0.1:{int(sys.argv[1])}"

with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    page = browser.new_page(viewport={"width": 1200, "height": 800}, accept_downloads=True)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(BASE + "/")
    page.wait_for_function('typeof kept !== "undefined"')
    with page.expect_download(timeout=180000) as download:
        written = page.evaluate(
            """async count => {
              const {encodeBundle, saveBundle} = await import('/page/lib/gallery-bundle.js');
              const items = Array.from({length: count}, (_, index) => ({workspace: 'image', id: 'z' + index,
                at: index, record: {id: 'z' + index},
                media: [{role: 'png', blob: new Blob([new Uint8Array([index & 255])], {type: 'image/png'})}]}));
              const started = performance.now();
              const blob = await encodeBundle(items, Date.now());
              window.__zip64 = blob;
              saveBundle(blob, 'zip64-test.zip');
              return {ms: Math.round(performance.now() - started), bytes: blob.size};
            }""",
            COUNT,
        )
    path = download.value.path()
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        assert len(names) == COUNT + 1, len(names)
        assert archive.testzip() is None
        sample = archive.read(names[-1])
    print(
        f"PASS a {COUNT + 1} entry archive is a valid ZIP64 file "
        f"({written['ms']} ms, {os.path.getsize(path) / 1024 / 1024:.1f} MB).",
        flush=True,
    )
    read = page.evaluate(
        """async () => {
          const {decodeBundle} = await import('/page/lib/gallery-bundle.js');
          const started = performance.now();
          const back = await decodeBundle(window.__zip64);
          return {items: back.length, last: back.at(-1)?.id, byte: back.at(-1)?.media?.[0]?.blob?.size,
            ms: Math.round(performance.now() - started)};
        }"""
    )
    assert read["items"] == COUNT, read
    assert read["last"] == f"z{COUNT - 1}", read
    assert read["byte"] == 1, read
    assert sample == bytes([(COUNT - 1) & 255]), sample
    print(f"PASS the same archive reads back through the ZIP64 end record ({read['ms']} ms).", flush=True)
    assert errors == [], errors
    browser.close()
