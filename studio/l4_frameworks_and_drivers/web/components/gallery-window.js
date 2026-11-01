import {LitElement, html} from 'https://cdn.jsdelivr.net/npm/lit@3.2.1/+esm';
import {repeat} from 'https://cdn.jsdelivr.net/npm/lit@3.2.1/directives/repeat.js/+esm';

// Only mount the visible cards and a small buffer; spacers preserve the full scroll range.
class GalleryWindow extends LitElement {
  static properties = {items: {attribute: false}, renderItem: {attribute: false}, axis: {}, selected: {attribute: false}, offset: {state: true}, itemSize: {attribute: false}};
  constructor() { super(); this.items = []; this.axis = 'horizontal'; this.offset = 0; }
  createRenderRoot() { return this; }
  connectedCallback() {
    super.connectedCallback();
    this.target = this.closest(this.axis === 'vertical' ? '.gallery-browser-grid' : '.strip');
    // Properties can arrive after connection, so attach after the first render too.
  }
  attach() {
    const target = this.closest(this.axis === 'vertical' ? '.gallery-browser-grid' : '.strip');
    if (target === this.listening) return;
    this.detach(); this.target = this.listening = target;
    this.onScroll = () => { if (!this.frame) this.frame = requestAnimationFrame(() => { this.frame = null; this.offset++; }); };
    target?.addEventListener('scroll', this.onScroll, {passive: true});
    this.onKey = async event => {
      if (this.axis !== 'horizontal' || !['Home', 'End'].includes(event.key) || !event.target.closest('.frame') || !this.items.length) return;
      event.preventDefault(); event.stopImmediatePropagation();
      const index = event.key === 'Home' ? 0 : this.items.length - 1;
      await this.reveal(index);
      const buttons = this.querySelectorAll('.frame');
      const button = event.key === 'Home' ? buttons[0] : buttons[buttons.length - 1];
      button?.click(); button?.focus();
    };
    target?.addEventListener('keydown', this.onKey, true);
    this.observer = new ResizeObserver(this.onScroll);
    if (target) this.observer.observe(target);
    this.offset++;
  }
  detach() {
    this.listening?.removeEventListener('scroll', this.onScroll);
    this.listening?.removeEventListener('keydown', this.onKey, true);
    this.observer?.disconnect();
    if (this.frame) cancelAnimationFrame(this.frame);
    this.frame = null;
  }
  disconnectedCallback() { this.detach(); super.disconnectedCallback(); }
  updated(changes) {
    this.attach();
    if (changes.has('selected') && changes.get('selected') != null && this.selected != null) {
      const index = this.items.findIndex(item => String(item.id ?? item.key ?? item.item?.id ?? item.take?.id) === String(this.selected));
      if (index >= 0) this.reveal(index);
    }
  }
  // A strip whose tiles follow the picture has no single width. The owner gives
  // each item's width, and the window turns those into offsets; the fixed stride
  // stays for the strips whose cards are one size.
  sizes() {
    if (this.axis === 'vertical' || typeof this.itemSize !== 'function') return null;
    const gap = 16;
    const widths = this.items.map(item => Math.max(1, Number(this.itemSize(item)) || 0));
    const offsets = [];
    let at = 0;
    widths.forEach(width => { offsets.push(at); at += width + gap; });
    return {gap, widths, offsets, total: Math.max(0, at - gap)};
  }
  geometry() {
    const vertical = this.axis === 'vertical';
    const columns = vertical ? Math.max(1, getComputedStyle(this.target || this).gridTemplateColumns.split(' ').filter(x => x.endsWith('px')).length) : 1;
    const position = vertical ? this.target?.scrollTop || 0 : this.target?.scrollLeft || 0;
    const extent = vertical ? this.target?.clientHeight || 400 : this.target?.clientWidth || 900;
    const sizes = this.sizes();
    if (sizes) {
      const from = Math.max(0, position - 200);
      const to = position + extent + 200;
      let first = sizes.offsets.findIndex((offset, index) => offset + sizes.widths[index] >= from);
      if (first < 0) first = Math.max(0, this.items.length - 1);
      let last = sizes.offsets.findIndex(offset => offset > to);
      if (last < 0) last = this.items.length;
      first = Math.max(0, first - 2);
      last = Math.min(this.items.length, last + 2);
      return {vertical, columns, stride: sizes.gap, position, extent, first, last, sizes};
    }
    const stride = vertical ? 176 : 124;
    const first = Math.max(0, Math.floor(position / stride) - 2) * columns;
    const last = Math.min(this.items.length, (Math.ceil((position + extent) / stride) + 2) * columns);
    return {vertical, columns, stride, position, extent, first: Math.min(first, Math.max(0, this.items.length - columns)), last, sizes: null};
  }
  async reveal(index) {
    const {vertical, columns, stride, position, extent, sizes} = this.geometry();
    const start = sizes ? sizes.offsets[index] || 0 : Math.floor(index / columns) * stride;
    const size = sizes ? sizes.widths[index] || 0 : stride;
    if (start < position || start + size > position + extent) {
      if (vertical) this.target.scrollTop = start; else this.target.scrollLeft = start;
      this.offset++; await this.updateComplete;
    }
  }
  render() {
    const {vertical, columns, stride, first, last, sizes} = this.geometry();
    const before = sizes
      ? (first ? Math.max(0, sizes.offsets[first] - sizes.gap) : 0)
      : Math.floor(first / columns) * stride;
    const after = sizes
      ? (last >= this.items.length ? 0 : Math.max(0, sizes.total - sizes.offsets[last]))
      : Math.max(0, Math.ceil((this.items.length - last) / columns) * stride);
    const spacer = size => html`<span class="gallery-window-spacer" aria-hidden="true" style=${vertical ? `grid-column:1/-1;height:${size}px;${size ? '' : 'display:none'}` : `flex:0 0 ${size}px;width:${size}px;${size ? '' : 'display:none'}`}></span>`;
    return html`${spacer(before)}${repeat(this.items.slice(first, Math.max(first, last)), item => item.id ?? item.key ?? item.item?.id ?? item.take?.id,
      (item, index) => this.renderItem?.(item, first + index))}${spacer(after)}`;
  }
}
customElements.define('gallery-window', GalleryWindow);
