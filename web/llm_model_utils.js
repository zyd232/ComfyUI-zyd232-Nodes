import { api } from "../../../scripts/api.js";

// Shared helpers for LLM nodes (LLM Text Generator & LLM Unload) that fetch
// model lists from the LLM server and manage the Model Select dropdowns.
// Keeping these in one module avoids duplicating the same logic across nodes.

/**
 * Load a config preset by name from the backend.
 * @param {string} configName - Preset name.
 * @returns {Promise<object|null>} The config object, or null on failure.
 */
export async function loadConfig(configName) {
    try {
        const res = await api.fetchApi(`/zyd232/load_config?config_name=${encodeURIComponent(configName)}`, { method: "GET" });
        const data = await res.json();
        if (!data.success) return null;
        return data.config || null;
    } catch (e) {
        console.error("[zyd232 LLM] Failed to load config:", e);
        return null;
    }
}

/**
 * Fetch the model list from the LLM server via the shared /zyd232/fetch_models
 * endpoint.
 * @param {string} baseUrl - Server base URL.
 * @param {string} apiKey - Resolved API key.
 * @param {string} configName - Config preset name (for api_key fallback).
 * @returns {Promise<string[]>} Array of model ids (empty on failure).
 */
export async function fetchModels(baseUrl, apiKey, configName) {
    try {
        const response = await api.fetchApi("/zyd232/fetch_models", {
            method: "POST",
            body: JSON.stringify({
                base_url: baseUrl || "",
                api_key: apiKey || "",
                config_name: configName || "Default"
            })
        });
        const data = await response.json();
        return (data.success && Array.isArray(data.models)) ? data.models : [];
    } catch (e) {
        console.error("[zyd232 LLM JS] Error fetching models:", e);
        return [];
    }
}

/**
 * Show the transient "Fetching models..." state on a dropdown.
 * @param {object} selectWidget - The combo widget.
 */
export function setDropdownFetching(selectWidget, fetchingText) {
    if (!selectWidget) return;
    selectWidget.options.values = [fetchingText];
    selectWidget.value = fetchingText;
}

/**
 * Show only "Fetch failed" on a dropdown, dropping any stale cached list.
 * @param {object} selectWidget - The combo widget.
 */
export function setDropdownFailed(selectWidget, failedText) {
    if (!selectWidget) return;
    selectWidget.options.values = [failedText];
    selectWidget.value = failedText;
}
