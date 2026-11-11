"""Operate Image Compare and zoom across phone, fold, and desktop layouts.

Run against a fresh Qwen all-backend stub:
uv run --with playwright python tests/e2e/verify_image_viewer.py <port> [--webkit] [--core]
Use --no-keep only when the runner cannot store native Blobs. This excludes the reload check.
"""

import io
import json
import re
import sys
import time

from PIL import Image
from playwright.sync_api import expect, sync_playwright
from style_controls import show_controls


def record(failures, condition, case, detail):
    if condition:
        return
    failures.append({"case": case, "detail": detail})
    print("FAIL", json.dumps(failures[-1]), flush=True)


def seed_edit(page, size):
    show_controls(page)
    page.locator('label[for="mode-edit"]').click()
    image = Image.new("RGB", size, "#b53328")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    page.locator("#reference").set_input_files(
        {"name": "viewer-before.png", "mimeType": "image/png", "buffer": buffer.getvalue()}
    )
    expect(page.locator("#thumbs .thumb")).to_have_count(1)
    page.locator("#prompt").fill("Make this image blue.")
    page.locator("#advanced > summary").click()
    page.locator("#steps").fill("1")
    page.locator("#advanced > summary").click()
    page.locator("#go").click()
    expect(page.locator("#image-stage .pic img.before")).to_be_visible(timeout=30000)
    page.wait_for_function("!busy() && !sharedOperation", timeout=30000)
    page.locator("#image-stage .shot").evaluate(
        "async shot=>await Promise.all(shot.getAnimations({subtree:true}).map(animation=>animation.finished))"
    )


def main_image(page):
    return page.locator("#image-stage .pic > img:not(.before)")


def touch_drag(page, start, end):
    session = page.context.new_cdp_session(page)
    session.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": start[0], "y": start[1]}]})
    for step in range(1, 9):
        point = {"x": start[0] + (end[0] - start[0]) * step / 8, "y": start[1] + (end[1] - start[1]) * step / 8}
        session.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [point]})
        time.sleep(0.02)
    session.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
    session.detach()


def pointer_drag(page, start, end, native_touch):
    if native_touch:
        touch_drag(page, start, end)
        return
    page.mouse.move(*start)
    page.mouse.down()
    page.mouse.move(*end, steps=8)
    page.mouse.up()


def dismiss_feedback(page, case, failures):
    errors = page.locator('#toasts .toast[role="alert"]').all_inner_texts()
    record(failures, not errors, case + "/unexpected-error-feedback", errors)
    for message in page.locator("#toasts .toast").all_inner_texts():
        print("FEEDBACK", case, message[:300], flush=True)
    label = page.evaluate("window.STUDIO_STRINGS['toast.dismiss']")
    dismiss = page.locator("#toasts").get_by_role("button", name=label, exact=True)
    while dismiss.count():
        dismiss.first.click()


def check_compare(page, case, failures, native_touch):
    dismiss_feedback(page, case + "/before-compare", failures)
    compare = page.locator("#image-stage .compare")
    original = main_image(page).get_attribute("src")
    compare.click()
    expect(page.locator("#image-stage .compare-range")).to_have_count(0)
    expect(compare).to_have_attribute("aria-pressed", "false")
    expect(compare).to_be_focused()
    compare.click()
    slider = page.locator("#image-stage .compare-range")
    expect(slider).to_be_visible()
    slider.press("ArrowLeft")
    before = int(slider.input_value())
    slider.press("ArrowRight")
    record(failures, int(slider.input_value()) > before, case + "/compare-keyboard", slider.input_value())
    bounds = slider.bounding_box()
    if native_touch:
        record(failures, min(bounds["width"], bounds["height"]) >= 44, case + "/compare-touch-area", bounds)
    if "--diagnostic" in sys.argv:
        slider.evaluate(
            "range=>{window.viewerProbeTargets=[];range.addEventListener('pointerdown',event=>window.viewerProbeTargets.push({tag:event.target.tagName,type:event.pointerType,action:'pointerdown'}));range.addEventListener('input',()=>window.viewerProbeTargets.push({value:range.value,action:'input'}));}"
        )
        points = [[bounds["x"] + bounds["width"] * edge, bounds["y"] + bounds["height"] * 0.5] for edge in (0.2, 0.8)]
        print(
            "RANGE_HIT_TARGETS",
            page.evaluate(
                "points=>points.map(([left,top])=>{const hit=document.elementFromPoint(left,top);return{tag:hit?.tagName,className:hit?.className};})",
                points,
            ),
            flush=True,
        )
    pointer_drag(
        page,
        (bounds["x"] + bounds["width"] * 0.2, bounds["y"] + bounds["height"] * 0.5),
        (bounds["x"] + bounds["width"] * 0.8, bounds["y"] + bounds["height"] * 0.5),
        native_touch,
    )
    record(
        failures,
        int(slider.input_value()) > 60,
        case + "/compare-drag",
        {"value": slider.input_value(), "bounds": bounds},
    )
    if "--diagnostic" in sys.argv:
        print("RANGE_EVENTS", page.evaluate("window.viewerProbeTargets"), flush=True)
    record(
        failures, main_image(page).get_attribute("src") == original, case + "/compare-keeps-result", "selected image"
    )


def check_viewer_bounds(page, case, failures):
    dimensions = page.locator("#image-viewer").evaluate("""dialog => {
        const rect=dialog.getBoundingClientRect();
        const viewport=dialog.querySelector('.image-viewer-viewport').getBoundingClientRect();
        const close=dialog.querySelector('.close').getBoundingClientRect();
        return {left:rect.left,top:rect.top,right:rect.right,bottom:rect.bottom,
            dialogWidth:rect.width,dialogHeight:rect.height,
            width:innerWidth,height:innerHeight,viewportWidth:viewport.width,viewportHeight:viewport.height,
            closeRight:close.right,closeBottom:close.bottom};
    }""")
    fits = dimensions["left"] >= 0 and dimensions["top"] >= 0
    fits = fits and dimensions["right"] <= dimensions["width"] + 1 and dimensions["bottom"] <= dimensions["height"] + 1
    fits = (
        fits and dimensions["closeRight"] <= dimensions["width"] and dimensions["closeBottom"] <= dimensions["height"]
    )
    record(failures, fits, case + "/viewer-bounds", dimensions)
    if dimensions["width"] < 600:
        fills = abs(dimensions["left"]) <= 1 and abs(dimensions["top"]) <= 1
        fills = fills and abs(dimensions["dialogWidth"] - dimensions["width"]) <= 1
        fills = fills and abs(dimensions["dialogHeight"] - dimensions["height"]) <= 1
        record(failures, fills, case + "/cover-full-screen", dimensions)
    record(
        failures,
        dimensions["viewportWidth"] > 100 and dimensions["viewportHeight"] > 100,
        case + "/usable-viewport",
        dimensions,
    )


def fitted_width(page):
    return page.locator(".image-viewer-image").bounding_box()["width"]


def open_viewer(page, zoom):
    zoom.click()
    dialog = page.locator("#image-viewer")
    expect(dialog).to_be_visible()
    expect(dialog.locator('[data-zoom-action="fit"]')).to_have_attribute("aria-pressed", "true")
    dialog.evaluate("async dialog=>await Promise.all(dialog.getAnimations().map(animation=>animation.finished))")
    return dialog


def check_viewer(page, zoom, case, failures, native_touch):
    original = main_image(page).get_attribute("src")
    split = page.locator("#image-stage .compare-range").input_value()
    dialog = open_viewer(page, zoom)
    bitmap = dialog.locator(".image-viewer-image")
    expect(bitmap).to_be_visible()
    record(failures, bitmap.get_attribute("src") == original, case + "/correct-bitmap", "selected edited bitmap")
    check_viewer_bounds(page, case, failures)
    fitted = fitted_width(page)
    viewport = dialog.locator(".image-viewer-viewport")
    viewport_bounds = viewport.bounding_box()
    record(failures, fitted <= viewport_bounds["width"] + 1, case + "/initial-fit", fitted)
    for action in ("in", "out", "fit", "actual"):
        button = dialog.locator('[data-zoom-action="' + action + '"]')
        expect(button).to_be_visible()
        record(
            failures, bool(button.inner_text().strip()), case + "/caption/" + action, button.get_attribute("aria-label")
        )
    fit_button = dialog.locator('[data-zoom-action="fit"]')
    expect(fit_button).to_have_attribute("aria-pressed", "true")
    pressed = fit_button.evaluate(
        "button=>({color:getComputedStyle(button).borderTopColor,width:parseFloat(getComputedStyle(button).borderTopWidth)})"
    )
    record(
        failures,
        pressed["width"] > 0 and pressed["color"] != "rgba(0, 0, 0, 0)",
        case + "/visible-fit-selection",
        pressed,
    )
    dialog.locator('[data-zoom-action="in"]').click()
    enlarged = fitted_width(page)
    record(failures, enlarged > fitted + 1, case + "/zoom-in", [fitted, enlarged])
    dialog.locator('[data-zoom-action="out"]').click()
    record(failures, fitted_width(page) < enlarged - 1, case + "/zoom-out", fitted_width(page))
    dialog.locator('[data-zoom-action="actual"]').click()
    natural = bitmap.evaluate("image=>image.naturalWidth")
    record(failures, abs(fitted_width(page) - natural) <= 2, case + "/natural-pixels", [fitted_width(page), natural])
    record(
        failures,
        "100" in dialog.locator(".image-viewer-scale").inner_text(),
        case + "/actual-scale-readout",
        dialog.locator(".image-viewer-scale").inner_text(),
    )
    dialog.locator('[data-zoom-action="fit"]').click()
    record(failures, abs(fitted_width(page) - fitted) <= 2, case + "/fit-restores", [fitted, fitted_width(page)])
    for _ in range(6):
        if fitted_width(page) > viewport_bounds["width"] + 100:
            break
        dialog.locator('[data-zoom-action="in"]').click()
    before = bitmap.bounding_box()
    center = (viewport_bounds["x"] + viewport_bounds["width"] / 2, viewport_bounds["y"] + viewport_bounds["height"] / 2)
    pointer_drag(page, center, (center[0] + 50, center[1] + 20), native_touch)
    after = bitmap.bounding_box()
    record(failures, abs(after["x"] - before["x"]) > 10, case + "/pan", [before["x"], after["x"]])
    expect(viewport).to_be_focused()
    viewport.press("ArrowRight")
    record(
        failures, abs(bitmap.bounding_box()["x"] - after["x"]) > 10, case + "/keyboard-pan", bitmap.bounding_box()["x"]
    )
    if page.context.browser.browser_type.name != "webkit" or page.viewport_size["width"] > 900:
        before_wheel = fitted_width(page)
        page.mouse.move(*center)
        page.mouse.wheel(0, -100)
        page.wait_for_function(
            "width=>document.querySelector('.image-viewer-image').getBoundingClientRect().width>width+1",
            arg=before_wheel,
        )
    viewport.press("Home")
    record(failures, abs(fitted_width(page) - fitted) <= 2, case + "/keyboard-fit", fitted_width(page))
    if not native_touch:
        viewport.dblclick()
        record(failures, fitted_width(page) > fitted * 1.5, case + "/mouse-double-click", fitted_width(page))
    record(failures, main_image(page).get_attribute("src") == original, case + "/pan-keeps-result", "selected image")
    page.keyboard.press("Escape")
    expect(dialog).to_have_count(0)
    expect(zoom).to_be_focused()
    open_viewer(page, zoom)
    record(failures, abs(fitted_width(page) - fitted) <= 2, case + "/reopen-starts-fitted", fitted_width(page))
    page.locator("#image-viewer .close").click()
    expect(zoom).to_be_focused()
    record(
        failures,
        page.locator("#image-stage .compare-range").input_value() == split,
        case + "/viewer-keeps-comparison",
        split,
    )


def check_pinch(page, zoom, case, failures):
    open_viewer(page, zoom)
    viewport = page.locator(".image-viewer-viewport").bounding_box()
    middle = (viewport["x"] + viewport["width"] / 2, viewport["y"] + viewport["height"] / 2)
    before = fitted_width(page)
    session = page.context.new_cdp_session(page)

    def contacts(distance):
        return [
            {"id": 1, "x": middle[0] - distance, "y": middle[1]},
            {"id": 2, "x": middle[0] + distance, "y": middle[1]},
        ]

    session.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": contacts(25)})
    for distance in (35, 45, 55, 65):
        session.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": contacts(distance)})
        time.sleep(0.03)
    session.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
    session.detach()
    record(failures, fitted_width(page) > before * 1.3, case + "/native-pinch", [before, fitted_width(page)])
    page.locator('[data-zoom-action="fit"]').click()
    page.touchscreen.tap(*middle)
    page.wait_for_timeout(100)
    page.touchscreen.tap(*middle)
    record(failures, fitted_width(page) > before * 1.5, case + "/native-double-tap", [before, fitted_width(page)])
    page.keyboard.press("Escape")


def check_open_fold(page, zoom, case, failures):
    previous = page.viewport_size
    open_viewer(page, zoom)
    for width, height in ((768, 748), (768, 440), (344, 882)):
        page.set_viewport_size({"width": width, "height": height})
        page.locator('[data-zoom-action="fit"]').click()
        check_viewer_bounds(page, case + "/fold=" + str(width) + "x" + str(height), failures)
        record(
            failures,
            fitted_width(page) <= page.locator(".image-viewer-viewport").bounding_box()["width"] + 1,
            case + "/fold-fit",
            fitted_width(page),
        )
    page.keyboard.press("Escape")
    expect(zoom).to_be_focused()
    page.set_viewport_size(previous)


def check_no_fullscreen(page, zoom, case, failures):
    buttons = page.locator("#stage-bar").get_by_role("button", name=re.compile(r"full.?screen|全螢幕", re.I))
    record(failures, buttons.count() == 0, case + "/no-image-fullscreen-action", buttons.count())
    page.locator("#canvas").press("f")
    page.wait_for_timeout(100)
    record(
        failures,
        not page.evaluate("Boolean(document.fullscreenElement)"),
        case + "/f-keeps-preview-in-page",
        "normal page",
    )
    open_viewer(page, zoom)
    page.locator(".image-viewer-viewport").press("f")
    record(
        failures,
        not page.evaluate("Boolean(document.fullscreenElement)"),
        case + "/viewer-stays-in-page",
        "inspection sheet",
    )
    expect(page.locator("#image-viewer")).to_be_visible()
    page.locator("#image-viewer .close").click()
    expect(zoom).to_be_focused()


def check_brush(page, zoom, case, failures, native_touch):
    page.get_by_role("button", name="Edit this", exact=True).click()
    if page.locator(".pane-switch").is_visible():
        page.locator('.pane-switch [data-pane="preview"]').click()
    marks = page.locator("#image-stage .region-mark")
    expect(marks).to_be_visible()
    bounds = marks.bounding_box()
    pointer_drag(
        page,
        (bounds["x"] + bounds["width"] * 0.2, bounds["y"] + bounds["height"] * 0.65),
        (bounds["x"] + bounds["width"] * 0.6, bounds["y"] + bounds["height"] * 0.65),
        native_touch,
    )
    painted = marks.evaluate("canvas=>canvas.toDataURL()")
    ink = marks.evaluate(
        "canvas=>canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data.some((value,index)=>index%4===3&&value>0)"
    )
    record(failures, ink, case + "/brush-draws", "visible stroke pixels")
    expect(page.locator("#image-stage .compare")).to_be_visible()
    expect(page.locator("#image-stage .compare-range")).not_to_be_visible()
    open_viewer(page, zoom)
    page.locator('[data-zoom-action="in"]').click()
    page.locator("#image-viewer .close").click()
    record(
        failures,
        marks.evaluate("canvas=>canvas.toDataURL()") == painted,
        case + "/zoom-keeps-marks",
        "stroke pixels unchanged",
    )
    page.locator("#image-stage .compare").click()
    page.locator("#image-stage .compare").click()
    remaining_ink = marks.evaluate(
        "canvas=>canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data.some((value,index)=>index%4===3&&value>0)"
    )
    record(
        failures,
        marks.evaluate("canvas=>canvas.toDataURL()") == painted,
        case + "/compare-keeps-marks",
        {"inkBefore": ink, "inkAfter": remaining_ink},
    )


def check_gallery_after_viewer(page, zoom, case, failures, native_touch):
    show_controls(page)
    page.locator('label[for="mode-generate"]').click()
    page.locator("#prompt").fill("A second viewer result.")
    if not page.locator("#advanced").evaluate("details=>details.open"):
        page.locator("#advanced > summary").click()
    page.locator("#steps").fill("1")
    page.locator("#advanced > summary").click()
    page.locator("#go").click()
    expect(main_image(page)).to_have_attribute("alt", "A second viewer result.", timeout=30000)
    page.wait_for_function("!busy() && !sharedOperation", timeout=30000)
    second = main_image(page).get_attribute("alt")
    open_viewer(page, zoom)
    viewport = page.locator(".image-viewer-viewport")
    viewport.press("ArrowRight")
    record(failures, main_image(page).get_attribute("alt") == second, case + "/viewer-owns-arrow-keys", second)
    bounds = viewport.bounding_box()
    pointer_drag(
        page,
        (bounds["x"] + bounds["width"] * 0.7, bounds["y"] + bounds["height"] * 0.6),
        (bounds["x"] + bounds["width"] * 0.3, bounds["y"] + bounds["height"] * 0.6),
        native_touch,
    )
    record(failures, main_image(page).get_attribute("alt") == second, case + "/viewer-owns-drag", second)
    page.locator("#image-viewer .close").click()
    zoom.focus()
    page.keyboard.press("ArrowRight")
    older = main_image(page).get_attribute("alt")
    record(failures, older != second, case + "/gallery-arrow-restored", older)
    page.keyboard.press("ArrowLeft")
    expect(main_image(page)).to_have_attribute("alt", second)
    if not native_touch:
        return
    bounds = main_image(page).bounding_box()
    center = (bounds["x"] + bounds["width"] / 2, bounds["y"] + bounds["height"] / 2)
    touch_drag(page, (center[0] + 45, center[1]), (center[0] - 65, center[1]))
    expect(main_image(page)).to_have_attribute("alt", older)
    page.locator("#image-stage .compare").click()
    bounds = main_image(page).bounding_box()
    center = (bounds["x"] + bounds["width"] / 2, bounds["y"] + bounds["height"] / 2)
    touch_drag(page, (center[0] - 45, center[1]), (center[0] + 65, center[1]))
    expect(main_image(page)).to_have_attribute("alt", second)


def check_short_library(page, case, failures, reload_check=False):
    dismiss_feedback(page, case + "/before-library", failures)
    library = page.locator("#image-gallery-browser")
    browse = library.locator(".gallery-browse-toggle")
    expect(browse).to_be_visible()
    expect(page.locator("#strip")).not_to_be_visible()
    browse.click()
    expect(library).to_have_attribute("expanded", "")
    expect(page.locator("#image-stage")).not_to_be_visible()
    expect(page.locator("#form .controls")).to_be_visible()
    library.locator(".gallery-card-pick").first.click()
    expect(library).not_to_have_attribute("expanded", "")
    expect(main_image(page)).to_be_visible()
    record(
        failures,
        page.locator(".work").evaluate("work=>work.scrollTop") == 0,
        case + "/selection-keeps-preview-position",
        "outer scroll remains zero",
    )
    if reload_check:
        count = page.locator("#strip .frame").count()
        page.reload()
        expect(page.locator("#strip .frame")).to_have_count(count, timeout=30000)
        record(
            failures,
            library.get_attribute("expanded") is None,
            case + "/selection-stays-preview-after-reload",
            library.get_attribute("expanded"),
        )
        record(failures, main_image(page).is_visible(), case + "/reload-visible-preview", "selected image visible")
        return
    browse.click()
    expect(library).to_have_attribute("expanded", "")
    browse.click()
    expect(main_image(page)).to_be_visible()
    original = page.viewport_size
    page.set_viewport_size({"width": original["width"], "height": 748})
    expect(page.locator("#strip")).not_to_be_visible()
    page.set_viewport_size(original)
    expect(page.locator("#strip")).not_to_be_visible()
    expect(page.locator("#form .controls")).to_be_visible()
    record(
        failures,
        page.locator(".work").evaluate("work=>work.scrollTop") == 0,
        case + "/resize-keeps-preview-position",
        "outer scroll remains zero",
    )


def check_case(browser, base, locale, width, height, failures, size=(768, 512)):
    context = browser.new_context(
        viewport={"width": width, "height": height}, locale=locale, has_touch=True, is_mobile=width <= 900
    )
    durable_case = locale == "en" and width == 768 and height == 440 and size[0] > size[1]
    keeping = "on" if "--library-core" in sys.argv or durable_case else "off"
    if "--no-keep" in sys.argv:
        keeping = "off"
    context.add_init_script(
        "localStorage.setItem('studio-keep','" + keeping + "');localStorage.setItem('studio-compare','on')"
    )
    page = context.new_page()
    page.goto(base + "/?lang=" + locale)
    seed_edit(page, size)
    case = locale + "/" + str(width) + "x" + str(height) + ("/portrait" if size[0] < size[1] else "")
    compare = page.locator("#image-stage .compare")
    record(failures, compare.count() == 1 and compare.is_visible(), case + "/visible-compare", compare.count())
    zoom = page.locator("#image-stage .image-zoom-toggle")
    record(failures, zoom.count() == 1 and zoom.is_visible(), case + "/visible-zoom", zoom.count())
    if zoom.count() and zoom.is_visible():
        picture = main_image(page).bounding_box()
        tools = page.locator("#image-stage .actions").bounding_box()
        overlap = min(picture["x"] + picture["width"], tools["x"] + tools["width"]) - max(picture["x"], tools["x"])
        overlap *= max(
            0, min(picture["y"] + picture["height"], tools["y"] + tools["height"]) - max(picture["y"], tools["y"])
        )
        record(failures, overlap <= 0, case + "/tools-clear-picture", {"picture": picture, "tools": tools})
        if width <= 900:
            record(failures, min(picture["width"], picture["height"]) >= 44, case + "/usable-picture", picture)
        frame = page.locator("#image-stage .shot").bounding_box()
        canvas = page.locator("#image-stage .canvas").bounding_box()
        contained = frame["x"] >= canvas["x"] - 1 and frame["y"] >= canvas["y"] - 1
        contained = contained and frame["x"] + frame["width"] <= canvas["x"] + canvas["width"] + 1
        contained = contained and frame["y"] + frame["height"] <= canvas["y"] + canvas["height"] + 1
        record(failures, contained, case + "/whole-frame-fits", {"frame": frame, "canvas": canvas})
    if zoom.count() and zoom.is_visible() and compare.is_visible():
        native_touch = browser.browser_type.name == "chromium" and width <= 900
        check_compare(page, case, failures, native_touch)
        check_viewer(page, zoom, case, failures, native_touch)
        if native_touch and width == 390 and locale == "en":
            check_pinch(page, zoom, case, failures)
        if width == 390 and locale == "en":
            check_open_fold(page, zoom, case, failures)
        if width == 1440 and locale == "en":
            check_no_fullscreen(page, zoom, case, failures)
        if width in (390, 1440) and locale == "en" and size[0] > size[1]:
            check_brush(page, zoom, case, failures, native_touch)
        if locale == "en" and size[0] > size[1] and (width in (390, 1440) or height <= 600):
            check_gallery_after_viewer(page, zoom, case, failures, native_touch)
        if 600 <= width <= 900 and height <= 600:
            check_short_library(page, case, failures, keeping == "on")
    print("CHECK", case, flush=True)
    context.close()


def scenarios():
    core = any(option in sys.argv for option in ("--core", "--portrait-core", "--short-core", "--library-core"))
    sizes = (
        ((390, 844),)
        if core
        else ((280, 882), (390, 844), (600, 748), (768, 748), (884, 1104), (1024, 900), (1440, 1000), (768, 440))
    )
    if "--short-core" in sys.argv or "--library-core" in sys.argv:
        sizes = ((768, 440),)
    locales = ("en",) if core else ("en", "zh-TW")
    size = (576, 1024) if "--portrait-core" in sys.argv else (768, 512)
    cases = [(locale, width, height, size) for locale in locales for width, height in sizes]
    if not core:
        cases.extend(
            (locale, width, height, (576, 1024))
            for locale in locales
            for width, height in ((390, 844), (768, 440), (1440, 1000))
        )
    return cases


base = "http://127.0.0.1:" + sys.argv[1]
failures = []
if "--no-keep" in sys.argv and "--library-core" in sys.argv:
    raise SystemExit("Choose --no-keep or --library-core.")
if "--no-keep" in sys.argv:
    print("LIMITATION native Blob storage unavailable; persistence reload check excluded", flush=True)
with sync_playwright() as playwright:
    browser = (playwright.webkit if "--webkit" in sys.argv else playwright.chromium).launch()
    for locale, width, height, size in scenarios():
        check_case(browser, base, locale, width, height, failures, size)
    browser.close()
print("FAILURES", len(failures), flush=True)
raise SystemExit(bool(failures))
