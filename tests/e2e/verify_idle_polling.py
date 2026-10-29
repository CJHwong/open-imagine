"""Check shared polling against the real module on a stub server.

Run: uv run --with playwright python tests/e2e/verify_idle_polling.py <port>
Visibility changes use document getters, so the browser's own timer throttling
cannot make a broken scheduler appear to pass.
"""

import json
import sys

from playwright.sync_api import TimeoutError as BrowserTimeout
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:" + sys.argv[1]
SHELL = """<!doctype html><html><body>
<div id="voice-studio"><button id="voice-generate" data-state="idle">Speak</button></div>
<div id="shared-operation"></div><button id="shared-operation-cancel"><span>Cancel</span></button>
<script>
window.hiddenForCheck = false;
Object.defineProperty(document, 'hidden', {get: () => window.hiddenForCheck});
Object.defineProperty(document, 'visibilityState', {get: () => window.hiddenForCheck ? 'hidden' : 'visible'});
document.addEventListener('operations-ready', event => {
  window.sharedPoll = event.detail.configure({
    clientId: 'idle-check', libraryId: 'idle-check', notify() {}, setActive() {},
    observeDrafts() {}, finishImageOperation() {}
  });
});
</script><script type="module" src="/page/lib/operations.js"></script>
</body></html>"""


def visible(page, shown):
    page.evaluate(
        """shown => {
        window.hiddenForCheck = !shown;
        document.dispatchEvent(new Event('visibilitychange'));
    }""",
        shown,
    )


def refresh_during_pending_request(browser, lifecycle):
    page = browser.new_page()
    pending_requests = []
    deferred = []
    idle = json.dumps({"active": None, "busy": False, "operations": []})

    def answer_pending(route):
        pending_requests.append(route.request.url)
        if len(pending_requests) == 1:
            deferred.append(route)
            return
        route.fulfill(content_type="application/json", body=idle)

    page.route("**/idle-power-check", lambda route: route.fulfill(content_type="text/html", body=SHELL))
    page.route("**/api/v1/state", answer_pending)
    try:
        page.goto(URL + "/idle-power-check")
        page.wait_for_function("Boolean(window.sharedPoll)")
        page.wait_for_timeout(100)
        assert deferred, "The initial request did not start."
        if lifecycle == "visibility":
            visible(page, False)
            visible(page, True)
        else:
            page.evaluate("window.dispatchEvent(new Event('pagehide')); window.dispatchEvent(new Event('pageshow'))")
        with page.expect_request("**/api/v1/state", timeout=1500) as refreshed:
            deferred[0].fulfill(content_type="application/json", body=idle)
        response = refreshed.value.response()
        return response is not None and response.status == 200 and len(pending_requests) == 2
    except BrowserTimeout:
        return False
    finally:
        page.close()


def local_work_starts_fast_polling(browser, marker):
    page = browser.new_page()
    pending_requests = []

    def idle_answer(route):
        pending_requests.append(route.request.url)
        route.fulfill(
            content_type="application/json", body=json.dumps({"active": None, "busy": False, "operations": []})
        )

    page.route("**/idle-power-check", lambda route: route.fulfill(content_type="text/html", body=SHELL))
    page.route("**/api/v1/state", idle_answer)
    try:
        page.goto(URL + "/idle-power-check")
        page.wait_for_function("Boolean(window.sharedPoll)")
        page.wait_for_timeout(100)
        with page.expect_request("**/api/v1/state", timeout=1500) as refreshed:
            page.evaluate(
                """marker => {
                if (marker === 'voice') document.getElementById('voice-generate').dataset.state = 'busy';
                else if (marker === 'voice-insert') document.getElementById('voice-studio').innerHTML = '<button id=voice-generate data-state=busy>Speak</button>';
                else document.body.classList.add(marker);
            }""",
                marker,
            )
        response = refreshed.value.response()
        assert response is not None and response.status == 200
        initial = len(pending_requests)
        page.wait_for_timeout(1000)
        return 2 <= len(pending_requests) - initial <= 4
    except BrowserTimeout:
        return False
    finally:
        page.close()


with sync_playwright() as tool:
    browser = tool.chromium.launch()
    page = browser.new_page()
    requests = []
    payload = {"active": None, "busy": False, "operations": []}
    failures = []

    def answer(route):
        requests.append(route.request.url)
        route.fulfill(content_type="application/json", body=json.dumps(payload))

    def check(name, passed):
        print(("PASS " if passed else "FAIL ") + name, flush=True)
        if not passed:
            failures.append(name)

    page.route("**/idle-power-check", lambda route: route.fulfill(content_type="text/html", body=SHELL))
    page.route("**/api/v1/state", answer)
    page.goto(URL + "/idle-power-check")
    page.wait_for_function("Boolean(window.sharedPoll)")
    page.wait_for_timeout(100)
    initial = len(requests)
    page.wait_for_timeout(1200)
    check("idle polling does not run every 350 milliseconds", len(requests) == initial)

    visible(page, False)
    hidden = len(requests)
    page.wait_for_timeout(1200)
    check("hidden tabs stop scheduled polling", len(requests) == hidden)
    page.evaluate("window.sharedPoll.refresh()")
    page.wait_for_timeout(100)
    check("explicit refresh does not poll a hidden tab", len(requests) == hidden)

    payload["busy"] = True
    with page.expect_response("**/api/v1/state", timeout=1500):
        visible(page, True)
    check("returning to the tab refreshes immediately", len(requests) == hidden + 1)
    active = len(requests)
    page.wait_for_timeout(1300)
    check("busy work keeps fast polling even when private status is hidden", 2 <= len(requests) - active <= 5)

    payload["busy"] = False
    with page.expect_response("**/api/v1/state"):
        page.evaluate("window.sharedPoll.refresh()")
    page.wait_for_timeout(100)
    idle = len(requests)
    page.wait_for_timeout(5200)
    check("idle work polls once in five seconds", len(requests) == idle + 1)

    page.evaluate("window.dispatchEvent(new Event('pagehide'))")
    stopped = len(requests)
    page.wait_for_timeout(1200)
    check("leaving the page stops polling", len(requests) == stopped)
    with page.expect_response("**/api/v1/state", timeout=1500):
        page.evaluate("window.dispatchEvent(new Event('pageshow'))")
    check("restoring the page refreshes immediately", len(requests) == stopped + 1)
    for lifecycle in ("visibility", "page"):
        check(
            lifecycle + " restore queues a refresh behind an unfinished request",
            refresh_during_pending_request(browser, lifecycle),
        )
    for marker in ("busy", "video-busy", "rewriting", "voice", "voice-insert"):
        check(
            marker + " starts fast polling before the server reports busy",
            local_work_starts_fast_polling(browser, marker),
        )
    browser.close()
    if failures:
        raise AssertionError("; ".join(failures))
