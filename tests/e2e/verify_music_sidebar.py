"""Music section tags preserve lyrics and preset summaries fit the sidebar."""

import sys

from playwright.sync_api import expect, sync_playwright


def main():
    base = f"http://127.0.0.1:{int(sys.argv[1])}"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for width, height in [(1440, 1000), (390, 844)]:
            page = browser.new_page(viewport={"width": width, "height": height})
            posts = []
            page.on(
                "request",
                lambda request, posts=posts: (
                    posts.append(request.url)
                    if request.method == "POST"
                    and (request.url.endswith("/operations") or request.url.endswith("/generate"))
                    else None
                ),
            )
            page.goto(base + "/?workspace=music")
            lyrics = page.locator("#music-lyrics")
            expect(lyrics).to_be_visible()
            page.locator(".music-tag-guide summary").click()
            chorus = page.get_by_role("button", name="[Chorus]", exact=True)
            expect(chorus).to_have_attribute("type", "button")
            original = "First line\nSecond line"
            lyrics.fill(original)
            lyrics.evaluate("input => input.setSelectionRange(5, 5)")
            chorus.click()
            insertion = "\n[Chorus]\n"
            expected = original[:5] + insertion + original[5:]
            expect(lyrics).to_have_value(expected)
            assert lyrics.evaluate("input => input.selectionStart") == 5 + len(insertion)
            assert lyrics.evaluate("input => input === document.activeElement")
            # Selected lyrics remain intact when a section is inserted before them.
            lyrics.fill("Before chosen words after")
            lyrics.evaluate("input => input.setSelectionRange(7, 19)")
            page.get_by_role("button", name="[Verse]", exact=True).focus()
            page.keyboard.press("Enter")
            expect(lyrics).to_have_value("Before \n[Verse]\nchosen words after")
            lyrics.fill("")
            tags = ["[Intro]", "[Verse]", "[Pre-Chorus]", "[Chorus]", "[Bridge]", "[Instrumental]", "[Outro]"]
            for tag in tags:
                page.get_by_role("button", name=tag, exact=True).click()
            saved = "\n".join(tags) + "\n"
            expect(lyrics).to_have_value(saved)
            page.locator("#music-studio").evaluate("studio => studio.storageQueue")
            page.reload()
            expect(lyrics).to_have_value(saved)
            page.locator(".music-tag-guide summary").click()
            maximum = int(lyrics.get_attribute("maxlength"))
            full = "x" * maximum
            lyrics.fill(full)
            page.get_by_role("button", name="[Outro]", exact=True).click()
            expect(lyrics).to_have_value(full)
            expect(page.get_by_text("The lyrics are too long to add a section tag.", exact=True)).to_be_visible()
            lyrics.fill(saved)
            style = page.locator("#music-style")
            style.fill("pop, warm, piano, female vocals, mid-tempo, modern production, english lyrics")
            presets = page.locator("#music-style-presets")
            summary = presets.locator("summary")
            expect(summary.locator("look-values")).to_have_text("6 presets")
            label = summary.locator(".music-style-label")
            expect(label).to_have_text("Style presets")
            assert label.evaluate(
                "label => label.getBoundingClientRect().height <= parseFloat(getComputedStyle(label).fontSize) * 1.7"
            )
            assert summary.evaluate("summary => summary.scrollWidth <= summary.clientWidth")
            summary.click()
            expect(presets.locator(".look-pick.picked")).to_have_count(6)
            style.fill("Keep the pulse, leave space.")
            rows = presets.locator(".look-row")
            genre = page.locator("#music-genre-presets")
            genre.locator("summary").click()
            genre.get_by_role("button", name="Pop", exact=True).click()
            rows.nth(0).locator(".look-row-toggle").click()
            rows.nth(0).get_by_role("button", name="Warm", exact=True).click()
            expanded = style.input_value()
            assert expanded.startswith("Keep the pulse, leave space.\n")
            assert ".," not in expanded and ". ," not in expanded and expanded.count("\n") == 2
            expect(genre.locator(".look-pick")).to_have_text("Pop")
            expect(rows.nth(0).locator(".look-pick")).to_have_text("Warm")
            page.locator("#music-studio").evaluate("studio => studio.storageQueue")
            page.reload()
            expect(style).to_have_value(expanded)
            expect(page.locator("#music-style-presets summary look-values")).to_have_text("Warm")
            assert posts == [], posts
            page.close()
        browser.close()
    print(
        "PASS tag caret insertion, selected-text preservation, keyboard, length limits, persistence, compact preset summary and sentence separators"
    )


if __name__ == "__main__":
    main()
