"""App-wide memory settings through real controls and HTTP, using CPU stubs only.

Run: uv run --with playwright python tests/e2e/verify_studio_settings.py
"""

import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

from studio.l3_interface_adapters.gateways.image.qwen21.capabilities import qwen21_capabilities
from studio.l3_interface_adapters.gateways.no_prompt_rewriter_gateway import NoPromptRewriterGateway
from studio.l3_interface_adapters.gateways.stub.image_backend_gateway import StubBackendGateway
from studio.l4_frameworks_and_drivers.json_studio_settings_gateway import JsonStudioSettingsGateway
from studio.l4_frameworks_and_drivers.main import assemble_studio


def serve(path):
    settings = JsonStudioSettingsGateway(path)
    studio = assemble_studio(
        {"qwen21": StubBackendGateway(qwen21_capabilities("CPU"))},
        {"qwen21": NoPromptRewriterGateway()},
        "qwen21",
        ("qwen21",),
        settings=settings,
        resource_memory_headroom=lambda: (64 * 1024**3, 64 * 1024**3),
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), studio.handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return studio, server


def main():
    errors = []
    with tempfile.TemporaryDirectory(prefix="studio-settings-check-") as scratch, sync_playwright() as playwright:
        path = Path(scratch) / "settings.json"
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, locale="en-US")
        studio, server = serve(path)
        try:
            url = f"http://127.0.0.1:{server.server_port}"
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(url)
            page.click("#theme-toggle")
            toggle = page.locator("#require-memory-estimate-toggle")
            expect(toggle).to_be_enabled()
            expect(toggle).to_have_attribute("aria-checked", "true")
            payload = {"kind": "image", "backend": "qwen21", "prompt": "a pear", "steps": 1, "seed": 7}
            denied = context.request.post(url + "/api/v1/operations", data=payload)
            assert denied.status == 503 and "Settings > Memory" in denied.json()["error"]
            print("PASS strict default blocks an unmeasured operation with actionable guidance")
            page.keyboard.press("Escape")
            page.fill("#prompt", "a pear")
            with page.expect_response(
                lambda response: response.url.endswith("/generate") and response.request.method == "POST"
            ) as blocked:
                page.click("#go")
            assert blocked.value.status == 200
            assert "Memory use has not been measured" in blocked.value.text()
            expect(page.get_by_text("Memory use has not been measured", exact=False)).to_be_visible()
            page.click("#theme-toggle")
            print("PASS the page run reports the same actionable policy rejection")
            toggle.click()
            expect(toggle).to_have_attribute("aria-checked", "false")
            assert context.request.get(url + "/api/v1/settings").json()["require_memory_estimate"] is False
            allowed = context.request.post(url + "/api/v1/operations", data=payload)
            assert allowed.status == 202, allowed.text()
            print("PASS the real UI toggle changes API admission for another caller")
            # A second page reads the server policy rather than a browser-local preference.
            second = context.new_page()
            second.goto(url)
            second.click("#theme-toggle")
            expect(second.locator("#require-memory-estimate-toggle")).to_have_attribute("aria-checked", "false")
            print("PASS another page sees the app-wide setting")
            # Failed writes must not make the control claim the setting changed.
            second.route(
                "**/api/v1/settings",
                lambda route: (
                    route.fulfill(status=503, json={"error": "test save failure"})
                    if route.request.method == "POST"
                    else route.continue_()
                ),
            )
            second.click("#require-memory-estimate-toggle")
            expect(
                second.get_by_text("Could not update Studio memory settings: test save failure", exact=True)
            ).to_be_visible()
            expect(second.locator("#require-memory-estimate-toggle")).to_have_attribute("aria-checked", "false")
            print("PASS a failed save leaves the current policy intact")
            second.close()
            page.close()
        except BaseException:
            browser.close()
            raise
        finally:
            server.shutdown()
            server.server_close()
            studio.shutdown()
        studio, server = serve(path)
        try:
            page = context.new_page()
            page.goto(f"http://127.0.0.1:{server.server_port}")
            page.click("#theme-toggle")
            toggle = page.locator("#require-memory-estimate-toggle")
            expect(toggle).to_be_enabled()
            expect(toggle).to_have_attribute("aria-checked", "false")
            toggle.click()
            expect(toggle).to_have_attribute("aria-checked", "true")
            assert JsonStudioSettingsGateway(path).require_memory_estimate() is True
            print("PASS app settings survive a server restart and can be enabled again")
            page.set_viewport_size({"width": 390, "height": 844})
            page.click("#theme-toggle")
            toggle.scroll_into_view_if_needed()
            bounds = toggle.bounding_box()
            assert bounds and bounds["x"] >= 0 and bounds["x"] + bounds["width"] <= 390, bounds
            print("PASS the memory control fits a phone-sized viewport")
            assert not errors, errors
        finally:
            browser.close()
            server.shutdown()
            server.server_close()
            studio.shutdown()


if __name__ == "__main__":
    main()
