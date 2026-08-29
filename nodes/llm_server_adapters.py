"""ServerAdapter 架构：统一不同 LLM 服务器（OpenAI/vLLM/llama.cpp/Ollama）的 API 标准差异。

通过 ``server_type`` 选择器 + 适配器模式，分流以下服务器标准差异：
  * chat 端点路径
  * payload 构建（reasoning_effort、context_length、seed、cache_prompt 等）
  * 卸载请求（端点 / HTTP 方法 / payload）
  * Stop 命令（哪些服务器需要显式命令）
  * 流式响应解析（OpenAI 标准 vs Ollama 原生格式）

``auto`` 模式通过探测确定实际服务器类型，失败时回退到 OpenAI 兼容（最大公约数）。
"""

import json
import threading
import time
import urllib.request
from dataclasses import dataclass, field


# ======================= 辅助数据结构 =======================

@dataclass
class PayloadContext:
    """构建请求 payload 所需的上下文。"""
    model: str
    messages: list
    temperature: float
    top_k: int
    seed: int
    context_length: int
    reasoning_effort: str = ""      # 原始用户输入（可能为 '' / 'off' / 'none' / 'low' 等）
    separate_thinking: bool = False
    cache_prompt: bool = True


@dataclass
class UnloadContext:
    """构建卸载请求所需的上下文。"""
    base_url: str
    model: str
    unload_endpoint: str | None = None   # 用户自定义覆盖；None 用适配器默认值


@dataclass
class StopContext:
    """构建 Stop 命令所需的上下文。"""
    base_url: str
    model: str


@dataclass
class UnloadRequest:
    """一个卸载/停止请求。"""
    url: str
    method: str = "POST"
    payload: dict | None = None


# ======================= unload_endpoint 解析 =======================
# 所有已知的 unload 端点预设值（无前导斜杠，与 _resolve_unload_endpoint 中
# lstrip("/") 后的值比较）。当 unload_endpoint 是这些预设值之一时，说明它是
# 旧版默认值（或用户从下拉框选的预设），应改用当前服务器类型的默认端点；
# 只有用户自定义的非预设值才被尊重。
KNOWN_UNLOAD_ENDPOINTS = {
    "v1/models/unload",
    "models/unload",
    "api/generate",
    "auto",
}


def _resolve_unload_endpoint(ctx, default_endpoint):
    """解析 unload_endpoint，返回实际使用的端点路径。

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


# ======================= 抽象基类 =======================

class ServerAdapter:
    """所有服务器适配器的抽象基类。"""

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
    def build_unload(self, ctx: UnloadContext) -> list:
        """返回卸载请求列表（可能多个候选）。"""
        raise NotImplementedError

    # ---- 停止 ----
    def build_stop_commands(self, ctx: StopContext) -> list:
        """返回停止命令请求列表（用于 Stop 按钮）。"""
        raise NotImplementedError

    # ---- 流式解析 ----
    def parse_stream_chunk(self, data: dict):
        """从单个 SSE data 块解析出 (content, reasoning)。"""
        raise NotImplementedError


# ======================= OpenAI 官方 =======================

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
        # OpenAI 托管服务无卸载端点
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


# ======================= vLLM =======================

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
        endpoint = _resolve_unload_endpoint(ctx, "/v1/models/unload")
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


# ======================= llama.cpp =======================

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
        endpoint = _resolve_unload_endpoint(ctx, "/models/unload")
        # llama.cpp 一次只加载一个模型，/models/unload 卸载当前加载的模型；
        # "卸载所有" 退化为卸载当前模型（即 ctx.model）。
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


# ======================= Ollama =======================

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
        # Ollama 无标准 reasoning_effort
        return payload

    def build_unload(self, ctx):
        # Ollama 通过 keep_alive:0 卸载
        endpoint = _resolve_unload_endpoint(ctx, "/api/generate")
        return [UnloadRequest(
            url=f"{ctx.base_url.rstrip('/')}/{endpoint.lstrip('/')}",
            method="POST",
            payload={"model": ctx.model, "keep_alive": 0},
        )]

    def build_stop_commands(self, ctx):
        # 关连接即停，无需额外命令
        return []

    def parse_stream_chunk(self, data):
        # Ollama 原生流式格式：{"response": "..."}
        return data.get("response") or "", ""


# ======================= auto 自动探测 =======================

class AutoAdapter(ServerAdapter):
    """通过探测确定实际服务器类型，所有方法委托给探测结果。"""

    server_type = "auto"

    def __init__(self, base_url="", api_key=""):
        self._detected = self._detect(base_url, api_key)

    def _probe(self, url, headers=None, timeout=3):
        try:
            req = urllib.request.Request(url, headers=headers or {})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status < 400
        except Exception:
            return False

    def _detect(self, base_url, api_key):
        base_url = (base_url or "").strip().rstrip("/")
        if not base_url:
            return OpenAIAdapter()
        auth = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        # 1. Ollama 特有 /api/tags
        if self._probe(f"{base_url}/api/tags"):
            print("[zyd232 LLM] Auto-detect: Ollama server detected.")
            return OllamaAdapter()
        # 2. llama.cpp 特有 /health
        if self._probe(f"{base_url}/health"):
            print("[zyd232 LLM] Auto-detect: llama.cpp server detected.")
            return LlamaCppAdapter()
        # 3. OpenAI 兼容 /v1/models
        if self._probe(f"{base_url}/v1/models", headers=auth):
            print("[zyd232 LLM] Auto-detect: OpenAI-compatible server detected (vLLM).")
            return vLLMAdapter()
        # 4. 默认回退 OpenAI 兼容
        print("[zyd232 LLM] Auto-detect: no server signature found, falling back to OpenAI-compatible.")
        return OpenAIAdapter()

    def chat_endpoint(self, base_url):
        return self._detected.chat_endpoint(base_url)

    def build_payload(self, ctx):
        return self._detected.build_payload(ctx)

    def build_unload(self, ctx):
        return self._detected.build_unload(ctx)

    def build_stop_commands(self, ctx):
        return self._detected.build_stop_commands(ctx)

    def parse_stream_chunk(self, data):
        return self._detected.parse_stream_chunk(data)


# ======================= 工厂 =======================

ADAPTER_REGISTRY = {
    "auto": AutoAdapter,
    "openai": OpenAIAdapter,
    "vllm": vLLMAdapter,
    "llama.cpp": LlamaCppAdapter,
    "ollama": OllamaAdapter,
}


def get_adapter(server_type, base_url="", api_key=""):
    """根据 server_type 返回适配器实例。

    ``auto`` 需要 base_url/api_key 进行探测；其他类型直接实例化。
    """
    cls = ADAPTER_REGISTRY.get(server_type, OpenAIAdapter)
    if server_type == "auto":
        return cls(base_url, api_key)
    return cls()


# ======================= 共享 Unload 辅助函数 =======================
# 这些函数原本位于 LLMGeneratorV3.py，现重构到本共享模块，供 LLM Text
# Generator 与 LLM Unload 两个节点共同复用。它们负责按 server_type 构建并
# 发送 unload 信号，并实现"同步发送 + 轮询确认"的混合卸载策略。

def send_unload_async(url, payload, headers, timeout_sec=5, method='POST'):
    """Send an unload request on a background daemon thread.

    Used so that unload requests never block the node's execute() from
    returning. llama.cpp stops processing (and unloads the model) only when it
    receives an unload/exit command, so this must be sent even when the user has
    not enabled the unload option, otherwise the server would keep processing the
    multimodal prompt after a Stop.

    ``method`` defaults to POST; pass 'DELETE' for servers that expect a DELETE
    unload request (e.g. the general /v1/models/unload endpoint).
    """
    def _do():
        try:
            req = urllib.request.Request(
                url, data=json.dumps(payload).encode('utf-8'),
                headers=headers, method=method
            )
            urllib.request.urlopen(req, timeout=timeout_sec)
        except Exception as e:
            print(f"[zyd232 LLM] Async unload request failed: {e}")

    threading.Thread(target=_do, daemon=True).start()


def send_unload_sync(url, payload, headers, timeout_sec=5, method='POST'):
    """Send an unload request synchronously and wait for the server's response.

    Unlike ``send_unload_async``, this blocks until the server has processed the
    unload request. This is essential when ``unload_after_gen`` is enabled and the
    workflow will continue to downstream nodes: if we return before the server has
    actually released its VRAM, a subsequent node that loads a large model can OOM.
    """
    try:
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode('utf-8'),
            headers=headers, method=method
        )
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            # Read the response body so the server has fully processed the request.
            resp.read()
        print(f"[zyd232 LLM] Unload request completed: {url}")
        return True
    except Exception as e:
        print(f"[zyd232 LLM] Sync unload request failed: {e}")
        return False


def wait_for_unload(base_url, model, headers, timeout_sec=3, poll_interval=0.5):
    """Poll /v1/models until the model disappears from the list, confirming unload.

    Some servers (e.g. vLLM) unload asynchronously: the unload request returns
    immediately but the model is still being released in the background. Polling
    the standard OpenAI-compatible /v1/models endpoint lets us wait until the
    model is actually gone before the workflow proceeds to downstream nodes.

    Servers that do not expose /v1/models (or that fail during unload) simply
    cause the poll to time out, which is harmless — we just proceed.
    """
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            req = urllib.request.Request(
                f"{base_url}/v1/models", headers=headers, method='GET'
            )
            with urllib.request.urlopen(req, timeout=2) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            models = [m.get("id") for m in data.get("data", [])]
            if model not in models:
                print(f"[zyd232 LLM] Model {model} confirmed unloaded.")
                return True
        except Exception:
            # Server may not support /v1/models or may be briefly unreachable
            # while unloading; ignore and keep polling until the deadline.
            pass
        time.sleep(poll_interval)
    print(f"[zyd232 LLM] Timed out waiting for unload of {model} after {timeout_sec}s.")
    return False


def unload_and_wait(adapter, base_url, model, headers, unload_endpoint,
                    server_type, timeout_sec=3):
    """Hybrid unload strategy: synchronous send + poll to confirm release.

    Used when ``unload_after_gen`` is enabled and the workflow will continue to
    downstream nodes. It:
      1. Sends the unload request(s) synchronously (waiting for the server's
         response), then
      2. Polls /v1/models until the model is confirmed released, bounded by
         ``timeout_sec`` so the node never blocks the workflow indefinitely.

    This prevents the OOM that could occur if the workflow proceeded to a
    downstream node (e.g. one that loads a large model into VRAM) before the
    server had actually finished unloading.
    """
    unload_reqs = adapter.build_unload(UnloadContext(
        base_url=base_url, model=model, unload_endpoint=unload_endpoint or None,
    ))
    # auto 模式兜底：当 server_type=auto 且探测失败（回退到 OpenAI，无卸载请求）
    # 时，尝试向所有可能的 unload 端点发送信号，确保卸载/停止信号能送达
    # （无害的 404 会被服务器忽略）。
    if server_type == "auto" and not unload_reqs:
        unload_reqs = [
            UnloadRequest(url=f"{base_url}/models/unload", method="POST", payload={"model": model}),
            UnloadRequest(url=f"{base_url}/v1/models/unload", method="DELETE", payload={"action": "unload", "model": model, "keep_alive": 0}),
            UnloadRequest(url=f"{base_url}/api/generate", method="POST", payload={"model": model, "keep_alive": 0}),
        ]
    for req in unload_reqs:
        print(f"[zyd232 LLM] Sending unload request to: {req.url} (method={req.method})")
        send_unload_sync(req.url, req.payload, headers, method=req.method)
    # Poll to confirm the model is actually released (if the server supports it).
    wait_for_unload(base_url, model, headers, timeout_sec=timeout_sec)
