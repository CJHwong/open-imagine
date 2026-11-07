"""Check that the video form gives each picture its own frame. Run against a fresh stub:

uv run --with playwright python tests/e2e/verify_keyframe_spread.py <port>

Pictures that arrive without a frame go to frame 0, then the last frame, then the middle,
because a model such as MiniMax H3 refuses two pictures on one frame. A captured frame that
names a taken frame takes the nearest free one. A shorter duration moves a picture past the end
to the last frame, and the pictures in its way step back, so they keep their order.
"""

import io
import sys

from PIL import Image
from playwright.sync_api import sync_playwright

URL = f"http://127.0.0.1:{sys.argv[1]}/?lang=en"
failures = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f" ({detail})" if detail else ""), flush=True)
    if not ok:
        failures.append(name)


def picture(name, colour):
    data = io.BytesIO()
    Image.new("RGB", (64, 36), colour).save(data, "PNG")
    return {"name": name, "mimeType": "image/png", "buffer": data.getvalue()}


def frames(page):
    return page.evaluate("() => document.getElementById('video-studio').imageReferences.map(r => r.frameIndex)")


def capture(page, name, frame_index):
    """Send a captured frame the way the clip's Add reference button does, through the page."""
    count = len(frames(page))
    page.evaluate(
        """([name, frameIndex]) => {
          const studio = document.getElementById('video-studio');
          const canvas = document.createElement('canvas');
          canvas.width = 64;
          canvas.height = 36;
          return new Promise((resolve) => canvas.toBlob((blob) => {
            document.dispatchEvent(new CustomEvent('video-frame-captured', {detail: {
              blob, name, target: 'video', epoch: studio.captureInputEpoch(), frameIndex,
            }}));
            resolve();
          }, 'image/png'));
        }""",
        [name, frame_index],
    )
    page.wait_for_function(f"() => document.getElementById('video-studio').imageReferences.length === {count + 1}")


with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    page = browser.new_page(viewport={"width": 1280, "height": 850})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(URL)
    page.locator("#media-video-mode").click()
    page.get_by_role("button", name="Set duration to 10 seconds").click()
    page.wait_for_function("() => document.getElementById('video-studio').frameLimit === 241")

    upload = page.locator("#video-media-upload")
    upload.set_input_files([picture("a.png", "red"), picture("b.png", "green"), picture("c.png", "blue")])
    page.wait_for_function("() => document.getElementById('video-studio').imageReferences.length === 3")
    check(
        "three pictures picked at once go to the first, the last and the middle frame",
        frames(page) == [0, 240, 120],
        str(frames(page)),
    )

    upload.set_input_files(picture("d.png", "white"))
    page.wait_for_function("() => document.getElementById('video-studio').imageReferences.length === 4")
    check("a fourth picture goes to the widest gap", frames(page) == [0, 240, 120, 60], str(frames(page)))

    capture(page, "clip frame 0:00", 0)
    check(
        "a frame captured at 0:00 takes the nearest free frame", frames(page) == [0, 240, 120, 60, 1], str(frames(page))
    )

    page.get_by_role("button", name="Set duration to 5 seconds").click()
    page.wait_for_function("() => document.getElementById('video-studio').frameLimit === 121")
    moved = frames(page)
    check(
        "a shorter clip keeps the end picture on the last frame and steps the middle one back",
        moved == [0, 120, 119, 60, 1],
        str(moved),
    )
    toast = page.locator("#toasts").inner_text()
    check(
        "the toast says that two pictures moved inside the clip",
        "2 image references moved inside the 121-frame clip, one per frame" in toast,
        toast,
    )
    with page.expect_request(lambda request: request.url.endswith("/video/generate")) as sent:
        page.fill("#video-prompt", "Five colours in a row.")
        page.locator("#video-generate").click()
    sent_frames = [reference["frame_index"] for reference in sent.value.post_data_json["references"]]
    check("the request sends one picture per frame", sorted(sent_frames) == [0, 1, 60, 119, 120], str(sent_frames))

    # A mode that pins its look image, such as Layout to Render, holds a capture on its frame.
    page.wait_for_function("() => document.getElementById('video-studio').captureInputEpoch() !== null")
    page.evaluate(
        """() => {
          const studio = document.getElementById('video-studio');
          studio.clearImageReferences();
          studio.lockReferenceFrame(0);
        }"""
    )
    capture(page, "clip frame 0:01", 24)
    locked = frames(page)
    page.evaluate("() => document.getElementById('video-studio').lockReferenceFrame(null)")
    check("a capture on a locked rail goes to the locked frame", locked == [0], str(locked))
    check("no page error", not errors, "; ".join(errors))
    browser.close()

print("FAILURES:", failures)
sys.exit(1 if failures else 0)
