import {LitElement, html, nothing} from '/page/vendor/lit.js';
import {queueVideoPreview} from '../lib/video-preview-queue.js';
import {watchVideoPreview} from '../lib/video-preview-clock.js';

// Prepare tiny contact sheets with bounded decoders, then reveal the visible group
// together; never leave a decoder running for each gallery card.
const frames = 16, width = 128, height = 72;
const cache = new Map();
const motion = matchMedia('(prefers-reduced-motion: reduce)'), previews = new Set();
motion.addEventListener('change', () => previews.forEach(preview => preview.refresh()));
function waitFor(video, event, start) {
  return new Promise((resolve, reject) => {
    const finish = error => {
      clearTimeout(timeout); video.removeEventListener(event, ready); video.removeEventListener('error', failed);
      error ? reject(error) : resolve();
    };
    const ready = () => finish(), failed = () => finish(new Error('Preview unavailable'));
    const timeout = setTimeout(failed, 10000);
    video.addEventListener(event, ready, {once: true}); video.addEventListener('error', failed, {once: true});
    start();
  });
}
async function contactSheet(source, active, key = source, animate = true, showPoster = () => {}) {
  if (!active()) return null;
  if (cache.has(key) && (!animate || cache.get(key).blob)) {
    const saved = cache.get(key); cache.delete(key); cache.set(key, saved); return saved;
  }
  const video = document.createElement('video');
  video.muted = true; video.playsInline = true; video.preload = 'metadata';
  try {
    await waitFor(video, 'loadeddata', () => { video.src = source; video.load(); });
    if (!video.videoWidth || !Number.isFinite(video.duration) || video.duration <= 0) return null;
    const seconds = Math.min(2, video.duration);
    const count = animate ? frames : 1;
    const canvas = document.createElement('canvas'); canvas.width = width * count; canvas.height = height;
    const context = canvas.getContext('2d');
    const scale = Math.min(width / video.videoWidth, height / video.videoHeight);
    const w = video.videoWidth * scale, h = video.videoHeight * scale;
    context.fillStyle = '#181818'; context.fillRect(0, 0, canvas.width, height);
    let poster;
    for (let index = 0; index < count; index++) {
      if (!active()) return null;
      // A tiny initial seek also uploads frame zero on hardware decoders that
      // report loadeddata before its first texture is available to canvas.
      await waitFor(video, 'seeked', () => { video.currentTime = index ? seconds * index / frames : Math.min(0.001, seconds / 16); });
      if (!active()) return null;
      context.drawImage(video, index * width + (width - w) / 2, (height - h) / 2, w, h);
      if (!index) {
        const still = document.createElement('canvas'); still.width = width; still.height = height;
        still.getContext('2d').drawImage(canvas, 0, 0, width, height, 0, 0, width, height);
        poster = await new Promise(resolve => still.toBlob(resolve, 'image/webp', 0.75));
        if (!active()) return null;
        if (poster) showPoster(poster);
      }
    }
    const blob = animate ? await new Promise(resolve => canvas.toBlob(resolve, 'image/webp', 0.55)) : null;
    if (!poster || !active()) return null;
    const result = {blob, poster, seconds};
    cache.set(key, result);
    if (cache.size > 32) cache.delete(cache.keys().next().value);
    return result;
  } finally {
    video.removeAttribute('src'); video.load();
  }
}

class VideoGalleryPreview extends LitElement {
  static properties = {source: {}, cacheKey: {}, poster: {}, blocked: {type: Boolean}, sheet: {state: true}, still: {state: true}, seconds: {state: true}};
  constructor() { super(); this.visible = false; this.sheet = ''; this.ticket = 0; }
  createRenderRoot() { return this; }
  connectedCallback() {
    super.connectedCallback();
    this.motion = motion;
    previews.add(this);
    this.onVisibility = () => this.refresh();
    document.addEventListener('visibilitychange', this.onVisibility);
    this.observer = new IntersectionObserver(entries => {
      this.visible = entries[0].isIntersecting; this.refresh();
    }, {threshold: 0.05});
    this.observer.observe(this);
  }
  disconnectedCallback() {
    this.observer?.disconnect(); document.removeEventListener('visibilitychange', this.onVisibility);
    previews.delete(this); this.clear();
    super.disconnectedCallback();
  }
  updated(changes) {
    if (changes.has('source')) { this.clear(); this.failed = ''; }
    if (changes.has('source') || changes.has('blocked')) this.refresh();
    if (changes.has('sheet') && this.sheet) this.startMotion();
  }
  startMotion() {
    const image = this.motionImage;
    if (!image || !this.active()) return;
    this.stopMotion?.();
    this.frameIndex = -1;
    this.stopMotion = watchVideoPreview(time => {
      if (!this.active()) { this.refresh(); return; }
      const index = Math.floor((time % (this.seconds * 1000)) / (this.seconds * 1000) * frames);
      if (index === this.frameIndex) return;
      const canvas = this.querySelector('canvas.video-gallery-sheet');
      if (!canvas) return;
      canvas.getContext('2d').drawImage(image, index * width, 0, width, height, 0, 0, width, height);
      this.frameIndex = index;
    });
  }
  active() {
    return this.readable() && !this.motion?.matches;
  }
  readable() {
    return this.isConnected && this.visible && !document.hidden && !this.blocked
      && this.source?.startsWith('blob:');
  }
  clear(keepStill = false) {
    this.ticket++;
    this.stopMotion?.(); this.stopMotion = null;
    this.motionImage = null; this.frameIndex = -1;
    if (this.sheet) URL.revokeObjectURL(this.sheet);
    this.sheet = '';
    if (!keepStill) {
      if (this.still) URL.revokeObjectURL(this.still);
      this.still = '';
    }
  }
  refresh() {
    if (!this.readable()) {
      this.clear(this.isConnected && this.visible && !document.hidden);
      return;
    }
    const animate = this.active();
    if (this.requestedAnimation !== animate) {
      this.requestedAnimation = animate;
      this.clear(true);
    }
    if (!animate && this.sheet) this.clear(true);
    if (!animate && (this.still || this.poster)) return;
    if (!this.still && cache.get(this.cacheKey || this.source)?.poster) {
      this.still = URL.createObjectURL(cache.get(this.cacheKey || this.source).poster);
    }
    if (this.sheet || this.queued || this.failed === this.source) return;
    const source = this.source, ticket = ++this.ticket;
    this.queued = true;
    const active = () => this.readable() && this.source === source && this.ticket === ticket;
    const showPoster = poster => {
      if (!active()) return;
      if (this.still) URL.revokeObjectURL(this.still);
      this.still = URL.createObjectURL(poster);
    };
    const task = queueVideoPreview(async () => {
      const result = await contactSheet(source, active, this.cacheKey || source, animate, showPoster);
      if (!result?.blob || !active()) return result;
      const image = new Image(), url = URL.createObjectURL(result.blob);
      try { image.src = url; await image.decode(); }
      finally { URL.revokeObjectURL(url); }
      return {...result, image};
    });
    task.then(result => {
      if (result && active()) {
        this.seconds = result.seconds;
        if (this.still) URL.revokeObjectURL(this.still);
        this.still = URL.createObjectURL(result.poster);
        if (result.blob && this.active()) {
          this.motionImage = result.image;
          this.sheet = URL.createObjectURL(result.blob);
        }
      }
    }).catch(() => { if (active()) this.failed = source; }).finally(() => {
      this.queued = false;
      if (ticket !== this.ticket && this.readable()) this.refresh();
    });
  }
  render() {
    return this.sheet ? html`<canvas class="video-gallery-sheet" width="128" height="72" aria-hidden="true"></canvas>`
      : this.poster || this.still ? html`<img src=${this.poster || this.still} alt="" loading="lazy" decoding="async">` : nothing;
  }
}
customElements.define('video-gallery-preview', VideoGalleryPreview);
