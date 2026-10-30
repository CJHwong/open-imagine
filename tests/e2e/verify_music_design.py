"""Check the Music design against the other three workspaces, on a fresh studio stub server."""

import io
import sys
import time
import wave

from playwright.sync_api import expect, sync_playwright

URL = "http://127.0.0.1:" + sys.argv[1]


def check(name, condition):
    assert condition, name
    print("PASS " + name, flush=True)


reference = io.BytesIO()
with wave.open(reference, "wb") as wav:
    wav.setparams((1, 2, 24000, 2400, "NONE", "not compressed"))
    wav.writeframes(bytes(4800))

with sync_playwright() as tool:
    browser = tool.chromium.launch()
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(URL + "/?workspace=music")
    page.wait_for_function("Boolean(document.getElementById('music-studio').capabilities)")

    # The run button is the shared one, drawn by the same component as the other workspaces.
    check("Music uses the shared run component", page.locator("#music-generate > run-button").count() == 1)
    check(
        "all workspaces use the shared run style",
        page.locator(
            "#go.run-button, #video-generate.run-button, #voice-generate.run-button, #music-generate.run-button"
        ).count()
        == 4,
    )
    check("the footer uses the shared caption classes", page.locator("#music-go-sub.sub.num").count() == 1)
    check("the idle run verb is the shared Generate", page.locator("#music-run-labels").inner_text() == "Generate")
    check(
        "the run caption names what this mode makes", page.locator("#music-go-sub").inner_text() == "A song with audio"
    )

    # The empty pane is the shared one, not a bespoke illustration.
    empty = page.locator(".music-empty")
    expect(empty).to_be_visible()
    check("the empty pane uses the shared skeleton", "empty" in empty.get_attribute("class").split())
    check("the empty pane carries a mark", empty.locator(".video-empty-mark").inner_text() == "MUSIC")
    check("the empty pane offers one action", empty.locator(".btn").count() == 1)
    check("the empty pane holds no record player", empty.locator(".music-turntable").count() == 0)
    check("an empty stage hides the gallery", page.locator(".music-gallery").is_hidden())
    check(
        "the Lyrics box shows its whole placeholder",
        int(page.locator("#music-lyrics").get_attribute("rows")) >= 5
        and page.locator("#music-lyrics").bounding_box()["height"]
        > page.locator("#music-style").bounding_box()["height"],
    )
    check(
        "the section-tag guide starts folded", page.locator(".music-tag-guide").evaluate("node => node.open") is False
    )
    page.locator(".music-tag-guide summary").click()
    check(
        "the Lyrics hint names the section tags",
        [item.inner_text().split("]")[0] + "]" for item in page.locator(".music-lyrics-tags li").all()]
        == ["[Intro]", "[Verse]", "[Pre-Chorus]", "[Chorus]", "[Bridge]", "[Instrumental]", "[Outro]"],
    )
    empty.get_by_role("button", name="Write a style", exact=True).click()
    check(
        "the empty action focuses the style",
        page.locator("#music-style").evaluate("node => node === document.activeElement"),
    )

    # Music offers two outputs. A reference recording is the source, so it turns Generate
    # into a cover and Compose into a transcription, without a third and fourth button.
    modes = page.get_by_role("radiogroup", name="Music mode", exact=True)
    check("Music uses native mode radios", modes.locator('input[type="radio"][name="music-workflow"]').count() == 2)
    check(
        "the two outputs are named",
        [label.inner_text() for label in modes.locator("label").all()] == ["Generate", "Compose"],
    )
    check("the reference field is offered in Generate", page.locator(".music-reference-fields").is_visible())
    check(
        "the reference field names what Generate does with a recording",
        page.locator("#music-reference-note").inner_text() == "Optional. Generate makes a cover.",
    )
    check(
        "the reference zone reads its lines from the left",
        page.locator("#music-reference-choose").evaluate("node => getComputedStyle(node).textAlign")
        in ("left", "start"),
    )
    for mode, caption, hint, action, engine in [
        (
            "generate",
            "A song with audio",
            "Write a style and lyrics, or add a recording to cover it.",
            "Write a style",
            "generate",
        ),
        ("plan", "Sheet music only", "Write a style and lyrics to compose sheet music.", "Write a style", "plan"),
    ]:
        page.locator('label[for="music-mode-' + mode + '"]').click()
        check("Mode " + mode + " updates the caption", page.locator("#music-go-sub").inner_text() == caption)
        check("Mode " + mode + " sets the engine mode", page.locator("#music-mode").input_value() == engine)
        check("Mode " + mode + " explains itself in the stage", page.locator("#music-empty-hint").inner_text() == hint)
        check("Mode " + mode + " offers one right action", page.locator("#music-write").inner_text() == action)
    check("the two outputs are one radio group", page.locator('input[name="music-workflow"]:checked').count() == 1)
    page.locator('label[for="music-mode-plan"]').click()
    check(
        "the Compose empty pane sits in the middle of the stage",
        page.evaluate("""() => {
          const middle = node => {
            const box = node.getBoundingClientRect();
            return {x: box.x + box.width / 2, y: box.y + box.height / 2};
          };
          const empty = middle(document.querySelector('.music-empty'));
          const pane = middle(document.querySelector('.music-preview-pane'));
          return Math.abs(empty.x - pane.x) <= 2 && Math.abs(empty.y - pane.y) <= 2;
        }"""),
    )

    # The recording, not a fourth radio, is the switch.
    page.locator("#music-reference").set_input_files(
        {"name": "reference.wav", "mimeType": "audio/wav", "buffer": reference.getvalue()}
    )
    check("a recording turns Compose into a transcription", page.locator("#music-mode").input_value() == "transcribe")
    check(
        "the transcription caption names the source",
        page.locator("#music-go-sub").inner_text() == "A score from your recording",
    )
    check(
        "the stage says the recording becomes a score",
        page.locator("#music-empty-hint").inner_text()
        == "Your recording becomes an editable score. Choose what to keep.",
    )
    check(
        "the empty action moves to what a transcription keeps",
        page.locator("#music-write").inner_text() == "Choose what to keep",
    )
    check("no fourth mode button appears", page.locator("#music-mode-transcribe, #music-mode-cover").count() == 0)
    page.locator('label[for="music-mode-generate"]').click()
    check("a recording turns Generate into a cover", page.locator("#music-mode").input_value() == "cover")
    check(
        "the cover caption names the source",
        page.locator("#music-go-sub").inner_text() == "A new song from your recording",
    )
    check(
        "the cover keeps Style and Lyrics",
        page.locator("#music-style").is_visible() and page.locator("#music-lyrics").is_visible(),
    )
    check("the reference names what a cover keeps", page.locator(".music-reference-scope").is_visible())
    page.locator("#music-reference-remove").click()
    check("removing the recording returns to Generate", page.locator("#music-mode").input_value() == "generate")

    # The panel groups its controls the way the other forms do.
    presets = page.locator("#music-style-presets")
    check("Style presets is a disclosure row", presets.evaluate("node => node.tagName") == "DETAILS")
    check("Style presets shares the Look summary", presets.locator("summary look-values.values").count() == 1)
    check("Style presets reuses the Look rows", presets.locator("look-rows.look").count() == 1)
    check(
        "Style presets is not nested in the Style field",
        presets.evaluate("node => !node.closest('section')"),
    )
    advanced = page.locator(".music-advanced-fields")
    check("Advanced shows a summary", advanced.locator("summary .values.num").count() == 1)
    check(
        "the Advanced summary names the current settings",
        page.locator("#music-advanced-values").inner_text() == "32 steps, guidance 1, random seed",
    )
    advanced.locator("summary").click()
    check(
        "every Advanced field explains itself",
        advanced.locator(".advanced .field").count() == advanced.locator(".advanced .field > .caption").count(),
    )
    check(
        "Advanced holds no hidden workflow switch",
        page.get_by_role("checkbox", name="Skip audio rendering").count() == 0,
    )

    # One sentence about instrumental output, not two.
    check(
        "the instrumental hint appears once",
        page.get_by_text("Leave blank for instrumental.", exact=False).count() == 1,
    )

    # Cancel uses the same seam the page uses to hand the workspace its operation. The
    # page's own poll reports the stub server as idle, so the route keeps the operation
    # alive for as long as this block needs it.
    page.route("**/api/v1/operations/*/cancel", lambda route: route.fulfill(status=204, body=""))
    client = page.evaluate("() => CLIENT_ID")
    running = {
        "id": "stub-operation",
        "kind": "music",
        "workspace": "music",
        "status": "running",
        "mode": "generate",
        "client_id": client,
        "started_at": time.time() - 2,
        "progress": {"step": 50, "total": 100},
    }
    page.route(
        "**/api/v1/state",
        lambda route: route.fulfill(json={"active": running, "operations": [running], "studio": {}}),
    )
    cancellations = []
    page.on("request", lambda request: cancellations.append(request.url) if request.url.endswith("/cancel") else None)
    page.evaluate(
        """(operation) => document.getElementById('music-studio').setOperation(operation)""",
        {
            "id": "stub-operation",
            "kind": "music",
            "status": "running",
            "mode": "generate",
            "client_id": client,
            "started_at": time.time() - 2,
            "progress": {"step": 50, "total": 100},
        },
    )
    check("a running operation uses Cancel", page.locator("#music-run-labels").inner_text() == "Cancel")
    check(
        "a running operation explains what stopping keeps",
        page.locator("#music-go-sub").inner_text() == "Finished songs remain if you stop",
    )
    check(
        "a run draws the player's own timeline",
        page.locator(".music-generation-timeline input[type=range]").count() == 1
        and page.locator(".music-generation-timeline input").is_disabled(),
    )
    check(
        "the timeline fills with the sampler's share", page.locator(".music-generation-percent").inner_text() == "50%"
    )
    page.locator("#music-generate").click()
    page.wait_for_function("document.getElementById('music-run-labels').getAttribute('data-state') === 'stopping'")
    check("the shared stopping label stays consistent", page.locator("#music-run-labels").inner_text() == "Stopping…")
    check("Stopping prevents a second cancellation", page.locator("#music-generate").is_disabled())
    check("Cancel sends one request", cancellations == [URL + "/api/v1/operations/stub-operation/cancel"])
    page.unroute("**/api/v1/state")
    page.evaluate("() => document.getElementById('music-studio').setOperation(null)")
    check("the idle verb comes back", page.locator("#music-run-labels").inner_text() == "Generate")

    check("the browser reports no page errors", not errors)
    for width, height in [(900, 600), (390, 700)]:
        compact = browser.new_context(viewport={"width": width, "height": height})
        narrow = compact.new_page()
        narrow.goto(URL + "/?workspace=music")
        narrow.wait_for_function("Boolean(document.getElementById('music-studio').capabilities)")
        check(
            f"the two choices fit {width} by {height}",
            narrow.locator("#music-controls").evaluate("node => node.scrollWidth <= node.clientWidth"),
        )
        check(
            f"the empty pane fits {width} by {height}",
            narrow.locator("#music-studio").evaluate("node => node.scrollWidth <= node.clientWidth"),
        )
        compact.close()
    browser.close()
