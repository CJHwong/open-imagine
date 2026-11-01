// A song becomes a tagged MP3 in the tab. The engine writes a WAV, and the page
// used to hand that file over as it was. An MP3 carries the title, the genre and
// the model, so a file that leaves the page still says what it is.
//
// lamejs comes from the CDN, the way abcjs does. Its ESM build at jsDelivr
// throws `MPEGMode is not defined`, so the UMD file is loaded as a script and
// read from the global. If the network is down the page keeps the WAV; the
// caller decides what to do with the failure.
const LAME = 'https://cdn.jsdelivr.net/npm/lamejs@1.2.1/lame.min.js';
const RATE = 48000;
const BITRATE = 192;

export async function encodeMp3(blob, tags = {}) {
  const audio = await decodeAt48k(blob);
  const Mp3Encoder = await loadLame();
  const encoder = new Mp3Encoder(2, RATE, BITRATE);
  const left = audio.getChannelData(0);
  const right = audio.numberOfChannels > 1 ? audio.getChannelData(1) : left;
  const parts = [];
  // One hundred milliseconds per call. The encoder is synchronous, so the loop
  // hands the page back every five seconds of audio.
  const block = RATE / 10;
  for (let start = 0; start < left.length; start += block) {
    const packed = encoder.encodeBuffer(int16(left, start, block), int16(right, start, block));
    if (packed.length) parts.push(new Uint8Array(packed));
    if (start / block % 50 === 49) await new Promise(resolve => setTimeout(resolve, 0));
  }
  const tail = encoder.flush();
  if (tail.length) parts.push(new Uint8Array(tail));
  return new Blob([id3(tags), ...parts], {type: 'audio/mpeg'});
}

// decodeAudioData reads the PCM in the WAV, including 24-bit samples, which no
// view of the raw bytes can do safely. The offline pass fixes the rate and the
// channel count that lamejs takes.
async function decodeAt48k(blob) {
  const context = new AudioContext();
  try {
    const buffer = await context.decodeAudioData(await blob.arrayBuffer());
    const frames = Math.max(1, Math.ceil(buffer.duration * RATE));
    const offline = new OfflineAudioContext(2, frames, RATE);
    const source = offline.createBufferSource();
    source.buffer = buffer;
    source.connect(offline.destination);
    source.start();
    return await offline.startRendering();
  } finally {
    await context.close();
  }
}

async function loadLame() {
  if (window.lamejs?.Mp3Encoder) return window.lamejs.Mp3Encoder;
  await new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = LAME;
    script.onload = resolve;
    script.onerror = () => reject(new Error('The MP3 encoder could not be loaded.'));
    document.head.append(script);
  });
  if (!window.lamejs?.Mp3Encoder) throw new Error('The MP3 encoder could not be loaded.');
  return window.lamejs.Mp3Encoder;
}

function int16(samples, start, length) {
  const block = new Int16Array(Math.min(length, samples.length - start));
  for (let index = 0; index < block.length; index += 1) {
    const value = Math.max(-1, Math.min(1, samples[start + index]));
    block[index] = value < 0 ? value * 0x8000 : value * 0x7fff;
  }
  return block;
}

// ID3v2.3. The tag header size is syncsafe; every frame size is a plain 32-bit
// count, which is the difference from v2.4 that readers still notice.
function id3(tags) {
  const frames = [];
  if (tags.title) frames.push(textFrame('TIT2', tags.title));
  if (tags.genre) frames.push(textFrame('TCON', tags.genre));
  if (tags.artist) frames.push(textFrame('TPE1', tags.artist));
  if (tags.year) frames.push(textFrame('TYER', String(tags.year), false));
  if (tags.comment) frames.push(commentFrame(tags.comment));
  if (tags.lengthMs) frames.push(textFrame('TLEN', String(Math.round(tags.lengthMs)), false));
  if (tags.cover) frames.push(pictureFrame(tags.cover));
  const body = join(frames);
  return new Uint8Array([0x49, 0x44, 0x33, 3, 0, 0, ...syncsafe(body.length), ...body]);
}

// A title may be Chinese, so the text frames carry UTF-16 with a byte-order mark.
// The year and the length are digits, and they stay in the older Latin-1 form.
function textFrame(id, text, wide = true) {
  const value = wide ? new Uint8Array([1, ...wideText(text)]) : new Uint8Array([0, ...latin1Text(text)]);
  return frame(id, value);
}

function commentFrame(text) {
  // Encoding, language, an empty description (wide, terminated), then the text.
  return frame('COMM', new Uint8Array([1, 0x65, 0x6e, 0x67, 0xff, 0xfe, 0, 0, ...wideText(text)]));
}

function pictureFrame(cover) {
  const mime = String(cover.type || 'image/png').toLowerCase();
  const type = mime.includes('jpeg') || mime.includes('jpg') ? 'image/jpeg' : 'image/png';
  const head = [0, ...latin1Text(type), 0, 3, 0];
  return frame('APIC', new Uint8Array([...head, ...cover.bytes]));
}

function frame(id, body) {
  const size = body.length;
  const head = [0, 0, 0, 0].map((_, index) => (size >>> (8 * (3 - index))) & 0xff);
  return new Uint8Array([...latin1Text(id), ...head, 0, 0, ...body]);
}

function wideText(text) {
  const value = String(text);
  const bytes = new Uint8Array(2 + value.length * 2);
  bytes[0] = 0xff;
  bytes[1] = 0xfe;
  for (let index = 0; index < value.length; index += 1) {
    const code = value.charCodeAt(index);
    bytes[2 + index * 2] = code & 0xff;
    bytes[3 + index * 2] = code >> 8;
  }
  return bytes;
}

function latin1Text(text) {
  return new Uint8Array(Array.from(String(text), character => character.charCodeAt(0) & 0xff));
}

function syncsafe(size) {
  return [(size >> 21) & 0x7f, (size >> 14) & 0x7f, (size >> 7) & 0x7f, size & 0x7f];
}

function join(parts) {
  const size = parts.reduce((total, part) => total + part.length, 0);
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const part of parts) {
    bytes.set(part, offset);
    offset += part.length;
  }
  return bytes;
}
