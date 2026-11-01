// Two controls for the whole shelf: save it to a file, or bring a file back in.
// The page owns the four stores, so this element only asks it to collect and
// restore, and it owns the file format in lib/gallery-bundle.js.
import {LitElement, html} from 'https://cdn.jsdelivr.net/npm/lit@3.2.1/+esm';
import {t} from '../lib/i18n.js';
import {bundleName, decodeBundle, encodeBundle, saveBundle} from '../lib/gallery-bundle.js';

const icon = name => html`<svg class="icon" aria-hidden="true"><use href=${'#i-' + name}></use></svg>`;

class GalleryTransfer extends LitElement {
  static properties = {working: {state: true}};

  createRenderRoot() { return this; }

  constructor() {
    super();
    this.working = false;
  }

  render() {
    return html`<span class="gallery-transfer">
      <button type="button" class="text-btn" ?disabled=${this.working} @click=${() => this.exportAll()}>
        ${icon('download')}${t('gallery.export')}</button>
      <button type="button" class="text-btn" ?disabled=${this.working} @click=${() => this.pick()}>
        ${icon('plus')}${t('gallery.import')}</button>
      <input type="file" accept=".gz,.json,application/gzip,application/json" hidden
        @change=${event => this.importFile(event)}>
    </span>`;
  }

  async exportAll() {
    if (this.working) return;
    const collect = window.collectStudioBundle;
    if (typeof collect !== 'function') return;
    this.working = true;
    try {
      const items = await collect();
      const at = Date.now();
      saveBundle(await encodeBundle(items, at), bundleName(at));
      this.say('info', t('gallery.exported', {count: items.length}));
    } catch (error) {
      this.say('error', t('gallery.exportFailed', {message: error.message}));
    } finally {
      this.working = false;
    }
  }

  pick() {
    if (this.working) return;
    this.querySelector('input[type=file]').click();
  }

  async importFile(event) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file || this.working) return;
    this.working = true;
    try {
      const items = await decodeBundle(file);
      const result = await window.restoreStudioBundle(items);
      this.say('info', t('gallery.imported', {count: result.imported, skipped: result.skipped}));
    } catch (error) {
      this.say('error', t('gallery.importFailed', {message: error.message}));
    } finally {
      this.working = false;
    }
  }

  say(kind, message) {
    if (typeof window.notifyStudio === 'function') window.notifyStudio(kind, message);
  }
}

customElements.define('gallery-transfer', GalleryTransfer);
