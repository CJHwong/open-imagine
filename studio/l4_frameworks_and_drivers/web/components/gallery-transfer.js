// Two controls for the whole shelf: save it to a file, or bring a file back in.
// The page owns the four stores, so this element only asks it to collect and
// restore, and it owns the file format in lib/gallery-bundle.js.
import {LitElement, html} from 'https://cdn.jsdelivr.net/npm/lit@3.2.1/+esm';
import {t} from '../lib/i18n.js';
import {bundleName, decodeBundle, encodeBundle, saveBundle} from '../lib/gallery-bundle.js';

const icon = name => html`<svg class="icon" aria-hidden="true"><use href=${'#i-' + name}></use></svg>`;

class GalleryTransfer extends LitElement {
  static properties = {action: {state: true}, workspace: {type: String},
    selected: {attribute: false}, selecting: {type: Boolean}};

  createRenderRoot() { return this; }

  constructor() {
    super();
    this.action = ''; this.selected = new Set(); this.selecting = false;
  }

  render() {
    const spin = name => this.action === name
      ? html`<span class="gallery-spinner" aria-hidden="true"></span>` : null;
    const chosen = this.selected ? this.selected.size : 0;
    const label = chosen ? t('gallery.exportSelected', {count: chosen}) : t('gallery.export');
    return html`<span class="gallery-transfer">
      <button type="button" class="text-btn" ?disabled=${Boolean(this.action)}
        aria-busy=${String(this.action === 'export')} @click=${() => this.exportAll()}>
        ${spin('export') || icon('download')}${label}</button>
      <button type="button" class="text-btn" ?disabled=${Boolean(this.action)}
        aria-busy=${String(this.action === 'import')} @click=${() => this.pick()}>
        ${spin('import') || icon('plus')}${t('gallery.import')}</button>
      <input type="file" accept=".gz,.json,application/gzip,application/json" hidden
        @change=${event => this.importFile(event)}>
    </span>`;
  }

  async exportAll() {
    if (this.action) return;
    const collect = window.collectStudioBundle;
    if (typeof collect !== 'function') return;
    this.action = 'export';
    try {
      const ids = this.selected ? [...this.selected] : [];
      const items = await collect(ids.length ? {workspace: this.workspace, ids} : undefined);
      const at = Date.now();
      saveBundle(await encodeBundle(items, at), bundleName(at));
      this.say('info', t('gallery.exported', {count: items.length}));
    } catch (error) {
      this.say('error', t('gallery.exportFailed', {message: error.message}));
    } finally {
      this.action = '';
    }
  }

  pick() {
    if (this.action) return;
    this.querySelector('input[type=file]').click();
  }

  async importFile(event) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file || this.action) return;
    this.action = 'import';
    try {
      const items = await decodeBundle(file);
      const result = await window.restoreStudioBundle(items);
      this.say('info', t('gallery.imported', {count: result.imported, skipped: result.skipped}));
    } catch (error) {
      this.say('error', t('gallery.importFailed', {message: error.message}));
    } finally {
      this.action = '';
    }
  }

  say(kind, message) {
    if (typeof window.notifyStudio === 'function') window.notifyStudio(kind, message);
  }
}

customElements.define('gallery-transfer', GalleryTransfer);
