// Workspace help owns its overlay and focus, independently of any media preview.
import {openSheet, dismissSheet} from '../lib/sheet.js';
const IMAGE_GUIDE = [
  ['Generate, or Edit', 'Generate writes a picture from a prompt. Edit changes one you already have, and needs an image from the strip: click a frame, then Edit this.'],
  ['A Look', 'A chip adds one sentence after your words. Each model offers only the options its own test kept.'],
  ['Rewrite', 'It writes out the words you typed, and the words in the marked areas, at length. Each answer lands where it was written, and the Look is added after them. In a batch your words lead every image and each row adds to them, and the press writes a row from its own picture.'],
  ['Mark a region', "Fill the area you want changed. Do not circle it: the mark's own shape is the shape that comes back repainted."],
  ['What changes there', 'One row per marked colour says what changes in that area. Or pick the Mark a region template and leave the rows empty.'],
  ['The brush', 'Three widths, and a loupe follows the brush while you draw. The area you mark is the area that changes, so keep the mark close to what should change.'],
  ['The wait', 'An edit reads your prompt and images for about a minute before its first step. The line in the top bar counts that time.'],
  ['Run and Cancel', 'Run empties the form it sent. Cancel puts all of it back, the marked region included.'],
  ['The strip', 'Images stay in the strip. Download the ones you want before you clear it.'],
];

const VIDEO_GUIDE = [
  ['Generate, or Edit', 'Generate a video from a prompt, optional image keyframes, or an audio track. Edit requires explicitly choosing a clip and an adapter; viewing a gallery clip does not select it for editing.'],
  ['Prompt and templates', 'Describe the subject, action, setting and camera movement. Templates provide starting points; a Look adds to your words.'],
  ['Rewrite and enhancement', 'Rewrite is an explicit prompt-writing action. Generate also runs the model’s prompt enhancer automatically before rendering.'],
  ['References', 'Add a still as a keyframe or an audio track to guide the video. Remove a reference with its cross; this does not delete a gallery result.'],
  ['Duration and size', 'Choose the output shape, resolution and duration before generating. Larger or longer clips take more time and memory.'],
  ['Fast mode', 'LTX-2.5 offers Fast mode in Advanced. It uses float16 computation with the same weights for faster rendering; generated details may differ.'],
  ['Run and Cancel', 'Progress covers the whole render and reaches completion only when the clip is ready. Cancel stops the active operation.'],
  ['The gallery', 'Select one clip to preview. Its action buttons let you download, copy inputs, edit or remove it.'],
];

const MUSIC_GUIDE = [
  ['A style', 'One sentence with the language, genre, mood, instruments, vocal and tempo. A genre word alone is thin.'],
  ['The words', 'Section tags name each part. Leave the words blank, with instrumental on, for a tune with no singing.'],
  ['Planning', 'Melody and chords writes a score first. Direct generation skips it and returns no useful score.'],
  ['Edit score', 'Opens the score beside a live sheet. Generate then makes a new take from the score you edited.'],
  ['A recording', 'A recording makes a cover with Generate, or a transcription with Compose.'],
  ['The songs strip', 'Download all saves every song as a file. Clear all removes them from this browser.'],
  ['The wait', 'A song takes longer than a picture. The run button counts the time, and Cancel keeps the finished songs.'],
];

// Three moves per workspace, then the reference rows. The steps are what a
// first visit needs; the rows answer the second question.
const STEPS = {
  image: [
    ['Say what you want', 'A subject, a setting and a light. Press Generate and read the picture before you change anything.'],
    ['Add a Look if you want one', 'A chip adds one sentence after your words. It costs nothing to leave empty.'],
    ['Run, then read the bar', 'The bar under the picture says the model, the seed and the time. Run empties the form it sent; Cancel puts it back.'],
  ],
  video: [
    ['Describe the shot', 'The subject, the action, the camera and the light. A template fills the shape of a shot.'],
    ['Add a clip only to edit one', 'Generate starts from words. Edit changes a clip you already have and needs an effect.'],
    ['Generate, then scrub', 'The whole render must finish before the clip plays. Cancel stops it and keeps what finished.'],
  ],
  voice: [
    ['Write the script', 'The words to speak, with cues such as [whispers] inline if the model takes them.'],
    ['Choose a voice, or add a recording', 'Design describes a voice. Clone copies one from a clean recording of a single speaker.'],
    ['Generate, then play', 'The preview and the strip keep every take. Download all saves them in one press.'],
  ],
  music: [
    ['Write a style and the words', 'The style sentence carries the genre, the instruments and the tempo. The words carry the song.'],
    ['Generate one take', 'The first take tests the style. A second seed tells you whether the style or the luck was good.'],
    ['Listen, then change one thing', 'Edit the score, reuse the style, or cover a recording. One change per take makes the comparison honest.'],
  ],
};

function musicGuide(_capabilities) {
  return MUSIC_GUIDE;
}

function videoGuide(capabilities) {
  const edit = capabilities.modes?.some(mode => mode.id === 'edit');
  return VIDEO_GUIDE.filter(([name]) => name !== 'Fast mode' || capabilities.fast_mode).map(([name, text]) => {
    if (!edit && name === 'Generate, or Edit') return ['Generate', 'Generate a video from a prompt, optional image keyframes, or an audio track.'];
    if (!edit && name === 'The gallery') return [name, 'Select one clip to preview. Use its action buttons to download, copy inputs or remove it.'];
    return [name, text];
  });
}

function voiceGuide(capabilities) {
  const params = capabilities.modes?.flatMap(mode => mode.params) || [];
  const drama = params.some(param => param.id === 'max_tokens');
  const edit = capabilities.modes?.some(mode => mode.id === 'edit');
  return [
    ['Generate a clip', 'Write the words you want spoken. Generate produces one continuous audio clip for the script.'],
    ['Templates and direction', drama
      ? 'Pick a delivery template or put cues such as [whispers] inside the script. Drama-3 does not use a separate voice description.'
      : 'For Design, choose a voice template or describe the voice. The script contains the words to speak; the voice description directs the delivery.'],
    ['Clone a voice', drama
      ? 'Add a clean reference recording and its exact transcript. Recordings longer than 15 seconds use the first 15 seconds; make the transcript match that excerpt.'
      : 'Add a clean reference recording of one speaker. AuK does not require a transcript for cloning. Remove the reference before recording another one.'],
    ['Preview and selection', 'Click the waveform to choose a playback position. Drag the end handles to select a range, then play that selection. Playback speed changes the preview only.'],
    ['Clip actions', (edit ? 'Download or edit the selected audio from the action bar. ' : 'Download the selected audio from the action bar. ') + 'The more menu includes Send to Video, Send to Clone and copying inputs.'],
    [drama ? 'Audio token limit' : 'Duration', drama
      ? 'Advanced sets a safety limit per internal script chunk. Higher values allow longer output but may prolong repetition; the default is 2048.'
      : 'Use automatic duration or set a target length in Advanced. A window that is too short can cut off words.'],
    ['Run and Cancel', 'The preview and gallery show generation progress. Cancel keeps completed clips; successful generation clears the submitted inputs.'],
    ['Shared status', 'UI and API runs share one model slot. Other tabs follow the current operation and lock controls while it runs.'],
  ];
}

let guideSheet = null;
let guideRestoreFocus = true;

export function closeGuide(restoreFocus = true) {
  if (!guideSheet) return;
  guideRestoreFocus = restoreFocus;
  dismissSheet(guideSheet);
}

export function syncGuide(workspace, backend) {
  if (guideSheet && (guideSheet.dataset.workspace !== workspace || guideSheet.dataset.backend !== backend)) closeGuide(false);
}

function entriesFor(workspace, capabilities) {
  if (workspace === 'voice') return voiceGuide(capabilities);
  if (workspace === 'video') return videoGuide(capabilities);
  if (workspace === 'music') return musicGuide(capabilities);
  return IMAGE_GUIDE;
}

function stepsFor(workspace, capabilities) {
  const steps = STEPS[workspace] || STEPS.image;
  if (workspace !== 'video') return steps;
  const edit = capabilities.modes?.some(mode => mode.id === 'edit');
  // A model without an edit mode gets no step about editing, and no sentence
  // that names it: the reference rows drop theirs the same way.
  if (edit) return steps;
  return [
    steps[0],
    ['Add a still or a track if you want one', 'An image sets the first frame. A track sets the audio.'],
    steps[2],
  ];
}

function stepsSection(workspace, capabilities) {
  const steps = stepsFor(workspace, capabilities);
  const section = document.createElement('section');
  section.className = 'guide-start';
  const title = document.createElement('h3');
  title.textContent = 'Start here';
  const list = document.createElement('ol');
  list.className = 'guide-steps';
  steps.forEach(([name, text]) => {
    const item = document.createElement('li');
    const strong = document.createElement('strong');
    strong.textContent = name;
    const copy = document.createElement('p');
    copy.textContent = text;
    item.append(strong, copy);
    list.append(item);
  });
  section.append(title, list);
  return section;
}

function referenceSection(entries) {
  const section = document.createElement('section');
  section.className = 'guide-more';
  const title = document.createElement('h3');
  title.textContent = 'The details';
  const list = document.createElement('dl');
  entries.forEach(([name, description]) => {
    const term = document.createElement('dt');
    const text = document.createElement('dd');
    term.textContent = name;
    text.textContent = description;
    list.append(term, text);
  });
  section.append(title, list);
  return section;
}

export function openGuide(workspace, backend, capabilities = {}) {
  if (guideSheet) return closeGuide();
  const api = document.createElement('p');
  api.className = 'guide-api';
  const spec = document.createElement('a');
  spec.href = '/api/docs';
  spec.target = '_blank';
  spec.rel = 'noreferrer';
  spec.textContent = 'OpenAPI spec';
  api.append(spec, document.createTextNode(' lists every JSON route. Start at /api/v1/studio.'));
  const body = document.createDocumentFragment();
  body.append(stepsSection(workspace, capabilities), referenceSection(entriesFor(workspace, capabilities)), api);
  guideSheet = openSheet({
    id: 'guide-sheet',
    title: 'How to use this studio',
    body,
    closeLabel: 'Close',
    onClose: function () {
      guideSheet = null;
      document.getElementById('guide-toggle').setAttribute('aria-expanded', 'false');
      if (guideRestoreFocus) document.getElementById('guide-toggle').focus();
      guideRestoreFocus = true;
    },
  });
  guideSheet.dataset.workspace = workspace;
  guideSheet.dataset.backend = backend;
  document.getElementById('guide-toggle').setAttribute('aria-expanded', 'true');
}

document.dispatchEvent(new CustomEvent('studio-guide-ready', {
  detail: {open: openGuide, close: closeGuide, sync: syncGuide},
}));
