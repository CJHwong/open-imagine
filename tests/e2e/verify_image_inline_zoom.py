"""Operate zoom on the main image without leaving its preview."""

import io
import json
import math
import re
import sys
import time

from PIL import Image
from playwright.sync_api import expect, sync_playwright
from style_controls import show_controls


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


def record(failures, condition, case, detail):
    if condition:
        return
    failures.append({"case": case, "detail": detail})
    print("FAIL", json.dumps(failures[-1]), flush=True)


def scale(page):
    return page.locator("#canvas").evaluate(
        "canvas => Number(getComputedStyle(canvas).getPropertyValue('--viewer-scale')) || 1"
    )


def position(page):
    return page.locator("#canvas").evaluate("""canvas => {
        const style = getComputedStyle(canvas);
        return ['--viewer-x', '--viewer-y'].map(name => parseFloat(style.getPropertyValue(name)) || 0);
    }""")


def drag(page, start, end):
    page.mouse.move(*start)
    page.mouse.down()
    page.mouse.move(*end, steps=8)
    page.mouse.up()


def contacts(session, action, points):
    session.send(
        "Input.dispatchTouchEvent",
        {
            "type": action,
            "touchPoints": [{"id": index + 1, "x": point[0], "y": point[1]} for index, point in enumerate(points)],
        },
    )


def pinch(page, center):
    session = page.context.new_cdp_session(page)
    contacts(session, "touchStart", [(center[0] - 20, center[1]), (center[0] + 20, center[1])])
    for spread in range(25, 66, 5):
        contacts(session, "touchMove", [(center[0] - spread, center[1]), (center[0] + spread, center[1])])
        time.sleep(0.02)
    contacts(session, "touchEnd", [])
    session.detach()


def inspect_preview(page, case, failures):
    check_minimal_preview(page, case, failures)
    check_no_fullscreen(page, case, failures)
    picture = page.locator("#image-stage .pic").bounding_box()
    record(failures, min(picture["width"], picture["height"]) >= 80, case + "/usable-fitted-image", picture)
    if "--screenshots" in sys.argv and case in ("en/390x882", "en/1440x1000"):
        page.screenshot(path="/tmp/image-gen-inline-main-" + case.split("/")[1] + ".png")


def check_inline(page, case, failures, native_touch, wheel):
    canvas = page.locator("#canvas")
    center = image_center(page)
    if wheel:
        page.mouse.move(*center)
        page.mouse.wheel(0, -360)
        page.wait_for_timeout(150)
        record(failures, scale(page) > 1.05, case + "/main-image-wheel", scale(page))
    canvas.press("Home")
    record(failures, abs(scale(page) - 1) < 0.01, case + "/home-fits-preview", scale(page))
    canvas.press("Equal")
    record(failures, scale(page) > 1, case + "/keyboard-zoom-in", scale(page))
    zoomed = scale(page)
    canvas.press("Minus")
    record(failures, scale(page) < zoomed, case + "/keyboard-zoom-out", scale(page))
    for _ in range(3):
        canvas.press("Equal")
    before = position(page)
    drag(page, (center[0] + 30, center[1] + 20), (center[0] - 30, center[1] - 20))
    record(failures, position(page) != before, case + "/main-image-pan", {"before": before, "after": position(page)})
    current_scale = scale(page)
    compare = page.locator("#image-stage .compare")
    compare.click()
    record(failures, abs(scale(page) - current_scale) < 0.01, case + "/compare-keeps-zoom", scale(page))
    expect(page.locator("#image-stage .compare-range")).to_be_visible()
    compare.click()
    canvas.press("Home")
    page.mouse.dblclick(*center)
    record(failures, scale(page) > 1.5, case + "/double-click-zooms", scale(page))
    page.mouse.dblclick(*center)
    record(failures, abs(scale(page) - 1) < 0.01, case + "/double-click-resets", scale(page))
    if native_touch:
        session = page.context.new_cdp_session(page)
        for _ in range(2):
            contacts(session, "touchStart", [center])
            contacts(session, "touchEnd", [])
            time.sleep(0.05)
        record(failures, scale(page) > 1.5, case + "/native-double-tap-zooms", scale(page))
        for _ in range(2):
            contacts(session, "touchStart", [center])
            contacts(session, "touchEnd", [])
            time.sleep(0.05)
        record(failures, abs(scale(page) - 1) < 0.01, case + "/native-double-tap-resets", scale(page))
        session.detach()
        canvas.press("Home")
        pinch(page, center)
        record(failures, scale(page) > 1.5, case + "/main-image-native-pinch", scale(page))
    record(failures, page.locator("#image-stage .pic").is_visible(), case + "/preview-remains-visible", "main image")


def check_brush(page, case, failures, native_touch):
    if scale(page) <= 1.001:
        page.locator("#canvas").press("Equal")
    before = page.locator("#image-stage .pic > img:not(.before)").bounding_box()["width"]
    page.locator("#image-stage .actions .preview-primary-action").click()
    if page.locator(".pane-switch").is_visible():
        page.locator('.pane-switch [data-pane="preview"]').click()
    marks = page.locator("#image-stage .region-mark")
    expect(marks).to_be_visible()
    expect(page.locator(".image-preview-help")).not_to_have_text("")
    help_text = page.locator(".image-preview-help").inner_text()
    record(
        failures,
        "zoom" in help_text.lower() or "縮放" in help_text,
        case + "/brush-guidance-names-inspection-viewer",
        help_text,
    )
    marks.evaluate(
        "async () => await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))"
    )
    current = page.locator("#image-stage .pic > img:not(.before)").bounding_box()["width"]
    record(failures, abs(current - before) <= 2, case + "/brush-keeps-zoom", {"before": before, "after": current})
    canvas = page.locator("#canvas").bounding_box()
    center = (canvas["x"] + canvas["width"] / 2, canvas["y"] + canvas["height"] / 2)
    offset = position(page)
    (touch_drag if native_touch else drag)(page, (center[0] - 30, center[1] - 10), (center[0] + 30, center[1] + 10))
    pixels = marks.evaluate("canvas => canvas.toDataURL()")
    ink = marks.evaluate(
        "canvas => canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data.some((value,index) => index%4 === 3 && value>0)"
    )
    record(failures, ink, case + "/brush-draws-pixels", ink)
    record(failures, position(page) == offset, case + "/brush-does-not-pan", position(page))
    if native_touch:
        before = scale(page)
        pinch(page, center)
        record(failures, abs(scale(page) - before) < 0.01, case + "/armed-brush-blocks-pinch", scale(page))
        pixels = marks.evaluate("canvas => canvas.toDataURL()")
    page.locator("#canvas").press("Home")
    fitted = page.locator("#image-stage .pic").bounding_box()
    print("BRUSH_FIT", case, json.dumps(fitted), flush=True)
    record(failures, min(fitted["width"], fitted["height"]) >= 80, case + "/usable-brush-fit", fitted)
    if min(fitted["width"], fitted["height"]) < 80:
        geometry = page.evaluate("""() => Object.fromEntries(['.topbar','#image-stage','#canvas','#stage-bar',
            '.region-tools','.image-preview-help','.image-actions','#strip-wrap','#strip'].map(selector => {
                const node = document.querySelector(selector), box = node.getBoundingClientRect();
                return [selector, {width: box.width, height: box.height, top: box.top, scrollHeight: node.scrollHeight}];
            }))""")
        print("GEOMETRY", case, json.dumps(geometry), flush=True)
        page.screenshot(path="/tmp/image-gen-inline-brush-" + case.replace("/", "-") + ".png")
    page.locator("#canvas").press("Equal")
    record(failures, scale(page) > 1, case + "/brush-allows-keyboard-zoom", scale(page))
    record(
        failures,
        marks.evaluate("canvas => canvas.toDataURL()") == pixels,
        case + "/zoom-keeps-brush-pixels",
        "same canvas pixels",
    )
    page.locator("#image-stage .compare").click()
    page.locator("#image-stage .compare").click()
    record(
        failures,
        marks.evaluate("canvas => canvas.toDataURL()") == pixels,
        case + "/compare-keeps-brush-pixels",
        "same canvas pixels",
    )
    expect(page.locator("#image-stage .compare-range")).to_have_count(0)


def touch_drag(page, start, end):
    session = page.context.new_cdp_session(page)
    contacts(session, "touchStart", [start])
    for step in range(1, 9):
        point = (start[0] + (end[0] - start[0]) * step / 8, start[1] + (end[1] - start[1]) * step / 8)
        contacts(session, "touchMove", [point])
        time.sleep(0.02)
    contacts(session, "touchEnd", [])
    session.detach()


def two_finger_pan(page, center):
    session = page.context.new_cdp_session(page)
    contacts(session, "touchStart", [(center[0] - 20, center[1]), (center[0] + 20, center[1])])
    for step in range(1, 9):
        contacts(
            session,
            "touchMove",
            [(center[0] - 20 + step * 4, center[1] + step * 2), (center[0] + 20 + step * 4, center[1] + step * 2)],
        )
        time.sleep(0.02)
    contacts(session, "touchEnd", [])
    session.detach()


def image_center(page):
    bounds = page.locator("#canvas").bounding_box()
    return bounds["x"] + bounds["width"] / 2, bounds["y"] + bounds["height"] / 2


def check_gallery_gestures(page, case, failures):
    page.locator("#image-stage .actions .preview-primary-action").click()
    show_controls(page)
    page.locator("#prompt").fill("A second inline zoom result.")
    if not page.locator("#advanced").evaluate("section => section.open"):
        page.locator("#advanced > summary").click()
    page.locator("#steps").fill("1")
    page.locator("#advanced > summary").click()
    page.locator("#go").click()
    bitmap = page.locator("#image-stage .pic > img:not(.before)")
    expect(bitmap).to_have_attribute("alt", "A second inline zoom result.", timeout=30000)
    page.wait_for_function("!busy() && !sharedOperation")
    bitmap.evaluate(
        "async image => await Promise.all(image.closest('.shot').getAnimations({subtree:true}).map(animation => animation.finished))"
    )
    record(failures, abs(scale(page) - 1) < 0.01, case + "/new-frame-resets-zoom", scale(page))
    compare = page.locator("#image-stage .compare")
    if compare.get_attribute("aria-pressed") == "true":
        compare.click()
    center = image_center(page)
    touch_drag(page, (center[0] + 45, center[1]), (center[0] - 65, center[1]))
    expect(bitmap).to_have_attribute("alt", "Make this image blue.")
    record(failures, abs(scale(page) - 1) < 0.01, case + "/gallery-swipe-resets-zoom", scale(page))
    pinch(page, center)
    selected = bitmap.get_attribute("alt")
    offset = position(page)
    page.locator("#canvas").press("ArrowRight")
    record(
        failures,
        bitmap.get_attribute("alt") == selected and position(page) != offset,
        case + "/zoomed-arrows-pan-without-navigation",
        {"alt": bitmap.get_attribute("alt"), "position": position(page)},
    )
    touch_drag(page, (center[0] + 35, center[1]), (center[0] - 35, center[1]))
    record(failures, bitmap.get_attribute("alt") == selected, case + "/zoomed-drag-does-not-navigate", selected)
    compare.click()
    slider = page.locator("#image-stage .compare-range")
    expect(slider).to_be_visible()
    value = float(slider.input_value())
    current_scale = scale(page)
    touch_drag(page, center, (center[0] + 45, center[1]))
    record(failures, float(slider.input_value()) != value, case + "/compare-one-finger-wipes", slider.input_value())
    record(
        failures,
        bitmap.get_attribute("alt") == selected and abs(scale(page) - current_scale) < 0.01,
        case + "/compare-drag-keeps-frame-and-zoom",
        {"alt": bitmap.get_attribute("alt"), "scale": scale(page)},
    )
    offset = position(page)
    split = slider.input_value()
    two_finger_pan(page, center)
    record(
        failures,
        slider.input_value() == split,
        case + "/two-finger-pan-keeps-split",
        {"before": split, "after": slider.input_value()},
    )
    record(
        failures,
        position(page) != offset,
        case + "/compare-two-finger-pan",
        {"before": offset, "after": position(page)},
    )
    page.locator("#canvas").press("Home")
    split = slider.input_value()
    pinch(page, center)
    record(
        failures,
        slider.input_value() == split,
        case + "/two-finger-pinch-keeps-split",
        {"before": split, "after": slider.input_value()},
    )
    record(failures, scale(page) > 1.5, case + "/compare-native-pinch", scale(page))
    compare.click()
    page.locator("#canvas").press("Home")
    touch_drag(page, (center[0] - 45, center[1]), (center[0] + 65, center[1]))
    expect(bitmap).to_have_attribute("alt", "A second inline zoom result.")
    record(failures, abs(scale(page) - 1) < 0.01, case + "/gallery-swipe-restored", scale(page))
    page.locator("#canvas").press("ArrowRight")
    expect(bitmap).to_have_attribute("alt", "Make this image blue.")


def check_minimal_preview(page, case, failures):
    actions = page.locator("#image-stage .actions")
    record(
        failures,
        page.locator("#image-stage [data-zoom-action]:visible").count() == 0,
        case + "/no-inline-zoom-controls",
        page.locator("#image-stage [data-zoom-action]:visible").count(),
    )
    record(
        failures,
        page.locator("#image-stage .image-preview-scale:visible").count() == 0,
        case + "/no-inline-zoom-percentage",
        "preview percentage",
    )
    compare = actions.locator(".compare")
    record(failures, compare.count() == 1, case + "/compare-in-main-actions", compare.count())
    if compare.count():
        record(
            failures,
            compare.evaluate("button => button.nextElementSibling?.classList.contains('preview-details-toggle')"),
            case + "/compare-immediately-before-details",
            "action order",
        )
    captions = [control.locator(".control-label") for control in actions.locator("button:visible,a:visible").all()]
    record(
        failures,
        all(label.count() == 1 and label.is_visible() and label.inner_text().strip() for label in captions),
        case + "/all-main-actions-have-captions",
        actions.inner_text(),
    )
    boxes = actions.locator("button:visible,a:visible").evaluate_all(
        "buttons => buttons.map(button => {const box=button.getBoundingClientRect();return {x:box.x,y:box.y,width:box.width,height:box.height};})"
    )
    record(
        failures,
        max(box["y"] for box in boxes) - min(box["y"] for box in boxes) <= 1,
        case + "/minimal-action-single-row",
        boxes,
    )
    record(
        failures,
        max(box["height"] for box in boxes) - min(box["height"] for box in boxes) <= 1,
        case + "/minimal-actions-same-height",
        boxes,
    )
    record(
        failures,
        all(box["x"] >= 0 and box["x"] + box["width"] <= page.viewport_size["width"] for box in boxes),
        case + "/minimal-actions-contained",
        boxes,
    )


def check_no_fullscreen(page, case, failures):
    buttons = page.locator("#stage-bar").get_by_role("button", name=re.compile(r"full.?screen|全螢幕", re.I))
    record(failures, buttons.count() == 0, case + "/no-image-fullscreen-action", buttons.count())
    page.locator("#canvas").press("f")
    page.wait_for_timeout(100)
    record(
        failures,
        not page.evaluate("Boolean(document.fullscreenElement)"),
        case + "/f-does-not-enter-fullscreen",
        "document fullscreen state",
    )


def check_toolbar_reach(page, case, failures):
    bar = page.locator("#stage-bar")
    clipped = []
    for control in bar.locator("button:visible,a:visible").all():
        control.scroll_into_view_if_needed()
        bounds, host = control.bounding_box(), bar.bounding_box()
        if bounds["y"] < host["y"] - 1 or bounds["y"] + bounds["height"] > host["y"] + host["height"] + 1:
            clipped.append({"name": control.get_attribute("aria-label"), "bounds": bounds, "host": host})
    record(failures, not clipped, case + "/toolbar-controls-scroll-reachable", clipped)
    record(
        failures,
        page.locator(".work").evaluate("work => work.scrollTop") == 0,
        case + "/toolbar-scroll-keeps-preview",
        "outer work scroll",
    )


def check_resize_zoom(page, case, failures):
    page.locator("#canvas").press("Home")
    center = image_center(page)
    bitmap = page.locator("#image-stage .pic > img:not(.before)")
    factor = bitmap.evaluate("image => image.naturalWidth") * 4 / bitmap.bounding_box()["width"]
    page.mouse.move(*center)
    page.mouse.wheel(0, -math.log(factor) / 0.002)
    page.wait_for_timeout(150)
    bitmap = page.locator("#image-stage .pic > img:not(.before)")
    before = bitmap.bounding_box()["width"]
    natural = bitmap.evaluate("image => image.naturalWidth")
    record(failures, abs(before / natural - 4) < 0.05, case + "/resize-starts-at400percent", before / natural)
    for width, height in ((390, 882), (768, 440), (1440, 1000)):
        page.set_viewport_size({"width": width, "height": height})
        bitmap.evaluate(
            "async () => await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))"
        )
        current = bitmap.bounding_box()["width"]
        record(
            failures,
            abs(current - before) <= 2,
            case + f"/resize-keeps-pixels-at{width}",
            {"before": before, "after": current},
        )
    page.locator("#canvas").press("Home")


def check_library_return(page, case, failures):
    library = page.locator("#image-gallery-browser")
    library.locator(".gallery-browse-toggle").click()
    expect(library).to_have_attribute("expanded", "")
    library.locator(".gallery-card-pick").first.click()
    page.locator("#canvas").evaluate(
        "async () => await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))"
    )
    record(
        failures,
        library.get_attribute("expanded") is None,
        case + "/library-selection-collapses",
        library.get_attribute("expanded"),
    )
    record(
        failures,
        page.locator("#image-stage .pic").is_visible(),
        case + "/library-selection-restores-preview",
        "main image",
    )


def check_optional_viewer(page, case, failures):
    zoom = page.locator("#image-stage .image-zoom-toggle")
    expect(zoom).to_be_visible()
    before = scale(page)
    zoom.click()
    dialog = page.locator("#image-viewer")
    expect(dialog).to_be_visible()
    dialog.evaluate("async dialog => await Promise.all(dialog.getAnimations().map(animation => animation.finished))")
    page.wait_for_function("document.querySelector('.image-viewer-image')?.naturalWidth > 0")
    viewport = dialog.locator(".image-viewer-viewport").bounding_box()
    bitmap = dialog.locator(".image-viewer-image").bounding_box()
    record(
        failures,
        viewport["height"] >= 200 and bitmap["width"] >= 80 and bitmap["height"] >= 80,
        case + "/expanded-image-usable",
        {"viewport": viewport, "image": bitmap},
    )
    page.wait_for_function("document.querySelector('.image-viewer-scale')?.textContent.trim().endsWith('%')")
    percentage = dialog.locator(".image-viewer-scale").inner_text()
    record(
        failures,
        percentage.endswith("%") and percentage[:-1].isdigit() and int(percentage[:-1]) > 0,
        case + "/expanded-natural-percentage",
        percentage,
    )
    titles = dialog.locator("h1:visible,h2:visible,h3:visible").all_inner_texts()
    record(failures, not any(title.strip() for title in titles), case + "/no-viewer-title", titles)
    header = dialog.locator(".sheet-head")
    header_controls = header.locator('.image-viewer-scale,[data-zoom-action="fit"],[data-zoom-action="actual"]')
    record(failures, header_controls.count() == 3, case + "/viewer-header-controls", header.inner_text())
    if header_controls.count() == 3:
        boxes = [control.bounding_box() for control in header_controls.all()]
        centers = [box["y"] + box["height"] / 2 for box in boxes]
        record(failures, max(centers) - min(centers) <= 2, case + "/viewer-header-single-row", boxes)
        group_center = (min(box["x"] for box in boxes) + max(box["x"] + box["width"] for box in boxes)) / 2
        head = header.bounding_box()
        record(
            failures,
            abs(group_center - head["x"] - head["width"] / 2) <= 2,
            case + "/viewer-header-centered",
            group_center,
        )
        close = dialog.locator(".close").bounding_box()
        record(
            failures, close["x"] >= max(box["x"] + box["width"] for box in boxes), case + "/viewer-close-right", close
        )
    if "--screenshots" in sys.argv and case in ("en/390x882", "en/1440x1000"):
        page.screenshot(path="/tmp/image-gen-inline-expanded-" + case.split("/")[1] + ".png")
    dialog.locator('[data-zoom-action="actual"]').click()
    actual = dialog.locator(".image-viewer-image").evaluate(
        "image => ({natural: image.naturalWidth, rendered: image.getBoundingClientRect().width})"
    )
    record(failures, abs(actual["natural"] - actual["rendered"]) <= 2, case + "/expanded-actual-pixels", actual)
    dialog.locator('[data-zoom-action="fit"]').click()
    expect(dialog.locator('[data-zoom-action="fit"]')).to_have_attribute("aria-pressed", "true")
    page.keyboard.press("Escape")
    expect(dialog).not_to_be_visible()
    expect(zoom).to_be_focused()
    record(failures, abs(scale(page) - before) < 0.01, case + "/viewer-keeps-inline-zoom", scale(page))


def check_case(browser, base, locale, width, height, failures, native_touch, wheel):
    context = browser.new_context(
        viewport={"width": width, "height": height}, has_touch=width <= 900, is_mobile=width <= 900
    )
    context.add_init_script("localStorage.setItem('studio-keep','off');localStorage.setItem('studio-compare','on')")
    page = context.new_page()
    page.goto(base + "/?lang=" + locale)
    seed_edit(page, (1248, 832))
    page.locator("#image-stage .compare").click()
    case = f"{locale}/{width}x{height}"
    if "--no-fullscreen-only" in sys.argv:
        check_no_fullscreen(page, case, failures)
        print("CHECK", case, flush=True)
        context.close()
        return
    if "--minimal-only" in sys.argv:
        check_minimal_preview(page, case, failures)
        check_no_fullscreen(page, case, failures)
        if "--screenshots" in sys.argv:
            page.screenshot(path="/tmp/image-gen-minimal-preview-" + case.split("/")[1] + ".png")
        center = image_center(page)
        page.mouse.move(*center)
        page.mouse.wheel(0, -360)
        page.wait_for_timeout(150)
        record(failures, scale(page) > 1.05, case + "/minimal-wheel-works", scale(page))
        page.locator("#canvas").press("Home")
        record(failures, abs(scale(page) - 1) < 0.01, case + "/minimal-home-resets", scale(page))
        print("CHECK", case, flush=True)
        context.close()
        return
    inspect_preview(page, case, failures)
    if "--resize-only" in sys.argv:
        check_resize_zoom(page, case, failures)
        print("CHECK", case, flush=True)
        context.close()
        return
    if "--library-only" in sys.argv:
        check_library_return(page, case, failures)
        print("CHECK", case, flush=True)
        context.close()
        return
    if "--compact-only" in sys.argv:
        check_brush(page, case, failures, False)
        check_toolbar_reach(page, case, failures)
        if "--screenshots" in sys.argv:
            page.screenshot(path="/tmp/image-gen-inline-compact-" + case.split("/")[1] + ".png")
        check_library_return(page, case, failures)
        print("CHECK", case, flush=True)
        context.close()
        return
    if "--viewer-only" in sys.argv:
        check_optional_viewer(page, case, failures)
        print("CHECK", case, flush=True)
        context.close()
        return
    check_inline(page, case, failures, native_touch, wheel)
    check_optional_viewer(page, case, failures)
    if locale == "en" and width == 1440:
        check_resize_zoom(page, case, failures)
    if native_touch and locale == "en":
        check_gallery_gestures(page, case, failures)
    if locale == "en" and width in (390, 600, 768, 1440):
        check_brush(page, case, failures, native_touch)
        check_toolbar_reach(page, case, failures)
    if 600 <= width <= 900:
        check_library_return(page, case, failures)
    record(
        failures, page.evaluate("document.documentElement.scrollWidth <= innerWidth"), case + "/no-page-overflow", width
    )
    print("CHECK", case, flush=True)
    context.close()


def main():
    failures = []
    webkit = "--webkit" in sys.argv
    scenarios = (
        [(390, 882), (1440, 1000)]
        if "--core" in sys.argv
        else [
            (280, 882),
            (390, 882),
            (600, 748),
            (768, 882),
            (884, 748),
            (1024, 1000),
            (1440, 1000),
            (600, 440),
            (768, 440),
        ]
    )
    with sync_playwright() as playwright:
        browser = (playwright.webkit if webkit else playwright.chromium).launch()
        locales = (
            ("en",)
            if any(
                flag in sys.argv
                for flag in (
                    "--native-only",
                    "--viewer-only",
                    "--compact-only",
                    "--library-only",
                    "--resize-only",
                    "--minimal-only",
                    "--no-fullscreen-only",
                )
            )
            else ("en", "zh-TW")
        )
        if "--native-only" in sys.argv or "--viewer-only" in sys.argv:
            scenarios = [(390, 882)]
        if "--compact-only" in sys.argv:
            scenarios = [(600, 748), (600, 440), (768, 440)]
        if "--library-only" in sys.argv:
            scenarios = [(600, 748)]
        if "--resize-only" in sys.argv:
            scenarios = [(1440, 1000)]
        if "--minimal-only" in sys.argv:
            scenarios = [(280, 882), (390, 882), (768, 882), (1440, 1000)]
        if "--no-fullscreen-only" in sys.argv:
            scenarios = [(390, 882)]
        for locale in locales:
            for width, height in scenarios:
                check_case(
                    browser,
                    f"http://127.0.0.1:{int(sys.argv[1])}",
                    locale,
                    width,
                    height,
                    failures,
                    not webkit and (width == 390 or (width == 768 and height == 440)),
                    not webkit or width > 900,
                )
        browser.close()
    print("FAILURES", len(failures), flush=True)
    return bool(failures)


if __name__ == "__main__":
    sys.exit(main())
