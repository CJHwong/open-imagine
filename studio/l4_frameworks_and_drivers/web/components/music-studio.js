import {musicSongs, saveMusicSong, updateMusicSong, deleteMusicSong, musicDraft, saveMusicDraft, clearMusic} from '../lib/music-store.js';
import {renderNotation} from '../lib/music-notation.js';
import {renderSongText} from '../lib/music-lyrics.js';
import {closeMenus, menuItem, toggleMenu} from './popup-menu.js';
import {blobBase64} from '../lib/voice-audio.js';
import {musicScore, musicCoverPrompt, musicCoverImagePrompt, musicCoverNeedsRewrite} from '../lib/music-score.js';
import {rememberGalleryView, preferredGalleryId, galleryBatch} from '../lib/gallery-view.js';
import {render} from 'https://cdn.jsdelivr.net/npm/lit@3.2.1/+esm';
import {pencilLoop, playingMark} from './gallery-marker.js';
import './gallery-browser.js';
import './run-button.js';
import {configureLookRows} from './look-rows.js';

// The run button says Generate in every workflow, as every other workspace's does, and
// the sub line names what this one makes. The mode picker is the four workflows the
// engine declares, so a workflow is never hidden behind an Advanced checkbox.
const MODE_CAPTIONS = {
  generate: 'A song with audio',
  plan: 'Sheet music only',
  transcribe: 'A score from your recording',
  cover: 'A new song from your recording',
};
// The empty pane says what the chosen output needs. Generate and Compose are the two
// choices; a reference recording turns them into a cover and a transcription, so the copy
// names that result rather than a fourth mode.
const EMPTY_COPY = {
  generate: ['Write a style and lyrics, or add a recording to cover it.', 'Write a style', 'style'],
  plan: ['Write a style and lyrics to compose sheet music.', 'Write a style', 'style'],
  transcribe: ['Your recording becomes an editable score. Choose what to keep.', 'Choose what to keep', 'task'],
  cover: ['Your recording sets the composition. Style and lyrics shape the new version.', 'Write a style', 'style'],
};

// The third field recognizes saved drafts that used keyword-only presets.
const MUSIC_STYLE_ROWS = [
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
    this.clearedText = null;
    this.restoreOnStop = false;
  }
  connectedCallback() {
    if (this.ready) return;
    this.ready = true;
    this.innerHTML = `<div class="music-studio-shell"><section class="music-preview-area stage" aria-label="Music preview">
      <div class="music-preview-pane">
      <div class="music-generation" hidden role="status" aria-live="polite">
        ${recordPlayer()}
        <strong class="music-generation-label">Generating music</strong>
        <div class="music-timeline music-generation-timeline">
          <input type="range" min="0" max="100" step="1" value="0" disabled aria-label="Generation progress">
          <div class="music-times num"><span class="music-generation-elapsed">0:00</span><span class="music-generation-percent"></span></div>
        </div>
        <span class="music-generation-detail"></span>
      </div>
      <div class="music-empty video-empty empty">
        <div class="video-empty-mark">MUSIC</div>
        <strong>Preview music</strong>
        <span id="music-empty-hint">Write a style and lyrics, or start from a reference recording.</span>
        <button type="button" class="btn" id="music-write">
          <svg class="icon" aria-hidden="true"><use href="#i-text"/></svg><span>Write a style</span></button>
      </div>
      <div class="music-songs"></div></div><div class="music-output-bars"></div><div class="music-detail-sheets"></div></section>
      <section class="music-gallery strip-wrap" aria-label="Songs" hidden>
        <div class="strip-head"><h2>Songs</h2><gallery-browser workspace="music"></gallery-browser>
          <button type="button" class="text-btn music-background-pause" aria-label="Pause background audio" hidden>Pause</button>
          <span class="music-count">0 songs</span></div>
        <div class="strip music-strip" role="group" aria-label="Select a song"></div>
      </section></div>`;
    this.controls = document.getElementById('music-controls');
    this.controls.innerHTML = `<div class="modes" role="radiogroup" aria-label="Music mode">
        <input type="radio" name="music-workflow" id="music-mode-generate" value="generate" checked>
        <label for="music-mode-generate"><svg class="icon" aria-hidden="true"><use href="#i-sparkle"/></svg>Generate</label>
        <input type="radio" name="music-workflow" id="music-mode-plan" value="plan">
        <label for="music-mode-plan"><svg class="icon" aria-hidden="true"><use href="#i-layout"/></svg>Compose</label>
      </div>
      <input type="hidden" id="music-mode" value="generate">
      <section class="music-generation-fields field prompt-field">
        <div class="field-head"><label for="music-style">Style</label></div>
        <textarea id="music-style" rows="4" placeholder="Mandarin, warm piano pop, expressive vocals, bass and light drums, 88 BPM" required></textarea>
      </section>
      <section class="music-reference-fields field">
        <div class="field-head"><label for="music-reference">Reference audio</label>
          <button type="button" class="text-btn" id="music-reference-replace" hidden>Replace</button></div>
        <input id="music-reference" type="file" hidden accept="audio/*,.wav,.mp3,.flac,.m4a,.ogg,.aiff,.aif">
        <div class="music-reference-drop" id="music-reference-drop">
          <button type="button" class="refs" id="music-reference-choose" aria-label="Add reference audio">
            <span class="refs-empty"><svg class="icon" aria-hidden="true"><use href="#i-music"/></svg>
              <span><strong>Add reference audio</strong>Click to choose, or drop audio.</span></span></button>
          <div class="music-reference-preview video-audios" hidden>
            <div class="video-audio"><div class="video-audio-picture">
              <span class="video-audio-badge"><svg class="icon" aria-hidden="true"><use href="#i-music"/></svg></span>
              <button type="button" class="video-audio-remove" id="music-reference-remove" aria-label="Remove reference">
                <svg class="icon" aria-hidden="true"><use href="#i-x"/></svg></button>
            </div><span class="video-audio-name" id="music-reference-name"></span></div>
          </div>
        </div>
        <span class="caption">Optional. With Generate it makes a cover; with Compose it makes a transcription.</span>
          <div class="music-reference-scope field"><div class="field-head"><label for="music-transcription-task">Keep from reference</label></div>
            <select id="music-transcription-task"><option value="melody-full">Vocal and instrumental melody</option><option value="melody-vocal">Vocal melody only</option><option value="full">Melody and chords</option></select></div>
      </section>
      <section class="music-generation-fields field prompt-field">
        <div class="music-lyrics-fields field"><div class="field-head"><label for="music-lyrics">Lyrics</label></div>
          <textarea id="music-lyrics" rows="6" placeholder="[Verse]&#10;Your lyrics…&#10;&#10;[Chorus]&#10;Your chorus…"></textarea>
          <span class="caption">Leave blank for instrumental. Start each part with a section tag.</span>
          <details class="music-tag-guide"><summary>Section tags</summary>
            <ul class="caption music-lyrics-tags">
              <li><button type="button" class="text-btn music-section-tag" data-music-section="[Intro]">[Intro]</button> sets the mood before the first words.</li>
              <li><button type="button" class="text-btn music-section-tag" data-music-section="[Verse]">[Verse]</button> tells the story, one scene per verse.</li>
              <li><button type="button" class="text-btn music-section-tag" data-music-section="[Pre-Chorus]">[Pre-Chorus]</button> builds tension into the chorus.</li>
              <li><button type="button" class="text-btn music-section-tag" data-music-section="[Chorus]">[Chorus]</button> repeats the line people remember.</li>
              <li><button type="button" class="text-btn music-section-tag" data-music-section="[Bridge]">[Bridge]</button> changes the mood late in the song.</li>
              <li><button type="button" class="text-btn music-section-tag" data-music-section="[Instrumental]">[Instrumental]</button> gives the band a passage alone.</li>
              <li><button type="button" class="text-btn music-section-tag" data-music-section="[Outro]">[Outro]</button> ends the song.</li>
            </ul>
          </details></div>
      </section>
      <details id="music-genre-presets"><summary><span class="music-style-label">Genre</span><span class="values look-pick">none</span></summary>
        <div class="music-genre-groups">${MUSIC_GENRE_GROUPS.map(([family, labels]) => `<section class="music-genre-family"><h3>${family}</h3><div class="look-chips">${labels.map(label => `<button type="button" class="chip" data-music-genre="${label}" aria-pressed="false">${label}</button>`).join('')}</div></section>`).join('')}</div>
        <p class="look-note">Choose one genre. Each pick adds a sentence to Style.</p>
      </details>
      <details id="music-style-presets"><summary><span class="music-style-label">Style presets</span> <look-values class="values" data-form="music"></look-values></summary>
        <look-rows class="look" data-form="music"></look-rows>
        <p class="look-note">Each pick adds a sentence to Style. One pick per row.</p>
      </details>
      <details class="music-advanced-fields"><summary>Advanced <span class="values num" id="music-advanced-values"></span></summary>
        <div class="advanced">
          <div class="field"><div class="field-head"><label for="music-seed">Seed</label></div>
            <input id="music-seed" type="number" min="0" max="4294967295" step="1" placeholder="Random">
            <span class="caption">Leave blank for a random seed.</span></div>
          <div class="field music-composition-fields"><div class="field-head"><label for="music-cot">Planning</label></div>
              <select id="music-cot"><option value="full">Melody and chords</option><option value="melody">Melody</option><option value="off">Direct generation</option></select>
              <span class="caption">How much of the song is planned before audio synthesis.</span></div>
          <div class="field music-composition-fields"><div class="field-head"><label for="music-abc">ABC score (optional)</label></div>
              <textarea id="music-abc" rows="8"></textarea>
              <span class="caption">Paste a composition to render it. Needs melody or full planning.</span></div>
          <div class="field music-synthesis-fields music-sound-fields"><div class="field-head"><label for="music-steps">Synthesis quality</label></div>
              <select id="music-steps"><option value="32">Standard · 32 steps</option><option value="16">Balanced · 16 steps</option><option value="8">Fast · 8 steps</option></select>
              <span class="caption">More steps take longer and can follow detail further.</span></div>
          <div class="field music-synthesis-fields music-sound-fields"><div class="field-head"><label for="music-cfg-scale">Style guidance</label></div>
              <input id="music-cfg-scale" type="number" min="0" max="5" step="0.1" value="1">
              <span class="caption">Higher values follow the style more closely.</span></div>
          <div class="field music-synthesis-fields"><div class="field-head"><label for="music-count">Variations</label></div>
              <select id="music-count"><option value="1">1</option><option value="2">2</option><option value="4">4</option><option value="8">8</option><option value="16">16</option></select>
              <span class="caption">Songs made from these settings, each with its own seed.</span></div>
        </div>
      </details><p class="music-note" id="music-loading-note" hidden></p>`;
    configureLookRows({form: 'music', fields: [], scope: () => this.controls,
      mode: () => this.controls.querySelector('#music-mode').value,
      rows: () => MUSIC_STYLE_ROWS.slice(1), picks: () => this.stylePicks(),
      labels: () => {
        const labels = Object.entries(this.stylePicks()).filter(([name]) => name !== 'Genre').flatMap(([, labels]) => labels);
        return labels.length > 2 ? [labels.length + ' presets'] : labels;
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
    const drop = this.controls.querySelector('#music-reference-drop');
    drop.addEventListener('dragover', event => { if (!this.busy) { event.preventDefault(); drop.classList.add('dragover'); } });
    drop.addEventListener('dragleave', () => drop.classList.remove('dragover'));
    drop.addEventListener('drop', event => {
      event.preventDefault(); drop.classList.remove('dragover');
      if (!this.busy && event.dataTransfer.files[0]) this.setReference(event.dataTransfer.files[0]);
    });
    this.querySelector('.music-background-pause').addEventListener('click', () => this.pausePlayback());
    window.addEventListener('pagehide', () => this.pausePlayback());
    window.addEventListener('resize', () => requestAnimationFrame(() => this.querySelectorAll('.music-notation').forEach(pane => this.updateScoreScrollHint(pane))));
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
      this.options.notify('error', 'The lyrics are too long to add a section tag.'); return;
    }
    lyrics.focus();
    lyrics.setRangeText(insertion, cursor, cursor, 'end');
    lyrics.dispatchEvent(new Event('input', {bubbles: true}));
  }
  syncGenre() {
    const selected = this.stylePicks().Genre[0];
    const section = this.controls.querySelector('#music-genre-presets');
    const summary = section.querySelector('.look-pick');
    const label = selected || 'none';
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
    if (input.maxLength > 0 && next.length > input.maxLength) { this.options.notify('error', 'The style is too long to add another preset.'); return; }
    input.value = next; input.dispatchEvent(new Event('input', {bubbles: true}));
  }
  draft() {
    const values = Object.fromEntries(['mode', 'style', 'lyrics', 'seed', 'cot', 'abc', 'steps', 'cfg-scale', 'count', 'transcription-task']
      .map(key => [key.replaceAll('-', '_'), this.controls.querySelector('#music-' + key).value]));
    return {...values, instrumental: !values.lyrics.trim()};
  }
  // Run empties the words it sent, as the Image workspace does. A cancelled run puts them
  // back, because the run never used them.
  clearInputs() {
    const style = this.controls.querySelector('#music-style');
    const lyrics = this.controls.querySelector('#music-lyrics');
    this.clearedText = {style: style.value, lyrics: lyrics.value};
    style.value = '';
    lyrics.value = '';
    this.controls.dispatchEvent(new Event('input', {bubbles: true}));
  }
  restoreInputs() {
    const snapshot = this.clearedText;
    this.clearedText = null;
    this.restoreOnStop = false;
    if (!snapshot) return;
    this.controls.querySelector('#music-style').value = snapshot.style;
    this.controls.querySelector('#music-lyrics').value = snapshot.lyrics;
    this.controls.dispatchEvent(new Event('input', {bubbles: true}));
  }
  prepareCancel() { this.restoreOnStop = Boolean(this.clearedText); }
  savedDraft() { return {...this.draft(), reference: this.reference || null}; }
  async setReference(file) {
    if (this.busy) return;
    const limit = this.capabilities?.max_reference_bytes || 32 * 1024 * 1024;
    if (file && (!file.size || file.size > limit)) {
      this.controls.querySelector('#music-reference').value = '';
      this.options.notify('error', `Choose a nonempty audio file up to ${Math.round(limit / 1024 / 1024)} MB.`); return;
    }
    if (file && file.type && !file.type.startsWith('audio/') && !/\.(wav|mp3|flac|m4a|ogg|aiff?|aac|opus)$/i.test(file.name)) {
      this.controls.querySelector('#music-reference').value = '';
      this.options.notify('error', 'Choose an audio recording.'); return;
    }
    this.closeScore(false);
    this.reference = file ? {blob: file, name: file.name || 'reference.wav'} : null;
    this.syncEngineMode();
    this.controls.querySelector('#music-reference').value = '';
    this.updateReference(); this.epoch++; this.sync();
    if (this.keeping) await this.store(() => saveMusicDraft(this.savedDraft())).catch(() => {});
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
  useScore(song) {
    if (this.busy || !song.score) return;
    closeMenus(); this.closeScore(false);
    const settings = song.settings || {};
    for (const key of ['style', 'lyrics', 'cot']) {
      if (settings[key] !== undefined) this.controls.querySelector('#music-' + key).value = settings[key];
    }
    this.selectWorkflow('generate');
    if (settings.instrumental) this.controls.querySelector('#music-lyrics').value = '';
    this.controls.querySelector('#music-cot').value = settings.cot === 'off' ? 'full' : settings.cot || 'full';
    this.controls.querySelector('#music-abc').value = song.score;
    this.controls.querySelector('.music-advanced-fields').open = true;
    this.epoch++; this.sync();
    this.controls.querySelector('#music-abc').focus();
    if (this.keeping) this.store(() => saveMusicDraft(this.savedDraft())).catch(() => {});
  }
  store(action) {
    const pending = this.storageQueue.then(action);
    this.storageQueue = pending.then(value => { this.storageFailure = ''; return value; }, error => {
      if (this.storageFailure !== error.message) this.options?.notify('error', 'Music could not be saved: ' + error.message);
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
      } catch (error) { this.options?.notify('error', 'Music could not be restored: ' + error.message); }
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
    for (const key of ['steps', 'cfg-scale']) this.controls.querySelector('#music-' + key).disabled = transcribe || scoreOnly;
    this.controls.querySelector('#music-count').disabled = transcribe;
    this.controls.querySelector('#music-seed').disabled = transcribe;
    const [hint, action, target] = EMPTY_COPY[draft.mode] || EMPTY_COPY.generate;
    this.querySelector('#music-empty-hint').textContent = hint;
    this.querySelector('#music-write span').textContent = action;
    this.querySelector('#music-write use').setAttribute('href', target === 'task' ? '#i-layout' : '#i-text');
    const seed = this.controls.querySelector('#music-seed').value.trim();
    this.controls.querySelector('#music-advanced-values').textContent = [
      transcribe || scoreOnly ? 'score only' : draft.steps + ' steps',
      transcribe || scoreOnly ? null : 'guidance ' + draft.cfg_scale,
      seed ? 'seed ' + seed : 'random seed',
    ].filter(Boolean).join(', ');
    const ready = transcribe ? Boolean(this.reference) : draft.style.trim() && (draft.instrumental || draft.lyrics.trim()) && (!needsReference || this.reference);
    this.controls.disabled = this.busy || this.hidden;
    this.querySelectorAll('[data-music-send]').forEach(button => { button.disabled = this.busy || button.dataset.stub === 'true' || button.dataset.scoreOnly === 'true'; });
    this.querySelectorAll('[data-music-use-score], [data-music-reuse]').forEach(button => { button.disabled = this.busy; });
    this.querySelectorAll('[data-music-cover]').forEach(button => { button.disabled = this.busy; });
    this.syncRunButton(draft, ready);
    const generating = this.pending || this.operation?.kind === 'music';
    const previewingGeneration = generating && this.showGeneration !== false;
    this.querySelector('.music-generation').hidden = !previewingGeneration;
    this.querySelector('.music-empty').hidden = this.songs.length > 0 || generating;
    for (const card of this.querySelectorAll('.music-song, .music-output-details')) card.hidden = previewingGeneration || card.dataset.songId !== this.selectedId;
    if (previewingGeneration || this.hidden) { this.closeDetails(false); this.closeScore(false); }
    const scores = this.songs.filter(song => !song.blob).length, recordings = this.songs.length - scores;
    this.querySelector('.music-count').textContent = scores ? `${recordings} song${recordings === 1 ? '' : 's'}, ${scores} score${scores === 1 ? '' : 's'}` : `${recordings} song${recordings === 1 ? '' : 's'}`;
    const progress = this.operation?.progress || {};
    this.querySelector('.music-generation-label').textContent = this.operation?.status === 'stopping' ? 'Stopping music generation'
      : progress.stage === 'preparing' ? 'Loading music model' : progress.stage === 'transcribing' ? 'Transcribing reference audio' : ({plan: 'Composing score', transcribe: 'Transcribing audio', cover: 'Creating cover song'}[this.operation?.mode || draft.mode] || 'Generating music');
    this.querySelector('.music-generation-detail').textContent = generating
      ? [musicModelName(this.operation?.model || this.capabilities?.name), progress.total > 0 ? `${progress.step} / ${progress.total} steps` : progress.step > 0 ? `${progress.step} tokens generated` : 'Composing your recording…'].filter(Boolean).join(' · ') : '';
    // A run in progress borrows the player's own timeline: the bar fills with the sampler's
    // share, and the line under it reads elapsed and percent instead of position and length.
    const bar = this.querySelector('.music-generation-timeline input');
    const percent = progress.total > 0 ? Math.min(100, Math.round(progress.step / progress.total * 100)) : null;
    bar.value = percent === null ? 0 : percent;
    bar.style.setProperty('--music-progress', (percent === null ? 0 : percent) + '%');
    bar.setAttribute('aria-valuetext', percent === null ? 'Progress not reported yet' : percent + '%');
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
    if (sub) sub.textContent = starting ? 'Preparing the request'
      : own ? 'Finished songs remain if you stop' : MODE_CAPTIONS[draft.mode] || '';
  }
  async cancel() {
    const operation = this.ownOperation;
    if (!operation || this.stopping) return;
    this.stopping = true;
    this.sync();
    try {
      const answer = await fetch('/api/v1/operations/' + encodeURIComponent(operation.id) + '/cancel', {method: 'POST'});
      if (!answer.ok) throw new Error((await answer.json()).error || 'The operation could not be stopped.');
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
    if (!Array.from(this.controls.querySelectorAll('input, textarea, select')).every(input => input.disabled || input.reportValidity())) return;
    const draft = this.draft();
    if (['generate', 'plan'].includes(draft.mode) && draft.abc.trim() && draft.cot === 'off') return this.options.notify('error', 'Choose melody or full planning for a supplied score.');
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
      if (!answer.ok) throw new Error(operation.error || 'Music generation could not start.');
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
        if (!response.ok) throw new Error('A Music batch recording could not be loaded.');
        await this.importSong({...operation, ...item, id, result_url: item.result_url, started_at: item.started_at, batch_total: null}, response);
      }
    } else await this.importSong(operation, answer);
  }
  async importSong(operation, answer) {
    if (this.songs.some(song => song.id === operation.id)) return;
    const scoreOnly = (answer.headers.get('content-type') || '').includes('application/json');
    const blob = scoreOnly ? null : await answer.blob();
    const metadataAnswer = await fetch(operation.result_url.replace(/\/result$/, '/metadata'), {cache: 'no-store'});
    if (!metadataAnswer.ok) throw new Error('Music generation details could not be loaded.');
    const details = await metadataAnswer.json();
    const finished = operation.completed_at || operation.finished_at;
    const generationSeconds = Number.isFinite(operation.started_at) && Number.isFinite(finished) && finished >= operation.started_at
      ? finished - operation.started_at : null;
    let song = {id: operation.id, blob, ...details, title: 'Untitled', settings: operation.settings,
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
  pausePlayback() { this.closeScore(false); this.querySelectorAll('audio').forEach(audio => audio.pause()); this.controls?.querySelectorAll('audio').forEach(audio => audio.pause()); }
  syncBackgroundPlayback() {
    const control = this.querySelector('.music-background-pause');
    const playing = [...this.querySelectorAll('.music-song audio')].find(audio => !audio.paused && !audio.ended);
    control.hidden = !playing || !playing.closest('.music-song').hidden;
    control.title = playing ? 'Pause ' + playing.getAttribute('aria-label') : '';
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
      pending.innerHTML = '<span class="still music-thumb-art"><span class="video-pending-indicator"></span><span>Generating</span></span><span class="no">NEW</span>';
      pending.setAttribute('aria-label', 'Show music generation'); pending.addEventListener('click', () => gallery.showPending()); strip.prepend(pending);
    }
    if (!gallery.pending && pending) pending.remove();
    else if (pending) { pending.classList.toggle('selected', gallery.pendingSelected); pending.setAttribute('aria-pressed', String(Boolean(gallery.pendingSelected))); }
    gallery.choose = id => this.selectSong(id);
    gallery.removeItem = id => this.removeSong(id);
    gallery.download = async ids => {
      for (const song of this.songs.filter(song => ids.includes(song.id))) {
        const link = document.createElement('a'); const url = URL.createObjectURL(song.blob || new Blob([song.score], {type: 'text/vnd.abc'}));
        link.href = url; link.download = `music-${song.seed}.${song.blob ? 'wav' : 'abc'}`; link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      }
    };
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
  async removeSong(id) {
    try {
      if (this.keeping) await this.store(() => deleteMusicSong(id));
      this.restoreEpoch = (this.restoreEpoch || 0) + 1;
      this.songs = this.songs.filter(song => song.id !== id);
      if (this.selectedId === id) this.selectedId = this.songs.at(-1)?.id;
      this.renderSongs(); localStorage.setItem('studio-music-changed', String(Date.now())); return true;
    } catch (_) { return false; }
  }
  renderChords(song) {
    const score = musicScore(song.score);
    const panel = document.createElement('section'); panel.className = 'music-chords'; panel.setAttribute('aria-label', 'Generated chords');
    const heading = document.createElement('h4'); heading.textContent = 'Chord chart'; panel.append(heading);
    const facts = document.createElement('p'); facts.className = 'music-score-facts';
    facts.textContent = [score.key && 'Key ' + score.key, score.meter, score.tempo && 'Tempo ' + score.tempo].filter(Boolean).join(' · '); panel.append(facts);
    if (!score.sections.length) {
      const note = document.createElement('p'); note.className = 'music-note';
      note.textContent = song.settings?.cot === 'off' ? 'Direct generation has no planned chord score.' : 'This score contains no chord symbols. Choose Melody and chords for a chord plan.';
      panel.append(note); return panel;
    }
    let barNumber = 0;
    for (const section of score.sections) {
      const label = document.createElement('h5'); label.textContent = section.name; panel.append(label);
      const bars = document.createElement('div'); bars.className = 'music-chord-bars';
      for (const symbols of section.bars) {
        const bar = document.createElement('div'); bar.className = 'music-chord-bar';
        const number = document.createElement('small'); number.textContent = String(++barNumber);
        const names = document.createElement('span'); names.textContent = symbols.join('  ·  ') || '—';
        bar.setAttribute('aria-label', `Bar ${barNumber}: ${symbols.join(', ') || 'no new chord symbol'}`);
        bar.append(number, names); bars.append(bar);
      }
      panel.append(bars);
    }
    const note = document.createElement('p'); note.className = 'music-note';
    note.textContent = (score.truncated ? 'Showing the first 256 bars. ' : '') + 'From the ABC score. — means no new chord symbol. The chart is not synchronized to the recording.';
    panel.append(note); return panel;
  }
  isCoverOperation(operation) {
    return ['image', 'rewrite'].includes(operation?.kind) && (operation.client_id?.startsWith(this.options?.clientId + ':music-cover:')
      || this.songs.some(song => song.coverClientId && [song.coverClientId, song.coverClientId + ':brief'].includes(operation.client_id)));
  }
  songTitle(song) { return typeof song?.title === 'string' && song.title.trim() ? song.title.trim().slice(0, 120) : 'Untitled'; }
  async renameSong(id, value) {
    const title = value.trim().slice(0, 120) || 'Untitled';
    const update = current => current ? {...current, title} : null;
    try {
      const updated = this.keeping ? await this.store(() => updateMusicSong(id, update)) : update(this.songs.find(song => song.id === id));
      if (!updated || !this.songs.some(song => song.id === id)) {
        this.options.notify('error', 'This song is no longer available.'); return;
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
    button.textContent = this.songTitle(song); button.title = 'Edit title';
    const input = document.createElement('input'); input.type = 'text'; input.className = 'music-title-input'; input.maxLength = 120;
    input.setAttribute('aria-label', 'Song title'); input.hidden = true;
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
    if (!answer.ok) throw new Error(operation.error || 'The artwork concept could not be prepared.');
    if (!operation.id || !operation.status_url) throw new Error('The artwork concept returned an invalid operation.');
    this.setOperation(operation);
    const owned = {id: operation.id, clientId: operation.client_id};
    const deadline = Date.now() + 180000;
    const timeout = async () => {
      if (owned.clientId === request.client_id) {
        try { await fetch('/api/v1/operations/' + encodeURIComponent(owned.id) + '/cancel', {method: 'POST', signal: AbortSignal.timeout(5000)}); } catch (_) { /* Only this request may be cancelled. */ }
      }
      throw new Error('Preparing the artwork concept timed out. Try again.');
    };
    while (!['succeeded', 'failed', 'cancelled'].includes(operation.status)) {
      if (Date.now() >= deadline) return timeout();
      await new Promise(resolve => setTimeout(resolve, 250));
      if (Date.now() >= deadline) return timeout();
      try {
        const status = await fetch(operation.status_url, {cache: 'no-store', signal: AbortSignal.timeout(Math.max(1, deadline - Date.now()))});
        if (!status.ok) throw new Error('The artwork concept status could not be loaded.');
        operation = await status.json();
      } catch (error) { if (Date.now() >= deadline) return timeout(); throw error; }
    }
    if (operation.status !== 'succeeded') throw new Error(operation.error || (operation.status === 'cancelled' ? 'Artwork preparation was cancelled.' : 'The artwork concept could not be prepared.'));
    if (!operation.result_url) throw new Error('The artwork concept is unavailable.');
    if (Date.now() >= deadline) return timeout();
    let brief;
    try {
      const result = await fetch(operation.result_url, {cache: 'no-store', signal: AbortSignal.timeout(Math.max(1, deadline - Date.now()))});
      if (!result.ok) throw new Error('The artwork concept could not be loaded.');
      brief = await result.json();
    } catch (error) { if (Date.now() >= deadline) return timeout(); throw error; }
    if (brief.cancelled) throw new Error('Artwork preparation was cancelled.');
    if (typeof brief.prompt !== 'string' || !brief.prompt.trim()) throw new Error('The artwork concept was empty or invalid.');
    return musicCoverImagePrompt(brief.prompt);
  }
  async generateCover(song) {
    if (this.busy) return;
    this.closeScore(false); this.coverStarting = true; this.sync(); this.options.onBusyChange();
    const clientId = this.options.clientId + ':music-cover:' + crypto.randomUUID();
    try {
      const stateAnswer = await fetch('/api/v1/studio', {cache: 'no-store'});
      if (!stateAnswer.ok) throw new Error('Image models could not be loaded.');
      const image = (await stateAnswer.json()).image;
      const mode = image?.capabilities?.modes.find(mode => mode.id === 'generate');
      const squares = (mode?.params.find(param => param.id === 'size')?.choices || [])
        .filter(choice => { const match = choice.value.match(/^(\d+)x(\d+)$/); return match && match[1] === match[2]; })
        .sort((a, b) => Math.abs(Number(a.value.split('x')[0]) - 512) - Math.abs(Number(b.value.split('x')[0]) - 512));
      if (!mode || !squares.length) throw new Error('The selected Image model does not offer square cover generation.');
      const current = await this.updateSong(song.id, item => item && (!item.coverClientId || item.coverError)
        ? {...item, coverClientId: clientId, coverRequestedAt: Date.now(), coverError: ''} : null);
      if (!current) throw new Error('This song was removed or another tab is already making its cover.');
      const defaults = Object.fromEntries(mode.params.filter(param => param.default != null).map(param => [param.id, param.default]));
      const parameters = {...defaults, mode: 'generate', backend: image.active, size: squares[0].value, count: 1, library_id: this.options.libraryId};
      let prompt = musicCoverPrompt(current);
      if (musicCoverNeedsRewrite(current)) prompt = await this.planCover({...parameters, kind: 'rewrite', prompt, client_id: clientId + ':brief'});
      const latest = await this.updateSong(song.id, item => item?.coverClientId === clientId
        ? {...item, coverRequestedAt: Date.now()} : null);
      if (!latest) throw new Error('This song was removed or its artwork request changed.');
      const answer = await fetch('/api/v1/operations', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({...parameters, kind: 'image', prompt, client_id: clientId})});
      const operation = await answer.json();
      if (!answer.ok) throw new Error(operation.error || 'Cover generation could not start.');
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
        ? {...current, coverClientId: '', coverError: 'Cover request expired. Generate it again.'} : null)
        .catch(error => this.options.notify('error', error.message)).finally(() => this.coverImports.delete(key));
    }
    for (const operation of operations) {
      const song = this.songs.find(song => song.coverClientId && song.coverClientId === operation.client_id);
      if (!song || !['succeeded', 'failed', 'cancelled'].includes(operation.status) || this.coverImports.has(operation.id)) continue;
      this.coverImports.add(operation.id);
      this.importCover(song, operation).then(() => this.coverFailures.delete(operation.id)).catch(error => {
        if (this.coverFailures.get(operation.id) !== error.message) this.options.notify('error', 'Cover could not be saved: ' + error.message);
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
            ? {...current, coverClientId: '', coverError: 'Cover result expired. Generate it again.'} : null);
          return;
        }
        throw new Error('The generated cover could not be loaded.');
      }
      const image = (await answer.json()).images?.[0];
      if (!image?.png_base64 || image.width !== image.height) {
        await this.updateSong(song.id, current => current?.coverClientId === clientId
          ? {...current, coverClientId: '', coverError: 'The Image model did not return a square cover. Try again.'} : null);
        return;
      }
      const response = await fetch('data:image/png;base64,' + image.png_base64);
      cover = {coverBlob: await response.blob(), coverPrompt: image.prompt, coverModel: operation.model, coverSeed: image.seed};
    }
    await this.updateSong(song.id, current => current?.coverClientId === clientId
      ? {...current, ...cover, coverClientId: '', coverError: operation.status === 'succeeded' ? '' : operation.error || 'Cover generation was cancelled.'} : null);
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
    content.setAttribute('aria-label', lyrics ? 'Song lyrics' : 'Song style');
    content.querySelector('.music-style-panel').hidden = lyrics;
    content.querySelector('.music-inline-lyrics').hidden = !lyrics;
    content.scrollTop = 0;
    card.querySelectorAll('[data-music-text-mode]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.musicTextMode === content.dataset.mode)));
    card.querySelector('.music-lyrics-toggle').title = lyrics ? 'Show style' : 'Show lyrics';
  }
  closeDetails(focus = true) {
    this.querySelectorAll('.music-details-sheet').forEach(sheet => { sheet.hidden = true; });
    this.querySelectorAll('[data-music-details]').forEach(button => button.setAttribute('aria-expanded', 'false'));
    if (focus) this.detailsTrigger?.focus();
  }
  openDetails(sheet, trigger) {
    this.closeScore(false); this.closeDetails(false); this.detailsTrigger = trigger;
    trigger.setAttribute('aria-expanded', 'true'); sheet.hidden = false;
    sheet.querySelector('.close').focus();
  }
  closeScore(focus = true) {
    for (const popover of this.querySelectorAll('.music-score-popover:popover-open')) {
      popover.returnFocus = focus;
      popover.hidePopover();
    }
  }
  openScore(popover, trigger) {
    this.closeScore(false); this.closeDetails(false);
    popover.returnFocus = true; popover.scoreTrigger = trigger;
    popover.showPopover();
    const paper = popover.querySelector('.music-notation');
    if (paper) this.updateScoreScrollHint(paper);
    this.engraveScore(popover.closest('.music-song'));
    popover.querySelector('.close').focus();
  }
  engraveScore(card) {
    const target = card.querySelector('.music-notation');
    if (!card.querySelector('.music-score-popover:popover-open') || !target || card.querySelector('[data-score-panel="sheet"]').hidden) return;
    if (target.dataset.started) { this.updateScoreScrollHint(target); return; }
    target.dataset.started = 'true';
    const song = this.songs.find(song => song.id === card.dataset.songId);
    const status = card.querySelector('.music-notation-status');
    renderNotation(target, song.score).then(warnings => {
      if (!target.isConnected) return;
      this.updateScoreScrollHint(target);
      status.textContent = warnings ? 'Some notation could not be interpreted. The complete ABC source is available below.' : '';
    }).catch(() => {
      status.textContent = 'Sheet music unavailable. The complete ABC source is available below.';
    });
  }
  updateScoreScrollHint(pane) {
    const hint = pane.parentElement.querySelector('.music-score-scroll-hint');
    if (hint) hint.hidden = pane.scrollHeight <= pane.clientHeight + 1 && pane.scrollWidth <= pane.clientWidth + 1;
  }
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
        const names = {'melody vocal': 'Vocal melody', 'melody instrumental': 'Instrumental melody', 'melody full': 'Full melody'};
        const label = names[stem.toLowerCase()] || stem.charAt(0).toUpperCase() + stem.slice(1);
        link.textContent = /\.midi?$/i.test(link.download) ? 'Download MIDI · ' + label : /\.lab$/i.test(link.download) ? 'Download LAB · ' + label : 'Download ' + link.download;
        links.append(link);
      } catch (_) { /* An unavailable export must not hide the composition. */ }
    }
    return links;
  }
  renderScore(song) {
    const section = document.createElement('section'); section.className = 'music-composition music-score-popover';
    section.setAttribute('popover', 'auto'); section.setAttribute('role', 'dialog');
    section.setAttribute('aria-label', 'Sheet music and chords');
    const heading = document.createElement('h4'); heading.textContent = 'Sheet music and chords'; section.append(heading);
    const close = document.createElement('button'); close.type = 'button'; close.className = 'icon-btn close'; close.setAttribute('aria-label', 'Close sheet music');
    close.innerHTML = '<svg class="icon" aria-hidden="true"><use href="#i-x"/></svg>';
    close.addEventListener('click', () => this.closeScore()); section.append(close);
    section.addEventListener('toggle', event => {
      if (event.newState === 'closed' && section.returnFocus && !this.hidden
        && (document.activeElement === document.body || section.contains(document.activeElement))) section.scoreTrigger?.focus();
    });
    if (!song.score?.trim()) {
      const note = document.createElement('p'); note.className = 'music-note';
      note.textContent = 'No score was returned for this song. Choose Melody or Melody and chords in Composition to generate a score.';
      section.append(note); return section;
    }
    const tabs = document.createElement('div'); tabs.className = 'music-score-tabs'; tabs.setAttribute('role', 'tablist'); tabs.setAttribute('aria-label', 'Composition view');
    const sheet = document.createElement('div'); sheet.dataset.scorePanel = 'sheet'; sheet.setAttribute('role', 'tabpanel');
    const status = document.createElement('p'); status.className = 'music-note music-notation-status'; status.setAttribute('role', 'status'); status.textContent = 'Preparing sheet music…';
    const paper = document.createElement('div'); paper.className = 'music-notation'; paper.setAttribute('aria-label', 'Generated sheet music'); paper.setAttribute('role', 'region'); paper.tabIndex = 0; paper.addEventListener('keydown', event => this.scrollScore(event));
    const hint = document.createElement('p'); hint.className = 'music-note music-score-scroll-hint'; hint.hidden = true;
    hint.id = 'music-score-scroll-' + this.songs.indexOf(song); hint.textContent = 'Scroll for the full score. Focus the score to use arrow keys.';
    paper.setAttribute('aria-describedby', hint.id);
    sheet.append(status, paper, hint);
    const chords = this.renderChords(song); chords.dataset.scorePanel = 'chords'; chords.setAttribute('role', 'tabpanel'); chords.tabIndex = 0; chords.addEventListener('keydown', event => this.scrollScore(event)); chords.hidden = true;
    const uid = 'music-score-' + this.songs.indexOf(song);
    for (const [mode, label, panel] of [['sheet', 'Sheet music', sheet], ['chords', 'Chords', chords]]) {
      const button = document.createElement('button'); button.type = 'button'; button.className = 'text-btn';
      button.id = uid + '-' + mode + '-tab'; panel.id = uid + '-' + mode;
      button.setAttribute('role', 'tab'); button.setAttribute('aria-controls', panel.id); panel.setAttribute('aria-labelledby', button.id);
      button.setAttribute('aria-selected', String(mode === 'sheet')); button.tabIndex = mode === 'sheet' ? 0 : -1; button.textContent = label;
      button.addEventListener('click', () => {
        for (const tab of tabs.children) { const active = tab === button; tab.setAttribute('aria-selected', String(active)); tab.tabIndex = active ? 0 : -1; }
        sheet.hidden = mode !== 'sheet'; chords.hidden = mode !== 'chords'; this.engraveScore(section.closest('.music-song'));
      });
      tabs.append(button);
    }
    tabs.addEventListener('keydown', event => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault(); const buttons = [...tabs.children];
      const next = event.key === 'Home' ? buttons[0] : event.key === 'End' ? buttons.at(-1) : buttons.find(button => button !== event.target);
      next?.click(); next?.focus();
    });
    const raw = document.createElement('details'); raw.className = 'music-score-source';
    const summary = document.createElement('summary'); summary.textContent = 'ABC source';
    const source = document.createElement('pre'); source.textContent = song.score;
    const download = document.createElement('a'); download.className = 'text-btn'; download.textContent = 'Download ABC'; download.download = `music-${song.seed}.abc`;
    const url = URL.createObjectURL(new Blob([song.score], {type: 'text/vnd.abc;charset=utf-8'})); this.urls.push(url); download.href = url;
    const edit = document.createElement('button'); edit.type = 'button'; edit.className = 'text-btn'; edit.textContent = song.blob ? 'Edit and render score' : 'Render score'; edit.dataset.musicUseScore = ''; edit.addEventListener('click', () => this.useScore(song));
    raw.append(summary, download, source);
    const note = document.createElement('p'); note.className = 'music-note'; note.textContent = 'The full score returned by YuE2, including its generated voices. Not synchronized to audio playback.';
    section.append(tabs, edit, this.scoreArtifacts(song), sheet, chords, raw, note); return section;
  }
  renderPlayer(audio, song) {
    const player = document.createElement('div'); player.className = 'music-player';
    const timeline = document.createElement('div'); timeline.className = 'music-timeline';
    const seek = document.createElement('input'); seek.type = 'range'; seek.min = '0'; seek.max = '0'; seek.step = '0.1'; seek.value = '0';
    seek.setAttribute('aria-label', 'Playback position');
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
    const back = control('Back 5 seconds', '<path d="M6 7a8 8 0 1 1-1 10M6 3v5H1" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/><text x="12" y="16" text-anchor="middle" font-size="10" font-family="sans-serif">5</text>');
    const toggle = control('Play', ''); toggle.classList.add('music-play');
    const forward = control('Forward 5 seconds', '<path d="M18 7a8 8 0 1 0 1 10M18 3v5h5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/><text x="12" y="16" text-anchor="middle" font-size="10" font-family="sans-serif">5</text>');
    transport.append(back, toggle, forward);
    const hasLyrics = !song.settings?.instrumental && Boolean(song.settings?.lyrics?.trim());
    const lyricsShown = hasLyrics && this.lyricsShown?.has(song.id);
    const lyrics = document.createElement('button'); lyrics.type = 'button'; lyrics.className = 'icon-btn music-lyrics-toggle';
    lyrics.setAttribute('aria-label', 'Lyrics'); lyrics.dataset.musicTextMode = 'lyrics'; lyrics.disabled = !hasLyrics;
    lyrics.innerHTML = '<svg class="icon" aria-hidden="true"><use href="#i-text"/></svg>';
    lyrics.setAttribute('aria-pressed', String(Boolean(lyricsShown))); lyrics.setAttribute('aria-controls', 'music-text-' + song.id);
    lyrics.title = lyricsShown ? 'Show style' : 'Show lyrics';
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
      seek.setAttribute('aria-valuetext', `${clock(position)} of ${clock(length)}`);
      elapsed.textContent = clock(position); remaining.textContent = '−' + clock(length - position);
      back.disabled = toggle.disabled = forward.disabled = !ready;
      const playing = !audio.paused && !audio.ended;
      toggle.setAttribute('aria-label', playing ? 'Pause' : 'Play'); toggle.title = playing ? 'Pause' : 'Play';
      toggle.setAttribute('aria-pressed', String(playing));
      toggle.innerHTML = `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${playing ? '<path d="M7 5h3v14H7zm7 0h3v14h-3z"/>' : '<path d="m8 5 11 7-11 7z"/>'}</svg>`;
      if (audio.error) { error.textContent = 'This song could not be played.'; error.hidden = false; }
    };
    const move = value => { if (!duration() || audio.error) return; audio.currentTime = Math.max(0, Math.min(duration(), value)); sync(); };
    back.addEventListener('click', () => move(audio.currentTime - 5));
    forward.addEventListener('click', () => move(audio.currentTime + 5));
    seek.addEventListener('input', () => move(Number(seek.value)));
    toggle.addEventListener('click', () => {
      if (!audio.paused) { audio.pause(); return; }
      if (audio.ended) move(0);
      error.hidden = true;
      audio.play().catch(() => { error.textContent = 'This song could not be played.'; error.hidden = false; sync(); });
    });
    audio.addEventListener('loadedmetadata', () => { if (!audio.error) error.hidden = true; });
    for (const event of ['loadedmetadata', 'durationchange', 'timeupdate', 'play', 'pause', 'ended', 'error', 'emptied', 'loadstart']) audio.addEventListener(event, sync);
    player.append(timeline, transport, error); sync(); return player;
  }
  renderSongs() {
    this.lyricsShown?.forEach(id => { if (!this.songs.some(song => song.id === id)) this.lyricsShown.delete(id); });
    this.closeDetails(false);
    this.closeScore(false);
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
    const sheets = this.querySelector('.music-detail-sheets'); sheets.replaceChildren();
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
        cover.src = coverUrl; cover.alt = 'Generated album cover'; artwork.prepend(cover); artwork.classList.add('has-cover');
      }
      const playback = document.createElement('span'); playback.className = 'music-playback-label'; playback.textContent = hasAudio ? 'Ready to play' : 'Score only';
      artwork.append(playback);
      if (song.coverClientId && !song.coverError) {
        const pending = document.createElement('span'); pending.className = 'music-cover-pending'; pending.textContent = 'Making cover…'; artwork.append(pending);
      }
      const syncPlayback = () => {
        const playing = !audio.paused && !audio.ended;
        card.classList.toggle('is-playing', playing);
        playback.textContent = playing ? 'Now playing' : audio.ended ? 'Playback finished' : 'Ready to play';
        this.syncBackgroundPlayback();
      };
      audio.onplay = () => {
        this.querySelectorAll('audio').forEach(other => { if (other !== audio) other.pause(); });
        this.controls.querySelectorAll('audio').forEach(reference => reference.pause());
        syncPlayback();
      };
      audio.onpause = audio.onended = syncPlayback;
      card.classList.toggle('is-playing', !audio.paused && !audio.ended);
      if (!audio.paused && !audio.ended) playback.textContent = 'Now playing';
      const style = document.createElement('p'); style.className = 'music-song-style'; style.textContent = song.settings?.style || 'Song';
      const download = document.createElement('a'); download.className = 'icon-btn';
      download.href = url; download.download = `music-${song.seed}.${hasAudio ? 'wav' : 'abc'}`; download.setAttribute('aria-label', hasAudio ? 'Download WAV' : 'Download ABC'); download.title = hasAudio ? 'Download WAV' : 'Download ABC'; download.innerHTML = '<svg class="icon" aria-hidden="true"><use href="#i-download"></use></svg>';
      const details = document.createElement('section');
      details.hidden = true; details.id = 'music-details-' + this.songs.indexOf(song);
      details.setAttribute('role', 'region'); details.setAttribute('aria-label', 'Music details');
      const summary = document.createElement('h3'); summary.textContent = hasAudio ? 'Song details' : 'Score details';
      details.append(summary);
      const metadata = document.createElement('dl');
      for (const [name, value] of [['Model', musicModelName(song.model)], ['Seed', song.seed], ['Length', hasAudio ? song.seconds.toFixed(1) + ' seconds' : null], ['Generation time', Number.isFinite(song.generationSeconds) ? song.generationSeconds.toFixed(1) + ' seconds' : null],
        ['Audio', hasAudio ? '48 kHz · stereo · WAV' : 'Score only · ABC'], ['Workflow', ({generate: 'Create song', plan: 'Compose score', transcribe: 'Transcribe audio', cover: 'Cover song'})[song.settings?.mode || 'generate']], ['Reference', song.settings?.reference_name], ['Instrumental', song.settings?.instrumental ? 'Yes' : null], ['Synthesis steps', hasAudio ? song.settings?.steps || 32 : null], ['Guidance', hasAudio ? song.settings?.cfg_scale ?? 1 : null], ['Style', song.settings?.style], ['Lyrics', song.settings?.lyrics], ['Planning', ({full: 'Melody and chords', melody: 'Melody', off: 'Direct generation'})[song.metadata?.config?.cot || song.settings?.cot]], ['Cover model', song.coverModel], ['Cover seed', song.coverSeed]]) {
        if (value === undefined || value === null || value === '') continue;
        const label = document.createElement('dt'); label.textContent = name;
        const data = document.createElement('dd'); data.textContent = String(value); metadata.append(label, data);
      }
      details.append(metadata);
      details.className = 'sheet music-details-sheet';
      const close = document.createElement('button'); close.type = 'button'; close.className = 'icon-btn close'; close.setAttribute('aria-label', 'Close music details'); close.innerHTML = '<svg class="icon" aria-hidden="true"><use href="#i-x"></use></svg>';
      close.addEventListener('click', () => this.closeDetails()); details.append(close);
      details.addEventListener('keydown', event => { if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); this.closeDetails(); } });
      const score = document.createElement('details'); const scoreHeading = document.createElement('summary'); scoreHeading.textContent = 'ABC score';
      const notation = document.createElement('pre'); notation.textContent = song.score || 'No score was generated.';
      score.append(scoreHeading, notation); details.append(score);
      const send = menuItem('music', 'Send to Video', () => {
        if (this.busy || song.stub || !hasAudio) return;
        this.options.onSendToVideo({blob: song.blob, name: `music-${song.seed}.wav`}).catch(error => this.options.notify('error', error.message));
      });
      send.dataset.musicSend = ''; send.dataset.stub = String(song.stub); send.dataset.scoreOnly = String(!hasAudio);
      send.disabled = this.busy || song.stub || !hasAudio;
      const remove = document.createElement('button'); remove.type = 'button'; remove.className = 'icon-btn danger'; remove.setAttribute('aria-label', 'Delete'); remove.title = 'Delete song';
      remove.innerHTML = '<svg class="icon" aria-hidden="true"><use href="#i-trash"></use></svg>';
      remove.addEventListener('click', () => this.removeSong(song.id));
      const cover = menuItem('image', song.coverBlob ? 'Regenerate artwork' : 'Generate artwork', () => this.generateCover(song));
      cover.dataset.musicCover = ''; cover.title = 'Generate a square cover from this song (Alt+C)'; cover.setAttribute('aria-keyshortcuts', 'Alt+C');
      const facts = document.createElement('div'); facts.className = 'facts num'; facts.setAttribute('aria-label', 'Music metadata');
      for (const value of [musicModelName(song.model), hasAudio ? song.seconds.toFixed(1) + ' s' : 'Score only', Number.isFinite(song.generationSeconds) ? 'Generated in ' + song.generationSeconds.toFixed(1) + ' s' : hasAudio ? '48 kHz · stereo' : 'ABC notation', 'Seed ' + song.seed]) { const fact = document.createElement('span'); fact.textContent = value; facts.append(fact); }
      const about = document.createElement('div'); about.className = 'about';
      const caption = document.createElement('p'); caption.className = 'prompt-line'; caption.textContent = song.settings?.style || song.settings?.reference_name || (hasAudio ? 'Song' : 'Music score'); caption.title = caption.textContent;
      caption.setAttribute('role', 'button'); caption.tabIndex = 0; caption.dataset.musicDetails = ''; caption.setAttribute('aria-controls', details.id); caption.setAttribute('aria-expanded', 'false');
      caption.addEventListener('click', () => this.openDetails(details, caption));
      caption.addEventListener('keydown', event => { if (['Enter', ' '].includes(event.key)) { event.preventDefault(); this.openDetails(details, caption); } });
      about.append(caption, facts);
      const actions = document.createElement('div'); actions.className = 'actions music-song-actions';
      const useScore = document.createElement('button'); useScore.type = 'button'; useScore.className = 'btn quiet'; useScore.innerHTML = '<svg class="icon" aria-hidden="true"><use href="#i-music"/></svg>Score'; useScore.addEventListener('click', () => this.openScore(composition, useScore));
      const more = document.createElement('div'); more.className = 'menu-anchor';
      const toggle = document.createElement('button'); toggle.type = 'button'; toggle.className = 'icon-btn'; toggle.setAttribute('aria-label', 'More actions'); toggle.title = 'More actions';
      const menu = document.createElement('div'); menu.className = 'menu up'; menu.id = 'music-actions-' + this.songs.indexOf(song); menu.hidden = true; menu.setAttribute('role', 'menu'); menu.setAttribute('aria-label', 'Music actions');
      toggle.setAttribute('aria-controls', menu.id); toggle.setAttribute('aria-expanded', 'false'); toggle.innerHTML = '<svg class="icon" aria-hidden="true"><use href="#i-more"></use></svg>'; toggle.addEventListener('click', () => toggleMenu(menu));
      const composition = this.renderScore(song);
      if (song.score?.trim()) menu.append(menuItem('music', 'Sheet music and chords', () => this.openScore(composition, toggle)));
      menu.append(cover, send);
      const reuse = menuItem('text', 'Reuse style and lyrics', () => { if (this.busy) return; for (const key of ['style', 'lyrics']) this.controls.querySelector('#music-' + key).value = song.settings?.[key] || ''; if (song.settings?.instrumental) this.controls.querySelector('#music-lyrics').value = ''; this.selectWorkflow('generate'); this.controls.dispatchEvent(new Event('input', {bubbles: true})); this.controls.querySelector('#music-style').focus(); }); reuse.dataset.musicReuse = ''; menu.append(reuse); more.append(toggle, menu);
      if (song.score) actions.append(useScore);
      const rule = document.createElement('span'); rule.className = 'rule'; rule.setAttribute('aria-hidden', 'true');
      actions.append(more, rule, download, remove);
      const bar = document.createElement('section'); bar.className = 'stage-bar music-output-details'; bar.dataset.songId = song.id; bar.setAttribute('aria-label', 'Music preview details'); bar.append(about, actions); bars.append(bar); sheets.append(details);
      const body = document.createElement('div'); body.className = 'music-track-body';
      body.append(title);
      if (song.stub) { const warning = document.createElement('p'); warning.className = 'music-note music-stub-note'; warning.textContent = hasAudio ? 'Stub preview · no music generated' : 'Stub score preview · no model used'; body.append(warning); }
      body.append(hasAudio ? renderSongText(song, this.lyricsShown?.has(song.id)) : style);
      if (hasAudio) body.append(retained?.controls || this.renderPlayer(audio, song), audio);
      body.append(composition);
      if (song.coverError) { const error = document.createElement('p'); error.className = 'music-error'; error.textContent = song.coverError; body.append(error); }
      card.append(artwork, body); list.append(card);
      const thumb = document.createElement('button'); thumb.type = 'button'; thumb.className = 'frame music-thumb'; thumb.dataset.songId = song.id;
      const number = this.songs.indexOf(song) + 1;
      thumb.setAttribute('aria-label', `Select ${hasAudio ? 'song' : 'score'} ${number}`); thumb.title = this.songTitle(song);
      const still = document.createElement('span'); still.className = 'still music-thumb-art';
      if (song.coverBlob) { const image = document.createElement('img'); image.src = this.coverUrls.get(song.id); image.alt = ''; still.append(image); }
      else { const mark = document.createElement('span'); mark.textContent = '♫'; mark.className = 'music-thumb-note'; still.append(mark); }
      const playing = document.createElement('span'); playing.className = 'music-playing-state'; playing.hidden = true;
      render(playingMark(), playing); still.append(playing);
      const label = document.createElement('span'); label.className = 'no'; label.textContent = `${String(number).padStart(2, '0')} · ${hasAudio ? song.seconds.toFixed(0) + 's' : 'SCORE'}`;
      thumb.append(still, label); thumb.addEventListener('click', () => this.selectSong(song.id)); strip.append(thumb);
    }
    this.sync(); this.syncGallery();
  }
}
customElements.define('music-studio', MusicStudio);
