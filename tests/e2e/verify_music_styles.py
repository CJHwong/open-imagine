"""Shared Music form spacing and style dropdowns, against a fresh CPU-only stub.

uv run --with playwright python tests/e2e/verify_music_styles.py <port>
"""

import sys

from playwright.sync_api import expect, sync_playwright
from style_controls import show_controls, style_menu


def verify_descriptions(page, rows, style):
    descriptions = {}
    for row in rows.all():
        style.fill("My own warm piano")
        for index in range(style_menu(page, row).locator('[role="menuitemradio"]').count() - 1):
            row.locator(".look-row-toggle").click()
            option = style_menu(page, row).get_by_role("menuitemradio").nth(index + 1)
            label = option.inner_text()
            option.click()
            parts = style.input_value().split(", ")
            assert len(parts) == 2 and parts[0] == "My own warm piano"
            sentence = parts[1]
            assert sentence.endswith(".") and 8 <= len(sentence.split()) <= 25, (label, sentence)
            assert "," not in sentence
            expect(row.locator(".look-pick")).to_have_text(label)
            expect(style_menu(page, row).locator('[aria-checked="true"]')).to_have_count(1)
            descriptions[label] = sentence
        row.locator(".look-row-toggle").click()
        style_menu(page, row).get_by_role("menuitemradio").first.click()
        expect(style).to_have_value("My own warm piano")
    return descriptions


def main():
    base = f"http://127.0.0.1:{int(sys.argv[1])}"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for width, height in [(1440, 1000), (390, 844)]:
            page = browser.new_page(viewport={"width": width, "height": height})
            errors = []
            page.on("pageerror", lambda error, errors=errors: errors.append(str(error)))
            page.goto(base + "/?workspace=music")
            show_controls(page)
            style = page.locator("#music-style")
            expect(style).to_be_visible()
            assert page.evaluate("""() => {
              const pairs = [
                ['#music-controls', '#image-controls'],
                ['#music-style', '#prompt'],
                ['label[for="music-style"]', 'label[for="prompt"]'],
                ['#music-style', '#video-prompt']
              ];
              const properties=['paddingTop','paddingRight','paddingBottom','paddingLeft',
                'marginTop','marginBottom','borderRadius','fontSize'];
              return pairs.every(([a,b])=>{
                const left=getComputedStyle(document.querySelector(a));
                const right=getComputedStyle(document.querySelector(b));
                return properties.every(property=>left[property]===right[property]);
              });
            }"""), "Music fields must inherit the shared form spacing and typography"
            expect(page.locator("#music-controls .music-advanced-fields")).to_have_count(1)
            look = page.locator('#music-controls details:has(look-rows[data-form="music"])')
            expect(look).to_have_count(1)
            look.locator("summary").click()
            rows = page.locator("#music-genre-presets, #music-style-presets .look-row")
            expect(rows.first).to_be_visible()
            assert rows.count() >= 3
            descriptions = verify_descriptions(page, rows, style)
            style.fill("My own warm piano")
            row = rows.first
            row.locator(".look-row-toggle").click()
            option = style_menu(page, row).get_by_role("menuitemradio").nth(1)
            label = option.inner_text()
            option.click()
            added = style.input_value()
            assert added.startswith("My own warm piano") and added != "My own warm piano"
            expect(row.locator(".look-pick")).to_have_text(label)
            row.locator(".look-row-toggle").click()
            style_menu(page, row).get_by_role("menuitemradio").first.click()
            expect(style).to_have_value("My own warm piano")
            # Keyboard selection follows the same button behavior as pointer selection.
            row.locator(".look-row-toggle").click()
            style_menu(page, row).get_by_role("menuitemradio").nth(1).focus()
            page.keyboard.press("Enter")
            expect(style).to_have_value(added)
            row.locator(".look-row-toggle").click()
            style_menu(page, row).get_by_role("menuitemradio").first.click()

            # Each preset row permits one choice without changing other rows or custom text.
            for index in range(rows.count()):
                current = rows.nth(index)
                current.locator(".look-row-toggle").click()
                first = style_menu(page, current).get_by_role("menuitemradio").nth(1)
                first.click()
                before = style.input_value().split(", ")
                current.locator(".look-row-toggle").click()
                second = style_menu(page, current).get_by_role("menuitemradio").nth(2)
                second_label = second.inner_text()
                second.click()
                expect(current.locator(".look-pick")).to_have_text(second_label)
                current.locator(".look-row-toggle").click()
                expect(style_menu(page, current).locator('[aria-checked="true"]')).to_have_count(1)
                expect(style_menu(page, current).get_by_role("menuitemradio").nth(1)).to_have_attribute(
                    "aria-checked", "false"
                )
                expect(style_menu(page, current).get_by_role("menuitemradio").nth(2)).to_have_attribute(
                    "aria-checked", "true"
                )
                assert len(style.input_value().split(", ")) == len(before)
                assert style.input_value().startswith("My own warm piano")
                style_menu(page, current).get_by_role("menuitemradio").first.click()
                expect(current.locator(".look-pick")).to_have_text("none")
                assert len(style.input_value().split(", ")) == len(before) - 1
            expect(style).to_have_value("My own warm piano")
            style.fill("My own warm piano, pop, rock, dreamy")
            expect(row.locator(".look-pick")).to_have_text("Pop")
            row.locator(".look-row-toggle").click()
            expect(style_menu(page, row).locator('[aria-checked="true"]')).to_have_count(1)
            style_menu(page, row).get_by_role("menuitemradio", name="Rock", exact=True).click()
            expect(style).to_have_value("My own warm piano, dreamy, " + descriptions["Rock"])
            expect(row.locator(".look-pick")).to_have_text("Rock")
            expect(rows.nth(1).locator(".look-pick")).to_have_text("Dreamy")
            style.fill("My own warm piano, " + descriptions["Rock"].upper() + ", POP, dreamy")
            expect(row.locator(".look-pick")).to_have_text("Pop")
            row.locator(".look-row-toggle").click()
            style_menu(page, row).get_by_role("menuitemradio", name="Rock", exact=True).click()
            expect(style).to_have_value("My own warm piano, dreamy, " + descriptions["Rock"])
            expect(rows.nth(1).locator(".look-pick")).to_have_text("Dreamy")
            maximum = int(style.get_attribute("maxlength"))
            full = "x" * (maximum - len(", pop")) + ", pop"
            style.fill(full)
            row.locator(".look-row-toggle").click()
            style_menu(page, row).get_by_role("menuitemradio", name="Rock", exact=True).click()
            expect(style).to_have_value(full)
            expect(row.locator(".look-pick")).to_have_text("Pop")
            expect(page.get_by_text("The style is too long to add another preset.", exact=True)).to_be_visible()
            style.fill("My own warm piano")
            row.locator(".look-row-toggle").click()
            style_menu(page, row).get_by_role("menuitemradio").nth(1).click()
            page.locator("#music-studio").evaluate("studio=>studio.storageQueue")
            page.reload()
            show_controls(page)
            expect(style).to_have_value(added)
            style.fill("Completely rewritten by hand")
            look = page.locator('#music-controls details:has(look-rows[data-form="music"])')
            look.locator("summary").click()
            expect(look.locator(".look-pick.picked")).to_have_count(0)
            page.locator('label[for="music-mode-plan"]').click()
            expect(page.locator("#music-empty-hint")).to_have_text("Write a style and lyrics to compose sheet music.")
            expect(
                page.get_by_text("Make a new performance from the reference composition.", exact=True)
            ).to_have_count(0)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert not errors, errors
            page.close()
        browser.close()
    print(
        "PASS all preset descriptions, single selection, legacy drafts, mixed sentences, length limit, editing, keyboard and persistence at desktop/mobile"
    )


if __name__ == "__main__":
    main()
