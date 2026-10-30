"""Music player, chord chart and generated covers. Uses a fresh stub server; no GPU.

uv run --with playwright python tests/e2e/verify_music_preview.py <port>
"""

import sys
import time

from playwright.sync_api import expect, sync_playwright

SCORE = 'X:1\nM:4/4\nL:1/4\nQ:1/4=88\nV: Vocal\nV: Ins\nK:F\n% verse\nV: Vocal\n"F"C4|"Dm7"D4|"Bb"E2"C/E"F2|\nV: Ins\n"G"G4|\n% chorus\nV: Vocal\n"Fmaj7"A4|'


def main():
    base = f"http://127.0.0.1:{int(sys.argv[1])}"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        def score_metadata(route):
            answer = route.fetch()
            body = answer.json()
            body["score"] = SCORE
            route.fulfill(response=answer, json=body)

        page.route("**/operations/*/metadata", score_metadata)
        page.goto(base + "/?workspace=music")
        # Parser fixtures run against the module actually served to the browser.
        page.evaluate("""async () => {
          const {musicScore, musicCoverPrompt} = await import('/page/lib/music-score.js');
          const chords = score => musicScore(score).sections.flatMap(s=>s.bars).flat();
          const equal = (actual, expected) => { if(JSON.stringify(actual)!==JSON.stringify(expected)) throw Error(JSON.stringify({actual,expected})); };
          equal(chords(''), []);
          equal(chords('K:C\\n"^annotation"C4|"Coda"D4|'), []);
          equal(chords('K:C\\n"C#m7"C4|"Bb13(#11)"D4|"N.C."z4|"F/G"C4|'), ['C#m7','Bb13(#11)','N.C.','F/G']);
          equal(chords('K:C\\nw:"Am" lyrics\\n"C"C4|'), ['C']);
          equal(chords('K:C\\n"^a % comment"C4|"Am"A4| % "G"ignored'), ['Am']);
          equal(chords('K:C\\nV:Ins\\n"G"C4|\\nV:Vocal\\n"F"F4|'), ['F']);
          equal(chords('K:C\\n|:"C"C4:|"G"G4||'), ['C','G']);
          equal(musicScore('K:C\\n"C"C4|Z4|').sections[0].bars.length, 5);
          const long=musicScore('K:C\\n'+ '"C"C4|'.repeat(300));
          equal(long.sections[0].bars.length,256); equal(long.truncated,true);
          equal(chords('K:C\\n"<img src=x onerror=alert(1)>"C4|'), []);
          const prompt=musicCoverPrompt({settings:{style:'jazz',lyrics:'[Verse]\\nBlue moon'}});
          if(!prompt.includes('jazz') || !/conceptual|painting/i.test(prompt) || !prompt.includes('Blue moon') || !/no visible text|do not render.*text/i.test(prompt)) throw Error('Cover prompt');
        }""")
        page.locator("#music-style").fill("Warm piano pop, original song")
        page.locator("#music-lyrics").fill("[Verse]\nMorning settles on the street\nEvery window keeps a beat")
        page.locator(".music-advanced-fields summary").click()
        page.locator("#music-seed").fill("42")
        page.locator("#music-generate").click()
        expect(page.locator(".music-song")).to_have_count(1)
        current = page.locator(".music-song:not([hidden])")
        bar = page.locator(".music-output-details:not([hidden])")
        expect(page.get_by_role("dialog", name="ABC score", exact=True)).to_be_hidden()
        bar.get_by_role("button", name="Edit score", exact=True).click()
        editor = page.get_by_role("dialog", name="ABC score", exact=True)
        expect(editor).to_be_visible()
        expect(editor.locator("#music-abc-notation svg").first).to_be_visible(timeout=30000)
        page.locator("#music-abc-close").click()
        expect(editor).to_be_hidden()
        held, artwork_requests = [], []

        def hold_image(route):
            payload = route.request.post_data_json
            artwork_requests.append(payload)
            if payload["kind"] == "image":
                held.append(route)
            else:
                route.continue_()

        page.route("**/api/v1/operations", hold_image)
        bar.get_by_role("button", name="More actions", exact=True).click()
        bar.get_by_role("menuitem", name="Generate artwork", exact=True).click()
        deadline = time.monotonic() + 10
        while not held and time.monotonic() < deadline:
            page.wait_for_timeout(50)
        assert held, "Cover operation was not submitted"
        payload = held[0].request.post_data_json
        assert payload["kind"] == "image" and payload["size"].split("x")[0] == payload["size"].split("x")[1]
        assert [request["kind"] for request in artwork_requests] == ["rewrite", "image"]
        brief = artwork_requests[0]
        assert "Morning settles" in brief["prompt"] and "Warm piano pop" in brief["prompt"]
        assert brief["client_id"].endswith(":brief")
        assert "Do not render" in payload["prompt"]
        assert payload["count"] == 1 and ":music-cover:" in payload["client_id"]
        expect(page.locator("#media-music-mode")).to_have_attribute("aria-pressed", "true")
        expect(bar.get_by_role("menuitem", name="Generate artwork", exact=True, include_hidden=True)).to_be_disabled()
        for route in held:
            route.continue_()
        page.unroute("**/api/v1/operations")
        expect(current.locator(".music-artwork > img")).to_be_visible(timeout=90000)
        expect(page.locator("#media-music-mode")).to_have_attribute("aria-pressed", "true")
        assert current.locator(".music-artwork > img").evaluate(
            "image => image.naturalWidth === image.naturalHeight && image.naturalWidth > 0"
        )
        expect(bar.get_by_role("menuitem", name="Regenerate artwork", exact=True, include_hidden=True)).to_be_enabled()
        page.reload()
        expect(current.locator(".music-artwork > img")).to_be_visible()
        bar.get_by_role("button", name="Edit score", exact=True).click()
        expect(page.locator("#music-abc")).to_have_value(SCORE)
        page.locator("#music-abc-close").click()
        # A failed regeneration preserves the previous cover and can be retried.
        page.route("**/api/v1/operations", lambda route: route.fulfill(status=409, json={"error": "Cover test busy"}))
        bar.get_by_role("button", name="More actions", exact=True).focus()
        page.keyboard.press("Alt+C")
        expect(current.locator(".music-error:not(.music-player-error)")).to_have_text("Cover test busy")
        expect(current.locator(".music-artwork > img")).to_be_visible()
        expect(bar.get_by_role("menuitem", name="Regenerate artwork", exact=True, include_hidden=True)).to_be_enabled()
        page.unroute("**/api/v1/operations")
        # The cover update transaction rejects stale requests and deleted songs.
        page.evaluate("""async () => {
          const {updateMusicSong, deleteMusicSong, saveMusicSong} = await import('/page/lib/music-store.js');
          const song = document.querySelector('#music-studio').songs[0];
          await updateMusicSong(song.id, s=>({...s,coverClientId:'newer'}));
          const stale = await updateMusicSong(song.id, s=>s.coverClientId==='older' ? {...s,coverClientId:''}:null);
          if(stale) throw Error('Stale cover overwrote newer request');
          const durable = await saveMusicSong({...song,coverBlob:undefined,coverClientId:''});
          if(durable.coverClientId!=='newer' || !durable.coverBlob) throw Error('Delayed import erased cover');
          await updateMusicSong(song.id, s=>({...s,coverClientId:'orphan',coverRequestedAt:Date.now()-130000,coverError:''}));
          await document.querySelector('#music-studio').restoreSongs();
          document.querySelector('#music-studio').observeCoverOperations([]);
          await saveMusicSong({...song,id:'cover-tombstone-test'});
          await deleteMusicSong('cover-tombstone-test');
          if(await updateMusicSong('cover-tombstone-test',s=>s)) throw Error('Deleted cover resurrected');
        }""")
        expect(current.locator(".music-error:not(.music-player-error)")).to_have_text(
            "Cover request expired. Generate it again."
        )
        expect(bar.get_by_role("menuitem", name="Regenerate artwork", exact=True, include_hidden=True)).to_be_enabled()
        expect(current.locator(".music-artwork > img")).to_be_visible()

        page.locator("#music-style").fill("Warm piano pop, original song")
        page.locator("#music-lyrics").fill("[Chorus]\nAnother morning on the road")
        if not page.locator(".music-advanced-fields").evaluate("node => node.open"):
            page.locator(".music-advanced-fields summary").click()
        page.locator("#music-seed").fill("43")
        page.locator("#music-generate").click()
        expect(page.locator(".music-song")).to_have_count(2)
        expect(page.locator(".music-song:not([hidden])")).to_have_count(1)
        page.get_by_role("button", name="Select song 1", exact=True).click()
        expect(current.locator(".music-artwork > img")).to_be_visible()
        page.keyboard.press("Home")
        expect(page.get_by_role("button", name="Select song 2", exact=True)).to_have_attribute("aria-pressed", "true")
        page.keyboard.press("End")
        expect(page.get_by_role("button", name="Select song 1", exact=True)).to_have_attribute("aria-pressed", "true")
        page.locator('gallery-browser[workspace="music"] .gallery-browse-toggle').click()
        expect(page.get_by_role("region", name="music gallery browser")).to_be_visible()
        page.get_by_role("searchbox", name="Search gallery").fill("piano")
        expect(page.locator(".gallery-card")).to_have_count(2)
        page.locator('gallery-browser[workspace="music"] .gallery-browse-toggle').click()
        page.set_viewport_size({"width": 390, "height": 844})
        expect(page.locator(".music-gallery")).to_be_visible()
        assert page.locator("#music-studio").evaluate("node=>node.scrollWidth <= node.clientWidth")
        assert errors == [], errors
        browser.close()
    print(
        "PASS Music preview: chord parser, album layout, cover generation, persistence, errors, conditional storage, gallery navigation and mobile."
    )


if __name__ == "__main__":
    main()
