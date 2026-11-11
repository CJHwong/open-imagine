import {t} from './i18n.js';

function textElement(tag, className, text) {
  const element = document.createElement(tag);
  element.className = className;
  element.textContent = text;
  return element;
}

function lyricLines(words) {
  const lyrics = document.createElement('div'); lyrics.className = 'music-inline-lyrics';
  for (const raw of words.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) continue;
    const section = line.match(/^\[([^\]]+)\]$/);
    lyrics.append(section
      ? textElement('h3', 'music-lyrics-section', section[1])
      : textElement('p', 'music-lyrics-line', line));
  }
  return lyrics;
}

export function renderSongText(song, lyricsShown = false) {
  const words = song.settings?.instrumental ? '' : song.settings?.lyrics || '';
  const showingLyrics = lyricsShown && Boolean(words.trim());
  const region = document.createElement('section'); region.className = 'music-track-text'; region.id = 'music-text-' + song.id;
  region.tabIndex = 0; region.setAttribute('role', 'region'); region.setAttribute('aria-label', showingLyrics ? t('music.text.lyrics_label') : t('music.text.style_label'));
  region.dataset.mode = showingLyrics ? 'lyrics' : 'style';
  const style = textElement('p', 'music-song-style music-style-panel', song.settings?.style || t('music.common.song'));
  style.hidden = showingLyrics;
  const lyrics = lyricLines(words); lyrics.hidden = !showingLyrics;
  if (!words.trim()) lyrics.append(textElement('p', 'music-note music-lyrics-empty', song.settings?.instrumental ? t('music.meta.instrumental') : t('music.text.no_lyrics')));
  region.append(style, lyrics);
  return region;
}
