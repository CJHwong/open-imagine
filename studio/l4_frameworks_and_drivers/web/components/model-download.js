// The Download that takes the run button's place while the picked model is not on disk.
//
// A run never downloads or packs a model: the server refuses one for a model whose files
// are not on disk. So when the model a workspace has picked is not ready, the page sets
// `data-model-missing` on the body, the stylesheet hides that workspace's run footer, and
// this footer offers what the model needs instead. A prepare is an operation like a run,
// so it waits in the same queue and stops through the same cancel route.
//
// The server knows no total size before the download, so the second line shows what is
// on disk already. It grows while the prepare downloads, which is the progress there is.

import { LitElement, html } from '/page/vendor/lit.js';
import { t, number } from '../lib/i18n.js';

const POLL_MS = 1500;
const WORKSPACES = ['image', 'video', 'voice', 'music'];
const ENDED = ['succeeded', 'failed', 'cancelled'];

async function readJson(path) {
  const answer = await fetch(path, {cache: 'no-store'});
  if (!answer.ok) throw new Error(path + ' answered ' + answer.status);
  return answer.json();
}

// The two readiness labels for a pack that is on disk but out of date (API.md). When they are
// all that is missing, the files are there and a prepare rebuilds them; nothing downloads.
function outOfDate(model) {
  const missing = model.missing || [];
  return missing.length > 0 && missing.every(label => label.startsWith('Pack out of date') || label === 'Pack for this build');
}

function onDisk(bytes) {
  if (!bytes) return t('page.download.none');
  return t('page.download.on_disk', {size: number(bytes / 1e9, {maximumFractionDigits: 1})});
}

class ModelDownload extends LitElement {
  static properties = {
    model: {state: true},
    stage: {state: true},
    error: {state: true},
  };

  createRenderRoot() { return this; }

  connectedCallback() {
    super.connectedCallback();
    this.models = [];
    this.active = {};
    this.following = '';
    // A run can end because its engine found the files out of date, such as a pack from
    // another torch. The server then reads the model as missing, so the list is read
    // again whenever a run ends.
    this.wasBusy = document.body.classList.contains('busy');
    this.watcher = new MutationObserver(() => {
      const busy = document.body.classList.contains('busy');
      if (this.wasBusy && !busy) this.refresh();
      else this.pick();
      this.wasBusy = busy;
    });
    this.watcher.observe(document.body, {attributes: true, attributeFilter: ['data-media', 'class']});
    this.refresh();
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    this.watcher.disconnect();
    clearTimeout(this.timer);
  }

  async refresh() {
    try {
      const [studio, models] = await Promise.all([readJson('/api/v1/studio'), readJson('/api/v1/models')]);
      this.active = Object.fromEntries(WORKSPACES.map(workspace => [workspace, studio[workspace]?.active]));
      this.models = models.models;
    } catch (error) {
      // Without the list, gating the run would lock the page; the server still refuses a
      // run on a model that is not ready, and says why.
      console.warn('The model list is unavailable:', error);
      this.models = [];
    }
    this.pick();
  }

  pick() {
    const workspace = document.body.dataset.media || 'image';
    const model = this.models.find(one => one.workspace === workspace && one.id === this.active[workspace]);
    this.model = model && model.state !== 'ready' ? model : null;
    document.body.toggleAttribute('data-model-missing', Boolean(this.model));
    this.hidden = !this.model;
    if (this.model?.operation && this.following !== this.model.operation) this.follow(this.model.operation);
  }

  async download() {
    this.error = '';
    this.stage = 'queued';
    const request = {kind: 'prepare', workspace: this.model.workspace, backend: this.model.id};
    try {
      const answer = await fetch('/api/v1/operations', {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(request),
      });
      const body = await answer.json();
      if (!answer.ok) throw new Error(body.error || String(answer.status));
      this.follow(body.id);
    } catch (error) {
      this.stage = '';
      this.error = error.message;
    }
  }

  follow(operationId) {
    clearTimeout(this.timer);
    this.following = operationId;
    this.poll();
  }

  async poll() {
    const operationId = this.following;
    let operation;
    try {
      operation = await readJson('/api/v1/operations/' + encodeURIComponent(operationId));
      const models = await readJson('/api/v1/models');
      this.models = models.models;
    } catch (error) {
      this.error = error.message;
      this.timer = setTimeout(() => this.poll(), POLL_MS);
      return;
    }
    if (operationId !== this.following) return;
    if (ENDED.includes(operation.status)) {
      this.following = '';
      this.stage = '';
      if (operation.status === 'failed') this.error = operation.error || t('page.download.failed');
      await this.refresh();
      return;
    }
    this.stage = operation.status === 'queued' ? 'queued' : operation.progress.stage;
    this.pick();
    this.timer = setTimeout(() => this.poll(), POLL_MS);
  }

  async cancel() {
    if (!this.following) return;
    this.stage = 'stopping';
    try {
      const answer = await fetch('/api/v1/operations/' + encodeURIComponent(this.following) + '/cancel', {method: 'POST'});
      if (!answer.ok && answer.status !== 409) throw new Error(String(answer.status));
    } catch (error) {
      this.error = error.message;
    }
  }

  stageLabel() {
    if (this.stage === 'queued') return t('page.download.queued');
    if (this.stage === 'rewriter') return t('page.download.rewriter');
    if (this.stage === 'stopping') return t('page.run.stopping');
    return t('page.download.engine');
  }

  render() {
    if (!this.model) return html``;
    const preparing = Boolean(this.stage);
    const stale = outOfDate(this.model);
    return html`<div class="footer download-footer">
      <p class="download-note" role="status">${this.error
        ? html`<span class="download-error">${this.error}</span>`
        : t(stale ? 'page.download.stale_note' : 'page.download.note', {model: this.model.name})}</p>
      <div class="download-actions">
        <button type="button" class="run-button" id="model-download-button" ?disabled=${preparing}
          @click=${() => this.download()}>
          <span class="main">${preparing ? this.stageLabel() : t(stale ? 'page.download.prepare_again' : 'page.download.button')}</span>
          <span class="sub num">${onDisk(this.model.bytes)}</span>
        </button>
        ${preparing ? html`<button type="button" class="download-cancel" ?disabled=${this.stage === 'stopping'}
          @click=${() => this.cancel()}>${t('page.download.cancel')}</button>` : ''}
      </div>
    </div>`;
  }
}

customElements.define('model-download', ModelDownload);
