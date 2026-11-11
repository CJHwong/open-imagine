"""Check shared result actions and mobile Music spacing on a fresh all-backend stub."""

import json
import re
import sys

from playwright.sync_api import expect, sync_playwright
from style_controls import show_controls
from verify_image_inline_zoom import seed_edit

WORKSPACES = (
    ("image", "#prompt", "#go", "#stage-bar .actions"),
    ("video", "#video-prompt", "#video-generate", "#video-output-details .actions"),
    ("voice", "#voice-text", "#voice-generate", "#voice-output-details .actions"),
    ("music", "#music-style", "#music-generate", "#music-studio .music-output-details .actions"),
)


def record(failures, condition, case, detail):
    if condition:
        return
    failures.append({"case": case, "detail": detail})
    print("FAIL", json.dumps(failures[-1]), flush=True)


def check_case(browser, base, workspace, field, generate, selector, width, locale, failures):
    context = browser.new_context(
        viewport={"width": width, "height": 882}, has_touch=width <= 900, is_mobile=width <= 900
    )
    context.add_init_script(
        "localStorage.setItem('studio-keep','off');localStorage.setItem('studio-autoplay','off');localStorage.setItem('studio-compare','on')"
    )
    page = context.new_page()
    page.goto(base + f"/?workspace={workspace}&lang={locale}")
    if workspace == "image":
        seed_edit(page, (768, 512))
    else:
        show_controls(page)
        expect(page.locator(field)).to_be_visible()
        page.locator(field).fill("A calm preview for action layout.")
        page.locator(generate).click()
    actions = page.locator(selector + ":visible").first
    expect(actions).to_be_visible(timeout=30000)
    page.wait_for_function("!busy() && !sharedOperation && !sharedBusy()", timeout=30000)
    case = f"{workspace}/{locale}/{width}"
    record(
        failures,
        actions.evaluate("row => row.classList.contains('preview-actions')"),
        case + "/shared-row-contract",
        actions.get_attribute("class"),
    )
    controls = actions.locator("button:visible,a:visible").all()
    boxes = []
    glyph_rows = []
    caption_rows = []
    for control in controls:
        label = control.locator(".control-label")
        icon = control.locator("svg.icon")
        valid = label.count() == 1 and label.is_visible() and bool(label.inner_text().strip()) and icon.count() == 1
        record(failures, valid, case + "/icon-with-visible-caption", control.get_attribute("aria-label"))
        if valid:
            text, glyph = label.bounding_box(), icon.bounding_box()
            button = control.bounding_box()
            glyph_rows.append(glyph["y"])
            caption_rows.append(text["y"])
            record(
                failures,
                text["x"] >= button["x"] - 1
                and text["x"] + text["width"] <= button["x"] + button["width"] + 1
                and text["y"] + text["height"] <= button["y"] + button["height"] + 1,
                case + "/caption-inside-button",
                {"label": text, "button": button},
            )
            record(
                failures,
                text["y"] >= glyph["y"] + glyph["height"] - 1,
                case + "/caption-below-icon",
                {"icon": glyph, "label": text},
            )
            record(
                failures,
                abs(text["x"] + text["width"] / 2 - glyph["x"] - glyph["width"] / 2) <= 2,
                case + "/caption-centered",
                {"icon": glyph, "label": text},
            )
        boxes.append(control.bounding_box())
    record(
        failures,
        max(box["y"] for box in boxes) - min(box["y"] for box in boxes) <= 1,
        case + "/single-aligned-row",
        boxes,
    )
    record(
        failures,
        max(box["height"] for box in boxes) - min(box["height"] for box in boxes) <= 1,
        case + "/consistent-action-height",
        boxes,
    )
    if glyph_rows:
        record(
            failures,
            max(glyph_rows) - min(glyph_rows) <= 1 and max(caption_rows) - min(caption_rows) <= 1,
            case + "/aligned-icons-and-captions",
            {"icons": glyph_rows, "captions": caption_rows},
        )
    edge = actions.bounding_box()
    record(
        failures,
        abs(max(box["x"] + box["width"] for box in boxes) - edge["x"] - edge["width"]) <= 1,
        case + "/actions-right-aligned",
        boxes,
    )
    record(
        failures,
        actions.get_by_role("button", name=re.compile(r"full.?screen|全螢幕", re.I)).count() == 0,
        case + "/no-fullscreen-action",
        "result row",
    )
    controls[0].focus()
    page.keyboard.press("f")
    page.wait_for_timeout(100)
    record(
        failures, not page.evaluate("Boolean(document.fullscreenElement)"), case + "/f-keeps-studio-in-page", workspace
    )
    for rule in actions.locator(".rule:visible").all():
        divider = rule.bounding_box()
        center = (min(box["y"] for box in boxes) + max(box["y"] + box["height"] for box in boxes)) / 2
        record(
            failures,
            abs(divider["y"] + divider["height"] / 2 - center) <= 1,
            case + "/separator-centered-on-action",
            divider,
        )
    if workspace == "music" and width <= 900:
        art = page.locator(".music-song:not([hidden]) .music-artwork")
        expect(art).to_be_visible()
        header = page.locator(".topbar").bounding_box()
        gap = art.bounding_box()["y"] - header["y"] - header["height"]
        record(failures, gap >= 24, case + "/music-mobile-top-space", gap)
    record(
        failures,
        all(box["x"] >= 0 and box["x"] + box["width"] <= width for box in boxes),
        case + "/actions-fit-window",
        boxes,
    )
    if "--screenshots" in sys.argv and locale == "en" and width == 390:
        page.screenshot(path=f"/tmp/image-gen-preview-{workspace}-390.png")
    print("CHECK", case, flush=True)
    context.close()


def main():
    failures = []
    core = "--core" in sys.argv
    with sync_playwright() as playwright:
        browser = (playwright.webkit if "--webkit" in sys.argv else playwright.chromium).launch()
        for workspace, field, generate, selector in WORKSPACES:
            if core and workspace not in ("image", "music"):
                continue
            for locale in ("en",) if core else ("en", "zh-TW"):
                for width in (280, 390) if core else (280, 390, 768, 1440):
                    check_case(
                        browser,
                        f"http://127.0.0.1:{int(sys.argv[1])}",
                        workspace,
                        field,
                        generate,
                        selector,
                        width,
                        locale,
                        failures,
                    )
        browser.close()
    print("FAILURES", len(failures), flush=True)
    return bool(failures)


if __name__ == "__main__":
    sys.exit(main())
