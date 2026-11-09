// Server-owned app settings. Browser preferences such as Theme stay local.
import { menuItem } from '../components/popup-menu.js';
import { t } from './i18n.js';

const menu = document.getElementById('theme-menu');
const heading = document.createElement('div');
heading.className = 'menu-head';
heading.textContent = t('settings.memory.heading');
let required = true;
let saving = false;
let revision = 0;
const toggle = menuItem('check', t('settings.memory.require'), async () => {
  if (saving) return;
  saving = true;
  revision += 1;
  toggle.disabled = true;
  try {
    const response = await fetch('/api/v1/settings', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({require_memory_estimate: !required}),
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.error || response.statusText);
    paint(body);
    showToast('info', t(required ? 'settings.memory.enabled' : 'settings.memory.disabled'));
  } catch (error) {
    showToast('error', t('settings.memory.failed', {message: error.message}));
  } finally {
    saving = false;
    toggle.disabled = false;
  }
}, t('settings.memory.help'));
toggle.id = 'require-memory-estimate-toggle';
toggle.setAttribute('role', 'menuitemcheckbox');
toggle.setAttribute('aria-checked', 'true');
toggle.disabled = true;
menu.append(heading, toggle);

function paint(settings) {
  required = settings.require_memory_estimate;
  toggle.setAttribute('aria-checked', String(required));
}

async function refresh() {
  if (saving) return;
  const requestRevision = ++revision;
  try {
    const response = await fetch('/api/v1/settings', {cache: 'no-store'});
    if (!response.ok) throw new Error(response.statusText);
    const settings = await response.json();
    if (!saving && requestRevision === revision) {
      paint(settings);
      toggle.disabled = false;
      toggle.title = t('settings.memory.help');
    }
  } catch (error) {
    if (saving || requestRevision !== revision) return;
    toggle.disabled = true;
    toggle.title = t('settings.memory.failed', {message: error.message});
  }
}
document.getElementById('theme-toggle').addEventListener('click', refresh);
window.addEventListener('focus', refresh);
refresh();
