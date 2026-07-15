import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";
import { createFullWidthButton, createMultiButtonRow } from "./button_utils.js";

const MODEL_PLACEHOLDER = "Choose a model from the list";
const API_KEY_MASKED = "********";
const CONFIG_DEFAULT = "Default";

// Sanitize configuration file name: remove illegal characters and reserved names
function sanitizeConfigName(name) {
    let cleaned = (name || "").trim();
    // Remove illegal file system characters : / \ : * ? " < > |
    cleaned = cleaned.replace(/[\\/:*?"<>|]/g, "");
    // Remove leading/trailing dots or spaces (Windows reserved)
    cleaned = cleaned.replace(/^[\s.]+|[\s.]+$/g, "");
    // Prevent reserved Windows filenames (CON, PRN, AUX, NUL, COM1-9, LPT1-9)
    const reservedRegex = /^(CON|PRN|AUX|NUL|COM\d|LPT\d)$/i;
    if (reservedRegex.test(cleaned)) {
        cleaned = "_" + cleaned;
    }
    return cleaned || CONFIG_DEFAULT;
}

// All widget names that will be saved into the configuration file
const SAVED_WIDGETS = [
    "base_url",
    "api_key",
    "model",
    "model_NoVision",
    "system_prompt",
    "user_prompt",
    "temperature",
    "top_k",
    "seed",
    "context_length",
    "thinking",
    "think_start_tag",
    "think_end_tag",
    "clean_comfy_vram_before_gen",
    "unload_after_gen",
    "unload_endpoint",
    "llama_cpp_unload",
    "llama_endpoint",
    "cache_prompt"
];

// Update a widget's value based on widget type, handling type coercion
function setWidgetValue(widget, value) {
    if (!widget) return;
    if (widget.type === "toggle") {
        widget.value = !!value;
    } else if (widget.type === "number" || widget.type === "combo_number") {
        const num = Number(value);
        widget.value = isNaN(num) ? widget.options?.DefaultValue ?? 0 : num;
    } else if (widget.type === "text" || widget.type === "string") {
        widget.value = value ?? "";
    } else if (widget.type === "customtext" || widget.type === "converted-widget") {
        widget.value = value ?? "";
    } else {
        widget.value = value ?? "";
    }
}

app.registerExtension({
    name: "zyd232.LLMModelFetcher",
    async nodeCreated(node) {
        if (node.comfyClass !== "zyd232 LLMGenerator") return;

        // ---- Core widgets (already existed) ----
        const baseUrlWidget = node.widgets.find(w => w.name === "base_url");
        const apiKeyWidget = node.widgets.find(w => w.name === "api_key");
        const modelWidget = node.widgets.find(w => w.name === "model");
        const modelNoVisionWidget = node.widgets.find(w => w.name === "model_NoVision");
        const modelSelectWidget = node.widgets.find(w => w.name === "model_select");
        const modelNoVisionSelectWidget = node.widgets.find(w => w.name === "model_NoVision_select");

        // ---- Configuration management widgets ----
        const configSelectWidget = node.widgets.find(w => w.name === "config_select");
        const configNameWidget = node.widgets.find(w => w.name === "config_name");

        // Remove old boolean-based widgets (config_refresh, config_save, config_delete, force_refresh)
        // and replace them with proper button widgets
        for (const oldName of ["config_refresh", "config_save", "config_delete", "force_refresh"]) {
            const idx = node.widgets.findIndex(w => w.name === oldName);
            if (idx !== -1) {
                node.widgets.splice(idx, 1);
            }
        }

        // Collect widget reference by name for batch save / load
        function getWidgetMap() {
            const map = {};
            for (const name of SAVED_WIDGETS) {
                map[name] = node.widgets.find(w => w.name === name);
            }
            return map;
        }

        // ============ Helpers ============
        async function listConfigs() {
            try {
                const res = await api.fetchApi("/zyd232/list_configs", { method: "GET" });
                const data = await res.json();
                return (data.success && Array.isArray(data.configs)) ? data.configs : [];
            } catch (e) {
                console.error("[zyd232 LLM] Failed to list configs:", e);
                return [];
            }
        }

        async function saveConfig(configName) {
            try {
                const body = { config_name: configName };
                const widgetMap = getWidgetMap();
                for (const name of SAVED_WIDGETS) {
                    if (!widgetMap[name]) continue;
                    let value = widgetMap[name].value;
                    // When api_key on canvas is the masked placeholder, we should NOT
                    // overwrite the stored value (the skip logic is handled in backend
                    // as a fallback, but for extra edge-suppression we also pass a flag.)
                    let skip = false;
                    if (name === "api_key" && value === API_KEY_MASKED) {
                        skip = true;
                    }
                    body[name] = skip ? undefined : value;
                    body[name + "_skip"] = skip;
                }

                const res = await api.fetchApi("/zyd232/save_config", {
                    method: "POST",
                    body: JSON.stringify(body)
                });
                const data = await res.json();
                return data;
            } catch (e) {
                console.error("[zyd232 LLM] Failed to save config:", e);
                return { success: false, error: e.message || "Network error" };
            }
        }

        async function deleteConfig(configName) {
            try {
                const res = await api.fetchApi("/zyd232/delete_config", {
                    method: "POST",
                    body: JSON.stringify({ config_name: configName })
                });
                const data = await res.json();
                return data;
            } catch (e) {
                console.error("[zyd232 LLM] Failed to delete config:", e);
                return { success: false, error: e.message || "Network error" };
            }
        }

        async function loadConfig(configName) {
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

        async function refreshConfigCombo() {
            if (!configSelectWidget) return;
            const configs = await listConfigs();
            const comboValues = [...configs];
            // Always include the "Default" entry so the user always has a base option to fall back
            if (!comboValues.includes(CONFIG_DEFAULT)) {
                comboValues.unshift(CONFIG_DEFAULT);
            }
            configSelectWidget.options.values = comboValues;
            if (node.setSize) node.setSize(node.size);
        }

        // ---- Action handlers for ButtonRow ----
        async function handleSaveConfig() {
            if (!configNameWidget || !configSelectWidget) return;
            const rawName = configNameWidget.value || CONFIG_DEFAULT;
            const sanitized = sanitizeConfigName(rawName);

            // If sanitization modified the value, update widget display
            if (sanitized !== rawName) {
                configNameWidget.value = sanitized;
            }

            const result = await saveConfig(sanitized);
            if (result && result.success) {
                // After save, mask api_key display and refresh combo
                apiKeyWidget.value = API_KEY_MASKED;
                await refreshConfigCombo();
                // If this is a newly created name, preselect it in combo
                if (!configSelectWidget.options.values.includes(sanitized)) {
                    configSelectWidget.options.values.push(sanitized);
                }
                configSelectWidget.value = sanitized;
                if (node.setSize) node.setSize(node.size);
                console.log("[zyd232 LLM] Config saved successfully:", sanitized);
            } else {
                alert(`Failed to save config: ${result?.error || "Unknown error"}`);
            }
        }

        async function handleDeleteConfig() {
            if (!configSelectWidget || !configNameWidget) return;
            const target = configSelectWidget.value || configNameWidget.value || CONFIG_DEFAULT;
            const sanitized = sanitizeConfigName(target);
            if (sanitized === CONFIG_DEFAULT) {
                alert("Cannot delete the Default preset.");
                return;
            }
            const ok = confirm(`Delete preset "${sanitized}"? This action cannot be undone.`);
            if (!ok) return;

            const result = await deleteConfig(sanitized);
            if (result && result.success) {
                // Reset to Default
                configNameWidget.value = CONFIG_DEFAULT;
                configSelectWidget.value = CONFIG_DEFAULT;
                await refreshConfigCombo();
                if (node.setSize) node.setSize(node.size);
                console.log("[zyd232 LLM] Config deleted successfully:", sanitized);
            } else {
                alert(`Failed to delete config: ${result?.error || "Unknown error"}`);
            }
        }

        // ---- Create button widgets using shared utilities ----
        const configSaveDeleteRow = createMultiButtonRow(
            ["\u{1F4BE} Save Config & Hide API", "\u{1F5D1} Delete"],
            [handleSaveConfig, handleDeleteConfig],
            { name: "config_save_delete" }
        );

        const configRefreshRow = createFullWidthButton(
            "\u{1F504} Refresh Config List",
            refreshConfigCombo,
            { name: "config_refresh" }
        );

        // Insert Save/Delete row and Refresh Config List row right after config_name
        const configNameIdx = node.widgets.findIndex(w => w.name === "config_name");
        if (configNameIdx !== -1) {
            node.widgets.splice(configNameIdx + 1, 0, configSaveDeleteRow, configRefreshRow);
        }

        const refreshModelsBtn = createFullWidthButton(
            "\u{1F504} Refresh Model List",
            updateModelList,
            { name: "refresh_models" }
        );

        // Insert Refresh Models button right after model_NoVision
        const modelNoVisionIdx = node.widgets.findIndex(w => w.name === "model_NoVision");
        if (modelNoVisionIdx !== -1) {
            node.widgets.splice(modelNoVisionIdx + 1, 0, refreshModelsBtn);
        }

        // ============ Wiring ============

        // --- config_select: when user chooses, load that config (skip placeholder logic) ---
        if (configSelectWidget) {
            configSelectWidget.callback = async function () {
                const selected = configSelectWidget.value;
                if (!selected || selected === MODEL_PLACEHOLDER) return;

                const cfg = await loadConfig(selected);
                if (!cfg) {
                    console.warn("[zyd232 LLM] Load config returned empty:", selected);
                    return;
                }

                // Override config_name widget too so it matches
                if (configNameWidget) configNameWidget.value = selected;

                // Set widget values (api_key field uses masked placeholder if present in config)
                const widgetMap = getWidgetMap();
                for (const name of SAVED_WIDGETS) {
                    if (cfg[name] === undefined) continue;
                    if (name === "api_key" && cfg.api_key) {
                        // Mask the api_key for display
                        setWidgetValue(widgetMap[name], API_KEY_MASKED);
                    } else {
                        setWidgetValue(widgetMap[name], cfg[name]);
                    }
                }

                if (node.setSize) node.setSize(node.size);
            };
        }

        // ============ Model Fetching (existing logic, kept intact) ============

        async function updateModelList() {
            if (!baseUrlWidget.value) return;
            try {
                const originalModel = modelWidget ? modelWidget.value : "";
                const originalNoVision = modelNoVisionWidget ? modelNoVisionWidget.value : "";

                if (modelWidget) modelWidget.value = "Fetching models...";
                if (modelNoVisionWidget) modelNoVisionWidget.value = "Fetching models...";

                // When api_key is masked, try to load the real key from current config
                let resolvedApiKey = apiKeyWidget.value;
                if (resolvedApiKey === API_KEY_MASKED) {
                    const currentConfig = configSelectWidget ? configSelectWidget.value : CONFIG_DEFAULT;
                    const cfg = await loadConfig(currentConfig);
                    if (cfg && cfg.api_key) {
                        resolvedApiKey = cfg.api_key;
                    } else {
                        resolvedApiKey = "";
                    }
                }

                const response = await api.fetchApi("/zyd232/fetch_models", {
                    method: "POST",
                    body: JSON.stringify({
                        base_url: baseUrlWidget.value,
                        api_key: resolvedApiKey,
                        config_name: configSelectWidget ? configSelectWidget.value : CONFIG_DEFAULT
                    })
                });

                const data = await response.json();
                if (data.success && data.models && data.models.length > 0) {
                    const comboValues = [MODEL_PLACEHOLDER, ...data.models];

                    if (modelSelectWidget) modelSelectWidget.options.values = comboValues;
                    if (modelNoVisionSelectWidget) modelNoVisionSelectWidget.options.values = comboValues;

                    if (modelWidget) {
                        if (data.models.includes(originalModel) && originalModel) {
                            modelWidget.value = originalModel;
                        } else {
                            modelWidget.value = data.models[0];
                        }
                    }

                    if (modelNoVisionWidget) {
                        if (data.models.includes(originalNoVision) && originalNoVision) {
                            modelNoVisionWidget.value = originalNoVision;
                        } else {
                            modelNoVisionWidget.value = data.models[0];
                        }
                    }
                } else {
                    if (modelWidget) modelWidget.value = "Fetch failed, check console";
                    if (modelNoVisionWidget) modelNoVisionWidget.value = "Fetch failed, check console";
                }
            } catch (error) {
                console.error("[zyd232 LLM JS] Error fetching models:", error);
                if (modelWidget) modelWidget.value = "Error connecting";
                if (modelNoVisionWidget) modelNoVisionWidget.value = "Error connecting";
            }
        }

        if (modelSelectWidget) {
            const originalCallback = modelSelectWidget.callback;
            modelSelectWidget.callback = function () {
                const selectedValue = modelSelectWidget.value;
                if (selectedValue && selectedValue !== MODEL_PLACEHOLDER) {
                    if (modelWidget) modelWidget.value = selectedValue;
                }
                modelSelectWidget.value = MODEL_PLACEHOLDER;
                if (node.setSize) node.setSize(node.size);
            };
        }

        if (modelNoVisionSelectWidget) {
            modelNoVisionSelectWidget.callback = function () {
                const selectedValue = modelNoVisionSelectWidget.value;
                if (selectedValue && selectedValue !== MODEL_PLACEHOLDER) {
                    if (modelNoVisionWidget) modelNoVisionWidget.value = selectedValue;
                }
                modelNoVisionSelectWidget.value = MODEL_PLACEHOLDER;
                if (node.setSize) node.setSize(node.size);
            };
        }

        baseUrlWidget.callback = function () { updateModelList(); };
        apiKeyWidget.callback = function () { updateModelList(); };

        // Initial fetch
        setTimeout(updateModelList, 200);
        // Initial refresh of config combo as well
        setTimeout(refreshConfigCombo, 250);
    }
});
