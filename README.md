<div align="center">

# ComfyUI zyd232 Nodes

[![中文](https://img.shields.io/badge/简体中文-README-blue)](README.zh-CN.md)

</div>

A collection of custom nodes for [ComfyUI](https://github.com/comfyanonymous/ComfyUI), including LLM text generation, image pixel comparison, image save/preview, and mask batch blending.

> 📖 **Full documentation is available in the [Wiki](wiki/Home.md)** — each node is documented individually with its features, inputs/outputs, and usage tips.

---

## 📦 Installation

1. Place this plugin directory under `ComfyUI/custom_nodes/`.
2. Restart ComfyUI.
3. The nodes will appear under the **zyd232 Nodes** category.

---

## 🧩 Node Index

| Node | Category | Description | Docs |
|------|----------|-------------|------|
| **LLM Text Generator** | `zyd232 Nodes/LLM` | Connect to any OpenAI-compatible LLM service for text generation. Supports multiple images/videos/audio, streaming display, config presets, and result locking. | [📄 Docs](wiki/LLM-Text-Generator.md) |
| **Images Pixels Compare** | `zyd232 Nodes` | Compare two images at the pixel level to check if they are identical; outputs a boolean. | [📄 Docs](wiki/Images-Pixels-Compare.md) |
| **Save Preview Images** | `zyd232 Nodes` | Save images (PNG/JPG) with quality, metadata, custom path, workflow JSON, and preview options. | [📄 Docs](wiki/Save-Preview-Images.md) |
| **Mask Batch Blend** | `zyd232 Nodes` | Blend multiple masks into one using add / max / average operations. | [📄 Docs](wiki/Mask-Batch-Blend.md) |

---

## 🚀 Quick Start

Type a node name in the ComfyUI node search box to find it. For detailed usage of each node, click the docs link above or browse the [Wiki home](wiki/Home.md).

---

## 📄 License

This project is released under the [LICENSE](LICENSE).
