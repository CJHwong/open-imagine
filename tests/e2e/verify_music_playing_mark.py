"""The Music gallery marks audible playback independently of selection."""

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
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(base + "/?workspace=music")
        page.wait_for_function("Boolean(document.querySelector('music-studio').capabilities)")
        page.evaluate(
            """async encoded => {
          const studio = document.querySelector('music-studio');
          await studio.setKeeping(false);
          const blob = new Blob([Uint8Array.from(atob(encoded), value => value.charCodeAt(0))], {type:'audio/wav'});
          studio.songs = ['First', 'Second'].map((title, index) => ({
            id:'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa:' + (index + 1), title, blob, seconds:20,
            seed:index, createdAt:Date.now()+index, score:'', settings:{style:'piano'}, metadata:{}
          }));
          studio.selectedId = studio.songs[0].id;
          studio.renderSongs();
        }""",
            base64.b64encode(source.getvalue()).decode(),
        )
        first_id = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa:1"
        second_id = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa:2"
        first = page.locator(f'.music-song[data-song-id="{first_id}"]')
        first.get_by_role("button", name="Play", exact=True).click()
        first.locator("audio").evaluate("audio => audio.loop = true")
        first_thumb = page.locator(f'.music-thumb[data-song-id="{first_id}"]')
        second_thumb = page.locator(f'.music-thumb[data-song-id="{second_id}"]')
        expect(first_thumb.locator(".music-playing-mark")).to_be_visible()
        expect(page.locator(".music-thumb.is-playing")).to_have_count(1)
        second_thumb.click()
        expect(first_thumb).to_have_attribute("aria-pressed", "false")
        expect(second_thumb).to_have_attribute("aria-pressed", "true")
        expect(first_thumb.locator(".music-playing-mark")).to_be_visible()
        expect(second_thumb.locator(".music-playing-mark")).to_be_hidden()
        gallery = page.locator('gallery-browser[workspace="music"]')
        gallery.locator(".gallery-browse-toggle").click()
        active_card = gallery.locator(".gallery-card.is-playing")
        expect(active_card).to_have_count(1)
        expect(active_card.locator(".gallery-card-pick")).to_have_attribute("data-item-id", first_id)
        expect(active_card.get_by_role("status", name="Now playing", exact=True)).to_be_visible()
        bars = active_card.locator(".music-playing-bars i")
        expect(bars).to_have_count(3)
        assert bars.first.evaluate("bar => getComputedStyle(bar).animationName") == "music-playing-bars"
        gallery.get_by_role("checkbox", name="Group batches").check()
        expect(gallery.locator(".gallery-card")).to_have_count(1)
        expect(gallery.locator(".gallery-card.is-playing .music-playing-mark")).to_be_visible()
        gallery.get_by_role("checkbox", name="Group batches").uncheck()
        second_card = gallery.locator(f'.gallery-card-pick[data-item-id="{second_id}"]')
        second_card.press("Space")
        expect(gallery.locator(".gallery-card.is-playing .gallery-card-pick")).to_have_attribute(
            "data-item-id", second_id
        )
        expect(first_thumb.locator(".music-playing-state")).to_have_js_property("hidden", True)
        expect(second_thumb.locator(".music-playing-state")).to_have_js_property("hidden", False)
        page.emulate_media(reduced_motion="reduce")
        active_card = gallery.locator(".gallery-card.is-playing")
        assert (
            active_card.locator(".music-playing-bars i").first.evaluate("bar => getComputedStyle(bar).animationName")
            == "none"
        )
        expect(active_card.get_by_text("Playing", exact=True)).to_be_visible()
        page.set_viewport_size({"width": 390, "height": 844})
        assert active_card.locator(".music-playing-mark").evaluate("""mark => {
          const badge = mark.getBoundingClientRect(), frame = mark.closest('.still').getBoundingClientRect();
          return badge.left >= frame.left && badge.right <= frame.right && badge.top >= frame.top && badge.bottom <= frame.bottom;
        }""")
        second_card.press("Space")
        expect(gallery.locator(".gallery-card.is-playing")).to_have_count(0)
        expect(page.locator(".music-thumb.is-playing")).to_have_count(0)
        second_card.press("Space")
        expect(gallery.locator(".gallery-card.is-playing")).to_have_count(1)
        page.locator(f'.music-song[data-song-id="{second_id}"] audio').evaluate("audio => audio.currentTime = 19.8")
        expect(gallery.locator(".gallery-card.is-playing")).to_have_count(0, timeout=5000)
        second_card.press("Space")
        expect(gallery.locator(".gallery-card.is-playing")).to_have_count(1)
        page.evaluate("document.querySelector('music-studio').removeSong('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa:2')")
        expect(gallery.locator(".gallery-card.is-playing")).to_have_count(0)
        expect(page.locator(".music-thumb.is-playing")).to_have_count(0)
        browser.close()
    print(
        "PASS playing marker: strip, Browse, grouped batch, selection independence, keyboard play/pause, track switch, ending, deletion and reduced motion"
    )


if __name__ == "__main__":
    main()
