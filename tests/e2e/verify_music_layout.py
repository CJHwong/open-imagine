"""Music score engraving and shared preview chrome; fresh stub server, no GPU.

uv run --with playwright python tests/e2e/verify_music_layout.py <port>
"""

import sys

from playwright.sync_api import expect, sync_playwright

SCORE = (
    "X:1\nT:Generated composition\nM:4/4\nL:1/4\nQ:1/4=88\n"
    'V:Vocal clef=treble name="Vocal Melody"\nV:Ins clef=treble name="Instrumental"\nK:C\n'
    + "\n".join('V:Vocal\n"C"CDEF|"Am"GABc|\nV:Ins\nC,2E,2|G,4|' for _ in range(8))
)


def open_composition(page):
    bar = page.locator(".music-output-details:not([hidden])")
    bar.get_by_role("button", name="More actions", exact=True).click()
    bar.get_by_role("menuitem", name="Sheet music and chords", exact=True).click()
    popup = page.get_by_role("dialog", name="Sheet music and chords", exact=True)
    expect(popup).to_be_visible()
    return popup


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
        expect(page.locator(".music-score-popover")).to_have_count(1)
        expect(page.locator(".music-score-popover")).to_be_hidden()
        expect(page.get_by_role("tab", name="Sheet music", exact=True)).to_have_count(0)
        recording = page.locator(".music-song audio")
        recording.evaluate("audio=>{audio.loop=true;return audio.play()}")
        popup = open_composition(page)
        assert recording.evaluate("audio=>!audio.paused"), "Reading the score paused the recording"
        page.keyboard.press("Escape")
        expect(popup).to_be_hidden()
        assert recording.evaluate("audio=>!audio.paused"), "Closing the score paused the recording"
        expect(
            page.locator(".music-output-details:not([hidden])").get_by_role("button", name="More actions", exact=True)
        ).to_be_focused()
        popup = open_composition(page)
        popup.evaluate("""node=>{
          window.scoreClosed = new Promise(resolve=>{
            const closed=event=>{if(event.newState==='closed'){node.removeEventListener('toggle',closed);resolve();}};
            node.addEventListener('toggle',closed);
          });
        }""")
        style_bounds = page.locator("#music-style").bounding_box()
        page.mouse.click(style_bounds["x"] + style_bounds["width"] - 8, style_bounds["y"] + 10)
        expect(popup).to_be_hidden()
        page.evaluate("()=>window.scoreClosed")
        expect(page.locator("#music-style")).to_be_focused()
        popup = open_composition(page)
        expect(page.locator(".music-notation svg").first).to_be_visible(timeout=30000)
        assert page.locator(".music-notation .abcjs-note").count() > 32
        assert "Vocal Melody" in page.locator(".music-notation").inner_text()
        assert "Instrumental" in page.locator(".music-notation").inner_text()
        expect(page.get_by_role("tab", name="Sheet music", exact=True)).to_have_attribute("aria-selected", "true")
        bar = page.locator(".music-output-details:not([hidden])")
        actions = bar.locator(".actions")
        before = actions.bounding_box()
        page.locator(".music-preview-pane").evaluate("node=>node.scrollTop=node.scrollHeight")
        page.locator(".music-notation").evaluate("node=>node.scrollTop=node.scrollHeight")
        notation = page.get_by_role("region", name="Generated sheet music", exact=True)
        expect(page.locator(".music-score-scroll-hint")).to_be_visible()
        expect(notation).to_have_attribute("aria-describedby", "music-score-scroll-0")
        notation.evaluate("node=>node.scrollTop=0")
        notation.hover()
        page.mouse.wheel(0, 240)
        page.wait_for_function("document.querySelector('.music-notation').scrollTop > 0")
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
        # A rendered wide score remains keyboard accessible, too. Zoom its actual
        # engraving rather than substituting a different scrolling element.
        notation.locator("svg").first.evaluate("node=>node.parentElement.style.width='1600px'")
        notation.hover()
        page.mouse.wheel(180, 0)
        page.wait_for_function("document.querySelector('.music-notation').scrollLeft > 0")
        notation.evaluate("node=>node.scrollLeft=0")
        notation.focus()
        page.keyboard.press("ArrowRight")
        assert notation.evaluate("node=>node.scrollLeft>0")
        page.keyboard.press("ArrowLeft")
        assert notation.evaluate("node=>node.scrollLeft===0")
        notation.locator("svg").first.evaluate("node=>node.parentElement.style.width=''")
        assert actions.bounding_box() == before, "Scrolling the score moved the actions"
        expect(bar.locator(".actions > .menu-anchor")).to_have_count(1)
        expect(bar.locator(".actions > .rule")).to_have_count(1)
        expect(bar.locator(".actions > .icon-btn")).to_have_count(2)
        expect(bar.get_by_role("button", name="Music details", exact=True)).to_have_count(0)
        page.get_by_role("button", name="Close sheet music", exact=True).click()
        expect(popup).to_be_hidden()
        expect(bar.get_by_role("button", name="More actions", exact=True)).to_be_focused()
        bar.get_by_role("button", name="More actions", exact=True).click()
        expect(bar.get_by_role("menuitem", name="Generate artwork", exact=True)).to_be_visible()
        expect(bar.get_by_role("menuitem", name="Send to Video", exact=True)).to_be_visible()
        page.keyboard.press("Escape")
        expect(bar.get_by_role("link", name="Download WAV")).to_be_visible()
        assert actions.bounding_box()["y"] < page.locator(".music-gallery").bounding_box()["y"]
        bar.locator(".prompt-line").click()
        sheet = page.get_by_role("region", name="Music details", exact=True)
        expect(sheet).to_be_visible()
        expect(sheet.locator("dd")).to_contain_text(["YuE2", "48 kHz", "Warm piano", "A melody"])
        expect(sheet.locator('dt:text-is("Model") + dd')).to_have_text("YuE2")
        expect(bar.locator(".facts span").first).to_have_text("YuE2")
        assert page.locator("#music-studio gallery-browser").evaluate(
            "node=>node.items.every(item=>item.model==='YuE2')"
        )
        page.keyboard.press("Escape")
        expect(sheet).to_be_hidden()
        expect(bar.locator(".prompt-line")).to_be_focused()
        bar.locator(".prompt-line").focus()
        page.keyboard.press("Enter")
        expect(sheet).to_be_visible()
        page.get_by_role("button", name="Close music details").click()
        popup = open_composition(page)
        page.get_by_role("tab", name="Chords", exact=True).click()
        page.set_viewport_size({"width": 1100, "height": 800})
        page.get_by_role("tab", name="Chords", exact=True).focus()
        page.keyboard.press("ArrowLeft")
        expect(page.locator(".music-score-scroll-hint")).to_be_visible()
        page.set_viewport_size({"width": 1280, "height": 800})
        expect(page.get_by_role("tab", name="Sheet music", exact=True)).to_be_focused()
        page.locator(".music-score-source summary").click()
        expect(page.locator(".music-score-source pre")).to_have_text(SCORE)
        with page.expect_download() as download:
            page.get_by_role("link", name="Download ABC").click()
        assert download.value.path().read_text() == SCORE
        page.get_by_role("button", name="Close sheet music", exact=True).click()
        expect(popup).to_be_hidden()
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(400)
        bounds = actions.bounding_box()
        assert bounds["x"] >= 0 and bounds["x"] + bounds["width"] <= 390
        assert bounds["y"] + bounds["height"] < 774, "Mobile footer obscures music actions"
        assert page.locator("#music-studio").evaluate("node=>node.scrollWidth<=node.clientWidth")
        # Native mobile touch scrolling reaches the rest of the real long score.
        mobile_context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        mobile = mobile_context.new_page()
        mobile.route("**/operations/*/metadata", metadata)
        mobile.goto(base + "/?workspace=music")
        mobile.locator("#music-style").fill("Piano")
        mobile.locator("#music-lyrics").fill("A long melody")
        mobile.locator("#music-generate").click()
        expect(mobile.locator(".music-song")).to_have_count(1)
        mobile_popup = open_composition(mobile)
        mobile_score = mobile.get_by_role("region", name="Generated sheet music", exact=True)
        expect(mobile_score.locator("svg").first).to_be_visible(timeout=30000)
        expect(mobile.locator(".music-score-scroll-hint")).to_be_visible()
        assert mobile_score.evaluate("n=>n.scrollHeight>n.clientHeight")
        rect = mobile_score.bounding_box()
        client = mobile_context.new_cdp_session(mobile)
        x, y = rect["x"] + rect["width"] / 2, rect["y"] + rect["height"] - 20
        client.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x, "y": y}]})
        for step in range(1, 9):
            client.send(
                "Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": x, "y": y - step * 24}]}
            )
        client.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
        mobile.wait_for_function("document.querySelector('.music-notation').scrollTop>0")
        popup_bounds = mobile_popup.bounding_box()
        assert popup_bounds["x"] >= 0 and popup_bounds["x"] + popup_bounds["width"] <= 390
        assert popup_bounds["y"] >= 0 and popup_bounds["y"] + popup_bounds["height"] <= 844
        mobile_context.close()
        # Opening a score never carries it to a newly selected recording.
        page.set_viewport_size({"width": 1280, "height": 800})
        page.locator("#music-lyrics").fill("[Verse]\nAnother morning melody")
        page.locator("#music-generate").click()
        expect(page.locator(".music-song")).to_have_count(2)
        selected_audio = page.locator(".music-song:not([hidden]) audio").element_handle()
        selected_audio.evaluate("audio=>{audio.loop=true;return audio.play()}")
        popup = open_composition(page)
        assert selected_audio.evaluate("audio=>!audio.paused")
        page.get_by_role("button", name="Select song 1", exact=True).click()
        assert selected_audio.evaluate("audio=>!audio.paused"), "Selection paused background playback"
        expect(page.locator(".music-score-popover:popover-open")).to_have_count(0)
        expect(page.locator(".music-song:not([hidden])")).to_have_attribute(
            "data-song-id", page.locator(".music-song").last.get_attribute("data-song-id")
        )
        # Losing the notation CDN preserves the full score and the output actions.
        fallback = browser.new_page()
        fallback.route("**/abcjs@*/**", lambda route: route.abort())
        fallback.route("**/operations/*/metadata", metadata)
        fallback.goto(base + "/?workspace=music")
        fallback.locator("#music-style").fill("Piano")
        fallback.locator("#music-lyrics").fill("Morning melody")
        fallback.locator("#music-generate").click()
        expect(fallback.locator(".music-score-popover")).to_have_count(1)
        expect(fallback.locator(".music-score-popover")).to_be_hidden()
        open_composition(fallback)
        expect(fallback.locator(".music-notation-status")).to_contain_text("Sheet music unavailable", timeout=30000)
        fallback.locator(".music-score-source summary").click()
        expect(fallback.locator(".music-score-source pre")).to_have_text(SCORE)
        fallback.get_by_role("button", name="Close sheet music", exact=True).click()
        fallback.get_by_role("button", name="More actions", exact=True).click()
        expect(fallback.get_by_role("menuitem", name="Generate artwork", exact=True)).to_be_visible()
        assert errors == [], errors
        browser.close()
    print(
        "PASS Music layout: full two-voice notation, fixed actions, metadata sheet, focus, ABC export, mobile and CDN fallback."
    )


if __name__ == "__main__":
    main()
