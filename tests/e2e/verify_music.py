"""Music browser and stereo transport checks. Run against a fresh --stub server.

uv run --with playwright python tests/e2e/verify_music.py <port>
No model is loaded. A real Music run is covered separately by the live test.
"""

import io
import sys
import time
import wave

from playwright.sync_api import expect, sync_playwright


def main():
    port = int(sys.argv[1])
    base = f"http://127.0.0.1:{port}"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        def chord_metadata(route):
            response = route.fetch()
            body = response.json()
            body["score"] = (
                'X:1\nM:4/4\nL:1/4\nQ:1/4=88\nV: Vocal\nV: Ins\nK:F\n% verse\nV: Vocal\n"F"C4|"Dm7"D4|"Bb"E2"C/E"F2|\nV: Ins\n"G"G4|\n% chorus\nV: Vocal\n"Fmaj7"A4|'
            )
            route.fulfill(response=response, json=body)

        page.route("**/operations/*/metadata", chord_metadata)
        page.goto(base + "/?workspace=music")
        expect(page.locator("#media-music-mode")).to_have_attribute("aria-pressed", "true")
        expect(page.locator("#music-generate")).to_be_disabled()
        expect(page.get_by_role("heading", name="Songs", exact=True)).to_be_hidden()
        expect(page.locator(".music-gallery")).to_be_hidden()
        expect(page.locator(".music-empty")).to_be_visible()
        expect(page.locator(".music-count")).to_have_text("0 songs")
        page.locator("#music-style").fill("English, warm piano pop, 88 BPM")
        page.locator("#music-lyrics").fill("[Verse]\nMorning fills the quiet street\nEvery window keeps a beat")
        page.locator(".music-advanced-fields summary").click()
        page.locator("#music-seed").fill("42")
        # Native form submission (e.g. Enter in Seed) must route to Music, never Image.
        requests = []
        page.on("request", lambda request: requests.append(request.url) if request.method == "POST" else None)
        with page.expect_response(lambda response: response.url.endswith("/music/operations")) as response:
            page.locator("#form").evaluate("form => form.requestSubmit()")
        assert response.value.status == 202
        operation = response.value.json()
        expect(page.locator(".music-song")).to_have_count(1)
        assert not any(url.endswith("/generate") or url.endswith("/image/operations") for url in requests)
        expect(page.locator(".music-song .music-song-title")).to_have_text("Untitled")
        expect(page.locator(".music-stub-note")).to_contain_text("Stub preview")
        expect(page.locator(".music-count")).to_have_text("1 song")
        expect(page.locator(".music-gallery")).to_be_visible()
        expect(page.locator(".music-empty")).to_be_hidden()
        expect(page.locator(".music-waveform")).to_have_count(0)
        expect(page.get_by_role("slider", name="Playback position")).to_be_visible()
        assert not page.locator(".music-song audio").evaluate("audio => audio.controls")
        expect(page.get_by_role("dialog", name="ABC score", exact=True)).to_be_hidden()
        # The record spins and the tonearm engages only during playback.
        expect(page.locator(".music-song .music-turntable")).to_have_count(1)
        player = page.locator(".music-song audio")
        player.evaluate("audio => { audio.loop = true; return audio.play(); }")
        expect(page.locator(".music-song.is-playing")).to_have_count(1)
        assert (
            page.locator(".music-song .music-record").evaluate("node => getComputedStyle(node).animationPlayState")
            == "running"
        )
        page.wait_for_function(
            """() => getComputedStyle(document.querySelector('.music-song .music-tonearm')).transform.startsWith('matrix(0.819')"""
        )
        player.evaluate("audio => audio.pause()")
        assert (
            page.locator(".music-song .music-record").evaluate("node => getComputedStyle(node).animationName")
            == "music-record-turn"
        )
        expect(page.locator(".music-song.is-playing")).to_have_count(0)
        page.wait_for_function(
            """() => getComputedStyle(document.querySelector('.music-song .music-tonearm')).transform === 'matrix(1, 0, 0, 1, 0, 0)'"""
        )
        assert (
            page.locator(".music-song .music-record").evaluate("node => getComputedStyle(node).animationPlayState")
            == "paused"
        )
        result = page.request.get(base + operation["status_url"] + "/result")
        assert result.headers["content-type"] == "audio/wav"
        with wave.open(io.BytesIO(result.body())) as audio:
            assert audio.getnchannels() == 2 and audio.getframerate() == 48000
        metadata = page.request.get(base + operation["status_url"] + "/metadata").json()
        assert metadata["seed"] == 42 and metadata["stub"]
        page.locator(".music-output-details:not([hidden]) .prompt-line").click()
        expect(page.get_by_role("dialog", name="Music details").get_by_text("Raw metadata", exact=True)).to_have_count(
            0
        )
        expect(page.get_by_role("dialog", name="Music details").locator("dl")).to_contain_text("piano pop")
        page.get_by_role("button", name="Close music details").click()
        assert page.locator("audio").get_attribute("src").startswith("blob:")
        page.locator("#media-voice-mode").click()
        expect(page.locator("#music-studio")).to_be_hidden()
        page.locator("#media-music-mode").click()
        expect(page.locator(".music-song")).to_have_count(1)
        # Default Keep is on: saved recordings survive a reload, and Run already emptied
        # the draft it sent.
        page.reload()
        page.locator("#media-music-mode").click()
        expect(page.locator("#music-style")).to_have_value("")
        expect(page.locator(".music-song")).to_have_count(1)
        # Edit score opens the editor with the saved score; it does not touch the song.
        page.locator(".music-output-details:not([hidden])").get_by_role("button", name="Edit score", exact=True).click()
        editor = page.get_by_role("dialog", name="ABC score", exact=True)
        expect(editor).to_be_visible()
        assert page.locator("#music-abc").input_value().startswith("X:")
        expect(page.locator("#music-abc-notation svg").first).to_be_visible(timeout=30000)
        page.locator("#music-abc-close").click()
        expect(editor).to_be_hidden()
        # A storage failure must keep the card until durable deletion succeeds.
        page.evaluate("""() => {
          window.musicDelete = IDBObjectStore.prototype.delete;
          IDBObjectStore.prototype.delete = function(...args) {
            if (this.name === 'songs') throw new DOMException('test quota', 'QuotaExceededError');
            return window.musicDelete.apply(this, args);
          };
        }""")
        page.locator(".music-output-details:not([hidden])").get_by_role("button", name="Delete", exact=True).click()
        expect(page.get_by_text("Music could not be saved: test quota", exact=True).first).to_be_visible()
        expect(page.locator(".music-song")).to_have_count(1)
        page.evaluate("() => { IDBObjectStore.prototype.delete = window.musicDelete; }")
        page.locator(".music-output-details:not([hidden])").get_by_role("button", name="Delete", exact=True).click()
        expect(page.locator(".music-song")).to_have_count(0)
        page.reload()
        page.locator("#media-music-mode").click()
        expect(page.locator(".music-song")).to_have_count(0)
        # Failed imports remain eligible for retry; they are never remembered as saved.
        page.evaluate("""() => {
          window.musicPut = IDBObjectStore.prototype.put;
          IDBObjectStore.prototype.put = function(...args) {
            if (this.name === 'songs') throw new DOMException('test import quota', 'QuotaExceededError');
            return window.musicPut.apply(this, args);
          };
        }""")
        # A retry sends the words again, because the failed run emptied them.
        page.locator("#music-style").fill("English, warm piano pop, 88 BPM")
        with page.expect_response(lambda response: response.url.endswith("/music/operations")) as response:
            page.locator("#music-generate").click()
        retry_operation = response.value.json()
        expect(page.get_by_text("Music could not be saved: test import quota", exact=True).first).to_be_visible()
        expect(page.locator(".music-song")).to_have_count(0)
        assert retry_operation["id"] not in page.evaluate(
            "JSON.parse(sessionStorage.getItem('studio-seen-operations') || '[]')"
        )
        page.evaluate("() => { IDBObjectStore.prototype.put = window.musicPut; }")
        expect(page.locator(".music-song")).to_have_count(1)
        page.locator(".music-output-details:not([hidden])").get_by_role("button", name="Delete", exact=True).click()
        expect(page.locator(".music-song")).to_have_count(0)
        # A late metadata fetch in a second tab cannot resurrect a deleted song.
        other = page.context.new_page()
        # Simulate delayed cross-tab notifications so the operation importer must run.
        other.add_init_script("""window.addEventListener('storage', event => {
            if (event.key === 'studio-music-changed') event.stopImmediatePropagation();
        }, true);""")
        delayed = []
        other.route("**/operations/*/metadata", lambda route: delayed.append(route))
        other.goto(base + "/?workspace=music")
        # The draft arrives empty because the last run emptied it.
        other.locator("#music-style").fill("English, warm piano pop, 88 BPM")
        expect(other.locator("#music-generate")).to_be_enabled()
        with page.expect_response(lambda response: response.url.endswith("/music/operations")) as response:
            page.locator("#music-style").fill("English, warm piano pop, 88 BPM")
            page.locator("#music-generate").click()
        late = response.value.json()
        expect(page.locator(".music-song")).to_have_count(1)
        deadline = time.monotonic() + 10
        while not delayed and time.monotonic() < deadline:
            page.wait_for_timeout(50)
        assert delayed, "Second tab never started metadata import"
        page.locator(".music-output-details:not([hidden])").get_by_role("button", name="Delete", exact=True).click()
        expect(page.locator(".music-song")).to_have_count(0)
        for route in delayed:
            route.continue_()
        other.wait_for_function(
            "id => JSON.parse(sessionStorage.getItem('studio-seen-operations') || '[]').includes(id)", arg=late["id"]
        )
        expect(other.locator(".music-song")).to_have_count(0)
        other.reload()
        expect(other.locator(".music-song")).to_have_count(0)
        other.close()

        # Simulate a non-stub completed result to test its Send action without a GPU.
        def nonstub_metadata(route):
            response = route.fetch()
            body = response.json()
            body["stub"] = False
            route.fulfill(response=response, json=body)

        page.route("**/operations/*/metadata", nonstub_metadata)
        page.locator("#music-style").fill("English, warm piano pop, 88 BPM")
        page.locator("#music-generate").click()
        expect(page.locator(".music-song")).to_have_count(1)
        send = page.locator(".music-output-details [data-music-send]")
        expect(send).to_be_enabled()
        held = []
        page.route("**/music/operations", lambda route: held.append(route))
        page.locator("#music-style").fill("English, warm piano pop, 88 BPM")
        page.locator("#music-generate").click()
        expect(send).to_be_disabled()
        expect(page.locator(".music-generation")).to_be_visible()
        detail = page.locator("#music-studio").evaluate("""node => {
            node.setOperation({kind: 'music', model: 'YuE2 (MLX Q8)', progress: {step: 32, total: 0}});
            return node.querySelector('.music-generation-detail').textContent;
        }""")
        assert detail == "YuE2 · 32 tokens generated"
        assert (
            page.locator(".music-generation .music-record").evaluate("node => getComputedStyle(node).animationName")
            == "music-record-turn"
        )
        page.emulate_media(reduced_motion="reduce")
        assert (
            page.locator(".music-generation .music-record").evaluate("node => getComputedStyle(node).animationName")
            == "none"
        )
        assert (
            page.locator(".music-generation .music-tonearm").evaluate(
                "node => getComputedStyle(node).transitionDuration"
            )
            == "0s"
        )
        page.emulate_media(reduced_motion="no-preference")
        assert page.locator("#video-studio").evaluate("node => node.audio") is None
        for route in held:
            route.continue_()
        expect(page.locator(".music-song")).to_have_count(2)
        expect(page.locator(".music-generation")).to_be_hidden()
        expect(page.locator(".music-count")).to_have_text("2 songs")
        while page.locator(".music-song").count():
            page.locator(".music-output-details:not([hidden])").get_by_role("button", name="Delete", exact=True).click()
            page.wait_for_timeout(100)
        # A mobile viewport must retain reachable form controls.
        page.set_viewport_size({"width": 390, "height": 844})
        expect(page.locator("#music-style")).to_be_visible()
        expect(page.locator("#music-generate")).to_be_visible()
        expect(page.locator(".music-empty")).to_be_visible()
        assert page.locator("#music-studio").evaluate("node => node.scrollWidth <= node.clientWidth")
        assert errors == [], errors
        browser.close()
    print(
        "PASS Music: form routing, stereo WAV, metadata, workspace switching, persistence, deletion, mobile controls, no page errors"
    )


if __name__ == "__main__":
    main()
