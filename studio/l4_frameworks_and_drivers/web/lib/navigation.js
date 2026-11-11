// Media actions request a pane without owning the responsive layout.
export function navigate(pane, target = '') {
  document.dispatchEvent(new CustomEvent('studio-navigate', {detail: {pane, target}}));
}

// A horizontal touch steps through results. Each tool keeps its own drag.
export function bindSwipe(surface, step) {
  const tools = 'input, textarea, select, button, a, audio, [role="slider"], [contenteditable], '
    + '.region-mark, audio-preview, .music-player, .music-track-text, .music-abc-notation, .music-output-details';
  let start = null;
  surface.addEventListener('pointerdown', event => {
    start = null;
    if (event.pointerType !== 'touch' || !event.isPrimary || event.target.closest(tools)) {
      return;
    }
    const video = event.target.closest('video');
    if (video && event.clientY > video.getBoundingClientRect().bottom - 56) return;
    start = {id: event.pointerId, left: event.clientX, top: event.clientY};
  });
  surface.addEventListener('pointerup', event => {
    const origin = start;
    start = null;
    if (!origin || origin.id !== event.pointerId) return;
    const horizontal = event.clientX - origin.left;
    const vertical = event.clientY - origin.top;
    if (Math.abs(horizontal) < 48 || Math.abs(horizontal) < Math.abs(vertical) * 2) return;
    const overlays = document.querySelectorAll('dialog[open], .sheet, .menu:not([hidden])');
    if ([...overlays].some(overlay => overlay.getClientRects().length)) return;
    step(horizontal < 0 ? 1 : -1);
  });
  surface.addEventListener('pointercancel', () => { start = null; });
}

document.dispatchEvent(new CustomEvent('navigation-ready', {detail: {bindSwipe}}));
