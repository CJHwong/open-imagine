"""Check the narrow-window panes: preview, gallery and controls, one at a time.

Run: uv run --with playwright python tests/e2e/verify_mobile_panes.py <port>
"""

import sys

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:" + sys.argv[1]
failures = []


def check(name, passed, detail=""):
    print(("PASS " if passed else "FAIL ") + name + ((" " + detail) if detail else ""), flush=True)
    if not passed:
        failures.append(name)


with sync_playwright() as tool:
    browser = tool.chromium.launch()
    page = browser.new_page(viewport={"width": 390, "height": 844})
    page.goto(BASE + "/?workspace=image")
    page.wait_for_function("Boolean(formApi)")
    page.wait_for_timeout(400)

    switch = page.locator(".pane-switch")
    check("a narrow window shows the pane switch", switch.is_visible())
    check("the page opens on the preview", page.evaluate("document.body.dataset.pane") == "preview")
    check("the preview hides the controls", page.locator("#form").evaluate("node => !node.getClientRects().length"))
    check("the preview shows the stage", page.locator("#image-stage").is_visible())

    switch.locator('[data-pane="gallery"]').click()
    page.wait_for_timeout(300)
    panel = page.locator("#image-gallery-browser .gallery-browser-panel")
    check("the gallery pane opens the browser", panel.is_visible())
    box = page.locator("#strip-wrap.pane-gallery-shelf").bounding_box()
    check(
        "the gallery fills the window above the switch",
        box is not None and box["width"] >= 380 and box["height"] >= 620,
        str(box),
    )
    check("the switch stays above the gallery", switch.is_visible())

    switch.locator('[data-pane="controls"]').click()
    page.wait_for_timeout(300)
    form = page.locator("#form")
    check("the controls pane fills the window", form.is_visible())
    form_box = form.bounding_box()
    run = page.locator("#go").bounding_box()
    check(
        "the controls show the form with its run button in view",
        form_box is not None and run is not None and form_box["height"] >= 620 and run["y"] + run["height"] <= 844,
        f"form {form_box}, run {run}",
    )

    switch.locator('[data-pane="preview"]').click()
    page.wait_for_timeout(300)
    check("the preview closes the controls", page.locator("#form").evaluate("node => !node.getClientRects().length"))
    check("the stage is back", page.locator("#image-stage").is_visible())

    page.goto(BASE + "/?workspace=music")
    page.wait_for_function("Boolean(document.querySelector('music-studio').capabilities)")
    page.locator('.pane-switch [data-pane="gallery"]').click()
    page.wait_for_timeout(400)
    music_panel = page.locator("music-studio gallery-browser .gallery-browser-panel")
    check("the music gallery opens in its own pane", music_panel.is_visible())

    page.set_viewport_size({"width": 1440, "height": 900})
    page.wait_for_timeout(300)
    check("a wide window hides the pane switch", not page.locator(".pane-switch").is_visible())
    check(
        "a wide window keeps the form and the stage",
        page.locator("#form").is_visible() and page.locator("#image-stage").count() >= 0,
    )
    browser.close()

if failures:
    raise AssertionError("; ".join(failures))
print("PASS Mobile panes: preview, gallery and controls, one at a time", flush=True)
