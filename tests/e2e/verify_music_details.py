"""Song labels, processing duration, score preview and editing on a stub."""

import io
import sys
import wave

from playwright.sync_api import expect, sync_playwright

SCORE = 'X:1\nM:4/4\nL:1/4\nK:C\n"C"CDEF|'


def main():
    source = io.BytesIO()
    with wave.open(source, "wb") as song:
        song.setparams((1, 2, 24000, 24000, "NONE", "not compressed"))
        song.writeframes(bytes(48000))
    base = f"http://127.0.0.1:{int(sys.argv[1])}"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.goto(base + "/?workspace=music")
        page.wait_for_function("Boolean(document.querySelector('music-studio').capabilities)")
        page.route("**/test-song/result", lambda route: route.fulfill(content_type="audio/wav", body=source.getvalue()))
        page.route(
            "**/test-song/metadata",
            lambda route: route.fulfill(
                json={"score": SCORE, "seconds": 1, "seed": 42, "metadata": {"private_fixture": "hidden raw value"}}
            ),
        )
        page.evaluate("""async () => {
          const studio = document.querySelector('music-studio');
          await studio.setKeeping(false);
          await studio.importSong({
            id:'details-song', started_at:100, finished_at:112.5, model:'YuE2',
            result_url:'/test-song/result', settings:{style:'piano', lyrics:'hello'}
          }, await fetch('/test-song/result'));
        }""")
        expect(page.locator(".music-count")).to_have_text("1 song")
        bar = page.locator(".music-output-details:not([hidden])")
        expect(bar.get_by_role("button", name="Score", exact=True)).to_be_visible()
        expect(bar.get_by_role("button", name="Edit score", exact=True)).to_have_count(0)
        expect(bar.locator(".facts")).to_contain_text("Generated in 12.5 s")
        bar.locator(".prompt-line").click()
        details = page.get_by_role("region", name="Music details", exact=True)
        expect(details.get_by_text("Generation time", exact=True)).to_be_visible()
        expect(details.get_by_text("12.5 seconds", exact=True)).to_be_visible()
        expect(details.get_by_text("Raw metadata", exact=True)).to_have_count(0)
        expect(details.get_by_text("hidden raw value", exact=True)).to_have_count(0)
        page.get_by_role("button", name="Close music details").click()
        page.locator("#music-abc").evaluate("input => input.value = 'unchanged draft'")
        bar.get_by_role("button", name="Score", exact=True).click()
        panel = page.get_by_role("dialog", name="Sheet music and chords", exact=True)
        expect(panel).to_be_visible()
        expect(page.locator("#music-abc")).to_have_value("unchanged draft")
        expect(panel.get_by_role("tab", name="Sheet music", exact=True)).to_be_visible()
        expect(panel.get_by_role("tab", name="Chords", exact=True)).to_be_visible()
        panel.get_by_role("button", name="Edit and render score", exact=True).click()
        expect(panel).to_be_hidden()
        editor = page.get_by_role("dialog", name="ABC score", exact=True)
        expect(editor).to_be_visible()
        expect(page.locator("#music-abc")).to_have_value(SCORE)
        page.locator("#music-abc-close").click()
        expect(editor).to_be_hidden()
        page.evaluate("""async () => {
          const studio = document.querySelector('music-studio');
          const manifest = {items:[{index:1, completed_at:150, result_url:'/test-song/result'}]};
          await studio.importOperation({
            id:'batch-song', batch_total:2, started_at:100, finished_at:150, model:'YuE2', settings:{style:'piano'}
          }, new Response(JSON.stringify(manifest)));
        }""")
        assert page.locator("#music-studio").evaluate("studio => studio.songs.at(-1).generationSeconds") is None
        expect(page.locator(".music-output-details:not([hidden]) .facts")).not_to_contain_text("Generated in")
        browser.close()
    print("PASS song labels, processing duration, no raw metadata, Score preview and explicit score editing")


if __name__ == "__main__":
    main()
