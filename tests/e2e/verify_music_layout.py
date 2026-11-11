"""Music controls stay balanced and reachable across phone, fold and desktop widths.

Run against a fresh all-backend stub. Add --webkit for WebKit.
"""

import json
import sys

from playwright.sync_api import expect, sync_playwright
from style_controls import show_controls, style_menu


def record(failures, condition, case, detail):
    if condition:
        return
    failures.append({"case": case, "detail": detail})
    print("FAIL", json.dumps(failures[-1]), flush=True)


def check_case(browser, base, locale, width, height, failures):
    context = browser.new_context(viewport={"width": width, "height": height})
    context.add_init_script("localStorage.setItem('studio-keep','off');localStorage.setItem('studio-autoplay','off')")
    page = context.new_page()
    page.goto(base + "/?workspace=music&lang=" + locale)
    show_controls(page)
    style = page.locator("#music-style")
    expect(style).to_be_visible()
    case = f"{locale}/{width}x{height}"
    presets = page.locator("#music-style-presets")
    record(
        failures,
        presets.get_attribute("open") is not None,
        case + "/style-default-expanded",
        presets.get_attribute("open"),
    )
    record(failures, presets.locator("#music-genre-presets").count() == 1, case + "/genre-inside-style", "Genre parent")
    modes = page.locator("#music-controls .modes label").evaluate_all(
        "labels => labels.map(label => label.getBoundingClientRect().width)"
    )
    record(failures, max(modes) - min(modes) <= 1, case + "/equal-workflow-widths", modes)
    tag_summary = page.locator(".music-tag-guide > summary")
    tag_summary.click()
    tags = page.locator(".music-lyrics-tags li").evaluate_all("""rows => rows.map(row => {
        const button = row.querySelector('button').getBoundingClientRect();
        const text = [...row.childNodes].find(node => node.nodeType === Node.TEXT_NODE && node.textContent.trim());
        const range = document.createRange(); range.selectNodeContents(text);
        return {width: button.width, description: range.getBoundingClientRect().left};
    })""")
    record(
        failures,
        max(tag["width"] for tag in tags) - min(tag["width"] for tag in tags) <= 1,
        case + "/equal-section-tag-widths",
        tags,
    )
    record(
        failures,
        max(tag["description"] for tag in tags) - min(tag["description"] for tag in tags) <= 1,
        case + "/aligned-tag-descriptions",
        tags,
    )
    tag = page.locator('[data-music-section="[Verse]"]')
    tag.scroll_into_view_if_needed()
    bounds = tag.bounding_box()
    record(failures, bounds["height"] >= 32, case + "/tag-hit-height", bounds)
    tag.click()
    expect(page.locator("#music-lyrics")).to_have_value("[Verse]\n")
    if presets.get_attribute("open") is None:
        presets.locator(":scope > summary").click()
    columns = presets.locator(".look-row-toggle").evaluate_all("""rows => rows.map(row => {
        const label = row.querySelector('.label').getBoundingClientRect();
        const value = row.querySelector('.look-pick').getBoundingClientRect();
        return {label: label.width, value: value.width, width: row.getBoundingClientRect().width};
    })""")
    record(
        failures,
        len(columns) == 7 and all(abs(row["label"] - row["value"]) <= 1 for row in columns),
        case + "/balanced-style-columns",
        columns,
    )
    presets.locator(":scope > summary").click()
    expect(presets.locator("#music-genre-toggle")).to_be_hidden()
    presets.locator(":scope > summary").click()
    genre = page.locator("#music-genre-presets")
    genre.locator(".look-row-toggle").click()
    menu = style_menu(page, genre)
    menu.locator('[data-music-genre]:not([data-music-genre=""])').first.click()
    expect(style).not_to_have_value("")
    page.locator("#music-lyrics").fill("[Verse]\nA quiet song for the morning.")
    page.locator("#music-generate").click()
    play = page.locator(".music-song:not([hidden]) .music-play").first
    expect(play).to_be_visible(timeout=30000)
    expect(play).to_be_enabled(timeout=30000)
    player = play.locator("xpath=ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' music-player ')]")
    center = player.bounding_box()
    button = play.bounding_box()
    delta = button["x"] + button["width"] / 2 - center["x"] - center["width"] / 2
    record(failures, abs(delta) <= 1, case + "/play-centered", delta)
    record(failures, not play.locator(".control-label:visible").count(), case + "/obvious-play-icon", play.inner_text())
    controls = player.locator("button:visible").all()
    boxes = [control.bounding_box() for control in controls]
    record(failures, all(box["width"] >= 44 and box["height"] >= 44 for box in boxes), case + "/player-targets", boxes)
    record(
        failures,
        all(
            box["x"] >= center["x"] - 1 and box["x"] + box["width"] <= center["x"] + center["width"] + 1
            for box in boxes
        ),
        case + "/player-contained",
        boxes,
    )
    overlaps = [
        (left, right)
        for index, left in enumerate(boxes)
        for right in boxes[index + 1 :]
        if min(left["x"] + left["width"], right["x"] + right["width"]) > max(left["x"], right["x"]) + 1
        and min(left["y"] + left["height"], right["y"] + right["height"]) > max(left["y"], right["y"]) + 1
    ]
    record(failures, not overlaps, case + "/player-no-overlap", overlaps)
    record(
        failures,
        all(control.get_attribute("aria-label") for control in controls),
        case + "/player-accessible-names",
        [control.get_attribute("aria-label") for control in controls],
    )
    player.evaluate("""player => {
        window.musicPlayback = [];
        player.closest('.music-song').querySelector('audio').addEventListener('play', () => {
            musicPlayback.push(player.querySelector('.music-play').getAttribute('aria-pressed'));
        });
    }""")
    record(
        failures,
        all(box["y"] >= 0 and box["y"] + box["height"] <= height for box in boxes),
        case + "/player-reachable",
        boxes,
    )
    play.click()
    page.wait_for_function("musicPlayback.length > 0")
    record(
        failures,
        page.evaluate("musicPlayback.includes('true')"),
        case + "/play-feedback",
        page.evaluate("musicPlayback"),
    )
    expect(play).to_have_attribute("aria-pressed", "false", timeout=10000)
    lyrics = player.locator(".music-lyrics-toggle")
    before = lyrics.get_attribute("aria-pressed")
    lyrics.click()
    expect(lyrics).to_have_attribute("aria-pressed", "false" if before == "true" else "true")
    record(
        failures, page.evaluate("document.documentElement.scrollWidth <= innerWidth"), case + "/no-page-overflow", width
    )
    if "--screenshots" in sys.argv and locale == "en" and width in (390, 1440):
        page.screenshot(path=f"/tmp/image-gen-music-layout-{width}.png")
    print("CHECK", case, flush=True)
    context.close()


def main():
    failures = []
    widths = [int(value) for value in sys.argv[2:] if value.isdecimal()] or [280, 390, 600, 768, 1024, 1440]
    with sync_playwright() as playwright:
        engine = playwright.webkit if "--webkit" in sys.argv else playwright.chromium
        browser = engine.launch()
        for locale in ("en", "zh-TW"):
            for width in widths:
                check_case(
                    browser,
                    f"http://127.0.0.1:{int(sys.argv[1])}",
                    locale,
                    width,
                    1000 if width > 900 else 882,
                    failures,
                )
            for fold_width in (600, 768):
                if fold_width in widths:
                    check_case(browser, f"http://127.0.0.1:{int(sys.argv[1])}", locale, fold_width, 440, failures)
        browser.close()
    print("FAILURES", len(failures), flush=True)
    return bool(failures)


if __name__ == "__main__":
    sys.exit(main())
