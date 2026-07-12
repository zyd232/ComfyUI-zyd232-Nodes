# ComfyUI zyd232 Nodes

## Node Description
### 1. LLM Text Generator
This node provides a flexible LLM API interface for text generation, supporting OpenAI-compatible endpoints. Key features include:
- **API Configuration**: Configurable `base_url` and `api_key` for connecting to any OpenAI-compatible LLM service (such as Ollama, vLLM, llama.cpp, LocalAI, etc.)
- **Model Selection**: Dynamically fetches and caches available models from the connected API server
- **Vision Support**: Optional image input for multimodal LLMs (like LLaVA, GPT-4o, etc.), automatically converting images to base64 format
- **Thinking/Reasoning Mode**: Supports extracting reasoning chains from model responses using custom start/end tags (e.g., `<think>` / `</think>`), with separate outputs for reasoning and final answer
- **Dual Output**: Provides two output ports — `text` (the final answer) and `reasoning` (the extracted reasoning chain)
- **Generation Parameters**: Configurable `temperature`, `top_k`, `seed`, and `context_length` for controlling generation behavior
- **Model Unloading**: Two independent automatic model unloading mechanisms to free up GPU memory after generation (see details below)
- **VRAM Cleanup Before Generation**: Automatic ComfyUI VRAM clearance before sending the LLM request to ensure enough GPU memory is available (see details below)

#### Clean ComfyUI VRAM Before Generation

The **`clean_comfy_vram_before_gen`** option (enabled by default) automatically frees up GPU memory before sending the LLM request. This helps prevent out-of-memory errors when your GPU is already loaded with other ComfyUI models.

**Quick Guide:**
- Keep enabled (default) if you have limited VRAM
- Disable only if you want to keep your ComfyUI models loaded in VRAM for faster image generation

#### Auto-Unload Model After Generation (Free GPU Memory)

LLM models take up a lot of VRAM while loaded. These two options let the node **automatically unload the model from GPU memory** after text generation is done, freeing resources for the rest of your ComfyUI workflow.

| Option | When to Use | What It Does |
|--------|-------------|--------------|
| **`unload_after_gen`** | vLLM, Ollama, LocalAI, etc. | Sends an unload command to the server after generation. Works with most OpenAI-compatible services. Automatically tries POST if DELETE is not supported. |
| **`llama_cpp_unload`** | llama.cpp multi-model server | Uses llama.cpp's dedicated unload endpoint. If the standard endpoint is unavailable, automatically falls back to clearing the model slot to free memory. |

**Quick Guide:**
- Using **vLLM / Ollama**? → Turn on `unload_after_gen`
- Using **llama.cpp**? → Turn on `llama_cpp_unload`
- Both can be enabled at the same time — the node will try both

> **Advanced**: If your server uses a custom unload path, you can set `unload_endpoint` and `llama_endpoint` to the path suffix (e.g., `/my/custom/unload`).

### 2. Images Pixels Compare
This node is used to compare whether two input images are exactly the same (pixel-level comparison) and outputs a boolean value.

### 3. Save Preview Images
This node saves input images with various options including format (PNG/JPG), quality, metadata, and custom paths. It can also save the workflow as JSON and generate preview images. Preview images are controlled by the same options. The save function can be disabled to use the node solely for preview purposes.

### 4. Mask Batch Blend
This node blends multiple masks together using different operations (add, max, average). It can handle masks with different dimensions and batch sizes. The node supports:
- **Add operation**: Sums all masks together (overlay effect)
- **Max operation**: Takes the maximum value at each pixel across all masks
- **Average operation**: Computes the average of all masks
