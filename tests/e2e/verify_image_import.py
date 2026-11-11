"""Import real HEIC pixels and choose large-image sizes without loading a model.

uv run --with playwright python tests/e2e/verify_image_import.py <port> [--webkit]
Run against a fresh all-backend stub.
"""

import base64
import io
import sys

from PIL import Image
from pillow_heif import register_heif_opener
from playwright.sync_api import expect, sync_playwright


def payload(name, format="PNG", size=(64, 48), mime="image/png", **options):
    register_heif_opener(thumbnails=False, depth_images=False, aux_images=False)
    contents = io.BytesIO()
    Image.new("RGB", size, (210, 30, 20)).save(contents, format=format, **options)
    return {"name": name, "mimeType": mime, "buffer": contents.getvalue()}


def import_file(page, workspace, item, source="file"):
    if source == "file":
        page.locator("#reference" if workspace == "image" else "#video-media-upload").set_input_files(item)
        return
    page.evaluate(
        """({workspace, name, mime, bytes, source}) => {
          const transfer = new DataTransfer();
          transfer.items.add(new File([new Uint8Array(bytes)], name, {type:mime}));
          if (source === 'paste') {
            document.dispatchEvent(new ClipboardEvent('paste', {bubbles:true, cancelable:true, clipboardData:transfer}));
          } else {
            const selector = source === 'rail' ? '#video-reference-rail'
              : workspace === 'image' ? '#refs' : '#video-source-panel';
            const target = document.querySelector(selector), box = target.getBoundingClientRect();
            target.dispatchEvent(new DragEvent('drop', {bubbles:true, cancelable:true, dataTransfer:transfer,
              clientX:box.left+box.width*0.75,clientY:box.top+box.height/2}));
          }
        }""",
        {
            "workspace": workspace,
            "name": item["name"],
            "mime": item["mimeType"],
            "bytes": list(item["buffer"]),
            "source": source,
        },
    )


def current_image(page, workspace):
    return page.locator("#thumbs img" if workspace == "image" else "#video-references .video-reference img").last


def check_pixels(page, workspace, width, height):
    image = current_image(page, workspace)
    expect(image).to_be_visible()
    expect(image).to_have_js_property("naturalWidth", width)
    expect(image).to_have_js_property("naturalHeight", height)
    source = image.evaluate("async image => { await image.decode(); return image.src; }")
    # Check the admitted PNG, including the browser's resize, without a second Canvas readback.
    with Image.open(io.BytesIO(base64.b64decode(source.split(",", 1)[1]))) as admitted:
        assert admitted.format == "PNG"
        assert admitted.size == (width, height)
        pixel = admitted.convert("RGBA").getpixel((width // 2, height // 2))
    assert pixel[3] == 255, pixel
    assert pixel[0] > pixel[1] + 100 and pixel[0] > pixel[2] + 100, pixel


def clear_reference(page, workspace, remaining=0):
    if workspace == "image":
        page.locator("#thumbs .remove").last.click()
    else:
        page.locator("#video-references .video-reference").last.click()
        page.locator(".video-reference-actions [data-action=remove-reference]").click()
    selector = "#thumbs img" if workspace == "image" else "#video-references .video-reference img"
    expect(page.locator(selector)).to_have_count(remaining)


def check_workspace(browser, base, workspace, width):
    context = browser.new_context(viewport={"width": width, "height": 1000}, has_touch=width < 600)
    context.add_init_script("localStorage.setItem('studio-keep', 'off')")
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(base + "/?workspace=" + workspace)
    expect(page.locator("body")).to_have_attribute("data-media", workspace)
    if page.locator(".pane-switch").is_visible():
        page.locator('.pane-switch [data-pane="controls"]').click()
    chooser = page.locator("#reference" if workspace == "image" else "#video-media-upload")
    assert all(extension in chooser.get_attribute("accept") for extension in (".heic", ".heif"))
    for source in ("file", "drop", "paste"):
        import_file(page, workspace, payload(source + ".HEIC", "HEIF", mime=""), source)
        check_pixels(page, workspace, 64, 48)
        clear_reference(page, workspace)
    exif = Image.Exif()
    exif[274] = 6
    import_file(page, workspace, payload("portrait.jpg", "JPEG", mime="image/jpeg", exif=exif))
    check_pixels(page, workspace, 48, 64)
    clear_reference(page, workspace)
    import_file(page, workspace, payload("edge.png", size=(2048, 1024)))
    check_pixels(page, workspace, 2048, 1024)
    expect(page.locator("#image-import-dialog")).to_have_count(0)
    clear_reference(page, workspace)
    large = payload("large.png", size=(4096, 2304))
    import_file(page, workspace, large)
    dialog = page.locator("#image-import-dialog")
    expect(dialog).to_be_visible()
    resize = dialog.locator(".image-import-resize")
    expect(resize).to_be_focused()
    expect(resize).to_have_text("Resize to 2048 \u00d7 1152 (recommended)")
    resize.click()
    check_pixels(page, workspace, 2048, 1152)
    clear_reference(page, workspace)
    import_file(page, workspace, large)
    dialog.get_by_role("button", name="Use original resolution", exact=True).click()
    check_pixels(page, workspace, 4096, 2304)
    clear_reference(page, workspace)
    import_file(page, workspace, large)
    dialog.get_by_role("button", name="Cancel", exact=True).click()
    expect(dialog).to_have_count(0)
    expect(current_image(page, workspace)).to_have_count(0)
    import_file(page, workspace, payload("keep.png", size=(32, 24)))
    check_pixels(page, workspace, 32, 24)
    import_file(page, workspace, large)
    dialog.get_by_role("button", name="Cancel", exact=True).click()
    check_pixels(page, workspace, 32, 24)
    if workspace == "video":
        import_file(page, workspace, payload("rail.heif", "HEIF", mime="image/heif"), "rail")
        expect(page.locator("#video-references .video-reference img")).to_have_count(2)
        check_pixels(page, workspace, 64, 48)
        clear_reference(page, workspace, remaining=1)
    clear_reference(page, workspace)
    if workspace == "image":
        page.locator('label[for="mode-edit"]').click()
    chooser.set_input_files([large, payload("second.png", size=(3000, 2000))])
    expect(dialog).to_contain_text("large.png")
    dialog.locator(".image-import-resize").click()
    expect(dialog).to_contain_text("second.png")
    dialog.get_by_role("button", name="Use original resolution", exact=True).click()
    selector = "#thumbs img" if workspace == "image" else "#video-references .video-reference img"
    expect(page.locator(selector)).to_have_count(2)
    expect(page.locator(selector).first).to_have_js_property("naturalWidth", 2048)
    expect(page.locator(selector).last).to_have_js_property("naturalWidth", 3000)
    clear_reference(page, workspace, remaining=1)
    clear_reference(page, workspace)
    import_file(page, workspace, {"name": "broken.heic", "mimeType": "image/heic", "buffer": b"invalid image"})
    expect(page.locator("#toasts").get_by_role("alert").last).to_be_visible()
    expect(current_image(page, workspace)).to_have_count(0)
    assert not errors, errors
    context.close()
    print(
        "PASS",
        workspace,
        width,
        "HEIC import pixels, upright JPEG, size choices, cancel preservation and decode error",
        flush=True,
    )


def main():
    engine = "webkit" if "--webkit" in sys.argv[2:] else "chromium"
    with sync_playwright() as playwright:
        browser = getattr(playwright, engine).launch()
        for width in (1280, 390):
            for workspace in ("image", "video"):
                check_workspace(browser, "http://127.0.0.1:" + sys.argv[1], workspace, width)
        browser.close()


if __name__ == "__main__":
    main()
