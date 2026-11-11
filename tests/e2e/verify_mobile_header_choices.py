"""Check readable model names, workspace alignment, and full-width choice grids.

Run against a fresh all-backend qwen21 stub. No model is loaded.
uv run --with playwright python tests/e2e/verify_mobile_header_choices.py <port> [chromium|webkit]
"""

import json
import sys

from playwright.sync_api import expect, sync_playwright
from style_controls import open_style_section, show_controls

WIDTHS = (280, 344, 600, 690, 884, 1024)


def record(failures, condition, case, detail):
    if not condition:
        failures.append({"case": case, "detail": detail})


def header_geometry(page):
    return page.evaluate("""() => {
        const bounds = selector => document.querySelector(selector).getBoundingClientRect();
        const name = document.querySelector('#backend-toggle .name');
        const clip = name.getBoundingClientRect();
        const range = document.createRange();
        range.selectNodeContents(name);
        const text = range.getBoundingClientRect();
        const workspace = document.querySelector('#workspace-toggle');
        const shown = workspace.getClientRects().length > 0;
        const center = box => ({horizontal: box.left + box.width / 2, vertical: box.top + box.height / 2});
        const workspaceBounds = workspace.getBoundingClientRect();
        const caption = bounds('#workspace-caption'), caret = bounds('.workspace-caret');
        const captionInsets = [caption.left - workspaceBounds.left, workspaceBounds.right - caption.right,
            caption.top - workspaceBounds.top, workspaceBounds.bottom - caption.bottom];
        const separated = caret.right <= caption.left || caret.left >= caption.right
            || caret.bottom <= caption.top || caret.top >= caption.bottom;
        return {
            name: name.textContent, verticalInsets: [text.top - clip.top, clip.bottom - text.bottom],
            workspace: shown ? {
                button: center(bounds('#workspace-toggle')), icon: center(bounds('.workspace-icon')),
                caption: center(bounds('#workspace-caption')), caret: center(bounds('.workspace-caret')),
                rightInset: workspaceBounds.right - caret.right, captionInsets, separated
            } : null
        };
    }""")


def check_header(page, case, failures):
    geometry = header_geometry(page)
    record(failures, min(geometry["verticalInsets"]) >= -0.5, case + "/model-text-height", geometry)
    workspace = geometry["workspace"]
    if not workspace:
        return
    record(
        failures,
        abs(workspace["icon"]["horizontal"] - workspace["caption"]["horizontal"]) <= 1,
        case + "/workspace-icon-caption",
        workspace,
    )
    centered = abs(workspace["caret"]["vertical"] - workspace["button"]["vertical"]) <= 1
    at_right = workspace["caret"]["horizontal"] > workspace["icon"]["horizontal"]
    record(failures, centered and at_right and workspace["rightInset"] >= 1, case + "/workspace-caret", workspace)
    record(
        failures,
        min(workspace["captionInsets"]) >= -0.5 and workspace["separated"],
        case + "/workspace-caption-bounds",
        workspace,
    )


def choice_geometry(group):
    return group.evaluate("""group => {
        const outer = group.getBoundingClientRect(), style = getComputedStyle(group);
        const start = outer.left + parseFloat(style.borderLeftWidth) + parseFloat(style.paddingLeft);
        const end = outer.right - parseFloat(style.borderRightWidth) - parseFloat(style.paddingRight);
        const rows = [];
        const buttons = [...group.querySelectorAll(':scope > button')].filter(button => button.getClientRects().length);
        const labels = buttons.map(button => {
            const box = button.getBoundingClientRect();
            let row = rows.find(row => Math.abs(row.top - box.top) <= 1);
            if (!row) { row = {top: box.top, left: box.left, right: box.right}; rows.push(row); }
            row.left = Math.min(row.left, box.left); row.right = Math.max(row.right, box.right);
            const walker = document.createTreeWalker(button, NodeFilter.SHOW_TEXT);
            const textBounds = [];
            while (walker.nextNode()) {
                if (!walker.currentNode.textContent.trim()) continue;
                const range = document.createRange(); range.selectNodeContents(walker.currentNode);
                textBounds.push(...[...range.getClientRects()].map(rect => ({
                    left: rect.left - box.left, right: box.right - rect.right,
                    top: rect.top - box.top, bottom: box.bottom - rect.bottom
                })));
            }
            return {text: button.textContent.trim(), width: box.width, height: box.height, textBounds};
        });
        return {start, end, rows, labels, overflow: group.scrollWidth - group.clientWidth};
    }""")


def check_group(page, selector, case, failures):
    group = page.locator(selector)
    if not group.is_visible() or not group.locator(":scope > button").count():
        return
    geometry = choice_geometry(group)
    record(failures, geometry["overflow"] <= 1, case + selector + "/overflow", geometry)
    widths = [label["width"] for label in geometry["labels"]]
    record(failures, max(widths) - min(widths) <= 1, case + selector + "/equal-width", geometry)
    first = geometry["rows"][0]
    full = abs(first["left"] - geometry["start"]) <= 1 and abs(first["right"] - geometry["end"]) <= 1
    record(failures, full, case + selector + "/full-first-row", geometry)
    for index, row in enumerate(geometry["rows"]):
        aligned = abs(row["left"] - geometry["start"]) <= 1
        record(failures, aligned, case + selector + "/row=" + str(index), geometry)
    for label in geometry["labels"]:
        fits = label["textBounds"] and all(min(bounds.values()) >= -0.5 for bounds in label["textBounds"])
        record(failures, fits, case + selector + "/label=" + label["text"], label)


def check_workspace(page, base, workspace, width, locale, failures):
    page.goto(base + "/?workspace=" + workspace)
    expect(page.locator("body")).to_have_attribute("data-media", workspace)
    show_controls(page)
    look = page.locator("#look" if workspace == "image" else "#video-look")
    record(failures, look.evaluate("section => section.open"), workspace + "/default-look", "Look starts closed")
    look.locator(":scope > summary").click()
    record(failures, not look.evaluate("section => section.open"), workspace + "/collapse-look", "Look stays open")
    open_style_section(page, "#look" if workspace == "image" else "#video-look")
    open_style_section(page, "#look" if workspace == "image" else "#video-look")
    if workspace == "image":
        record(
            failures,
            page.locator("#count-toggle").inner_text().strip() == page.locator("#count-shown").inner_text().strip(),
            workspace + "/count-caption",
            page.locator("#count-toggle").inner_text(),
        )
    for font in (None, 18, 24):
        case = workspace + "/" + locale + "/" + str(width) + "/font=" + str(font or "normal")
        override = page.add_style_tag(
            content=(
                ".topbar h1, #workspace-caption, #size-chips, #tier-sizes, #edit-sizes, "
                ".video-ratios, #video-resolutions, #size-chips button, #tier-sizes button, #edit-sizes button, "
                ".video-ratios button, #video-resolutions button {font-size: " + str(font) + "px !important}"
                if font
                else "/* Native font. */"
            )
        )
        check_header(page, case, failures)
        selectors = ("#size-chips", "#tier-sizes") if workspace == "image" else (".video-ratios", "#video-resolutions")
        for selector in selectors:
            check_group(page, selector, case, failures)
        if workspace == "image":
            page.locator('label[for="mode-edit"]').click()
            check_group(page, "#edit-sizes", case, failures)
            page.locator('label[for="mode-generate"]').click()
        override.evaluate("element => element.remove()")


def check_case(browser, base, width, locale, failures):
    context = browser.new_context(
        viewport={"width": width, "height": 1000}, locale=locale, is_mobile=width <= 900, has_touch=width <= 900
    )
    page = context.new_page()
    for workspace in ("image", "video"):
        check_workspace(page, base, workspace, width, locale, failures)
    context.close()


def main():
    failures = []
    base = "http://127.0.0.1:" + sys.argv[1]
    engine = sys.argv[2] if len(sys.argv) > 2 else "chromium"
    with sync_playwright() as tool:
        browser = getattr(tool, engine).launch()
        for locale in ("en", "zh-TW"):
            for width in WIDTHS:
                check_case(browser, base, width, locale, failures)
                print("CHECK", engine, locale, width, flush=True)
        browser.close()
    for failure in failures:
        print("FAIL", json.dumps(failure, ensure_ascii=False), flush=True)
    print("FAILURES", len(failures), flush=True)
    raise SystemExit(bool(failures))


if __name__ == "__main__":
    main()
