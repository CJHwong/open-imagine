"""The run-time figure beside the video button, read from the plan route.

The figure is asked of the backend's own plan, so this checks the page against the
answer that route gives for the body the page sent. It needs no model and no GPU.

    uv run --with playwright python tests/e2e/verify_video_estimate.py
"""

import math
import sys
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
    config = replace(config, visible_video_backends=("ltx25_mlx", "ltx23_mlx"))
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
    """The page's own rounding, from lib/time-format.js, so the two figures compare."""
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


def plan_response(page, action):
    with page.expect_response(lambda answer: answer.url.endswith("/api/v1/videos/plan")) as answered:
        action()
    return answered.value.json()["estimate"]["total_seconds"]


with stub() as url, sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    context = browser.new_context(viewport={"width": 1440, "height": 1000}, locale="en-US")
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    plans = []
    page.on("request", lambda request: plans.append(request.url) if request.url.endswith("/videos/plan") else None)
    page.goto(url)
    page.click("#media-video-mode")
    page.wait_for_selector("#video-prompt")

    check("an empty form asks for a prompt, not a time", page.inner_text("#video-go-sub").strip() == "Write a prompt")
    check("and no plan is asked for a form that cannot run", not plans, plans)

    total = plan_response(page, lambda: page.fill("#video-prompt", "A red kite over a grey sea, slow drift."))
    page.wait_for_function("document.querySelector('#video-go-sub').textContent.startsWith('about ')")
    figure = page.inner_text("#video-go-sub").strip()
    check("the figure is the plan's own answer", figure == "about " + spell(total), (figure, total))

    asked = len(plans)
    page.evaluate(
        "for (let i = 0; i < 5; i++) document.dispatchEvent(new CustomEvent('draft-change', {detail: 'video'}))"
    )
    page.wait_for_timeout(900)
    check("a redraw of an unchanged form asks nothing", len(plans) == asked, (len(plans), asked))

    longer = plan_response(
        page,
        lambda: page.evaluate(
            "(() => { const el = document.getElementById('video-duration'); el.value = '241';"
            " el.dispatchEvent(new Event('input', {bubbles: true})); })()"
        ),
    )
    page.wait_for_function("document.querySelector('#video-go-sub').textContent === '" + "about " + spell(longer) + "'")
    check(
        "a longer clip moves the figure",
        page.inner_text("#video-go-sub").strip() != figure,
        page.inner_text("#video-go-sub").strip(),
    )

    check("no page errors", not errors, errors)

    context.close()
    browser.close()

print(len(checks), "checks passed")
sys.exit(0)
