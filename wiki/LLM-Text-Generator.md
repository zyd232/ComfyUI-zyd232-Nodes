<div align="center">

# LLM Text Generator

[![简体中文](https://img.shields.io/badge/简体中文-文档-blue)](LLM-Text-Generator-简中)

</div>

> Back to [Wiki Home](Home)

## Overview

The **LLM Text Generator** node connects to any **OpenAI-compatible** LLM service (Ollama, vLLM, llama.cpp, LocalAI, etc.) for text generation inside ComfyUI workflows. It supports multiple reference images, videos, and audio, and can display generated text in real time via streaming (SSE).

- **Class name**: `zyd232 LLMGenerator`
- **Category**: `zyd232 Nodes/LLM`
- **Outputs**: `text` (final answer), `reasoning` (thinking process)

---

## Table of Contents

- [Config Preset System](#config-preset-system)
- [API Key & Environment Variables](#api-key--environment-variables)
- [Model Selection](#model-selection)
- [Multimodal Inputs (Images / Videos / Audio)](#multimodal-inputs-images--videos--audio)
- [Streaming Text Display](#streaming-text-display)
- [Lock Result](#lock-result)
- [Thinking / Reasoning Mode](#thinking--reasoning-mode)
- [Other Parameters Quick Reference](#other-parameters-quick-reference)

---

## Config Preset System

Save all your settings (API URL, key, model, prompts, parameters) as named presets and switch between them with one click. Presets are stored in a single JSON file (`presets/llm_text_generator_presets.json`).

### How to use

1. **Configure the node** — Fill in `base_url`, `api_key`, choose a model, write your prompts, and set other parameters.
2. **Name your preset** — Type a name into the **config_name** field (e.g., "My Ollama", "GPT-4o"). Invalid file-system characters are automatically removed.
3. **Save** — Click **💾 Save Config & Hide API**. All current settings are saved under that name, and your `api_key` is hidden as `********` for security.
4. **Switch presets** — Pick any saved preset from the **config_select** dropdown. All fields are filled in automatically (no separate "Load" button needed).
5. **Delete** — Select a preset in the dropdown, then click **🗑 Delete**. The built-in "Default" preset cannot be deleted.
6. **Refresh list** — Click **🔄 Refresh Config List** to reload the preset dropdown at any time.

### Tips

- **"Default"** is always available as a fallback preset.
- After saving, your `api_key` shows as `********` but the real key is still used behind the scenes.
- Create separate presets for different LLM backends (e.g., one for Ollama, one for vLLM) and switch instantly.

---

## API Key & Environment Variables

- The `api_key` field accepts a plain key, or `ENV:var_name` to read the key from an environment variable at runtime.
- If the widget shows the masked placeholder `********`, the real key is loaded from the saved preset automatically.
- As a last resort, the node falls back to the `api_key` stored in the **Default** preset.

---

## Model Selection

Two dropdown selectors are provided:

- **model_select** — Pick a vision model (used when an image/video/audio is connected). After picking, the dropdown resets to the placeholder.
- **model_NoVision_select** — Pick a text-only model (used when no media is connected). Resets after picking too.

You can also type model names directly into the **model** / **model_NoVision** text fields. Click **🔄 Refresh Model List** to re-fetch available models from your API server.

> When no image/video/audio input is connected, the node automatically uses **model_NoVision**. If that model fails, it falls back to **model**.

---

## Multimodal Inputs (Images / Videos / Audio)

The node supports multiple reference images, videos, and audio via autogrow inputs:

| Input | Description | Max count |
|-------|-------------|-----------|
| **images** | Reference images (`image_0`, `image_1`, …), converted to base64 PNG | 0–32 |
| **videos** | Reference videos (`video_0`, …); frames are sampled and sent as images | 0–32 |
| **video_audios** | Soundtrack of the same-numbered reference video (`video_audio_0`, …) | 0–32 |
| **audios** | Standalone reference audio (`audio_0`, …) | 0–32 |

> The inputs follow the same pattern as MiniMax H3 Reference to Video: connect `image_0` to reveal `image_1`, and so on.

### ⚠️ Input port numbering (0-based) vs. prompt numbering (1-based)

**Input ports** are numbered starting from **0** (`image_0`, `image_1`, `video_0`, …), but the **prompt labels** sent to the LLM start from **1** (`image_1`, `image_2`, `video_1`, …). The two differ by **1** — do not confuse them.

| Input port (0-based) | Prompt label (1-based) |
|----------------------|------------------------|
| `image_0` | `image_1` |
| `image_1` | `image_2` |
| `image_2` | `image_3` |
| `video_0` | `video_1` |
| `video_1` | `video_2` |
| `video_audio_0` | `video_audio_1` |
| `audio_0` | `audio_1` |

Video frame labels also start from 1: `video_1_frame_1`, `video_1_frame_2`, … (corresponding to frames 1 and 2 of input port `video_0`).

**Example**: Suppose you connect 3 reference images (input ports `image_0`, `image_1`, `image_2`). In your prompt you should refer to them like this:

> Compare the composition of **image_1** and **image_2**, and describe the subject in **image_3**.

Here `image_1` maps to input port `image_0`, `image_2` maps to `image_1`, and `image_3` maps to `image_2`. The node automatically annotates these 1-based labels in the media manifest sent to the model and instructs it to reference them by those numbers, so your prompt must use **1-based** numbering.

### Video sampling controls

- **video_fps** — Sampling density per reference video (default `1.0`). Assumes the source video is 24fps: keeps `video_fps` frames per 24 source frames (`n = total * video_fps/24`), then capped by `max_video_frames`.
- **max_video_frames** — Maximum number of frames sent per video to avoid exceeding the context length (default `-1`). Set to `-1` or `0` to disable the cap and send all sampled frames.

### Audio controls

- **enable_audio** — Encode and send audio references to the API. Only enable if the model supports audio input. Audio is converted to base64 WAV.

---

## Streaming Text Display

The node shows the generated text in real time on a floating panel to the right of the node. As chunks arrive over WebSocket, the panel updates live while the model is still generating. The panel is a DOM overlay that follows the node when it is moved or the canvas is zoomed/panned, and it never overlaps the node's widgets.

The panel supports:

- **Collapse / Expand** (`▼` / `▶`) — hide or show the panel.
- **Show / Hide Reasoning** (`🧠` / `🚫`) — toggle the reasoning block.
- **Lock / Unlock Result** (`🔒` / `🔓`) — lock the current output so it is saved into the workflow and reused on the next run without calling the LLM again (see below).
- **Clear** (`✕`) — clear the displayed text. Disabled while the result is locked (unlock first).
- **Copy** (`⧉`) — copy the displayed text to the clipboard.
- **Auto-scroll** — the panel stays scrolled to the bottom while streaming; scroll manually to pause auto-scroll.

---

## Lock Result

When you finish a generation, you can **lock** the result so it is stored inside the workflow itself. This is useful when you want to save or share a workflow: other users (or a later re-run) will use the locked output directly and **skip the LLM service call entirely**.

### How to use

1. Run the node and wait for the generation to finish.
2. Click the **🔒 Lock** button on the Streaming Text panel's title bar. The current output (and reasoning, if shown) is saved into the workflow.
3. Save the workflow as usual — the locked result is embedded in the workflow JSON.
4. When the workflow is re-run (by you or anyone who loads the shared file), the node returns the locked text/reasoning directly without contacting the LLM server. Downstream nodes consume the locked result as normal.
5. To generate fresh output again, click **🔓 Unlock** and re-run.

### Notes

- Hovering over the lock button shows a tooltip explaining its function.
- While locked, the **Clear** button is disabled so the locked result cannot be accidentally wiped; unlock first to clear.
- Locking an empty result is allowed (it simply locks an empty output).
- Unlocking changes the node's inputs, which invalidates ComfyUI's cache and forces the node to re-run the LLM on the next execution.

### Auto-lock

The **auto_lock** toggle (a boolean button on the node, default **off**) automatically locks the result as soon as a generation **completes successfully**. When enabled, you no longer need to click the 🔒 button manually — the panel locks itself, persists the output into the workflow, and skips the LLM call on the next run.

- Auto-lock only triggers on a **successful** completion. If you **Stop** a generation (incomplete result), it is **not** auto-locked.
- If the result is already locked, auto-lock does nothing.
- The `auto_lock` setting is saved with your config presets, so it persists across nodes and workflows.

#### Metadata persistence

When `auto_lock` is enabled, the locked result is written not only into the hidden widgets on the frontend canvas, but also into **two places** during the backend execution phase (before `execute()` returns):

1. **The execution prompt** (`cls.hidden.prompt`, the same mutable reference returned by `dynprompt.get_original_prompt()`) — this node's `use_locked` / `locked_text` / `locked_reasoning` values.
2. **The frontend canvas workflow** (`cls.hidden.extra_pnginfo["workflow"]`) — this node's `widgets_values` / `widgets_values_named` values.

This means: when the LLM-generated text is consumed by downstream nodes (e.g. text-to-image / text-to-video) that embed the workflow JSON into the **metadata** of the generated image / video, both the embedded `prompt` and `workflow` will **include the LLM's locked generated text**.

- **Re-running the workflow** reads the `prompt`, so the LLM node returns the locked text directly without calling the LLM service again.
- **Dragging the image / video back into ComfyUI** loads the `workflow`, so the Streaming Text panel correctly shows the **locked state** (🔒) and the locked text.

> Because ComfyUI keeps `prompt` (backend execution) and `workflow` (frontend canvas) as two independent representations, and the frontend prefers `workflow` when loading a dragged-in file, both must be updated to guarantee correct locked-state display on both the "re-run" and "drag-in reload" paths.

---

## Thinking / Reasoning Mode

Enable **thinking** to separate the model's reasoning chain from its final answer. Uses custom tags (`<think>` / `</think>` by default). Reasoning goes to the `reasoning` output, the answer to the `text` output.

- **thinking** — Enable/disable thinking mode.
- **think_start_tag** — Opening tag to mark the start of thinking content (default `<think>`).
- **think_end_tag** — Closing tag to mark the end of thinking content (default `</think>`).

---

## Other Parameters Quick Reference

| Parameter | What It Does | When to Enable |
|-----------|-------------|----------------|
| **cache_prompt** | Tells the server to cache prompts for faster repeated responses | Server supports caching (e.g., vLLM) |
| **auto_lock** | Automatically locks the result once a generation completes successfully | You want to persist output without clicking 🔒 manually |
| **clean_comfy_vram_before_gen** | Frees ComfyUI GPU memory before sending the LLM request | Limited VRAM |
| **unload_after_gen** | Sends an unload command to the server after generation | Using vLLM, Ollama, LocalAI, etc. |
| **unload_endpoint** | API endpoint path used for the general unload request | Custom server unload path |
| **llama_cpp_unload** | Unloads via llama.cpp-specific endpoint | Using a llama.cpp server |
| **llama_endpoint** | llama.cpp unload API endpoint path | Using a llama.cpp server |
| **context_length** | Context window size (`num_ctx` / `n_ctx`); `-1`/`0` uses server default | Control memory usage / context size |
| **video_fps** | Sampling density per reference video; assumes 24fps source, keeps `video_fps` frames per 24 source frames (`n = total * video_fps/24`), capped by `max_video_frames` | Using video inputs |
| **max_video_frames** | Max frames sent per video (avoids exceeding context length); `-1`/`0` disables the cap and sends all sampled frames | Using video inputs |
| **enable_audio** | Encode and send audio references to the API | Model supports audio input |
| **temperature** | Randomness: higher is more creative, lower is more stable (default `0.7`) | Control output style |
| **top_k** | Pick next word from top K candidates (default `40`) | Control diversity |
| **seed** | Random seed for reproducibility; `-1` for random (default `-1`) | Reproducible output |
| **timeout** | Timeout in seconds for the LLM generation request (default `180`) | Long-running tasks |

---

## Stop Generation

Click the **⏹ Stop Generation** button to interrupt the currently running request. The node uses streaming (SSE) generation; clicking Stop closes the active connection, which makes the server stop generating and the node return the text accumulated so far.

---

> Back to [Wiki Home](Home)
