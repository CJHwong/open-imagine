// A time figure the page shows for a run, rounded to a step a reader can act on.

import {t} from './i18n.js';

export function spell(seconds) {
  if (seconds < 90) return t('form.time.seconds', {seconds: Math.max(5, Math.round(seconds / 5) * 5)});
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round((seconds % 60) / 15) * 15;
  if (rest && rest < 60) return t('form.time.minutesSeconds', {minutes: minutes, seconds: rest});
  return t('form.time.minutes', {minutes: minutes + (rest ? 1 : 0)});
}
