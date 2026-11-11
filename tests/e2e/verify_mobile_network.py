"""Check phone startup over plain HTTP, outside localhost's secure context.

Run a stub with --host 0.0.0.0, then:
uv run --with playwright python tests/e2e/verify_mobile_network.py <port> [network-host]
"""

import re
import sys
import uuid

from playwright.sync_api import expect, sync_playwright
from style_controls import open_style_section

URL = "http://" + (sys.argv[2] if len(sys.argv) > 2 else "0.0.0.0") + ":" + sys.argv[1]


def check_phone(engine, name, width):
    browser = engine.launch()
    context = browser.new_context(viewport={"width": width, "height": 844}, is_mobile=True, has_touch=True)
    # Keep WebKit media in memory to isolate startup from persistent Blob storage.
    if name == "webkit":
        context.add_init_script("localStorage.setItem('studio-keep', 'off')")
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(URL + "/?workspace=image")
    assert page.evaluate("!isSecureContext && typeof crypto.randomUUID === 'undefined'"), URL
    expect(page.locator("#refs-empty")).to_be_attached(timeout=10000)
    assert not errors, errors
    selector = page.locator("#workspace-toggle")
    expect(selector).to_be_visible()
    selector.tap()
    expect(page.locator("#workspace-menu button:not([disabled])")).to_have_count(4)
    page.keyboard.press("Escape")
    header = page.locator(".topbar").bounding_box()
    assert header and header["height"] <= 72, header
    page.locator('.pane-switch [data-pane="controls"]').tap()
    page.locator("#refs-empty").scroll_into_view_if_needed()
    expect(page.locator("#refs-title")).to_have_text("Start from an image")
    page.locator("#size-field").scroll_into_view_if_needed()
    expect(page.locator("#size-caption")).to_have_text(re.compile(r"\d+ \u00d7 \d+"))
    expect(page.locator("size-chips .chip").first).to_be_visible()
    page.locator("#templates-toggle").tap()
    page.locator("#templates [role=menuitem]").last.tap()
    open_style_section(page)
    expect(page.locator("#look")).to_have_js_property("open", True)
    identities = page.evaluate("Array.from({length: 100}, () => studioIdentity())")
    assert len(set(identities)) == 100
    assert all(uuid.UUID(identity).version == 4 for identity in identities)
    blank = context.new_page()
    blank.goto(URL + "/api/v1/studio")
    standalone = blank.evaluate("async () => (await import('/page/lib/uuid.js')).uuid()")
    assert uuid.UUID(standalone).version == 4
    blank.close()
    page.locator("#advanced summary").tap()
    page.locator("#steps").fill("1")
    page.locator("#advanced summary").tap()
    page.locator("#prompt").fill("A phone network preview.")
    page.locator("#go").tap()
    page.wait_for_function("!busy() && !sharedOperation")
    expect(page.locator(".pic img").first).to_be_visible()
    for workspace, field, button, result in (
        ("video", "#video-prompt", "#video-generate", ".video-preview-stub"),
        ("voice", "#voice-text", "#voice-generate", "audio-preview"),
        ("music", "#music-style", "#music-generate", ".music-song"),
    ):
        selector.tap()
        page.locator(f'#workspace-menu [data-workspace="{workspace}"]').tap()
        expect(page.locator("body")).to_have_attribute("data-media", workspace)
        page.locator('.pane-switch [data-pane="controls"]').tap()
        page.locator(field).fill("A short network preview.")
        page.locator(button).tap()
        expect(page.locator("body")).to_have_attribute("data-pane", "preview")
        expect(page.locator(result).first).to_be_visible(timeout=20000)
        page.wait_for_function("!sharedOperation && !sharedBusy()")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert not errors, errors
    browser.close()
    print(
        "PASS",
        name,
        width,
        "plain HTTP startup, four workspaces, compact header, references, size and generation",
        flush=True,
    )


with sync_playwright() as playwright:
    for browser_name in ("chromium", "webkit"):
        check_phone(getattr(playwright, browser_name), browser_name, 390)
        check_phone(getattr(playwright, browser_name), browser_name, 320)
