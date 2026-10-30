// The language picker, a section of the settings menu beside Theme, Images and API. The
// chosen locale lives in a cookie so the server can draw the page in it on the next
// request; this module only records the pick and reloads. The page's copy is swept where
// the markup is, so a reload is what re-renders every surface at once.

import { menuItem, closeMenus } from '../components/popup-menu.js';

const COOKIE = 'studio-locale';

function pick(code) {
  document.cookie = COOKIE + '=' + encodeURIComponent(code) + '; path=/; max-age=31536000; samesite=lax';
  location.reload();
}

function mount() {
  const menu = document.getElementById('theme-menu');
  if (!menu) return;
  const current = document.documentElement.dataset.locale || 'en';
  const head = document.createElement('div');
  head.className = 'menu-head';
  head.textContent = (window.STUDIO_STRINGS || {})['locale.menu'] || 'Language';
  menu.append(head);
  (window.STUDIO_LOCALES || []).forEach(function (locale) {
    const item = menuItem('check', locale.label, function () {
      closeMenus();
      pick(locale.code);
    });
    item.setAttribute('role', 'menuitemradio');
    item.setAttribute('aria-checked', String(locale.code === current));
    item.dataset.locale = locale.code;
    menu.append(item);
  });
}

mount();
