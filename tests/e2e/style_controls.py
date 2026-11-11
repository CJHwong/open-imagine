"""Operate the shared style dropdowns through their public controls."""


def show_controls(page):
    if page.locator(".pane-switch").is_visible():
        page.locator('.pane-switch [data-pane="controls"]').click()


def style_menu(page, row):
    trigger = row.locator(".look-row-toggle")
    return page.locator("#" + trigger.get_attribute("aria-controls"))


def pick_style(page, row, label):
    row.locator(".look-row-toggle").click()
    style_menu(page, row).get_by_role("menuitemradio", name=label, exact=True).click()
