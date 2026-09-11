<div align="center">

# LLM Unload

[![简体中文](https://img.shields.io/badge/简体中文-文档-blue)](LLM-Unload-简中)

</div>

> Back to [Wiki Home](Home)

## Overview

The **LLM Unload** node sends an unload signal to the LLM server so the model is released from VRAM. It is useful when a workflow runs the LLM first and then a heavy diffusion model: unloading in between keeps the two from competing for VRAM.

Almost every parameter comes from a **config preset saved by the LLM Text Generator node** — this node has no server settings of its own. It also behaves like a reroute: whatever goes into `any_input` comes out of `any_output` unchanged, so it can be inserted anywhere in a graph without breaking the chain.

- **Class name**: `zyd232 LLMUnload`
- **Category**: `zyd232 Nodes/LLM`
- **Output**: `*`

> **Before using this node**, confirm that the LLM Text Generator node can run **Unload After Gen** correctly. This node does not configure the server itself — it reuses the preset, so the preset must already hold a working `base_url`, `api_key` and model.

---

## Inputs

| Input | Type | Description |
|-------|------|-------------|
| **config_select** | `COMBO` | Choose a saved server preset. `base_url`, `api_key`, `model`, `server_type` and `unload_endpoint` are read from it. |
| **model_select** | `COMBO` | Dropdown to select the model to unload. The selection fills the `model` field below. |
| **model** | `STRING` | Model name to unload (free input). Can be typed manually or picked from the dropdown above. Leave empty to fall back to the model stored in the preset. |
| **unload_timeout** | `INT` | 0–60, default `1`. Max seconds to wait for the server to finish unloading. `0` means do not wait and continue immediately. This widget comes from the node itself — it is **not** read from the preset. |
| **any_input** | `*` (optional) | Optional passthrough value. Lets the node be inserted anywhere in the workflow. |

---

## Output

| Output | Type | Description |
|--------|------|-------------|
| **any_output** | `*` | The `any_input` value, passed through unchanged. |

---

## How It Works

1. **Load the preset** — the selected preset is read from the config file saved by the LLM Text Generator node. An invalid preset name is sanitized automatically.
2. **Resolve the API key** — an `ENV:var_name` value is read from the environment; a masked value is treated as empty. If no key remains, the node falls back to the `Default` preset's `api_key`.
3. **Resolve the model** — the node's own `model` field wins; when it is empty, the preset's `model` is used.
4. **Send the unload signal** — the signal is built according to `server_type` (`auto`, `openai`, `vllm`, `llama.cpp` or `ollama`; anything else is treated as `auto`) and sent through the shared server adapter.
5. **Confirm the release** — a hybrid strategy is used: the unload request is sent synchronously, then `/v1/models` is polled to confirm the model is actually released, bounded by `unload_timeout`. This prevents downstream nodes from OOMing while the server is still unloading.
6. **Pass through** — `any_input` is returned regardless of the outcome.

In `auto` mode, a failed probe falls back across several candidate endpoints so the unload / stop signal still gets delivered.

### When nothing is sent

The node prints a message and passes the input through **without sending anything** when:

- the preset has no `base_url`
- no model can be determined (neither the `model` field nor the preset has one)

If the unload request itself fails, the error is printed and the node still returns `any_input` — it never aborts the workflow.

---

## Limits & Notes

- **The node never blocks the graph on failure.** Errors are reported to the ComfyUI console only.
- **`unload_timeout = 0`** sends the request and continues immediately, without confirming the release. Useful when you would rather not wait, but then downstream nodes may still hit a server that is mid-unload.
- `/v1/models` must be implemented by your server for the confirmation step to work. Servers that do not expose it will simply consume the timeout.
- The presets are managed by the LLM Text Generator node; edit them there, not here.

---

## Usage Examples

- **Free VRAM between stages**: LLM Text Generator → LLM Unload → a heavy diffusion or upscaling stage. The diffusion model then gets the memory the LLM released.
- **Reroute with a side effect**: because of the `any_input` / `any_output` passthrough, the node can be dropped into any existing link to add an unload without rewiring anything else.
- **Unload a specific model**: when the server hosts several models at once, pick the target in `model_select` (or type it into `model`) instead of relying on the preset's model.

---

> Back to [Wiki Home](Home)
