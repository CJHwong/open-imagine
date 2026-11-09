"""Interact with Settings through its accessible modal controls."""


def open_settings(page, section="appearance"):
    if not page.locator("#settings-dialog").is_visible():
        page.locator("#theme-toggle").click()
    page.locator("#settings-tab-" + section).click()
