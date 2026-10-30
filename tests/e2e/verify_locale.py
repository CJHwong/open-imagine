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
        print("PASS ?lang=en wins over the saved cookie", flush=True)

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
