"""Localized template bodies, placeholders, stable Voice IDs and English fallback. CPU stub only."""

import re
import sys

from playwright.sync_api import expect, sync_playwright

BASE = "http://127.0.0.1:" + sys.argv[1]


def main():
    with sync_playwright() as tool:
        browser = tool.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(BASE + "/?lang=zh-TW")
        page.locator("#templates-toggle").click()
        page.get_by_role("menuitem", name=re.compile("^人像照")).click()
        prompt = page.locator("#prompt")
        assert prompt.input_value().startswith("在[地點]、[一天中的時刻]拍攝[人物：年齡、髮型、外貌]")  # noqa: RUF001
        assert prompt.evaluate("input => input.value.slice(input.selectionStart,input.selectionEnd)") == "[地點]"
        prompt.press("Tab")
        assert (
            prompt.evaluate("input => input.value.slice(input.selectionStart,input.selectionEnd)") == "[一天中的時刻]"
        )
        expect(page.locator("#go")).to_be_disabled()
        print("PASS Image template text and fillable placeholders follow the UI language", flush=True)

        page.locator("#media-video-mode").click()
        page.locator("#video-templates-toggle").click()
        expect(page.get_by_role("menuitem", name="第一格", exact=True)).to_have_count(0)
        page.get_by_role("menuitem", name=re.compile("^運鏡")).click()
        assert page.locator("#video-prompt").input_value().startswith("[人物或物件]在[地點]")
        print("PASS Video template text is localized and reference-only templates stay hidden", flush=True)

        context.request.post(BASE + "/api/v1/voice/backend", data={"backend": "auk_base"})
        page.goto(BASE + "/?lang=zh-TW&workspace=voice")
        page.wait_for_function("document.getElementById('voice-studio').capabilities.backend_id === 'auk_base'")
        page.locator("#voice-templates-toggle").click()
        page.get_by_role("menuitem", name="聲音輪廓", exact=True).click()
        expect(page.locator("#voice-templates-toggle")).to_have_text("聲音輪廓")
        expect(page.get_by_label("說話者", exact=True)).to_have_value("旁白員")
        assert page.locator("#voice-description").input_value().startswith("一位旁白員以溫暖而清晰的聲音說話。")
        page.locator("#voice-text").fill("這是一段測試台詞。")
        requests = []
        page.route("**/voice/operations", lambda route: requests.append(route))
        page.locator("#voice-generate").click()
        page.wait_for_function("document.getElementById('voice-studio').voiceRunning")
        assert requests
        body = requests[0].request.post_data_json
        assert body["template"] == "Voice profile" and body["template_locale"] == "zh-TW"
        assert body["template_values"]["speaker"] == "旁白員"
        requests[0].abort()
        print(
            "PASS Voice translates text, field labels and defaults while submitting canonical template IDs", flush=True
        )

        page.goto(BASE + "/?lang=en&workspace=image")
        page.locator("#templates-toggle").click()
        page.get_by_role("menuitem", name=re.compile("^Portrait photo")).click()
        assert (
            page.locator("#prompt").input_value().startswith("Close-up portrait photograph of [who: age, hair, look]")
        )
        print("PASS English template text remains unchanged", flush=True)
        assert not errors, errors
        browser.close()


if __name__ == "__main__":
    main()
