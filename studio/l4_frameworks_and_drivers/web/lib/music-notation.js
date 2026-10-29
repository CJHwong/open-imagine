// Load the engraver only when a recording's score is opened.
let engraver;
export async function renderNotation(target, score) {
  if (!engraver) engraver = import('https://cdn.jsdelivr.net/npm/abcjs@6.6.1/+esm')
    .then(module => module.default || module).catch(error => { engraver = null; throw error; });
  const abc = await engraver;
  if (!target.isConnected) return;
  target.replaceChildren();
  const tunes = abc.renderAbc(target, score, {responsive: 'resize', staffwidth: 640,
    oneSvgPerLine: true, add_classes: true, paddingright: 20,
    wrap: {minSpacing: 1.8, maxSpacing: 2.7, preferredMeasuresPerLine: 4}});
  if (!target.querySelector('svg')) throw new Error('This score could not be engraved. Open the ABC source below.');
  const warnings = tunes.flatMap(tune => tune.warnings || []);
  return warnings.length;
}
