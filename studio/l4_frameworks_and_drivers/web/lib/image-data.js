// A reference keeps the bytes of the file it came from, so its type is read off those bytes.
globalThis.studioImageDataUrl = function (base64) {
  const type = base64.startsWith('/9j/') ? 'image/jpeg'
    : base64.startsWith('UklGR') ? 'image/webp'
    : base64.startsWith('R0lGOD') ? 'image/gif'
    : 'image/png';
  return 'data:' + type + ';base64,' + base64;
};
