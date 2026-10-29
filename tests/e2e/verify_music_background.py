"""Music keeps one recording playing while the gallery selection and records change.

Run against a fresh all-backends stub. No model is loaded.
"""

import base64
import io
import sys
import wave

from playwright.sync_api import expect, sync_playwright


def main():
    source = io.BytesIO()
    with wave.open(source, "wb") as recording:
        recording.setparams((1, 2, 24000, 1440000, "NONE", "not compressed"))
        recording.writeframes(bytes(2880000))
    base = f"http://127.0.0.1:{int(sys.argv[1])}"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/?workspace=music")
        page.wait_for_function("Boolean(document.querySelector('music-studio').capabilities)")
        page.evaluate(
            """async encoded => {
          const studio = document.querySelector('music-studio');
          await studio.setKeeping(false);
          const blob = new Blob([Uint8Array.from(atob(encoded), value => value.charCodeAt(0))], {type:'audio/wav'});
          studio.songs = ['First', 'Second'].map((title, index) => ({
            id: 'playback-' + index, title, blob, seconds: 60, seed: index,
            createdAt: Date.now() + index, score: '', settings: {style: 'piano'}, metadata: {}
          }));
          studio.selectedId = studio.songs[0].id;
          studio.renderSongs();
        }""",
            base64.b64encode(source.getvalue()).decode(),
        )
        first = page.locator('.music-song[data-song-id="playback-0"]')
        second = page.locator('.music-song[data-song-id="playback-1"]')
        expect(first.get_by_role("button", name="Play", exact=True)).to_be_enabled()
        first.get_by_role("button", name="Play", exact=True).click()
        page.wait_for_function("!document.querySelector('.music-song[data-song-id=\"playback-0\"] audio').paused")
        first.locator("audio").evaluate("audio => {window.firstAudio = audio; window.firstSource = audio.src;}")
        page.get_by_role("button", name="Select song 2", exact=True).click()
        assert page.evaluate("!window.firstAudio.paused"), "Selecting a recording stopped background playback"
        expect(second).to_be_visible()
        pause = page.get_by_role("button", name="Pause background audio", exact=True)
        expect(pause).to_be_visible()
        pause.click()
        assert page.evaluate("window.firstAudio.paused")
        expect(pause).to_be_hidden()
        page.get_by_role("button", name="Select song 1", exact=True).click()
        first.get_by_role("button", name="Play", exact=True).click()
        page.get_by_role("button", name="Select song 2", exact=True).click()
        second.get_by_role("button", name="Play", exact=True).click()
        expect(second.get_by_role("button", name="Pause", exact=True)).to_be_visible()
        assert page.evaluate("window.firstAudio.paused")
        second.locator("audio").evaluate("audio => {window.secondAudio = audio; window.secondSource = audio.src;}")
        expect(pause).to_be_hidden()
        # A new result redraws the gallery but must retain the active media and transport.
        page.evaluate("""() => {
          const studio = document.querySelector('music-studio');
          studio.songs.push({...studio.songs[0], id:'playback-2', title:'Third'});
          studio.selectedId = 'playback-2';
          studio.renderSongs();
        }""")
        assert page.evaluate("window.secondAudio.isConnected && !window.secondAudio.paused")
        assert second.locator("audio").evaluate(
            "audio => audio === window.secondAudio && audio.src === window.secondSource"
        )
        expect(pause).to_be_visible()
        page.evaluate("""async () => {
          const studio = document.querySelector('music-studio');
          await studio.setReference(new File([studio.songs[0].blob], 'reference.wav', {type:'audio/wav'}));
          await studio.setReference(null);
        }""")
        assert page.evaluate("!window.secondAudio.paused"), "Reference changes paused the song"

        def fast_artwork(route):
            response = route.fetch()
            body = response.json()
            for mode in body["image"]["capabilities"]["modes"]:
                for parameter in mode["params"]:
                    if parameter["id"] == "steps":
                        parameter["default"] = 1
            route.fulfill(response=response, json=body)

        page.route("**/api/v1/studio", fast_artwork)
        page.evaluate(
            "document.querySelector('music-studio').generateCover(document.querySelector('music-studio').songs[2])"
        )
        page.wait_for_function(
            "Boolean(document.querySelector('music-studio').songs.find(song => song.id === 'playback-2').coverBlob)"
        )
        page.unroute("**/api/v1/studio")
        assert page.evaluate("!window.secondAudio.paused"), "Artwork generation paused the song"
        # Deleting another recording must not interrupt the active one.
        page.evaluate("document.querySelector('music-studio').removeSong('playback-0')")
        assert page.evaluate("!window.secondAudio.paused")
        assert page.evaluate("window.firstAudio.paused && !window.firstAudio.isConnected")
        assert page.evaluate("fetch(window.firstSource).then(() => false, () => true)")
        # The persistent pause remains reachable on narrow screens.
        page.set_viewport_size({"width": 390, "height": 844})
        expect(pause).to_be_visible()
        assert pause.evaluate(
            "button => {const box=button.getBoundingClientRect();return box.left>=0 && box.right<=innerWidth && box.top>=0 && box.bottom<=innerHeight;}"
        )
        page.evaluate("window.secondAudio.currentTime = 59.8")
        expect(pause).to_be_hidden(timeout=5000)
        assert page.evaluate("window.secondAudio.ended")
        page.evaluate("document.querySelector('music-studio').selectSong('playback-1')")
        second.get_by_role("button", name="Play", exact=True).click()
        page.evaluate("document.querySelector('music-studio').removeSong('playback-1')")
        assert page.evaluate("window.secondAudio.paused && !window.secondAudio.isConnected")
        expect(pause).to_be_hidden()
        # Workspace changes retain the existing stop behavior.
        third = page.locator('.music-song[data-song-id="playback-2"]')
        third.get_by_role("button", name="Play", exact=True).click()
        third.locator("audio").evaluate("audio => window.thirdAudio = audio")
        page.locator("#media-voice-mode").click()
        expect(page.locator("#music-studio")).to_be_hidden()
        assert page.evaluate("window.thirdAudio.paused")
        assert errors == [], errors
        browser.close()
    print(
        "PASS Music background playback: selection, explicit pause, one player, redraw, removal, ending, mobile and workspace exit"
    )


if __name__ == "__main__":
    main()
