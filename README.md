# ComfyUI zyd232 Nodes

## Node Description
### 1. LLM Text Generator
This node connects to any OpenAI-compatible LLM service (Ollama, vLLM, llama.cpp, LocalAI, etc.) for text generation inside ComfyUI workflows. It supports multiple reference images, videos and audio, and can generate text from any OpenAI-compatible server.

#### Config Preset System — Save and Switch Settings

Save all your settings (API URL, key, model, prompts, parameters) as named presets, and switch between them with one click. Presets are stored in a single JSON file (`presets/llm_text_generator_presets.json`).

**How to use:**

1. **Configure the node** — Fill in `base_url`, `api_key`, choose a model, write your prompts, and set other parameters.
2. **Name your preset** — Type a name into the **config_name** field (e.g., "My Ollama", "GPT-4o"). Invalid file-system characters are automatically removed.
3. **Save** — Click **💾 Save Config & Hide API**. All current settings are saved under that name, and your `api_key` is hidden as `********` for security.
4. **Switch presets** — Pick any saved preset from the **config_select** dropdown. All fields are filled in automatically (no separate "Load" button needed).
5. **Delete** — Select a preset in the dropdown, then click **🗑 Delete**. The built-in "Default" preset cannot be deleted.
6. **Refresh list** — Click **🔄 Refresh Config List** to reload the preset dropdown at any time.

**Tips:**
- **"Default"** is always available as a fallback preset.
- After saving, your `api_key` shows as `********` but the real key is still used behind the scenes.
- Create separate presets for different LLM backends (e.g., one for Ollama, one for vLLM) and switch instantly.

#### API Key & Environment Variables

- The `api_key` field accepts a plain key, or `ENV:var_name` to read the key from an environment variable at runtime.
- If the widget shows the masked placeholder `********`, the real key is loaded from the saved preset automatically.
- As a last resort, the node falls back to the `api_key` stored in the **Default** preset.

#### Model Selection

Two dropdown selectors are provided:

- **model_select** — Pick a vision model (used when an image/video/audio is connected). After picking, the dropdown resets to the placeholder.
- **model_NoVision_select** — Pick a text-only model (used when no media is connected). Resets after picking too.

You can also type model names directly into the **model** / **model_NoVision** text fields. Click **🔄 Refresh Model List** to re-fetch available models from your API server.

> When no image/video/audio input is connected, the node automatically uses **model_NoVision**. If that model fails, it falls back to **model**.

#### Multimodal Inputs (Images, Videos, Audio)

The node supports multiple reference images, videos and audio via autogrow inputs:

- **images** — Connect one or more reference images (`image_0`, `image_1`, ... up to `image_9`). Images are converted to base64 PNG and sent to the API.
- **videos** — Connect one or more reference videos (`video_0`, `video_1`, ... up to `video_3`). Frames are sampled and sent as images.
- **video_audios** — Connect the soundtrack of the same-numbered reference video (`video_audio_0`, ... up to `video_audio_3`).
- **audios** — Connect standalone reference audio (`audio_0`, ... up to `audio_5`).

> The inputs follow the same pattern as MiniMax H3 Reference to Video: connect `image_0` to reveal `image_1`, and so on.

**Video sampling controls:**
- **video_fps** — Frames per second sampled from each reference video (default `1.0`).
- **max_video_frames** — Maximum number of frames sent per video to avoid exceeding the context length (default `16`).

**Audio controls:**
- **enable_audio** — Encode and send audio references to the API. Only enable if the model supports audio input. Audio is converted to base64 WAV.

#### Key Features

- **Vision Support** — Connect image inputs for multimodal LLMs (LLaVA, GPT-4o, etc.). Images are automatically converted to base64 for the API.
- **Video Support** — Connect reference videos; frames are sampled and sent as images for video understanding.
- **Audio Support** — Connect reference audio (standalone or video soundtracks) and send them as WAV to audio-capable models.
- **Thinking / Reasoning Mode** — Enable **thinking** to separate the model's reasoning chain from its final answer. Uses custom tags (`<think>` / `</think>` by default). Reasoning goes to the `reasoning` output, the answer to the `text` output.
- **Dual Output** — `text` (final answer) and `reasoning` (extracted thinking process).
- **Stop Generation** — Click the **⏹ Stop Generation** button to interrupt the currently running request. The node uses streaming (SSE) generation; clicking Stop closes the active connection, which makes the server stop generating and the node return the text accumulated so far.
- **Streaming Text Display** — The node shows the generated text in real time on a floating panel to the right of the node. As chunks arrive over WebSocket, the panel updates live while the model is still generating. The panel is a DOM overlay that follows the node when it is moved or the canvas is zoomed/panned, and it never overlaps the node's widgets. The panel supports:
  - **Collapse / Expand** (`▼` / `▶`) — hide or show the panel.
  - **Show / Hide Reasoning** (`🧠` / `🚫`) — toggle the reasoning block.
  - **Lock / Unlock Result** (`🔒` / `🔓`) — lock the current output so it is saved into the workflow and reused on the next run without calling the LLM again (see below).
  - **Clear** (`✕`) — clear the displayed text. Disabled while the result is locked (unlock first).
  - **Copy** (`⧉`) — copy the displayed text to the clipboard.
  - **Auto-scroll** — the panel stays scrolled to the bottom while streaming; scroll manually to pause auto-scroll.

#### Lock Result — Save & Reuse Output Without Re-running the LLM

When you finish a generation, you can **lock** the result so it is stored inside the workflow itself. This is useful when you want to save or share a workflow: other users (or a later re-run) will use the locked output directly and **skip the LLM service call entirely**.

**How to use:**
1. Run the node and wait for the generation to finish.
2. Click the **🔒 Lock** button on the Streaming Text panel's title bar. The current output (and reasoning, if shown) is saved into the workflow.
3. Save the workflow as usual — the locked result is embedded in the workflow JSON.
4. When the workflow is re-run (by you or anyone who loads the shared file), the node returns the locked text/reasoning directly without contacting the LLM server. Downstream nodes consume the locked result as normal.
5. To generate fresh output again, click **🔓 Unlock** and re-run.

**Notes:**
- Hovering over the lock button shows a tooltip explaining its function.
- While locked, the **Clear** button is disabled so the locked result cannot be accidentally wiped; unlock first to clear.
- Locking an empty result is allowed (it simply locks an empty output).
- Unlocking changes the node's inputs, which invalidates ComfyUI's cache and forces the node to re-run the LLM on the next execution.
- **Context Length Control** — Set **context_length** to control the context window (`num_ctx` / `n_ctx`). Set to `-1` or `0` to let the server use its default.

#### Other Options Quick Reference

| Option | What It Does | When to Enable |
|--------|-------------|----------------|
| **cache_prompt** | Tells the server to cache prompts for faster repeated responses | Server supports caching (e.g., vLLM) |
| **clean_comfy_vram_before_gen** | Frees ComfyUI GPU memory before sending the LLM request | Limited VRAM |
| **unload_after_gen** | Sends an unload command to the server after generation | Using vLLM, Ollama, LocalAI, etc. |
| **unload_endpoint** | API endpoint path used for the general unload request | Custom server unload path |
| **llama_cpp_unload** | Unloads via llama.cpp-specific endpoint | Using a llama.cpp server |
| **llama_endpoint** | llama.cpp unload API endpoint path | Using a llama.cpp server |
| **context_length** | Context window size (`num_ctx` / `n_ctx`); `-1`/`0` uses server default | Control memory usage / context size |
| **video_fps** | Frames per second sampled from each reference video | Using video inputs |
| **max_video_frames** | Max frames sent per video (avoids exceeding context length) | Using video inputs |
| **enable_audio** | Encode and send audio references to the API | Model supports audio input |

### 2. Images Pixels Compare
This node is used to compare whether two input images are exactly the same (pixel-level comparison) and outputs a boolean value.

### 3. Save Preview Images
This node saves input images with various options including format (PNG/JPG), quality, metadata, and custom paths. It can also save the workflow as JSON and generate preview images. Preview images are controlled by the same options. The save function can be disabled to use the node solely for preview purposes.

### 4. Mask Batch Blend
This node blends multiple masks together using different operations (add, max, average). It can handle masks with different dimensions and batch sizes. The node supports:
- **Add operation**: Sums all masks together (overlay effect)
- **Max operation**: Takes the maximum value at each pixel across all masks
- **Average operation**: Computes the average of all masks
