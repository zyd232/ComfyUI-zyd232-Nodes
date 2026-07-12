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
            
            const thinkingWidget = node.widgets.find(w => w.name === "thinking");
            const startTagWidget = node.widgets.find(w => w.name === "think_start_tag");
            const endTagWidget = node.widgets.find(w => w.name === "think_end_tag");

            if (!node.widgets_bak) {
                node.widgets_bak = {
                    think_start_tag: startTagWidget,
                    think_end_tag: endTagWidget
                };
            }

            // --- 优化版：锁定宽度，仅改变高度 ---
            function toggleThinkingWidgets() {
                const show = thinkingWidget.value;
                
                // 1. 先记录下节点当前的物理宽度
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

                // 2. 让引擎计算包含当前组件所需的新尺寸（主要是为了拿高度）
                const computedSize = node.computeSize();
                
                // 3. 强制覆盖：宽度保持用户拖拽的当前宽度，高度采用计算后的新高度
                node.size = [currentWidth, computedSize[1]];
                
                // 4. 刷新画布
                app.canvas.setDirty(true, true);
            }

            thinkingWidget.callback = function() {
                toggleThinkingWidgets();
            };

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
            }, 100);
        }
    }
});