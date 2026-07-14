import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

app.registerExtension({
    name: "zyd232.LLMModelFetcher",
    async nodeCreated(node) {
        if (node.comfyClass === "zyd232 LLMGenerator") {
            const baseUrlWidget = node.widgets.find(w => w.name === "base_url");
            const apiKeyWidget = node.widgets.find(w => w.name === "api_key");
            const modelWidget = node.widgets.find(w => w.name === "model");
            const modelNoVisionWidget = node.widgets.find(w => w.name === "model_NoVision");
            const refreshWidget = node.widgets.find(w => w.name === "force_refresh");

            async function updateModelList() {
                if (!baseUrlWidget.value) return;
                try {
                    const originalModel = modelWidget.value;
                    const originalNoVision = modelNoVisionWidget ? modelNoVisionWidget.value : "";

                    modelWidget.value = "Fetching models...";
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
                        modelWidget.options.values = data.models;
                        if (modelNoVisionWidget) {
                            modelNoVisionWidget.options.values = data.models;
                        }

                        if (data.models.includes(originalModel)) {
                            modelWidget.value = originalModel;
                        } else {
                            modelWidget.value = data.models[0];
                        }

                        if (modelNoVisionWidget) {
                            if (data.models.includes(originalNoVision)) {
                                modelNoVisionWidget.value = originalNoVision;
                            } else {
                                modelNoVisionWidget.value = data.models[0];
                            }
                        }
                    } else {
                        modelWidget.value = "Fetch failed, check console";
                        modelWidget.options.values = ["default"];
                        if (modelNoVisionWidget) {
                            modelNoVisionWidget.value = "Fetch failed, check console";
                            modelNoVisionWidget.options.values = ["default"];
                        }
                    }
                } catch (error) {
                    console.error("[zyd232 LLM JS] Error fetching models:", error);
                    modelWidget.value = "Error connecting";
                    if (modelNoVisionWidget) {
                        modelNoVisionWidget.value = "Error connecting";
                    }
                }
            }

            baseUrlWidget.callback = function () { updateModelList(); };
            apiKeyWidget.callback = function () { updateModelList(); };
            refreshWidget.callback = function () { updateModelList(); };

            setTimeout(updateModelList, 200);
        }
    }
});
