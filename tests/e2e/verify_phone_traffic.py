"""What a phone sends and receives over its slow pipe. Run against a fresh stub:

uv run studio --stub --all-backends --port <port>
uv run --with playwright --with pillow python tests/e2e/verify_phone_traffic.py <port>

1. A video run survives polls that fail, as they do while a phone sleeps. A run whose result
   read or whose start answer is lost still delivers its clip, through the shared poll.
2. A picture that needs no resize is sent as the file's own bytes, and a resize of a photo is a JPEG.
3. During a run, the state poll leaves out the studio block the page already holds.
4. A reload revalidates the page's files instead of downloading them again.
5. A state poll, a status read or a result read that never answers is given up and asked
   again: the clock keeps time, no failure is reported, and the clip still arrives. A result
   read ends when its bytes stop, never for taking long.
6. A page reopened after its run ended imports the clip, and two tabs import it once.
7. On a phone, a workspace switch shows a spinner on the picker while it waits. A switch that
   never answers is given up, and the next switch still works.
8. On a phone, a chosen picture holds its place with a busy tile, in the image form and in the
   video studio, from the choice until the picture appears or fails. A HEIC comes back from
   the studio as a JPEG, or a PNG with transparency, and those bytes are what the page sends.
9. A read that fails while the page is hidden, or just after it shows again, reports nothing.
   A page that stays visible and loses the studio shows one notice, and the next state that
   arrives closes it.
"""

import base64
import io
import re
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:" + sys.argv[1]
failures = []


def check(name, passed, detail=""):
    print(("PASS " if passed else "FAIL ") + name + (f"  ({detail})" if detail else ""), flush=True)
    if not passed:
        failures.append(name)


def photo(path, width, height):
    image = Image.effect_noise((width, height), 40).convert("RGB")
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=90)
    path.write_bytes(buffer.getvalue())
    return path


def studio(page):
    return page.locator("#video-studio")


def check_dropped_polls(page):
    dropped = []

    def drop_three(route):
        if len(dropped) < 3:
            dropped.append(route.request.url)
            route.abort("connectionreset")
        else:
            route.continue_()

    page.route("**/api/v1/operations/*", drop_three)
    page.fill("#video-prompt", "A kite over the sea.")
    page.locator("#video-generate").click()
    page.wait_for_function("() => videoRunState === 'idle'", timeout=30000)
    page.unroute("**/api/v1/operations/*", drop_three)
    status = page.locator("#video-request-status").text_content()
    check(
        "a run whose status polls drop still delivers its clip",
        len(dropped) == 3 and status == "Test preview added. No video file was generated.",
        f"dropped {len(dropped)}, status {status!r}",
    )


def run_with(page, pattern, handler):
    """One stub run with `pattern` routed to `handler`. Returns the clip count it added."""
    before = page.evaluate("() => document.getElementById('video-studio').clips.length")
    page.route(pattern, handler)
    page.fill("#video-prompt", "A paper boat on a pond.")
    page.locator("#video-generate").click()
    page.wait_for_function("() => videoRunState === 'idle'", timeout=30000)
    page.unroute(pattern, handler)
    # The shared poll is idle every five seconds; its page-show hook asks at once.
    page.evaluate("() => window.dispatchEvent(new Event('pageshow'))")
    page.wait_for_function(
        "count => document.getElementById('video-studio').clips.length > count", arg=before, timeout=20000
    )
    return page.evaluate("() => document.getElementById('video-studio').clips.length") - before


def check_lost_result_reads(page):
    lost = []

    def drop(route):
        lost.append(1)
        route.abort("connectionreset")

    # Every read the page makes itself drops. The shared poll reads the result after it gives up.
    added = run_with(page, "**/api/v1/operations/*/result", drop)
    check(
        "a run whose own result reads all drop still delivers one clip",
        added == 1 and len(lost) == 5,
        f"{added} clips, {len(lost)} reads dropped",
    )


def check_lost_start_answer(page):
    def answer_lost(route):
        route.fetch()
        route.abort("connectionreset")

    added = run_with(page, "**/video/operations", answer_lost)
    check("a run whose start answer is lost still delivers one clip", added == 1, f"{added} clips")


def check_phone_run(browser):
    context = browser.new_context(viewport={"width": 412, "height": 915}, is_mobile=True, has_touch=True)
    phone = context.new_page()
    phone.goto(BASE + "/?workspace=video", wait_until="networkidle")
    dropped = []
    phone.route(
        "**/api/v1/operations/*",
        lambda route: (dropped.append(1), route.abort("connectionreset")) if len(dropped) < 3 else route.continue_(),
    )
    phone.locator('.pane-switch [data-pane="controls"]').tap()
    phone.fill("#video-prompt", "A kite over the sea.")
    phone.locator("#video-generate").tap()
    phone.wait_for_function("() => videoRunState === 'idle'", timeout=30000)
    status = phone.locator("#video-request-status").text_content()
    check(
        "on a phone, a run whose polls drop still delivers its clip",
        len(dropped) == 3 and status == "Test preview added. No video file was generated.",
        f"dropped {len(dropped)}, status {status!r}",
    )
    context.close()


def shorten_limits(page):
    """The page's own limits are seconds long; these keep each hang in the suite short."""
    page.evaluate("() => { STUDIO_STATUS_TIMEOUT_MS = 1500; STUDIO_STALL_TIMEOUT_MS = 2000; }")


def hang(page, pattern, count):
    """The next `count` requests to `pattern` get no answer at all, as on a dead pipe connection."""
    held = []

    def handler(route):
        if len(held) < count:
            held.append(route)
        else:
            route.continue_()

    page.route(pattern, handler)
    return held


def elapsed_text(page):
    return page.locator("#shared-operation-elapsed").text_content()


def check_hung_video_reads(page):
    shorten_limits(page)
    # The run's first status read and first result read never answer.
    statuses = hang(page, re.compile(r"/api/v1/operations/[^/?]+$"), 1)
    results = hang(page, "**/api/v1/operations/*/result", 1)
    page.fill("#video-prompt", "A lantern in the rain.")
    page.locator("#video-generate").click()
    page.wait_for_function("() => videoRunState === 'idle'", timeout=30000)
    page.unroute_all(behavior="ignoreErrors")
    status = page.locator("#video-request-status").text_content()
    check(
        "a run whose status read and result read hang still delivers its clip",
        len(statuses) == 1 and len(results) == 1 and status == "Test preview added. No video file was generated.",
        f"{len(statuses)} status and {len(results)} result reads hung, status {status!r}",
    )


def check_hung_state_poll(page):
    shorten_limits(page)
    polls = []
    page.on("request", lambda request: polls.append(time.monotonic()) if "/api/v1/state" in request.url else None)
    # A stub video run ends within a second. The stub's default image model takes eight steps,
    # a second each, which holds the shared bar long enough.
    started = page.request.post(BASE + "/api/v1/operations", data={"kind": "image", "prompt": "a pear", "steps": 8})
    page.wait_for_function("() => document.getElementById('shared-operation').dataset.status === 'running'")
    states = hang(page, re.compile(r"/api/v1/state"), 2)
    deadline = time.monotonic() + 5
    while not states and time.monotonic() < deadline:
        page.wait_for_timeout(50)
    hung_at = time.monotonic()
    shown = elapsed_text(page)
    page.wait_for_timeout(2500)
    ticked = elapsed_text(page)
    check(
        "the clock ticks while a state poll hangs", started.status == 202 and ticked != shown, f"{shown!r}, {ticked!r}"
    )
    later = [moment for moment in polls if moment > hung_at]
    check(
        "a hung state poll is sent again once its limit passes",
        bool(later) and later[0] - hung_at < 2.5,
        f"next poll after {later[0] - hung_at:.1f}s" if later else "no poll after the hang",
    )
    page.wait_for_function("() => document.getElementById('shared-operation').hidden", timeout=40000)
    page.unroute_all(behavior="ignoreErrors")
    toasts = page.locator("#toasts").inner_text()
    check(
        "a hung state poll does not report the status as lost",
        "Cannot get the current task status." not in toasts and LOST not in toasts,
    )


STALL = """async ([gaps, stallMs]) => {
  // One chunk after each gap, through the page's own reader of a result.
  const real = window.fetch;
  window.fetch = async (url, init) => new Response(new ReadableStream({
    async start(controller) {
      for (const gap of gaps) {
        await new Promise((resolve, reject) => {
          const timer = setTimeout(resolve, gap);
          init.signal.addEventListener('abort', () => { clearTimeout(timer); reject(init.signal.reason); });
        });
        controller.enqueue(new Uint8Array([1]));
      }
      controller.close();
    },
  }));
  STUDIO_STALL_TIMEOUT_MS = stallMs;
  const started = performance.now();
  try {
    const answer = await studioStallFetch('/slow');
    return {bytes: (await answer.arrayBuffer()).byteLength, ms: performance.now() - started};
  } catch (error) {
    return {error: error.name, ms: performance.now() - started};
  } finally {
    window.fetch = real;
  }
}"""


def check_stall_limit(page):
    slow = page.evaluate(STALL, [[600, 600, 600, 600, 600], 1000])
    check("a result that keeps arriving is never cut, however long it takes", slow.get("bytes") == 5, str(slow))
    stalled = page.evaluate(STALL, [[100, 60000], 1000])
    check(
        "a result that stops arriving ends after the stall limit",
        stalled.get("error") == "TimeoutError" and stalled["ms"] < 3000,
        str(stalled),
    )


def start_and_leave(context, prompt):
    """A run whose page goes away before it ends, as when Android restarts the app. Returns its id."""
    page = context.new_page()
    page.goto(BASE + "/?workspace=video", wait_until="load")
    page.wait_for_function("typeof STUDIO === 'object'")
    page.fill("#video-prompt", prompt)
    with page.expect_response(lambda response: response.url.endswith("/video/operations")) as started:
        page.locator("#video-generate").click()
    operation = started.value.json()["id"]
    page.close()
    deadline = time.monotonic() + 60
    while context.request.get(f"{BASE}/api/v1/operations/{operation}").json()["status"] != "succeeded":
        if time.monotonic() > deadline:
            raise TimeoutError(f"run {operation} did not end")
        time.sleep(0.5)
    return operation


def open_video(context):
    page = context.new_page()
    page.goto(BASE + "/?workspace=video", wait_until="load")
    return page


def has_clip(page, operation):
    return page.evaluate(
        "id => document.getElementById('video-studio').clips.some(clip => clip.id === 'video-operation-' + id)",
        operation,
    )


def check_reopened_page(browser):
    context = browser.new_context()
    operation = start_and_leave(context, "A heron on one leg.")
    # Same localStorage, new sessionStorage: what a restarted app's WebView has.
    page = open_video(context)
    deadline = time.monotonic() + 20
    while not has_clip(page, operation) and time.monotonic() < deadline:
        page.wait_for_timeout(250)
    check("a page reopened after its run ended imports the clip", has_clip(page, operation))
    context.close()


def check_two_tabs(browser):
    context = browser.new_context()
    operation = start_and_leave(context, "A fox in the snow.")
    reads = []
    context.on("request", lambda request: reads.append(request.url) if f"{operation}/result" in request.url else None)
    first, second = open_video(context), open_video(context)
    deadline = time.monotonic() + 20
    while not (has_clip(first, operation) or has_clip(second, operation)) and time.monotonic() < deadline:
        first.wait_for_timeout(250)
    # Past one idle poll of each tab, so a second import has had its chance.
    first.wait_for_timeout(7000)
    check("two tabs that open together import the run once", len(reads) == 1, f"{len(reads)} result reads")
    context.close()


def pick_workspace(phone, name):
    phone.locator("#workspace-toggle").tap()
    phone.locator("#workspace-menu").get_by_role("menuitemradio", name=name).tap()


def check_workspace_switch(browser):
    context = browser.new_context(viewport={"width": 412, "height": 915}, is_mobile=True, has_touch=True)
    phone = context.new_page()
    phone.goto(BASE + "/?workspace=video", wait_until="networkidle")
    phone.evaluate("() => { STUDIO_SWITCH_TIMEOUT_MS = 1500; }")
    held = hang(phone, "**/workspace", 1)
    pick_workspace(phone, "Image")
    phone.wait_for_function("() => workspaceSwitchPending", timeout=5000)
    spinner = phone.evaluate(
        """() => {
          const toggle = document.getElementById('workspace-toggle');
          const icon = toggle.querySelector('.workspace-icon');
          return [getComputedStyle(toggle, '::after').animationName, getComputedStyle(icon).visibility];
        }"""
    )
    check("on a phone, the workspace picker spins while a switch waits", spinner == ["gallery-spin", "hidden"], spinner)
    phone.wait_for_function("() => !workspaceSwitchPending", timeout=5000)
    check(
        "a switch that never answers is given up and stays in place",
        len(held) == 1
        and phone.evaluate("mediaMode") == "video"
        and not phone.locator("#workspace-toggle").get_attribute("aria-busy"),
        phone.evaluate("mediaMode"),
    )
    pick_workspace(phone, "Image")
    phone.wait_for_function("() => mediaMode === 'image' && !workspaceSwitchPending", timeout=5000)
    check("the next switch still works", True)
    context.close()


LOST = "Lost contact with the server."


def encoded(mode, format):
    buffer = io.BytesIO()
    Image.new(mode, (40, 30), (200, 30, 20, 128) if mode == "RGBA" else (200, 30, 20)).save(buffer, format)
    return buffer.getvalue()


def hold_normalize(phone):
    """Every HEIC the page sends waits in the returned list until the check answers it."""
    held = []
    phone.route("**/image/normalize", lambda route: held.append(route))
    return held


def chosen(phone, held, choose):
    """Choose a HEIC and return the request it sent, still unanswered."""
    count = len(held)
    choose()
    deadline = time.monotonic() + 5
    while len(held) == count and time.monotonic() < deadline:
        phone.wait_for_timeout(50)
    return held[-1]


def busy_tile(phone, selector):
    """The spinner's animation when the busy tile is on screen, else None."""
    return phone.evaluate(
        """selector => {
          const tile = document.querySelector(selector);
          if (!tile || !tile.getClientRects().length) return null;
          return getComputedStyle(tile.querySelector('.import-busy-mark'), '::after').animationName;
        }""",
        selector,
    )


def check_import_tile(browser, folder):
    context = browser.new_context(viewport={"width": 412, "height": 915}, is_mobile=True, has_touch=True)
    phone = context.new_page()
    phone.goto(BASE + "/?workspace=image", wait_until="networkidle")
    phone.locator('.pane-switch [data-pane="controls"]').tap()
    phone.locator('label[for="mode-edit"]').tap()
    # The page sends the HEIC to the studio and never reads it, so any bytes serve.
    heic = folder / "photo.heic"
    heic.write_bytes(b"\x00\x00\x00\x18ftypheic")
    jpeg = encoded("RGB", "JPEG")
    choose = lambda: phone.locator("#reference").set_input_files(str(heic))  # noqa: E731
    requests = hold_normalize(phone)

    held = chosen(phone, requests, choose)
    tile = "#thumbs .import-busy"
    check("on a phone, a chosen picture shows a busy tile in the form", busy_tile(phone, tile) == "gallery-spin")
    held.fulfill(status=200, content_type="image/jpeg", body=jpeg)
    phone.wait_for_function("() => references.length === 1", timeout=5000)
    sent = phone.evaluate("() => references[0].b64")
    check(
        "the busy tile gives way to the picture, and a HEIC's JPEG is sent as the studio made it",
        busy_tile(phone, tile) is None and sent == base64.b64encode(jpeg).decode(),
        sent[:12],
    )
    phone.locator("#thumbs .remove").first.tap()

    held = chosen(phone, requests, choose)
    held.fulfill(status=200, content_type="image/png", body=encoded("RGBA", "PNG"))
    phone.wait_for_function("() => references.length === 1", timeout=5000)
    kept = phone.evaluate("() => references[0].b64")
    check("a HEIC with transparency is sent as the studio's PNG", kept.startswith("iVBOR"), kept[:8])
    phone.locator("#thumbs .remove").first.tap()

    held = chosen(phone, requests, choose)
    held.fulfill(status=400, content_type="application/json", body='{"error": "Could not read that image."}')
    phone.wait_for_function("() => document.querySelector('#toasts .toast.error')", timeout=5000)
    check(
        "a picture that fails takes its busy tile away and says why",
        busy_tile(phone, tile) is None and "photo.heic" in phone.locator("#toasts").inner_text(),
    )

    phone.goto(BASE + "/?workspace=video", wait_until="networkidle")
    phone.locator('.pane-switch [data-pane="controls"]').tap()
    requests = hold_normalize(phone)
    held = chosen(phone, requests, lambda: phone.locator("#video-media-upload").set_input_files(str(heic)))
    tile = "#video-references .import-busy"
    check("on a phone, a picture chosen for a video shows a busy tile", busy_tile(phone, tile) == "gallery-spin")
    held.fulfill(status=200, content_type="image/jpeg", body=jpeg)
    phone.wait_for_function("() => document.getElementById('video-studio').imageReferences.length === 1")
    check("the video's busy tile gives way to the picture", busy_tile(phone, tile) is None)
    context.close()


# A phone's screen going off, as the page sees it. `hidden` and `visibilityState` both move,
# because the page reads `hidden`.
HIDE = """hidden => {
  Object.defineProperty(document, 'hidden', {configurable: true, get: () => hidden});
  Object.defineProperty(document, 'visibilityState', {configurable: true, get: () => hidden ? 'hidden' : 'visible'});
  document.dispatchEvent(new Event('visibilitychange'));
}"""


def lost_notices(page):
    return page.locator("#toasts .toast.error", has_text=LOST).count()


def check_hidden_page(browser):
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    page.goto(BASE + "/?workspace=video", wait_until="networkidle")
    page.evaluate("() => { STUDIO_RESUME_GRACE_MS = 3000; }")
    page.evaluate(HIDE, True)
    page.route(re.compile(r"/api/v1/operations/[^/?]+$"), lambda route: route.abort("connectionreset"))
    page.route("**/api/v1/state*", lambda route: route.abort("connectionreset"))
    page.fill("#video-prompt", "A heron at dawn.")
    page.locator("#video-generate").click()
    # About nine status reads fail while hidden. Even with the grace taken off the first three
    # seconds, that is past the five the video line counts as lost.
    page.wait_for_timeout(9500)
    page.evaluate(HIDE, False)
    # Two seconds of failures inside the grace, as a phone's Wi-Fi wakes up.
    page.wait_for_timeout(2000)
    video = page.locator("#video-studio").inner_text()
    toasts = page.locator("#toasts").inner_text()
    check(
        "a page that is hidden, then just shown, reports no lost contact",
        LOST not in video and LOST not in toasts and "Cannot get the current task status." not in toasts,
        f"video line {LOST in video}, toasts {toasts!r}",
    )
    page.unroute_all(behavior="ignoreErrors")
    page.wait_for_function("() => videoRunState === 'idle'", timeout=30000)
    page.close()


def check_lost_contact(browser):
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    page.goto(BASE + "/?workspace=image", wait_until="networkidle")
    page.route("**/api/v1/state*", lambda route: route.abort("connectionreset"))
    page.evaluate("() => window.dispatchEvent(new Event('pageshow'))")
    page.wait_for_function("text => document.getElementById('toasts').innerText.includes(text)", arg=LOST)
    # Two more rounds of failed polls, five seconds apart.
    page.wait_for_timeout(11000)
    check(
        "a visible page that loses the studio shows one notice",
        lost_notices(page) == 1 and "Cannot get the current task status." not in page.locator("#toasts").inner_text(),
        f"{lost_notices(page)} notices",
    )
    page.unroute("**/api/v1/state*")
    page.evaluate("() => window.dispatchEvent(new Event('pageshow'))")
    page.wait_for_timeout(1500)
    check("the next state that arrives closes the notice", lost_notices(page) == 0, f"{lost_notices(page)} notices")
    page.close()


def check_reference_bytes(page, folder):
    small = photo(folder / "small.jpg", 1200, 900)
    page.locator("#video-media-upload").set_input_files(str(small))
    page.wait_for_function("() => document.getElementById('video-studio').imageReferences.length === 1")
    sent = studio(page).evaluate("element => element.imageReferences[0].base64")
    expected = len(small.read_bytes())
    check(
        "a JPEG that needs no resize keeps its own bytes",
        sent.startswith("/9j/") and abs(len(sent) * 3 / 4 - expected) < 4,
        f"{len(sent)} base64 characters for {expected} bytes",
    )
    page.evaluate("() => document.getElementById('video-studio').clearImageReferences()")
    large = photo(folder / "large.jpg", 4032, 3024)
    page.locator("#video-media-upload").set_input_files(str(large))
    page.locator("#image-import-dialog .image-import-resize").click()
    page.wait_for_function("() => document.getElementById('video-studio').imageReferences.length === 1")
    resized = studio(page).evaluate("element => element.imageReferences[0].base64")
    check("a resized photo is a JPEG", resized.startswith("/9j/"), resized[:8])
    page.evaluate("() => document.getElementById('video-studio').clearImageReferences()")
    clear = folder / "clear.png"
    Image.new("RGBA", (3000, 2000), (0, 0, 0, 0)).save(clear)
    page.locator("#video-media-upload").set_input_files(str(clear))
    page.locator("#image-import-dialog .image-import-resize").click()
    page.wait_for_function("() => document.getElementById('video-studio').imageReferences.length === 1")
    kept = studio(page).evaluate("element => element.imageReferences[0].base64")
    check("a resized picture that may be transparent stays PNG", kept.startswith("iVBOR"), kept[:8])
    page.evaluate("() => document.getElementById('video-studio').clearImageReferences()")


def check_state_revision(page):
    polls = []
    page.on("request", lambda request: polls.append(request.url) if "/api/v1/state" in request.url else None)
    page.evaluate("() => document.body.classList.add('video-busy')")
    page.wait_for_timeout(1500)
    page.evaluate("() => document.body.classList.remove('video-busy')")
    held = [url for url in polls if "?studio=" in url]
    check("a fast poll names the studio block it holds", len(held) >= 2, f"{len(held)} of {len(polls)} polls")
    if held:
        answer = page.request.get(held[-1]).json()
        check("the studio leaves that block out", "studio" not in answer and answer.get("studio_revision"))


def check_revalidation(page):
    answers = []
    page.on("response", lambda response: answers.append(response) if "/page/" in response.url else None)
    page.reload(wait_until="networkidle")
    asked = [one for one in answers if one.request.all_headers().get("if-none-match")]
    check(
        "a reload asks whether each page file changed",
        answers and len(asked) == len(answers),
        f"{len(asked)} of {len(answers)} asked",
    )


with tempfile.TemporaryDirectory() as directory, sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    page.goto(BASE + "/?workspace=video", wait_until="networkidle")
    check_dropped_polls(page)
    check_lost_result_reads(page)
    check_lost_start_answer(page)
    check_reference_bytes(page, Path(directory))
    check_state_revision(page)
    check_revalidation(page)
    check_stall_limit(page)
    check_hung_video_reads(page)
    check_hung_state_poll(page)
    check_phone_run(browser)
    check_reopened_page(browser)
    check_two_tabs(browser)
    check_workspace_switch(browser)
    check_import_tile(browser, Path(directory))
    check_hidden_page(browser)
    check_lost_contact(browser)
    browser.close()

print("FAILURES:", failures)
sys.exit(1 if failures else 0)
