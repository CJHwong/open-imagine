"""The line a run adds under a song does not squeeze the song's own details.

A run shows one more caption in the details bar. On the bar's line it took the width
the about block needed, and that block collapsed to nothing: every label stacked and
the bar grew to twice its height. It takes a line of its own instead.

No model and no GPU.
    uv run --with playwright python tests/e2e/verify_music_busy_bar.py
"""

import threading
from contextlib import contextmanager
from dataclasses import replace
from http.server import ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

from studio.l4_frameworks_and_drivers.config import load_config
from studio.l4_frameworks_and_drivers.main import IMAGE_BACKEND_FACTORIES, create_studio


@contextmanager
def stub():
    config = load_config(Path("studio.toml"), backend="qwen21", visible=tuple(IMAGE_BACKEND_FACTORIES))
    config = replace(config, visible_music_backends=("yue2",))
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


checks = []


def check(label, value, detail=""):
    assert value, label + (" " + str(detail) if detail else "")
    checks.append(label)
    print("PASS", label, ("(" + str(detail) + ")") if detail else "", flush=True)


with stub() as base, sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    page = browser.new_context(viewport={"width": 1520, "height": 1150}, locale="en-US").new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(base + "/?workspace=music")
    page.wait_for_selector("#music-generate")
    page.fill("#music-style", "warm acoustic folk")
    page.wait_for_timeout(300)
    page.click("#music-generate")
    page.wait_for_selector(".music-song", state="attached", timeout=30000)
    page.wait_for_timeout(2000)

    def boxes():
        return page.evaluate("""() => {
          const bar = document.querySelector('.music-output-details');
          const rect = element => element.getBoundingClientRect();
          return {
            about: rect(bar.querySelector('.about')).width,
            help: rect(bar.querySelector('.music-action-help')).width,
            bar: rect(bar).width,
            height: rect(bar).height,
          };
        }""")

    idle = boxes()
    check("the idle bar keeps the song's details on one line", idle["height"] < 120, idle)

    # The line is the page's own element for the busy state: `actionHelp.hidden = !busy`.
    page.evaluate("document.querySelector('.music-action-help').hidden = false")
    page.wait_for_timeout(300)
    busy = boxes()
    check("the run's line takes the width of the bar", busy["help"] > busy["bar"] * 0.9, busy)
    check("and the details keep their own width", busy["about"] > busy["bar"] * 0.4, busy)
    check("so the bar stays as tall as its content", busy["height"] < 160, busy)
    check("no page errors", not errors, errors)

    page.screenshot(path="/tmp/verify-music-busy-bar.png")
    browser.close()

print(len(checks), "checks passed")
