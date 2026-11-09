"""Settings geometry, keyboard use and destructive cleanup against disposable files only.

Run: uv run --with playwright python tests/e2e/verify_model_storage.py
"""

import hashlib
import tempfile
from pathlib import Path

from playwright.sync_api import expect, sync_playwright
from settings_controls import open_settings
from verify_studio_settings import serve

from studio.l1_entities.model_asset import ModelAsset
from studio.l4_frameworks_and_drivers.model_asset_storage_gateway import ModelAssetStorageGateway


def digest():
    root = Path("studio/l4_frameworks_and_drivers/web")
    return hashlib.sha256(b"".join(path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file())).hexdigest()


def main():
    before = digest()
    with tempfile.TemporaryDirectory(prefix="studio-model-cleanup-") as scratch, sync_playwright() as p:
        root = Path(scratch).resolve()
        weights = root / "weights"
        weights.mkdir()
        (weights / "model.bin").write_bytes(b"synthetic weights")
        runtime = root / "runtime"
        runtime.mkdir()
        (runtime / "python").write_text("synthetic runtime")
        shared = root / "shared"
        shared.mkdir()
        (shared / "encoder").write_text("shared weights")
        storage = ModelAssetStorageGateway(
            [
                (
                    "a",
                    "Optional A",
                    "image",
                    (
                        ModelAsset("Weights", str(weights)),
                        ModelAsset("Runtime", str(runtime), "runtime"),
                        ModelAsset("Encoder", str(shared)),
                    ),
                ),
                ("b", "Optional B", "video", (ModelAsset("Encoder", str(shared)),)),
            ],
            [root],
            scan_cache=lambda: None,
        )
        studio, server = serve(root / "settings.json", storage)
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, locale="en-US")
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        try:
            page.goto(f"http://127.0.0.1:{server.server_port}")
            open_settings(page)
            expect(page.get_by_role("dialog")).to_be_visible()
            page.locator("#settings-tab-appearance").focus()
            page.keyboard.press("ArrowRight")
            expect(page.locator("#settings-tab-generation")).to_be_focused()
            page.keyboard.press("End")
            expect(page.locator("#settings-tab-storage")).to_be_focused()
            expect(page.locator("#settings-storage-models input")).to_have_count(2)
            page.locator("input[value=a]").check()
            page.click("#settings-review")
            expect(page.locator("#settings-cleanup-preview")).to_be_visible()
            expect(page.locator("#settings-cleanup-items")).to_contain_text("shared")
            assert weights.exists() and runtime.exists() and shared.exists()
            # Changing selection invalidates the preview and requires another review.
            page.locator("input[value=b]").check()
            expect(page.locator("#settings-cleanup-preview")).to_be_hidden()
            page.locator("input[value=b]").uncheck()
            page.click("#settings-review")
            expect(page.locator("#settings-cleanup-preview")).to_be_visible()
            (weights / "changed").write_text("changed after review")
            page.click("#settings-remove")
            expect(page.locator("#settings-error")).to_contain_text("changed")
            assert weights.exists() and runtime.exists()
            page.click("#settings-back")
            page.click("#settings-review")
            expect(page.locator("#settings-cleanup-preview")).to_be_visible()
            page.click("#settings-remove")
            expect(page.locator("#settings-cleanup-preview")).to_be_hidden()
            assert not weights.exists() and runtime.exists() and shared.exists()
            print(
                "PASS real HTTP cleanup removes reviewed weights and retains runtime/shared assets; stale preview refuses deletion"
            )
            page.locator("input[value=a]").check()
            page.locator("input[value=b]").check()
            page.check("#settings-include-runtime")
            page.click("#settings-review")
            expect(page.locator("#settings-cleanup-preview")).to_be_visible()
            page.click("#settings-remove")
            expect(page.locator("#settings-storage-models")).to_contain_text("No declared model downloads")
            assert not runtime.exists() and not shared.exists()
            print("PASS runtime opt-in and selecting every owner permits complete cleanup")
            page.keyboard.press("Escape")
            expect(page.locator("#theme-toggle")).to_be_focused()
            for width, height in ((1440, 1000), (768, 900), (390, 844), (390, 360)):
                page.set_viewport_size({"width": width, "height": height})
                open_settings(page)
                for section in ("appearance", "generation", "library", "storage"):
                    page.click("#settings-tab-" + section)
                    assert page.locator("#settings-dialog").evaluate("(el)=>el.scrollWidth<=el.clientWidth+1")
                    bounds = page.locator("#settings-dialog").bounding_box()
                    assert (
                        bounds
                        and bounds["x"] >= 0
                        and bounds["y"] >= 0
                        and bounds["x"] + bounds["width"] <= width + 1
                        and bounds["y"] + bounds["height"] <= height + 1
                    ), bounds
                page.keyboard.press("Escape")
            print(
                "PASS modal tab navigation, Escape/focus restoration, every section at desktop/tablet/phone/short-phone widths"
            )
            assert not errors, errors
        finally:
            browser.close()
            server.shutdown()
            server.server_close()
            studio.shutdown()
    assert before == digest(), "served page bytes changed during check"
    print("PASS web digest " + before)


if __name__ == "__main__":
    main()
