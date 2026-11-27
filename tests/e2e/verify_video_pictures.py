"""Check the video form's References tray against a fresh stub with every backend:

uv run studio --stub --backend qwen21 --all-backends --port <port>
uv run --with playwright python tests/e2e/verify_video_pictures.py <port>

MiniMax H3 on CUDA takes up to nine pictures and an audio track as references, and no keyframe
beside them. The tray numbers the pictures in the order the request sends them, and a press on a
label puts it in the prompt. A plain add goes to the zone in use, and to the timeline while both
are empty. A keyframe there sits on the first or the last frame. LTX offers no pictures.
"""

import io
import json
import sys
import urllib.request
import wave

from PIL import Image
from playwright.sync_api import sync_playwright

BASE = f"http://127.0.0.1:{sys.argv[1]}"
failures = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f" ({detail})" if detail else ""), flush=True)
    if not ok:
        failures.append(name)


def api(path, body=None):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(BASE + path, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as answer:
        return json.loads(answer.read() or b"null")


def picture(name, colour):
    data = io.BytesIO()
    Image.new("RGB", (64, 36), colour).save(data, "PNG")
    return {"name": name, "mimeType": "image/png", "buffer": data.getvalue()}


def track():
    data = io.BytesIO()
    with wave.open(data, "wb") as sound:
        sound.setnchannels(1)
        sound.setsampwidth(2)
        sound.setframerate(16000)
        sound.writeframes(b"\0\0" * 16000)
    return {"name": "voice.wav", "mimeType": "audio/wav", "buffer": data.getvalue()}


def state(page):
    return page.evaluate(
        """() => {
          const studio = document.getElementById('video-studio');
          return {pictures: studio.pictures.map(p => p.name), keyframes: studio.imageReferences.map(r => r.frameIndex),
            audio: Boolean(studio.audio), error: document.querySelector('#video-studio .error, #video-error')?.textContent || ''};
        }"""
    )


def switch(page, backend, pictures):
    """Switch on the server, then load the page. A switch the page hears mid-way moves the
    form's input epoch, and a file read across it is dropped on purpose. Returns False when
    the server cannot offer the backend, such as MLX on a host that has no MLX stack."""
    try:
        api("/api/v1/videos/backend", {"backend": backend})
    except urllib.error.HTTPError as error:
        if error.code == 503:
            print(f"SKIP {backend}: the server does not offer it on this host", flush=True)
            return False
        raise
    page.goto(BASE + "/?lang=en")
    page.locator("#media-video-mode").click()
    page.wait_for_function(
        "(max) => document.getElementById('video-studio').maxPictures === max", arg=pictures, timeout=30000
    )
    return True


def labels(page):
    return page.locator("#video-pictures .video-picture-label").all_inner_texts()


def errors_shown(page):
    return page.evaluate("() => document.getElementById('video-studio').error || ''")


with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    page = browser.new_page(viewport={"width": 1280, "height": 850})
    page_errors = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    switch(page, "minimax_h3_cuda", 9)
    add = page.locator("#video-add-pictures")
    check("H3 on CUDA offers a Picture button", add.is_visible() and add.get_attribute("aria-disabled") == "false")

    page.locator("#video-picture-upload").set_input_files([picture("cube.png", "green"), picture("star.png", "purple")])
    page.wait_for_function("() => document.getElementById('video-studio').pictures.length === 2")
    check(
        "the tray numbers two pictures in the order picked",
        labels(page) == ["<Picture 1>", "<Picture 2>"],
        str(labels(page)),
    )
    check("the tray shows itself", page.locator("#video-picture-tray").is_visible())

    page.fill("#video-prompt", "The cube slides under")
    page.locator("#video-pictures .video-picture-label").nth(1).click()
    prompt = page.input_value("#video-prompt")
    check("a label press puts the label in the prompt", prompt == "The cube slides under <Picture 2>", prompt)

    page.locator("#video-media-upload").set_input_files(picture("table.png", "brown"))
    page.wait_for_function("() => document.getElementById('video-studio').pictures.length === 3")
    check("a plain add joins the tray while it is in use", state(page)["keyframes"] == [], str(state(page)))

    page.locator("#video-media-upload").set_input_files(track())
    page.wait_for_function("() => Boolean(document.getElementById('video-studio').audio)")
    check("the track sits in the tray as <Audio 1>", labels(page)[-1] == "<Audio 1>", str(labels(page)))
    check("the soundtrack tray stays hidden", page.locator("#video-audio-tray").is_hidden())

    blocked = page.evaluate(
        """() => {
          const studio = document.getElementById('video-studio');
          studio.addImageReference({id: 'video-ref-test', name: 'first.png', src: '', base64: studio.pictures[0].base64});
          return [studio.imageReferences.length, studio.error];
        }"""
    )
    check(
        "a keyframe beside the references is refused with the reason",
        blocked[0] == 0 and "keyframes or references, not both" in blocked[1],
        str(blocked),
    )

    with page.expect_request(lambda request: request.url.endswith("/video/operations")) as sent:
        page.locator("#video-generate").click()
    body = sent.value.post_data_json
    check(
        "the run sends the pictures in tray order, the track and no keyframe",
        [one["name"] for one in body["pictures"]] == ["cube.png", "star.png", "table.png"]
        and body["audio"] is not None
        and body["references"] == [],
        str([one["name"] for one in body["pictures"]]),
    )
    page.wait_for_function("() => document.getElementById('video-studio').captureInputEpoch() !== null", timeout=60000)
    plan = api(
        "/api/v1/videos/plan",
        {
            "backend": "minimax_h3_cuda",
            "width": 512,
            "height": 288,
            "num_frames": 124,
            "frame_rate": 24,
            "picture_count": 2,
        },
    )
    text = api(
        "/api/v1/videos/plan",
        {"backend": "minimax_h3_cuda", "width": 512, "height": 288, "num_frames": 124, "frame_rate": 24},
    )
    check(
        "a plan with two pictures costs more than text",
        plan["estimate"]["total_seconds"] > text["estimate"]["total_seconds"],
        f"{plan['estimate']['total_seconds']} s against {text['estimate']['total_seconds']} s",
    )

    page.evaluate(
        """() => {
          const studio = document.getElementById('video-studio');
          [...studio.pictures].forEach(p => studio.removePicture(p.id));
          studio.clearAudio();
        }"""
    )
    page.locator("#video-media-upload").set_input_files(picture("first.png", "red"))
    page.wait_for_function("() => document.getElementById('video-studio').imageReferences.length === 1")
    check("a plain add on an empty form goes to the timeline", state(page)["pictures"] == [], str(state(page)))
    # Playwright treats aria-disabled as disabled and would wait; a person can still press it.
    add.evaluate("(button) => button.click()")
    reason = errors_shown(page)
    check(
        "the Picture button is off beside a keyframe and a press says why",
        add.get_attribute("aria-disabled") == "true" and "Remove the keyframes" in reason,
        reason,
    )
    heading = page.locator("#video-reference-tray strong").first.inner_text()
    check("the timeline is named Keyframes beside the tray", heading == "Keyframes", heading)

    moved = page.evaluate(
        """() => {
          const studio = document.getElementById('video-studio');
          studio.assignReferenceFrame(studio.imageReferences[0].id, 100);
          return studio.imageReferences.map(r => r.frameIndex);
        }"""
    )
    check("a keyframe moved past the middle snaps to the last frame", moved == [123], str(moved))
    page.locator("#video-media-upload").set_input_files(picture("last.png", "blue"))
    page.wait_for_function("() => document.getElementById('video-studio').imageReferences.length === 2")
    check("a second keyframe takes the free end", sorted(state(page)["keyframes"]) == [0, 123], str(state(page)))

    page.locator("#video-media-upload").set_input_files(track())
    refused = errors_shown(page)
    check(
        "a track beside keyframes is refused with the reason",
        not state(page)["audio"] and "goes with pictures" in refused,
        refused,
    )

    if switch(page, "minimax_h3", 9):
        page.locator("#video-media-upload").set_input_files(picture("start.png", "red"))
        page.wait_for_function("() => document.getElementById('video-studio').imageReferences.length === 1")
        page.locator("#video-picture-upload").set_input_files(picture("cast.png", "green"))
        page.wait_for_function("() => document.getElementById('video-studio').pictures.length === 1")
        check(
            "H3 on MLX takes a picture beside a keyframe and numbers it after the keyframe",
            labels(page) == ["<Picture 2>"],
            str(labels(page)),
        )
        with page.expect_request(lambda request: request.url.endswith("/video/operations")) as sent:
            page.fill("#video-prompt", "<Picture 2> walks in.")
            page.locator("#video-generate").click()
        body = sent.value.post_data_json
        check(
            "H3 on MLX sends the keyframe and the picture together",
            len(body["references"]) == 1 and [one["name"] for one in body["pictures"]] == ["cast.png"],
            str(len(body["references"])),
        )
        page.wait_for_function(
            "() => document.getElementById('video-studio').captureInputEpoch() !== null", timeout=60000
        )

    # Three keyframes, the frame-0 one added last, then a switch another caller makes. The page
    # trims to two in add order, so the snap must not leave both on the last frame. A fresh
    # browser holds no CUDA draft, so the switch keeps the form instead of restoring one.
    fresh = browser.new_page(viewport={"width": 1280, "height": 850})
    fresh.on("pageerror", lambda error: page_errors.append(str(error)))
    if switch(fresh, "minimax_h3", 9):
        for name, colour in (("a.png", "red"), ("b.png", "blue"), ("c.png", "green")):
            fresh.locator("#video-media-upload").set_input_files(picture(name, colour))
        fresh.wait_for_function("() => document.getElementById('video-studio').imageReferences.length === 3")
        fresh.evaluate(
            """() => {
              const studio = document.getElementById('video-studio');
              const frames = [36, 72, 0];
              studio.imageReferences = studio.imageReferences.map((one, index) => ({...one, frameIndex: frames[index]}));
              studio.renderImageReferences();
            }"""
        )
        api("/api/v1/videos/backend", {"backend": "minimax_h3_cuda"})
        fresh.wait_for_function(
            "() => document.getElementById('video-studio').keyframesAtEnds"
            " && document.getElementById('video-studio').imageReferences.length === 2",
            timeout=30000,
        )
        ends = sorted(state(fresh)["keyframes"])
        check("a switch to H3 on CUDA keeps one keyframe on each end", ends == [0, 123], str(ends))
        fresh.close()

    switch(page, "minimax_h3_cuda", 9)
    page.evaluate(
        """() => {
          const studio = document.getElementById('video-studio');
          [...studio.imageReferences].forEach((one) => studio.removeImageReference(one.id));
        }"""
    )
    page.locator("#video-media-upload").set_input_files(track())
    page.wait_for_function("() => Boolean(document.getElementById('video-studio').audio)")
    page.locator("#video-media-upload").set_input_files(picture("guest.png", "green"))
    page.wait_for_function("() => document.getElementById('video-studio').pictures.length === 1", timeout=10000)
    check(
        "a plain add beside a reference track joins the tray",
        state(page)["keyframes"] == [] and labels(page)[0] == "<Picture 1>",
        str(state(page)),
    )

    switch(page, "minimax_h3_flash_cuda", 9)
    check("H3 Flash on CUDA offers the Picture button", add.is_visible())
    check("H3 Flash on CUDA offers no Fast mode", page.locator("#video-fast-field").is_hidden())
    page.locator("#video-picture-upload").set_input_files([picture("cube.png", "green")])
    page.wait_for_function("() => document.getElementById('video-studio').pictures.length >= 1")
    check("its tray numbers a picture", labels(page)[0] == "<Picture 1>", str(labels(page)))

    if switch(page, "minimax_h3_flash", 0):
        check("H3 Flash offers no Picture button", add.is_hidden())

    if switch(page, "ltx25_mlx", 0):
        check("LTX offers no Picture button", add.is_hidden())
        heading = page.locator("#video-reference-tray strong").first.inner_text()
        check("LTX keeps the name Image references", heading == "Image references", heading)
    check("no page error", not page_errors, "; ".join(page_errors))
    browser.close()

print("FAILURES:", failures)
sys.exit(1 if failures else 0)
