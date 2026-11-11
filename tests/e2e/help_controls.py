"""Read the visible explanation associated with a control."""


def visible_description(control):
    return control.evaluate("""element => (element.getAttribute('aria-describedby') || '')
        .split(/\\s+/).filter(Boolean).map(id => document.getElementById(id))
        .filter(note => note?.getClientRects().length && getComputedStyle(note).visibility !== 'hidden')
        .map(note => note.innerText.trim()).join(' ')""")
