# ServerAdapter 架构方案：统一 LLM 服务器标准差异

## 1. 背景与目标

当前 [`LLMGeneratorV3.py`](nodes/LLMGeneratorV3.py:1) 节点通过"双保险/全发一遍"的方式兼容不同 LLM 服务器，导致：

- **`reasoning_effort`**：同时发送 `chat_template_kwargs` + 顶层 `reasoning_effort`/`enable_thinking`（[`LLMGeneratorV3.py`](nodes/LLMGeneratorV3.py:1224)），部分服务器无法识别多余字段。
- **`unload`**：拆分为通用卸载（DELETE `/v1/models/unload`）与 llama.cpp 卸载（POST `/models/unload`）两个独立开关（[`LLMGeneratorV3.py`](nodes/LLMGeneratorV3.py:1362)），UI 冗余。
- **`stop`**：硬编码候选端点列表（[`LLMGeneratorV3.py`](nodes/LLMGeneratorV3.py:488)）。

**目标**：引入统一的 `server_type` 选择器，通过适配器模式（ServerAdapter）分流 `unload`、`reasoning_effort`、`stop`、`payload` 等所有服务器标准差异，实现精确控制、统一配置、可扩展。

## 2. 服务器标准差异矩阵

| 维度 | OpenAI 官方 | vLLM | llama.cpp | Ollama |
|------|------------|------|-----------|--------|
| **chat 端点** | `/v1/chat/completions` | `/v1/chat/completions` | `/v1/chat/completions` | `/api/chat` |
| **reasoning_effort** | 顶层字段 | 顶层 + `chat_template_kwargs` | `chat_template_kwargs` | 无标准，需模板 |
| **context_length** | 无 | `max_tokens` 相关 | `n_ctx` | `options.num_ctx` |
| **卸载端点** | 无 | `/v1/models/unload`(DELETE) | `/models/unload`(POST) | `keep_alive:0` |
| **停止流式** | 关连接即停 | 关连接即停 | 需显式命令 | 关连接即停 |
| **流式格式** | `choices[].delta` | `choices[].delta` | `choices[].delta` | `{"response":...}` |
| **认证** | Bearer | Bearer | Bearer | 无 |

## 3. ServerAdapter 抽象接口

```python
# nodes/llm_server_adapters.py

class ServerAdapter:
    """所有服务器适配器的抽象基类。"""

    # 服务器类型标识（用于 server_type 选择器）
    server_type = "generic"

    # ---- 端点 ----
    def chat_endpoint(self, base_url: str) -> str:
        """返回聊天补全端点 URL。"""
        raise NotImplementedError

    # ---- Payload 构建 ----
    def build_payload(self, ctx: PayloadContext) -> dict:
        """根据上下文构建请求 payload（含 reasoning_effort、context_length 等）。"""
        raise NotImplementedError

    # ---- 卸载 ----
    def build_unload(self, ctx: UnloadContext) -> list[UnloadRequest]:
        """返回卸载请求列表（可能多个候选）。每个 UnloadRequest 含 url/method/payload。"""
        raise NotImplementedError

    # ---- 停止 ----
    def build_stop_commands(self, ctx: StopContext) -> list[UnloadRequest]:
        """返回停止命令请求列表（用于 Stop 按钮）。"""
        raise NotImplementedError

    # ---- 流式解析 ----
    def parse_stream_chunk(self, data: dict) -> tuple[str, str]:
        """从单个 SSE data 块解析出 (content, reasoning)。"""
        raise NotImplementedError
```

### 辅助数据结构

```python
@dataclass
class PayloadContext:
    model: str
    messages: list
    temperature: float
    top_k: int
    seed: int
    context_length: int
    reasoning_effort: str      # 原始用户输入
    separate_thinking: bool
    cache_prompt: bool

@dataclass
class UnloadContext:
    base_url: str
    model: str
    unload_endpoint: str | None   # 用户自定义覆盖，None 用适配器默认

@dataclass
class UnloadRequest:
    url: str
    method: str = "POST"
    payload: dict | None = None
```

## 4. 各服务器适配器实现

### 4.1 OpenAIAdapter（`server_type = "openai"`）

```python
class OpenAIAdapter(ServerAdapter):
    server_type = "openai"

    def chat_endpoint(self, base_url):
        v1 = base_url if base_url.endswith("/v1") else f"{base_url}/v1"
        return f"{v1}/chat/completions"

    def build_payload(self, ctx):
        payload = {
            "model": ctx.model, "messages": ctx.messages,
            "temperature": ctx.temperature, "stream": True,
        }
        if ctx.seed != -1:
            payload["seed"] = ctx.seed
        # reasoning_effort：OpenAI 原生顶层字段
        if ctx.reasoning_effort:
            payload["reasoning_effort"] = ctx.reasoning_effort
        return payload

    def build_unload(self, ctx):
        # OpenAI 托管服务无卸载端点，返回空
        return []

    def build_stop_commands(self, ctx):
        # 关连接即停，无需额外命令
        return []

    def parse_stream_chunk(self, data):
        choices = data.get("choices") or []
        if not choices:
            return "", ""
        delta = choices[0].get("delta") or {}
        return delta.get("content") or "", delta.get("reasoning_content") or ""
```

### 4.2 vLLMAdapter（`server_type = "vllm"`）

```python
class vLLMAdapter(ServerAdapter):
    server_type = "vllm"

    def chat_endpoint(self, base_url):
        v1 = base_url if base_url.endswith("/v1") else f"{base_url}/v1"
        return f"{v1}/chat/completions"

    def build_payload(self, ctx):
        payload = {
            "model": ctx.model, "messages": ctx.messages,
            "temperature": ctx.temperature, "stream": True,
        }
        if ctx.seed != -1:
            payload["seed"] = ctx.seed
        # vLLM：顶层 + chat_template_kwargs 双保险（兼容新旧版本）
        if ctx.reasoning_effort:
            payload["reasoning_effort"] = ctx.reasoning_effort
            payload["chat_template_kwargs"] = {
                "reasoning_effort": ctx.reasoning_effort,
                "enable_thinking": ctx.reasoning_effort not in ("", "off", "none"),
            }
        return payload

    def build_unload(self, ctx):
        endpoint = ctx.unload_endpoint or "/v1/models/unload"
        return [UnloadRequest(
            url=f"{ctx.base_url}/{endpoint.lstrip('/')}",
            method="DELETE",
            payload={"action": "unload", "model": ctx.model, "keep_alive": 0},
        )]

    def build_stop_commands(self, ctx):
        # 关连接即停，无需额外命令
        return []

    def parse_stream_chunk(self, data):
        choices = data.get("choices") or []
        if not choices:
            return "", ""
        delta = choices[0].get("delta") or {}
        return delta.get("content") or "", delta.get("reasoning_content") or ""
```

### 4.3 LlamaCppAdapter（`server_type = "llama.cpp"`）

```python
class LlamaCppAdapter(ServerAdapter):
    server_type = "llama.cpp"

    def chat_endpoint(self, base_url):
        v1 = base_url if base_url.endswith("/v1") else f"{base_url}/v1"
        return f"{v1}/chat/completions"

    def build_payload(self, ctx):
        payload = {
            "model": ctx.model, "messages": ctx.messages,
            "temperature": ctx.temperature, "top_k": ctx.top_k, "stream": True,
        }
        if ctx.context_length not in (-1, 0):
            payload["n_ctx"] = ctx.context_length
        # llama.cpp：reasoning_effort 通过 chat_template_kwargs（需 Jinja 模板）
        if ctx.reasoning_effort:
            payload["chat_template_kwargs"] = {
                "reasoning_effort": ctx.reasoning_effort,
                "enable_thinking": ctx.reasoning_effort not in ("", "off", "none"),
            }
        if ctx.cache_prompt:
            payload["cache_prompt"] = True
        return payload

    def build_unload(self, ctx):
        endpoint = ctx.unload_endpoint or "/models/unload"
        return [UnloadRequest(
            url=f"{ctx.base_url}/{endpoint.lstrip('/')}",
            method="POST",
            payload={"model": ctx.model},
        )]

    def build_stop_commands(self, ctx):
        # llama.cpp 不自动停止，需显式命令（多个候选）
        return [
            UnloadRequest(url=f"{ctx.base_url}/models/unload", method="POST", payload={"model": ctx.model}),
            UnloadRequest(url=f"{ctx.base_url}/v1/models/unload", method="POST", payload={"model": ctx.model}),
            UnloadRequest(url=f"{ctx.base_url}/slots/0?action=release", method="POST", payload={"model": ctx.model}),
        ]

    def parse_stream_chunk(self, data):
        choices = data.get("choices") or []
        if not choices:
            return "", ""
        delta = choices[0].get("delta") or {}
        return delta.get("content") or "", delta.get("reasoning_content") or ""
```

### 4.4 OllamaAdapter（`server_type = "ollama"`）

```python
class OllamaAdapter(ServerAdapter):
    server_type = "ollama"

    def chat_endpoint(self, base_url):
        return f"{base_url.rstrip('/')}/api/chat"

    def build_payload(self, ctx):
        payload = {
            "model": ctx.model, "messages": ctx.messages, "stream": True,
            "options": {"temperature": ctx.temperature, "top_k": ctx.top_k},
        }
        if ctx.seed != -1:
            payload["options"]["seed"] = ctx.seed
        if ctx.context_length not in (-1, 0):
            payload["options"]["num_ctx"] = ctx.context_length
        # Ollama 无标准 reasoning_effort，通过 keep_alive 控制卸载
        return payload

    def build_unload(self, ctx):
        # Ollama 通过 keep_alive:0 卸载
        return [UnloadRequest(
            url=f"{ctx.base_url.rstrip('/')}/api/generate",
            method="POST",
            payload={"model": ctx.model, "keep_alive": 0},
        )]

    def build_stop_commands(self, ctx):
        # 关连接即停，无需额外命令
        return []

    def parse_stream_chunk(self, data):
        # Ollama 原生流式格式：{"response": "..."}
        return data.get("response") or "", ""
```

## 5. auto 自动探测模式

`server_type = "auto"` 时，通过探测确定实际适配器：

```python
class AutoAdapter(ServerAdapter):
    server_type = "auto"

    def __init__(self, base_url, api_key):
        self._detected = self._detect(base_url, api_key)

    def _detect(self, base_url, api_key):
        """探测服务器类型。"""
        # 1. 尝试 /api/tags（Ollama 特有）
        if self._probe(f"{base_url}/api/tags"):
            return OllamaAdapter()
        # 2. 尝试 /health（llama.cpp 特有）
        if self._probe(f"{base_url}/health"):
            return LlamaCppAdapter()
        # 3. 尝试 /v1/models（OpenAI 兼容）
        if self._probe(f"{base_url}/v1/models", headers={"Authorization": f"Bearer {api_key}"}):
            # 进一步区分 vLLM / OpenAI（通过响应头或字段）
            return vLLMAdapter()  # 或 OpenAIAdapter()
        # 4. 默认回退
        return OpenAIAdapter()

    def _probe(self, url, headers=None, timeout=3):
        try:
            req = urllib.request.Request(url, headers=headers or {})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status < 400
        except Exception:
            return False

    # 所有方法委托给 _detected
    def chat_endpoint(self, base_url): return self._detected.chat_endpoint(base_url)
    def build_payload(self, ctx): return self._detected.build_payload(ctx)
    def build_unload(self, ctx): return self._detected.build_unload(ctx)
    def build_stop_commands(self, ctx): return self._detected.build_stop_commands(ctx)
    def parse_stream_chunk(self, data): return self._detected.parse_stream_chunk(data)
```

**探测策略说明：**
- 探测在 `execute()` 开始时执行一次，缓存结果
- 探测失败时回退到 `OpenAIAdapter`（最大公约数）
- 探测结果可打印日志供用户确认

## 6. 适配器工厂

```python
ADAPTER_REGISTRY = {
    "auto": AutoAdapter,
    "openai": OpenAIAdapter,
    "vllm": vLLMAdapter,
    "llama.cpp": LlamaCppAdapter,
    "ollama": OllamaAdapter,
}

def get_adapter(server_type, base_url="", api_key=""):
    cls = ADAPTER_REGISTRY.get(server_type, OpenAIAdapter)
    if server_type == "auto":
        return cls(base_url, api_key)
    return cls()
```

## 7. schema 变更与向后兼容

### 7.1 新增字段

在 [`LLMGeneratorV3.py`](nodes/LLMGeneratorV3.py:713) 的 schema 中，将 `llama_cpp_unload`/`llama_endpoint` 替换为 `server_type`：

```python
io.Combo.Input("server_type",
    options=["auto", "openai", "vllm", "llama.cpp", "ollama"],
    default="auto",
    display_name="Server Type",
    tooltip="LLM server type. Determines how unload, reasoning_effort and payload are sent."),
```

保留 `unload_endpoint` 作为**可选自定义覆盖**（默认空，用适配器默认值）。

### 7.2 移除字段

- 移除 `llama_cpp_unload`（布尔开关）
- 移除 `llama_endpoint`（端点路径）

### 7.3 向后兼容策略

**关键风险：`widgets_values` 索引错位。**

由于移除中间两个 widget 会改变后续所有字段索引，破坏已保存工作流，采用以下策略：

**方案 A（推荐）：字段位置保持不变，仅替换类型**
- 将 `llama_cpp_unload`（布尔）位置替换为 `server_type`（combo）
- 将 `llama_endpoint`（字符串）位置替换为 `unload_endpoint` 的覆盖语义
- 这样 widget 数量不变，索引不偏移，旧工作流只需将布尔值映射为 combo 值

**方案 B：新增在末尾 + 前端按名恢复**
- 新增 `server_type` 在 schema 末尾
- 依赖前端 [`llm_model_fetcher.js`](web/llm_model_fetcher.js:133) 的按名恢复逻辑
- 旧工作流加载时 `server_type` 用默认值 `auto`

**推荐方案 A**，因为它最小化索引偏移风险。

### 7.4 预设迁移

在 [`load_config_file()`](nodes/LLMGeneratorV3.py:158) 或加载时增加迁移逻辑：

```python
def _migrate_config(cfg):
    """将旧版 llama_cpp_unload/llama_endpoint 迁移到 server_type。"""
    if "server_type" not in cfg:
        if cfg.get("llama_cpp_unload"):
            cfg["server_type"] = "llama.cpp"
        else:
            cfg["server_type"] = "auto"
    return cfg
```

## 8. execute() 重构

```python
def execute(cls, ..., server_type, unload_endpoint, ...):
    # 1. 获取适配器
    adapter = get_adapter(server_type, clean_base_url, actual_key)

    # 2. 构建 payload
    payload = adapter.build_payload(PayloadContext(
        model=actual_model, messages=messages, temperature=temperature,
        top_k=top_k, seed=seed, context_length=context_length,
        reasoning_effort=reasoning_effort, separate_thinking=separate_thinking,
        cache_prompt=cache_prompt,
    ))

    # 3. 流式请求（使用适配器的端点 + 解析器）
    chat_url = adapter.chat_endpoint(clean_base_url)
    full_text, reasoning = _run_stream(chat_url, payload, adapter, push_done=True)

    # 4. 卸载（统一走适配器）
    if _generation_was_stopped or unload_after_gen:
        for req in adapter.build_unload(UnloadContext(
            base_url=clean_base_url, model=actual_model,
            unload_endpoint=unload_endpoint or None,
        )):
            _send_unload_async(req.url, req.payload, headers, method=req.method)
```

### 8.1 `_stream_async` 改造

将硬编码的 OpenAI 解析逻辑（[`LLMGeneratorV3.py`](nodes/LLMGeneratorV3.py:562)）替换为适配器的 `parse_stream_chunk`：

```python
async def _stream_async(url, payload, headers, scope, adapter, ...):
    ...
    async for raw_line in resp.content:
        ...
        chunk = json.loads(data)
        delta_text, delta_reasoning = adapter.parse_stream_chunk(chunk)
        ...
```

### 8.2 Stop 命令改造

将 [`_send_stop_command_async()`](nodes/LLMGeneratorV3.py:488) 的硬编码候选列表替换为适配器的 `build_stop_commands`：

```python
def _send_stop_command_async(adapter, base_url, model, headers):
    for req in adapter.build_stop_commands(StopContext(base_url=base_url, model=model)):
        _send_unload_async(req.url, req.payload, headers, method=req.method)
```

## 9. 前端改动

### 9.1 [`llm_model_fetcher.js`](web/llm_model_fetcher.js:28) `SAVED_WIDGETS`

```javascript
const SAVED_WIDGETS = [
    ...
    "unload_after_gen",
    "unload_endpoint",
    "server_type",        // 替换 llama_cpp_unload
    // "llama_endpoint" 移除
    "cache_prompt",
    ...
];
```

### 9.2 本地化文件

`locales/zh/nodeDefs.json` 和 `locales/en/nodeDefs.json`：

```json
"server_type": {
    "name": "服务器类型",
    "tooltip": "LLM 服务器类型，决定卸载、reasoning_effort 和 payload 的发送方式"
}
```

移除 `llama_cpp_unload`、`llama_endpoint` 的翻译。

## 10. 文件结构

```
nodes/
├── LLMGeneratorV3.py          # 主节点，使用适配器
└── llm_server_adapters.py     # 新增：ServerAdapter 基类 + 各适配器 + 工厂
```

## 11. 实施步骤

1. 新建 `nodes/llm_server_adapters.py`，实现 `ServerAdapter` 基类、`PayloadContext`/`UnloadContext`/`UnloadRequest` 数据结构、`ADAPTER_REGISTRY` 工厂
2. 实现 `OpenAIAdapter`、`vLLMAdapter`、`LlamaCppAdapter`、`OllamaAdapter`
3. 实现 `AutoAdapter` 自动探测
4. 修改 [`LLMGeneratorV3.py`](nodes/LLMGeneratorV3.py:1)：
   - schema：`llama_cpp_unload`/`llama_endpoint` → `server_type`
   - `execute()` 签名与逻辑重构
   - `_stream_async` 使用适配器解析
   - `_send_stop_command_async` 使用适配器
   - `SAVED_FIELDS` 更新
   - 预设迁移逻辑
5. 修改前端 [`llm_model_fetcher.js`](web/llm_model_fetcher.js:28) `SAVED_WIDGETS`
6. 更新本地化文件
7. 测试各服务器类型

## 12. 风险与注意事项

- **向后兼容**：采用方案 A（字段位置不变）最小化索引偏移风险
- **auto 探测**：探测失败回退 OpenAIAdapter，需打印日志
- **Ollama 流式格式**：`parse_stream_chunk` 需处理 `{"response":...}` 格式
- **`_send_stop_command_async`**：llama.cpp 的候选端点需保留，确保 Stop 后能停止处理
- **`unload_endpoint` 覆盖**：保留作为可选覆盖，未设置时用适配器默认值
