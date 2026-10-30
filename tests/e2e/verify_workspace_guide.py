"""Workspace-aware guidance on a fresh stub, including model changes and mobile.

uv run studio --stub --port <port>
uv run --with playwright python tests/e2e/verify_workspace_guide.py <port>
"""

import sys

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:" + sys.argv[1]

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(URL)
    toggle = page.locator("#guide-toggle")
    sheet = page.locator("#guide-sheet")
    for width in (1440, 390):
        page.set_viewport_size({"width": width, "height": 1000 if width == 1440 else 844})
        for workspace, topic in [
            ("image", "Mark a region"),
            ("video", "Fast mode"),
            ("voice", "Audio token limit"),
            ("music", "Edit score"),
        ]:
            page.locator("#media-" + workspace + "-mode").click()
            page.wait_for_function(
                '(mode) => document.querySelector("#media-" + mode + "-mode").getAttribute("aria-pressed") === "true"',
                arg=workspace,
            )
            toggle.click()
            sheet.wait_for(state="visible")
            assert topic in sheet.inner_text(), (workspace, sheet.inner_text())
            if workspace == "voice":
                actions = sheet.locator("dt", has_text="Clip actions").locator("+ dd").inner_text()
                assert "edit" not in actions.lower(), actions
            assert sheet.locator("a").get_attribute("href") == "/api/docs"
            assert toggle.get_attribute("aria-expanded") == "true"
            box = sheet.bounding_box()
            assert box and box["width"] > 100 and box["height"] > 100
            assert box["x"] >= 0 and box["x"] + box["width"] <= width + 1
            assert sheet.locator("dd").evaluate_all("(els) => els.every(el => el.scrollWidth <= el.clientWidth)")
            page.keyboard.press("Escape")
            assert sheet.count() == 0 and toggle.get_attribute("aria-expanded") == "false"
            assert toggle.evaluate("(el) => el === document.activeElement")
            # The sheet is modal, so the toggle is behind its backdrop and the
            # close button is the second way out.
            toggle.click()
            sheet.wait_for(state="visible")
            sheet.get_by_role("button", name="Close").click()
            assert sheet.count() == 0 and toggle.get_attribute("aria-expanded") == "false"
            print(
                "PASS",
                width,
                workspace,
                "visible guide, correct content, wrapping, docs, toggle and Escape",
                flush=True,
            )
    # The guide is a modal sheet, so the workspace tabs and the model picker sit
    # behind its backdrop and wait for it to close.
    toggle.click()
    sheet.wait_for(state="visible")
    sheet.get_by_role("button", name="Close").click()
    assert sheet.count() == 0 and toggle.get_attribute("aria-expanded") == "false"
    page.locator("#media-video-mode").click()
    page.wait_for_function('document.querySelector("#media-video-mode").getAttribute("aria-pressed") === "true"')
    print("PASS the guide is modal and leaves before the workspace switch", flush=True)
    page.locator("#media-voice-mode").click()
    page.wait_for_function('document.querySelector("#media-voice-mode").getAttribute("aria-pressed") === "true"')
    page.locator("#backend-toggle").click()
    page.get_by_role("menuitemradio", name="AuK", exact=True).click()
    page.wait_for_function('document.querySelector("#voice-studio").capabilities.backend_id === "auk_base"')
    assert sheet.count() == 0
    toggle.click()
    assert "does not require a transcript" in sheet.inner_text()
    assert "Audio token limit" not in sheet.inner_text()
    page.keyboard.press("Escape")
    print("PASS a model change reaches its own help", flush=True)
    catalog = page.request.get(URL + "/api/v1/studio").json()["video"]["backends"]
    if any(model["id"] == "ltx23_mlx" for model in catalog):
        page.locator("#media-video-mode").click()
        page.wait_for_function('document.querySelector("#media-video-mode").getAttribute("aria-pressed") === "true"')
        page.locator("#backend-toggle").click()
        page.get_by_role("menuitemradio", name="LTX-2.3", exact=True).click()
        page.wait_for_function('STUDIO.video.backend.id === "ltx23_mlx"')
        toggle.click()
        entries = sheet.locator("dt").all_inner_texts()
        assert "Generate, or Edit" not in entries and "Fast mode" not in entries
        assert "edit" not in sheet.inner_text().lower()
        print("PASS LTX-2.3 hides unsupported Edit and Fast mode instructions", flush=True)
    assert not errors, errors
    print("PASS no browser errors", flush=True)
    browser.close()
