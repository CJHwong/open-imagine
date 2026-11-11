"""Check simultaneous preview and controls across fold and resize transitions.

Run against a fresh all-backend stub:
uv run --with playwright python tests/e2e/verify_fold_layout.py <port>
Widths exercise layout behavior, not a claimed device viewport.
"""

import json
import sys

from playwright.sync_api import expect, sync_playwright

WORKSPACES = (
    ("image", "#prompt", "#go", "#image-stage", ".pic img"),
    ("video", "#video-prompt", "#video-generate", "#video-studio", ".video-preview-stub"),
    ("voice", "#voice-text", "#voice-generate", "#voice-studio", "audio-preview"),
    ("music", "#music-style", "#music-generate", "#music-studio", ".music-song"),
)
SIZES = (
    (344, 882),
    (599, 748),
    (600, 748),
    (690, 748),
    (717, 748),
    (768, 748),
    (884, 1104),
    (884, 690),
    (768, 440),
    (768, 748),
    (1024, 900),
    (884, 1104),
    (690, 748),
    (600, 748),
    (599, 748),
    (344, 882),
)


def record(failures, condition, case, detail):
    if condition:
        return
    failure = {"case": case, "detail": detail}
    failures.append(failure)
    print("FAIL", json.dumps(failure), flush=True)


def selected_result(page, workspace):
    if workspace == "image":
        return page.locator(".pic img").first.get_attribute("alt")
    property_name = "selectedClipId" if workspace == "video" else "selectedId"
    return page.locator("#" + workspace + "-studio").evaluate("(studio, name) => studio[name]", property_name)


def seed_result(page, workspace, field, generate, result):
    page.locator('.pane-switch [data-pane="controls"]').tap()
    if workspace == "image":
        page.locator("#advanced > summary").tap()
        page.locator("#steps").fill("1")
        page.locator("#advanced > summary").tap()
    page.locator(field).fill("A short fold layout preview.")
    page.locator(generate).tap()
    expect(page.locator(result).first).to_be_visible(timeout=20000)
    page.wait_for_function("!busy() && !sharedOperation && !sharedBusy()", timeout=30000)
    page.locator('.pane-switch [data-pane="controls"]').tap()


def check_picker(page, width, height, case, failures):
    picker = page.locator(".mobile-menu-dialog[open]")
    expect(picker).to_be_visible()
    bounds = picker.bounding_box()
    if width < 600:
        fits = abs(bounds["x"]) <= 1 and abs(bounds["y"]) <= 1
        fits = fits and abs(bounds["width"] - width) <= 1 and abs(bounds["height"] - height) <= 1
        record(failures, fits, case + "/cover-full-screen", bounds)
    else:
        centered = abs(bounds["x"] * 2 + bounds["width"] - width) <= 2
        centered = centered and abs(bounds["y"] * 2 + bounds["height"] - height) <= 2
        record(failures, centered, case + "/picker-centered", bounds)
        margins = bounds["x"] >= 20 and bounds["y"] >= 20
        margins = margins and bounds["x"] + bounds["width"] <= width - 20
        margins = margins and bounds["y"] + bounds["height"] <= height - 20
        record(failures, margins, case + "/picker-margins", bounds)
        record(failures, bounds["width"] >= min(420, width - 80), case + "/picker-readable-width", bounds)
        spacing = picker.evaluate("""dialog => {
            const menu = dialog.querySelector('.menu');
            if (menu.scrollHeight > menu.clientHeight + 1) return null;
            const last = [...menu.children].filter(child => child.getClientRects().length).at(-1);
            if (!last) return null;
            return {
                blank: dialog.getBoundingClientRect().bottom - last.getBoundingClientRect().bottom,
                allowed: parseFloat(getComputedStyle(menu).paddingBottom)
                    + parseFloat(getComputedStyle(dialog).borderBottomWidth) + 2
            };
        }""")
        if spacing:
            record(failures, spacing["blank"] <= spacing["allowed"], case + "/short-menu-blank-space", spacing)
    close = picker.locator("header button").bounding_box()
    reachable = close["width"] >= 44 and close["height"] >= 44
    reachable = (
        reachable and close["y"] >= bounds["y"] and close["y"] + close["height"] <= bounds["y"] + bounds["height"]
    )
    record(failures, reachable, case + "/picker-close", close)
    targets = picker.locator(".menu button").evaluate_all(
        "buttons => buttons.every(button => button.getBoundingClientRect().height >= 44)"
    )
    record(failures, targets, case + "/picker-touch-targets", "menu choices remain at least 44px high")
    return picker


def sample_layout(page, workspace, stage, generate, width, height, failures):
    case = workspace + "/" + str(width) + "x" + str(height)
    page.set_viewport_size({"width": width, "height": height})
    page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
    compact = width < 600
    record(failures, page.locator(".pane-switch").is_visible() == compact, case + "/pane-dock", compact)
    record(failures, page.locator("#form").is_visible(), case + "/controls", "controls must remain visible")
    record(
        failures,
        page.locator(stage).is_visible() != compact,
        case + "/preview",
        "preview beside controls at width >=600",
    )
    record(
        failures, page.locator("#workspace-toggle").is_visible() == (width <= 900), case + "/workspace-picker", width
    )
    record(failures, page.locator("#workspace-tabs").is_visible() == (width > 900), case + "/workspace-tabs", width)
    record(failures, page.evaluate("document.documentElement.scrollWidth <= innerWidth"), case + "/overflow", width)
    if not compact and page.locator(stage).is_visible() and page.locator("#form").is_visible():
        preview = page.locator(".work").bounding_box()
        controls = page.locator("#form").bounding_box()
        column = page.locator("aside").bounding_box()
        fits = preview["x"] + preview["width"] <= controls["x"] + 1
        fits = fits and controls["x"] + controls["width"] <= width + 1
        record(failures, fits, case + "/columns", {"preview": preview, "controls": controls})
        record(
            failures,
            preview["width"] >= 280 and column["width"] >= 280 and controls["width"] >= column["width"] - 1,
            case + "/usable-widths",
            [preview["width"], column["width"], controls["width"]],
        )
        for action in page.locator(stage + " .stage-bar :is(button, a):visible").all():
            bounds = action.bounding_box()
            inside = (
                bounds["x"] >= preview["x"] and bounds["x"] + bounds["width"] <= preview["x"] + preview["width"] + 1
            )
            record(failures, inside, case + "/preview-action", bounds)
    button = page.locator(generate).bounding_box()
    record(
        failures,
        button and button["y"] >= 0 and button["y"] + button["height"] <= height,
        case + "/generate-reachable",
        button,
    )
    if 600 <= width <= 900:
        toggle = page.locator("#workspace-toggle")
        toggle.tap()
        picker = check_picker(page, width, height, case, failures)
        picker.locator("header button").tap()
        expect(toggle).to_be_focused()


def check_workspace(browser, base, spec, failures):
    workspace, field, generate, stage, result = spec
    context = browser.new_context(viewport={"width": 344, "height": 882}, is_mobile=True, has_touch=True)
    context.add_init_script("localStorage.setItem('studio-keep', 'off')")
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(base + "/?workspace=" + workspace)
    expect(page.locator("body")).to_have_attribute("data-media", workspace)
    seed_result(page, workspace, field, generate, result)
    chosen = selected_result(page, workspace)
    draft = "Keep this " + workspace + " draft across a fold."
    page.locator(field).fill(draft)
    page.locator(field).press("Tab")
    for width, height in SIZES:
        sample_layout(page, workspace, stage, generate, width, height, failures)
        record(failures, page.locator(field).input_value() == draft, workspace + "/draft", [width, height])
        record(failures, selected_result(page, workspace) == chosen, workspace + "/selection", [width, height])
    expect(page.locator("body")).to_have_attribute("data-pane", "controls")
    page.locator('.pane-switch [data-pane="gallery"]').tap()
    page.set_viewport_size({"width": 768, "height": 748})
    page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
    record(
        failures,
        not page.locator(".pane-gallery-shelf").count(),
        workspace + "/gallery-unfold",
        "restore the shelf before two-column layout",
    )
    record(
        failures,
        page.locator(stage).is_visible() and page.locator("#form").is_visible(),
        workspace + "/gallery-unfold-panels",
        "preview and controls must coexist",
    )
    page.set_viewport_size({"width": 344, "height": 882})
    expect(page.locator("body")).to_have_attribute("data-pane", "gallery")
    record(failures, not errors, workspace + "/page-errors", errors)
    context.close()
    print("CHECK", workspace, "fold transitions and preserved draft/result", flush=True)


def check_long_picker(browser, base, failures):
    context = browser.new_context(viewport={"width": 344, "height": 882}, is_mobile=True, has_touch=True)
    context.add_init_script("localStorage.setItem('studio-keep', 'off')")
    page = context.new_page()
    page.goto(base + "/?workspace=music")
    page.locator('.pane-switch [data-pane="controls"]').tap()
    style = page.locator("#music-style")
    draft = "pop, Keep a foldable picker draft."
    style.fill(draft)
    trigger = page.locator("#music-genre-toggle")
    trigger.tap()
    for width, height in ((344, 882), (768, 748), (768, 440), (344, 882)):
        page.set_viewport_size({"width": width, "height": height})
        case = "genre/" + str(width) + "x" + str(height)
        picker = check_picker(page, width, height, case, failures)
        expect(picker.locator('[aria-checked="true"] .item-text')).to_have_text("Pop")
        expect(style).to_have_value(draft)
    page.keyboard.press("Escape")
    expect(trigger).to_be_focused()
    page.set_viewport_size({"width": 768, "height": 440})
    trigger.tap()
    picker = check_picker(page, 768, 440, "genre/short-height", failures)
    menu = picker.locator(".menu")
    record(
        failures,
        menu.evaluate("menu => menu.scrollHeight > menu.clientHeight"),
        "genre/scroll",
        "long choices scroll inside the picker",
    )
    choice = menu.locator('[data-music-genre]:not([data-music-genre=""])').last
    label = choice.locator(".item-text").inner_text()
    choice.scroll_into_view_if_needed()
    bounds, viewport = choice.bounding_box(), menu.bounding_box()
    inside = bounds["y"] >= viewport["y"] and bounds["y"] + bounds["height"] <= viewport["y"] + viewport["height"] + 1
    record(failures, inside, "genre/last-choice-visible", {"choice": bounds, "menu": viewport})
    choice.tap()
    expect(trigger.locator(".look-pick")).to_have_text(label)
    assert "Keep a foldable picker draft." in style.input_value()
    expect(trigger).to_be_focused()
    page.set_viewport_size({"width": 768, "height": 748})
    page.locator(".music-advanced-fields > summary").tap()
    native = page.locator("#music-count")
    native.tap()
    picker = check_picker(page, 768, 748, "native-select", failures)
    picker.get_by_role("menuitemradio", name="2", exact=True).tap()
    expect(native).to_have_value("2")
    expect(native).to_be_focused()
    page.set_viewport_size({"width": 1024, "height": 900})
    trigger.tap()
    expect(page.locator(".mobile-menu-dialog")).to_have_count(0)
    expect(page.locator("#music-genre-menu")).to_be_visible()
    page.keyboard.press("Escape")
    expect(trigger).to_be_focused()
    page.set_viewport_size({"width": 768, "height": 748})
    trigger.tap()
    page.touchscreen.tap(8, 8)
    page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
    record(
        failures,
        page.locator(".mobile-menu-dialog").count() == 0,
        "genre/outside-dismiss",
        "tap outside the centered picker closes it",
    )
    record(
        failures,
        trigger.evaluate("element => element === document.activeElement"),
        "genre/outside-focus",
        "dismiss returns focus to the trigger",
    )
    if page.locator(".mobile-menu-dialog").count():
        page.keyboard.press("Escape")
    context.close()
    print("CHECK long genre scrolling, native select, open-picker folds and desktop menu", flush=True)


def check_mouse_picker(browser, base, failures):
    context = browser.new_context(viewport={"width": 768, "height": 748})
    context.add_init_script("localStorage.setItem('studio-keep', 'off')")
    page = context.new_page()
    page.goto(base + "/?workspace=music")
    page.locator(".music-advanced-fields > summary").click()
    native = page.locator("#music-count")
    native.click()
    picker = check_picker(page, 768, 748, "native-mouse", failures)
    picker.get_by_role("menuitemradio", name="2", exact=True).click()
    expect(native).to_have_value("2")
    expect(native).to_be_focused()
    native.click()
    check_picker(page, 768, 748, "native-mouse-reopen", failures)
    page.mouse.click(8, 8)
    expect(page.locator(".mobile-menu-dialog")).to_have_count(0)
    expect(native).to_be_focused()
    context.close()
    print("CHECK mouse opens native picker, selects, reopens and dismisses outside", flush=True)


def main():
    failures = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for spec in WORKSPACES:
            check_workspace(browser, "http://127.0.0.1:" + sys.argv[1], spec, failures)
        check_long_picker(browser, "http://127.0.0.1:" + sys.argv[1], failures)
        check_mouse_picker(browser, "http://127.0.0.1:" + sys.argv[1], failures)
        browser.close()
    print("FAILURES", len(failures), flush=True)
    raise SystemExit(bool(failures))


if __name__ == "__main__":
    main()
