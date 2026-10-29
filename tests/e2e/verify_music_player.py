"""Custom music transport against a real browser-decoded WAV; stub only, no GPU.

uv run --with playwright python tests/e2e/verify_music_player.py <port>
"""

import io
import sys
import wave

from playwright.sync_api import expect, sync_playwright


def main():
    base = f"http://127.0.0.1:{int(sys.argv[1])}"
    fixture = io.BytesIO()
    with wave.open(fixture, "wb") as wav:
        wav.setparams((1, 2, 24000, 480000, "NONE", "not compressed"))
        wav.writeframes(bytes(960000))
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route(
            "**/operations/*/result", lambda route: route.fulfill(content_type="audio/wav", body=fixture.getvalue())
        )
        page.goto(base + "/?workspace=music")
        page.locator("#music-style").fill("Warm piano instrumental")
        page.locator("#music-generate").click()
        expect(page.locator(".music-song")).to_have_count(1)
        current = page.locator(".music-song:not([hidden])")
        audio = current.locator("audio")
        seek = current.get_by_role("slider", name="Playback position", exact=True)
        play = current.get_by_role("button", name="Play", exact=True)
        back = current.get_by_role("button", name="Back 5 seconds", exact=True)
        forward = current.get_by_role("button", name="Forward 5 seconds", exact=True)
        expect(audio).to_be_hidden()
        assert audio.evaluate("audio=>!audio.controls")
        expect(page.locator(".music-waveform, .gallery-wave")).to_have_count(0)
        expect(play).to_be_enabled()
        assert audio.evaluate("audio=>audio.duration") == 20
        expect(current.locator(".music-time-elapsed")).to_have_text("0:00")
        expect(current.locator(".music-time-remaining")).to_have_text("\u22120:20")
        forward.click()
        assert audio.evaluate("audio=>audio.currentTime") == 5
        back.click()
        back.click()
        assert audio.evaluate("audio=>audio.currentTime") == 0
        seek.fill("18")
        forward.click()
        assert audio.evaluate("audio=>audio.currentTime") == 20
        back.click()
        assert audio.evaluate("audio=>audio.currentTime") == 15
        seek.focus()
        seek.press("Home")
        assert audio.evaluate("audio=>audio.currentTime") == 0
        seek.press("ArrowRight")
        assert abs(audio.evaluate("audio=>audio.currentTime") - 0.1) < 0.01
        seek.press("End")
        assert audio.evaluate("audio=>audio.currentTime") == 20
        seek.fill("3")
        play.click()
        expect(current.get_by_role("button", name="Pause", exact=True)).to_be_visible()
        expect(current).to_have_class("music-song is-playing")
        # Renaming must update chrome without replacing the playing media node.
        audio.evaluate("audio=>{window.playerAudio=audio}")
        current.locator(".music-title-button").click()
        title = current.get_by_role("textbox", name="Song title", exact=True)
        title.fill("Quiet Rotation")
        title.press("Enter")
        expect(current.locator(".music-title-button")).to_have_text("Quiet Rotation")
        assert audio.evaluate("audio=>audio===window.playerAudio && !audio.paused")
        current.get_by_role("button", name="Pause", exact=True).click()
        expect(play).to_be_visible()
        assert audio.evaluate("audio=>audio.paused")
        seek.fill("19.5")
        play.click()
        expect(current.get_by_role("button", name="Pause", exact=True)).to_be_visible()
        expect(play).to_be_visible(timeout=5000)
        assert audio.evaluate("audio=>audio.ended && audio.paused")
        expect(current).not_to_have_class("music-song is-playing")
        play.click()
        expect(current.get_by_role("button", name="Pause", exact=True)).to_be_visible()
        assert audio.evaluate("audio=>audio.currentTime<2")
        # All transport controls disable while no decodable recording is loaded.
        audio.evaluate('audio=>{window.playerSource=audio.src;audio.removeAttribute("src");audio.load()}')
        expect(play).to_be_disabled()
        expect(seek).to_be_disabled()
        expect(back).to_be_disabled()
        expect(forward).to_be_disabled()
        expect(current.locator(".music-time-remaining")).to_have_text("\u22120:00")
        audio.evaluate("audio=>{audio.src=window.playerSource;audio.load()}")
        expect(play).to_be_enabled()
        play.click()
        expect(current.get_by_role("button", name="Pause", exact=True)).to_be_visible()
        page.locator("#music-generate").click()
        expect(page.locator(".music-song")).to_have_count(2)
        assert page.evaluate("()=>!window.playerAudio.paused")
        current.get_by_role("button", name="Play", exact=True).click()
        expect(current.get_by_role("button", name="Pause", exact=True)).to_be_visible()
        second = current.locator("audio").element_handle()
        page.get_by_role("button", name="Select song 1", exact=True).click()
        assert second.evaluate("audio=>!audio.paused")
        expect(play).to_be_visible()
        page.locator('gallery-browser[workspace="music"] .gallery-browse-toggle').click()
        expect(page.locator(".gallery-card .gallery-no-preview")).to_have_text(["♫", "♫"])
        expect(page.locator(".gallery-wave")).to_have_count(0)
        page.locator('gallery-browser[workspace="music"] .gallery-browse-toggle').click()
        # Visibility alone misses controls clipped by the preview pane's scrolling box.
        current.locator(".music-track-text").evaluate(
            "node=>node.textContent='Evening lights across the water\\nMorning follows every quiet dream\\nFootsteps fade along the shore'"
        )
        for width, height in [(390, 844), (360, 740)]:
            page.set_viewport_size({"width": width, "height": height})
            page.locator(".music-preview-pane").evaluate("node=>node.scrollTop=0")
            assert current.locator(".music-player").evaluate("node=>node.scrollWidth<=node.clientWidth")
            assert page.locator("#music-studio").evaluate("node=>node.scrollWidth<=node.clientWidth")
            assert current.evaluate("""card=>{
              const pane=card.closest('.music-preview-pane').getBoundingClientRect();
              return ['.music-song-title','.music-track-text','.music-timeline','.music-transport'].every(selector=>{
                const rect=card.querySelector(selector).getBoundingClientRect();
                return rect.top>=pane.top && rect.bottom<=Math.min(pane.bottom,innerHeight) && rect.left>=pane.left && rect.right<=pane.right;
              });
            }"""), f"Player controls clipped at {width}x{height}"
        # Browser decoding failures produce a usable status and disable the controls.
        audio.evaluate('audio=>{window.playerSource=audio.src;audio.src="data:audio/wav;base64,YmFk";audio.load()}')
        expect(current.locator(".music-player-error")).to_have_text("This song could not be played.")
        expect(play).to_be_disabled()
        expect(seek).to_be_disabled()
        audio.evaluate("audio=>{audio.src=window.playerSource;audio.load()}")
        expect(play).to_be_enabled()
        expect(current.locator(".music-player-error")).to_be_hidden()
        assert errors == [], errors
        browser.close()
    print(
        "PASS Music player: custom transport, real WAV timing, skip clamps, keyboard seek, playback, rename, unready/error state, gallery and mobile."
    )


if __name__ == "__main__":
    main()
