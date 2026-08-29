"""LLM Unload 节点：向 LLM Server 发送 unload 信号，从显存卸载模型。

这是 LLM Text Generator 的简化版本，仅保留 config preset 栏目与
Refresh Config List 按钮。所有发送 unload 信号所需的参数（base_url、
api_key、model、server_type、unload_endpoint、unload_timeout）都直接
从当前选择的 config preset 中读取，而不是来自节点自身的参数。

与 LLM Text Generator 一样，根据 server_type 决定发送什么样的信号，
整个 unload 流程与兜底机制（auto 模式多端点兜底、同步发送 + 轮询确认
的混合策略）都复用共享模块 llm_server_adapters.py 中的实现。
"""

import importlib.util
import os
import sys

from comfy_api.latest import io

# nodes/ 目录不是 Python 包（模块按文件路径在 __init__.py 中加载），因此
# 这里按文件路径加载共享模块并缓存到 sys.modules，保证单一共享实例。
_NODES_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_shared_module(filename, module_name):
    """按文件路径加载 nodes/ 下的共享模块并缓存到 sys.modules。"""
    if module_name in sys.modules:
        return sys.modules[module_name]
    path = os.path.join(_NODES_DIR, filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# 共享 ServerAdapter 模块：提供 get_adapter / UnloadContext / UnloadRequest /
# unload_and_wait 等 unload 相关实现。
_adapters = _load_shared_module("llm_server_adapters.py", "zyd232_llm_server_adapters")
get_adapter = _adapters.get_adapter
UnloadContext = _adapters.UnloadContext
UnloadRequest = _adapters.UnloadRequest
unload_and_wait = _adapters.unload_and_wait

# 共享 LLMGeneratorV3 模块：复用其 config preset 读取辅助函数（load_config_file、
# list_config_files、sanitize_config_name、API_KEY_MASKED）。
# 注意：模块名必须与 __init__.py 中 _load_node_module 使用的
# "zyd232_nodes_LLMGeneratorV3" 完全一致，这样当 __init__.py 已加载过该模块时
# 会直接复用，避免重复执行模块（重复注册 HTTP 路由）。
_llm_gen = _load_shared_module("LLMGeneratorV3.py", "zyd232_nodes_LLMGeneratorV3")
load_config_file = _llm_gen.load_config_file
list_config_files = _llm_gen.list_config_files
sanitize_config_name = _llm_gen.sanitize_config_name
API_KEY_MASKED = _llm_gen.API_KEY_MASKED

# 合法的 server_type 取值（与 LLM Text Generator 一致）。
_VALID_SERVER_TYPES = ("auto", "openai", "vllm", "llama.cpp", "ollama")


def _resolve_api_key(cfg):
    """解析 config preset 中的 api_key。

    支持 ENV:var_name 从环境变量读取；若为空则回退到 Default preset 的
    api_key（与 LLM Text Generator 的兜底逻辑一致）。
    """
    key = (cfg.get("api_key") or "").strip()
    if key == API_KEY_MASKED:
        key = ""
    if key.startswith("ENV:"):
        env_var = key.split("ENV:")[1].strip()
        key = os.environ.get(env_var, "")
    if not key:
        default_cfg = load_config_file("Default") or {}
        key = (default_cfg.get("api_key") or "").strip()
        if key == API_KEY_MASKED:
            key = ""
    return key


# ======================= Node Class (V3 API) =======================

class zyd232_LLMUnload(io.ComfyNode):
    """向 LLM Server 发送 unload 信号，从显存卸载模型。

    所有参数均来自 LLM Text Generator 所保存的 config preset。载入该
    config preset 时，LLM Text Generator 节点能够在 Unload After Gen 开启时
    正常跑通，并在生成结束后指挥 LLM Server 从显存卸载模型。
    """

    _CHOICE_PLACEHOLDER = "Choose a model from the list"

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="zyd232 LLMUnload",
            display_name="LLM Unload",
            category="zyd232 Nodes/LLM",
            description=(
                "Send an unload signal to the LLM Server to release the model from VRAM. "
                "All parameters come from the config preset saved by the LLM Text Generator "
                "node. Before using this node, first confirm that the LLM Text Generator "
                "node's configuration can run 'Unload After Gen' correctly, because this "
                "node's proper operation relies on the parameters stored in the config "
                "preset being correctly configured. Acts like a reroute: the any input is "
                "passed through unchanged to the any output."
            ),
            inputs=[
                # --- Configuration management widgets --- #
                io.Combo.Input("config_select", options=list_config_files() or ["Default"],
                    display_name="Config Preset",
                    tooltip=(
                        "Choose a saved server preset. All unload parameters (base_url, api_key, "
                        "model, server_type, unload_endpoint, unload_timeout) are read from this "
                        "preset, which is saved by the LLM Text Generator node."
                    )),
                # --- Model selection (which model to unload) --- #
                # 下拉选择要卸载的模型；选择后填入下方的 model 字段。
                io.Combo.Input("model_select", options=[cls._CHOICE_PLACEHOLDER],
                    display_name="Model Select",
                    tooltip=(
                        "Dropdown to select the model to unload. Selection fills the 'model' field below."
                    )),
                io.String.Input("model", default="",
                    display_name="Model",
                    tooltip=(
                        "Model name to unload (free input). Can be typed manually or selected from the "
                        "dropdown above. Leave empty to fall back to the model stored in the config preset."
                    )),
                # --- Passthrough (reroute-like) --- #
                # optional=True：入口/出口可连接也可不连接，工作流都能跑通。
                io.AnyType.Input("any_input", display_name="Any Input", optional=True,
                    tooltip="Optional. Any value passed through unchanged. Lets this node be inserted anywhere in the workflow."),
            ],
            outputs=[
                io.AnyType.Output("any_output", display_name="Any Output",
                    tooltip="The input value passed through unchanged."),
            ],
        )

    @classmethod
    def execute(cls, config_select, model_select, model, any_input=None) -> io.NodeOutput:
        # --- Resolve the selected config preset ---
        safe_name = sanitize_config_name(config_select) if config_select else "Default"
        cfg = load_config_file(safe_name) or {}

        # --- Extract unload parameters from the preset ---
        base_url = (cfg.get("base_url") or "").strip().rstrip("/")
        server_type = cfg.get("server_type") or "auto"
        if server_type not in _VALID_SERVER_TYPES:
            server_type = "auto"
        unload_endpoint = (cfg.get("unload_endpoint") or "").strip()
        if not unload_endpoint:
            unload_endpoint = ""
        try:
            unload_timeout = int(cfg.get("unload_timeout") or 3)
        except (TypeError, ValueError):
            unload_timeout = 3
        if unload_timeout < 1:
            unload_timeout = 3

        api_key = _resolve_api_key(cfg)

        # --- Resolve which model to unload ---
        # 优先级：节点自身的 model 字段 > config preset 中的 model。
        model = (model or "").strip()
        if not model:
            model = (cfg.get("model") or "").strip()

        if not base_url:
            print(f"[zyd232 LLM] LLM Unload: preset '{safe_name}' is missing base_url; "
                  f"cannot send unload signal.")
            return io.NodeOutput(any_input)
        if not model:
            print(f"[zyd232 LLM] LLM Unload: no model specified and preset '{safe_name}' has no "
                  f"model; cannot send unload signal.")
            return io.NodeOutput(any_input)

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        # --- 根据 server_type 构建并发送 unload 信号 ---
        # 复用共享的 unload_and_wait 混合策略：同步发送 unload 请求，然后轮询
        # /v1/models 确认模型已释放，受 unload_timeout 限制。auto 模式在探测
        # 失败时会走多端点兜底，确保卸载/停止信号能送达。
        try:
            adapter = get_adapter(server_type, base_url, api_key)
            unload_and_wait(
                adapter, base_url, model, headers,
                unload_endpoint, server_type,
                timeout_sec=unload_timeout,
            )
            print(f"[zyd232 LLM] LLM Unload: sent unload signal for model '{model}' "
                  f"(server_type={server_type}, preset='{safe_name}').")
        except Exception as e:
            print(f"[zyd232 LLM] LLM Unload: unload request failed: {e}")

        return io.NodeOutput(any_input)
