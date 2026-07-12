import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

app.registerExtension({
    name: "zyd232.LLMModelFetcher",
    async nodeCreated(node) {
        if (node.comfyClass === "zyd232 LLMGenerator") {
            
            const baseUrlWidget = node.widgets.find(w => w.name === "base_url");
            const apiKeyWidget = node.widgets.find(w => w.name === "api_key");
            const modelWidget = node.widgets.find(w => w.name === "model");
            const refreshWidget = node.widgets.find(w => w.name === "force_refresh");
            
            // Thinking 栏
            const thinkingWidget = node.widgets.find(w => w.name === "thinking");
            const startTagWidget = node.widgets.find(w => w.name === "think_start_tag");
            const endTagWidget = node.widgets.find(w => w.name === "think_end_tag");

            // 通用 Unload 栏
            const unloadWidget = node.widgets.find(w => w.name === "unload_after_gen");
            const unloadEndpointWidget = node.widgets.find(w => w.name === "unload_endpoint");

            // Llama.cpp 专用 Unload 栏
            const llamaUnloadWidget = node.widgets.find(w => w.name === "llama_cpp_unload");
            const llamaEndpointWidget = node.widgets.find(w => w.name === "llama_endpoint");

            if (!node.widgets_bak) {
                node.widgets_bak = {
                    think_start_tag: startTagWidget,
                    think_end_tag: endTagWidget,
                    unload_endpoint: unloadEndpointWidget,
                    llama_endpoint: llamaEndpointWidget
                };
            }

            function refreshNodeSize(currentWidth) {
                const computedSize = node.computeSize();
                node.size = [currentWidth, computedSize[1]];
                app.canvas.setDirty(true, true);
            }

            // Thinking UI 控制
            function toggleThinkingWidgets() {
                const show = thinkingWidget.value;
                const currentWidth = node.size[0];
                
                if (show) {
                    const thinkIdx = node.widgets.indexOf(thinkingWidget);
                    if (thinkIdx !== -1) {
                        if (!node.widgets.includes(node.widgets_bak.think_start_tag)) {
                            node.widgets.splice(thinkIdx + 1, 0, node.widgets_bak.think_start_tag);
                        }
                        if (!node.widgets.includes(node.widgets_bak.think_end_tag)) {
                            node.widgets.splice(thinkIdx + 2, 0, node.widgets_bak.think_end_tag);
                        }
                    }
                } else {
                    node.widgets = node.widgets.filter(
                        w => w.name !== "think_start_tag" && w.name !== "think_end_tag"
                    );
                }
                refreshNodeSize(currentWidth);
            }

            // 通用 Unload UI 控制
            function toggleUnloadWidgets() {
                const show = unloadWidget.value;
                const currentWidth = node.size[0];

                if (show) {
                    const unloadIdx = node.widgets.indexOf(unloadWidget);
                    if (unloadIdx !== -1) {
                        if (!node.widgets.includes(node.widgets_bak.unload_endpoint)) {
                            node.widgets.splice(unloadIdx + 1, 0, node.widgets_bak.unload_endpoint);
                        }
                    }
                } else {
                    node.widgets = node.widgets.filter(w => w.name !== "unload_endpoint");
                }
                refreshNodeSize(currentWidth);
            }

            // Llama.cpp UI 控制
            function toggleLlamaWidgets() {
                const show = llamaUnloadWidget.value;
                const currentWidth = node.size[0];

                if (show) {
                    const llamaIdx = node.widgets.indexOf(llamaUnloadWidget);
                    if (llamaIdx !== -1) {
                        if (!node.widgets.includes(node.widgets_bak.llama_endpoint)) {
                            node.widgets.splice(llamaIdx + 1, 0, node.widgets_bak.llama_endpoint);
                        }
                    }
                } else {
                    node.widgets = node.widgets.filter(w => w.name !== "llama_endpoint");
                }
                refreshNodeSize(currentWidth);
            }

            thinkingWidget.callback = function() { toggleThinkingWidgets(); };
            unloadWidget.callback = function() { toggleUnloadWidgets(); };
            llamaUnloadWidget.callback = function() { toggleLlamaWidgets(); };

            async function updateModelList() {
                if (!baseUrlWidget.value) return;
                try {
                    const originalValue = modelWidget.value;
                    modelWidget.value = "Fetching models...";
                    
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
                        if (data.models.includes(originalValue)) {
                            modelWidget.value = originalValue;
                        } else {
                            modelWidget.value = data.models[0];
                        }
                    } else {
                        modelWidget.value = "Fetch failed, check console";
                        modelWidget.options.values = ["default"];
                    }
                } catch (error) {
                    console.error("[zyd232 LLM JS] Error fetching models:", error);
                    modelWidget.value = "Error connecting";
                }
            }

            baseUrlWidget.callback = function() { updateModelList(); };
            apiKeyWidget.callback = function() { updateModelList(); };
            refreshWidget.callback = function() { updateModelList(); };

            setTimeout(() => {
                updateModelList();
                toggleThinkingWidgets();
                toggleUnloadWidgets();
                toggleLlamaWidgets();
            }, 200);
        }
    }
});