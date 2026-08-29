import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";
import { createFullWidthButton } from "./button_utils.js";
import { loadTranslations, $tSync } from "./i18n.js";
import { loadConfig, fetchModels, setDropdownFetching, setDropdownFailed } from "./llm_model_utils.js";

const CONFIG_DEFAULT = "Default";

app.registerExtension({
    name: "zyd232.LLMUnload",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "zyd232 LLMUnload") return;

        // Preload translations so onNodeCreated can use $tSync() synchronously.
        await loadTranslations();

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;

            // One-time guard: onNodeCreated may fire multiple times (e.g. when
            // loading a workflow or cloning a node). Without this, the buttons
            // would be created repeatedly and pile up at the bottom.
            if (this.__zyd232UnloadInitialized) return r;
            this.__zyd232UnloadInitialized = true;

            const node = this;
            const configSelectWidget = node.widgets.find(w => w.name === "config_select");
            const modelSelectWidget = node.widgets.find(w => w.name === "model_select");
            const modelWidget = node.widgets.find(w => w.name === "model");

            // Localized placeholder for the Model Select dropdown. The backend
            // schema ships the English placeholder as the first option; replace
            // it with the translated string.
            const MODEL_PLACEHOLDER = $tSync("model.placeholder") || "Choose a model from the list";
            const FETCH_FAILED = "Fetch failed";
            const FETCHING = "Fetching models...";

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

            async function refreshConfigCombo() {
                if (!configSelectWidget) return;
                const configs = await listConfigs();
                const comboValues = [...configs];
                // Always include the "Default" entry so the user always has a base option.
                if (!comboValues.includes(CONFIG_DEFAULT)) {
                    comboValues.unshift(CONFIG_DEFAULT);
                }
                configSelectWidget.options.values = comboValues;
                if (node.setSize) node.setSize(node.size);
            }

            // ============ Model Fetching ============
            async function updateModelList() {
                if (!configSelectWidget) return;
                try {
                    const originalModel = modelWidget ? modelWidget.value : "";
                    setDropdownFetching(modelSelectWidget, FETCHING);

                    // Resolve api_key: if masked, load the real key from the current config.
                    const currentConfig = configSelectWidget.value || CONFIG_DEFAULT;
                    const cfg = await loadConfig(currentConfig);
                    const resolvedApiKey = (cfg && cfg.api_key) ? cfg.api_key : "";

                    const models = await fetchModels(cfg?.base_url || "", resolvedApiKey, currentConfig);
                    if (models.length > 0) {
                        // Placeholder first, then the fetched model list.
                        const comboValues = [MODEL_PLACEHOLDER, ...models];
                        if (modelSelectWidget) {
                            modelSelectWidget.options.values = comboValues;
                            modelSelectWidget.value = MODEL_PLACEHOLDER;
                        }
                        // Keep whatever the user had selected; only auto-pick the first
                        // model when the field is empty.
                        if (modelWidget && !originalModel) {
                            modelWidget.value = models[0];
                        }
                    } else {
                        // Fetch failed: show only "Fetch failed" so the user knows the
                        // server is unreachable. The Model field keeps its value.
                        setDropdownFailed(modelSelectWidget, FETCH_FAILED);
                    }
                } catch (error) {
                    console.error("[zyd232 LLM JS] Error fetching models:", error);
                    setDropdownFailed(modelSelectWidget, FETCH_FAILED);
                }
            }

            // ============ Refresh Config List Button ============
            const BTN_REFRESH_CONFIG = $tSync("button.refreshConfig");
            const refreshConfigBtn = createFullWidthButton(
                node,
                BTN_REFRESH_CONFIG,
                refreshConfigCombo,
                { name: "config_refresh" }
            );

            // ============ Refresh Model List Button ============
            const BTN_REFRESH_MODEL = $tSync("button.refreshModel");
            const refreshModelBtn = createFullWidthButton(
                node,
                BTN_REFRESH_MODEL,
                updateModelList,
                { name: "refresh_models" }
            );

            // Keep references so the node.serialize override can force
            // serialize === false, keeping the buttons out of widgets_values.
            node.__zyd232UnloadButtons = [refreshConfigBtn, refreshModelBtn].filter(Boolean);

            // ============ Wiring ============
            // model_select: when the user picks a model, fill the model field.
            if (modelSelectWidget) {
                modelSelectWidget.callback = function () {
                    const selectedValue = modelSelectWidget.value;
                    if (selectedValue && selectedValue !== MODEL_PLACEHOLDER && selectedValue !== FETCH_FAILED) {
                        if (modelWidget) modelWidget.value = selectedValue;
                    }
                    modelSelectWidget.value = MODEL_PLACEHOLDER;
                    if (node.setSize) node.setSize(node.size);
                };
            }

            // config_select: when the user switches preset, refresh the model list
            // using the newly selected preset's connection settings.
            if (configSelectWidget) {
                configSelectWidget.callback = async function () {
                    await updateModelList();
                };
            }

            // ============ Initial setup ============
            // Populate the config combo, then fetch the model list using the
            // currently-selected preset's connection settings.
            setTimeout(async () => {
                await refreshConfigCombo();
                await updateModelList();
            }, 200);

            return r;
        };
    },
});
