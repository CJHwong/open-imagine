// The gallery leaves and returns as one file. The bundle holds every workspace's
// records and their media, so a second browser gets the same shelf.
//
// The file is gzipped with the browser's own stream. Base64 makes the bytes a
// third larger, and gzip cannot win that back on media, but it keeps the format
// plain JSON inside, which is worth the size for a local tool.
const FORMAT = 'studio-gallery';
const VERSION = 1;

export async function encodeBundle(items, at = Date.now()) {
  const packed = [];
  for (const item of items) {
    const media = [];
    for (const entry of item.media || []) {
      if (!(entry.blob instanceof Blob)) continue;
      media.push({role: entry.role, mime: entry.blob.type || entry.mime || '', data: await base64(entry.blob)});
    }
    packed.push({workspace: item.workspace, id: item.id, at: item.at, record: item.record, media});
  }
  const body = new Blob([JSON.stringify({format: FORMAT, version: VERSION, exportedAt: at, items: packed})]);
  const gzipped = body.stream().pipeThrough(new CompressionStream('gzip'));
  return new Blob([await new Response(gzipped).arrayBuffer()], {type: 'application/gzip'});
}

export async function decodeBundle(file) {
  const bytes = new Uint8Array(await file.arrayBuffer());
  const plain = bytes[0] === 0x7b;  // `{`: a bundle that is not gzipped
  let text;
  if (plain) text = new TextDecoder().decode(bytes);
  else {
    if (bytes[0] !== 0x1f || bytes[1] !== 0x8b) throw new Error('This file is not a Studio gallery bundle.');
    const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));
    text = await new Response(stream).text();
  }
  let bundle;
  try { bundle = JSON.parse(text); } catch (error) { throw new Error('This file is not a Studio gallery bundle.'); }
  if (bundle.format !== FORMAT) throw new Error('This file is not a Studio gallery bundle.');
  if (bundle.version !== VERSION) throw new Error('This bundle was made by a newer Studio. Update the page first.');
  if (!Array.isArray(bundle.items)) throw new Error('This bundle holds no gallery items.');
  return bundle.items
    .filter(item => item && typeof item.id !== 'undefined' && Array.isArray(item.media))
    .map(item => ({...item, media: item.media.map(entry => ({...entry,
      blob: unbase64(entry.data || '', entry.mime)}))}));
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

async function base64(blob) {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let binary = '';
  const chunk = 0x8000;
  for (let index = 0; index < bytes.length; index += chunk) {
    binary += String.fromCharCode(...bytes.subarray(index, index + chunk));
  }
  return btoa(binary);
}

function unbase64(data, mime) {
  const binary = atob(data);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return new Blob([bytes], {type: mime || 'application/octet-stream'});
}
