// The LoRA picker: one chip for each LoRA the model offers, and a strength slider
// under each chip that is picked.
//
// A tree drawn from the model's offer and the picks, so Lit, with the element
// itself as the render root. Two boards share this component, the image form and
// the video form, and each element names its board with `data-form`, the way the
// Look rows do. Each board keeps its own picks, so the two forms never see each
// other's.
//
// The picks are this module's. The image form posts them as one JSON field, so
// the image element also draws a hidden `loras` input, and htmx sends it with the
// rest of the form. The video form builds its request in script and reads
// `picks()` through the board's handle.
//
// The page's own script cannot import this module, so the module announces itself
// on `lora-picks-ready`. The page hands over, per board, what the model offers,
// how many it takes, and why the picks are held, if they are.
//
// What a board shows and posts is its picks filtered to the offer in force, so a
// mode or a model switch never posts a LoRA that the new one lacks. The filter
// never writes back: watching another client's run switches the mode on screen,
// and the picks must still be there when it ends.

import { LitElement, html, nothing } from 'https://cdn.jsdelivr.net/npm/lit@3.2.1/+esm';

const boards = new Map();
const picksOf = new Map([['image', []], ['video', []]]);

function formOf(element) {
  return element.dataset.form === 'video' ? 'video' : 'image';
}

function elementsOf(form) {
  return Array.from(document.querySelectorAll('lora-picks[data-form="' + form + '"]'));
}

function decimals(step) {
  const text = String(step);
  return text.indexOf('.') < 0 ? 0 : text.length - text.indexOf('.') - 1;
}

function strengthText(lora, strength) {
  return Number(strength).toFixed(Math.max(1, decimals(lora.strength_step)));
}

// The picks that the offer in force takes, each strength inside its LoRA's own
// range, and no more of them than the model takes. The stored picks stay as they are.
function view(form) {
  const board = boards.get(form);
  if (!board) return [];
  const offer = board.offer();
  const byId = new Map(offer.map((lora) => [lora.id, lora]));
  return picksOf.get(form)
    .filter((pick) => byId.has(pick.id))
    .slice(0, board.max())
    .map(function (pick) {
      const lora = byId.get(pick.id);
      const strength = Math.min(lora.max_strength, Math.max(lora.min_strength, Number(pick.strength)));
      return { id: pick.id, strength: Number.isFinite(strength) ? strength : lora.strength };
    });
}

function redraw(form) {
  elementsOf(form).forEach((element) => element.requestUpdate());
}

function changed(form) {
  redraw(form);
  const board = boards.get(form);
  if (board && board.changed) board.changed(view(form));
}

// The sentence a closed section carries: each pick and its strength.
function summary(form) {
  const board = boards.get(form);
  if (!board) return '';
  const byId = new Map(board.offer().map((lora) => [lora.id, lora]));
  return view(form).map(function (pick) {
    const lora = byId.get(pick.id);
    return lora ? lora.label + ' ' + strengthText(lora, pick.strength) : '';
  }).filter(Boolean).join(', ');
}

class LoraPicks extends LitElement {
  createRenderRoot() { return this; }

  toggle(lora) {
    const form = formOf(this);
    const picks = picksOf.get(form);
    if (picks.some((pick) => pick.id === lora.id)) picksOf.set(form, picks.filter((pick) => pick.id !== lora.id));
    else picksOf.set(form, picks.concat([{ id: lora.id, strength: lora.strength }]));
    changed(form);
  }

  slide(lora, event) {
    const form = formOf(this);
    const strength = Number(event.target.value);
    picksOf.set(form, picksOf.get(form).map((pick) => (pick.id === lora.id ? { id: pick.id, strength } : pick)));
    changed(form);
  }

  render() {
    const form = formOf(this);
    const board = boards.get(form);
    if (!board) return nothing;
    const offer = board.offer();
    const max = board.max();
    const held = board.held ? board.held() : '';
    const picks = view(form);
    const field = this.dataset.name
      ? html`<input type="hidden" name=${this.dataset.name} .value=${picks.length ? JSON.stringify(picks) : ''}>`
      : nothing;
    const full = picks.length >= max;
    const rows = offer.map((lora) => {
      const pick = picks.find((one) => one.id === lora.id);
      const sliderId = 'lora-' + form + '-' + lora.id;
      const range = lora.recommended
        ? 'Suggested ' + strengthText(lora, lora.recommended[0]) + ' to ' + strengthText(lora, lora.recommended[1]) + '.'
        : '';
      const note = [lora.hint, range].filter(Boolean).join(' ');
      return html`<div class="lora-row" data-lora=${lora.id}>
        <button type="button" class="chip lora-toggle" aria-pressed=${pick ? 'true' : 'false'}
          ?disabled=${Boolean(held) || (!pick && full)}
          title=${!pick && full && !held ? 'This model takes at most ' + max + (max === 1 ? ' LoRA' : ' LoRAs') : ''}
          @click=${() => this.toggle(lora)}>${lora.label}</button>
        ${pick ? html`<div class="field lora-strength">
          <div class="field-head">
            <label for=${sliderId}>Strength</label>
            <span class="caption num">${strengthText(lora, pick.strength)}</span>
          </div>
          <input id=${sliderId} type="range" min=${lora.min_strength} max=${lora.max_strength}
            step=${lora.strength_step} .value=${String(pick.strength)} ?disabled=${Boolean(held)}
            @input=${(event) => this.slide(lora, event)}>
        </div>` : nothing}
        ${note ? html`<span class="caption">${note}</span>` : nothing}
      </div>`;
    });
    const limit = max > 1 && offer.length > max ? html`<p class="lora-note">Pick up to ${max}.</p>` : nothing;
    const heldNote = held ? html`<p class="lora-note lora-held">${held}</p>` : nothing;
    return html`${field}${heldNote}<div class="lora-rows">${rows}</div>${limit}`;
  }

  updated() {
    const values = this.closest('details')?.querySelector('summary .values');
    if (values) values.textContent = summary(formOf(this));
  }
}

customElements.define('lora-picks', LoraPicks);

document.dispatchEvent(new CustomEvent('lora-picks-ready', {
  detail: {
    // board: { offer() -> Lora[], max() -> int, held() -> '' or the reason, changed(picks) }
    configure: function (form, board) {
      boards.set(form, board);
      redraw(form);
    },
    picks: view,
    setPicks: function (form, picks) {
      picksOf.set(form, Array.isArray(picks) ? picks.map((pick) => ({ id: String(pick.id), strength: Number(pick.strength) })) : []);
      redraw(form);
    },
    summary: summary,
    refresh: redraw,
  },
}));
