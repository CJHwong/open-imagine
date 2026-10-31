"""The language switch: negotiation, the picker, the cookie and the translated chrome.

Run against `uv run studio --stub --port <port> --all-backends`.
"""

import sys

from playwright.sync_api import expect, sync_playwright

URL = "http://127.0.0.1:" + sys.argv[1]


def main() -> None:
    with sync_playwright() as tool:
        browser = tool.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        page.goto(URL + "/?lang=en")
        page.wait_for_function("Boolean(window.STUDIO_STRINGS)")
        expect(page.locator("html")).to_have_attribute("lang", "en")
        expect(page.locator("#media-image-mode")).to_have_text("Image")
        print("PASS ?lang=en draws the English page", flush=True)

        # No query and no cookie: the browser's own language list decides.
        chinese = browser.new_context(locale="zh-TW")
        chinese_page = chinese.new_page()
        chinese_page.goto(URL + "/")
        chinese_page.wait_for_function("document.documentElement.dataset.locale === 'zh-TW'")
        expect(chinese_page.locator("#media-image-mode")).to_have_text("圖片")
        chinese.close()
        print("PASS a browser that asks for zh-TW gets it", flush=True)

        # A plain URL, so the picker's cookie is what decides. The query wins by design.
        page.goto(URL + "/")
        page.wait_for_function("document.documentElement.dataset.locale === 'en'")

        page.locator("#theme-toggle").click()
        expect(page.locator("#theme-menu")).to_contain_text("Language")
        page.get_by_role("menuitemradio", name="繁體中文", exact=True).click()
        page.wait_for_load_state()
        page.wait_for_function("document.documentElement.dataset.locale === 'zh-TW'")
        expect(page.locator("html")).to_have_attribute("lang", "zh-TW")
        expect(page.locator("#media-image-mode")).to_have_text("圖片")
        expect(page.locator("#media-video-mode")).to_have_text("影片")
        expect(page.locator("#media-voice-mode")).to_have_text("語音")
        expect(page.locator("#media-music-mode")).to_have_text("音樂")
        expect(page.locator("#guide-toggle")).to_have_attribute("aria-label", "如何使用這個工作室")
        expect(page.locator("#theme-toggle")).to_have_attribute("aria-label", "設定")
        page.locator("#theme-toggle").click()
        expect(page.locator("#theme-menu")).to_contain_text("語言")
        expect(page.get_by_role("menuitemradio", name="繁體中文", exact=True)).to_have_attribute("aria-checked", "true")
        expect(page.locator("#workspace-tabs")).to_have_attribute("aria-label", "工作區")
        assert "locale-pending" not in (page.locator("html").get_attribute("class") or "")
        print("PASS the picker reloads into zh-TW and the sweep translated the chrome", flush=True)

        # Two strings no data-i18n attribute reaches, because a script writes them: the
        # guide's API line, and the parameters the voice model declares.
        page.locator("#guide-toggle").click()
        expect(page.locator(".guide-api")).to_contain_text("列出所有 JSON 路由。從 /api/v1/studio 開始。")
        page.keyboard.press("Escape")
        page.locator("#media-voice-mode").click()
        page.locator(".voice-advanced").evaluate("element => { element.open = true; }")
        panel = page.locator(".voice-advanced")
        expect(panel).to_contain_text("溫度")
        expect(panel).to_contain_text("數值越高，演出的變化越大。")  # noqa: RUF001 (the copy is Chinese)
        expect(panel).to_contain_text("首次執行會下載約 42 GB")
        page.locator("#media-image-mode").click()
        print("PASS the guide line and the declared voice parameters are translated", flush=True)

        cookie = [item for item in context.cookies() if item["name"] == "studio-locale"]
        assert cookie and cookie[0]["value"] == "zh-TW", cookie
        fresh = context.new_page()
        fresh.goto(URL + "/")
        fresh.wait_for_function("document.documentElement.dataset.locale === 'zh-TW'")
        expect(fresh.locator("#media-image-mode")).to_have_text("圖片")
        fresh.close()
        print("PASS the pick survives the next page in the same browser", flush=True)

        page.goto(URL + "/?lang=en")
        page.wait_for_function("document.documentElement.dataset.locale === 'en'")
        expect(page.locator("#media-image-mode")).to_have_text("Image")
        page.locator("#guide-toggle").click()
        expect(page.locator(".guide-api")).to_have_text("OpenAPI spec lists every JSON route. Start at /api/v1/studio.")
        page.keyboard.press("Escape")
        print("PASS ?lang=en wins over the saved cookie", flush=True)

        # The plain URL still reads the saved pick. Automatic drops it, and this context
        # asks for en-US, so the browser decides and the page comes back English.
        page.goto(URL + "/")
        page.wait_for_function("document.documentElement.dataset.locale === 'zh-TW'")
        page.locator("#theme-toggle").click()
        page.get_by_role("menuitemradio", name="自動（瀏覽器語言）", exact=True).click()  # noqa: RUF001
        page.wait_for_load_state()
        page.wait_for_function("document.documentElement.dataset.locale === 'en'")
        assert not [item for item in context.cookies() if item["name"] == "studio-locale"]
        print("PASS Automatic drops the pick and the browser decides", flush=True)

        mobile = context.new_page()
        mobile.set_viewport_size({"width": 390, "height": 844})
        mobile.goto(URL + "/?lang=zh-TW")
        mobile.wait_for_function("document.documentElement.dataset.locale === 'zh-TW'")
        assert mobile.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
        expect(mobile.locator("#media-image-mode")).to_have_text("圖片")
        mobile.close()
        print("PASS the translated page fits a phone width", flush=True)

        assert not errors, errors
        print("PASS no browser errors occurred", flush=True)
        browser.close()


main()
