"""Operate controls without native tooltips or hover-only explanations.

Run against a fresh all-backend stub:
uv run --with playwright python tests/e2e/verify_control_help.py <port> [width ...] [--webkit]
"""

import io
import json
import re
import sys

from help_controls import visible_description
from PIL import Image
from playwright.sync_api import expect, sync_playwright
from settings_controls import open_settings
from style_controls import show_controls

WORKSPACES = (
    ("image", "#prompt", "#go", "#image-stage", ".pic img"),
    ("video", "#video-prompt", "#video-generate", "#video-studio", ".video-preview-stub"),
    ("voice", "#voice-text", "#voice-generate", "#voice-studio", "audio-preview"),
    ("music", "#music-style", "#music-generate", "#music-studio", ".music-song"),
)


def record(failures, condition, case, detail):
    if condition:
        return
    failure = {"case": case, "detail": detail}
    failures.append(failure)
    print("FAIL", json.dumps(failure), flush=True)


def check_titles(page, case, failures):
    titles = page.locator("[title]").evaluate_all("""elements => elements.filter(element =>
        element.getClientRects().length && getComputedStyle(element).visibility !== 'hidden'
        && element.getAttribute('title')?.trim()).map(element => ({tag: element.tagName,
            id: element.id, title: element.getAttribute('title')}))""")
    record(failures, not titles, case + "/native-titles", titles)


def visible_words(control):
    return control.evaluate("""element => {
        const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
        const words = [];
        while (walker.nextNode()) {
            const node = walker.currentNode;
            if (!/[\\p{L}\\p{N}]/u.test(node.textContent) || node.parentElement.closest('svg')) continue;
            const range = document.createRange(); range.selectNodeContents(node);
            const style = getComputedStyle(node.parentElement);
            if (style.visibility !== 'hidden' && Number(style.opacity) > 0
                && [...range.getClientRects()].some(rect => rect.width > 4 && rect.height > 8)) words.push(node.textContent.trim());
        }
        return words.join(' ');
    }""")


def check_caption(control, case, failures):
    expect(control).to_be_visible()
    record(failures, bool(visible_words(control)), case + "/visible-label", control.get_attribute("aria-label"))


def check_result_actions(actions, case, failures):
    record(
        failures,
        "preview-actions" in (actions.get_attribute("class") or "").split(),
        case + "/shared-actions",
        "preview-actions",
    )
    for control in actions.locator("button:visible, a:visible").all():
        expect(control).to_have_accessible_name(re.compile(r"\S"))
        check_caption(control, case, failures)
        expect(control.locator("svg")).to_be_visible()
        expect(control.locator(".control-label")).to_be_visible()
        geometry = control.evaluate("""button => {
            const icon = button.querySelector('svg').getBoundingClientRect();
            const caption = button.querySelector('.control-label').getBoundingClientRect();
            const bounds = button.getBoundingClientRect();
            return {centerGap: Math.abs(icon.left + icon.width / 2 - caption.left - caption.width / 2),
                verticalGap: caption.top - icon.bottom, bottomInset: bounds.bottom - caption.bottom};
        }""")
        stacked = geometry["centerGap"] <= 1 and geometry["verticalGap"] >= -0.5 and geometry["bottomInset"] >= -0.5
        record(failures, stacked, case + "/caption-below-icon", geometry)
    separators = actions.evaluate("""row => {
        const controls = [...row.querySelectorAll('button, a')].filter(button => button.getClientRects().length)
            .map(button => button.getBoundingClientRect());
        const center = (Math.min(...controls.map(box => box.top)) + Math.max(...controls.map(box => box.bottom))) / 2;
        return [...row.querySelectorAll(':scope > .rule')].map(rule => rule.getBoundingClientRect())
            .filter(box => box.width && box.height).map(box => Math.abs(box.top + box.height / 2 - center));
    }""")
    record(failures, all(gap <= 1 for gap in separators), case + "/separator-center", separators)


def check_image_actions(actions, case, failures):
    expect(actions.get_by_role("button", name="Open the image viewer", exact=True)).to_be_visible()
    compare = actions.get_by_role("button", name="Compare", exact=True)
    if compare.count():
        record(
            failures,
            compare.evaluate("button => button.nextElementSibling?.classList.contains('preview-details-toggle')"),
            case + "/compare-before-details",
            actions.inner_text(),
        )


def check_fullscreen_absence(page, stage, case, failures):
    buttons = page.locator(stage).get_by_role("button", name=re.compile("full.?screen", re.I))
    record(failures, buttons.count() == 0, case + "/no-fullscreen-action", buttons.count())
    for video in page.locator(stage + " video[controls]").all():
        restrictions = (video.get_attribute("controlslist") or "").split()
        record(failures, "nofullscreen" in restrictions, case + "/native-fullscreen-disabled", restrictions)
    page.locator("body").press("f")
    page.wait_for_timeout(250)
    record(
        failures,
        not page.evaluate("Boolean(document.fullscreenElement)"),
        case + "/f-inert",
        "the preview stays outside full screen",
    )


def png_payload(name, colour):
    buffer = io.BytesIO()
    Image.new("RGB", (32, 24), colour).save(buffer, format="PNG")
    return {"name": name, "mimeType": "image/png", "buffer": buffer.getvalue()}


def check_video_references(page, case, failures):
    page.locator("#guide-toggle").click()
    guide = page.locator("#guide-sheet")
    explanation = guide.locator("dt", has_text="Reference images and audio").locator("+ dd")
    explanation.scroll_into_view_if_needed()
    expect(explanation).to_be_visible()
    text = explanation.inner_text()
    record(
        failures,
        all(word in text for word in ("Generate", "Reference", "frame", "image reference", "Remove")),
        case + "/frame-reference-guidance",
        text,
    )
    guide.get_by_role("button", name="Close", exact=True).click()
    show_controls(page)
    page.locator("#video-media-upload").set_input_files(
        [png_payload("first-help-reference.png", "red"), png_payload("second-help-reference.png", "blue")]
    )
    references = page.locator("#video-references .video-reference")
    expect(references).to_have_count(2)
    for index, name in enumerate(("first-help-reference.png", "second-help-reference.png")):
        references.nth(index).click()
        expect(page.locator(".video-reference-actions .video-reference-caption")).to_contain_text(name)
        remove = page.locator(".video-reference-actions .video-reference-remove")
        check_caption(remove, case + "/reference-remove", failures)
        page.mouse.move(1, 1)
        style = remove.evaluate(
            "button => ({opacity: getComputedStyle(button).opacity, pointer: getComputedStyle(button).pointerEvents})"
        )
        record(
            failures,
            float(style["opacity"]) >= 0.9 and style["pointer"] != "none",
            case + "/reference-remove-without-hover",
            style,
        )
        expect(remove).to_have_attribute("data-reference-id", references.nth(index).get_attribute("data-reference-id"))
    check_titles(page, case + "/references", failures)


def check_details(page, actions, case, failures):
    details = actions.locator(".preview-details-toggle")
    if not details.is_visible():
        return
    details.click()
    sheet = page.locator("dialog[open]")
    expect(sheet.locator("dl")).to_be_visible()
    text = sheet.inner_text()
    record(failures, "A visible control help preview." in text and "Seed" in text, case + "/metadata-preserved", text)
    check_titles(page, case + "/details", failures)
    sheet.get_by_role("button", name=re.compile("close", re.I)).first.click()


def check_brush(page, stage, case, failures):
    page.locator(stage).get_by_role("button", name="Edit this", exact=True).click()
    if page.locator(".pane-switch").is_visible():
        page.locator('.pane-switch [data-pane="preview"]').click()
    for selector in ("#mark-size", "#mark-undo", "#mark-clear"):
        check_caption(page.locator(selector), case + selector, failures)
    note = page.locator("#region-tool-note")
    expect(note).to_be_visible()
    record(
        failures,
        bool(re.search(r"\d+.*(?:px|pixels)", note.inner_text(), re.I)),
        case + "/brush-pixel-guidance",
        note.inner_text(),
    )
    check_titles(page, case + "/brush", failures)
    show_controls(page)
    for thumb in page.locator("#thumbs .thumb").all():
        name = thumb.locator("img").get_attribute("alt")
        record(failures, name in visible_words(thumb), case + "/reference-filename", name)
    check_titles(page, case + "/image-references", failures)


def check_image_edit_actions(page, case, failures):
    page.locator("#advanced > summary").click()
    page.locator("#steps").fill("1")
    page.locator("#advanced > summary").click()
    page.locator("#prompt").fill("A visible control help edit.")
    page.locator("#go").click()
    actions = page.locator("#image-stage .stage-bar .actions:visible")
    expect(actions.get_by_role("button", name="Compare", exact=True)).to_be_visible(timeout=20000)
    page.wait_for_function("!busy() && !sharedOperation && !sharedBusy()", timeout=30000)
    check_result_actions(actions, case + "/edit-preview", failures)
    check_image_actions(actions, case + "/edit-preview", failures)


def check_library_help(page, case, failures):
    open_settings(page, "library")
    export = page.get_by_role("button", name="Export", exact=True)
    explanation = (
        "Export the whole gallery as one ZIP with records and media. Import it in another browser to restore it."
    )
    record(
        failures,
        explanation in visible_description(export),
        case + "/visible-menu-description",
        visible_description(export),
    )
    check_titles(page, case + "/settings", failures)
    page.locator(".settings-close").click()


def check_music_editor(page, case, failures):
    show_controls(page)
    page.locator(".music-advanced-fields > summary").click()
    edit = page.locator("#music-abc-edit")
    check_caption(edit, case + "/editor-open", failures)
    edit.click()
    expect(page.locator("#music-abc-dialog")).to_be_visible()
    close = page.locator("#music-abc-close")
    check_caption(close, case + "/editor-close", failures)
    check_titles(page, case + "/editor", failures)
    close.click()
    expect(edit).to_be_focused()


def check_lock_feedback(browser, base, failures):
    context = browser.new_context(viewport={"width": 390, "height": 1000}, is_mobile=True, has_touch=True)
    context.add_init_script("localStorage.setItem('studio-keep', 'off')")
    watched = context.new_page()
    watched.goto(base + "/?workspace=image")
    show_controls(watched)
    owner = context.new_page()
    owner.goto(base + "/?workspace=image")
    show_controls(owner)
    owner.locator("#prompt").fill("A visible lock notice.")
    owner.locator("#go").click()
    notice = watched.locator("#panel-notice")
    expect(notice).to_be_visible(timeout=15000)
    record(failures, bool(notice.inner_text().strip()), "lock/inline-reason", notice.inner_text())
    expect(watched.locator("#go")).to_be_disabled()
    check_titles(watched, "lock", failures)
    owner.locator("#shared-operation-cancel").click()
    owner.wait_for_function("!sharedOperation && !busy()", timeout=15000)
    expect(notice).to_be_hidden(timeout=15000)
    owner.route(
        "**/generate", lambda route: route.fulfill(status=400, content_type="text/plain", body="Rejected test request.")
    )
    show_controls(owner)
    owner.locator("#prompt").fill("A visible failure notice.")
    owner.locator("#go").click()
    alert = owner.locator("#toasts").get_by_role("alert").first
    expect(alert).to_be_visible(timeout=10000)
    record(failures, bool(alert.inner_text().strip()), "feedback/visible-error", alert.inner_text())
    dismiss = alert.get_by_role("button", name="Dismiss", exact=True)
    check_caption(dismiss, "feedback/dismiss", failures)
    dismiss.click()
    expect(owner.locator("#toasts").get_by_role("alert")).to_have_count(0)
    context.close()
    print("CHECK inline lock reason and immediate error feedback", flush=True)


def check_workspace(browser, base, width, spec, failures):
    workspace, field, generate, stage, result = spec
    context = browser.new_context(
        viewport={"width": width, "height": 1000}, has_touch=width <= 900, is_mobile=width <= 900
    )
    context.add_init_script("localStorage.setItem('studio-keep', 'off')")
    page = context.new_page()
    page.goto(base + "/?workspace=" + workspace)
    expect(page.locator("body")).to_have_attribute("data-media", workspace)
    show_controls(page)
    case = workspace + "/" + str(width)
    check_titles(page, case + "/controls", failures)
    for selector in ("#guide-toggle", "#theme-toggle"):
        check_caption(page.locator(selector), case + selector, failures)
    header = page.locator(".topbar").bounding_box()
    record(failures, header["height"] <= 72, case + "/header-height", header)
    if workspace in ("image", "video"):
        rewrite = page.locator("#rewrite-toggle" if workspace == "image" else "#video-rewrite-toggle")
        expect(rewrite).to_be_disabled()
        guidance = page.get_by_text("Write a prompt to rewrite first", exact=True)
        record(
            failures,
            any(item.is_visible() for item in guidance.all()),
            case + "/inline-rewrite-reason",
            "empty Rewrite has a visible reason",
        )
        record(
            failures,
            "Write a prompt to rewrite first" in visible_description(rewrite),
            case + "/associated-rewrite-reason",
            visible_description(rewrite),
        )
    if workspace == "image":
        page.locator("#advanced > summary").click()
        page.locator("#steps").fill("1")
        page.locator("#advanced > summary").click()
    page.locator(field).fill("A visible control help preview.")
    page.locator(generate).click()
    expect(page.locator(result).first).to_be_visible(timeout=20000)
    page.wait_for_function("!busy() && !sharedOperation && !sharedBusy()", timeout=30000)
    actions = page.locator(stage + " .stage-bar .actions:visible").first
    expect(actions).to_be_visible()
    check_result_actions(actions, case + "/preview", failures)
    if workspace == "image":
        check_image_actions(actions, case + "/preview", failures)
    rows = actions.evaluate(
        "row => [...row.children].filter(child => !child.matches('.rule')).map(child => child.getBoundingClientRect()).filter(box => box.width).map(box => box.top)"
    )
    record(failures, max(rows) - min(rows) <= 1, case + "/toolbar-row", rows)
    edges = actions.evaluate("""row => {
        const children = [...row.children].map(child => child.getBoundingClientRect()).filter(box => box.width);
        const bounds = row.getBoundingClientRect(), bar = row.closest('.stage-bar');
        const outer = bar.getBoundingClientRect(), style = getComputedStyle(bar);
        return {left: bounds.left, right: bounds.right, last: Math.max(...children.map(box => box.right)),
            availableLeft: outer.left + parseFloat(style.paddingLeft),
            availableRight: outer.right - parseFloat(style.paddingRight), overflow: row.scrollWidth - row.clientWidth};
    }""")
    record(failures, abs(edges["right"] - edges["last"]) <= 1, case + "/toolbar-right-alignment", edges)
    fits = edges["left"] >= edges["availableLeft"] - 1 and edges["right"] <= edges["availableRight"] + 1
    record(failures, fits and edges["overflow"] <= 1, case + "/toolbar-bounds", edges)
    check_fullscreen_absence(page, stage, case, failures)
    check_titles(page, case + "/preview", failures)
    check_details(page, actions, case, failures)
    if workspace == "voice":
        check_caption(page.locator("audio-preview .audio-preview-player button").first, case + "/play", failures)
    if workspace == "music":
        for button in page.locator(".music-player .music-lyrics-toggle:visible").all():
            check_caption(button, case + "/player", failures)
    if workspace == "video":
        check_video_references(page, case, failures)
    if workspace == "image":
        check_brush(page, stage, case, failures)
        check_image_edit_actions(page, case, failures)
        check_library_help(page, case, failures)
    if workspace == "music":
        check_music_editor(page, case, failures)
    context.close()
    print("CHECK", case, flush=True)


def main():
    failures = []
    arguments = sys.argv[2:]
    widths = tuple(int(argument) for argument in arguments if argument != "--webkit") or (280, 390, 768, 1024, 1440)
    engine = "webkit" if "--webkit" in arguments else "chromium"
    with sync_playwright() as playwright:
        browser = getattr(playwright, engine).launch()
        for width in widths:
            for spec in WORKSPACES:
                check_workspace(browser, "http://127.0.0.1:" + sys.argv[1], width, spec, failures)
        check_lock_feedback(browser, "http://127.0.0.1:" + sys.argv[1], failures)
        browser.close()
    print("FAILURES", len(failures), flush=True)
    raise SystemExit(bool(failures))


if __name__ == "__main__":
    main()
