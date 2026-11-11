// The page's popup menus: the backend picker, the theme menu, the count menu and
// the more menu. They differ only in their items, so one manager owns them all.
//
// A menu is a `div.menu` the markup already carries, hidden until it opens. Its
// toggle is the element that names it in `aria-controls`. One menu is open at
// most: a pick, a click outside or Escape closes it, and Escape puts focus back
// on the toggle. The arrow keys walk its items.
//
// It opens, closes, moves focus and routes keys. Some menus rebuild their items on each open.
// A native dialog keeps mobile menus above clipped preview containers. The work finishes in the
// task that asked for it: the count menu focuses its checked item in the same
// task it opens, which an asynchronous render could not do. So it is a plain
// light-DOM module and not a Lit element, which the design's Decisions table
// now says.
//
// The page's own script is still a classic script, and a classic script cannot
// import a module. So the manager announces itself on `popup-menus-ready` and
// the page mounts its menu sections in that handler. The event fires while this
// module is evaluated, which is after the markup is parsed and before any
// interaction, so those sections are built in the same slot they always were.
// This one door closes when the inline script is gone.

import {t} from '../lib/i18n.js';

const mobile = matchMedia('(max-width: 900px)');
let mobilePicker = null;
let noteNumber = 0;

function closePicker(restoreFocus = false) {
  if (!mobilePicker) return;
  const {dialog, menu, marker, trigger, temporary} = mobilePicker;
  mobilePicker = null;
  menu.hidden = true;
  if (temporary) { marker.remove(); menu.remove(); }
  else marker.replaceWith(menu);
  dialog.close();
  dialog.remove();
  trigger.setAttribute('aria-expanded', 'false');
  if (restoreFocus && trigger.isConnected) trigger.focus();
}

function isBackdrop(event) {
  if (event.target !== event.currentTarget) return false;
  const bounds = event.currentTarget.getBoundingClientRect();
  return event.clientX < bounds.left || event.clientX > bounds.right
    || event.clientY < bounds.top || event.clientY > bounds.bottom;
}

function openPicker(menu, trigger, title, temporary = false) {
  const marker = document.createComment('menu position');
  menu.before(marker);
  const dialog = document.createElement('dialog');
  dialog.className = 'mobile-menu-dialog';
  dialog.setAttribute('aria-label', title);
  const header = document.createElement('header');
  const heading = document.createElement('h2');
  heading.textContent = title;
  const close = document.createElement('button');
  close.type = 'button';
  close.className = 'icon-btn';
  close.setAttribute('aria-label', t('guide.sheet.close'));
  close.innerHTML = glyph('x');
  close.addEventListener('click', () => closePicker(true));
  header.append(heading, close);
  dialog.append(header, menu);
  document.body.append(dialog);
  mobilePicker = {dialog, menu, marker, trigger, temporary};
  trigger.setAttribute('aria-expanded', 'true');
  dialog.addEventListener('cancel', event => { event.preventDefault(); closePicker(true); });
  // Native selects open on pointerdown. Ignore the click that completes that same tap.
  let backdropPressed = false;
  dialog.addEventListener('pointerdown', event => { backdropPressed = isBackdrop(event); });
  dialog.addEventListener('pointercancel', () => { backdropPressed = false; });
  dialog.addEventListener('click', event => {
    const dismiss = backdropPressed && isBackdrop(event);
    backdropPressed = false;
    if (dismiss) closePicker(true);
  });
  dialog.showModal();
}

// The glyph of an item. The page draws its own controls the same way, and the
// item's own markup has to match it, so the two agree by the same three lines.
function glyph(name) {
  return '<svg class="icon" aria-hidden="true"><use href="#i-' + name + '"/></svg>';
}

// The element that opens and closes a menu, named by the menu's own id.
function toggleOf(menu) {
  return document.querySelector('[aria-controls="' + menu.id + '"]');
}

function enabledItems(menu) {
  return [...menu.querySelectorAll('button:not(:disabled):not([hidden])')]
    .filter(button => button.getClientRects().length);
}

// One item of a menu. `name` is the glyph, or empty for a menu that reads as
// text only, as a template does. The caller sets `menuitemradio` or
// `menuitemcheckbox` and `aria-checked` on what this returns.
export function menuItem(name, label, onPick, detail = '') {
  const button = document.createElement('button');
  button.type = 'button';
  button.setAttribute('role', 'menuitem');
  button.innerHTML = (name ? glyph(name) : '') + '<span class="item-text"></span>';
  button.querySelector('.item-text').textContent = label;
  if (detail && detail !== label) {
    const note = document.createElement('span');
    note.className = 'item-note';
    note.id = 'menu-note-' + ++noteNumber;
    note.textContent = detail;
    button.setAttribute('aria-label', label);
    button.setAttribute('aria-describedby', note.id);
    button.querySelector('.item-text').append(note);
  }
  button.addEventListener('click', function () {
    closeMenus();
    onPick();
  });
  return button;
}

// Opens the menu, or closes it when it is already open. Opening one closes
// whatever else is open, so the page never shows two. The focus lands in this
// same task, which is what the count menu leans on.
export function toggleMenu(menu) {
  const opening = menu.hidden;
  closeMenus();
  if (!opening) return;
  menu.hidden = false;
  const trigger = toggleOf(menu);
  trigger.setAttribute('aria-expanded', 'true');
  if (mobile.matches) openPicker(menu, trigger, trigger.querySelector('.label')?.textContent.trim()
    || trigger.getAttribute('aria-label') || trigger.textContent.trim());
  else fitMenu(menu);
  enabledItems(menu)[0]?.focus();
}

function fitMenu(menu) {
  if (menu.closest('.mobile-menu-dialog')) return;
  menu.style.removeProperty('max-height');
  menu.style.removeProperty('max-width');
  menu.style.removeProperty('min-width');
  menu.style.removeProperty('translate');
  const viewportLeft = window.visualViewport?.offsetLeft || 0;
  const viewportRight = viewportLeft + (window.visualViewport?.width || window.innerWidth);
  const viewportTop = window.visualViewport?.offsetTop || 0;
  const viewportBottom = viewportTop + (window.visualViewport?.height || window.innerHeight);
  const controls = menu.closest('.controls');
  const clip = controls && getComputedStyle(controls).overflowY !== 'visible'
    ? controls.getBoundingClientRect() : null;
  const visibleTop = Math.max(viewportTop, clip?.top ?? viewportTop);
  const visibleBottom = Math.min(viewportBottom, clip?.bottom ?? viewportBottom);
  const visibleLeft = Math.max(viewportLeft, clip?.left ?? viewportLeft) + 6;
  const visibleRight = Math.min(viewportRight, clip?.right ?? viewportRight) - 6;
  const availableWidth = Math.max(0, visibleRight - visibleLeft);
  const minimumWidth = parseFloat(getComputedStyle(menu).minWidth) || 0;
  menu.style.minWidth = Math.min(minimumWidth, availableWidth) + 'px';
  menu.style.maxWidth = availableWidth + 'px';
  const bounds = menu.getBoundingClientRect();
  const shift = Math.max(visibleLeft - bounds.left, Math.min(0, visibleRight - bounds.right));
  menu.style.translate = shift + 'px 0';
  const room = menu.classList.contains('up') ? bounds.bottom - visibleTop - 6 : visibleBottom - bounds.top - 6;
  const limit = parseFloat(getComputedStyle(menu).maxHeight);
  menu.style.maxHeight = Math.max(0, Math.min(room, Number.isFinite(limit) ? limit : room)) + 'px';
  menu.style.overflowY = 'auto';
}

export function closeMenus() {
  closePicker();
  document.querySelectorAll('.menu:not([hidden])').forEach(function (menu) {
    menu.hidden = true;
    const toggle = toggleOf(menu);
    if (toggle) toggle.setAttribute('aria-expanded', 'false');
  });
}

function fitOpenMenus() {
  if (mobilePicker && !mobile.matches) closePicker(true);
  document.querySelectorAll('.menu:not([hidden])').forEach(fitMenu);
}
window.addEventListener('resize', fitOpenMenus);
window.visualViewport?.addEventListener('resize', fitOpenMenus);
window.visualViewport?.addEventListener('scroll', fitOpenMenus);
mobile.addEventListener('change', () => {
  if (!mobile.matches) { closePicker(true); return; }
  const menu = document.querySelector('.menu:not([hidden])');
  if (menu && !mobilePicker) { closeMenus(); toggleMenu(menu); }
});

document.addEventListener('click', function (event) {
  if (mobilePicker || event.target.closest('.menu, .mobile-menu-dialog, [aria-controls]')) return;
  closeMenus();
});

document.addEventListener('keydown', function (event) {
  const open = document.querySelector('.menu:not([hidden])');
  if (!open) return;
  if (event.key === 'Escape') {
    event.preventDefault();
    const trigger = mobilePicker?.trigger || toggleOf(open);
    closeMenus();
    trigger?.focus();
    return;
  }
  if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
  event.preventDefault();
  const items = enabledItems(open);
  if (!items.length) return;
  const step = event.key === 'ArrowDown' ? 1 : -1;
  const index = items.indexOf(document.activeElement);
  items[(index + step + items.length) % items.length].focus();
});

function openSelect(select) {
  closeMenus();
  const menu = document.createElement('div');
  menu.className = 'menu';
  menu.setAttribute('role', 'menu');
  select.after(menu);
  for (const option of select.options) {
    const item = menuItem('', option.textContent, () => {
      if (!select.isConnected || select.matches(':disabled') || select.closest('[inert]')) return;
      select.value = option.value;
      select.dispatchEvent(new Event('input', {bubbles: true}));
      select.dispatchEvent(new Event('change', {bubbles: true}));
      select.focus();
    });
    item.setAttribute('role', 'menuitemradio');
    item.setAttribute('aria-checked', String(option.selected));
    item.disabled = option.disabled || Boolean(option.closest('optgroup')?.disabled);
    menu.append(item);
  }
  const title = select.getAttribute('aria-label') || select.labels?.[0]?.textContent.trim()
    || select.closest('.field')?.querySelector('label, .label')?.textContent.trim() || t('run.details');
  openPicker(menu, select, title, true);
  menu.querySelector('[aria-checked="true"]:not(:disabled)')?.focus();
}

document.addEventListener('pointerdown', event => {
  const select = event.target.closest('select');
  if (!mobile.matches || !select || select.matches(':disabled') || select.closest('[inert]') || select.multiple || select.size > 1) return;
  event.preventDefault();
  openSelect(select);
}, true);

document.addEventListener('keydown', event => {
  if (!mobile.matches || !event.target.matches('select') || !['Enter', ' ', 'ArrowDown'].includes(event.key)) return;
  event.preventDefault();
  openSelect(event.target);
});

document.dispatchEvent(new CustomEvent('popup-menus-ready', { detail: { menuItem, toggleMenu, closeMenus } }));
