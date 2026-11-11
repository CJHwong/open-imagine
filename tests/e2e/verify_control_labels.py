"""Check control labels with large fonts and preserve selection of user text.

Run against a fresh all-backend stub:
uv run --with playwright python tests/e2e/verify_control_labels.py <port>
Chromium and WebKit do not prove behavior in Samsung Internet.
"""

import json
import sys

from playwright.sync_api import expect, sync_playwright
from style_controls import show_controls

WIDTHS = (280, 320, 390, 1024, 1440)


def record(failures, condition, case, detail):
    if not condition:
        failures.append({"case": case, "detail": detail})


def open_workspace(page, base, workspace):
    page.goto(base + "/?workspace=" + workspace)
    expect(page.locator("body")).to_have_attribute("data-media", workspace)
    show_controls(page)


def check_geometry(page, case, failures):
    page.locator("#video-advanced > summary").click()
    expect(page.locator("#video-fast-mode")).to_be_visible()
    expect(page.locator("#video-audio-track")).to_be_visible()
    for font in (None, 18, 24):
        override = page.add_style_tag(
            content=(
                "#video-controls button {font-size: " + str(font) + "px !important}" if font else "/* Native font. */"
            )
        )
        result = page.evaluate("""() => {
            const box = selector => document.querySelector(selector).getBoundingClientRect();
            const fast = box('#video-fast-mode'), audio = box('#video-audio-track');
            const groups = [...document.querySelectorAll('.video-ratios, #video-resolutions')];
            return {widths: [fast.width, audio.width], groups: groups.map(group => ({
                name: group.id || group.className,
                overflow: group.scrollWidth - group.clientWidth,
                labels: [...group.querySelectorAll('button')].map(button => {
                    const border = button.getBoundingClientRect();
                    const walker = document.createTreeWalker(button, NodeFilter.SHOW_TEXT);
                    const ranges = [];
                    while (walker.nextNode()) {
                        if (!walker.currentNode.textContent.trim()) continue;
                        const range = document.createRange();
                        range.selectNodeContents(walker.currentNode);
                        ranges.push(...[...range.getClientRects()].map(rect => ({
                            left: rect.left - border.left, right: border.right - rect.right,
                            top: rect.top - border.top, bottom: border.bottom - rect.bottom
                        })));
                    }
                    return {label: button.textContent.trim(), ranges};
                })
            }))};
        }""")
        sample = case + "/font=" + str(font or "normal")
        record(failures, abs(result["widths"][0] - result["widths"][1]) <= 1, sample + "/pill-width", result["widths"])
        for group in result["groups"]:
            record(failures, group["overflow"] <= 1, sample + "/group-overflow", group)
            for label in group["labels"]:
                fits = bool(label["ranges"]) and all(min(bounds.values()) >= 0.5 for bounds in label["ranges"])
                record(failures, fits, sample + "/label-bounds/" + group["name"], label)
        override.evaluate("element => element.remove()")


def selection_policy(locator):
    return locator.evaluate("""element => {
        for (let ancestor = element; ancestor; ancestor = ancestor.parentElement) {
            const style = getComputedStyle(ancestor);
            const policy = style.getPropertyValue('-webkit-user-select') || style.userSelect;
            if (policy && policy !== 'auto') return policy;
        }
        return 'auto';
    }""")


def drag_selection(page, locator):
    locator.scroll_into_view_if_needed()
    bounds = locator.evaluate("""element => {
        const range = document.createRange();
        range.selectNodeContents(element);
        const rect = [...range.getClientRects()].find(rect => rect.width > 4);
        return rect ? {x: rect.x, y: rect.y, width: rect.width, height: rect.height} : null;
    }""")
    assert bounds
    page.evaluate("getSelection().removeAllRanges()")
    vertical = bounds["y"] + bounds["height"] / 2
    page.mouse.move(bounds["x"] + 1, vertical)
    page.mouse.down()
    page.mouse.move(bounds["x"] + bounds["width"] - 1, vertical, steps=12)
    selected = page.evaluate("getSelection().toString()")
    page.mouse.up()
    page.keyboard.press("Escape")
    return selected


def check_control_text(page, locator, case, failures):
    policy = selection_policy(locator)
    record(failures, policy == "none", case + "/selection-policy", policy)
    selected = drag_selection(page, locator)
    record(failures, not selected.strip(), case + "/mouse-drag-selection", selected)


def check_look(page, case, failures, prefix):
    panel = page.locator(prefix)
    panel.locator("summary").click()
    trigger = panel.locator(".look-row-toggle").first
    check_control_text(page, trigger.locator(".label"), case + "/look-trigger", failures)
    if trigger.get_attribute("aria-expanded") == "true":
        page.keyboard.press("Escape")
    trigger.click()
    menu = page.locator("#" + trigger.get_attribute("aria-controls"))
    check_control_text(page, menu.locator(".item-text").nth(1), case + "/look-option", failures)
    note = panel.locator(".look-note")
    record(failures, selection_policy(note) != "none", case + "/paragraph-policy", selection_policy(note))
    selected = drag_selection(page, note)
    record(failures, bool(selected.strip()), case + "/paragraph-drag", selected)


def check_textarea(page, case, failures):
    field = page.locator("#video-prompt")
    field.fill("Keep this prompt selectable.")
    field.focus()
    page.keyboard.press("ControlOrMeta+A")
    selected = field.evaluate("field => field.value.slice(field.selectionStart, field.selectionEnd)")
    record(failures, selected == field.input_value(), case + "/textarea-selection", selected)
    record(failures, selection_policy(field) != "none", case + "/textarea-policy", selection_policy(field))
    field.press("Tab")


def check_metadata(page, case, failures):
    page.locator("#video-generate").click()
    expect(page.locator("#video-studio .video-preview-stub")).to_be_visible(timeout=20000)
    page.wait_for_function("!sharedOperation && !sharedBusy()")
    toggle = page.locator("#video-studio .preview-details-toggle")
    if toggle.is_visible():
        toggle.click()
        detail = page.locator("#result-details-sheet dd").filter(has_text="Keep this prompt selectable.")
    else:
        detail = page.locator("#video-studio .video-output-prompt")
    expect(detail).to_be_visible()
    record(failures, selection_policy(detail) != "none", case + "/metadata-policy", selection_policy(detail))
    selected = drag_selection(page, detail)
    record(failures, bool(selected.strip()), case + "/metadata-drag", selected)


def check_case(browser, engine_name, locale, width, base, failures):
    context = browser.new_context(
        viewport={"width": width, "height": 1000},
        locale=locale,
        has_touch=width < 900,
        is_mobile=width < 900,
    )
    context.add_init_script("localStorage.setItem('studio-keep', 'off')")
    page = context.new_page()
    case = engine_name + "/" + locale + "/" + str(width)
    open_workspace(page, base, "video")
    expect(page.locator("html")).to_have_attribute("data-locale", locale)
    check_geometry(page, case, failures)
    check_textarea(page, case, failures)
    check_look(page, case + "/video", failures, "#video-look")
    check_metadata(page, case, failures)
    open_workspace(page, base, "image")
    check_look(page, case + "/image", failures, "#look")
    open_workspace(page, base, "music")
    page.locator("#music-style-presets > summary").click()
    trigger = page.locator("#music-genre-toggle")
    check_control_text(page, trigger.locator(".label"), case + "/genre-trigger", failures)
    if trigger.get_attribute("aria-expanded") == "true":
        page.keyboard.press("Escape")
    trigger.click()
    menu = page.locator("#music-genre-menu")
    check_control_text(page, menu.locator(".item-text").nth(1), case + "/genre-option", failures)
    context.close()
    print("CHECK", case, flush=True)


def main():
    failures = []
    base = "http://127.0.0.1:" + sys.argv[1]
    with sync_playwright() as playwright:
        for engine_name in ("chromium", "webkit"):
            browser = getattr(playwright, engine_name).launch()
            for locale in ("en", "zh-TW"):
                for width in WIDTHS:
                    check_case(browser, engine_name, locale, width, base, failures)
            browser.close()
    for failure in failures:
        print("FAIL", json.dumps(failure, ensure_ascii=False), flush=True)
    print("FAILURES", len(failures), flush=True)
    raise SystemExit(bool(failures))


if __name__ == "__main__":
    main()
