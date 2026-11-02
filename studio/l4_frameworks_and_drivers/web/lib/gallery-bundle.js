// The gallery leaves and returns as one ZIP. gallery.json holds the records;
// media/ holds each picture, clip and track as its own file. Nothing is base64
// and nothing is gzipped a second time, so the file opens in Finder and the media
// is usable without Studio.
//
// The archive is written with stored entries (method 0): PNG, MP4 and WAV are
// already compressed. Each entry is a header plus the media Blob itself, so the
// writer never copies a file through a string. A JavaScript string caps near a few
// hundred megabytes in WebKit and Firefox; the old base64 JSON hit that cap.
//
// Older files still load: version 1 is one JSON object, version 2 is line-delimited
// JSON. Both are gzipped.
import {t} from './i18n.js';

const FORMAT = 'studio-gallery';
const VERSION = 3;
const LIMIT = 0xffffffff;

export async function encodeBundle(items, at = Date.now(), onProgress) {
  const manifest = {format: FORMAT, version: VERSION, exportedAt: at, items: []};
  const files = [];
  const used = new Set();
  for (const item of items) {
    const media = [];
    for (const entry of item.media || []) {
      if (!(entry.blob instanceof Blob)) continue;
      const name = freeName(used, mediaName(item, entry));
      files.push({name, blob: entry.blob});
      media.push({role: entry.role, mime: entry.blob.type || entry.mime || '',
        file: name, size: entry.blob.size});
    }
    manifest.items.push({workspace: item.workspace, id: item.id, at: item.at,
      record: item.record, media});
  }
  return buildZip(files, at, manifest, onProgress);
}

// The files leave as one archive too, without the manifest: a download gives files,
// not a backup, and Import must not mistake it for one.
export async function encodeFiles(files, at = Date.now(), onProgress) {
  const used = new Set();
  const named = [];
  for (const file of files) {
    if (!(file.blob instanceof Blob)) continue;
    named.push({name: freeName(used, rootName(file.name)), blob: file.blob});
  }
  return buildZip(named, at, null, onProgress);
}

export function filesName(kind, at = Date.now()) {
  const when = new Date(at);
  const two = value => String(value).padStart(2, '0');
  return 'studio-' + kind + '-' + when.getFullYear() + two(when.getMonth() + 1) + two(when.getDate())
    + '-' + two(when.getHours()) + two(when.getMinutes()) + two(when.getSeconds()) + '.zip';
}

async function buildZip(files, at, manifest, onProgress) {
  const parts = [];
  const central = [];
  let offset = 0;
  const total = files.reduce((sum, file) => sum + file.blob.size, 0);
  let done = 0;
  if (manifest) {
    const bytes = new TextEncoder().encode(JSON.stringify(manifest));
    const crc = crc32(bytes);
    const header = localHeader('gallery.json', crc, bytes.length, at);
    central.push(centralHeader('gallery.json', crc, bytes.length, offset, at));
    parts.push(header, bytes);
    offset += header.length + bytes.length;
  }
  let index = 0;
  for (const file of files) {
    const crc = await crc32Blob(file.blob);
    const header = localHeader(file.name, crc, file.blob.size, at);
    central.push(centralHeader(file.name, crc, file.blob.size, offset, at));
    parts.push(header, file.blob);
    offset += header.length + file.blob.size;
    if (offset > LIMIT) throw new Error(t('gallery.error.tooLarge'));
    done += file.blob.size;
    index += 1;
    if (onProgress) onProgress({done, total, index, count: files.length, file: file.name});
  }
  const directory = concat(central);
  const end = endRecord(central.length, directory.length, offset);
  if (offset + directory.length + end.length > LIMIT) throw new Error(t('gallery.error.tooLarge'));
  parts.push(directory, end);
  return new Blob(parts, {type: 'application/zip'});
}

export async function decodeBundle(file) {
  const head = new Uint8Array(await file.slice(0, 4).arrayBuffer());
  if (head[0] === 0x50 && head[1] === 0x4b) return decodeZip(file);
  const plain = head[0] === 0x7b;  // `{`: a bundle that is not gzipped
  if (!plain && (head[0] !== 0x1f || head[1] !== 0x8b)) {
    throw fail('gallery.error.notBundle');
  }
  const stream = plain ? file.stream() : file.stream().pipeThrough(new DecompressionStream('gzip'));
  return decodeLines(stream);
}

export function bundleName(at = Date.now()) {
  const when = new Date(at);
  const two = value => String(value).padStart(2, '0');
  return 'studio-gallery-' + when.getFullYear() + two(when.getMonth() + 1) + two(when.getDate())
    + '-' + two(when.getHours()) + two(when.getMinutes()) + two(when.getSeconds()) + '.zip';
}

export function saveBundle(blob, name) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url; link.download = name; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// A failed read is a bundle error, not a parser error, and the toast should show
// the translated sentence rather than a JSON parser's English.
function fail(key) {
  const error = new Error(t(key));
  error.bundle = true;
  return error;
}

// ---- the archive ----

function rootName(name) {
  const clean = String(name || '').replace(/[\\/:*?"<>|]+/g, '-').replace(/^\.+/, '').slice(0, 120);
  return clean || 'file';
}

function mediaName(item, entry) {
  const safe = String(item.id).replace(/[^A-Za-z0-9._-]+/g, '_').slice(0, 96) || 'item';
  const role = String(entry.role || 'media').replace(/[^A-Za-z0-9._-]+/g, '_');
  return `media/${item.workspace}-${safe}-${role}.${extension(entry.blob.type || entry.mime)}`;
}

function extension(mime) {
  const known = {'image/png': 'png', 'image/jpeg': 'jpg', 'image/webp': 'webp',
    'video/mp4': 'mp4', 'audio/wav': 'wav', 'audio/x-wav': 'wav', 'audio/mpeg': 'mp3'};
  return known[String(mime || '').toLowerCase()] || 'bin';
}

function freeName(used, name) {
  if (!used.has(name)) { used.add(name); return name; }
  const dot = name.lastIndexOf('.');
  const base = dot < 0 ? name : name.slice(0, dot);
  const tail = dot < 0 ? '' : name.slice(dot);
  let index = 2;
  while (used.has(`${base}-${index}${tail}`)) index += 1;
  used.add(`${base}-${index}${tail}`);
  return `${base}-${index}${tail}`;
}

function dosTime(at) {
  const when = new Date(at);
  return {
    time: (when.getHours() << 11) | (when.getMinutes() << 5) | (when.getSeconds() >> 1),
    date: ((when.getFullYear() - 1980) << 9) | ((when.getMonth() + 1) << 5) | when.getDate(),
  };
}

function localHeader(name, crc, size, at) {
  const nameBytes = new TextEncoder().encode(name);
  const bytes = new Uint8Array(30 + nameBytes.length);
  const view = new DataView(bytes.buffer);
  const stamp = dosTime(at);
  view.setUint32(0, 0x04034b50, true);
  view.setUint16(4, 20, true);
  view.setUint16(6, 0x0800, true);  // names are UTF-8
  view.setUint16(8, 0, true);       // stored, not deflated
  view.setUint16(10, stamp.time, true);
  view.setUint16(12, stamp.date, true);
  view.setUint32(14, crc, true);
  view.setUint32(18, size, true);
  view.setUint32(22, size, true);
  view.setUint16(26, nameBytes.length, true);
  view.setUint16(28, 0, true);
  bytes.set(nameBytes, 30);
  return bytes;
}

function centralHeader(name, crc, size, offset, at) {
  const nameBytes = new TextEncoder().encode(name);
  const bytes = new Uint8Array(46 + nameBytes.length);
  const view = new DataView(bytes.buffer);
  const stamp = dosTime(at);
  view.setUint32(0, 0x02014b50, true);
  view.setUint16(4, 20, true);
  view.setUint16(6, 20, true);
  view.setUint16(8, 0x0800, true);
  view.setUint16(10, 0, true);
  view.setUint16(12, stamp.time, true);
  view.setUint16(14, stamp.date, true);
  view.setUint32(16, crc, true);
  view.setUint32(20, size, true);
  view.setUint32(24, size, true);
  view.setUint16(28, nameBytes.length, true);
  view.setUint16(30, 0, true);
  view.setUint16(32, 0, true);
  view.setUint16(34, 0, true);
  view.setUint16(36, 0, true);
  view.setUint32(38, 0, true);
  view.setUint32(42, offset, true);
  bytes.set(nameBytes, 46);
  return bytes;
}

function endRecord(count, size, offset) {
  const bytes = new Uint8Array(22);
  const view = new DataView(bytes.buffer);
  view.setUint32(0, 0x06054b50, true);
  view.setUint16(8, count, true);
  view.setUint16(10, count, true);
  view.setUint32(12, size, true);
  view.setUint32(16, offset, true);
  return bytes;
}

function concat(parts) {
  const size = parts.reduce((total, part) => total + part.length, 0);
  const bytes = new Uint8Array(size);
  let at = 0;
  for (const part of parts) { bytes.set(part, at); at += part.length; }
  return bytes;
}

// ---- reading ----

async function decodeZip(file) {
  const entries = await readDirectory(file);
  const manifestEntry = entries.get('gallery.json');
  if (!manifestEntry) throw fail('gallery.error.notBundle');
  let manifest;
  try { manifest = JSON.parse(await (await entryBlob(file, manifestEntry)).text()); }
  catch (error) { throw fail('gallery.error.notBundle'); }
  if (manifest.format !== FORMAT) throw fail('gallery.error.notBundle');
  if (manifest.version !== VERSION) throw fail('gallery.error.newer');
  const items = [];
  for (const item of manifest.items || []) {
    const media = [];
    let complete = true;
    for (const ref of item.media || []) {
      const entry = entries.get(ref.file);
      // A file the archive names but does not hold is corruption. Drop the whole
      // item, or a restored record would point at a picture it never had.
      if (!entry) { complete = false; break; }
      media.push({role: ref.role, mime: ref.mime || '', blob: await entryBlob(file, entry, ref.mime)});
    }
    if (complete) items.push({...item, media});
  }
  return items.filter(item => typeof item.id !== 'undefined');
}

async function readDirectory(file) {
  const tail = new Uint8Array(await file.slice(Math.max(0, file.size - 66560)).arrayBuffer());
  const view = new DataView(tail.buffer);
  let end = -1;
  for (let at = tail.length - 22; at >= 0; at -= 1) {
    if (view.getUint32(at, true) === 0x06054b50) { end = at; break; }
  }
  if (end < 0) throw fail('gallery.error.notBundle');
  const count = view.getUint16(end + 10, true);
  const size = view.getUint32(end + 12, true);
  const offset = view.getUint32(end + 16, true);
  if (count === 0xffff || size === LIMIT || offset === LIMIT) throw new Error(t('gallery.error.tooLarge'));
  const directory = new DataView(await file.slice(offset, offset + size).arrayBuffer());
  const entries = new Map();
  let at = 0;
  for (let index = 0; index < count; index += 1) {
    if (directory.getUint32(at, true) !== 0x02014b50) throw fail('gallery.error.notBundle');
    const nameLength = directory.getUint16(at + 28, true);
    const extraLength = directory.getUint16(at + 30, true);
    const commentLength = directory.getUint16(at + 32, true);
    const name = new TextDecoder().decode(new Uint8Array(directory.buffer, at + 46, nameLength));
    entries.set(name, {method: directory.getUint16(at + 10, true),
      compressed: directory.getUint32(at + 20, true),
      size: directory.getUint32(at + 24, true),
      local: directory.getUint32(at + 42, true)});
    at += 46 + nameLength + extraLength + commentLength;
  }
  return entries;
}

async function entryBlob(file, entry, mime) {
  const local = new DataView(await file.slice(entry.local, entry.local + 30).arrayBuffer());
  const start = entry.local + 30 + local.getUint16(26, true) + local.getUint16(28, true);
  const slice = file.slice(start, start + entry.compressed);
  if (entry.method === 0) return mime ? new Blob([slice], {type: mime}) : slice;
  if (entry.method === 8) {
    const plain = await new Response(slice.stream().pipeThrough(new DecompressionStream('deflate-raw')))
      .arrayBuffer();
    return new Blob([plain], {type: mime || 'application/octet-stream'});
  }
  throw fail('gallery.error.notBundle');
}

// ---- version 1 and 2 ----

async function decodeLines(stream) {
  let header = null;
  const items = [];
  try {
    await eachLine(stream, line => {
      const parsed = JSON.parse(line);
      if (header) { items.push(restore(parsed)); return; }
      if (parsed.format !== FORMAT) throw fail('gallery.error.notBundle');
      // Version 2 wrote a header line, then one item per line. Version 1 wrote the
      // whole file as one object, so its only line is the bundle itself.
      if (parsed.version === 1) {
        header = parsed;
        for (const item of parsed.items || []) if (item && Array.isArray(item.media)) items.push(restore(item));
      } else if (parsed.version === 2) header = parsed;
      else throw fail('gallery.error.newer');
    });
  } catch (error) {
    if (error.bundle) throw error;
    throw fail('gallery.error.notBundle');
  }
  if (!header) throw fail('gallery.error.notBundle');
  return items.filter(item => typeof item.id !== 'undefined');
}

// Pieces wait in an array and join once per line. Growing one string chunk by
// chunk, then searching it again, copies the whole line on every read.
async function eachLine(stream, onLine) {
  const reader = stream.pipeThrough(new TextDecoderStream()).getReader();
  let pieces = [];
  for (;;) {
    const {done, value} = await reader.read();
    if (done) break;
    let text = value;
    for (;;) {
      const at = text.indexOf('\n');
      if (at < 0) { if (text) pieces.push(text); break; }
      pieces.push(text.slice(0, at));
      const line = pieces.join('');
      pieces = [];
      if (line.trim()) await onLine(line);
      text = text.slice(at + 1);
    }
  }
  const tail = pieces.join('');
  if (tail.trim()) await onLine(tail);
}

function restore(item) {
  return {...item, media: (item.media || []).map(entry => ({role: entry.role, mime: entry.mime,
    blob: unbase64(entry.data || '', entry.mime)}))};
}

function unbase64(data, mime) {
  const binary = atob(data);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return new Blob([bytes], {type: mime || 'application/octet-stream'});
}

// ---- CRC ----

const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let index = 0; index < 256; index += 1) {
    let value = index;
    for (let step = 0; step < 8; step += 1) {
      value = value & 1 ? 0xedb88320 ^ (value >>> 1) : value >>> 1;
    }
    table[index] = value >>> 0;
  }
  return table;
})();

function crc32(bytes) {
  let crc = 0xffffffff;
  for (let index = 0; index < bytes.length; index += 1) {
    crc = CRC_TABLE[(crc ^ bytes[index]) & 0xff] ^ (crc >>> 8);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

async function crc32Blob(blob) {
  let crc = 0xffffffff;
  const reader = blob.stream().getReader();
  for (;;) {
    const {done, value} = await reader.read();
    if (done) break;
    for (let index = 0; index < value.length; index += 1) {
      crc = CRC_TABLE[(crc ^ value[index]) & 0xff] ^ (crc >>> 8);
    }
  }
  return (crc ^ 0xffffffff) >>> 0;
}
