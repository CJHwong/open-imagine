"""Check equal choice widths, plain style rows, and immediate Rewrite feedback.

Run against a fresh all-backend stub:
uv run --with playwright python tests/e2e/verify_control_feedback.py <port> [--webkit]
"""

import json
import re
import sys

from playwright.sync_api import expect, sync_playwright
from style_controls import show_controls


def record(failures, condition, case, detail):
    if condition:
        return
    failures.append({"case": case, "detail": detail})
    print("FAIL", json.dumps(failures[-1]), flush=True)


def check_choices(page, width, failures):
    page.goto(BASE + "/?workspace=video")
    show_controls(page)
    page.locator("#video-advanced > summary").click()
    page.add_style_tag(content="#video-controls button {font-size:24px !important}")
    check_choice_groups(page, str(width), failures)
    ratios = page.locator(".video-ratios button")
    for index in range(ratios.count()):
        ratios.nth(index).click()
        check_choice_groups(page, str(width) + "/shape=" + ratios.nth(index).inner_text(), failures)


def check_choice_groups(page, case, failures):
    for selector in (".video-ratios", "#video-resolutions"):
        sizes = page.locator(selector).evaluate("""group => ({
            overflow:group.scrollWidth-group.clientWidth,
            buttons:[...group.querySelectorAll('button')].filter(button=>button.getClientRects().length)
                .map(button=>{
                    const border=button.getBoundingClientRect();
                    const range=document.createRange();range.selectNodeContents(button);
                    return {width:border.width,top:border.top,textFits:[...range.getClientRects()].every(text=>
                        text.left>=border.left && text.right<=border.right
                        && text.top>=border.top && text.bottom<=border.bottom)};
                })
        })""")
        widths = [button["width"] for button in sizes["buttons"]]
        record(failures, max(widths) - min(widths) <= 2, case + selector + "/equal-widths", sizes)
        record(failures, sizes["overflow"] <= 1, case + selector + "/no-overflow", sizes)
        record(failures, all(button["textFits"] for button in sizes["buttons"]), case + selector + "/text-fits", sizes)


def row_style(control):
    return control.evaluate("""button => {
        const style=getComputedStyle(button);
        const row=button.matches('.look-row-toggle') ? button.closest('.look-row') : null;
        const next=row ? row.nextElementSibling : button.nextElementSibling;
        const below=next?.matches('.look-row') ? next.querySelector('.look-row-toggle') : next;
        const edges=[style.borderBottomWidth,
            row ? getComputedStyle(row).borderBottomWidth : 0,
            below?.getClientRects().length ? getComputedStyle(below).borderTopWidth : 0,
            next?.getClientRects().length ? getComputedStyle(next).borderTopWidth : 0];
        return {background:style.backgroundColor,radius:parseFloat(style.borderRadius),
            left:parseFloat(style.borderLeftWidth),right:parseFloat(style.borderRightWidth),
            divider:Math.max(...edges.map(edge=>parseFloat(edge)||0)),shadow:style.boxShadow};
    }""")


def check_style(page, workspace, failures):
    page.goto(BASE + "/?workspace=" + workspace)
    show_controls(page)
    panel = page.locator({"image": "#look", "video": "#video-look", "music": "#music-style-presets"}[workspace])
    panel.locator("summary").click()
    trigger = panel.locator(".look-row-toggle").first
    style = row_style(trigger)
    plain = style["radius"] == style["left"] == style["right"] == 0
    plain = plain and style["background"] == "rgba(0, 0, 0, 0)" and 0 < style["divider"] <= 1
    record(failures, plain, workspace + "/plain-style-row", style)
    trigger.click()
    dialog = page.locator(".mobile-menu-dialog[open]")
    if dialog.count():
        title = dialog.locator("h2").inner_text()
        record(failures, title == trigger.locator(".label").inner_text(), workspace + "/picker-title", title)
    menu = page.locator("#" + trigger.get_attribute("aria-controls"))
    option = menu.get_by_role("menuitemradio").first
    style = row_style(option)
    plain = style["radius"] == style["left"] == style["right"] == 0
    plain = plain and 0 < style["divider"] <= 1 and style["background"] == "rgba(0, 0, 0, 0)"
    record(failures, plain, workspace + "/plain-option-divider", style)
    expect(option).to_have_attribute("aria-checked", "true")
    expect(option.locator(".choice-check")).to_be_visible()
    page.keyboard.press("ArrowDown")
    focused = menu.locator("button:focus")
    style = row_style(focused)
    record(failures, style["background"] == "rgba(0, 0, 0, 0)", workspace + "/keyboard-focus-no-fill", style)
    record(
        failures,
        focused.evaluate("button=>getComputedStyle(button).outlineStyle") != "none",
        workspace + "/keyboard-outline",
        style,
    )
    page.keyboard.press("Escape")


def check_rewrite(page, workspace, failures):
    page.goto(BASE + "/?workspace=" + workspace)
    show_controls(page)
    prefix = "video-" if workspace == "video" else ""
    field = page.locator("#" + prefix + "prompt")
    button = page.locator("#" + prefix + "rewrite-toggle")
    field.fill("")
    requests = []
    page.on("request", lambda request: requests.append(request.url) if request.method == "POST" else None)
    button.scroll_into_view_if_needed()
    bounds = button.bounding_box()
    page.touchscreen.tap(bounds["x"] + bounds["width"] / 2, bounds["y"] + bounds["height"] / 2)
    page.wait_for_timeout(150)
    feedback = page.locator("#toasts").inner_text()
    record(failures, "prompt" in feedback.lower(), workspace + "/blank-rewrite-feedback", feedback)
    record(failures, not requests, workspace + "/blank-rewrite-no-request", requests)
    notices = page.locator("#toasts .toast")
    before = notices.count()
    button.press("Enter")
    expect(notices).to_have_count(before + 1)
    record(failures, not requests, workspace + "/keyboard-blank-no-request", requests)
    field.fill("A short prompt for the rewriter.")
    button.click()
    expect(page.locator("body")).to_have_class(re.compile("rewriting"))
    expect(button).to_have_text("Preparing…", use_inner_text=True)
    expect(button).to_have_attribute("aria-disabled", "true")
    help_text = page.locator("#" + prefix + "rewrite-toggle-help").inner_text()
    bounds = button.bounding_box()
    page.touchscreen.tap(bounds["x"] + bounds["width"] / 2, bounds["y"] + bounds["height"] / 2)
    expect(page.locator("#toasts")).to_contain_text(help_text)
    page.wait_for_function(
        "id => document.getElementById(id).innerText.trim() === 'Cancel'", arg=prefix + "rewrite-toggle"
    )
    button.click()
    page.wait_for_function("!document.body.classList.contains('rewriting')")
    record(failures, any(url.endswith("/rewrite/cancel") for url in requests), workspace + "/rewrite-cancel", requests)


BASE = "http://127.0.0.1:" + sys.argv[1]
failures = []
with sync_playwright() as playwright:
    engine = playwright.webkit if "--webkit" in sys.argv else playwright.chromium
    browser = engine.launch()
    context = browser.new_context(viewport={"width": 280, "height": 882}, has_touch=True, is_mobile=True)
    context.add_init_script("localStorage.setItem('studio-keep','off')")
    page = context.new_page()
    for width in (280, 600):
        page.set_viewport_size({"width": width, "height": 882})
        check_choices(page, width, failures)
    page.set_viewport_size({"width": 390, "height": 882})
    for workspace in ("image", "video", "music"):
        check_style(page, workspace, failures)
    for workspace in ("image", "video"):
        check_rewrite(page, workspace, failures)
    browser.close()
print("FAILURES", len(failures), flush=True)
raise SystemExit(bool(failures))
