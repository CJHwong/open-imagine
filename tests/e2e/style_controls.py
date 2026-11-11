"""Operate the shared style dropdowns through their public controls."""


def show_controls(page):
    if page.locator(".pane-switch").is_visible():
        page.locator('.pane-switch [data-pane="controls"]').click()


def open_style_section(page, selector="#look"):
    section = page.locator(selector)
    if not section.evaluate("element => element.open"):
        section.locator(":scope > summary").click()
    assert section.evaluate("element => element.open"), selector + " must stay open"


def style_menu(page, row):
    trigger = row.locator(".look-row-toggle")
    return page.locator("#" + trigger.get_attribute("aria-controls"))


def pick_style(page, row, label):
    row.locator(".look-row-toggle").click()
    style_menu(page, row).get_by_role("menuitemradio", name=label, exact=True).click()
