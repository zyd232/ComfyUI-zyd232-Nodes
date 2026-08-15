<div align="center">

# ComfyUI zyd232 Nodes — Wiki

[![简体中文](https://img.shields.io/badge/简体中文-Wiki-blue)](zh-CN/Home)

</div>

Welcome to the **ComfyUI zyd232 Nodes** Wiki! Here each node is documented individually with its features, inputs/outputs, parameters, and usage tips.

> This Wiki is auto-synced from the [`wiki/`](https://github.com/zyd232/comfyui-zyd232-nodes/tree/main/wiki) directory in the repository via GitHub Actions.

---

## 📚 Node Index

| Node | Category | Description | Docs |
|------|----------|-------------|------|
| **LLM Text Generator** | `zyd232 Nodes/LLM` | Connect to any OpenAI-compatible LLM service for text generation. Supports multiple images/videos/audio, streaming display, config presets, and result locking. | [📄 Docs](LLM-Text-Generator) |
| **Images Pixels Compare** | `zyd232 Nodes` | Compare two images at the pixel level to check if they are identical; outputs a boolean. | [📄 Docs](Images-Pixels-Compare) |
| **Save Preview Images** | `zyd232 Nodes` | Save images (PNG/JPG) with quality, metadata, custom path, workflow JSON, and preview options. | [📄 Docs](Save-Preview-Images) |
| **Mask Batch Blend** | `zyd232 Nodes` | Blend multiple masks into one using add / max / average operations. | [📄 Docs](Mask-Batch-Blend) |

---

## 🚀 Quick Start

1. Place this plugin directory under `ComfyUI/custom_nodes/`.
2. Restart ComfyUI. The nodes will appear under the **zyd232 Nodes** category.
3. Type a node name in the node search box to find it.

---

## 🧩 Node Reference

All nodes are registered under the `zyd232 Nodes` category; the LLM node is in the `zyd232 Nodes/LLM` subcategory.

| Node | Class name (`NODE_CLASS_MAPPINGS` key) |
|------|----------------------------------------|
| LLM Text Generator | `zyd232 LLMGenerator` |
| Images Pixels Compare | `zyd232 ImagesPixelsCompare` |
| Save Preview Images | `zyd232_SavePreviewImages` |
| Mask Batch Blend | `zyd232 MaskBatchBlend` |

---

## 📖 Node Documentation

- [LLM Text Generator](LLM-Text-Generator)
- [Images Pixels Compare](Images-Pixels-Compare)
- [Save Preview Images](Save-Preview-Images)
- [Mask Batch Blend](Mask-Batch-Blend)

---

## 🌐 Languages

- [English](Home)
- [简体中文](zh-CN/Home)
