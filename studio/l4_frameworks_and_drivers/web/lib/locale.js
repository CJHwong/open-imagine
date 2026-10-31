// The language picker, a section of the settings menu beside Theme, Images and API. The
// chosen locale lives in a cookie so the server can draw the page in it on the next
// request; this module only records the pick and reloads. The page's copy is swept where
// the markup is, so a reload is what re-renders every surface at once.
//
// With no cookie the server reads the browser's own language list, which is the first thing
// a visitor sees. A pick outranks that list until Automatic clears it again.

import { menuItem, closeMenus } from '../components/popup-menu.js';

const COOKIE = 'studio-locale';

function copy(key, english) {
  return (window.STUDIO_STRINGS || {})[key] || english;
}

function picked() {
  const part = document.cookie.split('; ').find(function (entry) {
    return entry.startsWith(COOKIE + '=');
  });
  return part ? decodeURIComponent(part.slice(COOKIE.length + 1)) : '';
}

// An empty code drops the cookie, so the browser's language decides again.
function save(code) {
  const value = code ? '=' + encodeURIComponent(code) + '; max-age=31536000' : '=; max-age=0';
  document.cookie = COOKIE + value + '; path=/; samesite=lax';
  location.reload();
}

function mount() {
  const menu = document.getElementById('theme-menu');
  if (!menu) return;
  const chosen = picked();
  const head = document.createElement('div');
  head.className = 'menu-head';
  head.textContent = copy('locale.menu', 'Language');
  menu.append(head);
  const automatic = menuItem('check', copy('locale.automatic', 'Automatic (browser language)'), function () {
    closeMenus();
    save('');
  });
  automatic.setAttribute('role', 'menuitemradio');
  automatic.setAttribute('aria-checked', String(!chosen));
  automatic.id = 'locale-automatic';
  menu.append(automatic);
  (window.STUDIO_LOCALES || []).forEach(function (locale) {
    const item = menuItem('check', locale.label, function () {
      closeMenus();
      save(locale.code);
    });
    item.setAttribute('role', 'menuitemradio');
    item.setAttribute('aria-checked', String(locale.code === chosen));
    item.dataset.locale = locale.code;
    menu.append(item);
  });
}

mount();
