"""Music progress follows each phase; image progress remains monotonic.

Run against a fresh all-backends stub. No model is loaded.
"""

import sys
import time

from playwright.sync_api import expect, sync_playwright

base = f"http://127.0.0.1:{int(sys.argv[1])}"
with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    page = browser.new_page()
    state = page.request.get(base + "/api/v1/state").json()
    operation = {
        "id": "music-progress",
        "kind": "music",
        "workspace": "music",
        "status": "running",
        "mode": "cover",
        "model": "YuE2",
        "started_at": time.time(),
        "settings": {},
        "progress": {"stage": "running", "step": 1, "total": 1},
    }
    page.route("**/api/v1/state", lambda route: route.fulfill(json={**state, "active": operation}))
    page.goto(base + "/?workspace=music")
    percent = page.locator("#shared-operation-percent")
    expect(percent).to_have_text("99%")
    operation["progress"] = {"stage": "running", "step": 16, "total": 0}
    expect(percent).to_have_text("")
    operation["progress"] = {"stage": "running", "step": 1, "total": 32}
    expect(percent).to_have_text("3%")
    operation["progress"] = {"stage": "running", "step": 16, "total": 32}
    expect(percent).to_have_text("50%")
    operation["batch_total"] = 2
    operation["batch_index"] = 2
    operation["progress"] = {"stage": "preparing", "step": 0, "total": 0}
    expect(percent).to_have_text("")
    operation["progress"] = {"stage": "running", "step": 1, "total": 8}
    expect(percent).to_have_text("12%")
    operation.update(id="image-progress", kind="image", workspace="image", mode="edit")
    operation["progress"] = {"stage": "running", "step": 6, "total": 8}
    expect(percent).to_have_text("75%")
    operation["progress"] = {"stage": "running", "step": 1, "total": 8}
    # Observe the next snapshot before checking the percentage.
    operation["model"] = "Next image item"
    expect(page.locator("#shared-operation-detail")).to_contain_text("Next image item")
    expect(percent).to_have_text("75%")
    browser.close()
print("PASS Music phase progress, unknown token length, cover synthesis, batch reset, and monotonic image progress")
