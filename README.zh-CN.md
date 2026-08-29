<div align="center">

# ComfyUI zyd232 Nodes

[![English](https://img.shields.io/badge/English-README-blue)](README.md)

</div>

一组用于 [ComfyUI](https://github.com/comfyanonymous/ComfyUI) 的自定义节点，包含 LLM 文本生成、图片像素对比、图片保存预览与 Mask 批量混合等功能。

> 📖 **完整文档请浏览 [Wiki](https://github.com/zyd232/ComfyUI-zyd232-Nodes/wiki/Home-简中)** — 以节点为单位详细介绍每个节点的功能、输入输出与使用技巧。

---

## 📦 安装

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/zyd232/ComfyUI-zyd232-Nodes.git
```

重启 ComfyUI，节点会出现在 **zyd232 Nodes** 分类中。

---

## 🧩 节点索引

| 节点名称 | 类别 | 功能简介 | 文档 |
|---------|------|---------|------|
| **LLM Text Generator** | `zyd232 Nodes/LLM` | 连接任意 OpenAI 兼容 LLM 服务进行文本生成，支持多图/视频/音频、流式显示、配置预设、结果锁定 | [📄 文档](https://github.com/zyd232/ComfyUI-zyd232-Nodes/wiki/LLM-Text-Generator-简中) |
| **LLM Unload** | `zyd232 Nodes/LLM` | 向 LLM Server 发送 unload 信号，从显存卸载模型。所有参数均来自 LLM Text Generator 所保存的 config preset。支持选择要卸载的特定模型 | |
| **Images Pixels Compare** | `zyd232 Nodes` | 像素级比较两张图片是否完全相同，输出布尔值 | [📄 文档](https://github.com/zyd232/ComfyUI-zyd232-Nodes/wiki/Images-Pixels-Compare-简中) |
| **Save Preview Images** | `zyd232 Nodes` | 保存图片（PNG/JPG），支持质量、元数据、自定义路径、工作流 JSON 与预览 | [📄 文档](https://github.com/zyd232/ComfyUI-zyd232-Nodes/wiki/Save-Preview-Images-简中) |
| **Mask Batch Blend** | `zyd232 Nodes` | 将多个 Mask 通过 add / max / average 操作合并为一个 | [📄 文档](https://github.com/zyd232/ComfyUI-zyd232-Nodes/wiki/Mask-Batch-Blend-简中) |
| **Merge LoRA Stacks** | `zyd232 Nodes` | 将多个 lora_stack 输入合并为一个 lora_stack 输出，左侧输入可动态增加 | [📄 文档](https://github.com/zyd232/ComfyUI-zyd232-Nodes/wiki/Merge-LoRA-Stacks-简中) |

---

## 🚀 快速开始

在 ComfyUI 节点搜索框中输入节点名称即可找到对应节点。每个节点的详细用法请点击上方文档链接，或浏览 [Wiki 首页](https://github.com/zyd232/ComfyUI-zyd232-Nodes/wiki/Home-简中)。

---

## 📄 许可证

本项目基于 [LICENSE](LICENSE) 许可发布。
