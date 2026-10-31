import {LitElement, html, svg, nothing, render} from 'https://cdn.jsdelivr.net/npm/lit@3.2.1/+esm';
import {audioPeaks, blobBase64, decodeAudio, downloadAudio, joinAudio, normalizeReference, TRACK_GAP} from '../lib/voice-audio.js';
import {clearVoice, loadVoice, loadVoiceTake, saveVoice} from '../lib/voice-store.js';
import {startRecording} from '../lib/recorder.js';
import {closeMenus, toggleMenu} from './popup-menu.js';
import './run-button.js';
import './audio-preview.js';
import {mediaDownloadName, mediaExtension} from '../lib/download-name.js';
import {pencilLoop} from './gallery-marker.js';
import './gallery-browser.js';
import './gallery-window.js';
import {galleryBatch, preferredGalleryId, rememberGalleryView} from '../lib/gallery-view.js';
import {t, plural, label} from '../lib/i18n.js';

const DEFAULT_CAPABILITIES = {name: 'Drama-3', modes: []};

const MODE_KEYS = {
  generate: 'voice.mode.generate',
  design: 'voice.mode.design',
  clone: 'voice.mode.clone',
  edit: 'voice.mode.edit',
};

function modeLabel(id, fallback = '') {
  const key = MODE_KEYS[id];
  return key ? t(key) : fallback || id;
}

function transcriptText(text) {
  if (String(text).includes('<|phoneme_start|>')) return '';
  return String(text).replace(/\[[^\]]*\]/g, '').replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim();
}

function durationLabel(seconds) {
  return Number.isFinite(seconds) ? t('voice.duration.seconds', {value: seconds.toFixed(1)}) : '';
}

class VoiceStudio extends LitElement {
  static properties = {
    script: {state: true}, segments: {state: true}, mode: {state: true}, voice: {state: true},
    editText: {state: true},
    reference: {state: true}, referencePending: {state: true}, selectedId: {state: true}, templateName: {state: true},
    fieldValues: {state: true}, activeOperation: {state: true}, showGeneration: {state: true}, recording: {state: true},
    engineOptions: {state: true}, capabilities: {state: true}, seconds: {state: true}, convert: {state: true}, seed: {state: true},
    busy: {state: true}, stopping: {state: true}, error: {state: true}, playing: {state: true},
    position: {state: true}, trackDuration: {state: true}, detailsOpen: {state: true}, previewReady: {state: true}, previewBusy: {state: true}, previewSource: {attribute: false}, previewSpeed: {state: true},
  };

  constructor() {
    super();
    this.script = '';
    this.draftId = crypto.randomUUID();
    this.editText = '';
    this.segments = [];
    this.mode = 'design';
    this.voice = '';
    this.reference = null;
    this.referencePending = false;
    this.selectedId = null;
    this.templateName = '';
    this.fieldValues = {};
    this.activeOperation = null;
    this.showGeneration = false;
    this.recording = false;
    this.recordingPending = false;
    this.recordingText = '';
    this.recordingActive = 0;
    this.capture = null;
    this.capabilities = DEFAULT_CAPABILITIES;
    this.seconds = 0;
    this.convert = 'tw2s';
    this.seed = '';
    this.busy = false;
    this.stopping = false;
    this.error = '';
    this.playing = false;
    this.position = 0;
    this.trackDuration = 0;
    this.detailsOpen = false;
    this.previewReady = false;
    this.previewBusy = false;
    this.previewSource = null;
    this.previewSpeed = 1;
    this.options = {};
    this.engineOptions = {};
    this.saved = Promise.resolve();
    this.loading = true;
    this.importing = new Set();
    this.imported = new Set();
    this.batchCounts = new Map();
    this.fetchedItems = new Set();
    this.removed = new Set();
    this.cutoff = 0;
    try {
      this.removed = new Set(JSON.parse(localStorage.getItem('studio-voice-removed') || '[]'));
      this.cutoff = Number(localStorage.getItem('studio-voice-cutoff') || 0);
    } catch (error) { console.warn('Voice removals could not be read:', error); }
    this.urls = new Set();
    this.storageEpoch = 0;
    this.referenceVersion = 0;
    this.trackRevision = 0;
    this.playbackRevision = 0;
    this.player = new Audio();
    this.player.onended = () => { this.playing = false; };
    this.player.onpause = () => { this.playing = false; };
    this.player.onplay = () => { this.playing = true; };
    this.player.ontimeupdate = () => { this.position = this.player.currentTime; };
    this.player.ondurationchange = () => { this.trackDuration = Number.isFinite(this.player.duration) ? this.player.duration : 0; };
    this.player.onerror = () => this.fail(t('voice.error.playAudio'));
    this.channel = typeof BroadcastChannel === 'function' ? new BroadcastChannel('studio-voice') : null;
    if (this.channel) this.channel.onmessage = event => this.receive(event.data);
    this.pasteHandler = event => {
      if (this.hidden || this.locked) return;
      const file = Array.from(event.clipboardData?.files || []).find(item => item.type.startsWith('audio/'));
      if (file) { event.preventDefault(); this.addReference(file); }
    };
  }

  createRenderRoot() { return this; }

  connectedCallback() {
    super.connectedCallback();
    document.addEventListener('paste', this.pasteHandler);
    this.restore();
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    this.player.pause();
    this.channel?.close();
    document.removeEventListener('paste', this.pasteHandler);
    this.urls.forEach(url => URL.revokeObjectURL(url));
    this.stopRecording();
  }

  configure(options) {
    this.options = {...this.options, ...options};
    if (options.capabilities) {
      if ((this.capabilities.backend_id || this.draftBackend) && (this.capabilities.backend_id || this.draftBackend) !== options.capabilities.backend_id) {
        this.templateName = '';
        this.fieldValues = {};
        this.engineOptions = {};
      }
      this.capabilities = options.capabilities;
      this.reconcileMode();
      this.trimReferenceIfNeeded();
    }
    this.requestUpdate();
  }

  reconcileMode() {
    if (this.capabilities.modes.length && !this.capabilities.modes.some(mode => mode.id === this.mode)) {
      this.stopRecording();
      this.mode = this.capabilities.default_mode || this.capabilities.modes[0].id;
      this.templateName = '';
      this.fieldValues = {};
    }
  }

  hasParam(id) { return Boolean(this.currentMode?.params.some(param => param.id === id)); }

  // A parameter the model declares arrives with an id and a hint, never a label. The table
  // speaks first by id, and the id's own words stay the fallback, so a new model needs no copy.
  paramLabel(param) {
    return label('param', param.id, param.id.replaceAll('_', ' ').replace(/\b\w/g, letter => letter.toUpperCase()));
  }

  paramHint(param) {
    return label('param', param.id + '.hint', param.hint || '');
  }

  get needsReference() { return Boolean(this.currentMode?.min_references); }

  get takesCount() { return this.segments.reduce((count, segment) => count + segment.takes.length, 0); }

  get selectedTakes() {
    return this.segments.filter(segment => segment.inScript !== false).map(segment => segment.takes.find(take => take.id === segment.selected) || segment.takes[0]).filter(Boolean);
  }

  get scriptDuration() {
    const takes = this.selectedTakes;
    return takes.reduce((total, take) => total + take.duration, 0) + Math.max(0, takes.length - 1) * TRACK_GAP;
  }
  get currentMode() { return this.capabilities.modes.find(mode => mode.id === this.mode); }
  get templates() { return this.currentMode?.templates || []; }
  get selectedTake() {
    for (const segment of this.segments) {
      const take = segment.takes.find(item => item.id === this.selectedId);
      if (take) return {segment, take};
    }
    return null;
  }
  get previewItem() {
    if (this.selectedTake) return this.selectedTake;
    const segment = this.segments.find(item => item.takes.length) || this.segments[0];
    if (!segment) return null;
    return {segment, take: segment.takes.find(take => take.id === segment.selected) || segment.takes[0] || null};
  }

  get pending() { return this.segments.filter(segment => segment.inScript !== false && !segment.takes.length); }
  get ready() { return Boolean(this.capabilities.modes.length && this.options.clientId); }
  get referenceBusy() { return this.needsReference && (this.referencePending || this.recordingPending); }
  get locked() { return this.busy || Boolean(this.activeOperation); }
  get voiceRunning() { return this.busy || this.activeOperation?.kind === 'voice'; }
  get showingGeneration() { return this.voiceRunning && this.showGeneration; }
  get instruction() {
    const template = this.templates.find(item => item.name === this.templateName);
    if (!template) return this.editText.trim();
    return template.text.replace(/\{([^}]+)\}/g, (_, name) => String(this.fieldValues[name] ?? ''));
  }
  get templateComplete() {
    const template = this.templates.find(item => item.name === this.templateName);
    return !template?.fields.some(field => String(this.fieldValues[field.id] ?? '').trim() === '');
  }
  get referenceLimitReason() {
    const limit = this.capabilities.max_seconds || 120;
    return this.needsReference && this.reference?.duration > limit ? t('voice.reason.referenceTooLong', {seconds: limit}) : '';
  }
  get referenceClipSeconds() {
    return this.capabilities.backend_id === 'drama3' ? this.capabilities.max_seconds || 15 : Infinity;
  }

  trimReferenceIfNeeded() {
    if (this.reference?.duration > this.referenceClipSeconds && !this.referencePending) {
      this.chooseReference(this.reference.blob, this.reference);
    }
  }
  get reason() {
    if (!this.ready) return t('voice.reason.connecting');
    if (this.locked) return t('voice.reason.operationActive');
    if (this.recording) return t('voice.reason.stopRecording');
    if (this.referenceBusy) return this.recordingPending ? t('voice.status.openingMicrophone') : t('voice.status.preparingReference');
    if (this.needsReference && !this.reference) return t('voice.reason.addReference');
    if (this.referenceLimitReason) return this.referenceLimitReason;
    if (this.hasParam('ref_text') && !this.reference?.transcript?.trim()) return t('voice.reason.transcribeReference');
    for (const param of this.currentMode?.params || []) {
      if (param.kind !== 'number') continue;
      const value = this.engineOptions[param.id] ?? param.default;
      if (!Number.isFinite(value) || (param.minimum != null && value < param.minimum)
          || (param.maximum != null && value > param.maximum) || (param.integer && !Number.isInteger(value))) {
        return t('voice.reason.paramRange', {
          label: this.paramLabel(param), minimum: param.minimum, maximum: param.maximum,
        });
      }
    }
    if (!this.templateComplete) return t('voice.reason.fillTemplate');
    if (this.mode === 'design' && !this.voice.trim()) {
      return this.script.trim() ? t('voice.reason.chooseVoice') : t('voice.reason.addScriptAndVoice');
    }
    if (this.mode === 'edit') {
      const template = this.templates.find(item => item.name === this.templateName);
      if (template?.fields.some(field => String(this.fieldValues[field.id] ?? '').trim() === '')) return t('voice.reason.fillTemplate');
      return this.instruction ? '' : t('voice.action.describeChange');
    }
    if (!this.segments.some(segment => segment.inScript !== false)) return t('voice.action.writeScript');
    return '';
  }

  fail(message) {
    this.error = message;
    this.options.notify?.('error', message);
  }

  async restore() {
    try {
      if (localStorage.getItem('studio-keep') === 'off') return;
      const stored = await loadVoice();
      if (stored && !this.script && !this.takesCount) this.adopt(stored);
    } catch (error) {
      this.options.notify?.('error', t('voice.error.storageOpen'));
      console.warn(error);
    } finally {
      this.loading = false;
    }
  }

  adopt(stored) {
    this.script = stored.script || '';
    this.draftId = stored.draftId || null;
    this.editText = stored.editText || '';
    this.voice = stored.voice || '';
    this.mode = stored.mode || this.capabilities.default_mode || 'design';
    this.seconds = stored.seconds || 0;
    this.convert = stored.convert || 'tw2s';
    this.seed = stored.seed ?? '';
    this.draftBackend = stored.backend || null;
    this.engineOptions = stored.backend && this.capabilities.backend_id && stored.backend !== this.capabilities.backend_id ? {} : stored.engineOptions || {};
    this.reference = stored.reference || null;
    this.templateName = stored.templateName || '';
    this.fieldValues = stored.fieldValues || {};
    this.editSegmentId = stored.editSegmentId || null;
    if (stored.backend && this.capabilities.backend_id && stored.backend !== this.capabilities.backend_id) { this.templateName = ''; this.fieldValues = {}; }
    this.reconcileMode();
    this.trimReferenceIfNeeded();
    this.cutoff = Math.max(this.cutoff, stored.cutoff || 0);
    this.removed = new Set([...this.removed, ...(stored.removed || [])]);
    this.segments = (stored.segments || []).map(segment => ({...segment,
      takes: segment.takes.filter(take => !this.removed.has(take.id) && take.createdAt > this.cutoff).map(take => this.hydrate(take)),
    })).filter(segment => segment.inScript !== false || segment.takes.length);
    this.selectedId = preferredGalleryId('voice', this.segments.flatMap(segment => segment.takes), this.options.keeping?.() !== false)
      || stored.selectedId || null;
    if (this.mode !== 'edit') this.setScript(this.script);
  }

  hydrate(take) { return {...take}; }

  async retainMedia() {
    await this.saved;
    this.retainingMedia = true;
    try {
      for (const segment of this.segments) for (const take of segment.takes) await this.ensureTake(take);
      for (const segment of this.segments) for (const take of segment.takes) take.stored = false;
    } finally { this.retainingMedia = false; }
  }

  trimTakeMedia() {
    if (this.retainingMedia || this.forgettingMedia || this.options.keeping?.() === false) return;
    const selected = this.previewItem?.take;
    let spare = 0;
    for (const segment of this.segments) for (const take of segment.takes) {
      if (!take.stored || !take.blob || take === selected) continue;
      if (spare++ < 1) continue;
      delete take.blob;
    }
  }

  async ensureTake(take) {
    if (take.blob) return take.blob;
    if (!take.mediaLoading) take.mediaLoading = loadVoiceTake(take.id).then(blob => {
      if (!blob) throw new Error(t('voice.error.clipMissing'));
      if (this.segments.some(segment => segment.takes.includes(take))) {
        take.blob = blob; this.trimTakeMedia(); this.requestUpdate();
      }
      return blob;
    }).finally(() => { delete take.mediaLoading; });
    return take.mediaLoading;
  }

  snapshot() {
    return {
      backend: this.capabilities.backend_id, script: this.script, draftId: this.draftId, editText: this.editText, voice: this.voice, mode: this.mode, seconds: this.seconds,
      engineOptions: this.engineOptions, convert: this.convert, seed: this.seed, reference: this.reference,
      templateName: this.templateName, fieldValues: this.fieldValues, editSegmentId: this.editSegmentId,
      cutoff: this.cutoff, removed: Array.from(this.removed).slice(-2048), selectedId: this.selectedId,
      segments: this.segments.map(segment => ({...segment, takes: segment.takes.map(({url, mediaLoading, mediaError, ...take}) => take)})),
    };
  }

  persist(draft = false, selection = null, expectedDraftId = undefined) {
    if (this.loading || this.options.keeping?.() === false) return;
    if (draft) this.draftId = crypto.randomUUID();
    const project = this.snapshot();
    const epoch = this.storageEpoch;
    this.saved = this.saved.then(() => {
      if (epoch === this.storageEpoch && this.options.keeping?.() !== false) return saveVoice(project, draft, selection, expectedDraftId).then(() => {
        const saved = new Set(project.segments.flatMap(segment => segment.takes.map(take => take.id)));
        for (const segment of this.segments) for (const take of segment.takes) if (saved.has(take.id)) take.stored = true;
        this.trimTakeMedia();
      });
    }).catch(error => {
      console.warn(error);
      this.options.notify?.('error', t('voice.error.projectNotKept'));
    });
  }

  receive(message) {
    if (message.kind === 'take') this.addTake(message.take, message.text, false, message.segmentId);
    if (message.kind === 'remove') this.removeTake(message.id, false);
    if (message.kind === 'clear') this.clearCompleted(message.cutoff, false);
  }

  setScript(value) {
    this.invalidateTrack();
    this.script = value;
    if (this.mode !== 'edit') {
      const remaining = this.segments.slice();
      const texts = value.trim() ? [value.trim()] : [];
      const current = texts.map(text => {
        const index = remaining.findIndex(segment => segment.text === text);
        return index >= 0 ? {...remaining.splice(index, 1)[0], inScript: true}
          : {id: crypto.randomUUID(), text, takes: [], selected: null, inScript: true};
      });
      const history = remaining.filter(segment => segment.takes.length).map(segment => ({...segment, inScript: false}));
      this.segments = [...current, ...history];
    }
    this.persist(true);
  }

  selectMode(mode) {
    if (this.locked) return;
    if (!this.capabilities.modes.some(candidate => candidate.id === mode)) return;
    if (!this.capabilities.modes.find(candidate => candidate.id === mode)?.min_references) this.finishRecording();
    this.mode = mode;
    this.templateName = '';
    this.fieldValues = {};
    this.error = '';
    if (mode !== 'edit') this.setScript(this.script);
    else this.persist(true);
  }

  selectTemplate(name) {
    if (this.locked) return;
    closeMenus();
    this.templateName = name;
    const template = this.templates.find(item => item.name === name);
    this.fieldValues = Object.fromEntries((template?.fields || []).map(field => [field.id, field.default ?? '']));
    if (template?.target === 'voice') this.voice = this.templateText(template);
    else if (template && this.mode !== 'edit') this.setScript(this.templateText(template));
    else if (this.mode === 'design') this.voice = '';
    this.persist(true);
  }

  templateText(template, values = this.fieldValues) {
    return template.text.replace(/\{([^}]+)\}/g, (_, name) => String(values[name] ?? template.fields.find(field => field.id === name)?.default ?? ''));
  }

  setTemplateValue(name, value) {
    this.fieldValues = {...this.fieldValues, [name]: value};
    const template = this.templates.find(item => item.name === this.templateName);
    if (template?.target === 'voice') this.voice = this.templateText(template);
    else if (template && this.mode !== 'edit') this.setScript(this.templateText(template));
    this.persist(true);
  }

  async chooseReference(file, {name, transcript = ''} = {}) {
    if (!file || this.locked) return;
    const version = ++this.referenceVersion;
    this.referencePending = false;
    if (file.size > (this.capabilities.max_reference_megabytes || 32) * 1024 * 1024) {
      this.fail(t('voice.error.referenceTooLarge'));
      return;
    }
    this.referencePending = true;
    try {
      let normalized, backend;
      do {
        backend = this.capabilities.backend_id;
        normalized = await normalizeReference(file, this.capabilities.reference_sample_rate || 24000, this.referenceClipSeconds);
        if (version !== this.referenceVersion || this.locked) return;
      } while (backend !== this.capabilities.backend_id);
      if (normalized.duration > (this.capabilities.max_seconds || 120)) throw new Error(t('voice.error.referenceTooLong', {seconds: this.capabilities.max_seconds || 120}));
      if (normalized.blob.size > (this.capabilities.max_reference_megabytes || 32) * 1024 * 1024) throw new Error(t('voice.error.referenceNormalizedTooLarge'));
      this.reference = {...normalized, name: name || file.name || 'recording.wav', transcript: normalized.trimmed ? '' : transcript};
      this.editSegmentId = null;
      this.error = '';
      this.persist(true);
    } catch (error) {
      if (version === this.referenceVersion) this.fail(t('voice.error.referenceUnreadable', {message: error.message}));
    } finally {
      if (version === this.referenceVersion) this.referencePending = false;
    }
  }

  async addReference(file) {
    if (!file || this.locked) return;
    if (!file.type.startsWith('audio/')) { this.fail(t('voice.error.referenceNotAudio')); return; }
    if (!this.needsReference) this.selectMode('clone');
    await this.chooseReference(file);
  }

  toggleRecording() {
    if (this.recording) { this.stopRecording(); return; }
    if (this.reference || this.recordingPending || this.locked) return;
    this.recordingPending = true;
    this.requestUpdate();
    this.capture = startRecording({
      maxSeconds: this.capabilities.max_seconds || 120,
      onStart: () => {
        // The microphone can arrive after the mode or the workspace moved on.
        if (this.hidden || this.locked || !this.needsReference) {
          this.capture?.cancel();
          this.recordingPending = false;
          this.requestUpdate();
          return;
        }
        this.recording = true;
        this.recordingPending = false;
        this.recordingActive = 0;
        this.recordingText = this.recordingTextFor({active: 0, needed: 7});
        this.requestUpdate();
      },
      onTick: values => {
        this.recordingActive = values.active;
        this.recordingText = this.recordingTextFor(values);
        this.paintRecordingStatus();
      },
      onShort: values => this.reportShortTake(values),
      onFinish: file => {
        this.recording = false;
        this.recordingPending = false;
        this.capture = null;
        this.requestUpdate();
        this.chooseReference(file);
      },
      onError: message => {
        this.recording = false;
        this.recordingPending = false;
        this.capture = null;
        this.requestUpdate();
        this.fail(message);
      },
    });
  }

  // The line under the reference: the microphone opening, then the seconds of sound the
  // take holds, then that it is long enough. Stop below the minimum asks for a moment more.
  recordingTextFor({active, needed}) {
    return active >= needed
      ? t('record.ready', {needed})
      : t('record.progress', {active: active.toFixed(1), needed});
  }
  paintRecordingStatus() {
    // The form is rendered into `#voice-controls`, outside this element.
    const status = document.getElementById('voice-recording-status');
    if (!status) return;
    status.textContent = this.recordingPending ? t('record.opening') : this.recordingText;
    status.classList.toggle('is-recording', this.recording);
  }
  reportShortTake({active, needed, dropped}) {
    if (!dropped) {
      this.options.notify('info', t('record.keep_going', {remaining: (needed - active).toFixed(1)}));
      return;
    }
    this.recording = false;
    this.recordingPending = false;
    this.capture = null;
    this.recordingText = '';
    this.requestUpdate();
    this.options.notify('error', t('record.dropped', {active: active.toFixed(1), needed}));
  }
  // A mode or workspace that moves on ends the take rather than leaving the microphone
  // open. A take under the minimum is dropped, so the form never keeps a hum that is too
  // short for the engine.
  finishRecording() {
    if (this.recordingPending) { this.stopRecording(); return; }
    this.capture?.finish();
  }
  // Voice keeps the take: a mode or workspace that moves on still leaves the recording in
  // the form, which is what the Clone reference is for.
  stopRecording() {
    if (this.recordingPending) {
      this.capture?.cancel();
      this.capture = null;
      this.recordingPending = false;
      this.requestUpdate();
      return;
    }
    this.capture?.stop();
  }

  setOperation(operation) {
    const previous = this.activeOperation;
    this.activeOperation = operation;
    if (operation?.kind === 'voice' && operation.id !== previous?.id && !this.busy) {
      const mode = operation.mode || operation.settings?.mode;
      if (this.capabilities.modes.some(candidate => candidate.id === mode)) this.mode = mode;
      this.showGeneration = true;
      this.detailsOpen = false;
      this.pausePlayback();
    }
  }

  async generate(segment = null) {
    if (!this.ready || this.locked || this.recording || this.referenceBusy || (!segment && this.reason)) return;
    if (segment && this.referenceLimitReason) { this.fail(this.referenceLimitReason); return; }
    if (segment && this.hasParam('ref_text') && !this.reference?.transcript?.trim()) { this.fail(t('voice.reason.transcribeReference')); return; }
    if (segment && !this.templateComplete) { this.fail(t('voice.reason.fillTemplate')); return; }
    if (segment && this.needsReference && !this.reference) { this.fail(t('voice.reason.addReferenceFirst')); return; }
    const submittedDraftId = this.draftId;
    this.showGeneration = true;
    this.detailsOpen = false;
    this.pausePlayback();
    this.busy = true;
    this.error = '';
    try {
      const items = this.mode === 'edit' ? [{text: this.instruction, segment_id: this.editSegmentId,
        segment_text: this.segments.find(item => item.id === this.editSegmentId)?.text}]
        : (segment ? [segment] : this.segments.filter(item => item.inScript !== false).slice(0, 1)).map(item => ({text: item.text, segment_id: item.id}));
      const payload = {
        kind: 'voice', workspace: 'voice', backend: this.capabilities.backend_id || 'auk', mode: this.mode,
        client_id: this.options.clientId,
      };
      for (const param of this.currentMode.params) {
        if (param.id in this.engineOptions) payload[param.id] = this.engineOptions[param.id];
      }
      if (this.hasParam('voice')) payload.voice = this.voice;
      if (this.hasParam('seconds')) payload.seconds = Number(this.seconds);
      if (this.hasParam('convert')) payload.convert = this.convert;
      if (this.hasParam('ref_text')) payload.ref_text = this.reference?.transcript || '';
      if (this.templateName) {
        payload.template = this.templateName;
        payload.template_values = {...this.fieldValues};
      }
      if (this.seed !== '') payload.seed = Number(this.seed);
      const reference = this.needsReference ? this.reference : null;
      if (reference) payload.reference = {wav_base64: await blobBase64(reference.blob), name: reference.name};
      if (items.length === 1) Object.assign(payload, items[0]);
      else payload.items = items;
      const response = await fetch('/voice/operations', {
        method: 'POST', headers: {'Content-Type': 'application/json', 'X-Studio-Client': this.options.clientId,
          'X-Studio-Library': this.options.libraryId}, body: JSON.stringify(payload),
      });
      const operation = await response.json();
      if (!response.ok) throw new Error(operation.error || t('voice.error.startFailed'));
      this.ownOperationId = operation.id;
      this.requestUpdate();
      let state;
      do {
        await new Promise(resolve => setTimeout(resolve, 350));
        const answer = await fetch('/api/v1/operations/' + encodeURIComponent(operation.id), {cache: 'no-store'});
        state = await answer.json();
        if (!answer.ok) throw new Error(state.error || t('voice.error.statusFailed'));
        if (state.result_url && state.batch_completed > 0) await this.importOperation(state);
      } while (state.status === 'running' || state.status === 'stopping');
      if (state.result_url) await this.importOperation(state);
      document.dispatchEvent(new CustomEvent('operation-imported', {detail: operation.id}));
      if (state.status === 'failed') throw new Error(state.error || t('voice.error.operationFailed'));
      if (state.status === 'succeeded') this.clearInputs(submittedDraftId);
      if (state.status === 'cancelled') this.options.notify?.('info', t('voice.toast.operationStopped'));
    } catch (error) {
      this.fail(error.message);
    } finally {
      this.ownOperationId = null;
      this.busy = false;
      this.stopping = false;
      this.persist();
    }
  }

  clearInputs(expectedDraftId) {
    this.invalidateTrack();
    this.script = '';
    this.voice = '';
    this.editText = '';
    this.templateName = '';
    this.fieldValues = {};
    this.referenceVersion += 1;
    this.reference = null;
    this.referencePending = false;
    this.editSegmentId = null;
    this.seed = '';
    this.seconds = 0;
    this.convert = 'tw2s';
    this.engineOptions = {};
    this.segments = this.segments.filter(segment => segment.takes.length).map(segment => ({...segment, inScript: false}));
    this.persist(true, null, expectedDraftId);
  }

  async importOperation(operation, answer = null) {
    if (this.imported.has(operation.id) || this.importing.has(operation.id)) return;
    if (['running', 'stopping'].includes(operation.status) && this.batchCounts.get(operation.id) >= operation.batch_completed) return;
    this.importing.add(operation.id);
    try {
      const response = answer || await fetch(operation.result_url, {cache: 'no-store'});
      if (!response.ok) throw new Error(t('voice.error.resultUnreadable'));
      if ((response.headers.get('content-type') || '').includes('application/json')) {
        const manifest = await response.json();
        for (const [index, item] of (manifest.items || manifest.results || []).entries()) {
          if (!item.result_url) continue;
          const identity = operation.id + ':' + index;
          if (this.fetchedItems.has(identity)) continue;
          const answer = await fetch(item.result_url);
          if (!answer.ok) throw new Error(t('voice.error.segmentLoad'));
          await this.addAudio(await answer.blob(), {...operation, ...item,
            id: identity, text: item.text || item.settings?.text || operation.settings?.items?.[index]?.text,
          });
          this.fetchedItems.add(identity);
        }
        this.batchCounts.set(operation.id, manifest.items?.length || manifest.results?.length || 0);
      } else {
        await this.addAudio(await response.blob(), {...operation, text: operation.text || operation.settings?.text});
      }
      if (!['running', 'stopping'].includes(operation.status)) this.imported.add(operation.id);
    } finally {
      this.importing.delete(operation.id);
    }
  }

  async addAudio(blob, settings) {
    const id = 'voice-operation-' + settings.id;
    const createdAt = (settings.completed_at || settings.finished_at || Date.now() / 1000) * 1000;
    if (this.removed.has(id) || createdAt <= this.cutoff || this.segments.some(segment => segment.takes.some(take => take.id === id))) return;
    const decoded = await decodeAudio(blob);
    const design = this.capabilities.modes.find(mode => mode.id === 'design');
    const template = design?.templates?.find(item => item.name === (settings.settings?.template || settings.template));
    const voice = template ? this.templateText(template, settings.settings?.template_values || settings.template_values || {})
      : settings.settings?.voice || settings.voice || '';
    const take = {id, blob, createdAt, duration: decoded.duration, peaks: audioPeaks(decoded.samples),
      seed: settings.seed, mode: settings.settings?.mode || settings.mode || 'design',
      voice, model: settings.model || 'AuK Flash',
      backend: settings.settings?.backend || settings.backend || (settings.model === 'AuK' ? 'auk_base' : 'auk'),
      convert: settings.settings?.convert || settings.convert || 'tw2s',
      elapsed: settings.finished_at && settings.started_at ? settings.finished_at - settings.started_at : null};
    this.addTake(take, settings.settings?.segment_text || settings.segment_text || settings.text || settings.prompt || t('voice.import.fallbackText'),
      true, settings.settings?.segment_id || settings.segment_id || 'voice-line-' + settings.id);
  }

  addTake(take, text, broadcast = true, segmentId = null) {
    this.detailsOpen = false;
    if (this.removed.has(take.id) || take.createdAt <= this.cutoff || this.segments.some(segment => segment.takes.some(item => item.id === take.id))) return;
    this.pausePlayback();
    this.invalidateTrack();
    const index = segmentId ? this.segments.findIndex(segment => segment.id === segmentId)
      : this.segments.findIndex(segment => segment.text === text && !segment.takes.length);
    const segment = index >= 0 ? this.segments[index] : {id: segmentId || crypto.randomUUID(), text, takes: [], selected: null, inScript: false};
    const updated = {...segment, takes: [...segment.takes, this.hydrate(take)], selected: take.id};
    this.segments = index >= 0 ? this.segments.map((item, offset) => offset === index ? updated : item) : [...this.segments, updated];
    this.selectedId = take.id;
    if (broadcast) this.channel?.postMessage({kind: 'take', take, text, segmentId: segment.id});
    this.persist(false, {segmentId: segment.id, takeId: take.id});
  }

  removeTake(id, broadcast = true) {
    this.detailsOpen = false;
    this.invalidateTrack();
    this.removed.add(id);
    this.saveRemovals();
    if (this.selectedId === id) { this.player.pause(); this.selectedId = null; }
    this.segments.forEach(segment => segment.takes.filter(take => take.id === id).forEach(take => this.releaseUrl(take.url)));
    this.segments = this.segments.map(segment => ({...segment, takes: segment.takes.filter(take => take.id !== id),
      selected: segment.selected === id ? segment.takes.find(take => take.id !== id)?.id || null : segment.selected}))
      .filter(segment => segment.inScript !== false || segment.takes.length);
    if (broadcast) this.channel?.postMessage({kind: 'remove', id});
    this.persist();
  }

  clearCompleted(cutoff = Date.now(), broadcast = true) {
    this.detailsOpen = false;
    this.invalidateTrack();
    this.player.pause();
    this.cutoff = Math.max(this.cutoff, cutoff);
    this.segments.forEach(segment => segment.takes.forEach(take => { if (take.createdAt <= this.cutoff) this.removed.add(take.id); }));
    this.segments.forEach(segment => segment.takes.filter(take => take.createdAt <= this.cutoff).forEach(take => this.releaseUrl(take.url)));
    this.saveRemovals();
    this.segments = this.segments.map(segment => ({...segment, takes: segment.takes.filter(take => take.createdAt > this.cutoff), selected: null}))
      .filter(segment => segment.inScript !== false || segment.takes.length);
    this.selectedId = null;
    if (broadcast) this.channel?.postMessage({kind: 'clear', cutoff});
    this.persist();
  }

  async setKeeping(keep) {
    rememberGalleryView('voice', {}, keep);
    if (keep) this.persist(true);
    else {
      this.storageEpoch += 1;
      try {
        await this.saved;
        await clearVoice();
      } catch (error) {
        console.warn(error);
        this.fail(t('voice.error.clearProject'));
      }
    }
  }

  selectTake(segmentId, takeId) {
    this.showGeneration = false;
    this.detailsOpen = false;
    closeMenus();
    this.pausePlayback();
    this.invalidateTrack();
    this.segments = this.segments.map(segment => segment.id === segmentId ? {...segment, selected: takeId} : segment);
    this.selectedId = takeId;
    rememberGalleryView('voice', {selected: takeId}, this.options.keeping?.() !== false);
    this.persist(false, {segmentId, takeId});
  }

  galleryKey(event) {
    const buttons = Array.from(this.querySelectorAll('.voice-clip, .voice-render-pending'));
    const index = buttons.indexOf(event.target.closest('button'));
    if (index < 0) return;
    const moves = {ArrowRight: Math.min(index + 1, buttons.length - 1), ArrowLeft: Math.max(0, index - 1), Home: 0, End: buttons.length - 1};
    if (!(event.key in moves)) return;
    event.preventDefault();
    event.stopPropagation();
    const button = buttons[moves[event.key]];
    button.click();
    button.focus();
    button.scrollIntoView({block: 'nearest', inline: 'nearest'});
  }

  stepTake(delta) {
    const clips = this.segments.flatMap(segment => segment.takes.map(take => ({segment, take})))
      .sort((a, b) => b.take.createdAt - a.take.createdAt);
    const next = clips[clips.findIndex(({take}) => take.id === this.previewItem?.take?.id) + delta];
    if (!next) return false;
    this.selectTake(next.segment.id, next.take.id);
    this.updateComplete.then(() => this.querySelector('.voice-clip.selected')?.scrollIntoView({block: 'nearest', inline: 'nearest'}));
    return true;
  }

  async togglePreviewPlayback() {
    const take = this.previewItem?.take, revision = this.playbackRevision;
    if (!take || this.hidden) return;
    try { await this.ensureTake(take); }
    catch (error) { this.fail(error.message); return; }
    if (this.previewItem?.take !== take) return;
    await this.updateComplete;
    if (revision !== this.playbackRevision || this.hidden || this.previewItem?.take !== take) return;
    return this.querySelector('audio-preview')?.play();
  }

  pausePlayback() {
    this.playbackRevision++;
    this.player.pause();
    this.querySelector('audio-preview')?.pause();
  }

  async useSelection(event) {
    if (this.hidden) return;
    if (this.locked) { this.fail(t('voice.reason.operationActive')); return; }
    const {action, blob, start, end, name} = event.detail;
    if (action === 'video') {
      try { await this.options.onSendToVideo?.({blob, name}); }
      catch (error) { this.fail(error.message); }
      return;
    }
    if (action === 'clone') {
      if (this.recording || this.referenceBusy) { this.fail(t('voice.reason.stopAndWait')); return; }
      this.pausePlayback();
      this.editSegmentId = null;
      this.selectMode('clone');
      await this.chooseReference(blob, {name, transcript: start === 0 && end === this.querySelector('audio-preview')?.duration ? transcriptText(this.previewItem?.segment.text || '') : ''});
      return;
    }
    if (action !== 'edit' || !this.capabilities.modes.some(mode => mode.id === 'edit')) return;
    const preview = this.querySelector('audio-preview');
    const take = this.previewItem?.take;
    if (take && preview?.blob === take.blob && start === 0 && end === preview.duration) {
      this.pausePlayback();
      await this.useForEdit(take);
      return;
    }
    this.pausePlayback();
    this.referenceVersion += 1;
    this.referencePending = false;
    this.reference = {blob, name, duration: end - start};
    this.editSegmentId = null;
    this.selectMode('edit');
  }

  async reuseSettings(item) {
    if (this.locked || this.recording || this.referenceBusy) return;
    closeMenus();
    this.pausePlayback();
    const {segment, take} = item;
    this.selectMode(this.capabilities.modes.some(mode => mode.id === take.mode) ? take.mode : this.capabilities.default_mode || 'design');
    this.voice = take.voice || '';
    this.convert = take.convert || 'tw2s';
    this.setScript(segment.text);
    if (this.needsReference) {
      await this.ensureTake(take);
      await this.chooseReference(take.blob, {name: 'voice-reference.wav', transcript: transcriptText(segment.text)});
    }
    this.persist(true);
    document.getElementById('voice-text')?.focus();
  }

  async useForEdit(take) {
    if (this.locked) return;
    await this.ensureTake(take);
    this.referenceVersion += 1;
    this.referencePending = false;
    this.reference = {blob: take.blob, name: 'take.wav', duration: take.duration};
    this.editSegmentId = this.segments.find(segment => segment.takes.some(item => item.id === take.id))?.id;
    this.selectMode('edit');
  }

  saveRemovals() {
    try {
      localStorage.setItem('studio-voice-removed', JSON.stringify(Array.from(this.removed).slice(-2048)));
      localStorage.setItem('studio-voice-cutoff', String(this.cutoff));
    } catch (error) { console.warn('Voice removals could not be saved:', error); }
  }

  releaseUrl(url) {
    if (!url) return;
    URL.revokeObjectURL(url);
    this.urls.delete(url);
  }

  invalidateTrack() {
    this.trackRevision++;
    if (this.trackUrl && this.player.src === this.trackUrl) {
      this.player.pause();
      this.player.removeAttribute('src');
      this.player.load();
      this.trackDuration = 0;
      this.position = 0;
    }
    this.releaseUrl(this.trackUrl);
    this.trackUrl = null;
  }

  async exportTrack(play = false) {
    const revision = this.trackRevision;
    const playbackRevision = this.playbackRevision;
    const takes = this.selectedTakes;
    if (!takes.length) return;
    try {
      const blobs = [];
      for (const take of takes) blobs.push(await this.ensureTake(take));
      const joined = await joinAudio(blobs);
      if (play) {
        if (revision !== this.trackRevision || playbackRevision !== this.playbackRevision) return;
        this.releaseUrl(this.trackUrl);
        const url = URL.createObjectURL(joined);
        this.trackUrl = url;
        this.urls.add(url);
        this.player.src = url;
        await this.player.play();
      } else downloadAudio(joined, mediaDownloadName({kind: 'audio', text: this.script,
        at: Math.max(...takes.map(take => take.createdAt || 0)) || undefined,
        id: takes.map(take => take.id).join(','), extension: 'wav'}));
    } catch (error) {
      if (!play || (revision === this.trackRevision && playbackRevision === this.playbackRevision)) this.fail(error.message);
    }
  }

  async playTrack() {
    const revision = ++this.playbackRevision;
    this.querySelector('audio-preview')?.pause();
    if (this.playing) { this.player.pause(); return; }
    if (this.trackUrl && this.player.src === this.trackUrl && !this.player.ended) {
      try { await this.player.play(); } catch (error) { if (revision === this.playbackRevision) this.fail(error.message); }
      return;
    }
    await this.exportTrack(true);
  }

  async cancel() {
    const id = this.ownOperationId || this.activeOperation?.id;
    if (!id || this.stopping) return;
    this.stopping = true;
    try {
      const answer = await fetch('/api/v1/operations/' + encodeURIComponent(id) + '/cancel', {method: 'POST'});
      if (!answer.ok) throw new Error((await answer.json()).error || t('voice.error.stopFailed'));
    } catch (error) { this.stopping = false; this.fail(error.message); }
  }

  templateFields(template) {
    if (!template) return nothing;
    return html`<p class="caption voice-note">${template.hint}</p>
      ${template.fields.map(field => html`<label class="field voice-template-field">${this.mode === 'design' ? field.id[0].toUpperCase() + field.id.slice(1) : field.id}
        ${field.choices?.length ? html`<select .value=${String(this.fieldValues[field.id] ?? '')} ?disabled=${this.locked}
          @change=${event => this.setTemplateValue(field.id, event.target.value)}>
          ${field.choices.map(choice => html`<option value=${choice.value} ?selected=${String(choice.value) === String(this.fieldValues[field.id] ?? '')}>${choice.label}</option>`)}</select>`
          : html`<input type=${field.kind === 'number' ? 'number' : 'text'} .value=${String(this.fieldValues[field.id] ?? '')}
            min=${field.minimum ?? nothing} max=${field.maximum ?? nothing} step=${field.step ?? nothing} ?disabled=${this.locked}
            @input=${event => this.setTemplateValue(field.id, event.target.value)}>`}</label>`)}`;
  }

  templateButton() {
    if (!this.templates.length) return nothing;
    return html`<div class="head-actions"><button type="button" class="pill" id="voice-templates-toggle" aria-expanded="false" aria-controls="voice-templates"
      ?disabled=${this.locked} @click=${() => toggleMenu(document.getElementById('voice-templates'))}>
      <svg class="icon" aria-hidden="true"><use href="#i-layout"/></svg>${this.templateName || t('voice.action.templates')}</button></div>`;
  }

  templateMenu() {
    if (!this.templates.length) return nothing;
    return html`<div class="menu" id="voice-templates" role="menu" hidden>
      <button type="button" role="menuitem" ?disabled=${this.locked} @click=${() => this.selectTemplate('')}>${this.mode === 'design' ? t('voice.template.writeOwn') : this.mode === 'edit' ? t('voice.template.customInstruction') : t('voice.template.writeOwnScript')}</button>
      ${this.templates.map(item => html`<button type="button" role="menuitem" ?disabled=${this.locked}
        @click=${() => this.selectTemplate(item.name)}>${item.name}</button>`)}
    </div>`;
  }

  controlsTemplate() {
    const editing = this.mode === 'edit';
    const template = this.templates.find(item => item.name === this.templateName);
    return html`
      <div class="voice-panel" @dragover=${event => event.preventDefault()}
        @drop=${event => { event.preventDefault(); this.addReference(event.dataTransfer.files[0]); }}
        @keydown=${event => { if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) { event.preventDefault(); event.stopPropagation(); this.generate(); } }}>
        <div class="modes voice-mode-picker" role="radiogroup" aria-label=${t('voice.mode.aria')}>
          ${this.capabilities.modes.map(mode => html`<input type="radio" id=${'voice-mode-' + mode.id} name="voice-mode" value=${mode.id}
            .checked=${this.mode === mode.id} ?disabled=${this.locked} @change=${() => this.selectMode(mode.id)}>
            <label for=${'voice-mode-' + mode.id}><svg class="icon" aria-hidden="true"><use href=${'#i-' + (mode.id === 'edit' ? 'brush' : mode.id === 'clone' ? 'music' : 'sparkle')}/></svg>${modeLabel(mode.id, mode.label)}</label>`)}
        </div>
        <section class="field prompt-field voice-script-group">
          <div class="field-head">
            <label for="voice-text">${editing ? t('voice.script.labelEdit') : t('voice.script.label')}</label>
            ${!this.hasParam('voice') ? this.templateButton() : nothing}
          </div>
          ${!this.hasParam('voice') ? this.templateMenu() : nothing}
          <textarea id="voice-text" aria-required="true" rows="4" maxlength="20000" .value=${editing ? (template ? this.instruction : this.editText) : this.script} ?disabled=${this.locked}
            placeholder=${editing ? t('voice.script.placeholderEdit') : this.currentMode?.text_hint || t('voice.script.placeholder')}
            @input=${event => {
              if (editing) {
                this.editText = event.target.value;
                this.templateName = '';
                this.fieldValues = {};
                this.persist(true);
              } else {
                if (!this.hasParam('voice')) { this.templateName = ''; this.fieldValues = {}; }
                this.setScript(event.target.value);
              }
            }}></textarea>
          ${!this.hasParam('voice') ? this.templateFields(template) : nothing}
          <p class="caption voice-note">${editing ? t('voice.script.noteEdit')
            : t('voice.script.note')}</p>
        </section>
        ${this.hasParam('voice') ? html`<section class="field prompt-field">
          <div class="field-head"><label for="voice-description">${t('voice.description.label')}</label>${this.templateButton()}</div>
          ${this.templateMenu()}
          <textarea id="voice-description" rows="3" aria-required="true" .value=${this.voice} ?disabled=${this.locked}
            placeholder=${t('voice.description.placeholder')}
            @input=${event => { this.voice = event.target.value; this.templateName = ''; this.fieldValues = {}; this.persist(true); }}></textarea>
          ${this.templateFields(template)}
          ${!template ? html`<p class="caption voice-note">${t('voice.description.hint')}</p>` : nothing}
        </section>` : this.needsReference ? html`<section class="field voice-reference-group">
          <div class="field-head"><label for="voice-reference">${t('voice.reference.label')}</label>
            <button type="button" class="text-btn" ?disabled=${this.locked || this.recordingPending || Boolean(this.reference) && !this.recording} @click=${() => this.toggleRecording()}>${this.recording ? t('voice.action.stopRecording') : this.recordingPending ? t('voice.status.openingMicrophone') : t('voice.action.record')}</button></div>
          <input id="voice-reference" type="file" accept="audio/*" hidden ?disabled=${this.locked || this.recording}
            @change=${event => { this.chooseReference(event.target.files[0]); event.target.value = ''; }}>
          ${this.reference ? html`<div class="voice-reference-card video-audios">
            <div class="video-audio">
              <div class="video-audio-picture"><span class="video-audio-badge"><svg class="icon" aria-hidden="true"><use href="#i-music"/></svg></span>
                <button type="button" class="video-audio-remove" aria-label=${t('voice.reference.clearAria')} ?disabled=${this.locked}
                  @click=${() => { this.referenceVersion += 1; this.referencePending = false; this.reference = null; this.editSegmentId = null; this.persist(true); }}>
                  <svg class="icon" aria-hidden="true"><use href="#i-x"/></svg></button>
              </div>
              <div><span class="video-audio-name">${this.reference.name}</span><span class="caption">${this.reference.trimmed ? t('voice.reference.trimmed', {duration: durationLabel(this.reference.duration)}) : durationLabel(this.reference.duration)}</span></div>
            </div>
          </div>` : html`<button type="button" class="refs" id="voice-reference-choose" ?disabled=${this.locked || this.recording}
            aria-label=${t('voice.reference.add')} @click=${() => document.getElementById('voice-reference').click()}>
            <span class="refs-empty"><svg class="icon" aria-hidden="true"><use href="#i-music"/></svg>
              <span><strong>${t('voice.reference.add')}</strong>${t('voice.reference.dropHint')}</span></span>
          </button>`}
          ${this.recording || this.recordingPending ? html`<p class="caption voice-note voice-recording-status" id="voice-recording-status"></p>` : nothing}
          ${this.referencePending ? html`<p class="caption voice-note" role="status">${t('voice.status.preparingReference')}</p>` : nothing}
          <p class="caption voice-note">${editing ? t('voice.reference.chooseEdit') : t('voice.reference.useHint', {seconds: this.capabilities.max_seconds || 120})}${this.referenceClipSeconds < Infinity ? ' ' + t('voice.reference.trimHint') : ''}</p>
          ${this.hasParam('ref_text') ? html`<label class="field" for="voice-reference-text">${t('voice.reference.transcriptLabel')}
            <textarea id="voice-reference-text" rows="3" aria-required="true" .value=${this.reference?.transcript || ''}
              ?disabled=${this.locked || !this.reference} placeholder=${t('voice.reference.transcriptPlaceholder')}
              @input=${event => { this.reference = {...this.reference, transcript: event.target.value}; this.persist(true); }}></textarea>
            <span class="caption">${t('voice.reference.transcriptHint')}</span></label>` : nothing}
        </section>` : nothing}
        <details class="voice-advanced">
          <summary>${t('voice.advanced.summary')} <span class="values num">${this.hasParam('seconds') && this.seconds > 0 ? t('voice.duration.seconds', {value: this.seconds}) : t('voice.advanced.automaticDuration')}, ${String(this.seed).trim() ? t('voice.advanced.seedValue', {seed: this.seed}) : t('voice.advanced.randomSeed')}</span></summary>
          <div class="advanced">
            ${this.hasParam('seconds') ? html`<div class="field">
              <div class="field-head"><label for="voice-seconds">${t('voice.advanced.duration')}</label><span class="caption">${t('voice.advanced.seconds')}</span></div>
              <input id="voice-seconds" type="number" min="0" max="120" step="0.5" .value=${String(this.seconds)} ?disabled=${this.locked}
                @input=${event => { this.seconds = event.target.value; this.persist(true); }}>
              <span class="caption">${t('voice.advanced.durationHint')}</span>
            </div>` : nothing}
            <div class="field">
              <div class="field-head"><label for="voice-seed">${t('voice.advanced.seed')}</label></div>
              <input id="voice-seed" type="number" min="0" step="1" inputmode="numeric" placeholder=${t('voice.advanced.seedPlaceholder')} .value=${String(this.seed)} ?disabled=${this.locked}
                @input=${event => { this.seed = event.target.value; this.persist(true); }}>
              <span class="caption">${t('voice.advanced.seedHint')}</span>
            </div>
            ${this.hasParam('convert') ? html`<div class="field">
              <label for="voice-convert">${t('voice.advanced.convertLabel')}</label><select id="voice-convert" aria-describedby="voice-convert-hint" .value=${this.convert} ?disabled=${this.locked}
                @change=${event => { this.convert = event.target.value; this.persist(true); }}>
                <option value="tw2s" ?selected=${this.convert === 'tw2s'}>${t('voice.advanced.convertTw2s')}</option><option value="off" ?selected=${this.convert === 'off'}>${t('voice.advanced.convertOff')}</option>
              </select>
              <span class="caption" id="voice-convert-hint">${t('voice.advanced.convertHint')}</span>
            </div>` : nothing}
            ${(this.currentMode?.params || []).filter(param => !['seconds', 'voice', 'convert', 'ref_text'].includes(param.id)).map(param => html`<label class="field" for=${'voice-param-' + param.id}>${this.paramLabel(param)}
              <input id=${'voice-param-' + param.id} type="number" min=${param.minimum ?? nothing} max=${param.maximum ?? nothing}
                step=${param.step || (param.integer ? 1 : 0.1)} .value=${String(this.engineOptions[param.id] ?? param.default)} ?disabled=${this.locked}
                @input=${event => { this.engineOptions = {...this.engineOptions, [param.id]: Number(event.target.value)}; this.persist(true); }}>
              <span class="caption">${this.paramHint(param)}</span></label>`)}
            ${this.capabilities.loading?.note ? html`<p class="caption voice-note">${this.capabilities.loading.note}</p>` : nothing}
          </div>
        </details>
        ${this.error ? html`<p class="voice-error" role="alert">${this.error}</p>` : nothing}
      </div>`;
  }

  footerTemplate() {
    const own = this.busy && this.ownOperationId;
    const stopping = own && (this.stopping || this.activeOperation?.status === 'stopping');
    const starting = this.busy && !this.ownOperationId;
    const state = stopping ? 'stopping' : starting ? 'starting' : own ? 'busy' : 'idle';
    const caption = this.mode === 'edit' ? t('voice.footer.editCaption') : t('voice.footer.caption');
    return html`<button id="voice-generate" class="run-button" type="button" data-state=${state} ?disabled=${starting || stopping || (!own && Boolean(this.reason))}
      @click=${() => own ? this.cancel() : this.generate()}>
      <run-button id="voice-run-labels" data-mode=${this.mode === 'edit' ? 'edit' : 'generate'} data-state=${state}></run-button>
      <span class="sub num" id="voice-go-sub">${starting ? t('voice.status.preparingRequest') : own ? t('voice.footer.stopping') : this.reason || caption}</span>
    </button>`;
  }

  updated(changes) {
    const sheet = this.querySelector('#voice-details-sheet');
    if (this.detailsOpen && sheet && !sheet.open) sheet.showModal();
    const take = this.previewItem?.take;
    if (take && !take.blob && !take.mediaLoading && !take.mediaError && !this.showingGeneration) {
      this.ensureTake(take).catch(error => { take.mediaError = error.message; this.fail(error.message); });
    }
    if (changes.has('selectedId') && this.selectedId) {
      rememberGalleryView('voice', {selected: this.selectedId}, this.options.keeping?.() !== false);
    }
    if (changes.has('busy')) this.options.onBusyChange?.();
    if (!this.locked && (changes.has('busy') || changes.has('activeOperation'))) this.trimReferenceIfNeeded();
    const controls = document.getElementById('voice-controls');
    const footer = document.getElementById('voice-footer');
    if (controls) render(this.controlsTemplate(), controls);
    // After the render: a take's first paint creates the status line.
    if (changes.has('recording') || changes.has('recordingPending')) this.paintRecordingStatus();
    if (footer) render(this.footerTemplate(), footer);
    const menu = document.getElementById('voice-templates');
    if (this.locked && menu && !menu.hidden) closeMenus();
  }

  renderWaveform(take) {
    return html`<svg class="voice-waveform" viewBox="0 0 320 48" role="img" aria-label=${t('voice.preview.waveformAria')}>
      ${(take?.peaks || Array(80).fill(0.06)).map((peak, index) => svg`<line x1=${index * 4 + 1} x2=${index * 4 + 1}
        y1=${24 - Math.max(1, peak * 22)} y2=${24 + Math.max(1, peak * 22)}></line>`)}</svg>`;
  }

  // One path for the browser panel and the strip head, so a file's name and its
  // type come from the same place.
  async downloadTakes(clips, ids) {
    for (const {segment, take} of clips.filter(({take}) => ids.includes(take.id))) {
      const blob = await this.ensureTake(take);
      downloadAudio(blob, mediaDownloadName({kind: 'audio', text: segment.text,
        at: take.createdAt, id: take.id, extension: mediaExtension(blob.type, 'wav')}));
      await new Promise(resolve => setTimeout(resolve, 300));
    }
  }

  async openDetails(event) {
    this.detailsTrigger = event?.currentTarget;
    this.detailsOpen = true;
    await this.updateComplete;
    this.querySelector('#voice-details-close')?.focus();
  }

  closeDetails() {
    const sheet = this.querySelector('#voice-details-sheet');
    if (sheet?.open) sheet.close();
    this.detailsOpen = false;
    this.detailsTrigger?.focus();
  }

  renderMetadata(item) {
    if (!this.detailsOpen || !item) return nothing;
    // Escape is handled here and the state is written by closeDetails. A late
    // `close` event would write the same field after the next open, which is how
    // the second open closed itself.
    return html`<dialog class="sheet" id="voice-details-sheet" aria-label=${t('voice.details.aria')}
      @cancel=${event => { event.preventDefault(); this.closeDetails(); }}>
      <div class="sheet-head"><h2>${t('voice.details.aria')}</h2>
        <button type="button" class="icon-btn close" id="voice-details-close" aria-label=${t('voice.details.closeAria')} title=${t('voice.details.closeTitle')} @click=${() => this.closeDetails()}>
          <svg class="icon" aria-hidden="true"><use href="#i-x"></use></svg></button></div>
      <div class="sheet-body"><dl><dt>${t('voice.details.script')}</dt><dd>${item.segment.text}</dd>
        ${item.take?.voice ? html`<dt>${t('voice.details.voiceDescription')}</dt><dd>${item.take.voice}</dd>` : nothing}
        ${item.take ? html`<dt>${t('voice.details.model')}</dt><dd>${item.take.model || 'AuK Flash'}</dd>
          <dt>${t('voice.details.mode')}</dt><dd>${modeLabel(item.take.mode || 'design')}</dd>
          <dt>${t('voice.advanced.duration')}</dt><dd>${durationLabel(item.take.duration)}</dd>
          <dt>${t('voice.advanced.seed')}</dt><dd>${item.take.seed ?? t('voice.advanced.seedPlaceholder')}</dd>` : nothing}</dl></div>
    </dialog>`;
  }

  renderTrackMenu(item) {
    const joined = this.selectedTakes.length > 1;
    const canReuse = !this.locked && !this.recording && !this.referenceBusy;
    const selectionReady = this.previewReady && this.previewSource === item.take.blob && !this.previewBusy;
    return html`<div class="menu-anchor">
      <button type="button" class="icon-btn" id="voice-track-toggle" aria-label=${t('voice.menu.moreActions')} title=${t('voice.menu.moreActions')}
        aria-controls="voice-track-menu" aria-expanded="false" @click=${() => toggleMenu(this.querySelector('#voice-track-menu'))}>
        <svg class="icon" aria-hidden="true"><use href="#i-more"></use></svg></button>
      <div id="voice-track-menu" class="voice-track-menu menu up" role="menu" aria-label=${t('voice.menu.aria')} hidden>
        <button type="button" role="menuitem" id="voice-selected-reuse" ?disabled=${!canReuse}
          @click=${() => this.reuseSettings(item)}>${t('voice.action.reuse')}</button>
        <button type="button" role="menuitem" id="voice-selected-video" ?disabled=${!selectionReady || this.locked}
          @click=${() => { closeMenus(); this.querySelector('audio-preview')?.action('video'); }}>${t('voice.action.sendVideo')}</button>
        <button type="button" role="menuitem" id="voice-selected-clone" ?disabled=${!selectionReady || !canReuse}
          @click=${() => { closeMenus(); this.querySelector('audio-preview')?.action('clone'); }}>${t('voice.action.sendClone')}</button>
        ${joined ? html`<button type="button" role="menuitem" @click=${() => { closeMenus(); this.playTrack(); }}>${this.playing ? t('voice.action.pauseJoined') : t('voice.action.playJoined')}</button>
          <button type="button" role="menuitem" @click=${() => { closeMenus(); this.exportTrack(); }}>${t('voice.action.downloadJoined')}</button>` : nothing}
      </div></div>`;
  }

  renderDetails(item) {
    if (!item) return nothing;
    const {segment, take} = item;
    const selectionReady = this.previewReady && this.previewSource === take?.blob && !this.previewBusy;
    return html`<section class="stage-bar voice-output-details" id="voice-output-details" aria-label=${t('voice.preview.detailsAria')}>
      <div class="about">
        <p class="prompt-line voice-output-script" title=${segment.text} role="button" tabindex="0"
          aria-controls="voice-details-sheet" aria-expanded=${String(this.detailsOpen)} @click=${this.openDetails}
          @keydown=${event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); event.stopPropagation(); this.openDetails(event); } }}>${segment.text}</p>
        ${take?.voice ? html`<p class="prompt-line voice-output-description" title=${take.voice} role="button" tabindex="0"
          aria-controls="voice-details-sheet" aria-expanded=${String(this.detailsOpen)} @click=${this.openDetails}
          @keydown=${event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); event.stopPropagation(); this.openDetails(event); } }}><span class="caption">${t('voice.preview.voiceDescriptionLabel')}</span>${take.voice}</p>` : nothing}
        <div class="facts num" aria-label=${t('voice.preview.metadataAria')}>
          <span>${take ? t('voice.preview.audio', {number: this.clipNumber(take)}) : t('voice.details.script')}</span>
          ${take ? html`<span>${durationLabel(take.duration)}</span><span>${take.model || 'AuK Flash'}</span>
            <span>${modeLabel(take.mode || 'design')}</span><span>${Number.isInteger(take.seed) ? t('voice.preview.seed', {seed: take.seed}) : t('voice.preview.randomSeed')}</span>
            ${Number.isFinite(take.elapsed) ? html`<span>${t('voice.preview.took', {duration: durationLabel(take.elapsed)})}</span>` : nothing}` : html`<span>${t('voice.preview.notGenerated')}</span>`}
        </div>
      </div>
      <div class="actions voice-output-actions">
        ${take && this.capabilities.modes.some(mode => mode.id === 'edit') ? html`          <button type="button" class="btn quiet" id="voice-selected-edit" ?disabled=${!selectionReady || this.locked}
            @click=${() => this.querySelector('audio-preview')?.action('edit')}>
            <svg class="icon" aria-hidden="true"><use href="#i-brush"></use></svg>${t('voice.action.edit')}</button>` : nothing}
        ${take ? this.renderTrackMenu(item) : nothing}
        ${take ? html`<span class="rule" aria-hidden="true"></span>
          <button type="button" class="icon-btn" id="voice-selected-download" aria-label=${t('voice.preview.downloadAria')} title=${t('voice.preview.downloadTitle')}
            ?disabled=${!selectionReady} @click=${() => this.querySelector('audio-preview')?.action('download')}>
            <svg class="icon" aria-hidden="true"><use href="#i-download"></use></svg></button>
          <button type="button" class="icon-btn danger" id="voice-selected-remove" aria-label=${t('voice.preview.removeAria')} title=${t('voice.preview.removeTitle')}
            @click=${() => this.removeTake(take.id)}><svg class="icon" aria-hidden="true"><use href="#i-trash"></use></svg></button>` : nothing}
      </div>
    </section>`;
  }

  clipNumber(take) {
    const clips = this.segments.flatMap(segment => segment.takes).sort((first, second) => first.createdAt - second.createdAt);
    return clips.findIndex(clip => clip.id === take.id) + 1;
  }

  renderGallery(item) {
    const rendering = this.voiceRunning;
    const clips = this.segments.flatMap(segment => segment.takes.map(take => ({segment, take})));
    clips.sort((first, second) => (second.take?.createdAt ?? Infinity) - (first.take?.createdAt ?? Infinity));
    // The head names what the shelf holds and what happens to it, as the Image strip does.
    const shelfNote = this.options.keeping?.() !== false
      ? plural(this.takesCount, t('voice.gallery.shelfKept'))
      : plural(this.takesCount, t('voice.gallery.shelfTab'));
    return html`<section class="strip-wrap voice-gallery" id="voice-gallery" aria-label=${t('voice.gallery.aria')} ?hidden=${!clips.length && !rendering}>
      <div class="strip-head"><span>${shelfNote}</span>
        <gallery-browser workspace="voice" .items=${clips.map(({segment, take}) => ({id: take.id,
          number: this.clipNumber(take), text: segment.text, description: take.voice, model: take.model,
          mode: take.mode, seed: take.seed, at: take.createdAt, duration: take.duration, peaks: take.peaks,
          batch: galleryBatch(take.id), downloadable: Boolean(take.blob || take.stored)}))}
          .selectedId=${item?.take?.id} .keeping=${this.options.keeping?.() !== false}
          .pending=${rendering} .pendingSelected=${this.showingGeneration}
          .showPending=${() => { this.pausePlayback(); this.showGeneration = true; this.detailsOpen = false; }}
          .choose=${id => { const found = clips.find(({take}) => take.id === id); if (found) this.selectTake(found.segment.id, id); }}
          .removeItem=${id => { this.removeTake(id); return !this.segments.some(segment => segment.takes.some(take => take.id === id)); }}
          .download=${ids => this.downloadTakes(clips, ids)} .playback=${() => this.togglePreviewPlayback()}></gallery-browser>
        <span class="strip-actions"><button type="button" class="text-btn" id="voice-download-all"
          ?disabled=${!this.takesCount}
          @click=${() => this.downloadTakes(clips, clips.map(({take}) => take.id))}>${t('voice.action.downloadAll')}</button>
          <button type="button" class="text-btn" ?disabled=${!this.takesCount} @click=${() => {
            if (confirm(t('voice.gallery.confirmClear'))) this.clearCompleted();
          }}>${t('voice.action.clearAll')}</button></span></div>
      <div class="strip voice-clips" role="group" aria-label=${t('voice.gallery.generatedAria')} @keydown=${event => this.galleryKey(event)}>
        ${rendering ? html`<button type="button" class=${'frame pending voice-render-pending' + (this.showingGeneration ? ' selected' : '')}
          aria-label=${t('voice.gallery.showGenerationAria')} aria-pressed=${String(this.showingGeneration)}
          @click=${() => { this.pausePlayback(); this.showGeneration = true; this.detailsOpen = false; }}>
          <span class="still voice-clip-thumb"><span class="video-pending-indicator" aria-hidden="true"></span><span>${t('voice.gallery.generating')}</span></span>
          <span class="no">${String(this.takesCount + 1).padStart(2, '0')}</span>${this.showingGeneration ? pencilLoop() : nothing}
        </button>` : nothing}
        <gallery-window .items=${clips} .selected=${item?.take?.id} .renderItem=${({segment, take}) => html`
          <button type="button" class=${'frame voice-clip' + (item?.take?.id === take.id && !this.showingGeneration ? ' selected' : '')}
            data-take-id=${take.id} data-segment-id=${segment.id} aria-pressed=${String(item?.take?.id === take.id && !this.showingGeneration)}
            aria-label=${t('voice.preview.selectAria', {number: this.clipNumber(take)})} title=${segment.text}
            @click=${() => this.selectTake(segment.id, take.id)}>
            <span class="still voice-clip-thumb">${this.renderWaveform(take)}<span class="voice-clip-duration num">${durationLabel(take.duration)}</span></span>
            <span class="no">${String(this.clipNumber(take)).padStart(2, '0')}</span>${item?.take?.id === take.id && !this.showingGeneration ? pencilLoop(true) : nothing}</button>`}></gallery-window>
      </div>
    </section>`;
  }

  renderGeneration() {
    const operation = this.activeOperation?.kind === 'voice' ? this.activeOperation : null;
    const progress = operation?.progress || {};
    const percent = progress.total > 0 ? Math.max(0, Math.min(99, Math.round((progress.step || 0) / progress.total * 100))) : null;
    const editing = (operation?.mode || this.mode) === 'edit';
    let label = editing ? t('voice.generation.editing') : t('voice.generation.generating');
    if (!progress.step) label = t('voice.generation.preparing');
    if (progress.total > 0 && progress.step >= progress.total) label = t('voice.generation.finishing');
    let phase = !progress.step ? 'preparing' : progress.total > 0 && progress.step >= progress.total ? 'finishing' : 'generating';
    if (this.stopping || operation?.status === 'stopping') { label = t('voice.generation.stopping'); phase = 'stopping'; }
    const bars = Array.from({length: 64}, (_, index) => {
      const height = 12 + Math.abs(Math.sin(index * 0.73) * Math.cos(index * 0.19)) * 68;
      return svg`<line x1=${index * 10 + 5} x2=${index * 10 + 5} y1=${50 - height / 2} y2=${50 + height / 2}
        style=${'--bar-delay: ' + (-index * 0.07).toFixed(2) + 's'}></line>`;
    });
    return html`<section class="voice-generation audio-preview" id="voice-generation" data-phase=${phase}
      aria-label=${t('voice.generation.aria')}>
      <div class="audio-preview-heading voice-generation-status"><strong>${label}</strong><span>${operation?.model || this.capabilities.name}</span></div>
      <div class="audio-preview-wave voice-generation-wave" role="progressbar" aria-label=${t('voice.generation.progressAria')}
        aria-valuemin="0" aria-valuemax="100" aria-valuenow=${percent === null ? nothing : percent}
        aria-valuetext=${percent === null ? label : t('voice.generation.progress', {label, percent})}>
        <svg viewBox="0 0 640 100" preserveAspectRatio="none" aria-hidden="true">
          <defs><clipPath id="voice-generation-clip"><rect width=${percent === null ? 0 : percent * 6.4} height="100"></rect></clipPath></defs>
          <g class="voice-generation-bars voice-generation-outline">${bars}</g>
          <g class="voice-generation-bars voice-generation-fill" clip-path="url(#voice-generation-clip)">${bars}</g>
        </svg>
      </div>
      <p class="voice-generation-note">${t('voice.generation.note', {state: phase === 'finishing' ? t('voice.generation.saving') : phase === 'stopping' ? t('voice.generation.waitingStop') : t('voice.generation.playable')})}</p>
    </section>`;
  }

  render() {
    const item = this.previewItem;
    return html`<div class="voice-studio-shell" @dragover=${event => event.preventDefault()}
      @drop=${event => {
        event.preventDefault();
        // A stray drop used to switch to Clone and clear the template and its
        // fields. The mode that takes a recording is the mode that accepts it.
        if (!this.needsReference) {
          this.options.notify?.('info', t('voice.toast.dropped'));
          return;
        }
        this.addReference(event.dataTransfer.files[0]);
      }}>
      <div class="voice-preview-area stage">
        <div id="voice-preview-pane">
          ${this.showingGeneration ? this.renderGeneration() : item?.take ? html`<audio-preview id="voice-audio-preview" class=${this.previewReady ? 'voice-result-ready' : ''} .blob=${item.take.blob}
            .downloadText=${item.segment.text} .downloadAt=${item.take.createdAt} .downloadId=${item.take.id} .speed=${this.previewSpeed}
            .label=${t('voice.preview.audio', {number: this.clipNumber(item.take)})}
            .locked=${this.locked} @audio-preview-play=${() => this.pausePlayback()}
            @audio-preview-action=${event => this.useSelection(event)}
            @audio-preview-state=${event => {
              this.previewSource = event.detail.blob;
              this.previewSpeed = event.detail.speed;
              this.previewReady = event.detail.ready;
              this.previewBusy = event.detail.busy;
            }}></audio-preview>` : html`
            <div class="voice-empty video-empty empty"><div class="video-empty-mark">${t('voice.empty.mark')}</div><strong>${t('voice.empty.title')}</strong>
              <span>${item ? t('voice.empty.segment') : this.mode === 'edit' ? t('voice.empty.edit') : this.hasParam('voice') ? t('voice.empty.designVoice') : t('voice.empty.design')}</span>
              ${!item ? html`<button type="button" class="btn" @click=${() => document.getElementById('voice-text').focus()}>
                <svg class="icon" aria-hidden="true"><use href="#i-text"/></svg>${this.mode === 'edit' ? t('voice.action.describeChange') : t('voice.action.writeScript')}</button>` : nothing}
            </div>`}
        </div>
        ${this.showingGeneration ? nothing : this.renderDetails(item)}
        ${this.showingGeneration ? nothing : this.renderMetadata(item)}
      </div>
      ${this.renderGallery(item)}
    </div>`;
  }

}

customElements.define('voice-studio', VoiceStudio);
