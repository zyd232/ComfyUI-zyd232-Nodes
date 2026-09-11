<div align="center">

# ComfyUI zyd232 Nodes — Wiki

[![简体中文](https://img.shields.io/badge/简体中文-Wiki-blue)](Home-简中)

</div>

Welcome to the **ComfyUI zyd232 Nodes** Wiki! Here each node is documented individually with its features, inputs/outputs, parameters, and usage tips.

> This Wiki is auto-synced from the [`wiki/`](https://github.com/zyd232/comfyui-zyd232-nodes/tree/main/wiki) directory in the repository via GitHub Actions.

---

## 📚 Node Index

| Node | Category | Description | Docs |
|------|----------|-------------|------|
| **LLM Text Generator** | `zyd232 Nodes/LLM` | Connect to any OpenAI-compatible LLM service for text generation. Supports multiple images/videos/audio, streaming display, config presets, and result locking. | [📄 Docs](LLM-Text-Generator) |
| **LLM Unload** | `zyd232 Nodes/LLM` | Send an unload signal to the LLM Server to release the model from VRAM. All parameters come from the config preset saved by the LLM Text Generator node. Supports selecting a specific model to unload. | [📄 Docs](LLM-Unload) |
| **Images Pixels Compare** | `zyd232 Nodes` | Compare two images at the pixel level to check if they are identical; outputs a boolean. | [📄 Docs](Images-Pixels-Compare) |
| **Save Preview Images** | `zyd232 Nodes` | Save images (PNG/JPG) with quality, metadata, custom path, workflow JSON, and preview options. | [📄 Docs](Save-Preview-Images) |
| **Mask Batch Blend** | `zyd232 Nodes` | Blend multiple masks into one using add / max / average operations. | [📄 Docs](Mask-Batch-Blend) |
| **Merge LoRA Stacks** | `zyd232 Nodes` | Merge multiple lora_stack inputs into a single lora_stack output. The left-side inputs are dynamic (Autogrow) and can be added freely. | [📄 Docs](Merge-LoRA-Stacks) |
| **Join Videos** | `zyd232 Nodes` | Join multiple videos into one, in input order. Accepts file paths and VIDEO inputs through two dynamic (Autogrow) groups; outputs VHS_FILENAMES and VIDEO, joining losslessly when the segments already match the target format. | [📄 Docs](Join-Videos) |

---

## 🚀 Quick Start

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/zyd232/ComfyUI-zyd232-Nodes.git
```

Restart ComfyUI. The nodes will appear under the **zyd232 Nodes** category.

Then type a node name in the node search box to find it.

---

## 🧩 Node Reference

All nodes are registered under the `zyd232 Nodes` category; the LLM node is in the `zyd232 Nodes/LLM` subcategory.

| Node | Class name (`NODE_CLASS_MAPPINGS` key) |
|------|----------------------------------------|
| LLM Text Generator | `zyd232 LLMGenerator` |
| LLM Unload | `zyd232 LLMUnload` |
| Images Pixels Compare | `zyd232 ImagesPixelsCompare` |
| Save Preview Images | `zyd232_SavePreviewImages` |
| Mask Batch Blend | `zyd232 MaskBatchBlend` |
| Merge LoRA Stacks | `zyd232 MergeLoraStacks` |
| Join Videos | `zyd232_JoinVideos` |

---

## 📖 Node Documentation

- [LLM Text Generator](LLM-Text-Generator)
- [LLM Unload](LLM-Unload)
- [Images Pixels Compare](Images-Pixels-Compare)
- [Save Preview Images](Save-Preview-Images)
- [Mask Batch Blend](Mask-Batch-Blend)
- [Merge LoRA Stacks](Merge-LoRA-Stacks)
- [Join Videos](Join-Videos)

---

## 🌐 Languages

- [English](Home)
- [简体中文](Home-简中)
