"""Video rejects PNG reference payloads that exceed its existing request budget.

uv run --with playwright python tests/e2e/verify_image_import_budget.py <port>
Run against a fresh all-backend stub. The photographs are synthetic noise.
"""

import io
import sys

import numpy as np
from PIL import Image
from playwright.sync_api import expect, sync_playwright


def noise_photo(name, side):
    pixels = np.random.default_rng(7).integers(0, 256, (side, side, 3), dtype=np.uint8)
    output = io.BytesIO()
    Image.fromarray(pixels).save(output, format="JPEG", quality=95, subsampling=0)
    assert len(output.getvalue()) < 64 * 1024 * 1024
    return {"name": name, "mimeType": "image/jpeg", "buffer": output.getvalue()}


def choose(page, photo, original):
    page.locator("#video-media-upload").set_input_files(photo)
    dialog = page.locator("#image-import-dialog")
    expect(dialog).to_be_visible()
    if original:
        dialog.get_by_role("button", name="Use original resolution", exact=True).click()
    else:
        dialog.locator(".image-import-resize").click()


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 1000})
        page.add_init_script("localStorage.setItem('studio-keep','off')")
        page.goto("http://127.0.0.1:" + sys.argv[1] + "/?workspace=video")
        submissions = []
        page.on(
            "request",
            lambda request: submissions.append(request.url) if request.url.endswith("/video/generate") else None,
        )
        oversized = noise_photo("oversized.jpg", 4096)
        choose(page, oversized, original=True)
        alert = page.locator("#toasts").get_by_role("alert")
        expect(alert).to_contain_text("import this image again and choose Resize", timeout=20000)
        assert page.locator("#video-studio").evaluate("studio=>studio.imageReferences.length") == 0
        alert.get_by_role("button", name="Dismiss", exact=True).click()
        first = noise_photo("first.jpg", 3000)
        choose(page, first, original=True)
        expect(page.locator("#video-references .video-reference img")).to_have_js_property("naturalWidth", 3000)
        choose(page, {**first, "name": "second.jpg"}, original=True)
        expect(alert).to_contain_text("import this image again and choose Resize", timeout=20000)
        references = page.locator("#video-studio").evaluate(
            "studio=>studio.imageReferences.map(reference=>reference.name)"
        )
        assert references == ["first.jpg"], references
        alert.get_by_role("button", name="Dismiss", exact=True).click()
        choose(page, oversized, original=False)
        expect(page.locator("#video-references .video-reference img")).to_have_count(2)
        expect(page.locator("#video-references .video-reference img").last).to_have_js_property("naturalWidth", 2048)
        assert not submissions, submissions
        browser.close()
    print("PASS Video single/cumulative payload bounds preserve references and accept the recommended resize")


if __name__ == "__main__":
    main()
