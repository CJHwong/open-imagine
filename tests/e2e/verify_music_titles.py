"""Music titles use durable explicit names; fresh stub server, no GPU.

uv run --with playwright python tests/e2e/verify_music_titles.py <port>
"""

import sys

from playwright.sync_api import expect, sync_playwright


def stored_title(page):
    return page.evaluate("""async()=>{
      const {musicSongs}=await import('/page/lib/music-store.js');
      return (await musicSongs())[0]?.title || '';
    }""")


def main():
    base = f"http://127.0.0.1:{int(sys.argv[1])}"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/?workspace=music")
        page.locator("#music-style").fill("Warm piano pop")
        page.locator("#music-lyrics").fill("[Verse]\nNever use this lyric as the title")
        page.locator("#music-generate").click()
        expect(page.locator(".music-song")).to_have_count(1)
        title = page.locator(".music-song-title .music-title-button")
        editor = page.get_by_role("textbox", name="Song title", exact=True)
        expect(title).to_have_text("Untitled")
        assert stored_title(page) == "Untitled"
        expect(page.locator(".music-stub-note")).to_be_visible()
        recording = page.locator(".music-song audio")
        recording.evaluate("audio=>{window.titleRecording=audio;audio.loop=true;return audio.play()}")
        title.click()
        expect(editor).to_be_focused()
        expect(editor).to_have_attribute("maxlength", "120")
        editor.fill("Morning Windows")
        editor.press("Enter")
        expect(title).to_have_text("Morning Windows")
        assert stored_title(page) == "Morning Windows"
        assert recording.evaluate("audio=>audio===window.titleRecording && !audio.paused")
        title.focus()
        title.press("Enter")
        expect(editor).to_be_focused()
        editor.fill("Cancelled title")
        editor.press("Escape")
        expect(title).to_have_text("Morning Windows")
        expect(title).to_be_focused()
        assert stored_title(page) == "Morning Windows"
        title.click()
        editor.fill("  Evening Windows  ")
        page.locator("#music-style").click()
        expect(title).to_have_text("Evening Windows")
        assert stored_title(page) == "Evening Windows"
        assert recording.evaluate("audio=>audio===window.titleRecording && !audio.paused")
        title.click()
        editor.fill("   ")
        editor.press("Enter")
        expect(title).to_have_text("Untitled")
        assert stored_title(page) == "Untitled"
        # Title-less legacy records keep Untitled even with nonempty stored lyrics.
        page.evaluate("""async()=>{
          const {updateMusicSong}=await import('/page/lib/music-store.js');
          await updateMusicSong(document.querySelector('#music-studio').songs[0].id,s=>{
            const legacy={...s};delete legacy.title;return legacy;
          });
        }""")
        page.reload()
        expect(title).to_have_text("Untitled")
        other = context.new_page()
        other.goto(base + "/?workspace=music")
        expect(other.locator(".music-title-button")).to_have_text("Untitled")
        title.click()
        editor.fill("Across the Tabs")
        editor.press("Enter")
        expect(other.locator(".music-title-button")).to_have_text("Across the Tabs")
        page.locator('gallery-browser[workspace="music"] .gallery-browse-toggle').click()
        expect(page.locator(".gallery-card-text")).to_have_text("Across the Tabs")
        page.locator('gallery-browser[workspace="music"] .gallery-browse-toggle').click()
        page.reload()
        expect(title).to_have_text("Across the Tabs")
        # The thumbnail POST uses the saved title, style and lyrics as visual inspiration.
        artwork_requests = []

        def reject_artwork(route):
            payload = route.request.post_data_json
            artwork_requests.append(payload)
            if payload["kind"] == "rewrite":
                route.continue_()
            else:
                route.fulfill(status=409, json={"error": "Title artwork request captured"})

        page.route("**/api/v1/operations", reject_artwork)
        bar = page.locator(".music-output-details:not([hidden])")
        bar.get_by_role("button", name="More actions", exact=True).click()
        bar.get_by_role("button", name="Artwork", exact=True).click()
        expect(page.locator(".music-error:not(.music-player-error)")).to_have_text("Title artwork request captured")
        assert [request["kind"] for request in artwork_requests] == ["rewrite", "image"]
        brief = artwork_requests[0]["prompt"]
        assert "Across the Tabs" in brief and "Warm piano pop" in brief
        assert "Never use this lyric" in brief
        assert "Do not render" in artwork_requests[1]["prompt"]
        page.unroute("**/api/v1/operations", reject_artwork)
        # A newer cover update must survive a title change based on an older UI record.
        page.evaluate("""async()=>{
          const {updateMusicSong}=await import('/page/lib/music-store.js');
          const song=document.querySelector('#music-studio').songs[0];
          await updateMusicSong(song.id,s=>({...s,coverSeed:731,coverClientId:'concurrent-cover'}));
        }""")
        title.click()
        editor.fill("With Artwork")
        editor.press("Enter")
        expect(title).to_have_text("With Artwork")
        assert page.evaluate("""async()=>{
          const {musicSongs}=await import('/page/lib/music-store.js');
          const song=(await musicSongs())[0];
          return song.coverSeed===731 && song.coverClientId==='concurrent-cover';
        }""")
        # A storage failure leaves both the displayed and durable title unchanged.
        page.evaluate("""()=>{
          window.titleTransaction=IDBDatabase.prototype.transaction;
          IDBDatabase.prototype.transaction=function(stores,mode,...args){
            if(mode==='readwrite') throw Error('Title storage test failure');
            return window.titleTransaction.call(this,stores,mode,...args);
          };
        }""")
        title.click()
        editor.fill("Must not be saved")
        editor.press("Enter")
        expect(editor).to_be_hidden()
        expect(page.get_by_text("Music could not be saved: Title storage test failure", exact=True)).to_be_visible()
        expect(title).to_have_text("With Artwork")
        assert stored_title(page) == "With Artwork"
        page.evaluate("()=>{IDBDatabase.prototype.transaction=window.titleTransaction}")
        # A recording removed in another tab cannot be resurrected by an open editor.
        title.click()
        editor.fill("Deleted recording")
        page.evaluate("""async()=>{
          const {deleteMusicSong}=await import('/page/lib/music-store.js');
          await deleteMusicSong(document.querySelector('#music-studio').songs[0].id);
        }""")
        editor.press("Enter")
        expect(editor).to_be_hidden()
        assert (
            page.evaluate("""async()=>{
          const {musicSongs}=await import('/page/lib/music-store.js');
          return (await musicSongs()).length;
        }""")
            == 0
        )
        assert errors == [], errors
        context.close()
        browser.close()
    print(
        "PASS Music titles: Untitled, inline editing, keyboard, persistence, gallery, cross-tab, playback and safe conditional storage."
    )


if __name__ == "__main__":
    main()
