"""Check the phone-pairing dialog with a synthetic code and no real credentials.

Run against a stub: `uv run --with playwright python tests/e2e/verify_connect_dialog.py <port>`.
"""

import json
import sys
from itertools import product
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright
from settings_controls import open_settings

URL = "http://127.0.0.1:" + sys.argv[1]
FAILURES = []
SYNTHETIC_CODE = """<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256">
<rect width="256" height="256" fill="white"/>
<path fill="black" d="M24 24h64v64H24zM168 24h64v64h-64zM24 168h64v64H24zM120 120h24v24h-24zM168 168h32v32h-32z"/>
<path fill="white" d="M36 36h40v40H36zM180 36h40v40h-40zM36 180h40v40H36z"/>
</svg>"""


def check(name, condition, detail=None):
    print(("PASS " if condition else "FAIL ") + name, flush=True)
    if not condition:
        FAILURES.append(name)
        if detail is not None:
            print(json.dumps(detail, ensure_ascii=False), flush=True)


def connect_fixture(route):
    path = urlsplit(route.request.url).path
    if path == "/connect/qr.svg":
        route.fulfill(content_type="image/svg+xml", body=SYNTHETIC_CODE)
    elif path == "/connect/devices":
        route.fulfill(json={"active": 0, "total": 0, "devices": []})
    else:
        route.abort()


def open_pairing(page):
    open_settings(page, "phone")
    page.locator("#settings-phone-open").click()
    expect(page.locator("#connect-dialog")).to_be_visible()
    expect(page.locator("#connect-qr")).to_be_visible()


def geometry(page):
    return page.locator("#connect-dialog").evaluate("""dialog => {
      const bounds = selector => {
        const rectangle = dialog.querySelector(selector).getBoundingClientRect();
        return {left: rectangle.left, right: rectangle.right, top: rectangle.top,
          bottom: rectangle.bottom, width: rectangle.width, height: rectangle.height,
          middle: rectangle.top + rectangle.height / 2};
      };
      const rectangle = dialog.getBoundingClientRect();
      return {head: bounds('.connect-head'), title: bounds('#connect-title'),
        close: bounds('.connect-head button'), bottom: bounds('#connect-close'),
        dialog: {left: rectangle.left, right: rectangle.right, top: rectangle.top, bottom: rectangle.bottom},
        viewport: {width: innerWidth, height: innerHeight},
        overflow: dialog.scrollWidth > dialog.clientWidth};
    }""")


def verify_case(browser, width, locale):
    context = browser.new_context(viewport={"width": width, "height": 780}, locale=locale)
    context.route("**/connect/**", connect_fixture)
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    case = f"{width}px {locale}"
    try:
        page.goto(URL + "/?lang=" + locale)
        expect(page.locator("html")).to_have_attribute("lang", locale)
        open_pairing(page)
        bounds = geometry(page)
        head, title, close = bounds["head"], bounds["title"], bounds["close"]
        check(case + ": the title and header Close share one row", abs(title["middle"] - close["middle"]) <= 1, bounds)
        check(case + ": header Close follows the title", close["left"] >= title["right"] + 8, bounds)
        check(case + ": header Close stays at the right edge", 12 <= head["right"] - close["right"] <= 20, bounds)
        check(case + ": header Close provides a touch target", close["width"] >= 44 and close["height"] >= 44, bounds)
        check(case + ": the header stays compact", head["height"] <= 80, bounds)
        dialog, viewport = bounds["dialog"], bounds["viewport"]
        check(
            case + ": the dialog fits the viewport",
            dialog["left"] >= 0
            and dialog["right"] <= viewport["width"]
            and dialog["top"] >= 0
            and dialog["bottom"] <= viewport["height"]
            and not bounds["overflow"],
            bounds,
        )
        check(case + ": bottom Close stays inside the dialog", bounds["bottom"]["bottom"] <= dialog["bottom"], bounds)
        if "--screenshots" in sys.argv:
            page.locator("#connect-dialog").screenshot(path=f"/tmp/open-imagine-connect-dialog-{width}-{locale}.png")
        page.locator("#connect-dialog .connect-head button").click()
        expect(page.locator("#connect-dialog")).to_be_hidden()
        check(case + ": header Close closes the dialog", True)
        open_pairing(page)
        page.locator("#connect-close").click()
        expect(page.locator("#connect-dialog")).to_be_hidden()
        check(case + ": bottom Close closes the dialog", True)
        open_pairing(page)
        page.keyboard.press("Escape")
        expect(page.locator("#connect-dialog")).to_be_hidden()
        check(case + ": Escape closes the dialog", True)
        check(case + ": no script errors occur", errors == [], errors)
    finally:
        context.close()


with sync_playwright() as tool:
    browser = tool.chromium.launch()
    try:
        for width, locale in product((1440, 390), ("en", "zh-TW")):
            verify_case(browser, width, locale)
    finally:
        browser.close()

if FAILURES:
    raise SystemExit(f"{len(FAILURES)} pairing-dialog checks failed")
