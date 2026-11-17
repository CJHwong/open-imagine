"""Check that a result which fails to import is retried, not written off.

Run: uv run --with playwright python tests/e2e/verify_import_retry.py <port>

The module used to call `remember(id)` after three failed imports, which put the operation
in the imported set although nothing had been imported. A transient failure then hid the
result for the rest of the page session, while the server still held it. This serves the
result endpoint three 500s and then a success, which is the count that used to end the attempts.
"""

import json
import sys

from playwright.sync_api import TimeoutError as BrowserTimeout
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:" + sys.argv[1]
OPERATION = {
    "id": "retry-check",
    "kind": "image",
    "source": "api",
    "client_id": "another-tab",
    "library_id": "retry-check",
    "status": "succeeded",
    "started_at": 1,
    "finished_at": 2,
    "result_url": "/api/v1/operations/retry-check/result",
    "error": None,
    "settings": {"mode": "generate", "prompt": "pear"},
}
SHELL = """<!doctype html><html><body>
<div id="voice-studio"><button id="voice-generate" data-state="idle">Speak</button></div>
<div id="shared-operation"><span id="shared-operation-label"></span><span id="shared-operation-detail"></span>
<span id="shared-operation-percent"></span><span id="shared-operation-elapsed"></span>
<button id="shared-operation-details">Details</button></div>
<button id="shared-operation-cancel"><span>Cancel</span></button>
<script>
window.studioI18n = {t: key => key, plural: (count, forms) => (typeof forms === 'string' ? forms : forms.other),
  number: value => String(value), date: value => String(value), locale: () => 'en',
  label: (kind, id, english) => english};
window.importedImages = [];
window.notices = [];
document.addEventListener('operations-ready', event => {
  event.detail.configure({
    clientId: 'retry-check', libraryId: 'retry-check',
    notify(kind, text) { window.notices.push(text); },
    setActive() {}, changingModel: () => false, observeDrafts() {},
    finishImageOperation() {},
    addImages(operation, images) { window.importedImages.push(...images.map(() => operation.id)); }
  });
  window.retryCheckReady = true;
});
</script><script type="module" src="/page/lib/operations.js"></script>
</body></html>"""


def main() -> int:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        failures = []
        state = {"active": None, "busy": False, "operations": [OPERATION]}

        def answer_state(route):
            route.fulfill(content_type="application/json", body=json.dumps(state))

        def answer_result(route):
            if len(failures) < 3:
                failures.append(route.request.url)
                route.fulfill(status=500, content_type="application/json", body='{"error": "not ready"}')
                return
            route.fulfill(content_type="application/json", body='{"images": [{"png_base64": "unused"}]}')

        page.route("**/import-retry-check", lambda route: route.fulfill(content_type="text/html", body=SHELL))
        page.route("**/api/v1/state", answer_state)
        page.route("**/api/v1/operations/retry-check/result", answer_result)
        try:
            page.goto(URL + "/import-retry-check")
            page.wait_for_function("window.retryCheckReady === true", timeout=10000)
            page.wait_for_function("window.importedImages.length === 1", timeout=90000)
            # The notice is the proof that a failure names its operation. It runs here,
            # on the success path, because a version that sat after the timeout's return
            # could never run.
            notices = page.evaluate("window.notices")
            if not any("retry-ch" in text for text in notices):
                print(f"FAIL the failure did not name the operation: {notices}")
                return 1
        except BrowserTimeout:
            print(f"FAIL the result never arrived after {len(failures)} failed reads")
            return 1
        finally:
            browser.close()
    print(f"PASS imported after {len(failures)} failed reads")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
