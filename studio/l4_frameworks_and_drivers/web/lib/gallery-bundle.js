// The gallery leaves and returns as one file. The bundle holds every workspace's
// records and their media, so a second browser gets the same shelf.
//
// Version 2 is line-delimited JSON: one header line, then one line per item. A
// browser caps the length of one JavaScript string (WebKit and Firefox raise
// "allocation size overflow" near 256 MB), so the writer never builds the file as
// one string. It pushes small parts into a Blob and lets the gzip stream read them.
// The reader parses one line at a time for the same reason. Version 1 files still
// load: they are one JSON object, and one line is all they have.
const FORMAT = 'studio-gallery';
const VERSION = 2;
// Base64 takes 3 bytes to 4 characters, so a chunk that is a multiple of 3 keeps
// every chunk decodable on its own.
const CHUNK = 3 * 1024 * 1024;
const GZIP_PART = 4 * 1024 * 1024;

export async function encodeBundle(items, at = Date.now()) {
  const parts = [JSON.stringify({format: FORMAT, version: VERSION, exportedAt: at}) + '\n'];
  for (const item of items) {
    const media = (item.media || []).filter(entry => entry.blob instanceof Blob);
    parts.push(JSON.stringify({workspace: item.workspace, id: item.id, at: item.at,
      record: item.record}).slice(0, -1) + ',"media":[');
    for (let index = 0; index < media.length; index += 1) {
      const entry = media[index];
      if (index) parts.push(',');
      parts.push(JSON.stringify({role: entry.role, mime: entry.blob.type || entry.mime || ''}).slice(0, -1)
        + ',"data":"');
      for (let offset = 0; offset < entry.blob.size; offset += CHUNK) {
        const bytes = new Uint8Array(await entry.blob.slice(offset, offset + CHUNK).arrayBuffer());
        parts.push(base64(bytes));
      }
      parts.push('"}');
    }
    parts.push(']}\n');
  }
  return gzip(new Blob(parts));
}

export async function decodeBundle(file) {
  const head = new Uint8Array(await file.slice(0, 2).arrayBuffer());
  const plain = head[0] === 0x7b;  // `{`: a bundle that is not gzipped
  if (!plain && (head[0] !== 0x1f || head[1] !== 0x8b)) {
    throw new Error('This file is not a Studio gallery bundle.');
  }
  const stream = plain ? file.stream() : file.stream().pipeThrough(new DecompressionStream('gzip'));
  let header = null;
  const items = [];
  try {
    await eachLine(stream, line => {
      const parsed = JSON.parse(line);
      if (header) { items.push(restore(parsed)); return; }
      if (parsed.format !== FORMAT) throw new Error('This file is not a Studio gallery bundle.');
      // Version 2 writes a header line, then one item per line. Version 1 wrote the
      // whole file as one object, so its only line is the bundle itself.
      if (parsed.version === 1) {
        header = parsed;
        for (const item of parsed.items || []) if (item && Array.isArray(item.media)) items.push(restore(item));
      } else if (parsed.version === VERSION) header = parsed;
      else throw new Error('This bundle was made by a newer Studio. Update the page first.');
    });
  } catch (error) {
    if (error.message.startsWith('This bundle') || error.message.startsWith('This file')) throw error;
    throw new Error('This file is not a Studio gallery bundle.');
  }
  if (!header) throw new Error('This file is not a Studio gallery bundle.');
  return items.filter(item => typeof item.id !== 'undefined');
}

export function bundleName(at = Date.now()) {
  const when = new Date(at);
  const two = value => String(value).padStart(2, '0');
  return 'studio-gallery-' + when.getFullYear() + two(when.getMonth() + 1) + two(when.getDate())
    + '-' + two(when.getHours()) + two(when.getMinutes()) + two(when.getSeconds()) + '.json.gz';
}

export function saveBundle(blob, name) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url; link.download = name; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// A line can be empty at the end of the file, and a file that gzip cut short should
// fail as a bad bundle, not as a JSON parser error with no home. Pieces wait in an
// array and join once per line: growing one string chunk by chunk, then searching
// it again, copies the whole line on every read and turns a big item quadratic.
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
  // The base64 text has done its job once the Blob exists. Drop it, or a large
  // import keeps every character of the file in memory a second time.
  return {...item, media: (item.media || []).map(entry => ({role: entry.role, mime: entry.mime,
    blob: unbase64(entry.data || '', entry.mime)}))};
}

async function gzip(blob) {
  const reader = blob.stream().pipeThrough(new CompressionStream('gzip')).getReader();
  const parts = [];
  let pending = [], size = 0;
  const flush = () => {
    if (!size) return;
    const merged = new Uint8Array(size);
    let at = 0;
    for (const chunk of pending) { merged.set(chunk, at); at += chunk.length; }
    parts.push(merged); pending = []; size = 0;
  };
  for (;;) {
    const {done, value} = await reader.read();
    if (done) break;
    pending.push(value); size += value.length;
    if (size >= GZIP_PART) flush();
  }
  flush();
  return new Blob(parts, {type: 'application/gzip'});
}

function base64(bytes) {
  let binary = '';
  for (let index = 0; index < bytes.length; index += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(index, index + 0x8000));
  }
  return btoa(binary);
}

function unbase64(data, mime) {
  const binary = atob(data);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return new Blob([bytes], {type: mime || 'application/octet-stream'});
}
