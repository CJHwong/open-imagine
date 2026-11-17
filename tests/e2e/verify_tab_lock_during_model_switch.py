"""Check that a workspace tab cannot be pressed while a model switch runs.

Run against a fresh stub that offers more than one image model:

uv run studio --stub --all-backends --port <port>
uv run --with playwright python tests/e2e/verify_tab_lock_during_model_switch.py <port>

A model switch owns the slot from the press until the page reloads. A workspace tab
pressed in that window used to reach the studio, be refused as busy, and leave the tab
where it was, which reads as a stuck page. The tab is disabled for the whole switch now.
"""

import sys

from playwright.sync_api import TimeoutError as BrowserTimeout
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:" + sys.argv[1]


def main() -> int:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        held = []
        workspace_calls = []

        def hold_switch(route):
            held.append(route)

        def count_workspace(route):
            workspace_calls.append(route.request.url)
            route.fulfill(status=204, body="")

        page.route("**/backend", hold_switch)
        page.route("**/workspace", count_workspace)
        try:
            page.goto(URL + "/")
            page.wait_for_selector("#backend-toggle:not([disabled])", timeout=20000)
            page.click("#backend-toggle")
            page.wait_for_selector('#backend-menu [role="menuitemradio"][aria-checked="false"]', timeout=10000)
            page.click('#backend-menu [role="menuitemradio"][aria-checked="false"]')
            page.wait_for_selector("#backend-toggle[disabled]", timeout=10000)

            disabled = page.evaluate(
                "() => ['media-image-mode', 'media-video-mode', 'media-voice-mode', 'media-music-mode']"
                ".map(id => document.getElementById(id)?.disabled)"
            )
            for name, state in zip(("image", "video", "voice", "music"), disabled, strict=True):
                if state is not True:
                    print(f"FAIL the {name} tab is still enabled during a model switch")
                    return 1

            page.click("body", position={"x": 5, "y": 5})
            page.evaluate("document.getElementById('media-video-mode').click()")
            page.wait_for_timeout(500)
            if workspace_calls:
                print(f"FAIL a tab press reached the studio during the switch: {workspace_calls}")
                return 1

            for route in held:
                route.fulfill(status=200, body="<p>busy</p>", content_type="text/html")
            page.wait_for_selector("#backend-toggle:not([disabled])", timeout=10000)
            page.wait_for_function("() => !document.getElementById('media-video-mode').disabled", timeout=10000)
        except BrowserTimeout:
            print("FAIL the switch never settled")
            return 1
        finally:
            browser.close()
    print("PASS the tabs wait behind a model switch")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
