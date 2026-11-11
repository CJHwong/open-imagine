"""Music genre dropdowns keep common choices first and preserve custom text."""

import sys

from playwright.sync_api import expect, sync_playwright
from style_controls import show_controls, style_menu


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for width, height in [(1440, 1000), (390, 844)]:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.goto(f"http://127.0.0.1:{int(sys.argv[1])}/?workspace=music")
            show_controls(page)
            submissions = []
            page.on(
                "request",
                lambda request, submissions=submissions: (
                    submissions.append(request.url)
                    if request.method == "POST" and request.url.endswith("/operations")
                    else None
                ),
            )
            style = page.locator("#music-style")
            expect(style).to_be_visible()
            style.fill("pop, rock, dreamy, Keep my own phrase.")
            presets = page.locator("#music-style-presets")
            presets.locator("summary").click()
            expect(presets.locator('input[type="search"]')).to_have_count(0)
            expect(presets.locator("#music-genre-count")).to_have_count(0)
            row = page.locator("#music-genre-presets")
            choices = style_menu(page, row).locator('[data-music-genre]:not([data-music-genre=""])')
            expect(row.locator(".look-row-toggle")).to_have_attribute("aria-expanded", "false")
            expect(row.locator(".look-row-toggle .look-pick")).to_have_text("Pop")
            expect(presets.locator(".look-row")).to_have_count(6)
            expect(presets.locator('[data-row="Genre"]')).to_have_count(0)
            row.locator(".look-row-toggle").click()
            expect(choices).to_have_count(59)
            labels = choices.all_text_contents()
            assert len(set(label.lower() for label in labels)) == len(labels)
            for label in ["Math rock", "Romantic era", "Highlife-inspired", "Bebop", "House"]:
                assert label in labels
            assert labels[:4] == ["Pop", "Hip hop", "R&B", "Country"]
            assert style_menu(page, row).locator("h3").all_text_contents() == [
                "Popular",
                "Rock",
                "Electronic",
                "Soul and roots",
                "Jazz and blues",
                "Latin and Caribbean",
                "Classical and historical",
                "Regional inspirations",
            ]
            assert choices.evaluate_all("buttons => buttons.every(button => button.scrollWidth <= button.clientWidth)")
            assert style_menu(page, row).evaluate("menu => menu.scrollWidth <= menu.clientWidth")
            choice = style_menu(page, row).get_by_role("menuitemradio", name="Math rock", exact=True)
            choice.focus()
            page.keyboard.press("Enter")
            expected = "dreamy, Keep my own phrase.\nUse a math rock arrangement with irregular accents and abrupt stops between tightly repeated figures."
            expect(style).to_have_value(expected)
            expect(row.locator(".look-pick")).to_have_text("Math rock")
            expect(row.locator(".look-row-toggle")).to_be_focused()
            row.locator(".look-row-toggle").click()
            expect(style_menu(page, row).locator('[aria-checked="true"]')).to_have_count(1)
            expect(presets.locator(".look-row").first.locator(".look-pick")).to_have_text("Dreamy")
            expect(style).to_have_value(expected)
            style_menu(page, row).get_by_role("menuitemradio", name="House", exact=True).click()
            assert "math rock" not in style.input_value()
            assert style.input_value().startswith("dreamy, Keep my own phrase.")
            saved = style.input_value()
            row.locator(".look-row-toggle").click()
            expect(choices).to_have_count(59)
            assert not submissions, submissions
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert style_menu(page, row).evaluate(
                "menu => menu.clientHeight > 0 && menu.scrollHeight > menu.clientHeight"
            )
            page.keyboard.press("Escape")
            page.locator("#music-studio").evaluate("studio => studio.storageQueue")
            page.reload()
            show_controls(page)
            expect(style).to_have_value(saved)
            presets.locator("summary").click()
            expect(presets.locator("input")).to_have_count(0)
            expect(row.locator(".look-pick")).to_have_text("House")
            style.fill("romantic")
            expect(row.locator(".look-pick")).to_have_text("none")
            expect(presets.locator(".look-row").first.locator(".look-pick")).to_have_text("Romantic")
            page.close()
        browser.close()
    print(
        "PASS 59 unique genres, common choices first, dropdown choices, no search, keyboard, replacement, persistence and mobile bounds"
    )


if __name__ == "__main__":
    main()
