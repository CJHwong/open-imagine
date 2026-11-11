import {LitElement, html, svg, nothing} from '/page/vendor/lit.js';
import './video-gallery-preview.js';
import './gallery-media.js';
import './gallery-window.js';
import './gallery-card.js';
import {pencilLoop} from './gallery-marker.js';
import {galleryView, rememberGalleryView} from '../lib/gallery-view.js';
import {t} from '../lib/i18n.js';
import {navigate} from '../lib/navigation.js';

const icon = name => html`<svg class="icon" aria-hidden="true"><use href=${'#i-' + name}></use></svg>`;
const WORKSPACE_KEYS = {
  image: 'gallery.workspace.image', video: 'gallery.workspace.video',
  voice: 'gallery.workspace.voice', music: 'gallery.workspace.music',
};
const workspaceName = workspace => WORKSPACE_KEYS[workspace] ? t(WORKSPACE_KEYS[workspace]) : workspace;

// Each media owner supplies existing records and actions. This component owns browsing,
// never media storage, input selection, or generation state.
class GalleryBrowser extends LitElement {
  static properties = {
    workspace: {type: String}, items: {attribute: false}, selectedId: {attribute: false}, playingId: {attribute: false},
    choose: {attribute: false}, removeItem: {attribute: false}, download: {attribute: false},
    keeping: {type: Boolean}, pending: {type: Boolean}, pendingSelected: {type: Boolean},
    showPending: {attribute: false}, playback: {attribute: false},
    expanded: {type: Boolean, reflect: true}, query: {state: true}, order: {state: true},
    mode: {state: true}, model: {state: true}, grouped: {state: true}, group: {state: true},
    selecting: {state: true}, checked: {state: true}, working: {state: true},
    busyAction: {state: true}, error: {state: true},
  };
  constructor() {
    super();
    this.items = []; this.keeping = true; this.expanded = false;
    this.query = ''; this.order = 'newest'; this.mode = ''; this.model = '';
    this.grouped = false; this.group = ''; this.selecting = false;
    this.checked = new Set(); this.working = false; this.busyAction = ''; this.error = '';
    this.restored = false; this.gridScroll = 0;
    this.waitingImages = new WeakSet();
    this.stripScroll = event => {
      if (event.target.matches?.('.strip')) {
        if (this.restoreScroll || !this.gallery?.getClientRects().length) return;
        this.stripPosition = event.target.scrollLeft;
        this.remember({stripScroll: this.stripPosition});
      }
    };
  }
  createRenderRoot() { return this; }
  connectedCallback() {
    super.connectedCallback();
    this.gallery = this.closest('.strip-wrap');
    this.gallery?.addEventListener('scroll', this.stripScroll, true);
    this.visibility = new ResizeObserver(() => { if (this.restoreScroll) this.requestUpdate(); });
    if (this.gallery) this.visibility.observe(this.gallery);
  }
  disconnectedCallback() {
    this.gallery?.removeEventListener('scroll', this.stripScroll, true);
    this.visibility?.disconnect();
    super.disconnectedCallback();
  }
  remember(patch = {}) {
    rememberGalleryView(this.workspace, {expanded: this.expanded, query: this.query,
      order: this.order, mode: this.mode, model: this.model, grouped: this.grouped,
      group: this.group, gridScroll: this.gridScroll, ...patch}, this.keeping);
  }
  willUpdate(changes) {
    if (!this.restored && this.workspace) {
      const saved = this.keeping ? galleryView(this.workspace) : {};
      this.expanded = saved.expanded === true;
      this.query = typeof saved.query === 'string' ? saved.query : '';
      this.order = saved.order === 'oldest' ? 'oldest' : 'newest';
      this.mode = saved.mode || ''; this.model = saved.model || '';
      this.grouped = saved.grouped === true; this.group = saved.group || '';
      this.gridScroll = Number(saved.gridScroll) || 0;
      this.stripPosition = Number(saved.stripScroll) || 0;
      this.restored = true;
      this.restoreScroll = true;
    }
    if (changes.has('keeping') && !this.keeping) this.remember();
    if (changes.has('items')) {
      const ids = new Set(this.items.map(item => item.id));
      this.checked = new Set([...this.checked].filter(id => ids.has(id)));
      // Deleted or stale filter values should not strand the gallery on an empty category.
      if (this.items.length && this.mode && !this.items.some(item => item.mode === this.mode)) this.mode = '';
      if (this.items.length && this.model && !this.items.some(item => item.model === this.model)) this.model = '';
      if (this.items.length && this.group && !this.items.some(item => item.batch === this.group)) this.group = '';
    }
  }
  updated() {
    if (!this.restoreScroll) return;
    if (!this.items.length) return;
    if (this.gallery && !this.gallery.getClientRects().length) return;
    const strip = this.gallery?.querySelector('.strip');
    const grid = this.querySelector('.gallery-browser-grid');
    const window = (this.expanded ? grid : strip)?.querySelector('gallery-window');
    const apply = () => {
      if (!this.isConnected || !this.restoreScroll) return;
      if (strip && !this.expanded) strip.scrollLeft = this.stripPosition;
      if (grid) grid.scrollTop = this.gridScroll;
      this.restoreScroll = false;
      if (this.revealSelected) {
        this.revealSelected = false;
        strip?.querySelector('.selected')?.scrollIntoView({block: 'nearest', inline: 'nearest'});
      }
    };
    if (window?.isUpdatePending) window.updateComplete.then(apply);
    else apply();
  }

  toggle() {
    if (this.working) return;
    this.expanded = !this.expanded;
    if (!this.expanded) { this.selecting = false; this.checked = new Set(); this.revealSelected = true; }
    this.remember();
    this.restoreScroll = true;
  }
  filtered() {
    const query = this.query.trim().toLocaleLowerCase();
    return this.items.filter(item => (!this.mode || item.mode === this.mode)
      && (!this.model || item.model === this.model) && (!this.group || item.batch === this.group)
      && (!query || [item.text, item.description, item.model, item.mode, item.seed, item.name]
        .join(' ').toLocaleLowerCase().includes(query)))
      .map((item, index) => ({item, index})).sort((a, b) => {
        const delta = (Number(b.item.at) || 0) - (Number(a.item.at) || 0);
        return (this.order === 'oldest' ? -delta : delta) || a.index - b.index;
      }).map(row => row.item);
  }
  rows(items) {
    if (!this.grouped || this.group) return items.map(item => ({item}));
    const batches = new Map();
    items.forEach(item => { if (item.batch) batches.set(item.batch, [...(batches.get(item.batch) || []), item]); });
    const seen = new Set();
    return items.flatMap(item => {
      const batch = batches.get(item.batch);
      if (!batch || batch.length < 2) return [{item}];
      if (seen.has(item.batch)) return [];
      seen.add(item.batch);
      return [{item, batch}];
    });
  }
  change(field, value) {
    this[field] = value;
    if (field !== 'group') this.group = '';
    this.gridScroll = 0;
    this.restoreScroll = true;
    this.checked = new Set();
    this.remember();
  }
  check(id) {
    this.checked = new Set(this.checked);
    if (this.checked.has(id)) this.checked.delete(id); else this.checked.add(id);
  }
  pick(item) {
    if (this.working) return;
    if (this.selecting) this.check(item.id);
    else {
      this.choose?.(item.id);
      navigate('preview');
    }
  }
  async act(action) {
    const selected = this.items.filter(item => this.checked.has(item.id));
    if (!selected.length || this.working) return;
    if (action === 'remove' && !confirm(t(
      this.keeping ? 'gallery.confirm.remove.browser' : 'gallery.confirm.remove.tab',
      {count: selected.length, workspace: workspaceName(this.workspace)}))) return;
    this.working = true; this.busyAction = action; this.error = '';
    try {
      if (action === 'download') await this.download?.(selected.filter(item => item.downloadable !== false).map(item => item.id));
      else {
        let failed = 0;
        for (const item of selected) if (await this.removeItem?.(item.id) === false) failed++;
        this.checked = new Set();
        if (failed) this.error = t('gallery.error.remove', {count: failed});
      }
    } catch (error) { this.error = error.message || t('gallery.error.action'); }
    finally { this.working = false; this.busyAction = ''; }
  }
  async key(event) {
    if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey) return;
    if (event.key === 'Escape' && this.expanded) {
      event.preventDefault(); event.stopPropagation();
      if (this.selecting) { this.selecting = false; this.checked = new Set(); }
      else { this.toggle(); this.querySelector('.gallery-browse-toggle')?.focus(); }
      return;
    }
    if (event.target.closest('input, select, textarea, [contenteditable]')) return;
    const buttons = Array.from(this.querySelectorAll('.gallery-card-pick'));
    const current = buttons.indexOf(event.target.closest('.gallery-card-pick'));
    if (current < 0) return;
    if (event.key === ' ' && buttons[current].dataset.itemId && !this.selecting && this.workspace !== 'image' && this.playback) {
      event.preventDefault(); event.stopPropagation();
      const item = this.items.find(item => String(item.id) === buttons[current].dataset.itemId);
      if (item && String(item.id) !== String(this.selectedId)) {
        Promise.resolve(this.choose?.(item.id)).then(() => this.playback());
      } else this.playback();
      return;
    }
    const rows = this.rows(this.filtered());
    const rowId = row => String(row.batch ? 'batch-' + row.item.id : row.item.id);
    const card = event.target.closest('.gallery-card-pick');
    const position = rows.findIndex(row => rowId(row) === card.dataset.rowId);
    const window = this.querySelector('gallery-window');
    const columns = window?.geometry().columns || 1;
    const moves = {ArrowRight: position + 1, ArrowLeft: position - 1, ArrowDown: position + columns,
      ArrowUp: position - columns, Home: 0, End: rows.length - 1};
    if (!(event.key in moves) || !rows.length) return;
    event.preventDefault(); event.stopPropagation();
    const index = Math.max(0, Math.min(rows.length - 1, moves[event.key]));
    await window?.reveal(index);
    const row = rows[index];
    const next = Array.from(this.querySelectorAll('.gallery-card-pick')).find(button => button.dataset.rowId === rowId(row));
    next?.focus(); next?.scrollIntoView({block: 'nearest', inline: 'nearest'});
    if (!this.selecting && !row.batch) this.choose?.(row.item.id);
  }

  thumbnail(item) {
    if (item.loadMedia) return html`<gallery-media .identity=${this.workspace + '-' + item.id} .load=${item.loadMedia}
      .video=${this.workspace === 'video'} .blocked=${this.pending}></gallery-media>`;
    if (this.workspace === 'video' && item.video) return html`<video-gallery-preview .source=${item.video}
      .poster=${item.thumbnail} .blocked=${this.pending}></video-gallery-preview>`;
    if (item.thumbnail) return html`<img src=${item.thumbnail} alt="" loading="lazy" decoding="async">`;
    // A score has no recording to preview, so its tile wears the staff the strip uses.
    if (this.workspace === 'music' && item.score) {
      return html`<span class="gallery-no-preview gallery-music-note"><svg class="icon" aria-hidden="true"><use href="#i-score"></use></svg></span>`;
    }
    const maximum = Math.max(0.001, ...(item.peaks || []));
    if (item.peaks?.length) return svg`<svg class="gallery-wave" viewBox="0 0 160 60" preserveAspectRatio="none" aria-hidden="true">
      ${item.peaks.map((peak, index) => svg`<line x1=${(index + 0.5) * 160 / item.peaks.length}
        x2=${(index + 0.5) * 160 / item.peaks.length} y1=${30 - Math.max(1, peak / maximum * 25)} y2=${30 + Math.max(1, peak / maximum * 25)} />`)}</svg>`;
    return html`<span class=${'gallery-no-preview' + (this.workspace === 'music' ? ' gallery-music-note' : '')}>${this.workspace === 'music' ? '♫' : this.workspace === 'voice' ? t('gallery.audio') : t('gallery.noPreview')}</span>`;
  }
  card(row) {
    const item = row.item;
    const selected = String(this.selectedId) === String(item.id) && !this.pendingSelected;
    const playing = this.workspace === 'music' && this.playingId != null
      && (row.batch || [item]).some(entry => String(entry.id) === String(this.playingId));
    return html`<gallery-card .item=${item} .row=${row} workspace=${this.workspace}
      ?selected=${selected} ?playing=${playing} ?checked=${this.checked.has(item.id)}
      ?selecting=${this.selecting} ?working=${this.working} .thumbnail=${entry => this.thumbnail(entry)}
      @pick=${event => event.detail.batch ? this.change('group', event.detail.group) : this.pick(event.detail.item)}
      @check=${event => this.check(event.detail)}></gallery-card>`;
  }
  render() {
    const items = this.filtered();
    const models = [...new Set(this.items.map(item => item.model).filter(Boolean))].sort();
    const modes = [...new Set(this.items.map(item => item.mode).filter(Boolean))].sort();
    const checked = this.items.filter(item => this.checked.has(item.id));
    const batches = this.items.map(item => item.batch).filter(Boolean);
    const hasBatch = new Set(batches).size < batches.length;
    return html`<button type="button" class="text-btn gallery-browse-toggle" aria-expanded=${String(this.expanded)}
      aria-controls=${this.workspace + '-gallery-browser-panel'} ?disabled=${this.working}
      @keydown=${event => this.key(event)}
      @click=${() => this.toggle()}>${icon(this.expanded ? 'shrink' : 'layout')}${t(this.expanded ? 'gallery.compact' : 'gallery.browse')}</button>
      ${this.expanded ? html`<section class="gallery-browser-panel" id=${this.workspace + '-gallery-browser-panel'}
        aria-label=${t('gallery.panel', {workspace: workspaceName(this.workspace)})} @keydown=${event => this.key(event)}>
        <div class="gallery-browser-tools">
          <input type="search" aria-label=${t('gallery.search')} placeholder=${t('gallery.searchPlaceholder')}
            .value=${this.query} @input=${event => this.change('query', event.target.value)}>
          <select aria-label=${t('gallery.order')} @change=${event => this.change('order', event.target.value)}>
            <option value="newest" .selected=${this.order === 'newest'}>${t('gallery.orderNewest')}</option>
            <option value="oldest" .selected=${this.order === 'oldest'}>${t('gallery.orderOldest')}</option></select>
          ${hasBatch ? html`<label class="gallery-group-toggle"><input type="checkbox" .checked=${this.grouped}
            @change=${event => this.change('grouped', event.target.checked)}>${t('gallery.groupBatches')}</label>` : nothing}
          <button type="button" class="text-btn gallery-select-toggle" aria-pressed=${String(this.selecting)}
            ?disabled=${this.working}
            @click=${() => { this.selecting = !this.selecting; this.checked = new Set(); }}>${icon('check')}${t(this.selecting ? 'gallery.done' : 'gallery.selectMode')}</button>
        </div>
        </div>
        <div class="gallery-browser-summary">
          ${this.group ? html`<button type="button" class="text-btn" @click=${() => this.change('group', '')}>${icon('undo')}${t('gallery.allResults')}</button>` : nothing}
          <span role="status" aria-live="polite">${t('gallery.summary', {shown: items.length, total: this.items.length})}${checked.length ? t('gallery.selected', {count: checked.length}) : ''}</span>
          ${this.selecting ? html`<button type="button" class="text-btn" ?disabled=${this.working || !items.length}
            @click=${() => { this.checked = items.every(item => this.checked.has(item.id))
              ? new Set() : new Set(items.map(item => item.id)); }}>${t(items.every(item => this.checked.has(item.id))
              ? 'gallery.deselect' : 'gallery.selectAll', {count: items.length})}</button>
            <button type="button" class="text-btn" ?disabled=${this.working || !checked.some(item => item.downloadable !== false)}
              aria-busy=${String(this.busyAction === 'download')}
              title=${t('gallery.downloadSelected.title')}
              @click=${() => this.act('download')}>${this.busyAction === 'download'
                ? html`<span class="gallery-spinner" aria-hidden="true"></span>` : icon('download')}${t('gallery.downloadSelected', {count: checked.length})}</button>
            <button type="button" class="text-btn gallery-remove" ?disabled=${this.working || !checked.length}
              @click=${() => this.act('remove')}>${icon('trash')}${t('gallery.removeSelected', {count: checked.length})}</button>` : nothing}
        </div>
        ${this.error ? html`<p class="gallery-browser-error" role="alert">${this.error}</p>` : nothing}
        <div class="gallery-browser-grid" role="group" aria-label=${t('gallery.results')} @scroll=${event => {
          if (this.restoreScroll) return;
          this.gridScroll = event.target.scrollTop; this.remember();
        }}>
          ${this.pending ? html`<button type="button" class=${'frame gallery-card-pick gallery-pending' + (this.pendingSelected ? ' selected' : '')}
            aria-pressed=${String(Boolean(this.pendingSelected))}
            aria-label=${t('gallery.pending.show')} @click=${() => this.showPending?.()}>
            <span class="still"><span class="video-pending-indicator"></span><span>${t('gallery.pending.generating')}</span></span>
            ${this.pendingSelected ? pencilLoop(false) : nothing}
          </button>` : nothing}
          <gallery-window axis="vertical" .items=${this.rows(items)} .selected=${this.selectedId} .renderItem=${row => this.card(row)}></gallery-window>
          ${!items.length ? html`<div class="gallery-no-results"><strong>${this.items.length ? t('gallery.noMatches') : t('gallery.noResults')}</strong>
            ${this.items.length ? html`<button type="button" class="text-btn" @click=${() => {
              this.query = ''; this.mode = ''; this.model = ''; this.change('group', '');
            }}>${t('gallery.clearFilters')}</button>` : nothing}</div>` : nothing}
        </div>
      </section>` : nothing}`;
  }
}
customElements.define('gallery-browser', GalleryBrowser);
