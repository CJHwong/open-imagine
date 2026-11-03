"""The run sheet from the generating card, in all four workspaces.

Every workspace offers Details on its generating card, and one sheet shows what
the page sent plus the values that move. Run against a fresh stub server:

uv run studio --stub --port <port>
uv run --with playwright python tests/e2e/verify_run_sheet.py <port>
"""

import re
import sys

from playwright.sync_api import expect, sync_playwright

BASE = "http://127.0.0.1:" + sys.argv[1]


def check(name, condition, detail=""):
    assert condition, (name, detail)
    print("PASS " + name, flush=True)


def sheet(page):
    page.wait_for_selector("#run-sheet", timeout=8000)
    return page.evaluate("""() => {
      const dialog = document.querySelector('#run-sheet');
      return {
        open: dialog.open,
        title: dialog.querySelector('h2').textContent,
        terms: [...dialog.querySelectorAll('dt')].map(node => node.textContent),
        values: [...dialog.querySelectorAll('dd')].map(node => node.textContent),
      };
    }""")


def row(data, term):
    index = data["terms"].index(term)
    return data["values"][index]


def main():
    with sync_playwright() as tool:
        browser = tool.chromium.launch()
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        # Music: a real stub run keeps the generating card up while the sheet opens.
        page.goto(BASE + "/?workspace=music")
        page.wait_for_selector("#music-style", timeout=20000)
        page.fill("#music-style", "Progressive house EDM, 126 BPM")
        page.fill("#music-lyrics", "[Verse]\nMidnight on the wire")
        page.click("#music-generate")
        page.wait_for_selector(".music-run-details", timeout=15000)
        page.click(".music-run-details")
        music = sheet(page)
        check("Music opens one run sheet", music["open"] and music["title"] == "This run", music)
        check("the style is the sentence that was sent", row(music, "Style") == "Progressive house EDM, 126 BPM")
        check("the lyric keeps its line break", row(music, "Lyrics") == "[Verse]\nMidnight on the wire")
        check("planning and steps are named", row(music, "Planning") == "full" and row(music, "Steps") == "32")
        check("the live block follows the run", row(music, "Status") == "Running", music)
        page.keyboard.press("Escape")
        expect(page.locator("#run-sheet")).to_have_count(0)
        # One operation at a time: the next workspace opens when this run ends.
        page.wait_for_function("document.querySelector('#music-generate')?.dataset.state === 'idle'", timeout=60000)

        # Image: the Details action rides on the progress card itself.
        page.goto(BASE + "/?workspace=image")
        page.wait_for_selector("#prompt", timeout=20000)
        page.fill("#prompt", "a red barn in a field")
        page.click("#go")
        page.wait_for_selector(".card-details", timeout=20000)
        page.click(".card-details")
        image = sheet(page)
        check("Image opens the sheet from its card", image["open"], image)
        check(
            "the prompt and the model are the run's own",
            row(image, "Prompt") == "a red barn in a field" and "QWEN" in row(image, "Model").upper(),
            image,
        )
        check("the steps come from the form", row(image, "Steps") == "8", image)
        page.keyboard.press("Escape")
        page.wait_for_selector(".card", state="detached", timeout=60000)

        # Video: the monitor state is driven, as the media suite does, because the stub
        # clip returns before a render can be watched.
        page.goto(BASE + "/?workspace=video")
        page.wait_for_selector("#video-prompt", timeout=20000)
        page.evaluate("""() => {
          const studio = document.getElementById('video-studio');
          studio.rememberRun({prompt: 'a slow pan over a rainy street', modelName: 'LTX 2.5',
            mode: 'generate', width: 1280, height: 720, numFrames: 121, frameRate: 24, seed: 42});
          studio.setGenerationProgress({running: true, stage: 'running', step: 3, total: 8}, 12,
            {width: 1280, height: 720, modelName: 'LTX 2.5'});
        }""")
        page.wait_for_selector(".video-run-details", timeout=8000)
        page.click(".video-run-details")
        video = sheet(page)
        check("Video opens the sheet from the render placeholder", video["open"], video)
        check(
            "the size, frames and seed are the run's own",
            bool(re.fullmatch(r"1280\s.\s720", row(video, "Size")))
            and row(video, "Frames") == "121"
            and row(video, "Seed") == "42",
            video,
        )
        check("the live step reads the monitor", row(video, "Step") == "3 / 8", video)
        page.keyboard.press("Escape")

        # Voice: a real stub run, started from the form.
        context.request.post(BASE + "/api/v1/voice/backend", data={"backend": "auk_base"})
        page.goto(BASE + "/?workspace=voice")
        page.wait_for_function("document.getElementById('voice-studio')?.ready")
        page.locator("#voice-text").fill("A calm narrator with a warm, clear voice.")
        page.locator("#voice-generate").click()
        page.wait_for_selector(".voice-run-details", timeout=15000)
        page.locator(".voice-run-details").click()
        voice = sheet(page)
        check("Voice opens the sheet from its generation block", voice["open"], voice)
        check(
            "the script is the line that was sent",
            row(voice, "Text") == "A calm narrator with a warm, clear voice.",
            voice,
        )
        page.keyboard.press("Escape")

        check("no page errors", not errors, errors)
        print("PASS Run sheet: one sheet, four generating cards, the sent fields and the live step.")
        browser.close()


main()
