"""What a phone sends and receives over its slow pipe. Run against a fresh stub:

uv run studio --stub --all-backends --port <port>
uv run --with playwright --with pillow python tests/e2e/verify_phone_traffic.py <port>

1. A video run survives polls that fail, as they do while a phone sleeps. A run whose result
   read or whose start answer is lost still delivers its clip, through the shared poll.
2. A picture that needs no resize is sent as the file's own bytes, and a resize of a photo is a JPEG.
3. During a run, the state poll leaves out the studio block the page already holds.
4. A reload revalidates the page's files instead of downloading them again.
"""

import io
import sys
import tempfile
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
    check_phone_run(browser)
    browser.close()

print("FAILURES:", failures)
sys.exit(1 if failures else 0)
