// UI copy for the components. The one implementation lives in the page's classic script,
// because the page's own inline script needs it at parse time; this module hands the same
// functions to the components. The server inlines the chosen table and, for a translated
// page, the English one, so a key no translator has reached yet falls back to real copy.

const {t, plural, number, date, locale, label} = window.studioI18n;
export {t, plural, number, date, locale, label};
