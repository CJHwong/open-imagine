"""Music workflows on a fresh stub: two outputs, and a recording that switches the engine.

uv run --with playwright python tests/e2e/verify_music_workflows.py <port>
No model is loaded. Transcription exports are fixtures; runtime exports have unit coverage.
"""

import base64
import io
import sys
import wave

from playwright.sync_api import expect, sync_playwright


def verify_automatic_instrumental(browser, base):
    """Blank words imply instrumental without hiding the optional lyrics editor."""
    page = browser.new_page()
    submitted = []
    page.on(
        "request",
        lambda request: (
            submitted.append(request.post_data_json)
            if request.method == "POST" and request.url.endswith("/operations")
            else None
        ),
    )

    def metadata(route):
        answer = route.fetch()
        route.fulfill(
            response=answer, json={**answer.json(), "score": 'X:1\nT:Stub planned score\nM:4/4\nL:1/4\nK:C\n"C"CDEF|'}
        )

    page.route("**/operations/*/metadata", metadata)
    page.goto(base + "/?workspace=music")
    page.locator("#music-style").fill("Gentle acoustic piano")
    expect(page.locator("#music-instrumental")).to_have_count(0)
    expect(page.locator("#music-lyrics")).to_be_visible()
    for count, lyrics, instrumental in [(1, "", True), (2, "  \n\t ", True), (3, "[Verse]\nMorning melody", False)]:
        page.locator("#music-lyrics").fill(lyrics)
        expect(page.locator("#music-generate")).to_be_enabled()
        page.locator("#music-generate").click()
        expect(page.locator(".music-song")).to_have_count(count)
        assert submitted[-1]["instrumental"] is instrumental
        expect(page.locator("#music-instrumental")).to_have_count(0)
        expect(page.locator("#music-lyrics")).to_be_visible()
        if count == 2:
            page.reload()
            expect(page.locator(".music-song")).to_have_count(2)
            expect(page.locator("#music-instrumental")).to_have_count(0)
            expect(page.locator("#music-lyrics")).to_be_visible()
            page.locator("#music-studio").evaluate("""studio=>{
              for(const song of studio.songs) song.settings={...song.settings,instrumental:true,lyrics:'Old ignored words'};
            }""")
            bar = page.locator(".music-output-details:not([hidden])")
            bar.get_by_role("button", name="More actions", exact=True).click()
            bar.get_by_role("menuitem", name="Reuse style and lyrics", exact=True).click()
            expect(page.locator("#music-instrumental")).to_have_count(0)
            expect(page.locator("#music-lyrics")).to_be_visible()
            expect(page.locator("#music-lyrics")).to_have_value("")
            page.locator("#music-lyrics").fill("Words to replace")
            bar.get_by_role("button", name="Score", exact=True).click()
            page.get_by_role("dialog", name="Sheet music and chords").get_by_role(
                "button", name="Edit and render score", exact=True
            ).click()
            expect(page.locator("#music-instrumental")).to_have_count(0)
            expect(page.locator("#music-lyrics")).to_be_visible()
            expect(page.locator("#music-lyrics")).to_have_value("")
    # Older drafts could keep words while an explicit instrumental switch was on.
    page.evaluate("""async()=>{
      const {saveMusicDraft}=await import('/page/lib/music-store.js');
      const studio=document.querySelector('#music-studio');
      await saveMusicDraft({...studio.savedDraft(),lyrics:'[Verse]\\nPreviously ignored words',instrumental:true});
    }""")
    page.reload()
    expect(page.locator("#music-instrumental")).to_have_count(0)
    expect(page.locator("#music-lyrics")).to_be_visible()
    expect(page.locator("#music-lyrics")).to_have_value("")
    page.locator("#music-generate").click()
    expect(page.locator(".music-song")).to_have_count(4)
    assert submitted[-1]["instrumental"] is True
    page.close()


def main():
    base = f"http://127.0.0.1:{int(sys.argv[1])}"
    audio = io.BytesIO()
    with wave.open(audio, "wb") as wav:
        wav.setparams((1, 2, 24000, 2400, "NONE", "not compressed"))
        wav.writeframes(bytes(4800))
    midi = b"MThd\x00\x00\x00\x06\x00\x00\x00\x01\x00\x60MTrk\x00\x00\x00\x04\x00\xff\x2f\x00"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors, submitted = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on(
            "request",
            lambda request: (
                submitted.append(request.post_data_json)
                if request.method == "POST" and request.url.endswith("/operations")
                else None
            ),
        )

        def metadata(route):
            answer = route.fetch()
            body = answer.json()
            if body.get("metadata", {}).get("mode") == "transcribe":
                body["metadata"]["artifacts"] = [
                    {
                        "name": "composition.mid",
                        "content_type": "audio/midi",
                        "base64": base64.b64encode(midi).decode(),
                    },
                    {
                        "name": "melody_vocal.mid",
                        "content_type": "audio/midi",
                        "base64": base64.b64encode(midi).decode(),
                    },
                    {
                        "name": "chords.lab",
                        "content_type": "text/plain",
                        "base64": base64.b64encode(b"0.0\t2.0\tC\n").decode(),
                    },
                    {
                        "name": "key.lab",
                        "content_type": "text/plain",
                        "base64": base64.b64encode(b"0.0\t2.0\tC major\n").decode(),
                    },
                    {
                        "name": "beat.lab",
                        "content_type": "text/plain",
                        "base64": base64.b64encode(b"0.0\t1\n").decode(),
                    },
                ]
            route.fulfill(response=answer, json=body)

        page.route("**/operations/*/metadata", metadata)
        page.goto(base + "/?workspace=music")
        expect(page.locator("#workspace-tabs button")).to_have_text(["Image", "Video", "Voice", "Music"])
        expect(page.locator("#backend-toggle .name")).to_have_text("YuE2")
        expect(page.locator("#music-empty-hint")).to_have_text(
            "Write a style and lyrics, or add a recording to cover it."
        )
        expect(page.get_by_text("Write a style and lyrics, then generate music.", exact=True)).to_have_count(0)
        expect(page.get_by_role("radiogroup", name="Music mode")).to_have_class("modes")
        expect(page.locator("#music-mode-generate")).to_be_checked()
        expect(page.locator("#music-mode-plan")).to_be_enabled()
        assert page.evaluate("""() => {
          const properties=['display','marginTop','marginBottom','height','gap','fontSize','alignItems','justifyContent'];
          const music=getComputedStyle(document.querySelector('label[for="music-mode-generate"]'));
          const image=getComputedStyle(document.querySelector('label[for="mode-generate"]'));
          return properties.every(property=>music[property]===image[property]);
        }"""), "Music mode labels do not match the shared Image mode styling"
        expect(page.locator("#music-controls select#music-output")).to_have_count(0)
        expect(page.get_by_role("radiogroup", name="Music mode").get_by_role("radio")).to_have_count(2)
        expect(page.locator("#music-controls .music-advanced-fields")).to_have_count(1)
        advanced = page.locator(".music-advanced-fields")
        assert not advanced.evaluate("node=>node.open")
        # The recording is the switch, so its door is always open.
        expect(page.locator(".music-reference-fields")).to_be_visible()
        expect(page.locator("#music-reference-choose")).to_be_visible()
        expect(page.locator(".music-reference-scope")).to_be_hidden()
        expect(page.locator("#music-generate")).to_be_disabled()
        page.locator("#music-style").fill("Warm piano pop")
        page.locator("#music-lyrics").fill("[Verse]\nMorning settles on the street")
        advanced.locator("summary").click()
        page.locator("#music-seed").fill("42")
        page.locator("#music-cfg-scale").fill("9")
        page.locator("#music-steps").select_option("8")
        page.locator('label[for="music-mode-plan"]').click()
        expect(page.locator("#music-mode")).to_have_value("plan")
        expect(page.locator("#music-go-sub")).to_have_text("Sheet music only")
        expect(page.locator("#music-steps")).to_be_hidden()
        page.locator("#music-generate").click()
        expect(page.locator(".music-song.is-score")).to_have_count(1)
        expect(page.locator(".music-song audio")).to_have_count(0)
        expect(page.locator(".music-count")).to_have_text("0 songs, 1 score")
        bar = page.locator(".music-output-details:not([hidden])")
        expect(bar.get_by_role("button", name="Score", exact=True)).to_be_enabled()
        bar.get_by_role("button", name="More actions", exact=True).click()
        expect(bar.get_by_role("menuitem", name="Send to Video", exact=True)).to_be_disabled()
        page.keyboard.press("Escape")
        assert submitted[-1]["mode"] == "plan"
        assert submitted[-1]["steps"] == 32 and submitted[-1]["cfg_scale"] == 1
        score = page.locator("#music-studio").evaluate("node=>node.songs[0].score")
        assert score.startswith("X:")
        page.reload()
        expect(page.locator("#music-mode")).to_have_value("plan")
        expect(page.locator("#music-mode-plan")).to_be_checked()
        expect(page.locator(".music-song.is-score")).to_have_count(1)
        assert not advanced.evaluate("node=>node.open")
        bar.get_by_role("button", name="Score", exact=True).click()
        page.get_by_role("dialog", name="Sheet music and chords").get_by_role(
            "button", name="Render score", exact=True
        ).click()
        assert advanced.evaluate("node=>node.open"), "Render score did not reveal Advanced"
        expect(page.locator("#music-abc")).to_be_visible()
        expect(page.locator("#music-mode")).to_have_value("generate")
        expect(page.locator("#music-mode-generate")).to_be_checked()
        expect(page.locator("#music-abc")).to_have_value(score)
        expect(page.locator("#music-instrumental")).to_have_count(0)
        page.locator("#music-lyrics").fill("")
        expect(page.locator("#music-lyrics")).to_be_visible()
        advanced.evaluate("node=>node.open=true")
        page.locator("#music-steps").select_option("8")
        page.locator("#music-cfg-scale").fill("1.4")
        page.locator("#music-count").select_option("2")
        page.locator("#music-generate").click()
        expect(page.locator(".music-song")).to_have_count(3)
        assert submitted[-1]["items"] == [{"seed": 42}, {"seed": 43}]
        assert submitted[-1]["steps"] == 8 and submitted[-1]["cfg_scale"] == 1.4
        assert submitted[-1]["instrumental"] is True and submitted[-1]["abc"] == score
        expect(page.locator(".music-song audio")).to_have_count(2)

        # A recording turns Generate into a cover, in place.
        page.locator("#music-seed").fill("-1")
        page.locator("#music-cfg-scale").fill("9")
        page.locator('label[for="music-mode-generate"]').click()
        with page.expect_file_chooser() as chosen:
            page.locator("#music-reference-choose").click()
        chosen.value.set_files({"name": "reference.wav", "mimeType": "audio/wav", "buffer": audio.getvalue()})
        expect(page.locator("#music-mode")).to_have_value("cover")
        expect(page.locator("#music-go-sub")).to_have_text("A new song from your recording")
        expect(page.locator("#music-reference-name")).to_have_text("reference.wav")
        expect(page.locator(".music-reference-preview.video-audios > .video-audio")).to_be_visible()
        expect(page.locator("#music-reference-remove.video-audio-remove")).to_be_visible()
        expect(page.locator("#music-reference-choose")).to_be_hidden()
        expect(page.locator(".music-reference-scope")).to_be_visible()
        expect(page.locator("#music-style")).to_be_visible()
        expect(page.locator("#music-transcription-task")).to_be_visible()
        expect(page.locator("#music-generate")).to_be_enabled()
        with page.expect_file_chooser() as replaced:
            page.locator("#music-reference-replace").click()
        replaced.value.set_files({"name": "reference.wav", "mimeType": "audio/wav", "buffer": audio.getvalue()})
        expect(page.locator("#music-reference-name.video-audio-name")).to_have_text("reference.wav")
        expect(page.locator(".music-reference-preview .video-audio")).to_have_count(1)
        assert page.evaluate("""() => {
          const style=document.querySelector('#music-style');
          const reference=document.querySelector('.music-reference-fields');
          const lyrics=document.querySelector('#music-lyrics');
          return Boolean(style.compareDocumentPosition(reference)&Node.DOCUMENT_POSITION_FOLLOWING)
            && Boolean(reference.compareDocumentPosition(lyrics)&Node.DOCUMENT_POSITION_FOLLOWING);
        }"""), "Cover fields must follow Style, Reference audio, Lyrics in actual DOM order"

        # The two choices are the mode radios; the recording stays the source across them.
        page.locator("#media-voice-mode").click()
        expect(page.locator("#music-studio")).to_be_hidden()
        page.locator("#media-music-mode").click()
        expect(page.locator("#music-studio")).to_be_visible()
        page.reload()
        expect(page.locator("#music-mode")).to_have_value("cover")
        expect(page.locator("#music-mode-generate")).to_be_checked()
        expect(page.locator("#music-reference-name")).to_have_text("reference.wav")
        page.locator("#music-mode-generate").focus()
        page.keyboard.press("ArrowRight")
        expect(page.locator("#music-mode-plan")).to_be_checked()
        expect(page.locator("#music-mode")).to_have_value("transcribe")
        expect(page.locator("#music-go-sub")).to_have_text("A score from your recording")
        expect(page.locator("#music-style")).to_be_hidden()
        expect(page.locator("#music-lyrics")).to_be_hidden()
        page.keyboard.press("ArrowLeft")
        expect(page.locator("#music-mode-generate")).to_be_checked()
        expect(page.locator("#music-mode")).to_have_value("cover")
        page.keyboard.press("ArrowRight")
        expect(page.locator("#music-mode-transcribe, #music-mode-cover")).to_have_count(0)
        expect(page.locator("#music-controls audio, #music-controls video")).to_have_count(0)
        page.locator("#music-transcription-task").select_option("full")
        expect(page.locator("#music-generate")).to_be_enabled()
        page.locator("#music-generate").click()
        expect(page.locator(".music-song.is-score")).to_have_count(2)
        assert submitted[-1]["mode"] == "transcribe" and submitted[-1]["transcription_task"] == "full"
        assert base64.b64decode(submitted[-1]["reference_audio"]) == audio.getvalue()
        assert "items" not in submitted[-1]
        assert submitted[-1]["abc"] == ""
        assert submitted[-1]["seed"] is None
        assert submitted[-1]["steps"] == 32 and submitted[-1]["cfg_scale"] == 1
        expect(bar.get_by_role("button", name="Score", exact=True)).to_be_visible()
        expect(page.locator(".music-score-popover:popover-open")).to_have_count(0)
        bar.get_by_role("button", name="More actions", exact=True).click()
        bar.get_by_role("menuitem", name="Sheet music and chords", exact=True).click()
        expect(page.get_by_role("dialog", name="Sheet music and chords", exact=True)).to_be_visible()
        with page.expect_download() as downloaded:
            page.locator(".music-song:not([hidden])").get_by_role(
                "link", name="Download MIDI · Composition", exact=True
            ).click()
        assert downloaded.value.path().read_bytes() == midi
        for label in [
            "Download MIDI · Vocal melody",
            "Download LAB · Chords",
            "Download LAB · Key",
            "Download LAB · Beat",
        ]:
            expect(
                page.locator(".music-song:not([hidden])").get_by_role("link", name=label, exact=True)
            ).to_be_visible()
        page.get_by_role("button", name="Close sheet music", exact=True).click()

        # A cover keeps Style and Lyrics and starts from the recording's composition.
        page.locator('label[for="music-mode-generate"]').click()
        expect(page.locator("#music-mode")).to_have_value("cover")
        page.locator("#music-lyrics").fill("[Verse]\nA different morning song")
        advanced.evaluate("node=>node.open=true")
        page.locator("#music-steps").select_option("16")
        page.locator("#music-seed").fill("43")
        page.locator("#music-cfg-scale").fill("0.8")
        page.locator("#music-count").select_option("1")
        page.locator("#music-generate").click()
        expect(page.locator(".music-song")).to_have_count(5)
        assert submitted[-1]["mode"] == "cover" and submitted[-1]["reference_name"] == "reference.wav"
        assert submitted[-1]["abc"] == "" and submitted[-1]["steps"] == 16
        bar.get_by_role("button", name="More actions", exact=True).click()
        expect(bar.get_by_role("menuitem", name="Generate artwork", exact=True)).to_be_visible()
        page.keyboard.press("Escape")
        page.locator("#music-reference-remove").click()
        expect(page.locator("#music-mode")).to_have_value("generate")
        expect(page.locator(".music-reference-scope")).to_be_hidden()
        expect(page.locator("#music-generate")).to_be_enabled()
        expect(page.locator("#music-controls audio, #music-controls video")).to_have_count(0)
        transfer = page.evaluate_handle(
            """encoded=>{
          const file=new File([Uint8Array.from(atob(encoded),byte=>byte.charCodeAt(0))],'dropped.wav',{type:'audio/wav'});
          const transfer=new DataTransfer();transfer.items.add(file);return transfer;
        }""",
            base64.b64encode(audio.getvalue()).decode(),
        )
        page.dispatch_event("#music-reference-drop", "drop", {"dataTransfer": transfer})
        transfer.dispose()
        expect(page.locator("#music-reference-name")).to_have_text("dropped.wav")
        expect(page.locator("#music-mode")).to_have_value("cover")
        expect(page.locator("#music-generate")).to_be_enabled()
        page.locator("#music-reference-remove").click()
        page.locator("#music-reference").set_input_files(
            {"name": "notes.txt", "mimeType": "text/plain", "buffer": b"not audio"}
        )
        expect(page.locator("#music-reference-name")).to_have_text("")
        expect(page.get_by_text("Choose an audio recording.", exact=True)).to_be_visible()
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.locator("#music-studio").evaluate("node=>node.scrollWidth<=node.clientWidth")
        assert errors == [], errors
        verify_automatic_instrumental(browser, base)
        browser.close()
    print(
        "PASS Music workflows: two outputs, score planning, render/edit, instrumental, advanced settings, "
        "variations, reference-driven cover and transcription, exports, drops and validation."
    )


if __name__ == "__main__":
    main()
