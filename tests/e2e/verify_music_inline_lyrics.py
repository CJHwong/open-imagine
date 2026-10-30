"""Inline lyrics replace the main style text while playback and draft editing remain available."""

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
        for width, height in [(1440, 1000), (390, 700)]:
            page = browser.new_page(viewport={"width": width, "height": height})
            errors = []
            page.on("pageerror", lambda error, errors=errors: errors.append(str(error)))
            page.goto(base + "/?workspace=music")
            page.wait_for_function("Boolean(document.querySelector('music-studio').capabilities)")
            page.evaluate(
                """async encoded => {
                  const studio = document.querySelector('music-studio');
                  await studio.setKeeping(false);
                  const blob = new Blob([Uint8Array.from(atob(encoded), value=>value.charCodeAt(0))], {type:'audio/wav'});
                  studio.songs = ['Song', 'Instrumental', 'Score', 'Blank', 'Whitespace', 'Missing'].map((title, index)=>({
                    id:'inline-'+index, title, blob:index===2 ? null : blob, seconds:60, seed:index,
                    createdAt:Date.now()+index, score:'X:1\\nK:C\\nC4|', metadata:{},
                    settings:{style:'Detailed style stays in the metadata. '.repeat(64), instrumental:index===1,
                      lyrics:index===1 ? '' : '[Verse]\\n'+Array.from({length:32},(_,index)=>'Original line '+index).join('\\n')
                        +'\\n[Chorus]\\nThe final words'}
                  }));
                  studio.songs[3].settings.lyrics = '';
                  studio.songs[4].settings.lyrics = String.fromCharCode(32, 9, 10, 32);
                  delete studio.songs[5].settings.lyrics;
                  studio.selectedId='inline-0'; studio.renderSongs();
                }""",
                base64.b64encode(source.getvalue()).decode(),
            )
            page.locator("#music-style").fill("My editable draft style")
            current = page.locator('.music-song[data-song-id="inline-0"]')
            inline = current.locator(".music-inline-lyrics")
            expect(current.get_by_role("button", name="Style", exact=True)).to_have_count(0)
            toggle = current.get_by_role("button", name="Lyrics", exact=True)
            expect(toggle).to_have_attribute("aria-pressed", "false")
            assert toggle.inner_text() == ""
            expect(toggle.locator("svg use")).to_have_attribute("href", "#i-text")
            assert current.get_by_role("button", name="Forward 5 seconds", exact=True).evaluate(
                "button=>button.nextElementSibling.matches('.music-lyrics-toggle')"
            )
            content_height = current.locator(".music-track-text").evaluate("node=>node.clientHeight")
            assert current.locator(".music-track-text").evaluate("node=>node.scrollHeight>node.clientHeight")
            expect(current.locator(".music-style-panel")).to_be_visible()
            current.get_by_role("button", name="Lyrics", exact=True).click()
            expect(current.get_by_role("button", name="Lyrics", exact=True)).to_have_attribute("aria-pressed", "true")
            expect(inline).to_be_visible()
            expect(page.locator(".music-lyrics-dialog")).to_have_count(0)
            assert current.locator(".music-track-text").evaluate("node=>node.clientHeight") == content_height
            expect(inline.get_by_role("heading", name="Verse", exact=True)).to_be_visible()
            expect(inline.locator(".music-lyrics-line")).to_have_count(33)
            assert (
                inline.locator(".music-lyrics-line").first.evaluate(
                    "node => parseFloat(getComputedStyle(node).fontSize)"
                )
                == 15
            )
            expect(current.locator(".music-song-style")).to_be_hidden()
            expect(page.locator("#music-style")).to_have_value("My editable draft style")
            current.get_by_role("button", name="Play", exact=True).click()
            page.wait_for_function("!document.querySelector('.music-song[data-song-id=inline-0] audio').paused")
            current.locator("audio").evaluate("audio=>{window.inlineAudio=audio;audio.loop=true;}")
            content = current.locator(".music-track-text")
            assert content.evaluate("node=>node.scrollHeight>node.clientHeight")
            content.focus()
            page.keyboard.press("End")
            page.wait_for_function(
                "document.querySelector('.music-song[data-song-id=inline-0] .music-track-text').scrollTop>0"
            )
            assert page.evaluate("!window.inlineAudio.paused")
            toggle.click()
            expect(current.locator(".music-style-panel")).to_be_visible()
            expect(toggle).to_have_attribute("aria-pressed", "false")
            assert page.evaluate("!window.inlineAudio.paused")
            toggle.focus()
            page.keyboard.press("Enter")
            expect(toggle).to_have_attribute("aria-pressed", "true")
            page.evaluate("document.querySelector('music-studio').renderSongs()")
            expect(inline).to_be_visible()
            expect(toggle).to_have_attribute("aria-pressed", "true")
            assert page.evaluate("window.inlineAudio.isConnected && !window.inlineAudio.paused")
            expect(page.get_by_role("button", name="Expand lyrics", exact=True)).to_have_count(0)
            expect(page.locator(".music-lyrics-dialog")).to_have_count(0)
            page.locator(".music-output-details:not([hidden]) .prompt-line").click()
            details = page.get_by_role("dialog", name="Music details", exact=True)
            expect(details.locator("dd").filter(has_text="Detailed style stays in the metadata")).to_be_visible()
            page.get_by_role("button", name="Close music details", exact=True).click()
            page.get_by_role("button", name="Select song 2", exact=True).click()
            instrumental = page.locator('.music-song[data-song-id="inline-1"]')
            expect(instrumental.locator(".music-inline-lyrics")).to_have_text("Instrumental")
            expect(instrumental.get_by_role("button", name="Lyrics", exact=True)).to_be_disabled()
            assert page.evaluate("!window.inlineAudio.paused")
            for song_index in [1, 3, 4, 5]:
                page.get_by_role("button", name=f"Select song {song_index + 1}", exact=True).click()
                empty_song = page.locator(f'.music-song[data-song-id="inline-{song_index}"]')
                disabled_toggle = empty_song.get_by_role("button", name="Lyrics", exact=True)
                expect(disabled_toggle).to_be_visible()
                expect(disabled_toggle).to_be_disabled()
                expect(disabled_toggle).to_have_attribute("aria-pressed", "false")
                expect(empty_song.locator(".music-style-panel")).to_be_visible()
                expect(empty_song.locator(".music-inline-lyrics")).to_be_hidden()
                appearance = disabled_toggle.evaluate("""button => {
                  const style = getComputedStyle(button);
                  return {opacity:Number(style.opacity), color:style.color,
                    cursor:style.cursor, stroke:getComputedStyle(button.querySelector('svg')).stroke};
                }""")
                assert appearance["opacity"] == 0.45, appearance
                assert appearance["color"] == "rgb(136, 136, 136)", appearance
                assert appearance["stroke"] == appearance["color"], appearance
                assert appearance["cursor"] == "default", appearance
                empty_song.locator(".music-track-text").focus()
                disabled_toggle.evaluate("button=>button.focus()")
                assert not disabled_toggle.evaluate("button=>document.activeElement===button")
                page.keyboard.press("Enter")
                page.keyboard.press("Space")
                disabled_toggle.evaluate("button=>button.click()")
                expect(disabled_toggle).to_have_attribute("aria-pressed", "false")
                expect(empty_song.locator(".music-style-panel")).to_be_visible()
                assert page.evaluate("!window.inlineAudio.paused")
            page.get_by_role("button", name="Select score 3", exact=True).click()
            score = page.locator('.music-song[data-song-id="inline-2"]')
            expect(score.locator(".music-inline-lyrics")).to_have_count(0)
            expect(score.locator(".music-song-style")).to_contain_text("Detailed style stays in the metadata")
            expect(score.get_by_role("button", name="Lyrics", exact=True)).to_have_count(0)
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
            assert not errors, errors
            page.close()
        browser.close()
    print(
        "PASS inline lyrics: full lines, section labels, scrolling, playback, icon toggle, style details, and empty states"
    )


if __name__ == "__main__":
    main()
