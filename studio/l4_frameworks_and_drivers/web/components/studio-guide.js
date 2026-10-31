// Workspace help owns its overlay and focus, independently of any media preview.
import {openSheet, dismissSheet} from '../lib/sheet.js';
import {t} from '../lib/i18n.js';
const IMAGE_GUIDE = [
  ['guide.image.generateOrEdit.name', 'guide.image.generateOrEdit.text'],
  ['guide.image.look.name', 'guide.image.look.text'],
  ['guide.image.rewrite.name', 'guide.image.rewrite.text'],
  ['guide.image.markRegion.name', 'guide.image.markRegion.text'],
  ['guide.image.whatChanges.name', 'guide.image.whatChanges.text'],
  ['guide.image.brush.name', 'guide.image.brush.text'],
  ['guide.image.wait.name', 'guide.image.wait.text'],
  ['guide.image.runCancel.name', 'guide.image.runCancel.text'],
  ['guide.image.strip.name', 'guide.image.strip.text'],
];

const VIDEO_GUIDE = [
  ['guide.video.generateOrEdit.name', 'guide.video.generateOrEdit.text'],
  ['guide.video.promptTemplates.name', 'guide.video.promptTemplates.text'],
  ['guide.video.rewriteEnhancement.name', 'guide.video.rewriteEnhancement.text'],
  ['guide.video.references.name', 'guide.video.references.text'],
  ['guide.video.durationSize.name', 'guide.video.durationSize.text'],
  ['guide.video.fastMode.name', 'guide.video.fastMode.text'],
  ['guide.video.runCancel.name', 'guide.video.runCancel.text'],
  ['guide.video.gallery.name', 'guide.video.gallery.text'],
];

const MUSIC_GUIDE = [
  ['guide.music.style.name', 'guide.music.style.text'],
  ['guide.music.words.name', 'guide.music.words.text'],
  ['guide.music.planning.name', 'guide.music.planning.text'],
  ['guide.music.editScore.name', 'guide.music.editScore.text'],
  ['guide.music.recording.name', 'guide.music.recording.text'],
  ['guide.music.songsStrip.name', 'guide.music.songsStrip.text'],
  ['guide.music.wait.name', 'guide.music.wait.text'],
];

// Three moves per workspace, then the reference rows. The steps are what a
// first visit needs; the rows answer the second question.
const STEPS = {
  image: [
    ['guide.steps.image.say.name', 'guide.steps.image.say.text'],
    ['guide.steps.image.look.name', 'guide.steps.image.look.text'],
    ['guide.steps.image.runBar.name', 'guide.steps.image.runBar.text'],
  ],
  video: [
    ['guide.steps.video.describe.name', 'guide.steps.video.describe.text'],
    ['guide.steps.video.addClip.name', 'guide.steps.video.addClip.text'],
    ['guide.steps.video.generateScrub.name', 'guide.steps.video.generateScrub.text'],
  ],
  voice: [
    ['guide.steps.voice.script.name', 'guide.steps.voice.script.text'],
    ['guide.steps.voice.voice.name', 'guide.steps.voice.voice.text'],
    ['guide.steps.voice.play.name', 'guide.steps.voice.play.text'],
  ],
  music: [
    ['guide.steps.music.styleWords.name', 'guide.steps.music.styleWords.text'],
    ['guide.steps.music.oneTake.name', 'guide.steps.music.oneTake.text'],
    ['guide.steps.music.listen.name', 'guide.steps.music.listen.text'],
  ],
};

function musicGuide(_capabilities) {
  return MUSIC_GUIDE;
}

function videoGuide(capabilities) {
  const edit = capabilities.modes?.some(mode => mode.id === 'edit');
  return VIDEO_GUIDE.filter(([nameKey]) => nameKey !== 'guide.video.fastMode.name' || capabilities.fast_mode)
    .map(([nameKey, textKey]) => {
      if (!edit && nameKey === 'guide.video.generateOrEdit.name') {
        return ['guide.video.generate.name', 'guide.video.generate.text'];
      }
      if (!edit && nameKey === 'guide.video.gallery.name') {
        return [nameKey, 'guide.video.gallery.noEdit.text'];
      }
      return [nameKey, textKey];
    });
}

function voiceGuide(capabilities) {
  const params = capabilities.modes?.flatMap(mode => mode.params) || [];
  const drama = params.some(param => param.id === 'max_tokens');
  const edit = capabilities.modes?.some(mode => mode.id === 'edit');
  return [
    ['guide.voice.generate.name', 'guide.voice.generate.text'],
    ['guide.voice.templates.name', drama ? 'guide.voice.templates.drama.text' : 'guide.voice.templates.design.text'],
    ['guide.voice.clone.name', drama ? 'guide.voice.clone.drama.text' : 'guide.voice.clone.design.text'],
    ['guide.voice.preview.name', 'guide.voice.preview.text'],
    ['guide.voice.clipActions.name', edit ? 'guide.voice.clipActions.edit.text' : 'guide.voice.clipActions.download.text'],
    [drama ? 'guide.voice.tokenLimit.name' : 'guide.voice.duration.name',
      drama ? 'guide.voice.tokenLimit.text' : 'guide.voice.duration.text'],
    ['guide.voice.runCancel.name', 'guide.voice.runCancel.text'],
    ['guide.voice.sharedStatus.name', 'guide.voice.sharedStatus.text'],
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
    ['guide.steps.video.addStill.name', 'guide.steps.video.addStill.text'],
    steps[2],
  ];
}

function stepsSection(workspace, capabilities) {
  const steps = stepsFor(workspace, capabilities);
  const section = document.createElement('section');
  section.className = 'guide-start';
  const title = document.createElement('h3');
  title.textContent = t('guide.start.title');
  const list = document.createElement('ol');
  list.className = 'guide-steps';
  steps.forEach(([nameKey, textKey]) => {
    const item = document.createElement('li');
    // The number takes the first grid column, so the name and the sentence share a
    // wrapper. Loose children would put the sentence back in the number's 28 px column.
    const body = document.createElement('div');
    const strong = document.createElement('strong');
    strong.textContent = t(nameKey);
    const copy = document.createElement('p');
    copy.textContent = t(textKey);
    body.append(strong, copy);
    item.append(body);
    list.append(item);
  });
  section.append(title, list);
  return section;
}

function referenceSection(entries) {
  const section = document.createElement('section');
  section.className = 'guide-more';
  const title = document.createElement('h3');
  title.textContent = t('guide.details.title');
  const list = document.createElement('dl');
  entries.forEach(([termKey, textKey]) => {
    const term = document.createElement('dt');
    const text = document.createElement('dd');
    term.textContent = t(termKey);
    text.textContent = t(textKey);
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
  spec.textContent = t('page.api.spec');
  api.append(spec, document.createTextNode(t('guide.api.rest')));
  const body = document.createDocumentFragment();
  body.append(stepsSection(workspace, capabilities), referenceSection(entriesFor(workspace, capabilities)), api);
  guideSheet = openSheet({
    id: 'guide-sheet',
    title: t('guide.sheet.title'),
    body,
    closeLabel: t('guide.sheet.close'),
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
