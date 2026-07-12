# ComfyUI zyd232 Nodes

## Node Description
### 1. LLM Generator
This node provides a flexible LLM API interface for text generation, supporting OpenAI-compatible endpoints. Key features include:
- **API Configuration**: Configurable `base_url` and `api_key` for connecting to any OpenAI-compatible LLM service (such as Ollama, vLLM, LocalAI, etc.)
- **Model Selection**: Dynamically fetches and caches available models from the connected API server
- **Vision Support**: Optional image input for multimodal LLMs (like LLaVA, GPT-4o, etc.), automatically converting images to base64 format
- **Thinking/Reasoning Mode**: Supports extracting reasoning chains from model responses using custom start/end tags (e.g., `<think>` / `</think>`), with separate outputs for reasoning and final answer
- **Dual Output**: Provides two output ports — `text` (the final answer) and `reasoning` (the extracted reasoning chain)
- **Generation Parameters**: Configurable `temperature`, `top_k`, `seed`, and `context_length` for controlling generation behavior
- **Model Unloading**: Optional automatic model unloading after generation to free up GPU memory

### 2. Images Pixels Compare
This node is used to compare whether two input images are exactly the same (pixel-level comparison) and outputs a boolean value.

### 3. Save Preview Images
This node saves input images with various options including format (PNG/JPG), quality, metadata, and custom paths. It can also save the workflow as JSON and generate preview images. Preview images are controlled by the same options. The save function can be disabled to use the node solely for preview purposes.

### 4. Mask Batch Blend
This node blends multiple masks together using different operations (add, max, average). It can handle masks with different dimensions and batch sizes. The node supports:
- **Add operation**: Sums all masks together (overlay effect)
- **Max operation**: Takes the maximum value at each pixel across all masks
- **Average operation**: Computes the average of all masks
