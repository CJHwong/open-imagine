"""Real Music browser proof. Requires an owned server and exclusive GPU slot.

uv run --with playwright python tests/e2e/verify_music_live.py <port>
Makes two short recordings, edits an ABC score, then cancels another run.
"""

import sys
import time

from playwright.sync_api import expect, sync_playwright

SCORE = (
    "X:1\nT:Original UI verification\nM:4/4\nL:1/4\nQ:1/4=100\n"
    'V: Vocal clef=treble name="Vocal Melody"\nV: Ins clef=treble name="Instrumental"\nK:C\n'
    '% verse\nV: Vocal\n"C"C2E2|"Am"G2E2|"F"F2A2|"G"G4|\n'
    "V: Ins\nC,2G,2|A,2E,2|F,2C2|G,4|\n"
)


def main():
    base = f"http://127.0.0.1:{int(sys.argv[1])}"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/?workspace=music")
        page.locator("#music-style").fill("English, warm piano pop, clear vocals, piano, bass, 100 BPM")
        page.locator("#music-lyrics").fill("[Verse]\nMorning settles on the street\nEvery window keeps a beat")
        page.locator(".music-advanced-fields summary").click()
        page.locator("#music-seed").fill("42")
        page.locator("#music-abc-edit").click()
        page.locator("#music-abc").fill(SCORE)
        page.locator("#music-abc-close").click()
        page.locator("#music-steps").select_option("8")
        page.locator("#music-generate").click()
        expect(page.locator(".music-song")).to_have_count(1, timeout=240000)
        current = page.locator(".music-song:not([hidden])")
        expect(page.get_by_role("dialog", name="Sheet music and chords")).to_be_hidden()
        page.get_by_role("button", name="More actions", exact=True).click()
        page.get_by_role("menuitem", name="Sheet music and chords", exact=True).click()
        expect(
            page.get_by_role("dialog", name="Sheet music and chords").locator(".music-notation svg").first
        ).to_be_visible(timeout=30000)
        page.get_by_role("button", name="Close sheet music", exact=True).click()
        current.locator("audio").evaluate("audio=>{audio.loop=true;return audio.play();}")
        expect(current).to_have_class("music-song is-playing")
        current.locator("audio").evaluate("audio=>audio.pause()")
        page.get_by_role("button", name="Score", exact=True).click()
        page.get_by_role("dialog", name="Sheet music and chords").get_by_role(
            "button", name="Edit and render score", exact=True
        ).click()
        expect(page.locator("#music-abc")).to_have_value(SCORE)
        edited = SCORE.replace("C2E2", "E2G2")
        page.locator("#music-abc").fill(edited)
        page.locator("#music-abc-close").click()
        page.locator("#music-style").fill("English, warm piano pop, clear vocals, piano, bass, 100 BPM")
        page.locator("#music-generate").click()
        expect(page.locator(".music-song")).to_have_count(2, timeout=240000)
        assert page.locator("#music-studio").evaluate("node=>node.songs.at(-1).score") == edited
        page.locator("#music-abc-edit").click()
        page.locator("#music-abc").fill("")
        page.locator("#music-abc-close").click()
        page.locator("#music-seed").fill("12345")
        page.locator("#music-style").fill("English, warm piano pop, clear vocals, piano, bass, 100 BPM")
        with page.expect_response("**/music/operations") as answer:
            page.locator("#music-generate").click()
        operation = answer.value.json()
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            state = page.request.get(base + operation["status_url"]).json()
            if state.get("progress", {}).get("step", 0) > 0:
                break
            page.wait_for_timeout(100)
        page.locator("#shared-operation-cancel").click()
        for _ in range(100):
            state = page.request.get(base + operation["status_url"]).json()
            if state["status"] == "cancelled":
                break
            page.wait_for_timeout(100)
        assert state["status"] == "cancelled", state
        expect(page.locator(".music-song")).to_have_count(2)
        assert errors == [], errors
        browser.close()
    print("PASS real Music browser: generate, sheet music, playback, edit/render exact ABC, cancel during generation.")


if __name__ == "__main__":
    main()
