"""Display-only Music and Voice copy, against a fresh all-backend stub."""

import json
import sys

from playwright.sync_api import expect, sync_playwright


def check_case(browser, base, locale, failures):
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    context.add_init_script("localStorage.setItem('studio-keep','off');localStorage.setItem('studio-autoplay','off')")
    page = context.new_page()
    page.goto(base + "/?workspace=music&lang=" + locale)
    page.locator("#music-style").fill("A gentle acoustic song.")
    page.locator("#music-lyrics").fill("[Verse]\nMorning light returns.")
    page.locator("#music-generate").click()
    play = page.locator(".music-song:not([hidden]) .music-play").first
    expect(play).to_be_enabled(timeout=30000)
    labels = page.evaluate("""async () => {
      const studio = document.querySelector('music-studio');
      const label = () => studio.querySelector('.music-song:not([hidden]) .music-playback-label').textContent;
      const audio = studio.querySelector('.music-song:not([hidden]) audio');
      const result = {initial: label()};
      await audio.play();
      result.playing = label();
      studio.renderSongs();
      result.redrawn = label();
      audio.pause();
      await new Promise(resolve => setTimeout(resolve, 0));
      result.paused = label();
      return result;
    }""")
    expected = "Test preview" if locale == "en" else "測試預覽"
    if any(value != expected for value in labels.values()):
        failures.append({"case": locale + "/music-test-badge", "labels": labels})
    context.request.post(base + "/api/v1/voice/backend", form={"backend": "drama3"})
    page.goto(base + "/?workspace=voice&lang=" + locale)
    page.wait_for_function("document.getElementById('voice-studio')?.capabilities?.backend_id === 'drama3'")
    page.locator("#voice-templates-toggle").click()
    page.get_by_role("menuitem", name="Whisper" if locale == "en" else "耳語", exact=True).click()
    field = page.locator(".voice-template-field")
    expected = "Text to read" if locale == "en" else "朗讀內容"
    if field.inner_text().strip() != expected:
        failures.append({"case": locale + "/voice-field-label", "label": field.inner_text()})
    field.locator("input").fill("A quiet test sentence.")
    page.route("**/voice/operations", lambda route: route.fulfill(status=400, body="Display test finished."))
    with page.expect_request(
        lambda request: request.method == "POST" and request.url.endswith("/voice/operations")
    ) as sent:
        page.locator("#voice-generate").click()
    payload = sent.value.post_data_json
    assert payload["template"] == "Whisper"
    assert payload["template_values"]["script"] == "A quiet test sentence."
    assert payload["template_locale"] == locale
    print("CHECK", locale, flush=True)
    context.close()


def main():
    failures = []
    with sync_playwright() as tool:
        engine = tool.webkit if "--webkit" in sys.argv else tool.chromium
        browser = engine.launch()
        for locale in ["en", "zh-TW"]:
            check_case(browser, "http://127.0.0.1:" + sys.argv[1], locale, failures)
        browser.close()
    print("FAILURES", len(failures), json.dumps(failures, ensure_ascii=False), flush=True)
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
