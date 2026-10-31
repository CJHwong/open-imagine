"""Check the Music reference recorder with a deterministic microphone input.

Run against a fresh `uv run studio --stub --all-backends --port <port>`.
"""

import sys

from playwright.sync_api import sync_playwright
from voice_helpers import synthetic_microphone

URL = "http://127.0.0.1:" + sys.argv[1]


def check(name, condition):
    assert condition, name
    print("PASS " + name, flush=True)


with sync_playwright() as tool:
    browser = tool.chromium.launch(args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"])
    context = browser.new_context(permissions=["microphone"], viewport={"width": 1440, "height": 1000})
    synthetic_microphone(context)
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(URL + "/?workspace=music")
    page.wait_for_function("document.getElementById('music-studio')?.capabilities")
    page.fill("#music-style", "warm analog synth")
    check("the reference head offers the recorder", page.locator("#music-reference-record").is_visible())
    page.evaluate("""() => {
      const original = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
      window.calls = 0;
      navigator.mediaDevices.getUserMedia = async options => { window.calls++; window.stream = await original(options); return window.stream; };
      const studio = document.getElementById('music-studio');
      studio.toggleRecording();
      studio.toggleRecording();
    }""")
    page.wait_for_function("document.getElementById('music-studio').recording")
    check("repeated presses acquire only one microphone stream", page.evaluate("window.calls") == 1)
    check("the button becomes Stop", page.locator("#music-reference-record").inner_text() == "Stop")
    check("a running take holds the run button", page.locator("#music-generate").is_disabled())
    check(
        "the held run button says why",
        page.locator("#music-generate .sub").inner_text() == "Stop the recording first",
    )
    page.wait_for_timeout(1200)
    page.locator("#music-reference-record").click()
    page.wait_for_function("document.getElementById('music-studio').reference", timeout=15000)
    check(
        "the take becomes a WAV reference the engine can read",
        page.evaluate("""() => {
          const reference = document.getElementById('music-studio').reference;
          return reference.name === 'hum-mmm.wav' && reference.blob.type === 'audio/wav' && reference.blob.size > 1000;
        }"""),
    )
    check("the recorded reference shows in the preview", page.locator(".music-reference-preview").is_visible())
    check("the recorder gives way to Replace", not page.locator("#music-reference-record").is_visible())
    # The hum is short, so the chip is the play control: hear it before the run. The player
    # is not in the page, so the form still holds no media element.
    page.locator("#music-reference-play").click()
    page.wait_for_function(
        "document.getElementById('music-studio').referencePlayer?.currentTime > 0",
        timeout=5000,
    )
    check(
        "the chip plays the recording",
        not page.evaluate("document.getElementById('music-studio').referencePlayer.paused"),
    )
    check(
        "the chip offers Pause while it plays",
        page.locator("#music-reference-play").get_attribute("aria-label") == "Pause",
    )
    page.locator("#music-reference-play").click()
    page.wait_for_function(
        "document.querySelector('#music-reference-play').getAttribute('aria-label') === 'Play'",
    )
    check(
        "a second press stops it",
        page.evaluate("document.getElementById('music-studio').referencePlayer.paused"),
    )
    check(
        "the run button promises a cover",
        page.locator("#music-generate .sub").inner_text() == "A new song from your recording",
    )
    page.locator("#music-reference-remove").click()
    page.wait_for_function("!document.getElementById('music-studio').reference")
    check("removing the reference brings the recorder back", page.locator("#music-reference-record").is_visible())
    page.evaluate("""() => {
      const studio = document.getElementById('music-studio');
      studio.toggleRecording();
    }""")
    page.wait_for_function("document.getElementById('music-studio').recording")
    page.get_by_role("button", name="Image", exact=True).click()
    page.wait_for_function("window.stream.getTracks().every(track => track.readyState === 'ended')", timeout=15000)
    check("leaving Music releases the microphone", True)
    page.get_by_role("button", name="Music", exact=True).click()
    page.wait_for_timeout(400)
    check(
        "a dropped take is not kept as a reference",
        page.evaluate("document.getElementById('music-studio').reference") is None,
    )
    check("no browser errors occurred", not errors)
    browser.close()
