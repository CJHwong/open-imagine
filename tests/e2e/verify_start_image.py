"""The starting-image field shows only where the mode takes a picture. Run against a fresh stub:

uv run studio --stub --all-backends --port <port>
uv run --with playwright python tests/e2e/verify_start_image.py <port>
"""

import sys

from playwright.sync_api import expect, sync_playwright

BASE = "http://127.0.0.1:" + sys.argv[1]
PIXEL = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
failures = []


def check(name, passed, detail=""):
    print(("PASS " if passed else "FAIL ") + name + (f"  ({detail})" if detail else ""), flush=True)
    if not passed:
        failures.append(name)


def choose_model(page, name, runtime, backend):
    """A model offered on two engines has two entries of one name; the description says which."""
    page.locator("#backend-toggle").click()
    entry = page.get_by_role("menuitemradio", name=name, exact=True)
    entry.filter(has_text=f"Runs on {runtime}.").click()
    page.wait_for_function(f"STUDIO.backend.id === '{backend}'", timeout=15000)


def paste(page):
    """A paste reaches the form even where the field is hidden."""
    page.evaluate(
        """pixel => {
          const bytes = Uint8Array.from(atob(pixel), c => c.charCodeAt(0));
          const transfer = new DataTransfer();
          transfer.items.add(new File([bytes], 'paste.png', {type: 'image/png'}));
          document.dispatchEvent(new ClipboardEvent('paste', {bubbles: true, cancelable: true, clipboardData: transfer}));
        }""",
        PIXEL,
    )


def choose_mode(page, mode):
    page.locator(f'label[for="mode-{mode}"]').click()


with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    page.goto(BASE + "/?workspace=image", wait_until="load")
    page.wait_for_function("typeof STUDIO === 'object'", timeout=15000)
    field = page.locator("#reference-field")

    choose_model(page, "MiniMax H3-Image", "MLX", "minimax_h3_image")
    choose_mode(page, "generate")
    check("a Generate that takes no picture hides the field", field.is_hidden())

    paste(page)
    expect(page.locator("#toasts")).to_contain_text("cannot start Generate from a picture", timeout=5000)
    check(
        "a picture that still arrives names the mode, not Edit",
        "Edit takes at most" not in page.locator("#toasts").inner_text(),
    )
    check("that picture is not kept", page.evaluate("references.length") == 0)

    choose_mode(page, "edit")
    check("Edit on the same model shows the field", field.is_visible())

    for runtime, backend in (("MLX", "qwen21_turbo"), ("CUDA", "qwen21_turbo_cuda")):
        choose_model(page, "Qwen-Image-2.1-Turbo", runtime, backend)
        choose_mode(page, "generate")
        check(f"Turbo on {runtime} offers a starting picture in Generate", field.is_visible())
        if not page.evaluate("references.length"):
            paste(page)
        page.wait_for_function("references.length === 1", timeout=5000)
        check(f"Turbo on {runtime} offers its strength once a picture is in", page.locator("#strength").is_visible())
    browser.close()

print("FAILURES:", failures)
sys.exit(1 if failures else 0)
