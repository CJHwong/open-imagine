"""Check that an open video form follows a model switch made elsewhere. Run against a fresh
stub that offers two video models with different lengths and sizes:

uv run studio --stub \
    --config studio/l3_interface_adapters/gateways/video/minimax_h3/studio.toml --port <port>
uv run --with playwright python tests/e2e/verify_video_model_switch.py <port>

Another tab or an API caller can switch the video model. The open page learns of it from its
state poll, and it must then draw the new model's durations, shapes and sizes. Before, it kept
the old model's controls, and its next run sent sizes that the new model refuses.

The inputs on the form stay, except the ones the new model refuses. A Sound switched off on a
model that can leave out its audio comes back on for one that cannot, and stills past the new
model's limit and a track that its mode cannot follow leave the form. The old model's draft
keeps them, so a switch back brings them back.
"""

import io
import json
import struct
import sys
import urllib.request
import zlib

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


def form(page):
    """What the form offers now: the slider, the preset labels, the shapes and the label."""
    return page.evaluate(
        """() => ({
          min: Number(document.getElementById('video-duration').min),
          max: Number(document.getElementById('video-duration').max),
          step: Number(document.getElementById('video-duration').step),
          presets: [...document.querySelectorAll('[data-duration-frames]')].map(b => Number(b.dataset.durationFrames)),
          ratios: [...document.querySelectorAll('.video-ratios button')].map(b => b.dataset.ratio),
          label: document.getElementById('video-frame-count').textContent,
        })"""
    )


def png(red):
    """A small solid PNG, so the check needs no image file."""
    row = b"\x00" + bytes((red, 80, 160)) * 8
    chunks = [
        (b"IHDR", struct.pack(">IIBBBBB", 8, 8, 8, 2, 0, 0, 0)),
        (b"IDAT", zlib.compress(row * 8)),
        (b"IEND", b""),
    ]
    body = b"".join(
        struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data)) for kind, data in chunks
    )
    return b"\x89PNG\r\n\x1a\n" + body


def wav():
    """One second of silence at 16 kHz."""
    import wave

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as track:
        track.setnchannels(1)
        track.setsampwidth(2)
        track.setframerate(16000)
        track.writeframes(b"\0\0" * 16000)
    return buffer.getvalue()


def inputs(page):
    """What the form holds: its stills, its track and its Sound switch."""
    return page.evaluate(
        """() => ({
          stills: document.getElementById('video-studio').imageReferences.length,
          audio: Boolean(document.getElementById('video-studio').audio),
          sound: document.getElementById('video-audio-track').getAttribute('aria-pressed'),
          frames: Number(document.getElementById('video-duration').value),
        })"""
    )


def switch(page, backend, name):
    api("/api/v1/videos/backend", {"backend": backend})
    page.wait_for_function(
        "(name) => document.getElementById('backend-toggle')?.textContent.includes(name)", arg=name, timeout=30000
    )


def generate(page):
    with page.expect_response(lambda response: response.url.endswith("/video/generate")) as answered:
        page.fill("#video-prompt", "A paper boat on a pond.")
        page.locator("#video-generate").click()
    page.wait_for_function("() => document.getElementById('video-studio').captureInputEpoch() !== null")
    return answered.value.request.post_data_json, answered.value


def saved(page, backend, condition):
    """Wait until the draft for this backend meets the condition, read straight from storage."""
    page.wait_for_function(
        """([key, condition]) => new Promise(resolve => {
          const open = indexedDB.open('studio-drafts');
          open.onsuccess = () => {
            const read = open.result.transaction('inputs').objectStore('inputs').get(key);
            read.onsuccess = () => resolve(Boolean(read.result) && new Function('inputs', 'return ' + condition)(read.result.inputs));
          };
        })""",
        arg=[f"video:{backend}", condition],
        timeout=10000,
    )


def forget_draft(page, backend):
    """Delete this backend's video draft, so a switch to it meets a model with no draft."""
    page.evaluate(
        """(key) => new Promise(resolve => {
          const open = indexedDB.open('studio-drafts');
          open.onsuccess = () => {
            const removal = open.result.transaction('inputs', 'readwrite').objectStore('inputs').delete(key);
            removal.onsuccess = () => resolve();
          };
        })""",
        f"video:{backend}",
    )


def watch_toasts(page):
    """Record the text of every toast the page raises from now on."""
    # LEFT: `#toasts` has no role, and the check is about the words a toast carries.
    page.evaluate(
        """() => {
          window.toastsSeen = [];
          window.toastWatch?.disconnect();
          window.toastWatch = new MutationObserver(records => records.forEach(record =>
            record.addedNodes.forEach(node => window.toastsSeen.push(node.textContent || ''))));
          window.toastWatch.observe(document.getElementById('toasts'), {childList: true, subtree: true});
        }"""
    )


def toasts_seen(page):
    page.wait_for_timeout(500)
    return " | ".join(page.evaluate("() => window.toastsSeen"))


def offered(capabilities):
    ratios = []
    for shape in capabilities["shapes"]:
        if shape["ratio"] not in ratios:
            ratios.append(shape["ratio"])
    return {
        "min": capabilities["min_frames"],
        "max": capabilities["max_frames"],
        "step": capabilities["frame_step"],
        "presets": list(capabilities["duration_presets"]),
        "ratios": ratios,
    }


video = api("/api/v1/studio")["video"]
first = video["active"]
other = next(backend["id"] for backend in video["backends"] if backend["id"] != first)
models = {one: api(f"/api/v1/videos/backends/{one}") for one in (first, other)}
check(
    "the stub offers two video models that differ in length and shape",
    offered(models[first]) != offered(models[other]),
    f"{first} and {other}",
)

with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    page = browser.new_page(viewport={"width": 1280, "height": 850})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(BASE + "/?lang=en")
    page.locator("#media-video-mode").click()
    shown = form(page)
    check(
        f"the form opens on {first}'s own lengths and shapes",
        {key: shown[key] for key in offered(models[first])} == offered(models[first]),
        json.dumps(shown),
    )

    # A switch the page did not make: the same call another tab or a script makes.
    switch(page, other, models[other]["name"])
    shown = form(page)
    check(
        f"after a switch elsewhere, the form offers {other}'s lengths and shapes",
        {key: shown[key] for key in offered(models[other])} == offered(models[other]),
        json.dumps(shown),
    )
    default_frames = models[other]["default_frames"]
    check(
        f"the label names {other}'s own default length",
        shown["label"].endswith(f"{default_frames} frames"),
        shown["label"],
    )

    sent, answer = generate(page)
    sizes = {(shape["width"], shape["height"]) for shape in models[other]["shapes"]}
    check(
        f"the next run asks {other} for a length and a size it offers",
        sent["backend"] == other
        and models[other]["min_frames"] <= sent["num_frames"] <= models[other]["max_frames"]
        and (sent["width"], sent["height"]) in sizes,
        f"{sent['backend']} {sent['width']}x{sent['height']} {sent['num_frames']} frames",
    )
    check("the server accepts that run", answer.ok, str(answer.status))

    # Phase A. Fill the form on this model with what the first model may refuse: Sound off,
    # one still more than the first model takes, and the longest length. The draft keeps them
    # under this model's name.
    longest = models[other]["duration_presets"][-1]
    stills = min(models[other]["max_references"], models[first]["max_references"] + 1)
    page.locator(f'[data-duration-frames="{longest}"]').click()
    if models[other]["can_skip_audio"]:
        page.locator("#video-advanced summary").click()
        page.locator("#video-audio-track").click()
    page.locator("#video-media-upload").set_input_files(
        [
            {"name": f"still-{index}.png", "mimeType": "image/png", "buffer": png((40 + 50 * index) % 256)}
            for index in range(stills)
        ]
    )
    page.wait_for_function(
        "(count) => document.getElementById('video-studio').imageReferences.length === count", arg=stills
    )
    before = inputs(page)
    print("  phase A on", other, json.dumps(before), flush=True)
    check(
        f"{other} takes Sound off and {stills} stills",
        before["stills"] == stills and before["sound"] != "true",
        json.dumps(before),
    )
    saved(page, other, f"inputs.assets.imageReferences.length === {stills} && inputs.includeAudio === false")

    watch_toasts(page)
    switch(page, first, models[first]["name"])
    shown = form(page)
    check(
        f"a switch back to {first} restores its own lengths and shapes",
        {key: shown[key] for key in offered(models[first])} == offered(models[first]),
        json.dumps(shown),
    )
    after = inputs(page)
    check(
        f"{first} keeps the stills it can take and drops the rest",
        after["stills"] == min(before["stills"], models[first]["max_references"]),
        f"{after['stills']} of {before['stills']}, limit {models[first]['max_references']}",
    )
    if not models[first]["can_skip_audio"]:
        check(f"{first} cannot leave out its sound, so Sound is on again", after["sound"] == "true", after["sound"])
    removed = after["stills"] < before["stills"]
    toasts = toasts_seen(page)
    check(
        "a toast says what left the form, and only when something did",
        ("cannot use some pictures" in toasts) == removed,
        toasts,
    )
    sent, answer = generate(page)
    check(
        f"the run on {first} sends its sound and only the stills it takes",
        sent["backend"] == first
        and sent.get("include_audio", True) is True
        and len(sent.get("references") or []) <= models[first]["max_references"],
        f"include_audio {sent.get('include_audio')}, {len(sent.get('references') or [])} stills",
    )
    check(f"the server accepts the run on {first}", answer.ok, str(answer.status))

    # Phase B. The old model's draft brings its inputs back. Then a track, which the first
    # model's mode may not follow.
    switch(page, other, models[other]["name"])
    page.wait_for_function(
        "(frames) => Number(document.getElementById('video-duration').value) === frames", arg=longest, timeout=10000
    )
    restored = inputs(page)
    check(
        f"a switch back to {other} brings its own draft back",
        restored == before,
        f"{json.dumps(restored)} against {json.dumps(before)}",
    )
    page.locator("#video-media-upload").set_input_files(
        [{"name": "voice.wav", "mimeType": "audio/wav", "buffer": wav()}]
    )
    page.wait_for_function("() => document.getElementById('video-studio').audio !== null")
    saved(page, other, "inputs.assets.audio != null")

    # The run in phase A left a draft for the first model, and a draft replaces the form. The
    # case here is a model with no draft of its own, as in phase A.
    forget_draft(page, first)
    watch_toasts(page)
    switch(page, first, models[first]["name"])
    first_mode = (models[first]["modes"] or [{"accepts_audio": False}])[0]
    kept_audio = first_mode.get("accepts_audio", False)
    after = inputs(page)
    check(f"{first} keeps the track only if its mode follows one", after["audio"] == kept_audio, json.dumps(after))
    toasts = toasts_seen(page)
    check(
        "a toast says the track left the form, and only when it did",
        ("cannot use some pictures" in toasts) == (not kept_audio or after["stills"] < stills),
        toasts,
    )
    sent, answer = generate(page)
    check(
        f"the run on {first} sends a track only if it follows one",
        sent["backend"] == first and (sent.get("audio") is None) == (not kept_audio),
        f"audio {sent.get('audio') is not None}",
    )
    check(f"the server accepts that run on {first}", answer.ok, str(answer.status))
    # Hold media preparation while another client switches the model. The request
    # must keep the model, geometry and controls captured by the original press.
    switch(page, other, models[other]["name"])
    page.fill("#video-prompt", "A paper boat on a pond.")
    page.evaluate("""() => {
      const video = document.getElementById('video-studio');
      video.audioPayload = () => new Promise(resolve => { window.releaseVideoAudio = () => resolve(undefined); });
    }""")
    page.locator("#video-generate").click()
    page.wait_for_function("typeof window.releaseVideoAudio === 'function'")
    switch(page, first, models[first]["name"])
    with page.expect_response(lambda response: response.url.endswith("/video/generate")) as prepared:
        page.evaluate("window.releaseVideoAudio()")
    request = prepared.value.request.post_data_json
    check(
        "a model switch during media preparation keeps the submitted model",
        request["backend"] == other,
        request["backend"],
    )
    check(
        "a changed model is refused explicitly rather than receiving mixed settings",
        prepared.value.status == 503 and "video model changed" in prepared.value.json().get("error", "").lower(),
        str(prepared.value.status),
    )
    check("no page error", not errors, "; ".join(errors))
    browser.close()

print("FAILURES:", failures)
sys.exit(1 if failures else 0)
