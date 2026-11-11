"""Check model names from the first document through workspace and model changes.

uv run --with playwright python tests/e2e/verify_model_loading.py <port> [--webkit]
Run against a fresh all-backend stub.
"""

import json
import sys
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import expect, sync_playwright

WATCH_NAMES = """(() => {
    window.seenModelNames = [];
    const record = () => {
        const name = document.querySelector('#backend-toggle .name')?.textContent.trim();
        if (name && window.seenModelNames.at(-1) !== name) window.seenModelNames.push(name);
    };
    new MutationObserver(record).observe(document, {subtree:true, childList:true, characterData:true});
    document.addEventListener('DOMContentLoaded', record);
})()"""


def record(failures, condition, case, detail):
    if condition:
        return
    failures.append({"case": case, "detail": detail})
    print("FAIL", json.dumps(failures[-1]), flush=True)


def check_workspace(browser, base, workspace, saved, failures):
    context = browser.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
    context.add_init_script(
        "localStorage.setItem('studio-keep', 'on');"
        "localStorage.setItem('studio-draft-workspace', " + json.dumps(workspace if saved else "image") + ");"
    )
    context.add_init_script(WATCH_NAMES)
    page = context.new_page()
    suffix = "/" if saved else "/?workspace=" + workspace
    page.goto(base + suffix)
    studio = page.request.get(base + "/api/v1/state").json()["studio"]
    expected = studio[workspace]["capabilities"]["name"]
    expect(page.locator("#backend-toggle .name")).to_have_text(expected)
    page.reload()
    expect(page.locator("#backend-toggle .name")).to_have_text(expected)
    names = page.evaluate("window.seenModelNames")
    case = workspace + ("/saved" if saved else "/query")
    image_name = studio["image"]["capabilities"]["name"]
    record(failures, image_name not in names, case + "/no-image-fallback", names)
    record(failures, names[-1] == expected, case + "/selected-model", names)
    print("CHECK", case, flush=True)
    context.close()


def check_model_switch(browser, base, failures):
    context = browser.new_context(viewport={"width": 768, "height": 748}, has_touch=True, is_mobile=True)
    context.add_init_script("localStorage.setItem('studio-keep','off')")
    context.add_init_script(WATCH_NAMES)
    page = context.new_page()
    page.goto(base + "/?workspace=video")
    studio = page.request.get(base + "/api/v1/state").json()["studio"]
    video = studio["video"]
    target = next(backend for backend in video["backends"] if backend["id"] != video["active"])
    expect(page.locator("#backend-toggle")).to_be_enabled()
    page.locator("#backend-toggle").click()
    page.get_by_role("menuitemradio", name=target["name"], exact=True).click()
    expect(page.locator("#backend-toggle .name")).to_have_text(target["name"])
    names = page.evaluate("window.seenModelNames")
    record(failures, studio["image"]["capabilities"]["name"] not in names, "switch/no-image-fallback", names)
    print("CHECK selected video model after navigation", flush=True)
    context.close()


def check_workspace_navigation(browser, base, failures):
    context = browser.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
    context.add_init_script("localStorage.setItem('studio-keep','off')")
    page = context.new_page()
    page.goto(base + "/?workspace=image")
    studio = page.request.get(base + "/api/v1/state").json()["studio"]
    expected = studio["video"]["capabilities"]["name"]
    expect(page.locator("#workspace-toggle")).to_be_enabled()
    page.locator("#workspace-toggle").click()
    page.locator('#workspace-menu [data-workspace="video"]').click()
    expect(page.locator("body")).to_have_attribute("data-media", "video")
    requested = parse_qs(urlsplit(page.url).query).get("workspace")
    record(failures, requested == ["video"], "workspace/address", requested)
    page.reload()
    page.wait_for_function("document.body.dataset.media && document.querySelector('#backend-toggle .name').textContent")
    actual = page.locator("#backend-toggle .name").inner_text()
    record(failures, actual == expected, "workspace/reload-retains-model", actual)
    print("CHECK workspace navigation survives refresh", flush=True)
    context.close()


def check_invalid_workspace(browser, base, saved, failures):
    context = browser.new_context(viewport={"width": 390, "height": 844})
    context.add_init_script(
        "localStorage.setItem('studio-keep','on');localStorage.setItem('studio-draft-workspace','constructor')"
    )
    page = context.new_page()
    page.goto(base + ("/" if saved else "/?workspace=toString"))
    page.wait_for_function("document.body.dataset.media !== undefined")
    actual = page.locator("body").get_attribute("data-media")
    record(failures, actual == "image", "invalid/" + ("saved" if saved else "query"), actual)
    print("CHECK invalid workspace uses Image", flush=True)
    context.close()


base = "http://127.0.0.1:" + sys.argv[1]
failures = []
with sync_playwright() as playwright:
    engine = playwright.webkit if "--webkit" in sys.argv else playwright.chromium
    browser = engine.launch()
    for workspace in ("video", "voice", "music"):
        for saved in (False, True):
            check_workspace(browser, base, workspace, saved, failures)
    check_model_switch(browser, base, failures)
    check_workspace_navigation(browser, base, failures)
    for saved in (False, True):
        check_invalid_workspace(browser, base, saved, failures)
    browser.close()
print("FAILURES", len(failures), flush=True)
raise SystemExit(bool(failures))
