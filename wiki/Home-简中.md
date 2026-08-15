<div align="center">

# ComfyUI zyd232 Nodes — Wiki

[![English](https://img.shields.io/badge/English-Wiki-blue)](Home)

</div>

欢迎来到 **ComfyUI zyd232 Nodes** 的 Wiki！这里以**节点为单位**介绍每个节点的具体功能、输入输出、参数说明与使用技巧。

> 本 Wiki 由项目内 [`wiki/`](https://github.com/zyd232/comfyui-zyd232-nodes/tree/main/wiki) 目录自动同步生成，可通过 GitHub Actions 保持与代码同步更新。

---

## 📚 节点索引

| 节点名称 | 类别 | 功能简介 | 文档 |
|---------|------|---------|------|
| **LLM Text Generator** | `zyd232 Nodes/LLM` | 连接任意 OpenAI 兼容 LLM 服务进行文本生成，支持多图/视频/音频、流式显示、配置预设、结果锁定 | [📄 查看文档](LLM-Text-Generator-简中) |
| **Images Pixels Compare** | `zyd232 Nodes` | 像素级比较两张图片是否完全相同，输出布尔值 | [📄 查看文档](Images-Pixels-Compare-简中) |
| **Save Preview Images** | `zyd232 Nodes` | 保存图片（PNG/JPG），支持质量、元数据、自定义路径、工作流 JSON 与预览 | [📄 查看文档](Save-Preview-Images-简中) |
| **Mask Batch Blend** | `zyd232 Nodes` | 将多个 Mask 通过 add / max / average 操作合并为一个 | [📄 查看文档](Mask-Batch-Blend-简中) |

---

## 🚀 快速开始

1. 将本插件目录放入 `ComfyUI/custom_nodes/` 下。
2. 重启 ComfyUI，节点会出现在 **zyd232 Nodes** 分类中。
3. 在节点搜索框中输入节点名称即可找到对应节点。

---

## 🧩 节点通用信息

所有节点均注册在 `zyd232 Nodes` 分类下，其中 LLM 节点位于子分类 `zyd232 Nodes/LLM`。

| 节点 | 类名（`NODE_CLASS_MAPPINGS` 键） |
|------|--------------------------------|
| LLM Text Generator | `zyd232 LLMGenerator` |
| Images Pixels Compare | `zyd232 ImagesPixelsCompare` |
| Save Preview Images | `zyd232_SavePreviewImages` |
| Mask Batch Blend | `zyd232 MaskBatchBlend` |

---

## 📖 各节点文档

- [LLM Text Generator](LLM-Text-Generator-简中)
- [Images Pixels Compare](Images-Pixels-Compare-简中)
- [Save Preview Images](Save-Preview-Images-简中)
- [Mask Batch Blend](Mask-Batch-Blend-简中)

---

## 🌐 语言

- [English](Home)
- [简体中文](Home-简中)
