"""Shared Music form spacing and Look chips, against a fresh CPU-only stub.

uv run --with playwright python tests/e2e/verify_music_styles.py <port>
"""

import sys

from playwright.sync_api import expect, sync_playwright


def verify_descriptions(rows, style):
    descriptions = {}
    for row in rows.all():
        style.fill("My own warm piano")
        for index in range(row.locator(".chip").count()):
            row.locator(":scope > summary, .look-row-toggle").click()
            chip = row.locator(".chip").nth(index)
            label = chip.inner_text()
            chip.click()
            parts = style.input_value().split(", ")
            assert len(parts) == 2 and parts[0] == "My own warm piano"
            sentence = parts[1]
            assert sentence.endswith(".") and 8 <= len(sentence.split()) <= 25, (label, sentence)
            assert "," not in sentence
            expect(row.locator(".look-pick")).to_have_text(label)
            expect(row.locator('.chip[aria-pressed="true"]')).to_have_count(1)
            descriptions[label] = sentence
        row.locator(":scope > summary, .look-row-toggle").click()
        row.locator(".chip").last.click()
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
            descriptions = verify_descriptions(rows, style)
            style.fill("My own warm piano")
            row = rows.first
            row.locator(":scope > summary, .look-row-toggle").click()
            chip = row.locator(".chip").first
            label = chip.inner_text()
            chip.click()
            added = style.input_value()
            assert added.startswith("My own warm piano") and added != "My own warm piano"
            expect(row.locator(".look-pick")).to_have_text(label)
            row.locator(":scope > summary, .look-row-toggle").click()
            row.locator(".chip").first.click()
            expect(style).to_have_value("My own warm piano")
            # Keyboard selection follows the same button behavior as pointer selection.
            row.locator(":scope > summary, .look-row-toggle").click()
            row.locator(".chip").first.focus()
            page.keyboard.press("Enter")
            expect(style).to_have_value(added)
            row.locator(":scope > summary, .look-row-toggle").click()
            row.locator(".chip").first.click()

            # Each preset row permits one choice without changing other rows or custom text.
            for index in range(rows.count()):
                current = rows.nth(index)
                current.locator(":scope > summary, .look-row-toggle").click()
                first = current.locator(".chip").nth(0)
                first.click()
                before = style.input_value().split(", ")
                current.locator(":scope > summary, .look-row-toggle").click()
                second = current.locator(".chip").nth(1)
                second_label = second.inner_text()
                second.click()
                expect(current.locator(".look-pick")).to_have_text(second_label)
                current.locator(":scope > summary, .look-row-toggle").click()
                expect(current.locator('.chip[aria-pressed="true"]')).to_have_count(1)
                expect(current.locator(".chip").nth(0)).to_have_attribute("aria-pressed", "false")
                expect(current.locator(".chip").nth(1)).to_have_attribute("aria-pressed", "true")
                assert len(style.input_value().split(", ")) == len(before)
                assert style.input_value().startswith("My own warm piano")
                current.locator(".chip").nth(1).click()
                expect(current.locator(".look-pick")).to_have_text("none")
                assert len(style.input_value().split(", ")) == len(before) - 1
            expect(style).to_have_value("My own warm piano")
            style.fill("My own warm piano, pop, rock, dreamy")
            expect(row.locator(".look-pick")).to_have_text("Pop")
            row.locator(":scope > summary, .look-row-toggle").click()
            expect(row.locator('.chip[aria-pressed="true"]')).to_have_count(1)
            row.get_by_role("button", name="Rock", exact=True).click()
            expect(style).to_have_value("My own warm piano, dreamy, " + descriptions["Rock"])
            expect(row.locator(".look-pick")).to_have_text("Rock")
            expect(rows.nth(1).locator(".look-pick")).to_have_text("Dreamy")
            style.fill("My own warm piano, " + descriptions["Rock"].upper() + ", POP, dreamy")
            expect(row.locator(".look-pick")).to_have_text("Pop")
            row.locator(":scope > summary, .look-row-toggle").click()
            row.get_by_role("button", name="Rock", exact=True).click()
            expect(style).to_have_value("My own warm piano, dreamy, " + descriptions["Rock"])
            expect(rows.nth(1).locator(".look-pick")).to_have_text("Dreamy")
            maximum = int(style.get_attribute("maxlength"))
            full = "x" * (maximum - len(", pop")) + ", pop"
            style.fill(full)
            row.locator(":scope > summary, .look-row-toggle").click()
            row.get_by_role("button", name="Rock", exact=True).click()
            expect(style).to_have_value(full)
            expect(row.locator(".look-pick")).to_have_text("Pop")
            expect(page.get_by_text("The style is too long to add another preset.", exact=True)).to_be_visible()
            style.fill("My own warm piano")
            row.locator(":scope > summary, .look-row-toggle").click()
            row.locator(".chip").first.click()
            page.locator("#music-studio").evaluate("studio=>studio.storageQueue")
            page.reload()
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
