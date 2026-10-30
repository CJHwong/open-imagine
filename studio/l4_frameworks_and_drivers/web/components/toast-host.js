// The toasts: one line each about what just happened, over the stage.
//
// A toast is a tree drawn from a list of messages, and that list is this
// element's own state. No consumer outside it reads the list, so it is not a
// store field: the store carries the redraw signal between consumers, and a
// field with no other reader is a copy that can disagree with the thing it
// copies.
//
// The host stays `#toasts` with `role="status"` and `aria-live="polite"`, and
// each message carries `role="status"` itself, or `role="alert"` when it
// reports a failure. Both are what a role query reaches, so neither needs the
// id to be found.
//
// Errors stay until they are dismissed, because they say what to fix. Anything
// else clears itself.
//
// The page's own script is still a classic script, so it cannot import this
// module and the modules that toast while they work read the page's own
// `showToast` off the global scope. The page keeps that one name and forwards
// it here, on the door below. This door closes when the inline script is gone.

import { LitElement, html } from 'https://cdn.jsdelivr.net/npm/lit@3.2.1/+esm';
import { repeat } from 'https://cdn.jsdelivr.net/npm/lit@3.2.1/directives/repeat.js/+esm';
import { t } from '../lib/i18n.js';

// How long a message that is not a failure stays. A failure waits for a person.
const LIFETIME = 4000;

// Where the stack starts. It clears the shared operation bar when that bar is
// up, because the bar owns the strip under the top bar while a run is visible.
// Horizontally it stays over the work column, as it was before the popover: a
// stack centred on the window leaned over the sidebar's own menus.
function toastPlacement() {
  const bar = document.getElementById('shared-operation');
  const bottom = bar && !bar.hidden && bar.getClientRects().length ? bar.getBoundingClientRect().bottom : 0;
  const work = document.querySelector('.work');
  const middle = work ? work.getBoundingClientRect() : null;
  return {
    top: Math.max(68, Math.round(bottom) + 12) + 'px',
    left: middle ? Math.round(middle.left + middle.width / 2) + 'px' : '50%',
  };
}

// The page draws its own controls from the same sprite, and the two must agree
// on the three lines, so this draws a glyph exactly as `popup-menu.js` does.
function glyph(name) {
  return html`<svg class="icon" aria-hidden="true"><use href="#i-${name}"></use></svg>`;
}

class ToastHost extends LitElement {
  createRenderRoot() { return this; }

  // The list is this element's own, and no consumer outside it reads it, so it
  // is a plain field and the redraw is asked for by hand. A reactive property
  // would be a name nothing else reads.
  messages = [];
  counter = 1;

  notify(kind, text) {
    const id = this.counter++;
    this.messages = this.messages.concat([{ id: id, kind: kind, text: text }]);
    this.requestUpdate();
    if (kind !== 'error') setTimeout(() => this.dismiss(id), LIFETIME);
    this.updateComplete.then(() => this.present());
  }

  dismiss(id) {
    const left = this.messages.filter((message) => message.id !== id);
    if (left.length === this.messages.length) return;
    this.messages = left;
    this.requestUpdate();
    this.updateComplete.then(() => this.present());
  }

  clear() {
    if (!this.messages.length) return;
    this.messages = [];
    this.requestUpdate();
    this.updateComplete.then(() => this.present());
  }

  // The host is a popover, so the top layer paints it over the sticky shared bar
  // and over any modal sheet. A closed popover is display:none, so the host shows
  // itself only while it has a message, and its top clears the shared bar rather
  // than the fixed 68 pixels that the bar used to cover.
  present() {
    if (!this.messages.length) {
      if (this.hidePopover && this.matches(':popover-open')) this.hidePopover();
      return;
    }
    const place = toastPlacement();
    this.style.setProperty('--toast-top', place.top);
    this.style.setProperty('--toast-left', place.left);
    if (this.showPopover && !this.matches(':popover-open')) this.showPopover();
  }

  message(one) {
    const failure = one.kind === 'error';
    return html`<div class=${'toast ' + one.kind} role=${failure ? 'alert' : 'status'}>${glyph(failure ? 'alert' : 'info')}<p>${one.text}</p><button type="button" class="icon-btn" title=${t('toast.dismiss')} aria-label=${t('toast.dismiss')} @click=${() => this.dismiss(one.id)}>${glyph('x')}</button></div>`;
  }

  render() {
    return html`${repeat(this.messages, (one) => one.id, (one) => this.message(one))}`;
  }
}

customElements.define('toast-host', ToastHost);

// The handle the page forwards to. It reads the element once, at evaluation:
// the markup is parsed by then, and this module is deferred.
const host = document.querySelector('toast-host');

const handle = {
  notify: function (kind, text) {
    if (host) host.notify(kind, text);
  },
  clear: function () {
    if (host) host.clear();
  },
};

document.dispatchEvent(new CustomEvent('toast-ready', { detail: handle }));
