"""The run-time figure beside the voice button, for a mode that follows its script.

The audio length is not known until the engine speaks, so the page reads the backend's
measured seconds per character and the backend's own cost constants. No model, no GPU.

    uv run --with playwright python tests/e2e/verify_voice_estimate.py
"""

import math
import threading
from contextlib import contextmanager
from dataclasses import replace
from http.server import ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

from studio.l3_interface_adapters.gateways.voice.drama3.capabilities import ESTIMATE
from studio.l4_frameworks_and_drivers.config import load_config
from studio.l4_frameworks_and_drivers.main import IMAGE_BACKEND_FACTORIES, create_studio


@contextmanager
def stub():
    config = load_config(Path("studio.toml"), backend="qwen21", visible=tuple(IMAGE_BACKEND_FACTORIES))
    config = replace(config, visible_voice_backends=("drama3",))
    studio = create_studio(config, stub=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0), studio.handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield "http://127.0.0.1:" + str(server.server_port)
    finally:
        server.shutdown()
        server.server_close()
        studio.shutdown()
        thread.join()


def spell(seconds):
    """The page's own rounding, from lib/time-format.js."""
    if seconds < 90:
        return str(max(5, math.floor(seconds / 5 + 0.5) * 5)) + "s"
    minutes = int(seconds // 60)
    rest = math.floor((seconds % 60) / 15 + 0.5) * 15
    if rest and rest < 60:
        return str(minutes) + " min " + str(rest) + "s"
    return str(minutes + (1 if rest else 0)) + " min"


checks = []


def check(label, value, detail=""):
    assert value, label + (" " + str(detail) if detail else "")
    checks.append(label)
    print("PASS", label, ("(" + str(detail) + ")") if detail else "", flush=True)


with stub() as base, sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    page = browser.new_context(viewport={"width": 1440, "height": 1000}, locale="en-US").new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(base + "/?workspace=voice")
    page.wait_for_selector("#voice-text")

    check(
        "an empty script shows the reason, not a time",
        page.inner_text("#voice-go-sub").strip() == "Write the text to read",
    )

    script = "The harbour opens at six, and the first boat leaves at seven."
    page.fill("#voice-text", script)
    page.wait_for_timeout(500)
    expected = "about " + spell(ESTIMATE.overhead + ESTIMATE.rtf * len(script) * ESTIMATE.seconds_per_character)
    figure = page.inner_text("#voice-go-sub").strip()
    check("the figure is the backend's cost for the script it will speak", figure == expected, (figure, expected))

    longer = script + " " + "The wind is from the west and the water is flat. " * 3
    page.fill("#voice-text", longer)
    page.wait_for_timeout(500)
    bigger = "about " + spell(ESTIMATE.overhead + ESTIMATE.rtf * len(longer) * ESTIMATE.seconds_per_character)
    check(
        "a longer script asks for more time",
        page.inner_text("#voice-go-sub").strip() == bigger,
        page.inner_text("#voice-go-sub").strip(),
    )
    check("no page errors", not errors, errors)

    browser.close()

print(len(checks), "checks passed")
