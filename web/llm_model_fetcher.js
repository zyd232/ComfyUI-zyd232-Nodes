import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";
import { createFullWidthButton, createMultiButtonRow } from "./button_utils.js";
import { setupStreamingPanel } from "./streaming_text.js";
import { loadTranslations, $tSync } from "./i18n.js";

let MODEL_PLACEHOLDER = "Choose a model from the list";
let REASONING_EFFORT_PLACEHOLDER = "Choose reasoning effort";
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
    "timeout",
    "reasoning_effort",
    "separate_thinking",
    "think_start_tag",
    "think_end_tag",
    "clean_comfy_vram_before_gen",
    "unload_after_gen",
    "unload_endpoint",
    "llama_cpp_unload",
    "llama_endpoint",
    "cache_prompt",
    "auto_lock",
    "video_fps",
    "max_video_frames",
    "enable_audio"
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
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "zyd232 LLMGenerator") return;

        // Preload translations so onNodeCreated can use $tSync() synchronously.
        await loadTranslations();
        MODEL_PLACEHOLDER = $tSync("model.placeholder");
        REASONING_EFFORT_PLACEHOLDER = $tSync("reasoningEffort.placeholder");

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;

            // One-time guard: onNodeCreated may fire multiple times (e.g. when
            // loading a workflow or cloning a node). Without this, buttons and the
            // streaming panel would be created repeatedly and pile up at the bottom.
            if (this.__zyd232Initialized) return r;
            this.__zyd232Initialized = true;

            // Capture the node instance. Regular functions and widget callbacks
            // below do NOT have `this` bound to the node, so we use `node` instead.
            const node = this;

            // Set up the streaming text display panel on the right side of the node.
            setupStreamingPanel(node);

            // ============ Keep button widgets out of widgets_values ============
            // ComfyUI recreates the dynamically-added button widgets when a
            // workflow is loaded/pasted, and those recreated buttons end up with
            // `serialize !== false`. That injects their values into the
            // `widgets_values` array, shifting every later widget's index and
            // making `comfy run` / comfy-mcp report a "widgets order mismatch
            // with the server definition" (e.g. base_url lands on the model slot).
            //
            // Relying on the buttons' `serialize` flag is unreliable because
            // ComfyUI resets it to `true` on reload. Instead we make the node's
            // serialization bulletproof by overriding `serialize` to force every
            // button to `serialize = false` for the duration of the call, so the
            // buttons can NEVER enter `widgets_values` regardless of their flag
            // state. This keeps the saved positional array aligned with the
            // backend schema (base_url at index 2, model at index 5, ...).
            const origSerialize = node.serialize ? node.serialize.bind(node) : null;
            node.serialize = function (...args) {
                const buttons = node.__zyd232Buttons || [];
                const savedFlags = buttons.map(b => (b ? b.serialize : undefined));
                for (const b of buttons) {
                    if (b) b.serialize = false;
                }
                let result;
                try {
                    result = origSerialize ? origSerialize(...args) : undefined;
                } finally {
                    for (let i = 0; i < buttons.length; i++) {
                        if (buttons[i]) buttons[i].serialize = savedFlags[i];
                    }
                }
                return result;
            };

            // ============ Restore widget values by name (robust against index shift) ============
            // ComfyUI restores widget values from the positional `widgets_values`
            // array by iterating node.widgets in order and skipping serialize===false
            // widgets. Because the buttons can end up serialize!==false after a
            // reload, that positional restore misaligns every later widget. To be
            // robust (including against workflows saved before this fix), we wrap
            // `configure` to re-apply values by NAME from `widgets_values_named`
            // when present, falling back to a name->position map over the array.
            //
            // This wraps the INSTANCE onConfigure (which setupStreamingPanel
            // above already assigned) so it runs AFTER streaming_text.js's own
            // configure handling, guaranteeing the values are corrected once the
            // widget values have been restored.
            const origNodeOnConfigure = node.onConfigure ? node.onConfigure.bind(node) : null;
            node.onConfigure = function (...rest) {
                const r = origNodeOnConfigure ? origNodeOnConfigure(...rest) : undefined;
                const config = rest && rest[0];
                if (config) {
                    // Prefer the name-keyed map when ComfyUI provides it.
                    const named = config.widgets_values_named;
                    if (named && typeof named === "object") {
                        for (const w of node.widgets) {
                            if (w && w.name && named[w.name] !== undefined) {
                                setWidgetValue(w, named[w.name]);
                            }
                        }
                    } else if (Array.isArray(config.widgets_values)) {
                        // Fall back to positional restore. The array may be either
                        // correctly aligned (buttons excluded, produced by the
                        // node.serialize override above) or a historical misaligned
                        // one (buttons included, saved before this fix). Detect
                        // which by comparing the array length to the number of
                        // non-button widgets: if the array is longer, the buttons
                        // were serialized in, so consume their entries too to keep
                        // the schema widgets aligned.
                        const wv = config.widgets_values;
                        const nonButtonCount = node.widgets.filter(w => w && w.type !== "button").length;
                        const includeButtons = wv.length > nonButtonCount;
                        let w = 0;
                        for (const widget of node.widgets) {
                            if (!widget) continue;
                            if (widget.type === "button" && !includeButtons) continue;
                            if (w >= wv.length) break;
                            setWidgetValue(widget, wv[w]);
                            w++;
                        }
                    }
                }
                return r;
            };

            // Hide the locked-result persistence widgets. These are declared in
            // the backend schema (use_locked, locked_text, locked_reasoning) and
            // are serialized into the workflow JSON and passed to execute(), but
            // they must not be visible in the node UI.
            //
            // Simply setting w.type = "hidden" does NOT work here: ComfyUI decides
            // whether to render a widget when it is created (addWidget), so by the
            // time onNodeCreated runs the widgets are already in node.widgets and
            // already rendered. Instead we override their draw/computeSize so they
            // occupy zero height and render nothing, while keeping them in the
            // node.widgets array so their values are still serialized into the
            // workflow JSON and passed to execute().
            for (const hiddenName of ["use_locked", "locked_text", "locked_reasoning"]) {
                const w = node.widgets.find(w => w.name === hiddenName);
                if (w) {
                    w.draw = function () { return 0; };
                    w.computeSize = function () { return [0, -4]; };
                }
            }

            // Remove the front-end upper limit on max_video_frames. ComfyUI's
            // ComfyWidgets.INT defaults `max` to 2048 when the backend does not
            // specify one, which would prevent entering values above 2048. We
            // raise it to the maximum safe integer and allow -1/0 (no cap).
            const maxFramesWidget = node.widgets.find(w => w.name === "max_video_frames");
            if (maxFramesWidget) {
                maxFramesWidget.options.max = Number.MAX_SAFE_INTEGER;
                maxFramesWidget.options.min = -1;
            }

            // ---- Core widgets (already existed) ----
            const baseUrlWidget = node.widgets.find(w => w.name === "base_url");
            const apiKeyWidget = node.widgets.find(w => w.name === "api_key");
            const modelWidget = node.widgets.find(w => w.name === "model");
            const modelNoVisionWidget = node.widgets.find(w => w.name === "model_NoVision");
            const modelSelectWidget = node.widgets.find(w => w.name === "model_select");
            const modelNoVisionSelectWidget = node.widgets.find(w => w.name === "model_NoVision_select");
            const reasoningEffortWidget = node.widgets.find(w => w.name === "reasoning_effort");
            const reasoningEffortSelectWidget = node.widgets.find(w => w.name === "reasoning_effort_select");

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
                    alert($tSync("alert.saveFailed").replace("{error}", result?.error || $tSync("alert.unknownError")));
                }
            }

            async function handleDeleteConfig() {
                if (!configSelectWidget || !configNameWidget) return;
                const target = configSelectWidget.value || configNameWidget.value || CONFIG_DEFAULT;
                const sanitized = sanitizeConfigName(target);
                if (sanitized === CONFIG_DEFAULT) {
                    alert($tSync("alert.deleteDefault"));
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
                    alert($tSync("alert.deleteFailed").replace("{error}", result?.error || $tSync("alert.unknownError")));
                }
            }

            // ---- Button labels (used both for display and to locate the widgets
            // that addWidget appended to node.widgets). Text comes from the
            // locales/<lang>/main.json i18n files, not hardcoded here. ----
            const BTN_SAVE = $tSync("button.saveConfig");
            const BTN_DELETE = $tSync("button.deleteConfig");
            const BTN_REFRESH_CONFIG = $tSync("button.refreshConfig");
            const BTN_REFRESH_MODEL = $tSync("button.refreshModel");
            const BTN_STOP = $tSync("button.stopGeneration");

            // Move a widget (found by its name/label) to be right after another widget.
            // addWidget appends buttons to node.widgets, so we relocate the existing
            // widget objects rather than inserting the (different) returned objects.
            function moveWidgetAfter(widgetName, afterName) {
                const fromIdx = node.widgets.findIndex(w => w.name === widgetName);
                const afterIdx = node.widgets.findIndex(w => w.name === afterName);
                if (fromIdx === -1 || afterIdx === -1) return;
                const [w] = node.widgets.splice(fromIdx, 1);
                // Recompute the anchor index after removal (it may have shifted).
                const newAfterIdx = node.widgets.findIndex(x => x.name === afterName);
                node.widgets.splice(newAfterIdx + 1, 0, w);
            }

            // ---- Create button widgets using shared utilities ----
            // createMultiButtonRow returns an array of default button widgets (one per label).
            // We keep the returned widget objects so the node.serialize override
            // (see above) can force their `serialize` to false during serialization,
            // guaranteeing they never enter widgets_values even though ComfyUI
            // recreates them with serialize !== false after a workflow reload.
            const saveDeleteBtns = createMultiButtonRow(
                node,
                [BTN_SAVE, BTN_DELETE],
                [handleSaveConfig, handleDeleteConfig],
                { name: "config_save_delete" }
            );

            const refreshConfigBtn = createFullWidthButton(
                node,
                BTN_REFRESH_CONFIG,
                refreshConfigCombo,
                { name: "config_refresh" }
            );

            const refreshModelBtn = createFullWidthButton(
                node,
                BTN_REFRESH_MODEL,
                updateModelList,
                { name: "refresh_models" }
            );

            // ============ Stop Generation Button ============
            // Closes the active streaming connection so the running generation returns
            // immediately with the text accumulated so far.
            const stopBtn = createFullWidthButton(
                node,
                BTN_STOP,
                async () => {
                    try {
                        const res = await api.fetchApi("/zyd232/stop_generation", { method: "POST" });
                        const data = await res.json();
                        if (data && data.success) {
                            console.log("[zyd232 LLM] Stop signal sent:", data.message || "");
                        } else {
                            console.warn("[zyd232 LLM] Stop failed:", data?.error || "No active generation");
                        }
                    } catch (e) {
                        console.error("[zyd232 LLM] Error sending stop signal:", e);
                    }
                },
                { name: "stop_generation" }
            );

            // Keep references to every button widget so the node.serialize
            // override can force serialize === false during serialization, keeping
            // them out of widgets_values even after ComfyUI recreates them on load.
            node.__zyd232Buttons = [
                ...(Array.isArray(saveDeleteBtns) ? saveDeleteBtns : []),
                refreshConfigBtn,
                refreshModelBtn,
                stopBtn,
            ].filter(Boolean);

            // ---- Relocate the appended buttons to their intended positions ----
            // Save/Delete/Refresh Config right after config_name
            moveWidgetAfter(BTN_SAVE, "config_name");
            moveWidgetAfter(BTN_DELETE, BTN_SAVE);
            moveWidgetAfter(BTN_REFRESH_CONFIG, BTN_DELETE);
            // Refresh Model right after model_NoVision
            moveWidgetAfter(BTN_REFRESH_MODEL, "model_NoVision");
            // Stop right after Refresh Model
            moveWidgetAfter(BTN_STOP, BTN_REFRESH_MODEL);

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

                    // Switching to a different preset changes base_url/api_key, so
                    // refresh the model list for the newly selected server. This is an
                    // automatic refresh: on failure the Model fields keep their values.
                    updateModelList();
                };
            }

            // ============ Model Fetching ============

            // True when the current widget value is empty (no selection yet).
            function isModelValueEmpty(value) {
                return !value;
            }

            // When the LLM server cannot be reached, the Model Select / Text-Only
            // Model Select dropdowns must show only "Fetch failed" and drop any
            // previously cached model list, so the user is not misled into picking a
            // model that is currently unavailable.
            const FETCH_FAILED = "Fetch failed";
            const FETCHING = "Fetching models...";
            function setDropdownFailed(selectWidget) {
                if (!selectWidget) return;
                selectWidget.options.values = [FETCH_FAILED];
                selectWidget.value = FETCH_FAILED;
            }

            // Show the transient "Fetching models..." state on a dropdown.
            function setDropdownFetching(selectWidget) {
                if (!selectWidget) return;
                selectWidget.options.values = [FETCHING];
                selectWidget.value = FETCHING;
            }

            async function updateModelList() {
                if (!baseUrlWidget.value) return;
                try {
                    const originalModel = modelWidget ? modelWidget.value : "";
                    const originalNoVision = modelNoVisionWidget ? modelNoVisionWidget.value : "";

                    // The "Fetching models..." state belongs on the dropdowns, not on
                    // the Model / Text-Only Model fields. Those fields keep whatever
                    // the user had selected throughout the fetch.
                    setDropdownFetching(modelSelectWidget);
                    setDropdownFetching(modelNoVisionSelectWidget);

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

                        if (modelSelectWidget) {
                            modelSelectWidget.options.values = comboValues;
                            // Reset the displayed value so a previous "Fetch failed"
                            // marker is replaced by the normal placeholder.
                            modelSelectWidget.value = MODEL_PLACEHOLDER;
                        }
                        if (modelNoVisionSelectWidget) {
                            modelNoVisionSelectWidget.options.values = comboValues;
                            // Reset the displayed value so a previous "Fetch failed"
                            // marker is replaced by the normal placeholder.
                            modelNoVisionSelectWidget.value = MODEL_PLACEHOLDER;
                        }

                        // Keep whatever the user had selected. Only auto-pick the first
                        // model when the field is empty (or holds a stale placeholder).
                        if (modelWidget) {
                            if (isModelValueEmpty(originalModel)) {
                                modelWidget.value = data.models[0];
                            } else {
                                modelWidget.value = originalModel;
                            }
                        }

                        if (modelNoVisionWidget) {
                            if (isModelValueEmpty(originalNoVision)) {
                                modelNoVisionWidget.value = data.models[0];
                            } else {
                                modelNoVisionWidget.value = originalNoVision;
                            }
                        }
                    } else {
                        // Fetch failed (network down, server unreachable, or empty list).
                        // The dropdowns must not keep a stale cached list; show only
                        // "Fetch failed" so the user knows the server is unreachable.
                        // The Model / Text-Only Model fields are never touched here, so
                        // they keep whatever the user had selected.
                        setDropdownFailed(modelSelectWidget);
                        setDropdownFailed(modelNoVisionSelectWidget);
                    }
                } catch (error) {
                    console.error("[zyd232 LLM JS] Error fetching models:", error);
                    setDropdownFailed(modelSelectWidget);
                    setDropdownFailed(modelNoVisionSelectWidget);
                    // The Model / Text-Only Model fields keep their original values.
                }
            }

            if (modelSelectWidget) {
                const originalCallback = modelSelectWidget.callback;
                modelSelectWidget.callback = function () {
                    const selectedValue = modelSelectWidget.value;
                    // Ignore the placeholder and the "Fetch failed" marker so they
                    // never overwrite the user's model selection.
                    if (selectedValue && selectedValue !== MODEL_PLACEHOLDER && selectedValue !== FETCH_FAILED) {
                        if (modelWidget) modelWidget.value = selectedValue;
                    }
                    modelSelectWidget.value = MODEL_PLACEHOLDER;
                    if (node.setSize) node.setSize(node.size);
                };
            }

            if (modelNoVisionSelectWidget) {
                modelNoVisionSelectWidget.callback = function () {
                    const selectedValue = modelNoVisionSelectWidget.value;
                    // Ignore the placeholder and the "Fetch failed" marker so they
                    // never overwrite the user's model selection.
                    if (selectedValue && selectedValue !== MODEL_PLACEHOLDER && selectedValue !== FETCH_FAILED) {
                        if (modelNoVisionWidget) modelNoVisionWidget.value = selectedValue;
                    }
                    modelNoVisionSelectWidget.value = MODEL_PLACEHOLDER;
                    if (node.setSize) node.setSize(node.size);
                };
            }

            if (reasoningEffortSelectWidget) {
                reasoningEffortSelectWidget.callback = function () {
                    const selectedValue = reasoningEffortSelectWidget.value;
                    // Ignore the placeholder so it never overwrites the user's value.
                    if (selectedValue && selectedValue !== REASONING_EFFORT_PLACEHOLDER) {
                        if (reasoningEffortWidget) reasoningEffortWidget.value = selectedValue;
                    }
                    reasoningEffortSelectWidget.value = REASONING_EFFORT_PLACEHOLDER;
                    if (node.setSize) node.setSize(node.size);
                };
            }

            baseUrlWidget.callback = function () { updateModelList(); };
            apiKeyWidget.callback = function () { updateModelList(); };

            // Initial fetch
            setTimeout(updateModelList, 200);
            // Initial refresh of config combo as well
            setTimeout(refreshConfigCombo, 250);

            return r;
        };
    }
});
