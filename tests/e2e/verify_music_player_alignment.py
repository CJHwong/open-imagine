"""Music transport aligns with artwork on desktop and stays reachable on mobile."""

import base64
import io
import sys
import wave

from playwright.sync_api import expect, sync_playwright


def main():
    source = io.BytesIO()
    with wave.open(source, "wb") as song:
        song.setparams((1, 2, 24000, 480000, "NONE", "not compressed"))
        song.writeframes(bytes(960000))
    base = f"http://127.0.0.1:{int(sys.argv[1])}"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
        page.goto(base + "/?workspace=music")
        page.wait_for_function("Boolean(document.querySelector('music-studio').capabilities)")
        page.evaluate(
            """async encoded => {
          const studio = document.querySelector('music-studio');
          await studio.setKeeping(false);
          const blob = new Blob([Uint8Array.from(atob(encoded), value => value.charCodeAt(0))], {type:'audio/wav'});
          const coverBlob = new Blob(['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400"><rect width="400" height="400" fill="#294b48"/><circle cx="285" cy="105" r="60" fill="#d8ba79"/><path d="M0 300 150 160 400 340V400H0Z" fill="#49716b"/></svg>'], {type:'image/svg+xml'});
          studio.songs = [{
            id:'alignment-song', title:'Evening Lights', blob, coverBlob, seconds:20,
            seed:42, createdAt:Date.now(), generationSeconds:32.4, model:'YuE2', score:'',
            settings:{
              style:Array(3).fill('Use a pop arrangement with a memorable melodic hook and clear verse and chorus sections over a steady pulse. Create a warm mood with rounded timbres and gentle phrasing that feels intimate and welcoming. Feature an acoustic piano with clear hammer attacks and resonant chords supporting expressive melodic lines.').join(' '),
              lyrics:'[Verse]\\n' + Array.from({length:24}, (_, index) => 'Evening line ' + (index + 1) + ' across the bay').join('\\n')
            }, metadata:{}
          }];
          studio.selectedId = 'alignment-song';
          studio.renderSongs();
          await document.fonts.ready;
          await studio.querySelector('.music-artwork img').decode();
        }""",
            base64.b64encode(source.getvalue()).decode(),
        )
        current = page.locator(".music-song:not([hidden])")
        expect(current.get_by_role("button", name="Play", exact=True)).to_be_enabled()
        expect(current.locator(".music-track-text")).to_be_visible()
        for width, height in [(1440, 1000), (1280, 900), (1060, 900)]:
            page.set_viewport_size({"width": width, "height": height})
            page.wait_for_timeout(50)
            bounds = current.evaluate("""card => {
              const artwork = card.querySelector('.music-artwork').getBoundingClientRect();
              const play = card.querySelector('.music-play').getBoundingClientRect();
              const player = card.querySelector('.music-player').getBoundingClientRect();
              return {artwork:artwork.toJSON(), play:play.toJSON(), player:player.toJSON(),
                title:card.querySelector('.music-song-title').getBoundingClientRect().toJSON(),
                lyrics:card.querySelector('.music-track-text').getBoundingClientRect().toJSON()};
            }""")
            if width == 1440:
                page.screenshot(path="/tmp/music-player-alignment-desktop.png")
            assert abs(bounds["artwork"]["bottom"] - bounds["play"]["bottom"]) <= 2, bounds
            assert bounds["player"]["left"] >= bounds["artwork"]["right"], bounds
            assert abs(bounds["title"]["top"] - bounds["artwork"]["top"]) <= 2, bounds
            assert bounds["lyrics"]["height"] >= 64, bounds
            assert bounds["lyrics"]["bottom"] <= bounds["player"]["top"] + 1, bounds
            assert current.locator(".music-track-text").evaluate("pane => pane.scrollHeight > pane.clientHeight")
        for width, height in [(390, 844), (360, 740)]:
            page.set_viewport_size({"width": width, "height": height})
            page.locator(".music-preview-pane").evaluate("pane => pane.scrollTop = 0")
            page.wait_for_timeout(50)
            assert current.evaluate("""card => {
              const pane=card.closest('.music-preview-pane').getBoundingClientRect();
              const artwork=card.querySelector('.music-artwork').getBoundingClientRect();
              const player=card.querySelector('.music-player').getBoundingClientRect();
              const controls=card.querySelector('.music-transport').getBoundingClientRect();
              const lyrics=card.querySelector('.music-track-text');
              return player.top>=artwork.bottom && controls.bottom<=pane.bottom
                && player.left>=pane.left && player.right<=pane.right
                && lyrics.clientHeight>=64 && lyrics.scrollHeight>lyrics.clientHeight;
            }"""), f"Mobile transport clipped at {width}x{height}"
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            if width == 390:
                page.screenshot(path="/tmp/music-player-alignment-mobile.png")
        current.locator(".music-track-text").evaluate("pane => pane.scrollTop = pane.scrollHeight")
        assert current.locator(".music-track-text").evaluate("pane => pane.scrollTop > 0")
        # Style remains available in metadata while lyrics occupy the main player.
        page.locator(".music-output-details:not([hidden]) .prompt-line").click()
        expect(page.get_by_role("dialog", name="Music details").locator("dl")).to_contain_text("clear hammer attacks")
        browser.close()
    print("PASS cover-aligned title and transport, scrollable inline lyrics, mobile stack and full Style metadata")


if __name__ == "__main__":
    main()
