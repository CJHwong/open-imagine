"""Real video playback stays available after fullscreen controls are removed."""

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import expect, sync_playwright
from style_controls import show_controls


def record(failures, condition, case, detail):
    if condition:
        return
    failures.append({"case": case, "detail": detail})
    print("FAIL", json.dumps(failures[-1]), flush=True)


def make_clip(path):
    process = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=royalblue:s=320x180:r=12:d=6",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "ultrafast",
            "-movflags",
            "+faststart",
            "-y",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if process.returncode:
        raise RuntimeError(process.stderr)


def check_case(browser, base, clip, width, locale, failures):
    context = browser.new_context(
        viewport={"width": width, "height": 882}, has_touch=width <= 900, is_mobile=width <= 900
    )
    context.add_init_script("localStorage.setItem('studio-keep','off');localStorage.setItem('studio-autoplay','off')")
    page = context.new_page()
    page.goto(base + "/?workspace=video&lang=" + locale)
    show_controls(page)
    page.locator('label[for="video-mode-edit"]').click()
    page.locator("#video-media-upload").set_input_files(str(clip))
    if page.locator(".pane-switch").is_visible():
        page.locator('.pane-switch [data-pane="preview"]').click()
    player = page.locator("#video-preview")
    expect(player).to_be_visible(timeout=20000)
    page.wait_for_function(
        "document.querySelector('#video-preview').readyState >= 1 && document.querySelector('#video-preview').duration >= 5"
    )
    case = f"{locale}/{width}"
    actions = page.locator("#video-output-details .actions")
    record(
        failures,
        actions.get_by_role("button", name=re.compile(r"full.?screen|全螢幕", re.I)).count() == 0,
        case + "/no-video-fullscreen-action",
        actions.inner_text(),
    )
    record(
        failures,
        "nofullscreen" in (player.get_attribute("controlslist") or ""),
        case + "/native-controls-hide-fullscreen",
        player.get_attribute("controlslist"),
    )
    page.locator(".video-play-overlay").click()
    page.wait_for_function(
        "!document.querySelector('#video-preview').paused && document.querySelector('#video-preview').currentTime > 0.05",
        timeout=5000,
    )
    played = player.evaluate("video => video.currentTime")
    bounds = player.bounding_box()
    desktop_chromium = browser.browser_type.name == "chromium" and width > 900
    # Desktop Chromium puts its timeline below the playback buttons.
    point = (
        bounds["x"] + (24 if desktop_chromium else 33),
        bounds["y"] + bounds["height"] - (48 if desktop_chromium else 29),
    )
    (page.touchscreen.tap if width <= 900 else page.mouse.click)(*point)
    page.wait_for_function(
        "document.querySelector('#video-preview').paused && !document.querySelector('#video-preview').ended",
        timeout=2000,
    )
    paused = player.evaluate("video => video.currentTime")
    page.wait_for_timeout(200)
    record(
        failures,
        player.evaluate("video => video.paused") and abs(player.evaluate("video => video.currentTime") - paused) < 0.02,
        case + "/play-pause",
        {"played": played, "paused": paused},
    )
    seek = (bounds["x"] + bounds["width"] * 0.55, bounds["y"] + bounds["height"] - (22 if desktop_chromium else 29))
    (page.touchscreen.tap if width <= 900 else page.mouse.click)(*seek)
    page.wait_for_function("document.querySelector('#video-preview').currentTime > 1", timeout=5000)
    record(
        failures,
        player.evaluate("(video, paused) => video.paused && video.currentTime > paused+1", paused),
        case + "/native-seek",
        player.evaluate("video => video.currentTime"),
    )
    player.press("f")
    page.wait_for_timeout(150)
    record(
        failures,
        not page.evaluate("Boolean(document.fullscreenElement)"),
        case + "/f-keeps-video-in-page",
        "native player",
    )
    print("CHECK", case, flush=True)
    context.close()


def main():
    failures = []
    with tempfile.TemporaryDirectory(prefix="image-gen-playback-") as directory, sync_playwright() as playwright:
        clip = Path(directory) / "playback.mp4"
        make_clip(clip)
        browser = (playwright.webkit if "--webkit" in sys.argv else playwright.chromium).launch()
        for locale in ("en",) if "--core" in sys.argv else ("en", "zh-TW"):
            for width in (390,) if "--core" in sys.argv else (390, 768, 1024):
                check_case(browser, f"http://127.0.0.1:{int(sys.argv[1])}", clip, width, locale, failures)
        browser.close()
    print("FAILURES", len(failures), flush=True)
    return bool(failures)


if __name__ == "__main__":
    sys.exit(main())
