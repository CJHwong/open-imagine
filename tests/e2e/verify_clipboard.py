"""Check the shared paste control on desktop and phone widths without a GPU.

Run against a fresh `uv run studio --stub --backend qwen21 --all-backends --port <port>`:
    uv run --with playwright python tests/e2e/verify_clipboard.py <port>
"""

import base64
import io
import json
import math
import re
import struct
import sys
import wave

from PIL import Image
from playwright.sync_api import expect, sync_playwright
from style_controls import show_controls

URL = "http://127.0.0.1:" + sys.argv[1]
PASTE = '[data-clipboard-action="paste"]'

NATIVE = """(() => {
  window.clipboardTest = {
    types: ['image/png'], token: 'first', files: [CLIPBOARD_IMAGE],
    descriptions: 0, reads: 0, delayed: false, pending: [],
  };
  window.StudioClipboard = {
    describe: async () => {
      clipboardTest.descriptions++;
      return {types: [...clipboardTest.types], token: clipboardTest.token};
    },
    read: async () => {
      clipboardTest.reads++;
      const files = clipboardTest.files.map(file => ({...file}));
      if (!clipboardTest.delayed) return files;
      return new Promise(resolve => clipboardTest.pending.push(() => resolve(files)));
    },
  };
})();"""

BROWSER = """(() => {
  window.clipboardTest = {reads: 0};
  Object.defineProperty(navigator, 'clipboard', {configurable: true, value: {
    read: async () => {
      clipboardTest.reads++;
      const file = CLIPBOARD_IMAGE;
      const bytes = Uint8Array.from(atob(file.base64), character => character.charCodeAt(0));
      return [{types: [file.mime], getType: async () => new Blob([bytes], {type: file.mime})}];
    },
  }});
})();"""


def check(name, condition):
    assert condition, name
    print("PASS " + name, flush=True)


def image_clipboard():
    image = io.BytesIO()
    Image.new("RGB", (96, 64), (190, 90, 40)).save(image, "PNG")
    return {"name": "clipboard.png", "mime": "image/png", "base64": base64.b64encode(image.getvalue()).decode()}


def audio_clipboard():
    audio = io.BytesIO()
    samples = (int(math.sin(index * math.tau * 220 / 24000) * 6000) for index in range(24000 * 3))
    with wave.open(audio, "wb") as track:
        track.setnchannels(1)
        track.setsampwidth(2)
        track.setframerate(24000)
        track.writeframes(b"".join(struct.pack("<h", sample) for sample in samples))
    return {"name": "clipboard.wav", "mime": "audio/wav", "base64": base64.b64encode(audio.getvalue()).decode()}


def open_page(browser, width, adapter):
    context = browser.new_context(viewport={"width": width, "height": 900})
    context.add_init_script(adapter.replace("CLIPBOARD_IMAGE", json.dumps(image_clipboard())))
    page = context.new_page()
    page.set_default_timeout(10000)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("dialog", lambda dialog: dialog.accept())
    page.goto(URL + "/?workspace=image")
    show_controls(page)
    return context, page, errors


def control(page, target):
    return page.locator(f'[for="{target}"][context]')


def change_clipboard(page, token, types, files=None):
    page.evaluate(
        """({token, types, files}) => {
          Object.assign(clipboardTest, {token, types});
          if (files) clipboardTest.files = files;
          window.dispatchEvent(new Event('studio-clipboard-changed'));
        }""",
        {"token": token, "types": types, "files": files},
    )


def switch_workspace(page, workspace):
    tab = page.locator(f"#media-{workspace}-mode")
    if tab.is_visible():
        tab.click()
    else:
        page.locator("#workspace-toggle").click()
        page.locator(f'#workspace-menu [data-workspace="{workspace}"]').click()
    expect(page.locator("body")).to_have_attribute("data-media", workspace)
    show_controls(page)


def release_clipboard(page):
    page.evaluate("clipboardTest.pending.splice(0).forEach(release => release())")
    page.wait_for_timeout(250)


def verify_header_control(page, target):
    paste = control(page, target)
    expect(paste.locator(PASTE)).to_be_visible()
    bounds = paste.evaluate("""element => {
      const heading = element.closest('.field-head, .video-source-panel-head');
      if (!heading) return {header: false};
      const label = heading.querySelector('label, .label, strong').getBoundingClientRect();
      const button = element.querySelector('[data-clipboard-action="paste"]').getBoundingClientRect();
      const zone = document.getElementById(element.getAttribute('for')).parentElement
        .querySelector('.refs, #video-media-empty, .voice-reference-card, #music-reference-drop');
      const actions = [...heading.children].filter(child => !child.contains(element))
        .map(child => child.getBoundingClientRect()).filter(rectangle => rectangle.width && rectangle.height);
      return {header: true, adjacent: button.left - label.right >= 6 && button.left - label.right <= 20,
        aligned: Math.abs(button.top + button.height / 2 - label.top - label.height / 2) <= 1,
        touch: button.width >= 44 && button.height >= 44,
        separated: !zone || button.bottom <= zone.getBoundingClientRect().top,
        actions: actions.every(action => button.right <= action.left),
        overflow: document.documentElement.scrollWidth > innerWidth};
    }""")
    check(target + ": Paste belongs to the reference heading", bounds["header"])
    check(target + ": Paste sits beside the reference label", bounds["adjacent"] and bounds["aligned"])
    check(target + ": Paste provides a touch target", bounds["touch"])
    check(target + ": Paste overlaps no reference or action", bounds["separated"] and bounds["actions"])
    check(target + ": the heading introduces no horizontal overflow", not bounds["overflow"])
    expect(paste.locator('[data-clipboard-action="dismiss"]')).to_have_count(0)
    check(target + ": Paste has no dismissal control", paste.locator("button").count() == 1)


def verify_metadata(page, width):
    paste = control(page, "reference")
    expect(paste).to_have_attribute("context", "image:generate")
    expect(paste.locator(PASTE)).to_have_class(re.compile("clipboard-ready"))
    check(f"metadata never reads clipboard contents at {width}", page.evaluate("clipboardTest.reads") == 0)
    check("the paste control stays outside the file-picker zone", paste.evaluate("node => !node.closest('#refs')"))
    page.locator('label[for="mode-edit"]').click()
    expect(paste).to_have_attribute("context", "image:edit")
    expect(paste.locator(PASTE)).to_be_enabled()
    page.locator('label[for="mode-generate"]').click()
    expect(paste).to_have_attribute("context", "image:generate")
    expect(paste.locator(PASTE)).to_be_visible()
    change_clipboard(page, "unsupported", ["application/pdf"])
    expect(paste.locator(PASTE)).to_have_count(0)
    check(f"unsupported clipboard hides Paste at {width}", paste.locator(PASTE).count() == 0)
    change_clipboard(page, "", [], [])
    expect(paste.locator(PASTE)).to_have_count(0)
    check(f"empty clipboard hides Paste at {width}", paste.locator(PASTE).count() == 0)
    change_clipboard(page, "text", ["text/plain"])
    expect(paste.locator(PASTE)).to_have_count(0)
    change_clipboard(page, "third", ["image/png"], [image_clipboard()])
    expect(paste.locator(PASTE)).to_have_class(re.compile("clipboard-ready"))
    check(
        f"metadata and mode changes leave clipboard contents unread at {width}",
        page.evaluate("clipboardTest.reads") == 0,
    )


def verify_clipboard_errors(page, width):
    page.goto(URL + "/?workspace=image&lang=zh-TW")
    show_controls(page)
    paste = control(page, "reference")
    expect(paste.locator(PASTE)).to_be_visible()
    heading = paste.locator("xpath=..")
    height = heading.bounding_box()["height"]
    change_clipboard(page, "expired", ["image/png"], [])
    paste.locator(PASTE).click()
    expect(page.locator("#toasts")).to_contain_text("剪貼簿沒有支援的檔案。")
    expect(paste.locator(PASTE)).to_have_count(0)
    expect(heading.locator('p, [role="status"]')).to_have_count(0)
    check(f"an empty read keeps the reference heading compact at {width}", heading.bounding_box()["height"] <= height)
    change_clipboard(page, "read-error", ["image/png"])
    page.evaluate("() => { StudioClipboard.read = async () => { throw new Error('clipboard_denied'); }; }")
    paste.locator(PASTE).click()
    expect(page.locator("#toasts")).to_contain_text("無法讀取剪貼簿")
    expect(heading.locator('p, [role="status"]')).to_have_count(0)
    check(f"a denied read leaves the heading unchanged at {width}", heading.bounding_box()["height"] == height)
    check(
        f"clipboard errors introduce no horizontal overflow at {width}",
        page.evaluate("document.documentElement.scrollWidth <= innerWidth"),
    )


def verify_image_import(page, width):
    paste = control(page, "reference")
    choosers = []
    page.on("filechooser", lambda chooser: (choosers.append(chooser), chooser.set_files([])))
    page.evaluate("""() => {
      window.clipboardChanges = 0;
      window.clipboardScrolls = 0;
      window.addEventListener('scroll', () => clipboardScrolls++, true);
      document.getElementById('reference').addEventListener('change', () => clipboardChanges++);
    }""")
    navigations = []
    page.on("framenavigated", lambda frame: navigations.append(frame.url))
    paste.locator(PASTE).click()
    expect(page.locator("#thumbs img")).to_have_count(1, timeout=3000)
    expect(page.locator('#thumbs img[alt="clipboard.png"]')).to_be_visible()
    check(
        f"Paste imports immediately without scrolling or reloading at {width}",
        page.evaluate("clipboardScrolls") == 0 and not navigations,
    )
    check("paste uses the existing file-input change path", page.evaluate("clipboardChanges") == 1)
    check("paste opens no file chooser", not choosers)
    check(
        "paste decodes real image pixels",
        page.locator("#thumbs img").evaluate("image => image.naturalWidth === 96 && image.naturalHeight === 64"),
    )
    before = page.locator("#toasts").inner_text()
    broken = {"name": "broken.png", "mime": "image/png", "base64": base64.b64encode(b"invalid PNG").decode()}
    change_clipboard(page, "broken", ["image/png"], [broken])
    paste.locator(PASTE).click()
    expect(page.locator("#toasts")).not_to_have_text(before)
    expect(page.locator("#thumbs img")).to_have_count(1)
    check("paste keeps the existing image validation", page.locator("#thumbs img").count() == 1)


def verify_late_paste(page):
    paste = control(page, "reference")
    page.evaluate("clipboardTest.delayed = true")
    paste.locator(PASTE).click()
    page.wait_for_function("clipboardTest.pending.length === 1")
    page.locator('label[for="mode-edit"]').click()
    release_clipboard(page)
    expect(page.locator("#thumbs img")).to_have_count(0)
    check("a read that outlives its mode adds no reference", page.locator("#thumbs img").count() == 0)
    paste.locator(PASTE).click()
    page.wait_for_function("clipboardTest.pending.length === 1")
    switch_workspace(page, "video")
    release_clipboard(page)
    expect(page.locator("#thumbs img")).to_have_count(0)
    expect(page.locator("#video-references .video-reference")).to_have_count(0)
    check("a read that outlives its workspace adds no reference", page.locator("#thumbs img").count() == 0)
    page.evaluate("clipboardTest.delayed = false")


def verify_busy_paste(page):
    paste = control(page, "reference")
    page.evaluate("clipboardTest.delayed = true")
    for selector, attribute in (("#form", "data-panel-held"), ("#image-controls", "disabled")):
        paste.locator(PASTE).click()
        page.wait_for_function("clipboardTest.pending.length === 1")
        page.locator(selector).evaluate("(element, attribute) => element.setAttribute(attribute, 'true')", attribute)
        page.locator(selector).evaluate("(element, attribute) => element.removeAttribute(attribute)", attribute)
        release_clipboard(page)
        expect(page.locator("#thumbs img")).to_have_count(0)
        check("a completed hold invalidates the pending paste: " + attribute, page.locator("#thumbs img").count() == 0)
    page.evaluate("clipboardTest.delayed = false")


def verify_unchanged_attributes(page):
    paste = control(page, "reference")
    page.evaluate("clipboardTest.delayed = true")
    for selector, attribute in (("body", "data-pane"), ("#reference", "accept")):
        paste.locator(PASTE).click()
        page.wait_for_function("clipboardTest.pending.length === 1")
        page.locator(selector).evaluate(
            "(element, attribute) => element.setAttribute(attribute, element.getAttribute(attribute))", attribute
        )
        release_clipboard(page)
        expect(page.locator("#thumbs img")).to_have_count(1, timeout=3000)
        check(
            "an unchanged attribute preserves the pending paste: " + attribute, page.locator("#thumbs img").count() == 1
        )
        page.locator("#thumbs .remove").click()
        expect(page.locator("#thumbs img")).to_have_count(0)
    page.evaluate("clipboardTest.delayed = false")


def verify_media_workspaces(page):
    video = control(page, "video-media-upload")
    verify_header_control(page, "video-media-upload")
    video.locator(PASTE).click()
    expect(page.locator("#video-references .video-reference")).to_have_count(1, timeout=3000)
    check("video paste uses its media import path", page.locator("#video-references .video-reference").count() == 1)
    switch_workspace(page, "voice")
    expect(page.locator("voice-studio").locator(PASTE)).to_have_count(0)
    page.locator('label[for="voice-mode-clone"]').click()
    change_clipboard(page, "audio", ["audio/wav"], [audio_clipboard()])
    expect(page.locator("voice-studio").locator(PASTE)).to_have_count(0)
    check("voice has no Paste button in generate or clone", control(page, "voice-reference").count() == 0)
    switch_workspace(page, "music")
    expect(control(page, "music-reference")).to_have_count(0)
    page.locator('label[for="music-mode-plan"]').click()
    expect(control(page, "music-reference")).to_have_count(0)
    page.locator('label[for="music-mode-generate"]').click()
    expect(control(page, "music-reference")).to_have_count(0)
    check("music has no Paste button in generate or compose", control(page, "music-reference").count() == 0)


def verify_browser_fallback(browser, width):
    context, page, errors = open_page(browser, width, BROWSER)
    try:
        paste = control(page, "reference")
        expect(paste.locator(PASTE)).to_have_count(0)
        check(f"unknown browser clipboard hides Paste at {width}", paste.locator(PASTE).count() == 0)
        check(
            f"browser detection never requests clipboard access at {width}", page.evaluate("clipboardTest.reads") == 0
        )
        page.evaluate("""async () => {
          const items = await navigator.clipboard.read();
          const transfer = new DataTransfer();
          transfer.items.add(new File([await items[0].getType('image/png')], 'clipboard.png', {type: 'image/png'}));
          document.dispatchEvent(new ClipboardEvent('paste', {clipboardData: transfer, bubbles: true}));
        }""")
        expect(page.locator("#thumbs img")).to_have_count(1)
        check(f"browser keeps its standard paste path at {width}", page.locator("#thumbs img").count() == 1)
        check("browser paste reports no script errors", errors == [])
    finally:
        context.close()


def verify_native_image(browser, width):
    context, page, errors = open_page(browser, width, NATIVE)
    try:
        verify_header_control(page, "reference")
        verify_metadata(page, width)
        verify_image_import(page, width)
        verify_clipboard_errors(page, width)
        check("native paste reports no script errors", errors == [])
    finally:
        context.close()


def verify_native_workspaces(browser, width):
    context, page, errors = open_page(browser, width, NATIVE)
    try:
        verify_busy_paste(page)
        verify_unchanged_attributes(page)
        verify_late_paste(page)
        verify_media_workspaces(page)
        check("workspace paste reports no script errors", errors == [])
    finally:
        context.close()


def verify_import_progress(browser, width):
    adapter = (
        NATIVE
        + """
      window.pendingEncoding = [];
      const encode = HTMLCanvasElement.prototype.toBlob;
      HTMLCanvasElement.prototype.toBlob = function(callback, ...options) {
        pendingEncoding.push(() => encode.call(this, callback, ...options));
      };
    """
    )
    context, page, errors = open_page(browser, width, adapter)
    try:
        control(page, "reference").locator(PASTE).click()
        page.wait_for_function("pendingEncoding.length === 1")
        button = control(page, "reference").locator(PASTE)
        expect(button).to_have_attribute("aria-busy", "true")
        expect(button).to_be_disabled()
        check(f"Paste stays busy until image encoding finishes at {width}", button.is_disabled())
        page.evaluate("pendingEncoding.splice(0).forEach(encode => encode())")
        expect(page.locator("#thumbs img")).to_have_count(1, timeout=3000)
        expect(button).to_have_attribute("aria-busy", "false")
        check("image import raises no script errors", errors == [])
    finally:
        context.close()


def verify_cached_markup(browser):
    context, page, errors = open_page(browser, 1440, NATIVE)
    try:
        control(page, "reference").evaluate("element => element.remove()")
        page.locator("#prompt").fill("A ceramic cup on a table")
        page.locator('label[for="mode-edit"]').click()
        page.locator('label[for="mode-generate"]').click()
        check("cached markup without a paste control raises no script errors", errors == [])
        expect(page.locator("#go")).to_be_enabled()
        check("cached markup keeps the image form usable", page.locator("#go").is_enabled())
    finally:
        context.close()


with sync_playwright() as tool:
    browser = tool.chromium.launch()
    try:
        verify_import_progress(browser, 390)
        verify_cached_markup(browser)
        for width in (1440, 390):
            verify_native_image(browser, width)
            verify_native_workspaces(browser, width)
            verify_browser_fallback(browser, width)
    finally:
        browser.close()
