# unload_endpoint 默认值导致卸载失效的修复方案

## 1. Bug 分析

### 根本原因

`unload_endpoint` 的默认值是 `/v1/models/unload`（[`LLMGeneratorV3.py`](nodes/LLMGeneratorV3.py:792)），且 `execute()` 中把它作为**用户覆盖**传给适配器：

```python
adapter.build_unload(UnloadContext(
    base_url=clean_base_url, model=actual_model,
    unload_endpoint=unload_endpoint or None,   # 默认 "/v1/models/unload"
))
```

由于默认值非空，它**总是**覆盖适配器的默认端点：
- **llama.cpp**：适配器默认 `/models/unload`（POST），被 `/v1/models/unload` 覆盖 → 卸载失效
- **Ollama**：适配器默认 `/api/generate`（keep_alive:0），被 `/v1/models/unload` 覆盖 → 卸载失效

### 各服务器 unload 预设值

| server_type | 默认 unload 端点 | 方法 | payload |
|-------------|-----------------|------|---------|
| openai | 无（不卸载） | - | - |
| vllm | `/v1/models/unload` | DELETE | `{"action":"unload","keep_alive":0}` |
| llama.cpp | `/models/unload` | POST | `{"model":...}` |
| ollama | `/api/generate` | POST | `{"model":...,"keep_alive":0}` |

## 2. 修复方案：后端兜底 + 前端自动刷新

### 2.1 后端兜底（最可靠）

在适配器的 `build_unload` 中，识别 `unload_endpoint` 是否为"已知预设值"。若是预设值且与当前服务器类型不匹配，则忽略它，改用适配器默认端点。只有用户自定义值才被尊重。

**统一辅助函数**（在 `llm_server_adapters.py` 中）：

```python
# 所有已知的 unload 端点预设值
KNOWN_UNLOAD_ENDPOINTS = {
    "/v1/models/unload",
    "/models/unload",
    "/api/generate",
    "auto",
}

def _resolve_unload_endpoint(ctx, default_endpoint):
    """解析 unload_endpoint。

    - 空 / 'auto' → 用适配器默认端点
    - 已知预设值（非当前适配器默认）→ 视为旧默认值，改用适配器默认端点
    - 用户自定义值（非预设）→ 尊重用户输入
    """
    ep = (ctx.unload_endpoint or "").strip().lstrip("/")
    if not ep or ep == "auto":
        return default_endpoint
    if ep in KNOWN_UNLOAD_ENDPOINTS:
        # 预设值：若与当前适配器默认不同，说明是旧默认值，改用适配器默认
        return default_endpoint
    # 用户自定义
    return ctx.unload_endpoint
```

**各适配器 `build_unload` 使用该辅助函数**：

```python
# LlamaCppAdapter
def build_unload(self, ctx):
    endpoint = _resolve_unload_endpoint(ctx, "/models/unload")
    return [UnloadRequest(
        url=f"{ctx.base_url}/{endpoint.lstrip('/')}",
        method="POST",
        payload={"model": ctx.model},
    )]

# vLLMAdapter
def build_unload(self, ctx):
    endpoint = _resolve_unload_endpoint(ctx, "/v1/models/unload")
    return [UnloadRequest(
        url=f"{ctx.base_url}/{endpoint.lstrip('/')}",
        method="DELETE",
        payload={"action": "unload", "model": ctx.model, "keep_alive": 0},
    )]

# OllamaAdapter
def build_unload(self, ctx):
    endpoint = _resolve_unload_endpoint(ctx, "/api/generate")
    return [UnloadRequest(
        url=f"{ctx.base_url}/{endpoint.lstrip('/')}",
        method="POST",
        payload={"model": ctx.model, "keep_alive": 0},
    )]
```

### 2.2 auto 模式的兜底

当 `server_type=auto` 且探测到具体服务器后，`AutoAdapter.build_unload` 委托给探测结果。若探测失败回退到 OpenAIAdapter（无卸载），则卸载请求为空。为增强兜底，可在 `execute()` 中：当 `server_type=auto` 且 `unload_after_gen` 开启时，尝试向**所有可能的 unload 端点**发送信号。

**在 `execute()` 中增加 auto 兜底**：

```python
if _generation_was_stopped or unload_after_gen:
    try:
        unload_reqs = adapter.build_unload(UnloadContext(
            base_url=clean_base_url, model=actual_model,
            unload_endpoint=unload_endpoint or None,
        ))
        # auto 模式且未探测到具体服务器时，尝试所有可能的端点
        if server_type == "auto" and not unload_reqs:
            unload_reqs = [
                UnloadRequest(url=f"{clean_base_url}/models/unload", method="POST", payload={"model": actual_model}),
                UnloadRequest(url=f"{clean_base_url}/v1/models/unload", method="DELETE", payload={"action": "unload", "model": actual_model, "keep_alive": 0}),
                UnloadRequest(url=f"{clean_base_url}/api/generate", method="POST", payload={"model": actual_model, "keep_alive": 0}),
            ]
        for req in unload_reqs:
            print(f"[zyd232 LLM] Sending unload request to: {req.url} (method={req.method})")
            _send_unload_async(req.url, req.payload, headers, method=req.method)
    except Exception as e:
        print(f"[zyd232 LLM] Unload request failed: {e}")
```

### 2.3 前端自动刷新

**选择 `server_type` 时自动刷新 `unload_endpoint`**（在 [`llm_model_fetcher.js`](web/llm_model_fetcher.js:1) 中）：

```javascript
// server_type -> unload_endpoint 预设值映射
const UNLOAD_ENDPOINT_PRESETS = {
    "auto": "auto",
    "openai": "",
    "vllm": "/v1/models/unload",
    "llama.cpp": "/models/unload",
    "ollama": "/api/generate",
};

// server_type widget 变化时刷新 unload_endpoint
const serverTypeWidget = node.widgets.find(w => w.name === "server_type");
const unloadEndpointWidget = node.widgets.find(w => w.name === "unload_endpoint");
if (serverTypeWidget && unloadEndpointWidget) {
    serverTypeWidget.callback = function () {
        const preset = UNLOAD_ENDPOINT_PRESETS[serverTypeWidget.value];
        if (preset !== undefined) {
            unloadEndpointWidget.value = preset;
        }
    };
}
```

**加载节点/preset 时刷新**：在 `loadConfig` 应用配置后，若 `unload_endpoint` 是已知预设值，则按 `server_type` 刷新。

## 3. 实施步骤

1. [`llm_server_adapters.py`](nodes/llm_server_adapters.py:1)：增加 `KNOWN_UNLOAD_ENDPOINTS` 和 `_resolve_unload_endpoint`，各适配器 `build_unload` 使用
2. [`LLMGeneratorV3.py`](nodes/LLMGeneratorV3.py:1427)：`execute()` 卸载逻辑增加 auto 兜底
3. [`llm_model_fetcher.js`](web/llm_model_fetcher.js:1)：`server_type` 变化时刷新 `unload_endpoint`；加载 preset 时刷新
4. 验证

## 4. 风险与注意事项

- **用户自定义值**：非预设值（如自定义端点）会被尊重，不会被覆盖
- **向后兼容**：旧 preset 中 `unload_endpoint=/v1/models/unload` 会被识别为预设值，自动改用适配器默认端点
- **auto 兜底**：尝试所有端点可能产生无害的 404 错误（服务器忽略），但能确保卸载信号送达
