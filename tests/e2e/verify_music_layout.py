"""Music score editor and shared preview chrome; fresh stub server, no GPU.

uv run --with playwright python tests/e2e/verify_music_layout.py <port>
"""

import sys

from playwright.sync_api import expect, sync_playwright

SCORE = (
    "X:1\nT:Generated composition\nM:4/4\nL:1/4\nQ:1/4=88\n"
    'V:Vocal clef=treble name="Vocal Melody"\nV:Ins clef=treble name="Instrumental"\nK:C\n'
    + "\n".join('V:Vocal\n"C"CDEF|"Am"GABc|\nV:Ins\nC,2E,2|G,4|' for _ in range(24))
)


def open_editor(page):
    bar = page.locator(".music-output-details:not([hidden])")
    bar.get_by_role("button", name="More actions", exact=True).click()
    bar.get_by_role("menuitem", name="Use this score", exact=True).click()
    page.locator("#music-abc-edit").click()
    editor = page.get_by_role("dialog", name="ABC score", exact=True)
    expect(editor).to_be_visible()
    return editor


def main():
    base = f"http://127.0.0.1:{int(sys.argv[1])}"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        def metadata(route):
            answer = route.fetch()
            route.fulfill(response=answer, json={**answer.json(), "score": SCORE})

        page.route("**/operations/*/metadata", metadata)
        page.goto(base + "/?workspace=music")
        expect(page.locator("#music-instrumental")).to_have_count(0)
        expect(page.locator("#music-mode-plan")).to_be_enabled()
        expect(page.locator(".music-reference-fields")).to_be_visible()
        expect(page.locator("#music-controls .music-advanced-fields")).to_have_count(1)
        assert not page.locator(".music-advanced-fields").evaluate("node=>node.open")
        page.locator("#music-style").fill("Warm piano pop, two voices")
        page.locator("#music-lyrics").fill("[Verse]\nA melody for the morning")
        page.locator("#music-generate").click()
        expect(page.locator(".music-song audio")).to_have_count(1)
        expect(page.get_by_role("dialog", name="ABC score", exact=True)).to_be_hidden()
        recording = page.locator(".music-song audio")
        recording.evaluate("audio=>{audio.loop=true;return audio.play();}")
        editor = open_editor(page)
        assert recording.evaluate("audio=>!audio.paused"), "Opening the editor paused the recording"
        assert page.evaluate("document.activeElement?.id") == "music-abc", "The editor did not focus the text"
        expect(page.locator("#music-abc")).to_have_value(SCORE)
        page.keyboard.press("Escape")
        expect(editor).to_be_hidden()
        page.wait_for_function("() => document.activeElement?.id === 'music-abc-edit'", timeout=2000)
        assert recording.evaluate("audio=>!audio.paused"), "Closing the editor paused the recording"
        # The panel shows the score read only, and the editor engravings both voices.
        expect(page.locator("#music-abc-preview")).to_have_text(SCORE)
        editor = open_editor(page)
        expect(page.locator("#music-abc-notation svg").first).to_be_visible(timeout=30000)
        facts = page.locator("#music-abc-facts")
        expect(facts).to_be_visible()
        # Three labelled columns: each name keeps its own value when the line is copied.
        expect(facts.locator("dt")).to_have_text(["Key", "Meter", "Tempo"])
        expect(facts.locator("dd")).to_have_text(["C", "4/4", "88 BPM"])
        assert page.locator("#music-abc-notation .abcjs-note").count() > 32
        assert "Vocal Melody" in page.locator("#music-abc-notation").inner_text()
        assert "Instrumental" in page.locator("#music-abc-notation").inner_text()
        assert "Am" in page.locator("#music-abc-notation").inner_text()
        notation = page.get_by_role("region", name="Score preview", exact=True)
        notation.evaluate("node=>node.scrollTop=0")
        notation.hover()
        page.mouse.wheel(0, 240)
        page.wait_for_function("document.querySelector('#music-abc-notation').scrollTop > 0")
        # The hint promises arrow keys once the score is clicked; a click focuses it.
        notation.click()
        assert notation.evaluate("node=>node === document.activeElement")
        notation.evaluate("node=>node.scrollTop=0")
        page.keyboard.press("ArrowDown")
        page.wait_for_function("document.querySelector('#music-abc-notation').scrollTop > 0")
        notation.evaluate("node=>node.scrollTop=0")
        notation.focus()
        page.keyboard.press("PageDown")
        page.wait_for_timeout(300)
        assert notation.evaluate("node=>node.scrollTop>0"), str(
            notation.evaluate(
                "node=>({height:node.clientHeight,total:node.scrollHeight,focused:document.activeElement===node})"
            )
        )
        page.keyboard.press("End")
        assert notation.evaluate("node=>node.scrollTop+node.clientHeight>=node.scrollHeight-1")
        page.keyboard.press("Home")
        assert notation.evaluate("node=>node.scrollTop===0")
        notation.locator("svg").first.evaluate("node=>node.parentElement.style.width='1600px'")
        notation.hover()
        page.mouse.wheel(180, 0)
        page.wait_for_function("document.querySelector('#music-abc-notation').scrollLeft > 0")
        notation.evaluate("node=>node.scrollLeft=0")
        notation.focus()
        page.keyboard.press("ArrowRight")
        assert notation.evaluate("node=>node.scrollLeft>0")
        page.keyboard.press("ArrowLeft")
        assert notation.evaluate("node=>node.scrollLeft===0")
        notation.locator("svg").first.evaluate("node=>node.parentElement.style.width=''")
        page.locator("#music-abc-close").click()
        expect(editor).to_be_hidden()
        page.wait_for_function("() => document.activeElement?.id === 'music-abc-edit'", timeout=2000)
        # The details sheet owns the source, its download and the metadata.
        bar = page.locator(".music-output-details:not([hidden])")
        expect(bar.locator(".actions > .menu-anchor")).to_have_count(1)
        expect(bar.locator(".actions > .rule")).to_have_count(1)
        expect(bar.locator(".actions > .icon-btn")).to_have_count(2)
        expect(bar.get_by_role("link", name="Download WAV")).to_be_visible()
        assert bar.locator(".actions").bounding_box()["y"] < page.locator(".music-gallery").bounding_box()["y"]
        bar.locator(".prompt-line").click()
        sheet = page.get_by_role("dialog", name="Music details", exact=True)
        expect(sheet).to_be_visible()
        expect(sheet.locator("dd")).to_contain_text(["YuE2", "48 kHz", "Warm piano"])
        # The words start folded, so the sheet stays short until someone asks.
        lyrics = sheet.locator("details.music-details-lyrics")
        expect(lyrics).not_to_have_attribute("open", "")
        lyrics.locator("summary").click()
        expect(lyrics.locator("p")).to_have_text("[Verse]\nA melody for the morning")
        expect(sheet.locator('dt:text-is("Model") + dd')).to_have_text("YuE2")
        expect(bar.locator(".facts span").first).to_have_text("YuE2")
        assert page.locator("#music-studio gallery-browser").evaluate(
            "node=>node.items.every(item=>item.model==='YuE2')"
        )
        # Both readings start folded; the sheet engraves when it is opened.
        score_fold = sheet.locator("details.music-details-sheet")
        expect(score_fold).not_to_have_attribute("open", "")
        score_fold.locator("summary").click()
        expect(score_fold.locator(".music-details-notation svg").first).to_be_visible(timeout=30000)
        sheet.locator("details summary", has_text="ABC source").click()
        expect(sheet.locator("details pre")).to_have_text(SCORE)
        with page.expect_download() as download:
            sheet.get_by_role("link", name="Download ABC").click()
        assert download.value.path().read_text() == SCORE
        page.get_by_role("button", name="Close music details").click()
        expect(sheet).to_be_hidden()
        # A mobile context with touch scrolls the editor's sheet and keeps the dialog inside.
        mobile_context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        mobile = mobile_context.new_page()
        mobile.route("**/operations/*/metadata", metadata)
        mobile.goto(base + "/?workspace=music")
        mobile.locator("#music-style").fill("Piano")
        mobile.locator("#music-lyrics").fill("A long melody")
        mobile.locator("#music-generate").click()
        expect(mobile.locator(".music-song")).to_have_count(1)
        editor = open_editor(mobile)
        mobile.wait_for_timeout(400)
        box = mobile.evaluate("""() => {
          const dialog = document.querySelector('#music-abc-dialog');
          const text = document.querySelector('#music-abc').getBoundingClientRect();
          const sheet = document.querySelector('#music-abc-notation').getBoundingClientRect();
          const frame = dialog.getBoundingClientRect();
          return {overflow: dialog.scrollWidth - dialog.clientWidth,
                  inside: frame.left >= 0 && frame.right <= 390 && frame.top >= 0 && frame.bottom <= 844,
                  stacked: sheet.top >= text.bottom - 2};
        }""")
        assert box["overflow"] <= 0 and box["inside"] and box["stacked"], box
        mobile_notation = mobile.get_by_role("region", name="Score preview", exact=True)
        mobile_notation.scroll_into_view_if_needed()
        client = mobile_context.new_cdp_session(mobile)
        rect = mobile_notation.bounding_box()
        x, y = rect["x"] + rect["width"] / 2, rect["y"] + rect["height"] - 20
        client.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x, "y": y}]})
        for step in range(1, 9):
            client.send(
                "Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": x, "y": y - step * 24}]}
            )
        client.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
        mobile.wait_for_function("document.querySelector('#music-abc-notation').scrollTop>0")
        mobile.locator("#music-abc-close").click()
        expect(editor).to_be_hidden()
        mobile_context.close()
        # Losing the engraver keeps the text editable and says why the sheet is empty.
        fallback = browser.new_page(viewport={"width": 1280, "height": 900})
        fallback_errors = []
        fallback.on("pageerror", lambda error: fallback_errors.append(str(error)))
        fallback.route("**/abcjs@*/**", lambda route: route.abort())
        fallback.route("**/operations/*/metadata", metadata)
        fallback.goto(base + "/?workspace=music")
        fallback.locator("#music-style").fill("Piano")
        fallback.locator("#music-lyrics").fill("Morning melody")
        fallback.locator("#music-generate").click()
        expect(fallback.locator(".music-song")).to_have_count(1)
        open_editor(fallback)
        expect(fallback.locator("#music-abc-status")).to_contain_text("could not be engraved", timeout=30000)
        expect(fallback.locator("#music-abc")).to_have_value(SCORE)
        fallback.locator("#music-abc-close").click()
        assert fallback_errors == [], fallback_errors
        assert errors == [], errors
        browser.close()
    print(
        "PASS Music layout: edit entry, live two-voice sheet, scrolling, focus, details source and "
        "download, mobile dialog and CDN fallback."
    )


if __name__ == "__main__":
    main()
