import {t} from './i18n.js';
import {openSheet, dismissSheet} from './sheet.js';

const RECOMMENDED_EDGE = 2048;
const MAX_BYTES = 64 * 1024 * 1024;
const MAX_PIXELS = 64_000_000;

export function isImageFile(file) {
  return file.type.startsWith('image/') || /\.(png|jpe?g|gif|webp|bmp|tiff?|heic|heif)$/i.test(file.name);
}

function isHeif(file) {
  return /^image\/hei[cf](?:-sequence)?$/i.test(file.type) || /\.hei[cf]$/i.test(file.name);
}

async function normalizeHeif(file) {
  const response = await fetch('/image/normalize', {
    method: 'POST', headers: {'Content-Type': 'application/octet-stream'}, body: file,
  });
  if (!response.ok) {
    const failure = await response.json();
    const messages = {
      'Could not read that image.': t('image.import.unreadable', {name: file.name}),
      'Choose an image with at most 64 megapixels.': t('image.import.tooManyPixels'),
      'Choose an image smaller than 64 MB.': t('image.import.tooLarge'),
      'The image size must be between 1 byte and 64 MB.': file.size
        ? t('image.import.tooLarge') : t('image.import.unreadable', {name: file.name}),
    };
    const message = Object.hasOwn(messages, failure.error) ? messages[failure.error]
      : t('image.import.normalizeFailed', {name: file.name, message: failure.error || response.statusText});
    throw new Error(message);
  }
  return response.blob();
}

function loadImage(blob, name) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    const url = URL.createObjectURL(blob);
    image.onload = () => { URL.revokeObjectURL(url); resolve(image); };
    image.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error(t('image.import.unreadable', {name})));
    };
    image.src = url;
  });
}

function choiceButton(label, primary, onClick) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = primary ? 'btn image-import-resize' : 'btn quiet';
  button.textContent = label;
  button.addEventListener('click', onClick);
  return button;
}

function chooseSize(name, width, height, resizedWidth, resizedHeight) {
  return new Promise(resolve => {
    const trigger = document.activeElement;
    const body = document.createElement('div');
    body.className = 'image-import-explanation';
    body.id = 'image-import-explanation';
    for (const text of [t('image.import.largeText', {name, width, height}),
      t('image.import.recommendation', {edge: RECOMMENDED_EDGE}), t('image.import.formatNotice')]) {
      const paragraph = document.createElement('p');
      paragraph.textContent = text;
      body.append(paragraph);
    }
    const actions = document.createElement('div');
    actions.className = 'image-import-actions';
    let choice = null;
    const choose = value => { choice = value; dismissSheet(dialog); };
    const resize = choiceButton(t('image.import.resize', {width: resizedWidth, height: resizedHeight}), true, () => choose('resize'));
    const original = choiceButton(t('image.import.original'), false, () => choose('original'));
    const cancel = choiceButton(t('image.import.cancel'), false, () => choose(null));
    actions.append(resize, original, cancel);
    const dialog = openSheet({
      id: 'image-import-dialog', title: t('image.import.largeTitle'), closeLabel: t('image.import.close'),
      body, footer: actions, className: 'image-import-dialog',
      onClose: () => { trigger?.focus?.(); resolve(choice); },
    });
    dialog.setAttribute('aria-describedby', body.id);
    resize.focus({preventScroll: true});
  });
}

function pngBlob(image, width, height, name) {
  return new Promise((resolve, reject) => {
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext('2d');
    if (!context) { reject(new Error(t('image.import.unreadable', {name}))); return; }
    context.drawImage(image, 0, 0, width, height);
    canvas.toBlob(blob => {
      if (blob) resolve(blob);
      else reject(new Error(t('image.import.unreadable', {name})));
    }, 'image/png');
  });
}

function base64(blob, name) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(',')[1]);
    reader.onerror = () => reject(new Error(t('image.import.unreadable', {name})));
    reader.readAsDataURL(blob);
  });
}

export async function readImageFile(file) {
  if (file.size > MAX_BYTES) throw new Error(t('image.import.tooLarge'));
  const blob = isHeif(file) ? await normalizeHeif(file) : file;
  const image = await loadImage(blob, file.name);
  const width = image.naturalWidth;
  const height = image.naturalHeight;
  if (!width || !height) throw new Error(t('image.import.unreadable', {name: file.name}));
  if (width * height > MAX_PIXELS) throw new Error(t('image.import.tooManyPixels'));
  const scale = Math.min(1, RECOMMENDED_EDGE / Math.max(width, height));
  const resizedWidth = Math.max(1, Math.round(width * scale));
  const resizedHeight = Math.max(1, Math.round(height * scale));
  const choice = scale < 1 ? await chooseSize(file.name, width, height, resizedWidth, resizedHeight) : 'original';
  if (!choice) return null;
  const outputWidth = choice === 'resize' ? resizedWidth : width;
  const outputHeight = choice === 'resize' ? resizedHeight : height;
  const output = await pngBlob(image, outputWidth, outputHeight, file.name);
  return {b64: await base64(output, file.name), name: file.name, width: outputWidth, height: outputHeight};
}
