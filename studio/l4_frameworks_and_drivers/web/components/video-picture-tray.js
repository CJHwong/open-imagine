import {t, plural} from '../lib/i18n.js';

// The References tray: pictures of who or what the clip shows, on no frame of their own, and
// on a model whose track is a reference, the track too. The model numbers each kind in the
// order the request lists it, so the tray's order is the prompt's numbering, and the label
// on each row is the text the prompt uses to name it. A model that takes keyframes beside the
// pictures numbers its keyframes first, so `first` is the number of the first picture.

export function pictureLabel(position) {
  return `<Picture ${position + 1}>`;
}

export const AUDIO_LABEL = '<Audio 1>';

function removeButton(action, label, dataset = {}) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'video-audio-remove labeled-action';
  button.dataset.action = action;
  Object.assign(button.dataset, dataset);
  button.setAttribute('aria-label', label);
  button.innerHTML = '<svg class="icon" aria-hidden="true"><use href="#i-x"/></svg><span class="control-label"></span>';
  button.querySelector('.control-label').textContent = t('ui.action.remove');
  return button;
}

function labelButton(label, name) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'video-picture-label';
  button.dataset.action = 'insert-picture-label';
  button.dataset.label = label;
  button.textContent = label;
  button.setAttribute('aria-label', t('video.picture.insert', {label, name}));
  return button;
}

function row(thumb, label, name, remove) {
  const item = document.createElement('div');
  item.className = 'video-audio video-picture';
  const text = document.createElement('div');
  text.className = 'video-picture-text';
  const title = document.createElement('span');
  title.className = 'video-audio-name';
  title.textContent = name;
  text.append(label, title);
  item.append(thumb, text, remove);
  return item;
}

function pictureRow(picture, position, first) {
  const thumb = document.createElement('div');
  thumb.className = 'video-source-thumb';
  const image = document.createElement('img');
  image.src = picture.src;
  image.alt = '';
  thumb.append(image);
  const label = pictureLabel(first - 1 + position);
  return row(thumb, labelButton(label, picture.name), picture.name,
    removeButton('remove-picture', t('video.picture.remove', {name: picture.name}), {pictureId: picture.id}));
}

function audioRow(audio) {
  const thumb = document.createElement('span');
  thumb.className = 'video-audio-badge';
  thumb.innerHTML = '<svg class="icon" aria-hidden="true"><use href="#i-music"/></svg>';
  return row(thumb, labelButton(AUDIO_LABEL, audio.name), audio.name,
    removeButton('remove-audio', t('video.audio.remove', {name: audio.name})));
}

// `audio` is the track when it belongs in this tray, and null when it is a soundtrack.
export function renderPictureTray(tray, {pictures, audio, busy, first = 1}) {
  const list = tray.querySelector('#video-pictures');
  const count = tray.querySelector('#video-picture-count');
  list.replaceChildren();
  pictures.forEach((picture, position) => list.append(pictureRow(picture, position, first)));
  if (busy) list.append(busy);
  if (audio) list.append(audioRow(audio));
  count.textContent = plural(pictures.length, t('video.picture.count'));
  tray.hidden = !pictures.length && !audio && !busy;
}

// Put a label into the prompt at the caret, with a space on each side where the text needs one,
// and tell the form the words changed.
export function insertLabel(prompt, label) {
  const start = prompt.selectionStart ?? prompt.value.length;
  const end = prompt.selectionEnd ?? start;
  const before = prompt.value.slice(0, start);
  const after = prompt.value.slice(end);
  const text = (before && !/\s$/.test(before) ? ' ' : '') + label + (after && !/^\s/.test(after) ? ' ' : '');
  prompt.value = before + text + after;
  const caret = before.length + text.length;
  prompt.setSelectionRange(caret, caret);
  prompt.dispatchEvent(new Event('input', {bubbles: true}));
  prompt.focus();
}
