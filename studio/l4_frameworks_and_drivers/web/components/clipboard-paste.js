import {LitElement, html, nothing} from '/page/vendor/lit.js';
import {t} from '../lib/i18n.js';

const EXTENSIONS = {
  'image/png': ['.png'], 'image/jpeg': ['.jpg', '.jpeg'], 'image/webp': ['.webp'],
  'image/gif': ['.gif'], 'image/heic': ['.heic'], 'image/heif': ['.heif'],
  'video/mp4': ['.mp4', '.m4v'], 'video/quicktime': ['.mov'], 'video/webm': ['.webm'],
  'audio/wav': ['.wav'], 'audio/x-wav': ['.wav'], 'audio/mpeg': ['.mp3'],
  'audio/flac': ['.flac'], 'audio/ogg': ['.ogg', '.oga'], 'audio/mp4': ['.m4a'],
  'audio/aac': ['.aac'], 'audio/aiff': ['.aif', '.aiff'],
};

class ClipboardPaste extends LitElement {
  static properties = {
    context: {type: String, reflect: true}, disabled: {type: Boolean, reflect: true},
    metadata: {state: true}, reading: {state: true},
  };

  constructor() {
    super();
    this.context = '';
    this.disabled = false;
    this.metadata = null;
    this.reading = false;
    this.epoch = 0;
    this.refreshClipboard = () => this.refresh();
  }

  createRenderRoot() { return this; }
  get input() { return document.getElementById(this.getAttribute('for')); }
  get supported() { return Boolean(window.StudioClipboard || navigator.clipboard?.read); }
  get available() {
    return !this.disabled && this.input && !this.input.matches(':disabled')
      && this.input.form?.dataset.panelHeld !== 'true' && !document.hidden
      && this.getClientRects().length > 0;
  }

  connectedCallback() {
    super.connectedCallback();
    window.addEventListener('focus', this.refreshClipboard);
    window.addEventListener('studio-clipboard-changed', this.refreshClipboard);
    document.addEventListener('visibilitychange', this.refreshClipboard);
    this.observer = new MutationObserver(records => {
      if (!records.some(record => record.oldValue !== record.target.getAttribute(record.attributeName))) return;
      this.epoch++;
      this.refresh();
    });
    this.observer.observe(document.body, {attributes: true, attributeOldValue: true, attributeFilter: ['data-media', 'data-pane']});
    this.updateComplete.then(() => {
      if (!this.isConnected || !this.input) return;
      this.observer.observe(this.input, {attributes: true, attributeOldValue: true, attributeFilter: ['disabled', 'accept']});
      const fieldset = this.input.closest('fieldset');
      if (fieldset) this.observer.observe(fieldset, {attributes: true, attributeOldValue: true, attributeFilter: ['disabled', 'hidden']});
      if (this.input.form) this.observer.observe(this.input.form, {attributes: true, attributeOldValue: true, attributeFilter: ['data-panel-held']});
      this.refresh();
    });
  }

  disconnectedCallback() {
    this.epoch++;
    this.observer.disconnect();
    window.removeEventListener('focus', this.refreshClipboard);
    window.removeEventListener('studio-clipboard-changed', this.refreshClipboard);
    document.removeEventListener('visibilitychange', this.refreshClipboard);
    super.disconnectedCallback();
  }

  updated(changed) {
    if (!changed.has('context') && !changed.has('disabled')) return;
    this.epoch++;
    this.refresh();
  }

  accepts(mime, name = '') {
    const accepted = (this.input?.accept || '').toLowerCase().split(',').map(rule => rule.trim()).filter(Boolean);
    if (!accepted.length) return /^(image|audio|video)\//.test(mime);
    return accepted.some(rule => rule === mime || rule.endsWith('/*') && mime.startsWith(rule.slice(0, -1))
      || rule.startsWith('.') && (EXTENSIONS[mime]?.includes(rule) || name.toLowerCase().endsWith(rule)));
  }

  async refresh() {
    this.requestUpdate();
    if (!this.available || !window.StudioClipboard) return;
    const epoch = this.epoch;
    try {
      const metadata = await window.StudioClipboard.describe();
      if (epoch === this.epoch && this.available) this.metadata = metadata;
    } catch (error) {
      // Failed detection must not advertise media that the app cannot confirm.
      if (epoch === this.epoch) this.metadata = null;
    }
  }

  async readFiles() {
    if (window.StudioClipboard) {
      const files = await window.StudioClipboard.read();
      return files.filter(file => this.accepts(file.mime, file.name)).map(file => {
        const bytes = Uint8Array.from(atob(file.base64), character => character.charCodeAt(0));
        return new File([bytes], file.name, {type: file.mime});
      });
    }
    const items = await navigator.clipboard.read();
    const files = [];
    for (const item of items) {
      const mime = item.types.find(type => this.accepts(type));
      if (!mime) continue;
      const blob = await item.getType(mime);
      files.push(new File([blob], 'clipboard' + (EXTENSIONS[mime]?.[0] || '.bin'), {type: mime}));
    }
    return files;
  }

  keepDrawing() {
    let frame;
    const draw = () => {
      if (this.reading && this.available) frame = requestAnimationFrame(draw);
    };
    // WebView can leave asynchronous imports unpainted when the last touch ends.
    frame = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frame);
  }

  async paste() {
    if (!this.available || this.reading) return;
    const context = this.context;
    const input = this.input;
    const epoch = this.epoch;
    const canCommit = () => this.isConnected && this.available && this.input === input
      && this.context === context && this.epoch === epoch;
    this.reading = true;
    const stopDrawing = this.keepDrawing();
    try {
      const files = await this.readFiles();
      if (!canCommit()) return;
      if (!files.length) {
        this.metadata = null;
        document.querySelector('toast-host')?.notify('info', t('clipboard.empty'));
        return;
      }
      const transfer = new DataTransfer();
      (input.multiple ? files : files.slice(0, 1)).forEach(file => transfer.items.add(file));
      input.files = transfer.files;
      const imports = [];
      input.dispatchEvent(new CustomEvent('change', {
        bubbles: true, detail: {waitUntil: importing => imports.push(importing)},
      }));
      await Promise.all(imports);
      if (canCommit()) await new Promise(resolve => requestAnimationFrame(resolve));
    } catch (error) {
      if (canCommit()) document.querySelector('toast-host')?.notify('error', t('clipboard.unavailable'));
    } finally {
      stopDrawing();
      this.reading = false;
    }
  }

  render() {
    const ready = this.metadata?.token
      && this.metadata.types?.some(type => this.accepts(type));
    if (!this.supported || !ready) return nothing;
    return html`<div class="clipboard-actions">
      <button type="button" class="text-btn clipboard-ready" data-clipboard-action="paste"
        title=${t('clipboard.ready')} aria-busy=${String(this.reading)}
        ?disabled=${!this.available || this.reading}
        @click=${() => this.paste()}>${this.reading ? t('clipboard.reading') : t('clipboard.paste')}</button>
    </div>`;
  }
}

customElements.define('clipboard-paste', ClipboardPaste);
