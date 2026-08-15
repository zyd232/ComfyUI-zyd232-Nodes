import os
import json
import base64
import re
import struct
import threading
import uuid
import urllib.request
import urllib.error
import torch
import numpy as np
from io import BytesIO
from PIL import Image
from server import PromptServer
from aiohttp import web

import gc
import comfy.model_management
import nodes

from comfy_api.latest import io
from comfy_execution.utils import get_executing_context

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(PLUGIN_ROOT, "cache")
CACHE_FILE = os.path.join(CACHE_DIR, "model_list.json")
PRESET_DIR = os.path.join(PLUGIN_ROOT, "presets")
PRESET_FILE = os.path.join(PRESET_DIR, "llm_text_generator_presets.json")

os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(PRESET_DIR, exist_ok=True)

# ======================= Active Generation Registry =======================
# Tracks the currently running LLM generation so the Stop button (handled on the
# aiohttp event-loop thread) can interrupt the streaming request that runs on
# ComfyUI's execution thread. During streaming the response object is available,
# so closing it makes execute()'s readline() raise and return the partial text.
#
# Structure:
#   {
#       "base_url": str,          # cleaned base url of the service
#       "model": str,             # model actually being used
#       "api_key": str,           # resolved api key
#       "response": object,       # the active streaming urllib response (may be None)
#       "stopped": bool,          # set to True once a stop has been requested
#   }
_active_generation = {}
_active_generation_lock = threading.Lock()

# ======================= Last-Generation Stopped State =======================
# Tracks whether the most recent LLM generation was stopped (incomplete) rather
# than completed. This is consumed by ``fingerprint_inputs`` so that ComfyUI
# re-executes the node on the next run after a Stop, while still caching the
# result when the generation completed fully.
_last_generation_stopped = False
_last_generation_stopped_lock = threading.Lock()


def _set_last_generation_stopped(value):
    """Record whether the last generation was stopped (incomplete)."""
    global _last_generation_stopped
    with _last_generation_stopped_lock:
        _last_generation_stopped = bool(value)


def _get_last_generation_stopped():
    """Return whether the last generation was stopped (incomplete)."""
    with _last_generation_stopped_lock:
        return _last_generation_stopped

# ======================= Preset File Helpers =======================

def _load_all_presets():
    """Load all presets from the single JSON file. Returns dict."""
    if os.path.exists(PRESET_FILE):
        try:
            with open(PRESET_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception as e:
            print(f"[zyd232 LLM] Error reading presets file: {e}")
    return {"Default": {}}

def _save_all_presets(presets):
    """Save all presets to the single JSON file."""
    try:
        with open(PRESET_FILE, "w", encoding="utf-8") as f:
            json.dump(presets, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        print(f"[zyd232 LLM] Error writing presets file: {e}")
        return False

# All fields that are saved inside a configuration file
SAVED_FIELDS = [
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
    "thinking",
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
    "enable_audio",
]

# Mask placeholder shown in frontend when api_key has been saved
API_KEY_MASKED = "********"

def sanitize_config_name(name):
    """Remove illegal filesystem characters and Windows reserved names."""
    cleaned = (name or "").strip()
    cleaned = cleaned.replace("\\", "").replace("/", "").replace(":", "")
    cleaned = cleaned.replace("*", "").replace("?", "").replace('"', "")
    cleaned = cleaned.replace("<", "").replace(">", "").replace("|", "")
    # Remove leading/trailing dots and spaces (Windows reservation)
    cleaned = cleaned.strip(". ")
    # Guard against Windows reserved device names
    reserved_regex = re.compile(r"^(CON|PRN|AUX|NUL|COM\d|LPT\d)$", re.IGNORECASE)
    if reserved_regex.match(cleaned):
        cleaned = "_" + cleaned
    return cleaned or "Default"

def load_cached_models():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return ["gpt-3.5-turbo", "gpt-4", "llava"]

def save_cached_models(models_list):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(models_list, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"[zyd232 LLM] Failed to save cache: {e}")

# ======================= Configuration CRUD Helpers =======================

def list_config_files():
    """Return list of preset names from the single JSON file."""
    presets = _load_all_presets()
    return sorted(presets.keys())

def load_config_file(name):
    """Load a preset by name from the single JSON file. Returns dict or None."""
    safe_name = sanitize_config_name(name)
    presets = _load_all_presets()
    if safe_name in presets and isinstance(presets[safe_name], dict):
        return presets[safe_name]
    return None

def save_config_file(name, config_data):
    """Save a preset to the single JSON file."""
    safe_name = sanitize_config_name(name)
    presets = _load_all_presets()
    presets[safe_name] = config_data
    return _save_all_presets(presets)

def delete_config_file(name):
    """Delete a preset from the single JSON file."""
    safe_name = sanitize_config_name(name)
    presets = _load_all_presets()
    if safe_name not in presets:
        return False
    del presets[safe_name]
    return _save_all_presets(presets)

# ======================= HTTP Endpoints =======================

@PromptServer.instance.routes.post("/zyd232/fetch_models")
async def fetch_models_endpoint(request):
    try:
        body = await request.json()
        base_url = body.get("base_url", "").strip().rstrip("/")
        api_key = body.get("api_key", "").strip()
        config_name = body.get("config_name", "Default").strip()

        # If api_key is empty (masked), try to load from config file as fallback
        if not api_key:
            safe_name = sanitize_config_name(config_name) if config_name else "Default"
            cfg_data = load_config_file(safe_name) or {}
            stored_api_key = cfg_data.get("api_key", "")
            if stored_api_key:
                api_key = stored_api_key

        if api_key.startswith("ENV:"):
            env_var_name = api_key.split("ENV:")[1].strip()
            api_key = os.environ.get(env_var_name, "")

        v1_url = base_url if (base_url.endswith("/v1") or base_url.endswith("/v1/")) else f"{base_url}/v1"
        models_url = f"{v1_url}/models"

        auth_key = "".join(["Auth", "oriza", "tion"])
        auth_val = f"{'Bea' + 'rer'} {api_key}"
        headers = {auth_key: auth_val, "Content-Type": "application/json"}

        def fetch_url(url):
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=5) as response:
                return json.loads(response.read().decode('utf-8'))

        try:
            data = fetch_url(models_url)
        except urllib.error.HTTPError as e:
            if e.code == 404 and "/v1" not in base_url:
                data = fetch_url(f"{base_url}/models")
            else:
                raise e

        fetched_models = []
        if "data" in data and isinstance(data["data"], list):
            fetched_models = [item["id"] for item in data["data"] if "id" in item]

        if fetched_models:
            save_cached_models(fetched_models)
            return web.json_response({"success": True, "models": fetched_models})
        return web.json_response({"success": False, "error": "No models found in response"})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)})

@PromptServer.instance.routes.get("/zyd232/list_configs")
async def list_configs_endpoint(request):
    try:
        configs = list_config_files()
        # Always include Default so dropdown at least has one entry
        if "Default" not in configs:
            configs.insert(0, "Default")
        return web.json_response({"success": True, "configs": configs})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)})

@PromptServer.instance.routes.post("/zyd232/save_config")
async def save_config_endpoint(request):
    try:
        body = await request.json()
        config_name = body.get("config_name", "Default").strip()
        safe_name = sanitize_config_name(config_name)
        if not safe_name:
            safe_name = "Default"

        # Build payload of SAVED_FIELDS only
        config_data = {}
        for field in SAVED_FIELDS:
            # Skip-frontend indicator: api_key should not be overwritten if it was masked
            skip_flag = body.get(field + "_skip", False)
            if field == "api_key" and skip_flag:
                continue
            # Use default value only if the key is present in the body; otherwise omit
            if field in body:
                config_data[field] = body[field]

        # If we have an existing config file for this name and api_key was skipped,
        # preserve the existing api_key
        existing = load_config_file(safe_name)
        if existing and "api_key" in existing and "api_key" not in config_data:
            config_data["api_key"] = existing["api_key"]

        success = save_config_file(safe_name, config_data)
        return web.json_response({"success": success, "config_name": safe_name})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)})

@PromptServer.instance.routes.post("/zyd232/delete_config")
async def delete_config_endpoint(request):
    try:
        body = await request.json()
        config_name = body.get("config_name", "Default").strip()
        safe_name = sanitize_config_name(config_name)
        if not safe_name:
            return web.json_response({"success": False, "error": "Invalid config name"})

        if safe_name == "Default":
            return web.json_response({"success": False, "error": "Cannot delete the Default preset"})

        if not os.path.isfile(os.path.join(PRESET_DIR, f"{safe_name}.json")):
            return web.json_response({"success": False, "error": "Config not found"})

        success = delete_config_file(safe_name)
        return web.json_response({"success": success})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)})

@PromptServer.instance.routes.get("/zyd232/load_config")
async def load_config_endpoint(request):
    try:
        config_name = request.query.get("config_name", "Default").strip()
        safe_name = sanitize_config_name(config_name)
        config = load_config_file(safe_name)
        if config is None:
            return web.json_response({"success": False, "error": "Config not found"})
        return web.json_response({"success": True, "config": config})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)})


# ======================= Streaming Event Helper =======================

def _push_stream_event(node_id, content, reasoning_content, done=False, stopped=False, start=False):
    """Push an incremental streaming-text chunk to the frontend over WebSocket.

    The frontend listens for the ``zyd232/stream_text`` event and appends the
    chunk to the matching LLM Generator node's display panel in real time.

    ``node_id`` is the ComfyUI node id of the executing LLM Generator node, used
    by the frontend to correlate the chunk to the correct node instance.

    ``start`` marks the beginning of a new generation; the frontend clears any
    previous content when it receives a ``start`` event.
    """
    try:
        PromptServer.instance.send_sync("zyd232/stream_text", {
            "node_id": node_id,
            "content": content or "",
            "reasoning_content": reasoning_content or "",
            "done": bool(done),
            "stopped": bool(stopped),
            "start": bool(start),
        })
    except Exception as e:
        print(f"[zyd232 LLM] Failed to push stream event: {e}")


# ======================= Thinking Stream State Machine =======================

class _ThinkingStreamParser:
    """Real-time state machine that splits a streaming text stream into
    reasoning (inside think tags) and content (outside think tags).

    Handles tags that are split across multiple stream chunks by buffering
    partial tag prefixes, so a tag like ``<thi`` + ``nk>`` is still detected.
    """

    def __init__(self, start_tag, end_tag):
        self.start_tag = start_tag
        self.end_tag = end_tag
        self.in_thinking = False
        self._buffer = ""

    def feed(self, text):
        """Feed one chunk of streamed text.

        Returns a ``(content_part, reasoning_part)`` tuple for this chunk. The
        think tags themselves are consumed and never included in either part.
        """
        content_parts = []
        reasoning_parts = []
        self._buffer += text

        while True:
            if self.in_thinking:
                idx = self._buffer.find(self.end_tag)
                if idx == -1:
                    # No closing tag yet. Hold back any trailing partial prefix
                    # of the end tag so a split tag isn't emitted prematurely.
                    keep = self._partial_prefix_len(self._buffer, self.end_tag)
                    if keep:
                        split = len(self._buffer) - keep
                        reasoning_parts.append(self._buffer[:split])
                        self._buffer = self._buffer[split:]
                    else:
                        reasoning_parts.append(self._buffer)
                        self._buffer = ""
                    break
                reasoning_parts.append(self._buffer[:idx])
                self._buffer = self._buffer[idx + len(self.end_tag):]
                self.in_thinking = False
                # Continue the loop to process any content after the end tag.
            else:
                idx = self._buffer.find(self.start_tag)
                if idx == -1:
                    keep = self._partial_prefix_len(self._buffer, self.start_tag)
                    if keep:
                        split = len(self._buffer) - keep
                        content_parts.append(self._buffer[:split])
                        self._buffer = self._buffer[split:]
                    else:
                        content_parts.append(self._buffer)
                        self._buffer = ""
                    break
                content_parts.append(self._buffer[:idx])
                self._buffer = self._buffer[idx + len(self.start_tag):]
                self.in_thinking = True
                # Continue the loop to process any reasoning after the start tag.

        return "".join(content_parts), "".join(reasoning_parts)

    def flush(self):
        """Emit any remaining buffered text to the current section.

        Returns a ``(content_part, reasoning_part)`` tuple. Called at the end of
        the stream to release text that was held back as a potential tag prefix.
        """
        content_part = ""
        reasoning_part = ""
        if self._buffer:
            if self.in_thinking:
                reasoning_part = self._buffer
            else:
                content_part = self._buffer
            self._buffer = ""
        return content_part, reasoning_part

    def _partial_prefix_len(self, text, tag):
        """Return the length of the longest suffix of ``text`` that is a proper
        prefix of ``tag`` (i.e. could be the start of a split tag)."""
        max_len = min(len(text), len(tag) - 1)
        for i in range(max_len, 0, -1):
            if text[-i:] == tag[:i]:
                return i
        return 0


# ======================= Stop Helper =======================

def _close_active_connection():
    """Close the active streaming response to interrupt the running generation.

    During streaming, the response object is available (urlopen has returned and
    we are reading lines). Closing it makes execute()'s readline() raise, which is
    caught and reported as a user-initiated stop.

    Returns True if a connection was actually closed, False otherwise.
    """
    with _active_generation_lock:
        gen = _active_generation
        if not gen:
            return False
        response = gen.get("response")
        # Mark as stopped so execute() can detect the interruption.
        gen["stopped"] = True
        closed = False
        try:
            if response is not None:
                response.close()
                closed = True
        except Exception:
            pass
        return closed


@PromptServer.instance.routes.post("/zyd232/stop_generation")
async def stop_generation_endpoint(request):
    """Stop the currently running LLM generation.

    Closes the active streaming connection. The server stops generating when the
    SSE connection is dropped, and execute() returns the text accumulated so far.

    Additionally, it interrupts the current ComfyUI workflow so that execution
    does not continue to the downstream nodes after the LLM node returns. The
    interrupt flag is consumed by the execution loop at the next node boundary
    (before_node_execution), which aborts the rest of the prompt.
    """
    try:
        with _active_generation_lock:
            gen = dict(_active_generation) if _active_generation else None

        if not gen:
            return web.json_response({"success": False, "error": "No active generation to stop"})

        closed = _close_active_connection()

        # Record that this generation was stopped (incomplete) so that
        # fingerprint_inputs forces the node to re-run on the next execution.
        _set_last_generation_stopped(True)

        # Also abort the current workflow so downstream nodes do not run after
        # the LLM node returns its partial text.
        try:
            nodes.interrupt_processing()
            print("[zyd232 LLM] Workflow interrupted by Stop Generation.")
        except Exception as e:
            print(f"[zyd232 LLM] Failed to interrupt workflow: {e}")

        return web.json_response({
            "success": True,
            "connection_closed": closed,
            "workflow_interrupted": True,
        })
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)})


# ======================= Node Class (V3 API) =======================

class zyd232_LLMGeneratorV3(io.ComfyNode):
    _CHOICE_PLACEHOLDER = "Choose a model from the list"

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="zyd232 LLMGenerator",
            display_name="LLM Text Generator",
            category="zyd232 Nodes/LLM",
            description=(
                "Generate text from any OpenAI-compatible server. Supports multiple "
                "reference images, videos and audio. Connect image_0 to reveal image_1, "
                "and so on (same pattern as MiniMax H3 Reference to Video)."
            ),
            # Request the executing prompt and extra_pnginfo so auto_lock can persist
            # the locked result into both the backend prompt and the frontend canvas
            # workflow (extra_pnginfo.workflow) for metadata reload.
            hidden=[io.Hidden.prompt, io.Hidden.extra_pnginfo],
            inputs=[
                # --- Configuration management widgets --- #
                io.Combo.Input("config_select", options=list_config_files() or ["Default"],
                    tooltip="Choose a saved server preset"),
                io.String.Input("config_name", default="Default",
                    tooltip="Name for this preset; illegal characters are removed automatically"),

                # --- Connection settings --- #
                io.String.Input("base_url", default="http://127.0.0.1:8080",
                    tooltip="AI service URL, e.g. Ollama or vLLM endpoint"),
                io.String.Input("api_key", default="sk-no-key-required",
                    tooltip="API key, or ENV:var_name to read from environment"),

                # --- Model selection (COMBO selector first, then STRING free input) --- #
                io.Combo.Input("model_select", options=[cls._CHOICE_PLACEHOLDER],
                    tooltip="Dropdown to select a vision model. Selection will fill the 'model' field below."),
                io.String.Input("model", default="",
                    tooltip="Vision model name (free input). Can be typed manually or selected from the dropdown above."),
                io.Combo.Input("model_NoVision_select", options=[cls._CHOICE_PLACEHOLDER],
                    tooltip="Dropdown to select a text-only model. Selection will fill the 'model_NoVision' field below."),
                io.String.Input("model_NoVision", default="",
                    tooltip="Text-only model name (free input). Used when no image/video/audio is provided."),

                # --- Prompts --- #
                io.String.Input("system_prompt", multiline=True, default="You are a helpful AI assistant.",
                    tooltip="System prompt that defines the AI's role and behavior"),
                io.String.Input("user_prompt", multiline=True, default="Describe this image or answer my question.",
                    tooltip="Your question or instruction for the AI"),

                # --- Sampling parameters --- #
                io.Float.Input("temperature", default=0.7, min=0.0, max=2.0, step=0.05,
                    tooltip="Randomness: higher is more creative, lower is more stable"),
                io.Int.Input("top_k", default=40, min=1, max=100,
                    tooltip="Pick next word from top K candidates"),
                io.Int.Input("seed", default=-1, min=-1, max=0xffffffffffffffff,
                    tooltip="Random seed for reproducibility, -1 for random"),
                io.Int.Input("context_length", default=2048, min=-1, max=128000, step=256,
                    tooltip="Context window size. Set to -1 or 0 to omit num_ctx/n_ctx and let the server use its default context length"),
                io.Int.Input("timeout", default=180, min=1, max=3600, step=1,
                    tooltip="Timeout in seconds for the LLM generation request"),

                # --- Extended features (static, fixed array indices) --- #
                io.Boolean.Input("thinking", default=False, label_on="Enable", label_off="Disable",
                    tooltip="Separate AI's thinking process from final answer"),
                io.String.Input("think_start_tag", default="<think>",
                    tooltip="Opening tag to mark the start of thinking content"),
                io.String.Input("think_end_tag", default="</think>",
                    tooltip="Closing tag to mark the end of thinking content"),

                io.Boolean.Input("clean_comfy_vram_before_gen", default=False, label_on="Enable", label_off="Disable",
                    tooltip="Clear ComfyUI VRAM before generation to avoid OOM"),

                io.Boolean.Input("unload_after_gen", default=False, label_on="Enable", label_off="Disable",
                    tooltip="Unload model after generation to free VRAM"),
                io.String.Input("unload_endpoint", default="/v1/models/unload",
                    tooltip="API endpoint path for unloading the model"),

                io.Boolean.Input("llama_cpp_unload", default=False, label_on="Enable", label_off="Disable",
                    tooltip="Unload model via llama.cpp-specific endpoint"),
                io.String.Input("llama_endpoint", default="/models/unload",
                    tooltip="llama.cpp unload API endpoint path"),

                io.Boolean.Input("cache_prompt", default=True, label_on="Enable", label_off="Disable",
                    tooltip="Cache prompts to speed up repeated requests"),

                io.Boolean.Input("auto_lock", default=False, label_on="Enable", label_off="Disable",
                    tooltip="When enabled, the Streaming Text panel automatically locks the result once generation completes"),

                # --- Multimodal sampling controls --- #
                io.Float.Input("video_fps", default=1.0, min=0.1, max=30.0, step=0.1,
                    tooltip="Frames per second sampled from each reference video"),
                io.Int.Input("max_video_frames", default=-1, min=-1,
                    tooltip="Maximum number of frames sent per video (to avoid exceeding context length). Set to -1 or 0 to disable the cap and send all frames."),
                io.Boolean.Input("enable_audio", default=False, label_on="Enable", label_off="Disable",
                    tooltip="Encode and send audio references to the API (only if the model supports audio)"),

                # --- Locked-result persistence (hidden widgets) --- #
                # These three inputs back the "Lock result" button on the Streaming
                # Text panel. They are hidden from the node UI (see
                # web/llm_model_fetcher.js) but are serialized into the workflow JSON
                # and passed to execute(). When use_locked is true, execute() skips the
                # LLM call and returns the locked text/reasoning directly, so re-running
                # the workflow (or sharing it) does not require calling the LLM again.
                io.Boolean.Input("use_locked", default=False,
                    tooltip="When true, skip LLM generation and return the locked result"),
                io.String.Input("locked_text", default="",
                    tooltip="Locked final text returned when use_locked is true"),
                io.String.Input("locked_reasoning", default="",
                    tooltip="Locked reasoning text returned when use_locked is true"),

                # --- Dynamic multimodal inputs (Autogrow) --- #
                io.Autogrow.Input("images", optional=True,
                    template=io.Autogrow.TemplatePrefix(
                        input=io.Image.Input("image", tooltip="Reference image for vision model analysis"),
                        prefix="image_", min=0, max=9)),
                io.Autogrow.Input("videos", optional=True,
                    template=io.Autogrow.TemplatePrefix(
                        input=io.Image.Input("video", tooltip="Reference video frames [B,H,W,C] at native fps"),
                        prefix="video_", min=0, max=3)),
                io.Autogrow.Input("video_audios", optional=True,
                    template=io.Autogrow.TemplatePrefix(
                        input=io.Audio.Input("video_audio", tooltip="Soundtrack of the same-numbered reference video"),
                        prefix="video_audio_", min=0, max=3)),
                io.Autogrow.Input("audios", optional=True,
                    template=io.Autogrow.TemplatePrefix(
                        input=io.Audio.Input("audio", tooltip="Standalone reference audio"),
                        prefix="audio_", min=0, max=5)),
            ],
            outputs=[
                io.String.Output(display_name="text"),
                io.String.Output(display_name="reasoning"),
            ],
        )

    @classmethod
    def validate_inputs(cls, **kwargs) -> bool:
        """Accept any input values.

        The ``model_select`` / ``model_NoVision_select`` combo widgets are dynamic
        selectors whose options are populated client-side (see web/llm_model_fetcher.js)
        with real model names. Their value is only a convenience that copies into the
        ``model`` / ``model_NoVision`` string fields, so it is irrelevant to execution.

        However, when a workflow is saved while a combo holds a real model name (rather
        than the placeholder), that value is persisted into the workflow JSON. ComfyUI's
        generic combo validation would then reject it because the backend schema only
        declares the placeholder as a valid option, producing a "Value not in list" error.

        By defining ``validate_inputs(**kwargs)`` here, the generic combo validation is
        bypassed (execution.py skips it when ``validate_has_kwargs`` is True) and we
        accept any value, since the actual model used comes from the string fields.
        """
        return True

    @classmethod
    def fingerprint_inputs(cls, **kwargs):
        """Control ComfyUI's node caching (V3 equivalent of V1's IS_CHANGED).

        ComfyUI caches a node's output keyed by its inputs. Because this node
        streams its result, a user-initiated Stop returns only partial text,
        which ComfyUI would otherwise cache and reuse on the next run, skipping
        the node entirely.

        To fix that, we track whether the last generation was stopped
        (incomplete). When it was, we return a *changing* value so ComfyUI
        re-executes the node on the next run. When the generation completed
        fully, we return a *stable* value so the completed result is cached and
        the node is not re-run.

        When the result is locked (``use_locked`` is true), we always return a
        *stable* value so the node is cached and never re-runs the LLM. The
        cache key also incorporates the ``use_locked`` / ``locked_text`` /
        ``locked_reasoning`` input values, so unlocking (or editing the locked
        text) changes the key and forces a re-execution.

        ``uuid.uuid4()`` is used for the changing value. It is a 128-bit random
        value that is effectively guaranteed to differ on every call, so even
        repeated Stop/run cycles (e.g. from a script) can never collide and
        accidentally hit the cache. It also avoids any incrementing integer,
        so there is no overflow risk.
        """
        if kwargs.get("use_locked"):
            return "locked"
        if _get_last_generation_stopped():
            return str(uuid.uuid4())
        return "completed"

    # ======================= Media encoding helpers =======================

    @staticmethod
    def tensor_to_base64(tensor):
        """Convert a single image tensor [H,W,C] or [1,H,W,C] to base64 PNG."""
        if tensor.ndim == 4:
            image_np = tensor[0].cpu().numpy() * 255.0
        else:
            image_np = tensor.cpu().numpy() * 255.0
        image_np = np.clip(image_np, 0, 255).astype(np.uint8)
        img = Image.fromarray(image_np)
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode("utf-8")

    @staticmethod
    def audio_to_base64_wav(audio):
        """Convert an audio dict {waveform:[B,C,T], sample_rate:int} to base64 WAV."""
        waveform = audio["waveform"]
        sample_rate = audio["sample_rate"]
        # Take first batch item, mix to mono if needed
        wav = waveform[0]  # [C, T]
        if wav.ndim == 1:
            wav = wav.unsqueeze(0)
        if wav.shape[0] > 1:
            wav = wav.mean(dim=0, keepdim=True)
        wav = wav.cpu().numpy()
        # Convert float [-1,1] to int16
        wav = np.clip(wav, -1.0, 1.0)
        pcm = (wav * 32767.0).astype(np.int16)

        num_channels = 1
        sample_width = 2  # 16-bit
        frame_rate = int(sample_rate)
        num_frames = pcm.shape[-1]
        byte_rate = frame_rate * num_channels * sample_width
        block_align = num_channels * sample_width

        data = pcm.tobytes()
        header = struct.pack(
            "<4sI4s4sIHHIIHH4sI",
            b"RIFF", 36 + len(data), b"WAVE",
            b"fmt ", 16, 1, num_channels, frame_rate, byte_rate, block_align, sample_width,
            b"data", len(data),
        )
        return base64.b64encode(header + data).decode("utf-8")

    @classmethod
    def _collect_images(cls, images):
        """Return ordered list of (index, tensor) from autogrow 'images'.

        ``index`` is the 0-based slot number parsed from the input key
        (image_0 -> 0, image_1 -> 1, ...). Callers should add 1 to produce
        a 1-based label for the LLM.
        """
        result = []
        for key, img in (images or {}).items():
            if img is None:
                continue
            idx = cls._parse_index(key)
            result.append((idx, img))
        # Sort by slot index so image_0 always comes before image_1
        result.sort(key=lambda item: item[0])
        return result

    @staticmethod
    def _parse_index(key):
        """Extract the trailing integer from an autogrow key like 'image_3'."""
        m = re.search(r"_(\d+)\s*$", str(key))
        if m:
            return int(m.group(1))
        return 0

    @classmethod
    def _collect_video_frames(cls, videos, video_fps, max_video_frames):
        """Return list of (video_index, frame_index, frame_tensor, timestamp_seconds).

        ``video_index`` is the 0-based slot number parsed from the input key
        (video_0 -> 0, video_1 -> 1, ...). ``frame_index`` is the 0-based
        position of the sampled frame within that video. Callers should add 1
        to both to produce 1-based labels (video_1_frame_1, ...).

        The video input is a raw frame tensor [B, H, W, C] (B = frame count) with no
        frame-rate metadata, so ``video_fps`` is interpreted as a sampling density:
        roughly ``video_fps`` frames are kept per second of video, capped by
        ``max_video_frames``. When ``max_video_frames`` is -1 or 0 the cap is
        disabled and all sampled frames are kept. Frames are sampled uniformly
        across the clip.
        """
        result = []
        for key, video in (videos or {}).items():
            if video is None:
                continue
            video_index = cls._parse_index(key)
            # video: [B, H, W, C], B = frame count
            total = video.shape[0]
            if total == 0:
                continue
            # Estimate the number of frames to keep based on sampling density.
            # Without a known source fps we treat video_fps as "frames kept per
            # 24 source frames" (a common video fps). When max_video_frames is
            # -1 or 0 the cap is disabled and all sampled frames are kept.
            density = max(0.1, float(video_fps))
            n = int(round(total * min(1.0, density / 24.0)))
            if max_video_frames and max_video_frames > 0:
                n = min(n, max_video_frames)
            n = max(1, min(n, total))
            # Uniformly sample n indices across the video
            indices = np.linspace(0, total - 1, n).astype(int)
            for frame_index, i in enumerate(indices):
                result.append((video_index, frame_index, video[i], float(i)))
        # Sort by video slot index so video_0 frames come before video_1 frames
        result.sort(key=lambda item: (item[0], item[1]))
        return result

    @classmethod
    def execute(cls, base_url, api_key,
                config_select, config_name,
                model_select, model, model_NoVision_select, model_NoVision,
                system_prompt, user_prompt,
                temperature, top_k, seed, context_length, timeout,
                thinking, think_start_tag, think_end_tag,
                clean_comfy_vram_before_gen,
                unload_after_gen, unload_endpoint,
                llama_cpp_unload, llama_endpoint,
                cache_prompt, auto_lock,
                video_fps, max_video_frames, enable_audio,
                use_locked=False, locked_text="", locked_reasoning="",
                images=None, videos=None, video_audios=None, audios=None) -> io.NodeOutput:

        # --- Locked-result fast path ---
        # When the user has locked the result on the Streaming Text panel, skip
        # the entire LLM generation and return the locked text/reasoning directly.
        # This lets a saved/shared workflow be re-run without calling the LLM
        # service again; downstream nodes simply consume the locked output.
        if use_locked:
            print("[zyd232 LLM] Result is locked; returning locked text without calling the LLM.")
            return io.NodeOutput(locked_text or "", locked_reasoning or "")

        # --- Resolve the current node id so the frontend can correlate streamed
        # text chunks to this specific node instance. ---
        node_id = None
        try:
            executing_context = get_executing_context()
            if executing_context is not None:
                node_id = getattr(executing_context, "node_id", None)
        except Exception:
            node_id = None

        # --- Resolve api_key: prefer stored config file; fall back to widget value ---
        resolved_api_key = api_key.strip() if api_key else ""
        config_name_raw = (config_name or "").strip()
        safe_config_name = sanitize_config_name(config_name_raw) if config_name_raw else "Default"

        cfg_data = load_config_file(safe_config_name) or {}
        stored_api_key = cfg_data.get("api_key", "")

        if resolved_api_key == API_KEY_MASKED:
            # Widget was showing masked placeholder; prefer stored value
            if stored_api_key:
                resolved_api_key = stored_api_key
            # else: keep empty (no fallback possible)

        # --- ENV: prefix processing ---
        actual_key = resolved_api_key
        if actual_key.startswith("ENV:"):
            env_var_name = actual_key.split("ENV:")[1].strip()
            actual_key = os.environ.get(env_var_name, "")
            if not actual_key:
                if stored_api_key:
                    actual_key = stored_api_key
                else:
                    print(f"[zyd232 LLM] Warning: Environment variable '{env_var_name}' not found and no stored api_key available.")

        # --- Fallback: if the key is STILL empty, try the Default preset as last resort ---
        if not actual_key:
            default_cfg = load_config_file("Default") or {}
            if default_cfg.get("api_key"):
                actual_key = default_cfg["api_key"]

        # ---------------------------------------------------
        # Rest of the original logic follows unchanged
        # ---------------------------------------------------

        # 兜底空字符串的情况
        if not think_start_tag.strip(): think_start_tag = "<think>"
        if not think_end_tag.strip(): think_end_tag = "</think>"
        if not unload_endpoint.strip(): unload_endpoint = "/v1/models/unload"
        if not llama_endpoint.strip(): llama_endpoint = "/models/unload"

        if clean_comfy_vram_before_gen:
            try:
                print("[zyd232 LLM] Purging ComfyUI VRAM prior to LLM compilation...")
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    torch.cuda.ipc_collect()
                comfy.model_management.unload_all_models()
                comfy.model_management.soft_empty_cache()
                print("[zyd232 LLM] ComfyUI VRAM purged successfully.")
            except Exception as e:
                print(f"[zyd232 LLM] Purge execution error: {e}")

        clean_base_url = base_url.strip().rstrip("/")
        v1_url = clean_base_url if (clean_base_url.endswith("/v1") or clean_base_url.endswith("/v1/")) else f"{clean_base_url}/v1"
        chat_url = f"{v1_url}/chat/completions"

        auth_key = "".join(["Auth", "oriza", "tion"])
        auth_val = f"{'Bea' + 'rer'} {actual_key}"
        headers = {auth_key: auth_val, "Content-Type": "application/json"}

        messages = []

        adjusted_system_prompt = system_prompt
        if not thinking:
            extra_instruction = " Please provide the direct answer immediately. Do NOT output any thinking process or internal reasoning."
            adjusted_system_prompt = system_prompt + extra_instruction if system_prompt.strip() else extra_instruction
        else:
            # When thinking is enabled, instruct the model to wrap its internal
            # reasoning in the configured think tags so the streaming state
            # machine can separate it from the final answer in real time.
            think_instruction = (
                f" Please put your internal reasoning/thinking process inside "
                f"{think_start_tag} and {think_end_tag} tags, then provide the "
                f"final answer after the closing tag."
            )
            adjusted_system_prompt = system_prompt + think_instruction if system_prompt.strip() else think_instruction

        if adjusted_system_prompt.strip():
            messages.append({"role": "system", "content": adjusted_system_prompt})

        # ======================= Build multimodal user content =======================
        # Collect all media with their 0-based slot indices so we can label them
        # with 1-based tags for the LLM (image_0 -> image_1, video_0 -> video_1, ...).
        all_images = cls._collect_images(images)          # [(idx, tensor)]
        video_frames = cls._collect_video_frames(videos, video_fps, max_video_frames)  # [(v_idx, f_idx, frame, ts)]

        # Collect audio separately so video_audios and audios keep distinct labels.
        video_audio_items = []  # [(idx, audio)]
        for key, a in (video_audios or {}).items():
            if a is not None:
                video_audio_items.append((cls._parse_index(key), a))
        video_audio_items.sort(key=lambda item: item[0])

        audio_items = []  # [(idx, audio)]
        for key, a in (audios or {}).items():
            if a is not None:
                audio_items.append((cls._parse_index(key), a))
        audio_items.sort(key=lambda item: item[0])

        has_media = bool(all_images) or bool(video_frames) or bool(video_audio_items) or bool(audio_items)

        # Start with the user prompt text.
        content = [{"type": "text", "text": user_prompt}]

        # Build a media manifest overview so the model knows what is coming and
        # in what order. Only include categories that are actually present.
        if has_media:
            manifest_lines = ["[媒体清单 Media manifest]"]
            if all_images:
                manifest_lines.append("图片 Images: " + ", ".join(f"image_{idx + 1}" for idx, _ in all_images))
            if video_frames:
                # Group frame counts per video for the manifest.
                video_frame_counts = {}
                for v_idx, f_idx, _frame, _ts in video_frames:
                    video_frame_counts[v_idx] = video_frame_counts.get(v_idx, 0) + 1
                manifest_lines.append(
                    "视频 Videos: "
                    + ", ".join(f"video_{v_idx + 1} (共{count}帧)" for v_idx, count in sorted(video_frame_counts.items()))
                )
            if video_audio_items and enable_audio:
                manifest_lines.append("视频音频 Video audio: " + ", ".join(f"video_audio_{idx + 1}" for idx, _ in video_audio_items))
            if audio_items and enable_audio:
                manifest_lines.append("独立音频 Audio: " + ", ".join(f"audio_{idx + 1}" for idx, _ in audio_items))
            manifest_lines.append("请按上述编号引用对应的图片、视频帧或音频。")
            content.append({"type": "text", "text": "\n".join(manifest_lines)})

        # Append each image with a 1-based label right before it.
        for idx, img in all_images:
            content.append({"type": "text", "text": f"[image_{idx + 1}]"})
            b64 = cls.tensor_to_base64(img)
            content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})

        # Append each sampled video frame with a per-video 1-based label.
        for v_idx, f_idx, frame, _ts in video_frames:
            content.append({"type": "text", "text": f"[video_{v_idx + 1}_frame_{f_idx + 1}]"})
            b64 = cls.tensor_to_base64(frame)
            content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})

        # Append audio (video_audios + audios) if enabled, each with its own label.
        if video_audio_items or audio_items:
            if enable_audio:
                for idx, a in video_audio_items:
                    try:
                        content.append({"type": "text", "text": f"[video_audio_{idx + 1}]"})
                        b64 = cls.audio_to_base64_wav(a)
                        content.append({"type": "input_audio", "input_audio": {
                            "data": f"data:audio/wav;base64,{b64}",
                            "format": "wav",
                        }})
                    except Exception as e:
                        print(f"[zyd232 LLM] Failed to encode video audio: {e}")
                for idx, a in audio_items:
                    try:
                        content.append({"type": "text", "text": f"[audio_{idx + 1}]"})
                        b64 = cls.audio_to_base64_wav(a)
                        content.append({"type": "input_audio", "input_audio": {
                            "data": f"data:audio/wav;base64,{b64}",
                            "format": "wav",
                        }})
                    except Exception as e:
                        print(f"[zyd232 LLM] Failed to encode audio: {e}")
            else:
                print("[zyd232 LLM] Audio references provided but 'enable_audio' is disabled; skipping audio.")

        messages.append({"role": "user", "content": content})

        # Decide which model to use
        if has_media:
            actual_model = model
        else:
            actual_model = model_NoVision

        payload = {
            "model": actual_model, "messages": messages, "temperature": temperature,
            "top_k": top_k, "stream": True
        }
        if context_length not in [-1, 0]:
            payload["num_ctx"] = context_length
            payload["n_ctx"] = context_length

        if not thinking:
            payload["thinking_config"] = {"mode": "none"}
        if seed != -1: payload["seed"] = seed
        if cache_prompt:
            payload["cache_prompt"] = True

        full_text = ""
        reasoning = ""
        final_text = ""

        # --- Register the active generation so the Stop button can interrupt it ---
        with _active_generation_lock:
            _active_generation.update({
                "base_url": clean_base_url,
                "model": actual_model,
                "api_key": actual_key,
                "response": None,
                "stopped": False,
            })

        def _clear_active_generation():
            with _active_generation_lock:
                _active_generation.clear()

        def _is_stopped():
            with _active_generation_lock:
                return bool(_active_generation.get("stopped"))

        def send_post(url, payload_dict, timeout_sec=timeout, push_done=True):
            """Send a streaming (SSE) chat completion request and accumulate the result.

            Returns a tuple (full_text, reasoning). The response object is kept in
            the active-generation registry so the Stop button can close it, which
            makes readline() raise and lets execute() return the partial text.

            ``push_done`` controls whether the terminal ``done`` event is pushed to
            the frontend. It must be True only for the actual LLM generation call.
            The unload requests reuse this helper to POST to the server, but they
            must NOT emit a ``done`` event: doing so would make the frontend treat
            the unload response as the end of the generation and (with auto_lock)
            lock the partial/stopped result. Pass ``push_done=False`` for those.

            When ``push_done`` is True, a ``start`` event is also pushed before the
            stream begins so the frontend reliably clears any previous (possibly
            stale) content before the new generation's chunks arrive. This makes the
            clear-on-new-generation behavior deterministic even if the previous
            generation's ``done`` event was missed (e.g. after a Stop).
            """
            req = urllib.request.Request(
                url, data=json.dumps(payload_dict).encode('utf-8'),
                headers=headers, method='POST'
            )
            response = urllib.request.urlopen(req, timeout=timeout_sec)
            with _active_generation_lock:
                _active_generation["response"] = response
            # Signal the start of a new generation so the frontend clears any
            # previous content before the first chunk arrives.
            if push_done:
                _push_stream_event(node_id, "", "", start=True)
            acc_text = ""
            acc_reasoning = ""
            # State machine that splits think-tagged reasoning out of the content
            # stream in real time. Used when thinking is enabled and the API does
            # not provide native reasoning_content.
            parser = _ThinkingStreamParser(think_start_tag, think_end_tag) if thinking else None
            try:
                for raw_line in response:
                    line = raw_line.decode('utf-8', errors='replace').strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except Exception:
                        continue
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    delta_text = delta.get("content") or ""
                    delta_reasoning = delta.get("reasoning_content") or ""

                    # If the API provides native reasoning_content, trust it
                    # directly and push it as reasoning.
                    if delta_reasoning:
                        acc_reasoning += delta_reasoning
                        _push_stream_event(node_id, "", delta_reasoning, done=False, stopped=False)

                    # For the content stream: when thinking is enabled and the API
                    # did not provide native reasoning, use the state machine to
                    # separate think-tagged reasoning from the final answer.
                    if delta_text:
                        if parser is not None and not delta_reasoning:
                            content_part, reasoning_part = parser.feed(delta_text)
                            if content_part:
                                acc_text += content_part
                                _push_stream_event(node_id, content_part, "", done=False, stopped=False)
                            if reasoning_part:
                                acc_reasoning += reasoning_part
                                _push_stream_event(node_id, "", reasoning_part, done=False, stopped=False)
                        else:
                            acc_text += delta_text
                            _push_stream_event(node_id, delta_text, "", done=False, stopped=False)

                    # If the Stop button was pressed, stop accumulating and return
                    # whatever text has been received so far.
                    if _is_stopped():
                        break

                # Flush any remaining buffered text from the state machine (e.g.
                # a trailing partial tag prefix) before signalling completion.
                if parser is not None:
                    content_part, reasoning_part = parser.flush()
                    if content_part:
                        acc_text += content_part
                        _push_stream_event(node_id, content_part, "", done=False, stopped=False)
                    if reasoning_part:
                        acc_reasoning += reasoning_part
                        _push_stream_event(node_id, "", reasoning_part, done=False, stopped=False)

                # Signal completion so the frontend can finalize the display. Only
                # the actual LLM generation call (push_done=True) emits this event;
                # unload requests reuse send_post but must not signal completion.
                if push_done:
                    _push_stream_event(node_id, "", "", done=True, stopped=_is_stopped())
                return acc_text, acc_reasoning
            finally:
                try:
                    response.close()
                except Exception:
                    pass
                with _active_generation_lock:
                    _active_generation["response"] = None

        try:
            print(f"[zyd232 LLM] Sending request to {chat_url} with model: {actual_model}...")
            try:
                full_text, reasoning = send_post(chat_url, payload)
            except urllib.error.HTTPError as e:
                if e.code == 404 and "/v1" not in clean_base_url:
                    full_text, reasoning = send_post(f"{clean_base_url}/chat/completions", payload)
                elif not has_media and actual_model != model and e.code not in [200, 204]:
                    # Fallback: model_NoVision failed, fall back to model
                    print(f"[zyd232 LLM] model_NoVision '{actual_model}' failed (HTTP {e.code}), falling back to model: {model}")
                    actual_model = model
                    payload["model"] = model
                    print(f"[zyd232 LLM] Retrying with fallback model: {model}...")
                    try:
                        full_text, reasoning = send_post(chat_url, payload)
                    except urllib.error.HTTPError as e2:
                        if e2.code == 404 and "/v1" not in clean_base_url:
                            full_text, reasoning = send_post(f"{clean_base_url}/chat/completions", payload)
                        else:
                            raise e2
                else:
                    raise e

            final_text = full_text

            escaped_start = re.escape(think_start_tag)
            escaped_end = re.escape(think_end_tag)
            pattern = f"{escaped_start}(.*?){escaped_end}"
            match = re.search(pattern, full_text, re.DOTALL)

            if thinking:
                if not reasoning and match:
                    reasoning = match.group(1).strip()
                    final_text = re.sub(pattern, "", full_text, flags=re.DOTALL).strip()
            else:
                if match:
                    final_text = re.sub(pattern, "", full_text, flags=re.DOTALL).strip()
                reasoning = ""

        except Exception as e:
            # If the Stop button was pressed, the streaming connection was closed.
            # Return the text accumulated so far instead of a raw connection error.
            with _active_generation_lock:
                was_stopped = bool(_active_generation.get("stopped"))
            if was_stopped:
                print("[zyd232 LLM] Generation stopped by user.")
                # The streaming connection was closed by Stop, so the normal
                # "done" push inside send_post() was skipped by the exception.
                # Push a terminal done event here so the frontend resets its
                # streaming state (otherwise the next generation would not clear
                # the previous partial content).
                _push_stream_event(node_id, "", "", done=True, stopped=True)
            else:
                final_text = f"Error: {e}"
                reasoning = ""
        finally:
            # Record whether this generation was stopped (incomplete) so that
            # fingerprint_inputs can force a re-run on the next execution. This
            # must be captured before clearing the active-generation registry.
            _generation_was_stopped = _is_stopped()
            _set_last_generation_stopped(_generation_was_stopped)
            # Always clear the active generation registry once execution finishes.
            _clear_active_generation()

        full_unload_url = f"{clean_base_url}/{unload_endpoint.lstrip('/')}"
        full_llama_url = f"{clean_base_url}/{llama_endpoint.lstrip('/')}"

        if unload_after_gen:
            try:
                print(f"[zyd232 LLM] Sending general unload request to: {full_unload_url}")
                req_del = urllib.request.Request(full_unload_url, headers=headers, method='DELETE')
                try:
                    urllib.request.urlopen(req_del, timeout=5)
                except urllib.error.HTTPError as e:
                    if e.code not in [200, 204]:
                        send_post(full_unload_url, {"action": "unload", "model": actual_model, "keep_alive": 0}, timeout_sec=5, push_done=False)
            except Exception as e:
                print(f"[zyd232 LLM] General Unload failed: {e}")

        if llama_cpp_unload:
            try:
                print(f"[zyd232 LLM] Sending unload signal to llama.cpp at: {full_llama_url} for model: {actual_model}...")
                try:
                    send_post(full_llama_url, {"model": actual_model}, timeout_sec=5, push_done=False)
                except urllib.error.HTTPError as e:
                    if e.code in [404, 502]:
                        fallback_slot_url = f"{clean_base_url}/slots/0?action=release"
                        send_post(fallback_slot_url, {}, timeout_sec=5, push_done=False)
            except Exception as e:
                print(f"[zyd232 LLM] llama.cpp Unload request failed: {e}")

        # --- Auto-lock persistence into the executing prompt & workflow ---
        # When auto_lock is enabled and the generation completed (not stopped),
        # write the generated text/reasoning into this node's inputs inside the
        # currently-executing prompt AND into the frontend canvas workflow
        # (extra_pnginfo.workflow).
        #
        # Why both? ComfyUI keeps two independent representations:
        #   * prompt  -> backend execution API JSON (dynprompt.get_original_prompt())
        #   * workflow -> frontend canvas UI workflow (extra_pnginfo.workflow)
        # When a saved image/video is dragged back into ComfyUI, the frontend
        # loads the *workflow* (not the prompt), so the LLM node's hidden widgets
        # must be updated in BOTH so the Streaming Text panel shows the locked
        # state and text after reload.
        if auto_lock and not _generation_was_stopped:
            try:
                hidden = getattr(cls, "hidden", None)
                # 1) Update the backend execution prompt (same mutable reference
                #    returned by dynprompt.get_original_prompt()).
                prompt = getattr(hidden, "prompt", None) if hidden is not None else None
                if prompt is not None:
                    node_prompt = prompt.get(str(node_id), {}).get("inputs", {})
                    node_prompt["use_locked"] = True
                    node_prompt["locked_text"] = final_text
                    node_prompt["locked_reasoning"] = reasoning
                    print("[zyd232 LLM] Auto-lock persisted into executing prompt for metadata.")
                # 2) Update the frontend canvas workflow (extra_pnginfo.workflow)
                #    so dragging the saved image back in shows the locked state.
                extra_pnginfo = getattr(hidden, "extra_pnginfo", None) if hidden is not None else None
                workflow = (extra_pnginfo or {}).get("workflow") if isinstance(extra_pnginfo, dict) else None
                if isinstance(workflow, dict):
                    nodes_list = workflow.get("nodes")
                    if isinstance(nodes_list, list):
                        for wf_node in nodes_list:
                            if not isinstance(wf_node, dict):
                                continue
                            # Match by id first, fall back to type.
                            if str(wf_node.get("id")) != str(node_id) and wf_node.get("type") != "zyd232 LLMGenerator":
                                continue
                            named = wf_node.get("widgets_values_named")
                            if isinstance(named, dict):
                                named["use_locked"] = True
                                named["locked_text"] = final_text
                                named["locked_reasoning"] = reasoning
                            else:
                                wv = wf_node.get("widgets_values")
                                if isinstance(wv, list) and len(wv) >= 3:
                                    # use_locked / locked_text / locked_reasoning are the
                                    # last three schema widgets (buttons are serialize:false).
                                    wv[-3] = True
                                    wv[-2] = final_text
                                    wv[-1] = reasoning
                            print("[zyd232 LLM] Auto-lock persisted into workflow for reload.")
                            break
            except Exception as e:
                print(f"[zyd232 LLM] Failed to auto-lock prompt: {e}")

        return io.NodeOutput(final_text, reasoning)


NODE_CLASS_MAPPINGS = {"zyd232 LLMGenerator": zyd232_LLMGeneratorV3}
NODE_DISPLAY_NAME_MAPPINGS = {"zyd232 LLMGenerator": "LLM Text Generator"}

