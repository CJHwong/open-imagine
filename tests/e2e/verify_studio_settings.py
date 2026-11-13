"""App-wide memory settings through real controls and HTTP, using CPU stubs only.

Run: uv run --with playwright python tests/e2e/verify_studio_settings.py
"""

import tempfile
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import expect, sync_playwright
from settings_controls import open_settings

from studio.l2_use_cases.boundaries.memory_estimate_gateway import MemoryEstimateGateway
from studio.l3_interface_adapters.gateways.image.qwen21.capabilities import qwen21_capabilities
from studio.l3_interface_adapters.gateways.no_prompt_rewriter_gateway import NoPromptRewriterGateway
from studio.l3_interface_adapters.gateways.stub.image_backend_gateway import StubBackendGateway
from studio.l4_frameworks_and_drivers.json_studio_settings_gateway import JsonStudioSettingsGateway
from studio.l4_frameworks_and_drivers.main import assemble_studio


class OversizedEstimate(MemoryEstimateGateway):
    def estimate(self, payload, total_memory_gib):
        return 512.0


def serve(path, storage=None, estimates=None):
    settings = JsonStudioSettingsGateway(path, True)
    studio = assemble_studio(
        {"qwen21": StubBackendGateway(qwen21_capabilities("CPU"))},
        {"qwen21": NoPromptRewriterGateway()},
        "qwen21",
        ("qwen21",),
        settings=settings,
        model_storage=storage,
        memory_estimates=estimates,
        resource_memory_headroom=lambda: (64 * 1024**3, 64 * 1024**3),
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), studio.handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return studio, server


def verify_known_estimate(context, path):
    studio, server = serve(path, estimates=OversizedEstimate())
    page = context.new_page()
    try:
        url = f"http://127.0.0.1:{server.server_port}"
        page.goto(url)
        open_settings(page, "generation")
        toggle = page.locator("#require-memory-estimate-toggle")
        expect(toggle).to_have_attribute("aria-checked", "true")
        payload = {"kind": "image", "backend": "qwen21", "prompt": "a pear", "steps": 1, "seed": 7}
        denied = context.request.post(url + "/api/v1/images/generate", data=payload)
        assert denied.status == 503 and "Not enough memory" in denied.json()["error"], denied.text()
        toggle.click()
        expect(toggle).to_have_attribute("aria-checked", "false")
        allowed = context.request.post(url + "/api/v1/operations", data=payload)
        assert allowed.status == 202, allowed.text()
        status_url = url + allowed.json()["status_url"]
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            operation = context.request.get(status_url).json()
            if operation["status"] in {"succeeded", "failed", "cancelled"}:
                break
            time.sleep(0.1)
        assert operation["status"] == "succeeded", operation
        toggle.click()
        expect(toggle).to_have_attribute("aria-checked", "true")
        denied = context.request.post(url + "/api/v1/images/generate", data=payload)
        assert denied.status == 503 and "Not enough memory" in denied.json()["error"], denied.text()
        print("PASS turning checks off runs an oversized measured request; turning checks on blocks it again")
    finally:
        page.close()
        server.shutdown()
        server.server_close()
        studio.shutdown()


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
            open_settings(page, "generation")
            toggle = page.locator("#require-memory-estimate-toggle")
            expect(toggle).to_be_enabled()
            expect(toggle).to_have_attribute("aria-checked", "true")
            payload = {"kind": "image", "backend": "qwen21", "prompt": "a pear", "steps": 1, "seed": 7}
            denied = context.request.post(url + "/api/v1/operations", data=payload)
            assert denied.status == 503 and "Settings > Generation" in denied.json()["error"]
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
            open_settings(page, "generation")
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
            open_settings(second, "generation")
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
            expect(second.get_by_text("test save failure", exact=False)).to_be_visible()
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
            open_settings(page, "generation")
            toggle = page.locator("#require-memory-estimate-toggle")
            expect(toggle).to_be_enabled()
            expect(toggle).to_have_attribute("aria-checked", "false")
            toggle.click()
            expect(toggle).to_have_attribute("aria-checked", "true")
            assert JsonStudioSettingsGateway(path).require_memory_estimate() is True
            print("PASS app settings survive a server restart and can be enabled again")
            page.set_viewport_size({"width": 390, "height": 844})
            open_settings(page, "generation")
            toggle.scroll_into_view_if_needed()
            bounds = toggle.bounding_box()
            assert bounds and bounds["x"] >= 0 and bounds["x"] + bounds["width"] <= 390, bounds
            print("PASS the memory control fits a phone-sized viewport")
            assert not errors, errors
        finally:
            server.shutdown()
            server.server_close()
            studio.shutdown()
        try:
            verify_known_estimate(context, path)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
