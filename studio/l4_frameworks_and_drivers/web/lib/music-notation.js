// Load the engraver only when a recording's score is opened.
let engraver;
export async function renderNotation(target, score) {
  if (!engraver) engraver = import('https://cdn.jsdelivr.net/npm/abcjs@6.6.1/+esm')
    .then(module => module.default || module).catch(error => { engraver = null; throw error; });
  const abc = await engraver;
  if (!target.isConnected) return;
  target.replaceChildren();
  // Engrave at the page's width up to the widest staff that still reads as a sheet.
  // A wider page scales that staff to fill the paper, so the music keeps the page's
  // width instead of sitting in its left half. Narrow pages engrave at their own
  // width rather than shrinking the notes.
  const width = Math.max(320, Math.round(target.clientWidth || 640));
  const staffwidth = Math.min(900, width);
  const tunes = abc.renderAbc(target, score, {responsive: 'resize', staffwidth,
    oneSvgPerLine: true, add_classes: true, paddingright: 20,
    wrap: {minSpacing: 1.8, maxSpacing: 2.7, preferredMeasuresPerLine: Math.max(4, Math.round(staffwidth / 220))}});
  if (!target.querySelector('svg')) throw new Error('This score could not be engraved. Open the ABC source below.');
  const warnings = tunes.flatMap(tune => tune.warnings || []);
  // The tunes are the engraving's own objects: their elements are the SVG on the page, so
  // a player can light the notes the synth reaches.
  return {tunes, warnings: warnings.length};
}
