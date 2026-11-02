// One card for every workspace's gallery browser. The owner still draws the
// thumbnail, because a still, a waveform, a cover and a staff are different
// pictures; everything around it is the same card.
import {LitElement, html, nothing} from '/page/vendor/lit.js';
import {pencilLoop, playingMark} from './gallery-marker.js';
import {t} from '../lib/i18n.js';

const WORKSPACE_KEYS = {
  image: 'gallery.workspace.image', video: 'gallery.workspace.video',
  voice: 'gallery.workspace.voice', music: 'gallery.workspace.music',
};
const workspaceName = workspace => WORKSPACE_KEYS[workspace] ? t(WORKSPACE_KEYS[workspace]) : workspace;

class GalleryCard extends LitElement {
  static properties = {
    item: {attribute: false}, row: {attribute: false}, workspace: {type: String},
    selected: {type: Boolean}, playing: {type: Boolean}, checked: {type: Boolean},
    selecting: {type: Boolean}, working: {type: Boolean}, thumbnail: {attribute: false},
  };

  createRenderRoot() { return this; }

  render() {
    const {item, row} = this;
    if (!item) return nothing;
    return html`<article class="gallery-card${this.checked ? ' checked' : ''}${this.playing ? ' is-playing' : ''}">
      <button type="button" class=${'frame gallery-card-pick' + (this.selected && !row.batch ? ' selected' : '')}
        data-row-id=${row.batch ? 'batch-' + item.id : item.id}
        data-item-id=${row.batch ? nothing : item.id} ?disabled=${this.working}
        aria-label=${row.batch
          ? t('gallery.batch.open', {count: row.batch.length})
          : t('gallery.view', {workspace: workspaceName(this.workspace), number: item.number})}
        aria-pressed=${row.batch ? nothing : String(this.selected)}
        @click=${() => this.dispatchEvent(new CustomEvent('pick', {detail: {item, batch: row.batch, group: item.batch}}))}>
        <span class="still">${this.thumbnail ? this.thumbnail(item) : nothing}
          ${this.playing ? playingMark() : nothing}
          ${item.duration ? html`<span class="gallery-duration">${item.duration.toFixed(1)} s</span>` : nothing}
          ${row.batch ? html`<span class="gallery-batch-count">${t('gallery.batch.count', {count: row.batch.length})}</span>` : nothing}
        </span>
        <span class="gallery-card-foot">
          <span class="no">${row.batch ? t('gallery.batch.label') : String(item.number).padStart(2, '0')}</span>
          ${item.mode ? html`<span class="gallery-card-mode">${item.mode}</span>` : nothing}
        </span>
        ${this.selected && !row.batch ? pencilLoop(false) : nothing}
      </button>
      ${this.selecting && !row.batch ? html`<label class="gallery-check" title=${t('gallery.selectResult')}>
        <input type="checkbox" aria-label=${t('gallery.select', {workspace: workspaceName(this.workspace), number: item.number})}
          .checked=${this.checked} ?disabled=${this.working}
          @change=${() => this.dispatchEvent(new CustomEvent('check', {detail: item.id}))}></label>` : nothing}
      <p class="gallery-card-text" title=${item.text || item.name || ''}>${item.text || item.name || t('gallery.untitled')}</p>
    </article>`;
  }
}

customElements.define('gallery-card', GalleryCard);
