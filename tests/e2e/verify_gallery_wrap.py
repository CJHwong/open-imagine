"""Arrow keys wrap completed and pending results in every workspace. CPU stub only."""

import sys

from playwright.sync_api import expect, sync_playwright
from voice_helpers import choose_voice_profile, create_voice_clips

BASE = "http://127.0.0.1:" + sys.argv[1]


def check_wrap(page, selector):
    tiles = page.locator(selector)
    assert tiles.count() >= 2
    first, last = tiles.first, tiles.last
    first.click()
    first.press("ArrowLeft")
    expect(last).to_have_attribute("aria-pressed", "true")
    last.press("ArrowRight")
    expect(first).to_have_attribute("aria-pressed", "true")
    expect(first.locator("svg.mark")).to_have_count(1)
    first.press("ArrowRight")
    expect(tiles.nth(1)).to_have_attribute("aria-pressed", "true")
    assert page.evaluate("document.activeElement.matches('.frame.selected')")


def main():
    with sync_playwright() as tool:
        browser = tool.chromium.launch()
        for workspace in sys.argv[2:] or ("image", "video", "voice", "music"):
            context = browser.new_context(viewport={"width": 1600, "height": 1000})
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error, errors=errors: errors.append(str(error)))
            if workspace == "voice":
                context.request.post(BASE + "/api/v1/voice/backend", data={"backend": "auk_base"})
            page.goto(BASE + "/?lang=en&workspace=" + workspace)
            if workspace == "image":
                field, button, selector = "#prompt", "#go", "#strip .frame"
            elif workspace == "video":
                field, button, selector = "#video-prompt", "#video-generate", "#video-gallery .frame"
            elif workspace == "voice":
                field, button, selector = "#voice-text", "#voice-generate", ".voice-clips .frame"
            else:
                field, button, selector = "#music-style", "#music-generate", ".music-strip .frame"
                page.locator("#music-lyrics").fill("A little song for the morning.")
            if workspace == "voice":
                create_voice_clips(page, ["A short first sentence.", "A short second sentence."])
            else:
                for number in (1, 2):
                    page.locator(field).fill(f"A blue teapot beside a red cup, variation {number}.")
                    page.locator(button).click()
                    expect(page.locator(selector)).to_have_count(number, timeout=30000)
                    page.locator(field).fill("Ready for another synthetic gallery result.")
                    expect(page.locator(button)).to_be_enabled(timeout=30000)
            check_wrap(page, selector)
            if workspace == "voice":
                choose_voice_profile(page)
            held = []
            route_pattern = (
                "**/generate"
                if workspace == "image"
                else ("**/video/generate" if workspace == "video" else f"**/{workspace}/operations")
            )
            page.route(route_pattern, lambda route, request, held=held: held.append(route))
            page.locator(field).fill("A third synthetic gallery test.")
            with page.expect_request(route_pattern):
                page.locator(button).click()
            expect(page.locator(selector)).to_have_count(3)
            check_wrap(page, selector)
            if workspace == "voice":
                widths = page.locator(selector).evaluate_all(
                    "nodes => nodes.map(node => node.getBoundingClientRect().width)"
                )
                assert max(widths) - min(widths) < 1, widths
            assert held, workspace
            held[0].abort()
            assert not errors, errors
            print(
                f"PASS {workspace}: both ends wrap, pending result is selectable and circled, keyboard focus follows",
                flush=True,
            )
            context.close()
        browser.close()


if __name__ == "__main__":
    main()
