import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

// ---- i18n module ----
// Loads translation data from the official /i18n endpoint (which aggregates all
// custom nodes' locales/ folders) and provides a $t() helper for UI strings.
//
// Translation files live in locales/<lang>/:
//   - nodeDefs.json : node titles, widget names and tooltips (applied by ComfyUI)
//   - main.json     : custom UI strings (buttons, panel text, status, tooltips)
//
// The /i18n endpoint returns a structure like:
//   { "en": { "nodeDefs": {...}, "ui": {...} }, "zh": { "nodeDefs": {...}, "ui": {...} } }

let _translations = null;
let _loadPromise = null;

// Resolve the current ComfyUI interface language code (e.g. "en", "zh").
//
// In the newer Vue-based ComfyUI frontend the active locale is stored in the
// "Comfy.Locale" setting (read via app.ui.settings.getSettingValue), not on
// app.i18n. Reading app.i18n.locale there returns undefined, which would make
// every lookup fall back to English. We therefore prefer the settings value and
// keep app.i18n as a fallback for older frontends.
function getLocale() {
    try {
        const fromSettings = app.ui?.settings?.getSettingValue?.("Comfy.Locale");
        if (fromSettings) return String(fromSettings).toLowerCase();
        const locale = app.i18n?.locale || app.i18n?.getLocale?.() || "";
        return String(locale).toLowerCase();
    } catch (e) {
        return "";
    }
}

// Returns true when the interface language is Chinese.
export function isChinese() {
    return getLocale().startsWith("zh");
}

// Load all translations from the /i18n endpoint (cached).
export async function loadTranslations() {
    if (_translations) return _translations;
    if (_loadPromise) return _loadPromise;
    _loadPromise = (async () => {
        try {
            const res = await api.fetchApi("/i18n", { method: "GET" });
            _translations = await res.json();
        } catch (e) {
            console.error("[zyd232] Failed to load i18n translations:", e);
            _translations = {};
        }
        return _translations;
    })();
    return _loadPromise;
}

// Translate a UI string key using the current language.
// Falls back to English, then to the key itself.
export async function $t(key) {
    const translations = await loadTranslations();
    const locale = getLocale();
    const lang = translations[locale] || translations[locale.split("-")[0]] || {};
    const ui = lang.ui || {};
    if (ui[key]) return ui[key];
    // Fallback to English
    const en = translations.en?.ui || {};
    if (en[key]) return en[key];
    return key;
}

// Synchronous variant for callers that already awaited loadTranslations().
export function $tSync(key) {
    const translations = _translations || {};
    const locale = getLocale();
    const lang = translations[locale] || translations[locale.split("-")[0]] || {};
    const ui = lang.ui || {};
    if (ui[key]) return ui[key];
    const en = translations.en?.ui || {};
    if (en[key]) return en[key];
    return key;
}
