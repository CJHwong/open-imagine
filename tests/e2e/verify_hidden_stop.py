"""The page stops another client's private run, and learns nothing about it.

Run against a fresh all-backends stub: `python tests/e2e/verify_hidden_stop.py <port> [shots dir]`.
"""

import sys
import time
import uuid
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

URL = f"http://127.0.0.1:{sys.argv[1]}"
SHOTS = Path(sys.argv[2]) if len(sys.argv) > 2 else None
KEY = {"X-Studio-Private-Key": "hidden-stop-" + uuid.uuid4().hex}
CANARY = "hidden canary " + uuid.uuid4().hex[:12]


def start_private(request):
    # Four stub images take about 32 seconds, so each check stops a run that still holds the GPU.
    answer = request.post(URL + "/api/v1/operations", data={"kind": "image", "prompt": CANARY, "count": 4}, headers=KEY)
    assert answer.status == 202, answer.text()
    operation = answer.json()
    assert status(request, operation) == "running"
    return operation


def status(request, operation):
    return request.get(URL + operation["status_url"], headers=KEY).json()["status"]


def shot(page, name):
    if SHOTS is not None:
        page.screenshot(path=str(SHOTS / name))


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1280, "height": 850})
    page.goto(URL + "/?lang=en")
    page.wait_for_function("typeof formApi !== 'undefined' && Boolean(formApi)")
    bar = page.locator("#shared-operation")
    cancel = page.locator("#shared-operation-cancel")
    assert bar.is_hidden()

    operation = start_private(page.request)
    page.locator("#shared-operation[data-status=hidden]").wait_for()
    expect(page.locator("#shared-operation-label")).to_have_text("Studio is busy with another task")
    expect(page.locator("#shared-operation-detail")).to_have_text("This page cannot view that task's content.")
    assert page.locator("#shared-operation-percent").inner_text() == ""
    assert page.locator("#shared-operation-elapsed").inner_text() == ""
    assert page.locator("#shared-operation-details").is_hidden()
    assert cancel.is_enabled()
    assert bar.get_attribute("data-operation-id") == ""
    assert CANARY not in page.content()
    assert page.evaluate("sharedOperation") is None
    shot(page, "hidden-desktop.png")
    print("PASS a private run shows only as busy with another client, with no prompt, id or progress", flush=True)

    page.set_viewport_size({"width": 390, "height": 844})
    box = cancel.bounding_box()
    assert box and box["y"] >= 0 and box["y"] + box["height"] <= 844 and box["x"] + box["width"] <= 390, box
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    shot(page, "hidden-mobile.png")
    cancel.click()
    expect(page.locator("#shared-operation-label")).to_have_text("Stopping")
    expect(cancel).to_be_disabled()
    bar.wait_for(state="hidden", timeout=30000)
    assert status(page.request, operation) == "cancelled"
    print("PASS the mobile bar keeps Cancel on screen, shows Stopping, and the private run ends cancelled", flush=True)

    # The run can end between the poll and the press. The bar says so and stays usable.
    operation = start_private(page.request)
    page.locator("#shared-operation[data-status=hidden]").wait_for()
    page.route(
        "**/hidden/cancel", lambda route: route.fulfill(status=409, json={"error": "No hidden operation is running."})
    )
    cancel.click()
    expect(page.locator(".toast", has_text="No hidden operation is active now.")).to_be_visible()
    expect(cancel).to_be_enabled()
    assert status(page.request, operation) == "running"
    page.unroute("**/hidden/cancel")
    cancel.click()
    bar.wait_for(state="hidden", timeout=30000)
    assert status(page.request, operation) == "cancelled"
    print("PASS a press that arrives after the run ended reports it and leaves Cancel usable", flush=True)

    touch = browser.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True, locale="zh-TW")
    phone = touch.new_page()
    phone.goto(URL + "/?lang=zh-TW")
    phone.wait_for_function("typeof formApi !== 'undefined' && Boolean(formApi)")
    operation = start_private(phone.request)
    phone.locator("#shared-operation[data-status=hidden]").wait_for()
    expect(phone.locator("#shared-operation-label")).to_have_text("Studio 正在執行其他工作")
    assert phone.evaluate("document.documentElement.scrollWidth <= innerWidth")
    shot(phone, "hidden-mobile-zh.png")
    phone.locator("#shared-operation-cancel").tap()
    phone.locator("#shared-operation").wait_for(state="hidden", timeout=30000)
    assert status(phone.request, operation) == "cancelled"
    print("PASS a touch press stops the private run from the Traditional Chinese phone page", flush=True)

    # A new hidden run can start before the page sees an idle poll. Stopping must not lock it out.
    busy = {"active": None, "busy": True, "operations": []}
    page.route("**/api/v1/state", lambda route: route.fulfill(json=busy))
    page.route("**/hidden/cancel", lambda route: route.fulfill(status=204, body=""))
    page.locator("#shared-operation[data-status=hidden]").wait_for()
    pressed = time.monotonic()
    cancel.click()
    expect(page.locator("#shared-operation-label")).to_have_text("Stopping")
    expect(cancel).to_be_disabled()
    expect(cancel).to_be_enabled(timeout=15000)
    assert time.monotonic() - pressed >= 9, time.monotonic() - pressed
    expect(page.locator("#shared-operation-label")).to_have_text("Studio is busy with another task")
    print("PASS Stopping lasts about ten seconds, then Cancel works again for the next hidden run", flush=True)

    # A visible operation after a hidden one brings Details back and names its own id.
    visible = {
        "id": "visible-after-hidden",
        "kind": "image",
        "workspace": "image",
        "status": "running",
        "mode": "generate",
        "model": "Stub",
        "started_at": time.time(),
        "settings": {},
        "client_id": "another-tab",
        "progress": {"stage": "running", "step": 1, "total": 8},
    }
    page.unroute("**/api/v1/state")
    page.route("**/api/v1/state", lambda route: route.fulfill(json={**busy, "active": visible}))
    page.locator("#shared-operation[data-operation-id=visible-after-hidden]").wait_for()
    expect(page.locator("#shared-operation-details")).to_be_visible()
    page.unroute("**/api/v1/state")
    page.unroute("**/hidden/cancel")
    print("PASS a visible operation after a hidden one shows its Details again", flush=True)
    browser.close()
