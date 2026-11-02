// One compact tile for the four strips. The gallery browser draws the full card; a
// strip shows the same picture, number and marks without the caption and the checkbox.
// The owner supplies the picture, the foot line and the mark, because a still, a wave,
// a frame and a cover are different pictures.
import { LitElement, html, nothing } from '/page/vendor/lit.js';
import { pencilLoop } from './gallery-marker.js';

class GalleryTile extends LitElement {
  static properties = {
    label: { type: String }, title: { type: String }, extra: { type: String },
    stillClass: { type: String }, selected: { type: Boolean }, pending: { type: Boolean },
    disabled: { type: Boolean }, width: { attribute: false }, content: { attribute: false },
    footer: { attribute: false }, mark: { attribute: false }, onPick: { attribute: false },
    action: { type: String }, clipId: { attribute: false }, takeId: { attribute: false },
    segmentId: { attribute: false }, songId: { attribute: false },
  };

  createRenderRoot() { return this; }

  // The strips redraw from a template that is replaced on every state change, so the
  // tile must have its button in place the moment it is inserted. Lit renders on a
  // microtask by default; this one draws now.
  connectedCallback() {
    super.connectedCallback();
    if (!this.hasUpdated) this.performUpdate();
  }

  render() {
    const classes = ['frame'].concat(this.extra ? this.extra.split(' ') : [])
      .concat(this.pending ? ['pending'] : []).concat(this.selected ? ['selected'] : []);
    return html`<button type="button" class=${classes.join(' ')}
      style=${this.width ? 'width:' + this.width + 'px' : nothing}
      ?disabled=${this.disabled} aria-pressed=${String(this.selected)}
      aria-label=${this.label || nothing} title=${this.title || nothing}
      data-action=${this.action || nothing} data-clip-id=${this.clipId ?? nothing}
      data-take-id=${this.takeId ?? nothing} data-segment-id=${this.segmentId ?? nothing}
      data-song-id=${this.songId ?? nothing}
      @click=${() => this.onPick?.()}><span class=${"still" + (this.stillClass ? " " + this.stillClass : "") + (this.pending ? " waiting" : "")} style=${this.width ? "width:100%" : nothing}>${this.content?.()}</span>${this.footer ? html`<span class="no">${this.footer()}</span>` : nothing}${this.mark ? this.mark() : this.selected ? pencilLoop(false) : nothing}
    </button>`;
  }
}

customElements.define('gallery-tile', GalleryTile);
