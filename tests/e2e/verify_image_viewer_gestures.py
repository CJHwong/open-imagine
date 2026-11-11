"""Check interrupted taps do not combine into a viewer double tap.

Run against a fresh all-backend qwen21 stub. No model is loaded.
uv run --with playwright python tests/e2e/verify_image_viewer_gestures.py <port>
"""

import json
import sys

from playwright.sync_api import expect, sync_playwright
from style_controls import show_controls


def prepare_image(page, base):
    page.goto(base)
    show_controls(page)
    page.locator("#prompt").fill("A synthetic gesture test image.")
    page.locator("#advanced > summary").click()
    page.locator("#steps").fill("1")
    page.locator("#advanced > summary").click()
    page.locator("#go").click()
    expect(page.locator("#image-stage .image-zoom-toggle")).to_be_visible(timeout=20000)
    page.wait_for_function("!busy() && !sharedOperation && !sharedBusy()")


def open_viewer(page):
    page.locator("#image-stage .image-zoom-toggle").click()
    dialog = page.locator("#image-viewer")
    expect(dialog).to_be_visible()
    expect(dialog.locator('[data-zoom-action="fit"]')).to_have_attribute("aria-pressed", "true")
    dialog.evaluate("async dialog=>await Promise.all(dialog.getAnimations().map(animation=>animation.finished))")
    viewport = dialog.locator(".image-viewer-viewport")
    viewport.evaluate("""viewport => {
        window.viewerGestureEvents = [];
        for (const name of ['pointerdown', 'pointerup', 'pointercancel', 'lostpointercapture']) {
            viewport.addEventListener(name, event => {
                viewport.dataset.gesturePointer = event.pointerId;
                window.viewerGestureEvents.push({type: event.type, at: performance.now()});
            });
        }
    }""")
    box = viewport.bounding_box()
    return viewport, (box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)


def touch(session, event_type, point=None):
    contacts = [{"id": 1, "x": point[0], "y": point[1]}] if point else []
    session.send("Input.dispatchTouchEvent", {"type": event_type, "touchPoints": contacts})


def tap(session, point):
    touch(session, "touchStart", point)
    touch(session, "touchEnd")


def interrupted_taps(page, session, interruption):
    viewport, point = open_viewer(page)
    tap(session, point)
    touch(session, "touchStart", point)
    if interruption == "drag":
        touch(session, "touchMove", (point[0] + 24, point[1]))
        touch(session, "touchMove", point)
        touch(session, "touchEnd")
    elif interruption == "cancel":
        touch(session, "touchCancel")
    else:
        touch(session, "touchMove", (point[0] + 1, point[1]))
        assert viewport.evaluate("viewport => viewport.hasPointerCapture(Number(viewport.dataset.gesturePointer))")
        viewport.evaluate("viewport => viewport.releasePointerCapture(Number(viewport.dataset.gesturePointer))")
        touch(session, "touchMove", (point[0] + 2, point[1]))
        touch(session, "touchEnd")
    tap(session, point)
    result = viewport.evaluate("""viewport => ({
        scale: Number(viewport.style.getPropertyValue('--viewer-scale')),
        events: window.viewerGestureEvents
    })""")
    page.keyboard.press("Escape")
    return result


def ordinary_double_tap(page, session):
    viewport, point = open_viewer(page)
    tap(session, point)
    tap(session, point)
    result = viewport.evaluate("""viewport => ({
        scale: Number(viewport.style.getPropertyValue('--viewer-scale')),
        events: window.viewerGestureEvents
    })""")
    page.keyboard.press("Escape")
    return result


def check_interrupted(page, session, interruption, failures):
    result = interrupted_taps(page, session, interruption)
    endings = [event for event in result["events"] if event["type"] == "pointerup"]
    assert len(endings) >= 2 and endings[-1]["at"] - endings[0]["at"] < 320, result
    if interruption == "cancel":
        assert any(event["type"] == "pointercancel" for event in result["events"]), result
    if interruption == "capture":
        names = [event["type"] for event in result["events"]]
        second_press = [index for index, name in enumerate(names) if name == "pointerdown"][1]
        second_release = names.index("pointerup", second_press)
        assert "lostpointercapture" in names[second_press:second_release], result
    if result["scale"] != 1:
        failures.append({"case": interruption, "detail": result})
    print("CHECK", interruption, "scale", result["scale"], flush=True)


def main():
    failures = []
    with sync_playwright() as tool:
        browser = tool.chromium.launch()
        context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        context.add_init_script("localStorage.setItem('studio-keep','off')")
        page = context.new_page()
        prepare_image(page, "http://127.0.0.1:" + sys.argv[1])
        session = context.new_cdp_session(page)
        for interruption in ("drag", "cancel", "capture"):
            check_interrupted(page, session, interruption, failures)
        ordinary = ordinary_double_tap(page, session)
        assert ordinary["scale"] > 1.5, ordinary
        print("CHECK ordinary double tap scale", ordinary["scale"], flush=True)
        session.detach()
        context.close()
        browser.close()
    for failure in failures:
        print("FAIL", json.dumps(failure), flush=True)
    print("FAILURES", len(failures), flush=True)
    raise SystemExit(bool(failures))


if __name__ == "__main__":
    main()
