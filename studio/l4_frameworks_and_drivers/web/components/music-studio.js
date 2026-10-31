import {musicSongs, saveMusicSong, updateMusicSong, deleteMusicSong, musicDraft, saveMusicDraft, clearMusic} from '../lib/music-store.js';
import {renderNotation} from '../lib/music-notation.js';
import {renderSongText} from '../lib/music-lyrics.js';
import {closeMenus, menuItem, toggleMenu} from './popup-menu.js';
import {blobBase64, normalizeReference} from '../lib/voice-audio.js';
import {startRecording} from '../lib/recorder.js';
import {musicScore, musicCoverPrompt, musicCoverImagePrompt, musicCoverNeedsRewrite} from '../lib/music-score.js';
import {rememberGalleryView, preferredGalleryId, galleryBatch} from '../lib/gallery-view.js';
import {openSheet, dismissSheet} from '../lib/sheet.js';
import {render} from 'https://cdn.jsdelivr.net/npm/lit@3.2.1/+esm';
import {pencilLoop, playingMark} from './gallery-marker.js';
import './gallery-browser.js';
import './run-button.js';
import {configureLookRows} from './look-rows.js';
import {t, plural} from '../lib/i18n.js';

// The run button says Generate in every workflow, as every other workspace's does, and
// the sub line names what this one makes. The mode picker is the four workflows the
// engine declares, so a workflow is never hidden behind an Advanced checkbox.
const MODE_CAPTIONS = {
  generate: 'music.mode_caption.generate',
  plan: 'music.mode_caption.plan',
  transcribe: 'music.mode_caption.transcribe',
  cover: 'music.mode_caption.cover',
};
// The empty pane says what the chosen output needs. Generate and Compose are the two
// choices; a reference recording turns them into a cover and a transcription, so the copy
// names that result rather than a fourth mode.
const EMPTY_COPY = {
  generate: [t('music.empty.generate'), t('music.empty.action'), 'style'],
  plan: [t('music.empty.plan'), t('music.empty.action'), 'style'],
  transcribe: [t('music.empty.transcribe'), t('music.empty.choose_keep'), 'task'],
  cover: [t('music.empty.cover'), t('music.empty.action'), 'style'],
};

// The row names and the chip labels are UI copy. The sentence is the model's and stays
// English. The third field stays English too, because a saved draft may still name its
// preset that way.
const STYLE_ROW_SLUGS = {
  Genre: 'genre', Mood: 'mood', Instruments: 'instrument', Vocals: 'vocal',
  Tempo: 'tempo', Production: 'production', Language: 'language',
};
function presetSlug(legacy) {
  return String(legacy).toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
}
const MUSIC_STYLE_ROWS_EN = [
  {name: "Genre", options: [
    ["Pop", "Use a pop arrangement with a memorable melodic hook and clear verse and chorus sections over a steady pulse.", "pop"],
    ["Hip hop", "Use a hip hop arrangement with a syncopated groove and repeated motifs that leave room for the lead.", "hip hop"],
    ["Rock", "Use a rock arrangement with a firm backbeat and strong rhythmic accents that build contrast between sections.", "rock"],
    ["Electronic", "Use an electronic arrangement with repeating rhythmic patterns and evolving layers that build through distinct sections.", "electronic"],
    ["R&B", "Use an R&B arrangement with a smooth syncopated groove and rich harmonies supporting expressive melodic phrases.", "r&b"],
    ["Country", "Use a country arrangement with a steady backbeat and clear storytelling phrases over simple chord changes.", "country"],
    ["Latin", "Use a Latin arrangement with interlocking rhythmic patterns and syncopated accents that support a flowing melodic lead.", "latin"],
    ["Metal", "Use a metal arrangement with tightly accented rhythmic patterns and strong contrasts between sustained power and rapid attacks.", "metal"],
    ["Jazz", "Use a jazz arrangement with a swinging rhythmic feel and extended harmonies that invite expressive melodic variation.", "jazz"],
    ["Classical", "Use a classical arrangement with developed melodic themes and contrasting phrases shaped by clear harmonic movement.", "classical"],
    ["Folk", "Use a folk arrangement with a simple memorable melody and repeating verse structure that supports musical storytelling.", "folk"],
    ["Reggae", "Use a reggae arrangement with offbeat chord accents and a steady syncopated groove that leaves space between phrases.", "reggae"],
    ["Lo-fi", "Use a lo-fi arrangement with understated repeating motifs and a loosely placed groove around a compact harmonic loop.", "lo-fi"],
    ["Ambient", "Use an ambient arrangement with evolving harmonic layers and spacious melodic fragments rather than a prominent rhythmic pattern.", "ambient"],
    ["House", "Use a house arrangement with a steady four-on-the-floor pulse and syncopated repeating figures.", "house"],
    ["Techno", "Use a techno arrangement with a persistent pulse and small evolving rhythmic variations.", "techno"],
    ["Funk", "Use a funk arrangement with interlocking syncopated figures and deliberate spaces between accents.", "funk"],
    ["Neo-soul", "Use a neo-soul arrangement with rich harmonies and a relaxed syncopated groove.", "neo-soul"],
    ["Gospel", "Use a gospel-inspired arrangement with expressive call-and-response and rising vocal intensity.", "gospel"],
    ["Motown soul", "Use a Motown-inspired soul arrangement with a strong melodic hook and a tight danceable pulse.", "motown soul"],
    ["Heavy metal", "Use a heavy metal arrangement with tightly accented riffs and strong contrasts between sustained power and fast attacks.", "heavy metal"],
    ["Punk rock", "Use a punk rock arrangement with short forceful phrases and a direct urgent pulse.", "punk rock"],
    ["Bossa nova", "Use a bossa nova arrangement with understated syncopation and gently moving harmonies.", "bossa nova"],
    ["Salsa", "Use a salsa arrangement with energetic layered rhythmic patterns and sharply answered melodic phrases.", "salsa"],
    ["Samba", "Use a samba arrangement with buoyant interlocking rhythmic figures and flowing melodic responses.", "samba"],
    ["Tango", "Use a tango arrangement with strongly shaped accents and dramatic pauses between melodic phrases.", "tango"],
    ["Afrobeat-inspired", "Use an Afrobeat-inspired arrangement with interlocking cyclical figures and extended rhythmic momentum.", "afrobeat-inspired"],
    ["Drum and bass", "Use a drum and bass arrangement with fast broken-beat accents and contrasting sustained harmonic space.", "drum and bass"],
    ["Trance", "Use a trance arrangement with repeating arpeggios and a rising sense of harmonic release.", "trance"],
    ["Dubstep", "Use a dubstep arrangement with a spacious half-time feel and abrupt rhythmic contrasts.", "dubstep"],
    ["Psychedelic rock", "Use a psychedelic rock arrangement with circling motifs and gradually changing harmonic colors.", "psychedelic rock"],
    ["Progressive rock", "Use a progressive rock arrangement with contrasting sections and asymmetrical rhythmic groupings.", "progressive rock"],
    ["Shoegaze", "Use a shoegaze arrangement with layered harmonic motion and blurred melodic boundaries.", "shoegaze"],
    ["Math rock", "Use a math rock arrangement with irregular accents and abrupt stops between tightly repeated figures.", "math rock"],
    ["Bluegrass", "Use a bluegrass arrangement with rapid interlocking melodic figures and a strong acoustic pulse.", "bluegrass"],
    ["Delta blues", "Use a Delta blues arrangement with repeated call-and-response phrases and an earthy relaxed pulse.", "delta blues"],
    ["Chicago blues", "Use a Chicago blues arrangement with a firm shuffle and strongly shaped answering phrases.", "chicago blues"],
    ["Ragtime", "Use a ragtime arrangement with a syncopated upper melody against a regular alternating bass.", "ragtime"],
    ["New Orleans jazz", "Use a New Orleans jazz arrangement with collective melodic responses and a buoyant two-beat feel.", "new orleans jazz"],
    ["Bebop", "Use a bebop arrangement with agile melodic lines and rapid harmonic responses.", "bebop"],
    ["Modal jazz", "Use a modal jazz arrangement with spacious melodic exploration over a sustained tonal center.", "modal jazz"],
    ["Plainchant", "Use a plainchant-inspired melody with unison voices and flexible phrasing without a drum groove.", "plainchant"],
    ["Renaissance choral", "Use Renaissance-inspired choral writing with overlapping melodic entries and balanced contrapuntal phrases.", "renaissance choral"],
    ["Baroque chamber", "Use a Baroque chamber arrangement with sequential melodic figures and active contrapuntal movement.", "baroque chamber"],
    ["Classical chamber", "Use a Classical-era chamber arrangement with balanced question-and-answer phrases and clear cadences.", "classical chamber"],
    ["Romantic era", "Use a Romantic arrangement with expressive melodic shaping and broad harmonic movement.", "romantic era"],
    ["Impressionist", "Use an impressionist arrangement with floating harmonic colors and gently shifting melodic fragments.", "impressionist"],
    ["Son cubano", "Use a son cubano-inspired arrangement with interlocking syncopated phrases and a clear cyclical groove.", "son cubano"],
    ["Highlife-inspired", "Use a highlife-inspired arrangement with bright interlocking melodic patterns and a buoyant dance pulse.", "highlife-inspired"],
    ["Mande-inspired", "Use a Mande-inspired arrangement with cyclical interlocking phrases and ornamented melodic variation.", "mande-inspired"],
    ["Arabic taqsim-inspired", "Use an Arabic taqsim-inspired arrangement with free-sounding melodic exploration and carefully shaped ornaments.", "arabic taqsim-inspired"],
    ["Hindustani-inspired", "Use a Hindustani-inspired arrangement with sustained tonal focus and ornamented cyclical melodic development.", "hindustani-inspired"],
    ["Qawwali-inspired", "Use qawwali-inspired call-and-response phrases that build through repeated rhythmic cycles and emphatic group responses.", "qawwali-inspired"],
    ["Chinese traditional-inspired", "Use a Chinese traditional-inspired arrangement with pentatonic melodic turns and delicately balanced answering phrases.", "chinese traditional-inspired"],
    ["Japanese koto-inspired", "Use a Japanese koto-inspired arrangement with spacious plucked phrases and expressive pauses around the melodic line.", "japanese koto-inspired"],
    ["Gamelan-inspired", "Use a gamelan-inspired arrangement with interlocking cyclical patterns and clear punctuating phrase endings.", "gamelan-inspired"],
    ["Celtic jig-inspired", "Use a Celtic jig arrangement with a lilting compound pulse and lively repeated melodic turns.", "celtic jig-inspired"],
    ["Flamenco-inspired", "Use a flamenco-inspired arrangement with sharply shaped accents and expressive melodic tension.", "flamenco-inspired"],
    ["Balkan brass-inspired", "Use a Balkan brass-inspired arrangement with asymmetrical rhythmic groupings and rapid ornamented phrases.", "balkan brass-inspired"],
  ]},
  {name: "Mood", options: [
    ["Warm", "Create a warm mood with rounded timbres and gentle phrasing that feels intimate and welcoming.", "warm"],
    ["Dreamy", "Create a dreamy atmosphere with soft attacks and lingering notes over spacious harmonies.", "dreamy"],
    ["Energetic", "Keep the mood energetic with decisive attacks and strong accents that sustain forward movement.", "energetic"],
    ["Melancholic", "Create a melancholic mood with restrained dynamics and wistful melodic phrases over unresolved harmonies.", "melancholic"],
    ["Uplifting", "Create an uplifting mood with rising melodic shapes and open harmonies that build toward a hopeful release.", "uplifting"],
    ["Dark", "Create a dark mood with weighty textures and tense harmonies that keep the atmosphere uneasy.", "dark"],
    ["Playful", "Create a playful mood with light articulation and surprising rhythmic turns that keep the phrases lively.", "playful"],
    ["Romantic", "Create a romantic mood with tender phrasing and flowing melodies that linger over warm harmonies.", "romantic"],
    ["Calm", "Keep the mood calm with gentle dynamics and smooth phrases that leave space between musical gestures.", "calm"],
    ["Epic", "Create an epic mood with broad melodic statements and layered crescendos that build toward a strong climax.", "epic"],
  ]},
  {name: "Instruments", options: [
    ["Piano", "Feature an acoustic piano with clear hammer attacks and resonant chords supporting expressive melodic lines.", "piano"],
    ["Acoustic guitar", "Feature clear acoustic guitar picking and strumming with audible string texture and natural resonance.", "acoustic guitar"],
    ["Electric guitar", "Feature an electric guitar with articulate riffs and sustained notes that shape the main melodic voice.", "electric guitar"],
    ["Strings", "Feature bowed strings with sustained ensemble lines and expressive swells that connect the musical phrases.", "strings"],
    ["Synthesizers", "Feature synthesizers with shaped electronic tones and evolving layers that carry the melody and harmonic texture.", "synthesizers"],
    ["Bass", "Feature a prominent bass line with clearly defined low notes that connect the rhythm and harmony.", "bass"],
    ["Drums", "Feature a detailed drum part with a clear kick and snare pattern and fills that mark phrase changes.", "drums"],
    ["Saxophone", "Feature a saxophone with breath-shaped phrases and a rounded tone that carries the main melody.", "saxophone"],
    ["Flute", "Feature a flute with airy sustained notes and light melodic runs above the accompaniment.", "flute"],
    ["Brass", "Feature a brass section with bright chord accents and strong melodic calls that answer the main theme.", "brass"],
    ["Organ", "Feature an organ with sustained chords and a rich resonant tone that supports the groove.", "organ"],
    ["Harp", "Feature a harp with clear plucked notes and flowing arpeggios that ring into the surrounding harmony.", "harp"],
  ]},
  {name: "Vocals", options: [
    ["Female vocals", "Use a female lead vocal with clear words and expressive phrasing that follows the supplied lyrics.", "female vocals"],
    ["Male vocals", "Use a male lead vocal with clear words and expressive phrasing that follows the supplied lyrics.", "male vocals"],
    ["Duet", "Use two contrasting lead voices that alternate phrases and join in harmony while singing the supplied lyrics.", "duet"],
    ["Choir", "Use a choir singing the supplied lyrics in blended harmonies with coordinated entrances and clear phrase endings.", "choir"],
    ["Falsetto", "Use a light falsetto vocal register with controlled breath and smooth transitions through the supplied lyrics.", "falsetto"],
    ["Whispered", "Deliver the supplied lyrics in a close whispered vocal with soft consonants and audible breath.", "whispered vocals"],
    ["Rap", "Deliver the supplied lyrics as rhythmic rap with clear consonants and precise placement against the beat.", "rap"],
    ["Wordless vocals", "Use wordless vocal sounds as a melodic instrument with sustained vowels and no intelligible words.", "wordless vocals"],
  ]},
  {name: "Tempo", options: [
    ["Slow", "Keep a slow tempo with a spacious pulse and enough time for each phrase to breathe.", "slow tempo"],
    ["Mid-tempo", "Keep a moderate tempo with an even pulse that supports a comfortable head-nodding groove.", "mid-tempo"],
    ["Upbeat", "Use a brisk tempo with a buoyant pulse that keeps the arrangement moving lightly forward.", "upbeat"],
    ["Driving", "Maintain a driving rhythmic pulse with persistent accented patterns that propel the music forward.", "driving rhythm"],
    ["Half-time", "Create a half-time feel by spacing the main backbeat across a slower pulse while the underlying subdivisions continue.", "half-time"],
    ["Waltz", "Use a waltz rhythm in triple meter with a clear strong first beat followed by two lighter beats.", "waltz"],
  ]},
  {name: "Production", options: [
    ["1960s", "Use 1960s production with a compact stereo image and warm saturation while keeping the main melody clearly forward.", "1960s production"],
    ["1970s", "Use 1970s production with warm analog color and natural room ambience while preserving separation between musical parts.", "1970s production"],
    ["1980s", "Use 1980s production with a wide polished stereo image and pronounced reverberation around sharply defined rhythmic accents.", "1980s production"],
    ["1990s", "Use 1990s production with a full midrange and controlled ambience that keeps each part distinct in the mix.", "1990s production"],
    ["Modern", "Use modern production with a balanced mix and controlled low frequencies that preserve detail across the stereo field.", "modern production"],
    ["Tape", "Apply gentle tape saturation with softened transients and subtle harmonic color while keeping the mix clear.", "tape saturation"],
  ]},
  {name: "Language", options: [
    ["English", "Sing the supplied lyrics in English with clear consonants and natural stress across each musical phrase.", "english lyrics"],
    ["Mandarin", "Sing the supplied lyrics in Mandarin with clear syllables and natural phrasing that preserves the words.", "mandarin lyrics"],
    ["Cantonese", "Sing the supplied lyrics in Cantonese with clear syllables and natural phrasing that preserves the words.", "cantonese lyrics"],
    ["Japanese", "Sing the supplied lyrics in Japanese with clear vowel sounds and natural phrasing across each musical line.", "japanese lyrics"],
    ["Korean", "Sing the supplied lyrics in Korean with clear syllable endings and natural phrasing across each musical line.", "korean lyrics"],
    ["Spanish", "Sing the supplied lyrics in Spanish with clear vowels and natural stress across each musical phrase.", "spanish lyrics"],
    ["French", "Sing the supplied lyrics in French with clear vowel shaping and natural phrasing across each musical line.", "french lyrics"],
  ]},
];

const MUSIC_STYLE_ROWS = MUSIC_STYLE_ROWS_EN.map(row => ({
  name: t('music.row.' + STYLE_ROW_SLUGS[row.name]),
  options: row.options.map(([label, sentence, legacy]) => [
    t('music.' + STYLE_ROW_SLUGS[row.name] + '.' + presetSlug(legacy)), sentence, legacy,
  ]),
}));
const GENRE_LABELS = new Map(MUSIC_STYLE_ROWS_EN[0].options.map(([label, , legacy]) => [
  label, t('music.genre.' + presetSlug(legacy)),
]));
const GENRE_GROUP_KEYS = {
  Popular: 'music.genre_group.popular',
  Rock: 'music.genre.rock',
  Electronic: 'music.genre.electronic',
  'Soul and roots': 'music.genre_group.soul_and_roots',
  'Jazz and blues': 'music.genre_group.jazz_and_blues',
  'Latin and Caribbean': 'music.genre_group.latin_and_caribbean',
  'Classical and historical': 'music.genre_group.classical_and_historical',
  'Regional inspirations': 'music.genre_group.regional_inspirations',
};

const MUSIC_GENRE_GROUPS = [
  [
    "Popular",
    [
      "Pop",
      "Hip hop",
      "R&B",
      "Country"
    ]
  ],
  [
    "Rock",
    [
      "Rock",
      "Metal",
      "Heavy metal",
      "Punk rock",
      "Psychedelic rock",
      "Progressive rock",
      "Shoegaze",
      "Math rock"
    ]
  ],
  [
    "Electronic",
    [
      "Electronic",
      "House",
      "Techno",
      "Lo-fi",
      "Ambient",
      "Drum and bass",
      "Trance",
      "Dubstep"
    ]
  ],
  [
    "Soul and roots",
    [
      "Folk",
      "Funk",
      "Neo-soul",
      "Gospel",
      "Motown soul",
      "Bluegrass"
    ]
  ],
  [
    "Jazz and blues",
    [
      "Jazz",
      "Delta blues",
      "Chicago blues",
      "Ragtime",
      "New Orleans jazz",
      "Bebop",
      "Modal jazz"
    ]
  ],
  [
    "Latin and Caribbean",
    [
      "Latin",
      "Reggae",
      "Bossa nova",
      "Salsa",
      "Samba",
      "Tango",
      "Son cubano"
    ]
  ],
  [
    "Classical and historical",
    [
      "Classical",
      "Plainchant",
      "Renaissance choral",
      "Baroque chamber",
      "Classical chamber",
      "Romantic era",
      "Impressionist"
    ]
  ],
  [
    "Regional inspirations",
    [
      "Afrobeat-inspired",
      "Highlife-inspired",
      "Mande-inspired",
      "Arabic taqsim-inspired",
      "Hindustani-inspired",
      "Qawwali-inspired",
      "Chinese traditional-inspired",
      "Japanese koto-inspired",
      "Gamelan-inspired",
      "Celtic jig-inspired",
      "Flamenco-inspired",
      "Balkan brass-inspired"
    ]
  ]
];

function musicModelName(name) { return String(name || '').replace(/\s*\(MLX Q8\)\s*$/i, '').trim(); }

function recordPlayer() {
  return `<div class="music-turntable" aria-hidden="true">
    <div class="music-record"><span>♪</span></div>
    <span class="music-tonearm"><i></i></span>
    <span class="music-power"></span><span class="music-rpm">33⅓ RPM</span>
  </div>`;
}

class MusicStudio extends HTMLElement {
  constructor() {
    super();
    this.songs = [];
    this.pending = false;
    this.stopping = false;
    this.operation = null;
    this.epoch = 0;
    this.storageQueue = Promise.resolve();
    this.coverImports = new Set();
    this.coverFailures = new Map();
    this.clearedInputs = null;
    this.restoreOnStop = false;
    this.engraving = false;
    this.engravePending = false;
    this.engraveTimer = null;
    this.abcReturnFocus = true;
    this.detailsSheet = null;
    this.detailsQuiet = false;
    this.detailsBodies = new Map();
    this.capture = null;
    this.referencePlayer = null;
    this.recording = false;
    this.recordingPending = false;
    this.recordingText = '';
    this.recordingActive = 0;
  }
  connectedCallback() {
    if (this.ready) return;
    this.ready = true;
    this.innerHTML = `<div class="music-studio-shell"><section class="music-preview-area stage" aria-label="${t('music.preview.label')}">
      <div class="music-preview-pane">
      <div class="music-generation" hidden role="status" aria-live="polite">
        ${recordPlayer()}
        <strong class="music-generation-label">${t('music.generation.generating')}</strong>
        <div class="music-timeline music-generation-timeline">
          <input type="range" min="0" max="100" step="1" value="0" disabled aria-label="${t('music.generation.progress')}">
          <div class="music-times num"><span class="music-generation-elapsed">0:00</span><span class="music-generation-percent"></span></div>
        </div>
        <span class="music-generation-detail"></span>
      </div>
      <div class="music-empty video-empty empty">
        <div class="video-empty-mark">MUSIC</div>
        <strong>${t('music.empty.title')}</strong>
        <span id="music-empty-hint">${t('music.empty.hint')}</span>
        <button type="button" class="btn" id="music-write">
          <svg class="icon" aria-hidden="true"><use href="#i-text"/></svg><span>${t('music.empty.action')}</span></button>
      </div>
      <div class="music-songs"></div></div><div class="music-output-bars"></div></section>
      <section class="music-gallery strip-wrap" aria-label="${t('music.gallery.label')}" hidden>
        <div class="strip-head"><span class="music-count">${plural(0, t('music.shelf.songs'))}</span><gallery-browser workspace="music"></gallery-browser>
          <button type="button" class="text-btn music-background-pause" aria-label="${t('music.audio.pause_label')}" hidden>${t('music.audio.pause')}</button>
          <span class="strip-actions">
            <button type="button" class="text-btn" id="music-download-all">${t('music.gallery.download_all')}</button>
            <button type="button" class="text-btn" id="music-clear-all">${t('music.gallery.clear_all')}</button>
          </span></div>
        <div class="strip music-strip" role="group" aria-label="${t('music.strip.label')}"></div>
      </section></div>`;
    this.controls = document.getElementById('music-controls');
    this.controls.innerHTML = `<div class="modes" role="radiogroup" aria-label="${t('music.mode.label')}">
        <input type="radio" name="music-workflow" id="music-mode-generate" value="generate" checked>
        <label for="music-mode-generate"><svg class="icon" aria-hidden="true"><use href="#i-sparkle"/></svg>${t('music.mode.generate')}</label>
        <input type="radio" name="music-workflow" id="music-mode-plan" value="plan">
        <label for="music-mode-plan"><svg class="icon" aria-hidden="true"><use href="#i-layout"/></svg>${t('music.mode.compose')}</label>
      </div>
      <input type="hidden" id="music-mode" value="generate">
      <section class="music-generation-fields field prompt-field">
        <div class="field-head"><label for="music-style">${t('music.field.style')}</label></div>
        <textarea id="music-style" rows="4" placeholder="${t('music.style.placeholder')}" required></textarea>
      </section>
      <section class="music-reference-fields field">
        <div class="field-head"><label for="music-reference">${t('music.field.reference')}</label>
          <span class="music-reference-actions">
            <button type="button" class="text-btn" id="music-reference-record">${t('music.reference.record')}</button>
            <button type="button" class="text-btn" id="music-reference-replace" hidden>${t('music.common.replace')}</button></span></div>
        <input id="music-reference" type="file" hidden accept="audio/*,.wav,.mp3,.flac,.m4a,.ogg,.aiff,.aif">
        <div class="music-reference-drop" id="music-reference-drop">
          <button type="button" class="refs" id="music-reference-choose" aria-label="${t('music.reference.add')}">
            <span class="refs-empty"><svg class="icon" aria-hidden="true"><use href="#i-music"/></svg>
              <span><strong>${t('music.reference.add')}</strong><span id="music-reference-note"></span></span></span></button>
          <div class="music-reference-preview video-audios" hidden>
            <div class="video-audio"><div class="video-audio-picture">
              <button type="button" class="video-audio-badge music-reference-play" id="music-reference-play"
                aria-label="${t('audio.preview.play')}" title="${t('audio.preview.play')}">
                <svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M9 5l11 7-11 7z"></path></svg></button>
              <button type="button" class="video-audio-remove" id="music-reference-remove" aria-label="${t('music.reference.remove_label')}">
                <svg class="icon" aria-hidden="true"><use href="#i-x"/></svg></button>
            </div><span class="video-audio-name" id="music-reference-name"></span></div>
          </div>
        </div>
        <p class="caption music-recording-status" id="music-recording-status" hidden></p>
          <div class="music-reference-scope field"><div class="field-head"><label for="music-transcription-task">${t('music.field.keep')}</label></div>
            <select id="music-transcription-task"><option value="melody-full">${t('music.keep.melody_full')}</option><option value="melody-vocal">${t('music.keep.melody_vocal')}</option><option value="full">${t('music.planning.full')}</option></select></div>
      </section>
      <section class="music-generation-fields field prompt-field">
        <div class="music-lyrics-fields field"><div class="field-head"><label for="music-lyrics">${t('music.field.lyrics')}</label></div>
          <textarea id="music-lyrics" rows="6" placeholder="${t('music.lyrics.placeholder')}"></textarea>
          <span class="caption">${t('music.lyrics.hint')}</span>
          <details class="music-tag-guide"><summary>${t('music.lyrics.tags')}</summary>
            <ul class="caption music-lyrics-tags">
              <li><button type="button" class="text-btn music-section-tag" data-music-section="[Intro]">[Intro]</button> ${t('music.tags.intro')}</li>
              <li><button type="button" class="text-btn music-section-tag" data-music-section="[Verse]">[Verse]</button> ${t('music.tags.verse')}</li>
              <li><button type="button" class="text-btn music-section-tag" data-music-section="[Pre-Chorus]">[Pre-Chorus]</button> ${t('music.tags.pre_chorus')}</li>
              <li><button type="button" class="text-btn music-section-tag" data-music-section="[Chorus]">[Chorus]</button> ${t('music.tags.chorus')}</li>
              <li><button type="button" class="text-btn music-section-tag" data-music-section="[Bridge]">[Bridge]</button> ${t('music.tags.bridge')}</li>
              <li><button type="button" class="text-btn music-section-tag" data-music-section="[Instrumental]">[Instrumental]</button> ${t('music.tags.instrumental')}</li>
              <li><button type="button" class="text-btn music-section-tag" data-music-section="[Outro]">[Outro]</button> ${t('music.tags.outro')}</li>
            </ul>
          </details></div>
      </section>
      <details id="music-genre-presets"><summary><span class="music-style-label">${t('music.row.genre')}</span><span class="values look-pick">${t('music.common.none')}</span></summary>
        <div class="music-genre-groups">${MUSIC_GENRE_GROUPS.map(([family, labels]) => `<section class="music-genre-family"><h3>${t(GENRE_GROUP_KEYS[family] || family)}</h3><div class="look-chips">${labels.map(label => { const translated = GENRE_LABELS.get(label) || label; return `<button type="button" class="chip" data-music-genre="${translated}" aria-pressed="false">${translated}</button>`; }).join('')}</div></section>`).join('')}</div>
        <p class="look-note">${t('music.genre.note')}</p>
      </details>
      <details id="music-style-presets"><summary><span class="music-style-label">${t('music.style.presets')}</span> <look-values class="values" data-form="music"></look-values></summary>
        <look-rows class="look" data-form="music"></look-rows>
        <p class="look-note">${t('music.style.note')}</p>
      </details>
      <details class="music-advanced-fields"><summary>${t('music.advanced.title')} <span class="values num" id="music-advanced-values"></span></summary>
        <div class="advanced">
          <div class="field"><div class="field-head"><label for="music-seed">${t('music.field.seed')}</label></div>
            <input id="music-seed" type="number" min="0" max="4294967295" step="1" placeholder="${t('music.seed.random')}">
            <span class="caption">${t('music.seed.hint')}</span></div>
          <div class="field music-composition-fields"><div class="field-head"><label for="music-cot">${t('music.field.planning')}</label></div>
              <select id="music-cot"><option value="full">${t('music.planning.full')}</option><option value="melody">${t('music.planning.melody')}</option><option value="off">${t('music.planning.off')}</option></select>
              <span class="caption">${t('music.planning.hint')}</span></div>
          <div class="field music-composition-fields"><div class="field-head"><span class="label" id="music-abc-label">${t('music.score.label')}</span>
              <button type="button" class="text-btn" id="music-abc-edit">${t('music.score.add')}</button></div>
              <pre class="music-abc-preview is-empty" id="music-abc-preview" aria-labelledby="music-abc-label">${t('music.score.empty')}</pre>
              <span class="caption">${t('music.score.hint')}</span></div>
          <div class="field music-synthesis-fields music-sound-fields"><div class="field-head"><label for="music-steps">${t('music.field.steps')}</label></div>
              <select id="music-steps"><option value="32">${t('music.steps.standard')}</option><option value="16">${t('music.steps.balanced')}</option><option value="8">${t('music.steps.fast')}</option></select>
              <span class="caption">${t('music.steps.hint')}</span></div>
          <div class="field music-synthesis-fields music-sound-fields"><div class="field-head"><label for="music-cfg-scale">${t('music.field.cfg')}</label></div>
              <input id="music-cfg-scale" type="number" min="0" max="5" step="0.1" value="1">
              <span class="caption">${t('music.cfg.hint')}</span></div>
          <div class="field music-synthesis-fields"><div class="field-head"><label for="music-count">${t('music.field.count')}</label></div>
              <select id="music-count"><option value="1">1</option><option value="2">2</option><option value="4">4</option><option value="8">8</option><option value="16">16</option></select>
              <span class="caption">${t('music.count.hint')}</span></div>
        </div>
      </details>
      <dialog class="music-abc-dialog" id="music-abc-dialog" aria-labelledby="music-abc-dialog-title">
        <div class="music-abc-dialog-head"><h2 id="music-abc-dialog-title">${t('music.score.label')}</h2>
          <button type="button" class="icon-btn close" id="music-abc-close" aria-label="${t('music.score.close_label')}">
            <svg class="icon" aria-hidden="true"><use href="#i-x"/></svg></button></div>
        <div class="music-abc-editor">
          <textarea id="music-abc" rows="14" spellcheck="false" aria-labelledby="music-abc-dialog-title"></textarea>
          <div class="music-abc-sheet">
            <div class="music-abc-notation" id="music-abc-notation" role="region" aria-label="${t('music.score.preview_label')}" tabindex="0"></div>
            <p class="music-abc-facts" id="music-abc-facts" hidden></p>
            <p class="music-note" id="music-abc-status" aria-live="polite"></p>
          </div>
        </div>
      </dialog>
      <p class="music-note" id="music-loading-note" hidden></p>`;
    configureLookRows({form: 'music', fields: [], scope: () => this.controls,
      mode: () => this.controls.querySelector('#music-mode').value,
      rows: () => MUSIC_STYLE_ROWS.slice(1), picks: () => this.stylePicks(),
      labels: () => {
        const labels = Object.entries(this.stylePicks()).filter(([name]) => name !== MUSIC_STYLE_ROWS[0].name).flatMap(([, labels]) => labels);
        return labels.length > 2 ? [plural(labels.length, t('music.style.count'))] : labels;
      }, text: () => '', avoids: () => '',
      pick: (row, label) => this.pickStyle(row, label)});
    const footer = document.getElementById('music-footer');
    footer.innerHTML = `<button type="button" id="music-generate" class="run-button" data-state="idle">
      <run-button id="music-run-labels" data-mode="generate" data-state="idle"></run-button>
      <span class="sub num" id="music-go-sub"></span></button>`;
    this.generateButton = footer.querySelector('button');
    this.generateButton.addEventListener('click', () => this.ownOperation ? this.cancel() : this.generate());
    this.querySelector('#music-write').addEventListener('click', () => {
      const target = (EMPTY_COPY[this.draft().mode] || EMPTY_COPY.generate)[2];
      if (target === 'task') this.controls.querySelector('#music-transcription-task').focus();
      else this.controls.querySelector('#music-style').focus();
    });
    this.controls.addEventListener('input', event => {
      if (event.target.matches('input[name="music-workflow"]')) this.syncEngineMode();
      this.epoch++;
      this.sync();
      if (this.keeping) this.store(() => saveMusicDraft(this.savedDraft())).catch(() => {});
    });
    const abcDialog = this.controls.querySelector('#music-abc-dialog');
    this.controls.querySelector('#music-abc-edit').addEventListener('click', () => this.openAbcEditor());
    this.controls.querySelector('#music-abc-close').addEventListener('click', () => this.closeAbcEditor());
    this.controls.querySelector('#music-abc-notation').addEventListener('keydown', event => this.scrollScore(event));
    this.controls.querySelector('#music-abc').addEventListener('input', () => {
      if (abcDialog.open) this.scheduleEngraving();
    });
    abcDialog.addEventListener('close', () => {
      if (!this.abcReturnFocus || this.hidden || this.busy) return;
      // The browser restores focus to the element that opened the dialog after this event,
      // so the panel's own Edit button has to wait its turn.
      setTimeout(() => this.controls.querySelector('#music-abc-edit').focus(), 0);
    });
    abcDialog.addEventListener('click', event => {
      if (event.target !== abcDialog) return;
      const rect = abcDialog.getBoundingClientRect();
      if (event.clientX < rect.left || event.clientX > rect.right
        || event.clientY < rect.top || event.clientY > rect.bottom) this.closeAbcEditor();
    });
    this.controls.querySelector('#music-genre-presets').addEventListener('click', event => {
      const button = event.target.closest('[data-music-genre]');
      if (!button) return;
      this.pickStyle(MUSIC_STYLE_ROWS[0], button.dataset.musicGenre);
      const section = this.controls.querySelector('#music-genre-presets');
      section.open = false;
      section.querySelector('summary').focus();
    });
    this.controls.querySelector('.music-tag-guide').addEventListener('click', event => {
      const button = event.target.closest('[data-music-section]');
      if (button) this.insertSectionTag(button.dataset.musicSection);
    });
    const referenceInput = this.controls.querySelector('#music-reference');
    for (const id of ['music-reference-choose', 'music-reference-replace']) this.controls.querySelector('#' + id).addEventListener('click', () => referenceInput.click());
    referenceInput.addEventListener('change', () => { if (referenceInput.files[0]) this.setReference(referenceInput.files[0]); });
    this.controls.querySelector('#music-reference-remove').addEventListener('click', () => this.setReference(null));
    this.controls.querySelector('#music-reference-record').addEventListener('click', () => this.toggleRecording());
    this.controls.querySelector('#music-reference-play').addEventListener('click', () => this.toggleReferencePlayback());
    const drop = this.controls.querySelector('#music-reference-drop');
    drop.addEventListener('dragover', event => { if (!this.busy) { event.preventDefault(); drop.classList.add('dragover'); } });
    drop.addEventListener('dragleave', () => drop.classList.remove('dragover'));
    drop.addEventListener('drop', event => {
      event.preventDefault(); drop.classList.remove('dragover');
      if (!this.busy && event.dataTransfer.files[0]) this.setReference(event.dataTransfer.files[0]);
    });
    this.querySelector('.music-background-pause').addEventListener('click', () => this.pausePlayback());
    this.querySelector('#music-download-all').addEventListener('click', () => this.downloadSongs(this.songs.map(song => song.id)));
    this.querySelector('#music-clear-all').addEventListener('click', () => this.clearAllSongs());
    window.addEventListener('pagehide', () => this.pausePlayback());
    window.addEventListener('keydown', event => {
      if (this.hidden || !event.altKey || event.code !== 'KeyC' || event.target.closest?.('input, textarea, select, [contenteditable]')) return;
      const song = this.songs.find(item => item.id === this.selectedId);
      if (song && !this.busy) { event.preventDefault(); this.generateCover(song); }
    });
    this.querySelector('.music-strip').addEventListener('keydown', event => {
      const buttons = [...this.querySelectorAll('.music-strip button')];
      const index = buttons.indexOf(event.target);
      if (index < 0) return;
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1
        : event.key === 'ArrowRight' ? Math.min(index + 1, buttons.length - 1) : event.key === 'ArrowLeft' ? Math.max(0, index - 1) : null;
      if (next !== null) { event.preventDefault(); buttons[next].click(); buttons[next].focus(); }
    });
    window.addEventListener('storage', event => {
      if (event.key === 'studio-music-changed' && this.keeping) this.restoreSongs();
    });
  }
  get busy() { return this.pending || this.coverStarting || Boolean(this.operation); }
  // The operation this workspace may stop: its own song, or the artwork request it started.
  get ownOperation() {
    const operation = this.operation;
    return operation && (operation.kind === 'music' || this.isCoverOperation(operation)) ? operation : null;
  }
  needsReference() {
    return ['cover', 'transcribe'].includes(this.draft().mode);
  }
  // The two choices are Generate and Compose. A reference recording is the source, so it
  // turns them into a cover and a transcription, the engine's other two modes.
  syncEngineMode() {
    const visible = this.controls.querySelector('input[name="music-workflow"]:checked')?.value || 'generate';
    const withReference = visible === 'plan' ? 'transcribe' : 'cover';
    this.controls.querySelector('#music-mode').value = this.reference ? withReference : visible;
  }
  get takesCount() { return this.songs.length; }
  configure(options) {
    this.options = options;
    this.capabilities = options.capabilities;
    const caps = this.capabilities;
    this.controls.querySelector('#music-style').maxLength = caps.max_style_characters;
    this.controls.querySelector('#music-lyrics').maxLength = caps.max_lyrics_characters;
    this.controls.querySelector('#music-abc').maxLength = caps.max_score_characters;
    this.controls.querySelector('#music-loading-note').textContent = caps.loading_note;
    if (this.keeping === undefined) this.setKeeping(options.keeping());
    this.sync();
  }
  selectWorkflow(mode) {
    const engine = ['generate', 'plan', 'transcribe', 'cover'].includes(mode) ? mode : 'generate';
    const visible = engine === 'plan' || engine === 'transcribe' ? 'plan' : 'generate';
    this.controls.querySelector('#music-mode-' + visible).checked = true;
    this.syncEngineMode();
  }
  insertSectionTag(tag) {
    const lyrics = this.controls.querySelector('#music-lyrics');
    if (this.busy || this.hidden || lyrics.disabled) return;
    const cursor = lyrics.selectionStart ?? lyrics.value.length;
    const before = lyrics.value.slice(0, cursor);
    const insertion = (before && !before.endsWith('\n') ? '\n' : '') + tag + '\n';
    if (lyrics.maxLength > 0 && lyrics.value.length + insertion.length > lyrics.maxLength) {
      this.options.notify('error', t('music.error.lyrics_too_long')); return;
    }
    lyrics.focus();
    lyrics.setRangeText(insertion, cursor, cursor, 'end');
    lyrics.dispatchEvent(new Event('input', {bubbles: true}));
  }
  syncGenre() {
    const selected = this.stylePicks()[MUSIC_STYLE_ROWS[0].name][0];
    const section = this.controls.querySelector('#music-genre-presets');
    const summary = section.querySelector('.look-pick');
    const label = selected || t('music.common.none');
    if (summary.textContent !== label) summary.textContent = label;
    summary.classList.toggle('picked', Boolean(selected));
    section.querySelectorAll('[data-music-genre]').forEach(button => {
      button.setAttribute('aria-pressed', String(button.dataset.musicGenre === selected));
    });
  }
  stylePicks() {
    const phrases = this.controls.querySelector('#music-style').value.split(/[,\n]/).map(phrase => phrase.trim().toLowerCase());
    return Object.fromEntries(MUSIC_STYLE_ROWS.map(row => [row.name, row.options.filter(([, sentence, legacy]) => phrases.includes(sentence.toLowerCase()) || phrases.includes(legacy.toLowerCase())).slice(0, 1).map(([label]) => label)]));
  }
  pickStyle(row, label) {
    row = MUSIC_STYLE_ROWS.find(candidate => candidate.name === row.name);
    if (!row) return;
    if (this.busy || this.hidden || this.controls.querySelector('#music-style').disabled) return;
    const input = this.controls.querySelector('#music-style'), sentence = row.options.find(([name]) => name === label)?.[1];
    if (!sentence) return;
    const parts = input.value.split(/[,\n]/).map(part => part.trim()).filter(Boolean);
    const picked = this.stylePicks()[row.name].includes(label);
    const rowPhrases = new Set(row.options.flatMap(([, sentence, legacy]) => [sentence.toLowerCase(), legacy.toLowerCase()]));
    const remaining = parts.filter(part => !rowPhrases.has(part.toLowerCase()));
    const next = (picked ? remaining : [...remaining, sentence]).join(', ').replace(/\.\s*,\s*/g, '.\n');
    if (input.maxLength > 0 && next.length > input.maxLength) { this.options.notify('error', t('music.error.style_too_long')); return; }
    input.value = next; input.dispatchEvent(new Event('input', {bubbles: true}));
  }
  draft() {
    const values = Object.fromEntries(['mode', 'style', 'lyrics', 'seed', 'cot', 'abc', 'steps', 'cfg-scale', 'count', 'transcription-task']
      .map(key => [key.replaceAll('-', '_'), this.controls.querySelector('#music-' + key).value]));
    return {...values, instrumental: !values.lyrics.trim()};
  }
  // Run empties what it sent, as the Image workspace does: the words, the reference
  // recording and the Advanced settings. A cancelled or failed run puts them back. The
  // reference recording stays: it is the same hum for the next cover or transcription.
  clearInputs() {
    const field = id => this.controls.querySelector('#music-' + id);
    const advanced = ['seed', 'count', 'steps', 'cfg-scale', 'cot', 'abc', 'transcription-task'];
    this.clearedInputs = {
      style: field('style').value,
      lyrics: field('lyrics').value,
      reference: this.reference,
      advanced: Object.fromEntries(advanced.map(id => [id, field(id).value])),
    };
    const defaults = {
      seed: '',
      count: '1',
      steps: String(this.capabilities?.default_steps || 32),
      'cfg-scale': '1',
      cot: this.capabilities?.default_planning || 'full',
      abc: '',
      'transcription-task': 'melody-full',
    };
    field('style').value = '';
    field('lyrics').value = '';
    for (const [id, value] of Object.entries(defaults)) field(id).value = value;
    this.updateReference();
    this.syncEngineMode();
    this.controls.dispatchEvent(new Event('input', {bubbles: true}));
  }
  restoreInputs() {
    const snapshot = this.clearedInputs;
    this.clearedInputs = null;
    this.restoreOnStop = false;
    if (!snapshot) return;
    const field = id => this.controls.querySelector('#music-' + id);
    field('style').value = snapshot.style;
    field('lyrics').value = snapshot.lyrics;
    for (const [id, value] of Object.entries(snapshot.advanced || {})) field(id).value = value;
    this.releaseReferenceAudio();
    this.reference = snapshot.reference || null;
    this.updateReference();
    this.syncEngineMode();
    this.controls.dispatchEvent(new Event('input', {bubbles: true}));
  }
  prepareCancel() { this.restoreOnStop = Boolean(this.clearedInputs); }
  // The shared poll reports a terminal failure from its history, after the active slot
  // emptied. Only this client's run owns the snapshot.
  restoreAfterFailure(operation) {
    if (operation?.client_id !== this.options?.clientId) return;
    this.restoreInputs();
  }
  savedDraft() { return {...this.draft(), reference: this.reference || null}; }
  async setReference(file) {
    if (this.busy) return;
    const limit = this.capabilities?.max_reference_bytes || 32 * 1024 * 1024;
    if (file && (!file.size || file.size > limit)) {
      this.controls.querySelector('#music-reference').value = '';
      this.options.notify('error', t('music.error.file_too_large', {size: Math.round(limit / 1024 / 1024)})); return;
    }
    if (file && file.type && !file.type.startsWith('audio/') && !/\.(wav|mp3|flac|m4a|ogg|aiff?|aac|opus)$/i.test(file.name)) {
      this.controls.querySelector('#music-reference').value = '';
      this.options.notify('error', t('music.error.file_type')); return;
    }
    this.closeScore(false);
    this.releaseReferenceAudio();
    this.reference = file ? {blob: file, name: file.name || 'reference.wav'} : null;
    this.syncEngineMode();
    this.controls.querySelector('#music-reference').value = '';
    this.updateReference(); this.epoch++; this.sync();
    if (this.keeping) await this.store(() => saveMusicDraft(this.savedDraft())).catch(() => {});
  }
  // A hum is short, so the chip plays it back before the run. The player stays off the
  // page: the form holds no media element, and the only URL it reads is the one it made.
  toggleReferencePlayback() {
    if (!this.reference) return;
    if (!this.referencePlayer) {
      this.referencePlayer = new Audio(URL.createObjectURL(this.reference.blob));
      this.referencePlayer.addEventListener('play', () => this.paintReferencePlayback(true));
      this.referencePlayer.addEventListener('pause', () => this.paintReferencePlayback(false));
      this.referencePlayer.addEventListener('ended', () => this.paintReferencePlayback(false));
    }
    if (this.referencePlayer.paused) this.referencePlayer.play().catch(() => this.paintReferencePlayback(false));
    else this.referencePlayer.pause();
  }
  paintReferencePlayback(playing) {
    const button = this.controls?.querySelector('#music-reference-play');
    if (!button) return;
    const text = playing ? t('audio.preview.pause') : t('audio.preview.play');
    button.setAttribute('aria-label', text);
    button.title = text;
    button.querySelector('path')?.setAttribute('d', playing ? 'M9 6v12M15 6v12' : 'M9 5l11 7-11 7z');
  }
  releaseReferenceAudio() {
    if (!this.referencePlayer) return;
    this.referencePlayer.pause();
    URL.revokeObjectURL(this.referencePlayer.src);
    this.referencePlayer = null;
    this.paintReferencePlayback(false);
  }
  updateReference() {
    const attached = Boolean(this.reference);
    const preview = this.controls.querySelector('.music-reference-preview');
    preview.hidden = !attached;
    preview.title = this.reference?.name || '';
    this.controls.querySelector('#music-reference-choose').hidden = attached;
    this.controls.querySelector('#music-reference-replace').hidden = !attached;
    this.controls.querySelector('#music-reference-name').textContent = this.reference?.name || '';
  }
  // The microphone hands back WebM, which the transcription may not read. The Voice
  // workspace normalises its takes the same way, so both reach the engine as WAV.
  async recordReference(file) {
    try {
      const normalized = await normalizeReference(file, 44100, 120);
      await this.setReference(new File([normalized.blob], 'hum-mmm.wav', {type: 'audio/wav'}));
    } catch (error) {
      this.options.notify('error', error.message);
    } finally {
      this.sync();
    }
  }
  toggleRecording() {
    if (this.recording) { this.finishRecording(); return; }
    if (this.recordingPending || this.busy || this.hidden || this.reference) return;
    this.recordingPending = true;
    this.sync();
    this.capture = startRecording({
      maxSeconds: 120,
      onStart: () => {
        this.recording = true;
        this.recordingPending = false;
        this.recordingActive = 0;
        this.recordingText = this.recordingTextFor({active: 0, needed: 7});
        this.sync();
      },
      onTick: values => {
        this.recordingActive = values.active;
        this.recordingText = this.recordingTextFor(values);
        this.paintRecordingStatus();
      },
      onShort: values => this.reportShortTake(values),
      onFinish: file => {
        this.recording = false;
        this.capture = null;
        this.recordReference(file);
      },
      onError: message => {
        this.recording = false;
        this.recordingPending = false;
        this.capture = null;
        this.sync();
        this.options.notify('error', message);
      },
    });
  }
  // The button ends a take and keeps it. Leaving the workspace drops it, so a half-finished
  // hum never lands in the form by surprise.
  finishRecording() { this.capture?.stop(); }
  // The line under the door: the microphone opening, then the seconds of sound the take
  // holds, then that it is long enough. Stop below the minimum asks for a moment more.
  recordingTextFor({active, needed}) {
    return active >= needed
      ? t('record.ready', {needed})
      : t('record.progress', {active: active.toFixed(1), needed});
  }
  paintRecordingStatus() {
    const status = this.controls?.querySelector('#music-recording-status');
    if (!status) return;
    status.hidden = !(this.recording || this.recordingPending);
    status.textContent = this.recordingPending ? t('record.opening') : this.recordingText;
    status.classList.toggle('is-recording', this.recording);
  }
  reportShortTake({active, needed, dropped}) {
    if (!dropped) {
      this.options.notify('info', t('record.keep_going', {remaining: (needed - active).toFixed(1)}));
      return;
    }
    this.recording = false;
    this.recordingPending = false;
    this.capture = null;
    this.recordingText = '';
    this.sync();
    this.options.notify('error', t('record.dropped', {active: active.toFixed(1), needed}));
  }
  stopRecording() {
    if (!this.capture && !this.recording && !this.recordingPending) return;
    this.capture?.cancel();
    this.capture = null;
    this.recording = false;
    this.recordingPending = false;
    this.sync();
  }
  // The item's whole job: the song's score becomes the form's score, and the form shows
  // where it landed. The editor stays behind the form's own Edit score link.
  useScore(song) {
    if (this.busy || !song.score) return;
    closeMenus();
    if (['cover', 'transcribe'].includes(this.draft().mode)) this.selectWorkflow('generate');
    this.controls.querySelector('#music-abc').value = song.score;
    this.controls.querySelector('.music-advanced-fields').open = true;
    this.epoch++; this.sync();
    const field = this.controls.querySelector('#music-abc-preview').closest('.field');
    field?.scrollIntoView({block: 'center', behavior: 'smooth'});
    if (this.keeping) this.store(() => saveMusicDraft(this.savedDraft())).catch(() => {});
  }
  openAbcEditor() {
    if (this.busy || this.hidden || this.needsReference()) return;
    const dialog = this.controls.querySelector('#music-abc-dialog');
    if (!dialog || dialog.open) return;
    this.controls.querySelector('.music-advanced-fields').open = true;
    dialog.showModal();
    this.controls.querySelector('#music-abc').focus();
    this.setAbcFacts(this.controls.querySelector('#music-abc').value);
    this.scheduleEngraving();
  }
  closeAbcEditor(focus = true) {
    const dialog = this.controls.querySelector('#music-abc-dialog');
    if (!dialog?.open) return;
    clearTimeout(this.engraveTimer);
    this.engraveTimer = null;
    this.abcReturnFocus = focus;
    dialog.close();
  }
  // The sheet must follow the text, so this listens to `input` rather than abcjs's own
  // Editor, which binds onkeyup and onchange as element properties and misses a
  // programmatic value set.
  // The sheet draws the key and meter as symbols. This line says them in words.
  setAbcFacts(score) {
    const facts = this.controls.querySelector('#music-abc-facts');
    if (!facts) return;
    const parsed = musicScore(score);
    const meters = [...new Set((String(score || '').match(/^M:\s*(\S+)/gm) || []).map(line => line.replace(/^M:\s*/, '')))];
    const tempo = String(parsed.tempo || '').match(/=\s*(\d+(?:\.\d+)?)/)?.[1];
    const items = [
      [t('music.score.key'), parsed.key],
      [t('music.score.meter'), meters.join(', ')],
      [t('music.score.tempo'), tempo ? tempo + ' BPM' : ''],
    ].filter(([, value]) => value);
    // A label over its value, in columns: three facts read as a table, and each one keeps
    // its own name instead of running into the next when the line is copied out.
    facts.replaceChildren(...items.map(([name, value]) => {
      const pair = document.createElement('div');
      const label = document.createElement('dt'); label.textContent = name;
      const data = document.createElement('dd'); data.textContent = value;
      pair.append(label, data); return pair;
    }));
    facts.hidden = !items.length;
  }
  scheduleEngraving() {
    clearTimeout(this.engraveTimer);
    this.engraveTimer = setTimeout(() => { this.engraveTimer = null; this.engraveAbc(); }, 250);
  }
  engraveDetails(pane, score) {
    if (pane.dataset.engraved === '1') return;
    renderNotation(pane, score).then(() => { pane.dataset.engraved = '1'; }).catch(() => {
      pane.textContent = t('music.error.engraving_source');
    });
  }
  async engraveAbc() {
    const dialog = this.controls.querySelector('#music-abc-dialog');
    const pane = this.controls.querySelector('#music-abc-notation');
    const status = this.controls.querySelector('#music-abc-status');
    if (!dialog?.open) return;
    if (this.engraving) { this.engravePending = true; return; }
    this.engraving = true;
    try {
      do {
        this.engravePending = false;
        const score = this.controls.querySelector('#music-abc').value;
        if (!score.trim()) { pane.replaceChildren(); this.setAbcFacts(''); status.textContent = ''; break; }
        this.setAbcFacts(score);
        status.textContent = '';
        try {
          const warnings = await renderNotation(pane, score);
          status.textContent = warnings ? t('music.error.notation_warning') : '';
        } catch (_) {
          pane.replaceChildren();
          status.textContent = t('music.error.engraving');
        }
      } while (this.engravePending);
    } finally { this.engraving = false; }
  }
  store(action) {
    const pending = this.storageQueue.then(action);
    this.storageQueue = pending.then(value => { this.storageFailure = ''; return value; }, error => {
      if (this.storageFailure !== error.message) this.options?.notify('error', t('music.error.save', {message: error.message}));
      this.storageFailure = error.message;
    });
    return pending;
  }
  setKeeping(on) {
    return this.changeKeeping(on).catch(() => {});
  }
  async changeKeeping(on) {
    if (this.keeping === on) return;
    const first = this.keeping === undefined;
    this.keeping = on;
    const epoch = this.epoch;
    if (!on) { await this.store(clearMusic); return; }
    if (first) {
      try {
        const draft = await musicDraft();
        if (!this.keeping) return;
        if (draft && this.epoch === epoch) {
          for (const [key, value] of Object.entries(draft)) {
            const input = this.controls.querySelector('#music-' + key.replaceAll('_', '-'));
            if (input && input.type !== 'file') { if (input.type === 'checkbox') input.checked = Boolean(value); else input.value = value; }
          }
          if (draft.instrumental) this.controls.querySelector('#music-lyrics').value = '';
          if (draft.reference?.blob instanceof Blob) { this.reference = draft.reference; this.updateReference(); }
          this.selectWorkflow(draft.mode || 'generate');
        }
        await this.restoreSongs();
      } catch (error) { this.options?.notify('error', t('music.error.restore', {message: error.message})); }
    } else {
      await this.store(async () => {
        await saveMusicDraft(this.savedDraft());
        for (const song of this.songs) await saveMusicSong(song);
      });
    }
    this.sync();
  }
  async restoreSongs() {
    const epoch = this.restoreEpoch = (this.restoreEpoch || 0) + 1;
    const saved = await musicSongs();
    if (!this.keeping || epoch !== this.restoreEpoch) return;
    this.songs = saved.sort((a, b) => a.createdAt - b.createdAt);
    if (!this.songs.some(song => song.id === this.selectedId)) this.selectedId = preferredGalleryId('music', this.songs, this.keeping) || this.songs.at(-1)?.id;
    this.renderSongs();
  }
  sync() {
    const draft = this.draft();
    this.controls.querySelectorAll('[data-form=music]').forEach(element => element.requestUpdate?.());
    const transcribe = draft.mode === 'transcribe', coverSong = draft.mode === 'cover';
    const needsReference = transcribe || coverSong, scoreOnly = draft.mode === 'plan';
    this.controls.querySelector('.music-reference-fields').hidden = false;
    this.controls.querySelector('.music-reference-scope').hidden = !this.reference;
    this.controls.querySelectorAll('.music-generation-fields').forEach(section => { section.hidden = transcribe; });
    this.controls.querySelectorAll('.music-composition-fields').forEach(field => { field.hidden = needsReference; });
    this.controls.querySelectorAll('.music-synthesis-fields').forEach(field => { field.hidden = transcribe; });
    this.controls.querySelectorAll('.music-sound-fields').forEach(field => { field.hidden = transcribe || scoreOnly; });
    this.controls.querySelector('#music-style-presets').hidden = transcribe;
    this.controls.querySelector('#music-genre-presets').hidden = transcribe;
    this.syncGenre();
    this.controls.querySelector('#music-style').disabled = transcribe;
    this.controls.querySelector('#music-style').required = !transcribe;
    this.controls.querySelector('#music-lyrics').disabled = transcribe;
    this.controls.querySelectorAll('[data-music-section]').forEach(button => { button.disabled = transcribe || this.busy; });
    this.controls.querySelector('#music-lyrics').required = !transcribe && !draft.instrumental;
    this.controls.querySelector('#music-cot').disabled = needsReference;
    this.controls.querySelector('#music-cot option[value="off"]').disabled = scoreOnly || draft.instrumental;
    if ((scoreOnly || draft.instrumental) && draft.cot === 'off') this.controls.querySelector('#music-cot').value = 'full';
    this.controls.querySelector('#music-abc').disabled = needsReference;
    const abc = this.controls.querySelector('#music-abc').value;
    const abcPreview = this.controls.querySelector('#music-abc-preview');
    abcPreview.textContent = abc.trim() ? abc : t('music.score.empty');
    abcPreview.classList.toggle('is-empty', !abc.trim());
    // A cover or a transcription carries no score, so the door says why it is off
    // instead of returning silently when it is pressed.
    const abcEdit = this.controls.querySelector('#music-abc-edit');
    abcEdit.textContent = abc.trim() ? t('music.score.edit') : t('music.score.add');
    abcEdit.disabled = this.busy || needsReference;
    abcEdit.title = needsReference ? t('music.score.title_reference')
      : this.busy ? t('music.score.title_busy') : '';
    // The door's second line names what this mode does with a recording. It sits inside
    // the door, one line like the Video form's media door, so the field keeps its shape.
    this.controls.querySelector('#music-reference-note').textContent = transcribe
      ? t('music.reference.note_transcribe')
      : coverSong ? t('music.reference.note_cover')
        : draft.mode === 'plan' ? t('music.reference.note_plan')
          : t('music.reference.note_generate');
    const record = this.controls.querySelector('#music-reference-record');
    record.hidden = Boolean(this.reference);
    record.textContent = this.recording ? t('music.common.stop') : this.recordingPending ? t('music.reference.opening') : t('music.reference.record');
    record.disabled = this.busy || this.recordingPending;
    record.title = this.recording ? t('music.reference.title_stop')
      : this.busy ? t('music.reference.title_busy') : t('music.reference.title_idle');
    this.paintRecordingStatus();
    if ((this.busy || this.hidden || needsReference) && this.controls.querySelector('#music-abc-dialog').open) {
      this.closeAbcEditor(false);
    }
    for (const key of ['steps', 'cfg-scale']) this.controls.querySelector('#music-' + key).disabled = transcribe || scoreOnly;
    this.controls.querySelector('#music-count').disabled = transcribe;
    this.controls.querySelector('#music-seed').disabled = transcribe;
    const [hint, action, target] = EMPTY_COPY[draft.mode] || EMPTY_COPY.generate;
    this.querySelector('#music-empty-hint').textContent = hint;
    this.querySelector('#music-write span').textContent = action;
    this.querySelector('#music-write use').setAttribute('href', target === 'task' ? '#i-layout' : '#i-text');
    const seed = this.controls.querySelector('#music-seed').value.trim();
    this.controls.querySelector('#music-advanced-values').textContent = [
      transcribe || scoreOnly ? t('music.summary.score_only') : t('music.summary.steps', {count: draft.steps}),
      transcribe || scoreOnly ? null : t('music.summary.guidance', {value: draft.cfg_scale}),
      seed ? t('music.summary.seed', {value: seed}) : t('music.summary.random_seed'),
    ].filter(Boolean).join(', ');
    const ready = !this.recording && !this.recordingPending
      && (transcribe ? Boolean(this.reference) : draft.style.trim() && (draft.instrumental || draft.lyrics.trim()) && (!needsReference || this.reference));
    this.controls.disabled = this.busy || this.hidden;
    this.querySelectorAll('[data-music-send]').forEach(button => { button.disabled = this.busy || button.dataset.stub === 'true' || button.dataset.scoreOnly === 'true'; });
    this.querySelectorAll('[data-music-reuse]').forEach(button => { button.disabled = this.busy; });
    // A control that cannot act is off and says why, rather than taking the press
    // and returning in silence.
    this.querySelectorAll('[data-music-score]').forEach(button => {
      button.disabled = this.busy;
      button.title = this.busy ? t('music.score.title_busy') : t('music.score.copy_title');
    });
    this.querySelectorAll('[data-music-more]').forEach(button => {
      button.disabled = this.busy;
      button.setAttribute('aria-disabled', String(this.busy));
      button.title = this.busy ? t('music.actions.title_busy') : t('music.actions.more');
    });
    const downloadAll = this.querySelector('#music-download-all');
    const clearAll = this.querySelector('#music-clear-all');
    if (downloadAll) downloadAll.disabled = !this.songs.length;
    if (clearAll) clearAll.disabled = !this.songs.length || this.busy;
    this.querySelectorAll('[data-music-cover]').forEach(button => { button.disabled = this.busy; });
    this.syncRunButton(draft, ready);
    const generating = this.pending || this.operation?.kind === 'music';
    const previewingGeneration = generating && this.showGeneration !== false;
    this.querySelector('.music-generation').hidden = !previewingGeneration;
    this.querySelector('.music-empty').hidden = this.songs.length > 0 || generating;
    for (const card of this.querySelectorAll('.music-song, .music-output-details')) card.hidden = previewingGeneration || card.dataset.songId !== this.selectedId;
    if (previewingGeneration || this.hidden) { this.closeDetails(false); this.closeScore(false); }
    const scores = this.songs.filter(song => !song.blob).length, recordings = this.songs.length - scores;
    // The head names what the shelf holds, and what happens to it, the way the Image strip
    // does. It is the first child, so the shared head rule sets it at the left edge.
    const songs = plural(recordings, t('music.shelf.songs'));
    const shelf = scores ? t('music.shelf.both', {songs, scores: plural(scores, t('music.shelf.scores'))}) : songs;
    this.querySelector('.music-count').textContent = this.keeping
      ? t('music.shelf.kept', {count: shelf})
      : t('music.shelf.tab', {count: shelf});
    const progress = this.operation?.progress || {};
    this.querySelector('.music-generation-label').textContent = this.operation?.status === 'stopping' ? t('music.generation.stopping')
      : progress.stage === 'preparing' ? t('music.generation.loading') : progress.stage === 'transcribing' ? t('music.generation.transcribing_reference') : (t({plan: 'music.generation.composing', transcribe: 'music.generation.transcribing', cover: 'music.generation.covering'}[this.operation?.mode || draft.mode] || 'music.generation.generating'));
    this.querySelector('.music-generation-detail').textContent = generating
      ? [musicModelName(this.operation?.model || this.capabilities?.name), progress.total > 0 ? t('music.generation.steps', {step: progress.step, total: progress.total}) : progress.step > 0 ? plural(progress.step, t('music.generation.tokens')) : t('music.generation.composing_recording')].filter(Boolean).join(' · ') : '';
    // A run in progress borrows the player's own timeline: the bar fills with the sampler's
    // share, and the line under it reads elapsed and percent instead of position and length.
    const bar = this.querySelector('.music-generation-timeline input');
    const percent = progress.total > 0 ? Math.min(100, Math.round(progress.step / progress.total * 100)) : null;
    bar.value = percent === null ? 0 : percent;
    bar.style.setProperty('--music-progress', (percent === null ? 0 : percent) + '%');
    bar.setAttribute('aria-valuetext', percent === null ? t('music.generation.no_progress') : percent + '%');
    this.querySelector('.music-generation-percent').textContent = percent === null ? '' : percent + '%';
    const started = Number(this.operation?.started_at) || 0;
    const elapsed = started ? Math.max(0, Math.floor(Date.now() / 1000 - started)) : 0;
    this.querySelector('.music-generation-elapsed').textContent =
      Math.floor(elapsed / 60) + ':' + String(elapsed % 60).padStart(2, '0');
    this.syncBackgroundPlayback();
  }
  // The run button is the shared one: Generate while idle, Cancel while this workspace owns
  // the run, and the same Starting and Stopping labels as the Image, Video and Voice forms.
  syncRunButton(draft, ready) {
    if (!this.generateButton) return;
    const own = this.ownOperation;
    const stopping = Boolean(own) && (this.stopping || own.status === 'stopping');
    const starting = Boolean(this.pending || this.coverStarting) && !own;
    const state = stopping ? 'stopping' : starting ? 'starting' : own ? 'busy' : 'idle';
    this.generateButton.dataset.state = state;
    const labels = this.generateButton.querySelector('run-button');
    const sub = this.generateButton.querySelector('.sub');
    if (labels) { labels.dataset.state = state; labels.dataset.mode = 'generate'; }
    this.generateButton.disabled = stopping || (state === 'idle' && (!this.capabilities || !ready || this.busy));
    if (sub) sub.textContent = starting ? t('music.run.preparing')
      : own ? t('music.run.songs_remain')
        : this.recording ? t('music.run.stop_recording_first') : t(MODE_CAPTIONS[draft.mode] || 'music.mode_caption.generate');
  }
  async cancel() {
    const operation = this.ownOperation;
    if (!operation || this.stopping) return;
    this.stopping = true;
    this.sync();
    try {
      const answer = await fetch('/api/v1/operations/' + encodeURIComponent(operation.id) + '/cancel', {method: 'POST'});
      if (!answer.ok) throw new Error((await answer.json()).error || t('music.error.stop_failed'));
      this.prepareCancel();
    } catch (error) { this.stopping = false; this.options.notify('error', error.message); this.sync(); }
  }
  setOperation(operation) {
    if (operation?.kind === 'music' && this.operation?.id !== operation.id) this.showGeneration = true;
    const stopped = !operation && Boolean(this.operation) && this.restoreOnStop;
    this.operation = operation;
    if (!this.ownOperation) this.stopping = false;
    if (stopped) this.restoreInputs();
    this.sync();
    this.syncGallery();
  }
  async generate() {
    if (this.generateButton.disabled || this.busy) return;
    if (this.recording || this.recordingPending) return this.options.notify('info', t('music.error.stop_recording_first'));
    if (!Array.from(this.controls.querySelectorAll('input, textarea, select')).every(input => input.disabled || input.reportValidity())) return;
    const draft = this.draft();
    if (['generate', 'plan'].includes(draft.mode) && draft.abc.trim() && draft.cot === 'off') return this.options.notify('error', t('music.error.planning_for_score'));
    this.pending = true;
    this.showGeneration = true;
    this.sync();
    this.options.onBusyChange();
    try {
      const reference = ['transcribe', 'cover'].includes(draft.mode) && this.reference
        ? {reference_audio: await blobBase64(this.reference.blob), reference_name: this.reference.name} : {};
      const scoreOnly = ['plan', 'transcribe'].includes(draft.mode);
      const payload = {...draft, ...reference, steps: scoreOnly ? 32 : Number(draft.steps), cfg_scale: scoreOnly ? 1 : Number(draft.cfg_scale), count: 1,
        abc: ['generate', 'plan'].includes(draft.mode) ? draft.abc : '',
        cot: ['transcribe', 'cover'].includes(draft.mode) ? (draft.transcription_task === 'full' ? 'full' : 'melody') : draft.cot, instrumental: draft.mode === 'transcribe' ? false : draft.instrumental,
        seed: draft.mode === 'transcribe' || draft.seed === '' ? null : Number(draft.seed), kind: 'music',
        backend: this.capabilities.backend_id, client_id: this.options.clientId, library_id: this.options.libraryId};
      const count = draft.mode === 'transcribe' ? 1 : Number(draft.count);
      if (count > 1) payload.items = Array.from({length: count}, (_, index) => ({seed: payload.seed === null ? null : (payload.seed + index) >>> 0}));
      const answer = await fetch('/music/operations', {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload),
      });
      const operation = await answer.json();
      if (!answer.ok) throw new Error(operation.error || t('music.error.start_failed'));
      this.setOperation(operation);
      this.clearInputs();
      document.dispatchEvent(new CustomEvent('music-submitted'));
    } catch (error) { this.options.notify('error', error.message); }
    finally { this.pending = false; this.sync(); this.options.onBusyChange(); }
  }
  async importOperation(operation, answer) {
    if (operation.batch_total) {
      const manifest = await answer.json();
      for (const item of manifest.items || []) {
        const id = operation.id + ':' + item.index;
        if (this.songs.some(song => song.id === id)) continue;
        const response = await fetch(item.result_url, {cache: 'no-store'});
        if (!response.ok) throw new Error(t('music.error.batch_load'));
        await this.importSong({...operation, ...item, id, result_url: item.result_url, started_at: item.started_at, batch_total: null}, response);
      }
    } else await this.importSong(operation, answer);
  }
  async importSong(operation, answer) {
    if (this.songs.some(song => song.id === operation.id)) return;
    const scoreOnly = (answer.headers.get('content-type') || '').includes('application/json');
    const blob = scoreOnly ? null : await answer.blob();
    const metadataAnswer = await fetch(operation.result_url.replace(/\/result$/, '/metadata'), {cache: 'no-store'});
    if (!metadataAnswer.ok) throw new Error(t('music.error.details_load'));
    const details = await metadataAnswer.json();
    const finished = operation.completed_at || operation.finished_at;
    const generationSeconds = Number.isFinite(operation.started_at) && Number.isFinite(finished) && finished >= operation.started_at
      ? finished - operation.started_at : null;
    let song = {id: operation.id, blob, ...details, title: t('music.common.untitled'), settings: operation.settings,
      model: operation.model, createdAt: finished * 1000, generationSeconds};
    if (this.keeping) {
      song = await this.store(() => saveMusicSong(song));
      if (!song) return;
    }
    if (this.songs.some(item => item.id === song.id)) return;
    this.restoreEpoch = (this.restoreEpoch || 0) + 1;
    this.songs.push(song);
    this.selectedId = song.id;
    this.showGeneration = false;
    this.renderSongs();
    localStorage.setItem('studio-music-changed', String(Date.now()));
  }
  pausePlayback() {
    this.querySelectorAll('audio').forEach(audio => audio.pause());
    this.controls?.querySelectorAll('audio').forEach(audio => audio.pause());
    this.referencePlayer?.pause();
  }
  syncBackgroundPlayback() {
    const control = this.querySelector('.music-background-pause');
    const playing = [...this.querySelectorAll('.music-song audio')].find(audio => !audio.paused && !audio.ended);
    control.hidden = !playing || !playing.closest('.music-song').hidden;
    control.title = playing ? t('music.audio.pause_named', {name: playing.getAttribute('aria-label')}) : '';
    const playingId = playing?.closest('.music-song').dataset.songId || null;
    this.querySelector('gallery-browser').playingId = playingId;
    for (const thumb of this.querySelectorAll('.music-thumb')) {
      const active = thumb.dataset.songId === playingId;
      thumb.classList.toggle('is-playing', active);
      thumb.querySelector('.music-playing-state').hidden = !active;
    }
  }
  selectSong(id) {
    if (!this.songs.some(song => song.id === id)) return;
    this.closeDetails(false);
    this.closeScore(false); this.selectedId = id; this.showGeneration = false;
    rememberGalleryView('music', {selected: id}, this.keeping);
    this.sync(); this.syncGallery();
  }
  syncGallery() {
    const gallery = this.querySelector('gallery-browser');
    gallery.items = this.songs.slice().reverse().map((song, i) => ({id: song.id, number: this.songs.length - i,
      text: this.songTitle(song), description: song.settings?.style || song.settings?.reference_name, model: musicModelName(song.model), seed: song.seed,
      at: song.createdAt, duration: song.seconds, thumbnail: this.coverUrls?.get(song.id), batch: galleryBatch(song.id)}));
    gallery.selectedId = this.selectedId; gallery.keeping = this.keeping;
    gallery.pending = this.pending || this.operation?.kind === 'music';
    gallery.pendingSelected = gallery.pending && this.showGeneration !== false;
    gallery.showPending = () => { this.closeScore(false); this.showGeneration = true; this.sync(); this.syncGallery(); };
    const section = this.querySelector('.music-gallery');
    if (section) section.hidden = !this.songs.length && !gallery.pending;
    const strip = this.querySelector('.music-strip');
    let pending = strip.querySelector('.music-pending-thumb');
    if (gallery.pending && !pending) {
      pending = document.createElement('button'); pending.type = 'button'; pending.className = 'frame music-pending-thumb pending';
      pending.innerHTML = `<span class="still music-thumb-art"><span class="video-pending-indicator"></span><span>${t('music.common.generating')}</span></span><span class="no">NEW</span>`;
      pending.setAttribute('aria-label', t('music.generation.show_label')); pending.addEventListener('click', () => gallery.showPending()); strip.prepend(pending);
    }
    if (!gallery.pending && pending) pending.remove();
    else if (pending) { pending.classList.toggle('selected', gallery.pendingSelected); pending.setAttribute('aria-pressed', String(Boolean(gallery.pendingSelected))); }
    gallery.choose = id => this.selectSong(id);
    gallery.removeItem = id => this.removeSong(id);
    gallery.download = async ids => this.downloadSongs(ids);
    gallery.playback = () => {
      const audio = this.querySelector('.music-song:not([hidden]) audio');
      if (audio) { if (audio.paused) audio.play().catch(error => this.options.notify('error', error.message)); else audio.pause(); }
    };
    this.querySelectorAll('.music-strip [data-song-id]').forEach(button => {
      const selected = button.dataset.songId === this.selectedId && !gallery.pendingSelected;
      button.classList.toggle('selected', selected); button.setAttribute('aria-pressed', String(selected));
      let marker = button.querySelector('.music-selection-mark');
      if (!selected && marker) marker.remove();
      if (selected && !marker) { marker = document.createElement('span'); marker.className = 'music-selection-mark'; render(pencilLoop(true), marker); button.append(marker); }
    });
  }
  // One path for every download, so the strip and the browser panel cannot
  // disagree about a file's name or its type.
  downloadSongs(ids) {
    for (const song of this.songs.filter(song => ids.includes(song.id))) {
      const link = document.createElement('a');
      const url = URL.createObjectURL(song.blob || new Blob([song.score || ''], {type: 'text/vnd.abc'}));
      link.href = url; link.download = `music-${song.seed}.${song.blob ? 'wav' : 'abc'}`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    }
  }
  async clearAllSongs() {
    if (this.busy || !this.songs.length) return;
    const count = this.songs.length;
    if (!confirm(plural(count, t('music.confirm.remove')))) return;
    try {
      if (this.keeping) await this.store(clearMusic);
      this.songs = []; this.selectedId = null;
      this.renderSongs();
      localStorage.setItem('studio-music-changed', String(Date.now()));
      this.options.notify('info', plural(count, t('music.toast.removed')));
    } catch (error) {
      this.options.notify('error', error.message || t('music.error.remove_failed'));
    }
  }
  async removeSong(id) {
    try {
      if (this.keeping) await this.store(() => deleteMusicSong(id));
      this.restoreEpoch = (this.restoreEpoch || 0) + 1;
      this.songs = this.songs.filter(song => song.id !== id);
      if (this.selectedId === id) this.selectedId = this.songs.at(-1)?.id;
      this.renderSongs(); localStorage.setItem('studio-music-changed', String(Date.now())); return true;
    } catch (_) { return false; }
  }
  isCoverOperation(operation) {
    return ['image', 'rewrite'].includes(operation?.kind) && (operation.client_id?.startsWith(this.options?.clientId + ':music-cover:')
      || this.songs.some(song => song.coverClientId && [song.coverClientId, song.coverClientId + ':brief'].includes(operation.client_id)));
  }
  songTitle(song) { return typeof song?.title === 'string' && song.title.trim() ? song.title.trim().slice(0, 120) : t('music.common.untitled'); }
  async renameSong(id, value) {
    const title = value.trim().slice(0, 120) || t('music.common.untitled');
    const update = current => current ? {...current, title} : null;
    try {
      const updated = this.keeping ? await this.store(() => updateMusicSong(id, update)) : update(this.songs.find(song => song.id === id));
      if (!updated || !this.songs.some(song => song.id === id)) {
        this.options.notify('error', t('music.error.song_missing')); return;
      }
      this.restoreEpoch = (this.restoreEpoch || 0) + 1;
      this.songs = this.songs.map(song => song.id === id ? {...song, title: updated.title} : song);
      const current = this.songs.find(song => song.id === id);
      for (const card of this.querySelectorAll('.music-song')) {
        if (card.dataset.songId !== id) continue;
        card.querySelector('.music-title-button').textContent = this.songTitle(current);
        card.querySelector('audio')?.setAttribute('aria-label', this.songTitle(current));
      }
      for (const thumb of this.querySelectorAll('.music-thumb')) if (thumb.dataset.songId === id) thumb.title = this.songTitle(current);
      this.syncGallery();
      localStorage.setItem('studio-music-changed', String(Date.now()));
    } catch (_) { /* The storage queue reports a failed save; retain the previous title. */ }
  }
  renderTitle(song) {
    const heading = document.createElement('h3'); heading.className = 'music-song-title';
    const button = document.createElement('button'); button.type = 'button'; button.className = 'text-btn music-title-button';
    button.textContent = this.songTitle(song); button.title = t('music.title.edit');
    const input = document.createElement('input'); input.type = 'text'; input.className = 'music-title-input'; input.maxLength = 120;
    input.setAttribute('aria-label', t('music.title.label')); input.hidden = true;
    let editing = false;
    const finish = (save, focus) => {
      if (!editing) return;
      editing = false; input.hidden = true; button.hidden = false;
      if (save) this.renameSong(song.id, input.value);
      if (focus) button.focus();
    };
    button.addEventListener('click', () => {
      editing = true; input.value = this.songTitle(this.songs.find(current => current.id === song.id));
      button.hidden = true; input.hidden = false; input.focus(); input.select();
    });
    input.addEventListener('blur', () => finish(true, false));
    input.addEventListener('keydown', event => {
      if (!['Enter', 'Escape'].includes(event.key)) return;
      event.preventDefault(); event.stopPropagation(); finish(event.key === 'Enter', true);
    });
    heading.append(button, input); return heading;
  }
  async updateSong(id, update) {
    const updated = this.keeping ? await this.store(() => updateMusicSong(id, update)) : update(this.songs.find(song => song.id === id));
    if (!updated || !this.songs.some(song => song.id === id)) return null;
    this.restoreEpoch = (this.restoreEpoch || 0) + 1;
    this.songs = this.songs.map(song => song.id === id ? updated : song);
    this.renderSongs(); localStorage.setItem('studio-music-changed', String(Date.now())); return updated;
  }
  async planCover(request) {
    const answer = await fetch('/api/v1/operations', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(request)});
    let operation = await answer.json();
    if (!answer.ok) throw new Error(operation.error || t('music.cover.error.prepare'));
    if (!operation.id || !operation.status_url) throw new Error(t('music.cover.error.invalid_operation'));
    this.setOperation(operation);
    const owned = {id: operation.id, clientId: operation.client_id};
    const deadline = Date.now() + 180000;
    const timeout = async () => {
      if (owned.clientId === request.client_id) {
        try { await fetch('/api/v1/operations/' + encodeURIComponent(owned.id) + '/cancel', {method: 'POST', signal: AbortSignal.timeout(5000)}); } catch (_) { /* Only this request may be cancelled. */ }
      }
      throw new Error(t('music.cover.error.timeout'));
    };
    while (!['succeeded', 'failed', 'cancelled'].includes(operation.status)) {
      if (Date.now() >= deadline) return timeout();
      await new Promise(resolve => setTimeout(resolve, 250));
      if (Date.now() >= deadline) return timeout();
      try {
        const status = await fetch(operation.status_url, {cache: 'no-store', signal: AbortSignal.timeout(Math.max(1, deadline - Date.now()))});
        if (!status.ok) throw new Error(t('music.cover.error.status'));
        operation = await status.json();
      } catch (error) { if (Date.now() >= deadline) return timeout(); throw error; }
    }
    if (operation.status !== 'succeeded') throw new Error(operation.error || (operation.status === 'cancelled' ? t('music.cover.error.artwork_cancelled') : t('music.cover.error.prepare')));
    if (!operation.result_url) throw new Error(t('music.cover.error.unavailable'));
    if (Date.now() >= deadline) return timeout();
    let brief;
    try {
      const result = await fetch(operation.result_url, {cache: 'no-store', signal: AbortSignal.timeout(Math.max(1, deadline - Date.now()))});
      if (!result.ok) throw new Error(t('music.cover.error.load'));
      brief = await result.json();
    } catch (error) { if (Date.now() >= deadline) return timeout(); throw error; }
    if (brief.cancelled) throw new Error(t('music.cover.error.artwork_cancelled'));
    if (typeof brief.prompt !== 'string' || !brief.prompt.trim()) throw new Error(t('music.cover.error.empty'));
    return musicCoverImagePrompt(brief.prompt);
  }
  async generateCover(song) {
    if (this.busy) return;
    this.closeScore(false); this.coverStarting = true; this.sync(); this.options.onBusyChange();
    const clientId = this.options.clientId + ':music-cover:' + crypto.randomUUID();
    try {
      const stateAnswer = await fetch('/api/v1/studio', {cache: 'no-store'});
      if (!stateAnswer.ok) throw new Error(t('music.cover.error.image_models'));
      const image = (await stateAnswer.json()).image;
      const mode = image?.capabilities?.modes.find(mode => mode.id === 'generate');
      const squares = (mode?.params.find(param => param.id === 'size')?.choices || [])
        .filter(choice => { const match = choice.value.match(/^(\d+)x(\d+)$/); return match && match[1] === match[2]; })
        .sort((a, b) => Math.abs(Number(a.value.split('x')[0]) - 512) - Math.abs(Number(b.value.split('x')[0]) - 512));
      if (!mode || !squares.length) throw new Error(t('music.cover.error.no_square'));
      const current = await this.updateSong(song.id, item => item && (!item.coverClientId || item.coverError)
        ? {...item, coverClientId: clientId, coverRequestedAt: Date.now(), coverError: ''} : null);
      if (!current) throw new Error(t('music.cover.error.busy'));
      const defaults = Object.fromEntries(mode.params.filter(param => param.default != null).map(param => [param.id, param.default]));
      const parameters = {...defaults, mode: 'generate', backend: image.active, size: squares[0].value, count: 1, library_id: this.options.libraryId};
      let prompt = musicCoverPrompt(current);
      if (musicCoverNeedsRewrite(current)) prompt = await this.planCover({...parameters, kind: 'rewrite', prompt, client_id: clientId + ':brief'});
      const latest = await this.updateSong(song.id, item => item?.coverClientId === clientId
        ? {...item, coverRequestedAt: Date.now()} : null);
      if (!latest) throw new Error(t('music.cover.error.request_changed'));
      const answer = await fetch('/api/v1/operations', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({...parameters, kind: 'image', prompt, client_id: clientId})});
      const operation = await answer.json();
      if (!answer.ok) throw new Error(operation.error || t('music.cover.error.start_failed'));
      this.setOperation(operation);
    } catch (error) {
      try { await this.updateSong(song.id, item => item?.coverClientId === clientId ? {...item, coverError: error.message} : null); } catch (_) { /* Report the initiating error too. */ }
      this.options.notify('error', error.message);
    } finally { this.coverStarting = false; this.sync(); this.options.onBusyChange(); }
  }
  observeCoverOperations(operations) {
    // Allow a submitting tab two minutes before recovering an abandoned request.
    for (const song of this.songs) {
      const key = 'missing:' + song.id;
      if (!song.coverClientId || song.coverError || this.coverStarting || this.coverImports.has(key)
        || Date.now() - (song.coverRequestedAt || 0) < 120000
        || operations.some(operation => operation.client_id === song.coverClientId
          || (operation.client_id === song.coverClientId + ':brief' && !['succeeded', 'failed', 'cancelled'].includes(operation.status)))) continue;
      this.coverImports.add(key);
      this.updateSong(song.id, current => current?.coverClientId === song.coverClientId
        ? {...current, coverClientId: '', coverError: t('music.cover.error.expired')} : null)
        .catch(error => this.options.notify('error', error.message)).finally(() => this.coverImports.delete(key));
    }
    for (const operation of operations) {
      const song = this.songs.find(song => song.coverClientId && song.coverClientId === operation.client_id);
      if (!song || !['succeeded', 'failed', 'cancelled'].includes(operation.status) || this.coverImports.has(operation.id)) continue;
      this.coverImports.add(operation.id);
      this.importCover(song, operation).then(() => this.coverFailures.delete(operation.id)).catch(error => {
        if (this.coverFailures.get(operation.id) !== error.message) this.options.notify('error', t('music.cover.error.save', {message: error.message}));
        this.coverFailures.set(operation.id, error.message);
      })
        .finally(() => this.coverImports.delete(operation.id));
    }
  }
  async importCover(song, operation) {
    const clientId = operation.client_id;
    let cover = {};
    if (operation.status === 'succeeded') {
      const answer = await fetch(operation.result_url, {cache: 'no-store'});
      if (!answer.ok) {
        if ([404, 410].includes(answer.status)) {
          await this.updateSong(song.id, current => current?.coverClientId === clientId
            ? {...current, coverClientId: '', coverError: t('music.cover.error.result_expired')} : null);
          return;
        }
        throw new Error(t('music.cover.error.load_failed'));
      }
      const image = (await answer.json()).images?.[0];
      if (!image?.png_base64 || image.width !== image.height) {
        await this.updateSong(song.id, current => current?.coverClientId === clientId
          ? {...current, coverClientId: '', coverError: t('music.cover.error.not_square')} : null);
        return;
      }
      const response = await fetch('data:image/png;base64,' + image.png_base64);
      cover = {coverBlob: await response.blob(), coverPrompt: image.prompt, coverModel: operation.model, coverSeed: image.seed};
    }
    await this.updateSong(song.id, current => current?.coverClientId === clientId
      ? {...current, ...cover, coverClientId: '', coverError: operation.status === 'succeeded' ? '' : operation.error || t('music.cover.error.cancelled')} : null);
  }
  setTextView(id, mode) {
    const card = this.querySelector('.music-song[data-song-id="' + CSS.escape(id) + '"]');
    if (!card) return;
    const song = this.songs.find(item => item.id === id);
    const lyrics = mode === 'lyrics' && !song.settings?.instrumental && Boolean(song.settings?.lyrics?.trim());
    this.lyricsShown ||= new Set();
    if (lyrics) this.lyricsShown.add(id); else this.lyricsShown.delete(id);
    const content = card.querySelector('.music-track-text');
    content.dataset.mode = lyrics ? 'lyrics' : 'style';
    content.setAttribute('aria-label', lyrics ? t('music.text.lyrics_label') : t('music.text.style_label'));
    content.querySelector('.music-style-panel').hidden = lyrics;
    content.querySelector('.music-inline-lyrics').hidden = !lyrics;
    content.scrollTop = 0;
    card.querySelectorAll('[data-music-text-mode]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.musicTextMode === content.dataset.mode)));
    card.querySelector('.music-lyrics-toggle').title = lyrics ? t('music.text.show_style') : t('music.text.show_lyrics');
  }
  closeDetails(focus = true) {
    this.querySelectorAll('[data-music-details]').forEach(button => button.setAttribute('aria-expanded', 'false'));
    if (!this.detailsSheet) {
      if (focus) this.detailsTrigger?.focus();
      return;
    }
    this.detailsQuiet = !focus;
    dismissSheet(this.detailsSheet);
  }
  openDetails(songId, trigger) {
    const detail = this.detailsBodies.get(songId);
    if (!detail) return;
    this.closeScore(false); this.closeDetails(false); this.detailsTrigger = trigger;
    trigger.setAttribute('aria-expanded', 'true');
    this.detailsSheet = openSheet({
      id: detail.id,
      title: detail.title,
      label: t('music.details.label'),
      closeLabel: t('music.details.close_label'),
      body: detail.body,
      footer: detail.footer,
      onClose: () => {
        const quiet = this.detailsQuiet;
        this.detailsQuiet = false;
        this.detailsSheet = null;
        this.querySelectorAll('[data-music-details]').forEach(button => button.setAttribute('aria-expanded', 'false'));
        if (!quiet) this.detailsTrigger?.focus();
      },
    });
  }
  closeScore(focus = true) { this.closeAbcEditor(focus); }
  scrollScore(event) {
    if (event.target !== event.currentTarget || event.altKey || event.ctrlKey || event.metaKey) return;
    const pane = event.currentTarget;
    const distance = {ArrowLeft: -40, ArrowRight: 40, ArrowDown: 40, ArrowUp: -40, PageDown: pane.clientHeight * .85, PageUp: -pane.clientHeight * .85,
      Home: -pane.scrollHeight, End: pane.scrollHeight}[event.key];
    if (distance === undefined) return;
    event.preventDefault(); event.stopPropagation();
    if (['ArrowLeft', 'ArrowRight'].includes(event.key)) pane.scrollLeft += distance; else pane.scrollTop += distance;
  }
  scoreArtifacts(song) {
    const links = document.createElement('div'); links.className = 'music-score-downloads';
    for (const artifact of song.metadata?.artifacts || song.artifacts || []) {
      try {
        if (typeof artifact.name !== 'string' || typeof artifact.base64 !== 'string') continue;
        const bytes = Uint8Array.from(atob(artifact.base64), byte => byte.charCodeAt(0));
        const url = URL.createObjectURL(new Blob([bytes], {type: artifact.content_type || 'application/octet-stream'})); this.urls.push(url);
        const link = document.createElement('a'); link.className = 'text-btn'; link.href = url; link.download = artifact.name.split(/[\\/]/).at(-1);
        const stem = link.download.replace(/\.[^.]+$/, '').replace(/[_.-]+/g, ' ').trim();
        const names = {'melody vocal': t('music.artifact.vocal'), 'melody instrumental': t('music.artifact.instrumental'), 'melody full': t('music.artifact.full')};
        const label = names[stem.toLowerCase()] || stem.charAt(0).toUpperCase() + stem.slice(1);
        link.textContent = /\.midi?$/i.test(link.download) ? t('music.artifact.download_midi', {name: label}) : /\.lab$/i.test(link.download) ? t('music.artifact.download_lab', {name: label}) : t('music.artifact.download', {name: link.download});
        links.append(link);
      } catch (_) { /* An unavailable export must not hide the composition. */ }
    }
    return links;
  }
  renderPlayer(audio, song) {
    const player = document.createElement('div'); player.className = 'music-player';
    const timeline = document.createElement('div'); timeline.className = 'music-timeline';
    const seek = document.createElement('input'); seek.type = 'range'; seek.min = '0'; seek.max = '0'; seek.step = '0.1'; seek.value = '0';
    seek.setAttribute('aria-label', t('music.player.position'));
    const times = document.createElement('div'); times.className = 'music-times num';
    const elapsed = document.createElement('span'); elapsed.className = 'music-time-elapsed';
    const remaining = document.createElement('span'); remaining.className = 'music-time-remaining';
    times.append(elapsed, remaining); timeline.append(seek, times);
    const transport = document.createElement('div'); transport.className = 'music-transport';
    const control = (label, paths) => {
      const button = document.createElement('button'); button.type = 'button'; button.className = 'icon-btn';
      button.setAttribute('aria-label', label); button.title = label;
      button.innerHTML = `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${paths}</svg>`;
      return button;
    };
    const back = control(t('music.player.back'), '<path d="M6 7a8 8 0 1 1-1 10M6 3v5H1" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/><text x="12" y="16" text-anchor="middle" font-size="10" font-family="sans-serif">5</text>');
    const toggle = control(t('music.player.play'), ''); toggle.classList.add('music-play');
    const forward = control(t('music.player.forward'), '<path d="M18 7a8 8 0 1 0 1 10M18 3v5h5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/><text x="12" y="16" text-anchor="middle" font-size="10" font-family="sans-serif">5</text>');
    transport.append(back, toggle, forward);
    const hasLyrics = !song.settings?.instrumental && Boolean(song.settings?.lyrics?.trim());
    const lyricsShown = hasLyrics && this.lyricsShown?.has(song.id);
    const lyrics = document.createElement('button'); lyrics.type = 'button'; lyrics.className = 'icon-btn music-lyrics-toggle';
    lyrics.setAttribute('aria-label', t('music.field.lyrics')); lyrics.dataset.musicTextMode = 'lyrics'; lyrics.disabled = !hasLyrics;
    lyrics.innerHTML = '<svg class="icon" aria-hidden="true"><use href="#i-text"/></svg>';
    lyrics.setAttribute('aria-pressed', String(Boolean(lyricsShown))); lyrics.setAttribute('aria-controls', 'music-text-' + song.id);
    lyrics.title = lyricsShown ? t('music.text.show_style') : t('music.text.show_lyrics');
    lyrics.addEventListener('click', () => this.setTextView(song.id, this.lyricsShown?.has(song.id) ? 'style' : 'lyrics'));
    transport.append(lyrics);
    const error = document.createElement('p'); error.className = 'music-error music-player-error'; error.setAttribute('role', 'status'); error.hidden = true;
    const clock = value => { const seconds = Math.floor(Math.max(0, value)); return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`; };
    const duration = () => Number.isFinite(audio.duration) && audio.duration > 0 ? audio.duration : 0;
    const sync = () => {
      const length = duration(), ready = length > 0 && audio.readyState > 0 && !audio.error;
      const position = Math.max(0, Math.min(length, Number.isFinite(audio.currentTime) ? audio.currentTime : 0));
      seek.max = String(length); seek.value = String(position); seek.disabled = !ready;
      seek.style.setProperty('--music-progress', `${length ? position / length * 100 : 0}%`);
      seek.setAttribute('aria-valuetext', t('music.player.position_of', {position: clock(position), duration: clock(length)}));
      elapsed.textContent = clock(position); remaining.textContent = '−' + clock(length - position);
      back.disabled = toggle.disabled = forward.disabled = !ready;
      const playing = !audio.paused && !audio.ended;
      toggle.setAttribute('aria-label', playing ? t('music.audio.pause') : t('music.player.play')); toggle.title = playing ? t('music.audio.pause') : t('music.player.play');
      toggle.setAttribute('aria-pressed', String(playing));
      toggle.innerHTML = `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${playing ? '<path d="M7 5h3v14H7zm7 0h3v14h-3z"/>' : '<path d="m8 5 11 7-11 7z"/>'}</svg>`;
      if (audio.error) { error.textContent = t('music.player.error'); error.hidden = false; }
    };
    const move = value => { if (!duration() || audio.error) return; audio.currentTime = Math.max(0, Math.min(duration(), value)); sync(); };
    back.addEventListener('click', () => move(audio.currentTime - 5));
    forward.addEventListener('click', () => move(audio.currentTime + 5));
    seek.addEventListener('input', () => move(Number(seek.value)));
    toggle.addEventListener('click', () => {
      if (!audio.paused) { audio.pause(); return; }
      if (audio.ended) move(0);
      error.hidden = true;
      audio.play().catch(() => { error.textContent = t('music.player.error'); error.hidden = false; sync(); });
    });
    audio.addEventListener('loadedmetadata', () => { if (!audio.error) error.hidden = true; });
    for (const event of ['loadedmetadata', 'durationchange', 'timeupdate', 'play', 'pause', 'ended', 'error', 'emptied', 'loadstart']) audio.addEventListener(event, sync);
    player.append(timeline, transport, error); sync(); return player;
  }
  renderSongs() {
    this.lyricsShown?.forEach(id => { if (!this.songs.some(song => song.id === id)) this.lyricsShown.delete(id); });
    this.closeDetails(false);
    this.closeScore(false);
    this.detailsBodies = new Map();
    const players = new Map();
    for (const card of this.querySelectorAll('.music-song')) {
      const audio = card.querySelector('audio');
      if (!audio) continue;
      if (!this.songs.some(song => song.id === card.dataset.songId)) { audio.pause(); continue; }
      players.set(card.dataset.songId, {audio, controls: card.querySelector('.music-player')});
      // Keep the media connected while the gallery redraws around it.
      this.append(audio);
    }
    const retainedUrls = new Set([...players.values()].map(player => player.audio.src));
    this.urls?.forEach(url => { if (!retainedUrls.has(url)) URL.revokeObjectURL(url); });
    this.urls = [];
    this.coverUrls = new Map();
    if (!this.songs.some(song => song.id === this.selectedId)) this.selectedId = this.songs.at(-1)?.id;
    const list = this.querySelector('.music-songs');
    list.replaceChildren();
    const bars = this.querySelector('.music-output-bars'); bars.replaceChildren();
    const strip = this.querySelector('.music-strip'); strip.replaceChildren();
    for (const song of this.songs.slice().reverse()) {
      const card = document.createElement('article');
      card.className = 'music-song';
      card.dataset.songId = song.id;
      const hasAudio = song.blob instanceof Blob && song.blob.size > 0;
      if (!hasAudio) card.classList.add('is-score');
      const title = this.renderTitle(song);
      const retained = players.get(song.id);
      const audio = retained?.audio || document.createElement('audio');
      const url = retained ? audio.src : URL.createObjectURL(hasAudio ? song.blob : new Blob([song.score || ''], {type: 'text/vnd.abc'})); this.urls.push(url);
      audio.controls = false; audio.hidden = true; if (hasAudio && !retained) audio.src = url; audio.preload = 'metadata';
      audio.setAttribute('aria-label', this.songTitle(song));
      const artwork = document.createElement('div'); artwork.className = 'music-artwork';
      artwork.innerHTML = recordPlayer();
      if (song.coverBlob) {
        const cover = document.createElement('img'); const coverUrl = URL.createObjectURL(song.coverBlob);
        this.urls.push(coverUrl); this.coverUrls.set(song.id, coverUrl);
        cover.src = coverUrl; cover.alt = t('music.cover.alt'); artwork.prepend(cover); artwork.classList.add('has-cover');
      }
      const playback = document.createElement('span'); playback.className = 'music-playback-label'; playback.textContent = hasAudio ? t('music.playback.ready') : t('music.playback.score_only');
      artwork.append(playback);
      if (song.coverClientId && !song.coverError) {
        const pending = document.createElement('span'); pending.className = 'music-cover-pending'; pending.textContent = t('music.cover.making'); artwork.append(pending);
      }
      const syncPlayback = () => {
        const playing = !audio.paused && !audio.ended;
        card.classList.toggle('is-playing', playing);
        playback.textContent = playing ? t('music.playback.playing') : audio.ended ? t('music.playback.finished') : t('music.playback.ready');
        this.syncBackgroundPlayback();
      };
      audio.onplay = () => {
        this.querySelectorAll('audio').forEach(other => { if (other !== audio) other.pause(); });
        this.controls.querySelectorAll('audio').forEach(reference => reference.pause());
        syncPlayback();
      };
      audio.onpause = audio.onended = syncPlayback;
      card.classList.toggle('is-playing', !audio.paused && !audio.ended);
      if (!audio.paused && !audio.ended) playback.textContent = t('music.playback.playing');
      const style = document.createElement('p'); style.className = 'music-song-style'; style.textContent = song.settings?.style || t('music.common.song');
      const download = document.createElement('a'); download.className = 'icon-btn';
      download.href = url; download.download = `music-${song.seed}.${hasAudio ? 'wav' : 'abc'}`; download.setAttribute('aria-label', hasAudio ? t('music.download.wav') : t('music.download.abc')); download.title = hasAudio ? t('music.download.wav') : t('music.download.abc'); download.innerHTML = '<svg class="icon" aria-hidden="true"><use href="#i-download"></use></svg>';
      const details = document.createElement('div');
      details.className = 'music-details-body';
      const metadata = document.createElement('dl');
      const planning = song.metadata?.config?.cot || song.settings?.cot;
      const planningKey = {full: 'music.planning.full', melody: 'music.planning.melody', off: 'music.planning.off'}[planning];
      for (const [name, value] of [[t('music.meta.model'), musicModelName(song.model)], [t('music.field.seed'), song.seed], [t('music.meta.length'), hasAudio ? t('music.meta.seconds', {value: song.seconds.toFixed(1)}) : null], [t('music.meta.time'), Number.isFinite(song.generationSeconds) ? t('music.meta.seconds', {value: song.generationSeconds.toFixed(1)}) : null],
        [t('music.meta.audio_label'), hasAudio ? t('music.meta.audio_value') : t('music.meta.score_value')], [t('music.meta.workflow'), t({generate: 'music.meta.workflow_song', plan: 'music.meta.workflow_plan', transcribe: 'music.meta.workflow_transcribe', cover: 'music.meta.workflow_cover'}[song.settings?.mode || 'generate'])], [t('music.meta.reference'), song.settings?.reference_name], [t('music.meta.instrumental'), song.settings?.instrumental ? t('music.common.yes') : null], [t('music.meta.steps'), hasAudio ? song.settings?.steps || 32 : null], [t('music.meta.guidance'), hasAudio ? song.settings?.cfg_scale ?? 1 : null], [t('music.field.style'), song.settings?.style], [t('music.field.planning'), planningKey ? t(planningKey) : null], [t('music.meta.cover_model'), song.coverModel], [t('music.meta.cover_seed'), song.coverSeed]]) {
        if (value === undefined || value === null || value === '') continue;
        const label = document.createElement('dt'); label.textContent = name;
        const data = document.createElement('dd'); data.textContent = String(value); metadata.append(label, data);
      }
      details.append(metadata);
      // The words are the longest thing in the sheet and the least often read,
      // so they start folded. A song with no words has nothing to fold.
      const lyrics = String(song.settings?.lyrics || '').trim();
      if (lyrics) {
        const fold = document.createElement('details'); fold.className = 'music-details-lyrics';
        const lyricsHead = document.createElement('summary'); lyricsHead.textContent = t('music.field.lyrics');
        const words = document.createElement('p'); words.textContent = lyrics;
        fold.append(lyricsHead, words); details.append(fold);
      }
      // The sheet the song was written from, then the text it was written in. A score
      // arrives engraved when the sheet opens, because the engraver needs a laid-out box.
      if (song.score) {
        const scoreView = document.createElement('section'); scoreView.className = 'music-details-score';
        const pane = document.createElement('div'); pane.className = 'music-abc-notation music-details-notation';
        pane.tabIndex = 0; pane.setAttribute('role', 'region'); pane.setAttribute('aria-label', t('music.score.rendered_label'));
        pane.addEventListener('keydown', event => this.scrollScore(event));
        // Both readings start folded, so the sheet opens on the metadata. The engraver needs
        // a laid-out box, so it runs on the first open rather than on a hidden element.
        const sheetFold = document.createElement('details'); sheetFold.className = 'music-details-sheet';
        const sheetHead = document.createElement('summary'); sheetHead.textContent = t('music.common.score');
        sheetFold.addEventListener('toggle', () => {
          if (sheetFold.open) this.engraveDetails(pane, song.score);
        });
        sheetFold.append(sheetHead, pane);
        const source = document.createElement('details'); const sourceHead = document.createElement('summary'); sourceHead.textContent = t('music.score.source');
        const notation = document.createElement('pre'); notation.textContent = song.score;
        source.append(sourceHead, notation);
        scoreView.append(sheetFold, source); details.append(scoreView);
      }
      // The downloads sit in the sheet's own foot, so they stay reachable while
      // the body scrolls through the metadata.
      let downloads = null;
      if (song.score) {
        downloads = this.scoreArtifacts(song);
        const abc = document.createElement('a'); abc.className = 'text-btn'; abc.textContent = t('music.download.abc'); abc.download = `music-${song.seed}.abc`;
        const abcUrl = URL.createObjectURL(new Blob([song.score], {type: 'text/vnd.abc;charset=utf-8'})); this.urls.push(abcUrl); abc.href = abcUrl;
        downloads.prepend(abc);
      }
      const send = menuItem('music', t('music.menu.send_video'), () => {
        if (this.busy || song.stub || !hasAudio) return;
        this.options.onSendToVideo({blob: song.blob, name: `music-${song.seed}.wav`}).catch(error => this.options.notify('error', error.message));
      });
      send.dataset.musicSend = ''; send.dataset.stub = String(song.stub); send.dataset.scoreOnly = String(!hasAudio);
      send.disabled = this.busy || song.stub || !hasAudio;
      const remove = document.createElement('button'); remove.type = 'button'; remove.className = 'icon-btn danger'; remove.setAttribute('aria-label', t('music.common.delete')); remove.title = t('music.delete.title');
      remove.innerHTML = '<svg class="icon" aria-hidden="true"><use href="#i-trash"></use></svg>';
      remove.addEventListener('click', () => this.removeSong(song.id));
      const artworkButton = document.createElement('button'); artworkButton.type = 'button'; artworkButton.className = 'btn quiet';
      artworkButton.dataset.musicCover = '';
      artworkButton.innerHTML = `<svg class="icon" aria-hidden="true"><use href="#i-image"/></svg>${t('music.cover.artwork')}`;
      artworkButton.title = song.coverBlob ? t('music.cover.new_title') : t('music.cover.generate_title');
      artworkButton.setAttribute('aria-keyshortcuts', 'Alt+C');
      artworkButton.addEventListener('click', () => this.generateCover(song));
      const facts = document.createElement('div'); facts.className = 'facts num'; facts.setAttribute('aria-label', t('music.meta.label'));
      for (const value of [musicModelName(song.model), hasAudio ? t('music.duration.seconds', {value: song.seconds.toFixed(1)}) : t('music.playback.score_only'), Number.isFinite(song.generationSeconds) ? t('music.facts.generated_in', {value: song.generationSeconds.toFixed(1)}) : hasAudio ? t('music.facts.audio') : t('music.facts.abc'), t('music.facts.seed', {value: song.seed})]) { const fact = document.createElement('span'); fact.textContent = value; facts.append(fact); }
      const detailsId = 'music-details-' + this.songs.indexOf(song);
      this.detailsBodies.set(song.id, {id: detailsId, title: hasAudio ? t('music.details.song_title') : t('music.details.score_title'), body: details, footer: downloads});
      const about = document.createElement('div'); about.className = 'about';
      const caption = document.createElement('p'); caption.className = 'prompt-line'; caption.textContent = song.settings?.style || song.settings?.reference_name || (hasAudio ? t('music.common.song') : t('music.common.music_score')); caption.title = caption.textContent;
      caption.setAttribute('role', 'button'); caption.tabIndex = 0; caption.dataset.musicDetails = ''; caption.setAttribute('aria-controls', detailsId); caption.setAttribute('aria-expanded', 'false');
      caption.addEventListener('click', () => this.openDetails(song.id, caption));
      caption.addEventListener('keydown', event => { if (['Enter', ' '].includes(event.key)) { event.preventDefault(); this.openDetails(song.id, caption); } });
      about.append(caption, facts);
      const actions = document.createElement('div'); actions.className = 'actions music-song-actions';
      // A score moves into the form from here; the modal belongs to the form's own
      // Edit score link, so this item never opens it.
      const useScore = menuItem('music', t('music.menu.use_score'), () => this.useScore(song)); useScore.dataset.musicScore = '';
      const more = document.createElement('div'); more.className = 'menu-anchor';
      const toggle = document.createElement('button'); toggle.type = 'button'; toggle.className = 'icon-btn'; toggle.dataset.musicMore = ''; toggle.setAttribute('aria-label', t('music.actions.more')); toggle.title = t('music.actions.more');
      const menu = document.createElement('div'); menu.className = 'menu up'; menu.id = 'music-actions-' + this.songs.indexOf(song); menu.hidden = true; menu.setAttribute('role', 'menu'); menu.setAttribute('aria-label', t('music.actions.menu_label'));
      toggle.setAttribute('aria-controls', menu.id); toggle.setAttribute('aria-expanded', 'false'); toggle.innerHTML = '<svg class="icon" aria-hidden="true"><use href="#i-more"></use></svg>'; toggle.addEventListener('click', () => toggleMenu(menu));
      menu.append(...(song.score ? [useScore] : []), send);
      const reuse = menuItem('text', t('music.menu.reuse'), () => {
        if (this.busy) return;
        for (const key of ['style', 'lyrics']) this.controls.querySelector('#music-' + key).value = song.settings?.[key] || '';
        if (song.settings?.instrumental) this.controls.querySelector('#music-lyrics').value = '';
        const seed = Number.isFinite(song.seed) ? song.seed : song.settings?.seed;
        if (Number.isFinite(seed)) this.controls.querySelector('#music-seed').value = String(seed);
        this.selectWorkflow('generate');
        this.controls.dispatchEvent(new Event('input', {bubbles: true}));
        this.controls.querySelector('#music-style').focus();
      }); reuse.dataset.musicReuse = ''; menu.append(reuse); more.append(toggle, menu);
      const rule = document.createElement('span'); rule.className = 'rule'; rule.setAttribute('aria-hidden', 'true');
      actions.append(artworkButton, more, rule, download, remove);
      const bar = document.createElement('section'); bar.className = 'stage-bar music-output-details'; bar.dataset.songId = song.id; bar.setAttribute('aria-label', t('music.preview.details_label')); bar.append(about, actions); bars.append(bar);
      const body = document.createElement('div'); body.className = 'music-track-body';
      body.append(title);
      if (song.stub) { const warning = document.createElement('p'); warning.className = 'music-note music-stub-note'; warning.textContent = hasAudio ? t('music.stub.audio') : t('music.stub.score'); body.append(warning); }
      body.append(hasAudio ? renderSongText(song, this.lyricsShown?.has(song.id)) : style);
      if (hasAudio) body.append(retained?.controls || this.renderPlayer(audio, song), audio);
      if (song.coverError) { const error = document.createElement('p'); error.className = 'music-error'; error.textContent = song.coverError; body.append(error); }
      card.append(artwork, body); list.append(card);
      const thumb = document.createElement('button'); thumb.type = 'button'; thumb.className = 'frame music-thumb'; thumb.dataset.songId = song.id;
      const number = this.songs.indexOf(song) + 1;
      thumb.setAttribute('aria-label', t('music.thumb.select', {kind: hasAudio ? t('music.thumb.song') : t('music.thumb.score'), number})); thumb.title = this.songTitle(song);
      const still = document.createElement('span'); still.className = 'still music-thumb-art';
      if (song.coverBlob) { const image = document.createElement('img'); image.src = this.coverUrls.get(song.id); image.alt = ''; still.append(image); }
      else { const mark = document.createElement('span'); mark.textContent = '♫'; mark.className = 'music-thumb-note'; still.append(mark); }
      const playing = document.createElement('span'); playing.className = 'music-playing-state'; playing.hidden = true;
      render(playingMark(), playing); still.append(playing);
      const label = document.createElement('span'); label.className = 'no'; label.textContent = t('music.thumb.meta', {number: String(number).padStart(2, '0'), value: hasAudio ? t('music.thumb.seconds', {value: song.seconds.toFixed(0)}) : t('music.thumb.score')});
      thumb.append(still, label); thumb.addEventListener('click', () => this.selectSong(song.id)); strip.append(thumb);
    }
    this.sync(); this.syncGallery();
  }
}
customElements.define('music-studio', MusicStudio);
