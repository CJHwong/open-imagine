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
"""

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
    check("a hung state poll does not report the status as lost", "Cannot get the current task status." not in toasts)


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
    browser.close()

print("FAILURES:", failures)
sys.exit(1 if failures else 0)
