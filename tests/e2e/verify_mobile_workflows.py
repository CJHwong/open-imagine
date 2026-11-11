"""Operate phone workflows against a fresh stub with all backends.

Run: uv run --with playwright python tests/e2e/verify_mobile_workflows.py <port>
"""

import re
import sys
import time

from playwright.sync_api import expect, sync_playwright
from settings_controls import open_settings
from style_controls import open_style_section

BASE = "http://127.0.0.1:" + sys.argv[1]


def pane(page, name):
    expect(page.locator("body")).to_have_attribute("data-pane", name)


def controls(page):
    page.locator('.pane-switch [data-pane="controls"]').tap()


def set_steps(page, steps):
    panel = page.locator("#advanced")
    if not panel.evaluate("element => element.open"):
        panel.locator("summary").tap()
    expect(panel).to_have_js_property("open", True)
    page.locator("#steps").fill(str(steps))
    panel.locator("summary").tap()


def reachable(locator):
    assert locator.evaluate("""button => {
        const rect = button.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0 && rect.top >= 0 && rect.bottom <= innerHeight
          && button.contains(document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2));
    }"""), "the control must receive a tap"


def swipe(page, direction, center=(195, 350)):
    session = page.context.new_cdp_session(page)
    horizontal, vertical = center
    session.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": horizontal, "y": vertical}]})
    for distance in (20, 45, 75, 110):
        session.send(
            "Input.dispatchTouchEvent",
            {
                "type": "touchMove",
                "touchPoints": [{"x": horizontal + distance * direction, "y": vertical + 2}],
            },
        )
        time.sleep(0.03)
    session.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
    session.detach()


def open_workspace(page, name):
    page.goto(BASE + "/?workspace=" + name)
    expect(page.locator("#media-" + name + "-mode")).to_have_attribute("aria-pressed", "true")
    pane(page, "preview")


def check_shortcuts(page):
    for workspace, shortcut, target in (
        ("image", ".canvas .video-empty .btn", "#templates"),
        ("video", "#video-studio .video-empty .btn", "#video-templates"),
        ("voice", ".voice-empty .btn", "#voice-text"),
        ("music", "#music-write", "#music-style"),
    ):
        open_workspace(page, workspace)
        page.locator(shortcut).tap()
        pane(page, "controls")
        expect(page.locator(target)).to_be_visible()
        if workspace in ("image", "video"):
            page.locator(target).get_by_role("menuitem").first.tap()
            pane(page, "controls")
            expect(page.locator("#prompt" if workspace == "image" else "#video-prompt")).to_be_focused()
        print("PASS", workspace, "preview shortcut opens the controls", flush=True)


def check_preview_tools(page):
    for width in (280, 320, 390, 768, 884):
        page.set_viewport_size({"width": width, "height": 844})
        workspace = page.locator("body").get_attribute("data-media")
        root = "#image-stage" if workspace == "image" else "#" + workspace + "-studio"
        actions = page.locator(root + " .stage-bar .actions:visible").first
        expect(actions).to_be_visible()
        for primary in actions.locator(".preview-primary-action").all():
            expect(primary).to_have_accessible_name(re.compile(r"\S"))
        rows = actions.evaluate("""row => [...row.children]
            .map(child => child.getBoundingClientRect()).filter(box => box.width)
            .map(box => box.top)""")
        assert max(rows) - min(rows) < 1, (workspace, width, rows)
        expect(page.locator(root + " .stage-bar .about").first).to_be_hidden()
        details = actions.locator(".preview-details-toggle")
        details.tap()
        sheet = page.locator("dialog.sheet[open]")
        expect(sheet).to_be_visible()
        expect(sheet.locator("dl").first).to_contain_text(re.compile("Seed", re.I))
        sheet.locator(".sheet-head .close").tap()
        expect(details).to_be_focused()
        edges = actions.evaluate("""row => {
            const children = [...row.children].map(child => child.getBoundingClientRect()).filter(box => box.width);
            return {right: row.getBoundingClientRect().right, last: Math.max(...children.map(box => box.right))};
        }""")
        assert abs(edges["right"] - edges["last"]) < 1, edges
        toggle = actions.locator(".menu-anchor > button[aria-controls]").first
        toggle.tap()
        menu = page.locator("#" + toggle.get_attribute("aria-controls"))
        expect(menu).to_be_visible()
        picker = page.locator(".mobile-menu-dialog[open]")
        bounds = picker.bounding_box()
        if width < 600:
            assert bounds["x"] == 0 and abs(bounds["width"] - width) <= 1 and bounds["height"] == 844, bounds
        else:
            assert bounds["x"] >= 20 and bounds["y"] >= 20, bounds
            assert bounds["x"] + bounds["width"] <= width - 20 and bounds["y"] + bounds["height"] <= 824, bounds
            assert abs(bounds["x"] * 2 + bounds["width"] - width) <= 2, bounds
            assert abs(bounds["y"] * 2 + bounds["height"] - 844) <= 2, bounds
        page.keyboard.press("Escape")
    page.set_viewport_size({"width": 390, "height": 844})
    print(
        "PASS metadata opens in Details, actions align right, cover menus fill the screen, inner-screen menus center",
        flush=True,
    )


def check_image(page):
    open_workspace(page, "image")
    for prompt in ("A red cup.", "A blue cup."):
        controls(page)
        set_steps(page, 1)
        page.locator("#prompt").fill(prompt)
        page.locator("#go").tap()
        pane(page, "preview")
        page.wait_for_function("!busy() && !sharedOperation", timeout=60000)
        expect(page.locator(".pic img").first).to_have_attribute("alt", prompt)
    check_preview_tools(page)
    newest = page.locator(".pic img").first.get_attribute("alt")
    page.locator(".pane-switch [data-pane=preview]").focus()
    page.keyboard.press("ArrowRight")
    older = page.locator(".pic img").first.get_attribute("alt")
    assert older != newest
    swipe(page, 1)
    expect(page.locator(".pic img").first).to_have_attribute("alt", newest)
    swipe(page, -1)
    expect(page.locator(".pic img").first).to_have_attribute("alt", older)
    print("PASS touch swipes follow the same gallery order as arrow keys", flush=True)
    page.locator(".pane-switch [data-pane=gallery]").tap()
    page.locator("gallery-browser .gallery-card").first.tap()
    pane(page, "preview")
    page.get_by_role("button", name="Edit this", exact=True).tap()
    pane(page, "controls")
    expect(page.locator("#mode-edit")).to_be_checked()
    expect(page.locator("#prompt")).to_be_focused()
    print("PASS gallery selection previews the item and Edit opens its controls", flush=True)
    page.locator("#prompt").fill("Make the cup green.")
    set_steps(page, 40)
    page.locator("#go").tap()
    pane(page, "preview")
    expect(page.locator("#shared-operation")).to_be_visible(timeout=15000)
    controls(page)
    reachable(page.locator("#shared-operation-cancel"))
    page.locator("#shared-operation-cancel").tap()
    pane(page, "controls")
    page.wait_for_function("!busy() && !sharedOperation", timeout=15000)
    expect(page.locator("#prompt")).to_have_value("Make the cup green.")
    print("PASS Cancel stays reachable over Controls and restores the edit", flush=True)


def check_prompt_aids(page):
    open_workspace(page, "image")
    controls(page)
    page.locator("#templates-toggle").tap()
    count = page.locator("#templates [role=menuitem]").count()
    page.keyboard.press("Escape")
    for index in range(count):
        page.locator("#templates-toggle").tap()
        page.locator("#templates [role=menuitem]").nth(index).tap()
        pane(page, "controls")
        expect(page.locator("#prompt")).not_to_have_value("")
    open_style_section(page)
    expect(page.locator("#look")).to_have_js_property("open", True)
    picks = 0
    rows = page.locator("#look-rows .look-row")
    for row_index in range(rows.count()):
        row = rows.nth(row_index)
        expect(row.locator(".look-row-toggle")).to_have_attribute("aria-haspopup", "menu")
        trigger = row.locator(".look-row-toggle")
        assert trigger.evaluate("button => getComputedStyle(button).webkitTapHighlightColor === 'rgba(0, 0, 0, 0)'")
        menu = page.locator("#" + trigger.get_attribute("aria-controls"))
        count = menu.locator("[role=menuitemradio]").count()
        for option_index in range(1, count):
            trigger.tap()
            option = menu.locator("[role=menuitemradio]").nth(option_index)
            label = option.inner_text()
            option.tap()
            expect(row.locator(".look-row-toggle")).to_contain_text(label)
            picks += 1
    print("PASS focused prompt keeps the next tap, all", count, "templates and", picks, "Look options", flush=True)


def check_media_runs(page):
    for workspace, field, button, text in (
        ("video", "#video-prompt", "#video-generate", "A cup turns slowly."),
        ("voice", "#voice-text", "#voice-generate", "A short phone preview."),
        ("music", "#music-style", "#music-generate", "Warm piano, instrumental"),
    ):
        open_workspace(page, workspace)
        for attempt in range(2):
            controls(page)
            page.locator(field).fill(text + str(attempt))
            page.locator(button).tap()
            pane(page, "preview")
            page.wait_for_function("!sharedOperation && !sharedBusy()", timeout=30000)
            result = {"video": ".video-preview-stub", "voice": "audio-preview", "music": ".music-song"}[workspace]
            expect(page.locator(result).first).to_be_visible(timeout=15000)
        print("PASS", workspace, "Generate opens Preview and shows the completed result", flush=True)
        check_preview_tools(page)
        root = page.locator("#" + workspace + "-studio")
        property_name = "selectedClipId" if workspace == "video" else "selectedId"
        current = root.evaluate("(studio, name) => studio[name]", property_name)
        surface = {"video": ".video-preview-area", "voice": ".voice-preview-area", "music": ".music-preview-area"}[
            workspace
        ]
        box = page.locator(surface).bounding_box()
        dismiss = page.locator("#toasts").get_by_role("button", name="Dismiss", exact=True)
        while dismiss.count():
            dismiss.first.tap()
        center = (box["x"] + box["width"] * 0.7, box["y"] + box["height"] * 0.15)
        swipe(page, -1, center)
        expect(root).not_to_have_js_property(property_name, current)
        swipe(page, 1, center)
        expect(root).to_have_js_property(property_name, current)
        print("PASS", workspace, "real touch swipes select the adjacent gallery items", flush=True)


def check_layout(page):
    for width, height in ((280, 653), (344, 882), (390, 844), (717, 748), (884, 1104), (844, 390)):
        page.set_viewport_size({"width": width, "height": height})
        if width < 600:
            controls(page)
        else:
            expect(page.locator(".pane-switch")).to_be_hidden()
            expect(page.locator("#form")).to_be_visible()
            expect(page.locator("#music-studio")).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (width, "horizontal overflow")
        reachable(page.locator("#music-generate"))
        expect(page.locator("#workspace-toggle")).to_be_visible()
        for button in page.locator(".pane-switch button:visible, #workspace-toggle").all():
            bounds = button.bounding_box()
            assert bounds and bounds["height"] >= 44 and bounds["x"] >= 0 and bounds["x"] + bounds["width"] <= width
        assert page.locator("#music-style").evaluate("element => parseFloat(getComputedStyle(element).fontSize) >= 16")
    page.set_viewport_size({"width": 1440, "height": 1000})
    expect(page.locator(".pane-switch")).to_be_hidden()
    expect(page.locator("#workspace-toggle")).to_be_hidden()
    expect(page.locator("#workspace-tabs")).to_be_visible()
    expect(page.locator("#form")).to_be_visible()
    expect(page.locator("#music-studio")).to_be_visible()
    assert page.locator("#form").bounding_box()["x"] >= 1000
    expect(page.locator("#music-studio .about").first).to_be_visible()
    expect(page.locator("#music-studio .preview-details-toggle").first).to_be_hidden()
    page.set_viewport_size({"width": 344, "height": 882})
    pane(page, "controls")
    page.locator("#music-style").fill("Keep this draft across a fold.")
    page.set_viewport_size({"width": 884, "height": 1104})
    pane(page, "preview")
    expect(page.locator("#form")).to_be_visible()
    expect(page.locator("#music-studio")).to_be_visible()
    page.set_viewport_size({"width": 1440, "height": 1000})
    page.set_viewport_size({"width": 344, "height": 882})
    pane(page, "controls")
    expect(page.locator("#music-style")).to_have_value("Keep this draft across a fold.")
    page.locator('.pane-switch [data-pane="gallery"]').tap()
    sort = page.locator(".pane-gallery-shelf select")
    sort.tap()
    picker = page.locator(".mobile-menu-dialog[open]")
    expect(picker).to_be_visible()
    picker.get_by_role("menuitemradio", name="Oldest first").tap()
    expect(picker).to_have_count(0)
    expect(sort).to_have_value("oldest")
    sort.tap()
    sort.evaluate("element => { element.disabled = true; }")
    page.locator(".mobile-menu-dialog").get_by_role("menuitemradio", name="Newest first").tap()
    expect(sort).to_have_value("oldest")
    sort.evaluate("element => { element.disabled = false; }")
    print(
        "PASS cover screen, two-column inner screen, fold transitions, landscape, full-screen selects and desktop layout",
        flush=True,
    )


def check_rejected_starts(page):
    for workspace, endpoint, field, button in (
        ("image", "/generate", "#prompt", "#go"),
        ("video", "/video/generate", "#video-prompt", "#video-generate"),
        ("voice", "/voice/operations", "#voice-text", "#voice-generate"),
        ("music", "/music/operations", "#music-style", "#music-generate"),
    ):
        open_workspace(page, workspace)
        controls(page)
        if workspace == "image":
            page.locator('label[for="mode-generate"]').tap()
        page.locator(field).fill("Retain this input after a rejected request.")
        page.route("**" + endpoint, lambda route: route.fulfill(status=400, json={"error": "Rejected request."}))
        page.locator(button).tap()
        expect(page.locator(button)).to_be_enabled(timeout=15000)
        pane(page, "controls")
        expect(page.locator(field)).to_have_value("Retain this input after a rejected request.")
        page.unroute("**" + endpoint)
        print("PASS", workspace, "a rejected start keeps its inputs in Controls", flush=True)


def check_picker_locks(page):
    other = page.context.new_page()
    other.goto(BASE + "/?workspace=image")
    controls(other)
    other.locator('label[for="mode-generate"]').tap()
    set_steps(other, 40)
    for target in ("#workspace-toggle", ".pane-gallery-shelf select"):
        page.locator(target).tap()
        expect(page.locator(".mobile-menu-dialog[open]")).to_be_visible()
        other.locator("#prompt").fill("A public stub run from another tab.")
        other.locator("#go").tap()
        expect(page.locator("#workspace-toggle")).to_be_disabled(timeout=15000)
        expect(page.locator(".mobile-menu-dialog")).to_have_count(0)
        other.locator("#shared-operation-cancel").tap()
        other.wait_for_function("!busy() && !sharedOperation", timeout=15000)
        expect(page.locator("#workspace-toggle")).to_be_enabled(timeout=15000)
    other.close()
    print("PASS another tab's run closes workspace and select pickers", flush=True)


def luminance(color):
    channels = [int(channel) / 255 for channel in re.findall(r"\d+", color)[:3]]
    linear = [channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4 for channel in channels]
    return sum(channel * weight for channel, weight in zip(linear, (0.2126, 0.7152, 0.0722), strict=True))


def check_contrast(workspace, theme, pairs):
    for colors in pairs:
        low, high = sorted(luminance(color) for color in colors)
        ratio = (high + 0.05) / (low + 0.05)
        assert ratio >= 4.5, (workspace, theme, colors, ratio)


def check_galleries(page):
    for workspace in ("image", "video", "voice", "music"):
        open_workspace(page, workspace)
        page.locator('.pane-switch [data-pane="gallery"]').tap()
        for theme in ("", "leica", "kodak", "polaroid", "blueprint", "cel", "broadcast", "risograph"):
            open_settings(page, "appearance")
            page.locator(f'#settings-dialog [data-theme="{theme}"]').tap()
            page.keyboard.press("Escape")
            expect(page.locator("#theme-toggle")).to_have_attribute("aria-expanded", "false")
            pairs = page.locator(".pane-gallery-shelf").evaluate("""shelf => {
                const copy = shelf.querySelector('.gallery-card-text, .gallery-no-results');
                const search = shelf.querySelector('input[type=search]');
                const number = shelf.querySelector('.gallery-card .no');
                const pairs = [[getComputedStyle(copy).color, getComputedStyle(shelf).backgroundColor],
                  [getComputedStyle(search, '::placeholder').color, getComputedStyle(search).backgroundColor]];
                if (number) pairs.push([getComputedStyle(number).color, getComputedStyle(number.closest('.gallery-card')).backgroundColor]);
                return pairs;
            }""")
            check_contrast(workspace, theme, pairs)
        print("PASS", workspace, "gallery text contrast in all eight themes", flush=True)


with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    check_shortcuts(page)
    check_prompt_aids(page)
    check_image(page)
    check_media_runs(page)
    check_rejected_starts(page)
    check_galleries(page)
    check_layout(page)
    check_picker_locks(page)
    assert not errors, errors
    browser.close()
print("PASS mobile workflows", flush=True)
