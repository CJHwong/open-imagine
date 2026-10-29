"""Music genres show common choices first and fit their text without search."""

import sys

from playwright.sync_api import expect, sync_playwright


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for width, height in [(1440, 1000), (390, 844)]:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.goto(f"http://127.0.0.1:{int(sys.argv[1])}/?workspace=music")
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
            expect(row).not_to_have_attribute("open", "")
            expect(row.locator("summary .look-pick")).to_have_text("Pop")
            expect(presets.locator(".look-row")).to_have_count(6)
            expect(presets.locator('[data-row="Genre"]')).to_have_count(0)
            row.locator("summary").click()
            expect(row.locator(".chip")).to_have_count(59)
            labels = row.locator(".chip").all_text_contents()
            assert len(set(label.lower() for label in labels)) == len(labels)
            for label in ["Math rock", "Romantic era", "Highlife-inspired", "Bebop", "House"]:
                assert label in labels
            assert labels[:4] == ["Pop", "Hip hop", "R&B", "Country"]
            assert row.locator("h3").all_text_contents() == [
                "Popular",
                "Rock",
                "Electronic",
                "Soul and roots",
                "Jazz and blues",
                "Latin and Caribbean",
                "Classical and historical",
                "Regional inspirations",
            ]
            assert row.locator(".chip").evaluate_all("""chips => chips.every(chip => {
                const style = getComputedStyle(chip);
                const range = document.createRange();
                range.selectNodeContents(chip);
                const expected = range.getBoundingClientRect().width + parseFloat(style.paddingLeft)
                    + parseFloat(style.paddingRight) + parseFloat(style.borderLeftWidth) + parseFloat(style.borderRightWidth);
                return Math.abs(chip.getBoundingClientRect().width - expected) < 2;
            })"""), "Genre pills must fit their text and normal padding"
            assert all(
                chips.evaluate("chips => chips.scrollWidth <= chips.clientWidth")
                for chips in row.locator(".look-chips").all()
            )
            choice = row.get_by_role("button", name="Math rock", exact=True)
            choice.focus()
            page.keyboard.press("Enter")
            expected = "dreamy, Keep my own phrase.\nUse a math rock arrangement with irregular accents and abrupt stops between tightly repeated figures."
            expect(style).to_have_value(expected)
            expect(row.locator(".look-pick")).to_have_text("Math rock")
            expect(row.locator("summary")).to_be_focused()
            row.locator("summary").click()
            expect(row.locator('.chip[aria-pressed="true"]')).to_have_count(1)
            expect(presets.locator(".look-row").first.locator(".look-pick")).to_have_text("Dreamy")
            expect(style).to_have_value(expected)
            row.get_by_role("button", name="House", exact=True).click()
            assert "math rock" not in style.input_value()
            assert style.input_value().startswith("dreamy, Keep my own phrase.")
            saved = style.input_value()
            row.locator("summary").click()
            expect(row.locator(".chip")).to_have_count(59)
            assert not submissions, submissions
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert row.locator(".music-genre-groups").evaluate(
                "groups => groups.clientHeight <= 360 && groups.scrollHeight > groups.clientHeight"
            )
            row.locator(".music-genre-groups").scroll_into_view_if_needed()
            page.screenshot(path=f"/tmp/music-genres-{width}.png")
            page.locator("#music-studio").evaluate("studio => studio.storageQueue")
            page.reload()
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
        "PASS 59 unique genres, common choices first, text-sized pills, no search, keyboard, replacement, persistence and mobile bounds"
    )


if __name__ == "__main__":
    main()
