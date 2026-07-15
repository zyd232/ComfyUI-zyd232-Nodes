# ComfyUI zyd232 Nodes

## Node Description
### 1. LLM Text Generator
This node connects to any OpenAI-compatible LLM service (Ollama, vLLM, llama.cpp, LocalAI, etc.) for text generation inside ComfyUI workflows.

#### Config Preset System — Save and Switch Settings

Save all your settings (API URL, key, model, prompts, parameters) as named presets, and switch between them with one click.

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

#### Model Selection

Two dropdown selectors are provided:

- **model_select** — Pick a vision model (used when an image is connected). After picking, the dropdown resets to the placeholder.
- **model_NoVision_select** — Pick a text-only model (used when no image is connected). Resets after picking too.

You can also type model names directly into the **model** / **model_NoVision** text fields. Click **🔄 Refresh Model List** to re-fetch available models from your API server.

> When no image input is connected, the node automatically uses **model_NoVision**. If that model fails, it falls back to **model**.

#### Key Features

- **Vision Support** — Connect an image input for multimodal LLMs (LLaVA, GPT-4o, etc.). Images are automatically converted to base64 for the API.
- **Thinking / Reasoning Mode** — Enable **thinking** to separate the model's reasoning chain from its final answer. Uses custom tags (`<think>` / `</think>` by default). Reasoning goes to the `reasoning` output, the answer to the `text` output.
- **Dual Output** — `text` (final answer) and `reasoning` (extracted thinking process).

#### Other Options Quick Reference

| Option | What It Does | When to Enable |
|--------|-------------|----------------|
| **cache_prompt** | Tells the server to cache prompts for faster repeated responses | Server supports caching (e.g., vLLM) |
| **clean_comfy_vram_before_gen** | Frees ComfyUI GPU memory before sending the LLM request | Limited VRAM |
| **unload_after_gen** | Sends an unload command to the server after generation | Using vLLM, Ollama, LocalAI, etc. |
| **llama_cpp_unload** | Unloads via llama.cpp-specific endpoint | Using a llama.cpp server |

### 2. Images Pixels Compare
This node is used to compare whether two input images are exactly the same (pixel-level comparison) and outputs a boolean value.

### 3. Save Preview Images
This node saves input images with various options including format (PNG/JPG), quality, metadata, and custom paths. It can also save the workflow as JSON and generate preview images. Preview images are controlled by the same options. The save function can be disabled to use the node solely for preview purposes.

### 4. Mask Batch Blend
This node blends multiple masks together using different operations (add, max, average). It can handle masks with different dimensions and batch sizes. The node supports:
- **Add operation**: Sums all masks together (overlay effect)
- **Max operation**: Takes the maximum value at each pixel across all masks
- **Average operation**: Computes the average of all masks
