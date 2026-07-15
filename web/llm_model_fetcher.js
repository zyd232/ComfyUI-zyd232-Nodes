import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

const PLACEHOLDER = "Choose a model from the list";

app.registerExtension({
    name: "zyd232.LLMModelFetcher",
    async nodeCreated(node) {
        if (node.comfyClass === "zyd232 LLMGenerator") {
            const baseUrlWidget = node.widgets.find(w => w.name === "base_url");
            const apiKeyWidget = node.widgets.find(w => w.name === "api_key");
            
            // STRING widgets (actual model values passed to backend)
            const modelWidget = node.widgets.find(w => w.name === "model");
            const modelNoVisionWidget = node.widgets.find(w => w.name === "model_NoVision");
            
            // COMBO widgets (dropdown selectors that populate STRING widgets)
            const modelSelectWidget = node.widgets.find(w => w.name === "model_select");
            const modelNoVisionSelectWidget = node.widgets.find(w => w.name === "model_NoVision_select");
            
            const refreshWidget = node.widgets.find(w => w.name === "force_refresh");

            async function updateModelList() {
                if (!baseUrlWidget.value) return;
                try {
                    // Preserve current STRING values before updating
                    const originalModel = modelWidget ? modelWidget.value : "";
                    const originalNoVision = modelNoVisionWidget ? modelNoVisionWidget.value : "";

                    // Show loading state in STRING widgets
                    if (modelWidget) {
                        modelWidget.value = "Fetching models...";
                    }
                    if (modelNoVisionWidget) {
                        modelNoVisionWidget.value = "Fetching models...";
                    }

                    const response = await api.fetchApi("/zyd232/fetch_models", {
                        method: "POST",
                        body: JSON.stringify({
                            base_url: baseUrlWidget.value,
                            api_key: apiKeyWidget.value
                        })
                    });

                    const data = await response.json();
                    if (data.success && data.models && data.models.length > 0) {
                        // Update COMBO widget options with placeholder prefix
                        const comboValues = [PLACEHOLDER, ...data.models];
                        
                        if (modelSelectWidget) {
                            modelSelectWidget.options.values = comboValues;
                        }
                        if (modelNoVisionSelectWidget) {
                            modelNoVisionSelectWidget.options.values = comboValues;
                        }

                        // Restore or set STRING widget values
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
                        if (modelWidget) {
                            modelWidget.value = "Fetch failed, check console";
                        }
                        if (modelNoVisionWidget) {
                            modelNoVisionWidget.value = "Fetch failed, check console";
                        }
                    }
                } catch (error) {
                    console.error("[zyd232 LLM JS] Error fetching models:", error);
                    if (modelWidget) {
                        modelWidget.value = "Error connecting";
                    }
                    if (modelNoVisionWidget) {
                        modelNoVisionWidget.value = "Error connecting";
                    }
                }
            }

            // When COMBO widget is changed, populate the corresponding STRING widget
            // but keep COMBO displaying the placeholder for next use
            if (modelSelectWidget) {
                const originalCallback = modelSelectWidget.callback;
                modelSelectWidget.callback = function () {
                    const selectedValue = modelSelectWidget.value;
                    // Only update STRING widget if user selected an actual model (not placeholder)
                    if (selectedValue && selectedValue !== PLACEHOLDER) {
                        if (modelWidget) {
                            modelWidget.value = selectedValue;
                        }
                    }
                    // Reset COMBO back to placeholder, keeping display clean
                    modelSelectWidget.value = PLACEHOLDER;
                    // Trigger UI update
                    if (node.setSize) {
                        node.setSize(node.size);
                    }
                };
            }

            if (modelNoVisionSelectWidget) {
                modelNoVisionSelectWidget.callback = function () {
                    const selectedValue = modelNoVisionSelectWidget.value;
                    if (selectedValue && selectedValue !== PLACEHOLDER) {
                        if (modelNoVisionWidget) {
                            modelNoVisionWidget.value = selectedValue;
                        }
                    }
                    // Reset COMBO back to placeholder
                    modelNoVisionSelectWidget.value = PLACEHOLDER;
                    if (node.setSize) {
                        node.setSize(node.size);
                    }
                };
            }

            // Trigger fetch when base_url, api_key, or force_refresh changes
            baseUrlWidget.callback = function () { updateModelList(); };
            apiKeyWidget.callback = function () { updateModelList(); };
            refreshWidget.callback = function () { updateModelList(); };

            // Initial fetch on node creation
            setTimeout(updateModelList, 200);
        }
    }
});
