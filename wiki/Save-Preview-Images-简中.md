<div align="center">

# Save Preview Images

[![English](https://img.shields.io/badge/English-Docs-blue)](Save-Preview-Images)

</div>

> 返回 [Wiki 首页](Home-简中)

## 概述

**Save Preview Images** 节点用于保存输入图片，提供多种选项，包括格式（PNG/JPG）、质量、元数据和自定义路径。它还可以将工作流保存为 JSON 并生成预览图片。预览图片由相同选项控制。可禁用保存功能，仅将节点用于预览目的。

- **类名**：`zyd232_SavePreviewImages`
- **类别**：`zyd232 Nodes`
- **输出节点**：`OUTPUT_NODE = True`（无数据输出，仅 UI 预览）

---

## 输入

| 输入 | 类型 | 说明 |
|------|------|------|
| **images** | `IMAGE` | 待保存的图片 |
| **save_image** | `BOOLEAN` | 是否执行保存操作（默认 `true`） |
| **save_workflow_as_json** | `BOOLEAN` | 是否将工作流保存为 JSON（默认 `false`） |
| **preview** | `BOOLEAN` | 是否生成预览图片（默认 `true`） |
| **format** | `["png", "jpg"]` | 输出图片格式 |
| **quality** | `INT` | 图片质量（默认 `85`，范围 0–100） |
| **meta_data_png** | `BOOLEAN` | 是否在 PNG 中写入元数据（默认 `true`） |
| **custom_path** | `STRING` | 自定义保存路径（默认空） |
| **filename_prefix** | `STRING` | 文件名前缀（默认 `ComfyUI_`） |
| **timestamp** | `["second", "millisecond", "None"]` | 文件名时间戳模式 |

---

## 输出

无数据输出。节点通过 UI 返回预览图片列表（`type: "temp"`）。

---

## 功能说明

### 保存图片

- 支持 **PNG** 和 **JPG** 两种格式。
- **quality** 控制压缩质量：PNG 使用 `compress_level`（由 `(100 - quality) // 10` 计算），JPG 使用 `quality` 参数。
- 当 `save_image = false` 时，跳过实际保存，仅用于预览。

### 文件名与时间戳

- **filename_prefix** 支持 `%date`（`YYYY-MM-DD`）和 `%time`（`HH-MM-SS`）占位符。
- **timestamp** 决定文件名后缀：
  - `second` — 追加 `YYYY-MM-DD_HH-MM-SS`
  - `millisecond` — 追加 `YYYY-MM-DD_HH-MM-SS-fff`
  - `None` — 使用计数器（`_00001` 等）
- 若文件已存在，会自动递增计数器避免覆盖。

### 自定义路径

- **custom_path** 支持 `%date` 和 `%time` 占位符。
- 若路径不存在会自动创建。
- 留空则保存到 ComfyUI 默认输出目录。

### 元数据

- 当 `meta_data_png = true` 时，会将 `prompt` 和 `extra_pnginfo`（含工作流）写入 PNG 元数据。

### 工作流 JSON

- 当 `save_workflow_as_json = true` 时，会将工作流保存为与图片同名的 `.json` 文件。
- 若未找到工作流数据，会打印提示并跳过。

### 预览

- 当 `preview = true` 时，会生成预览图片（保存到临时目录），并在 UI 中显示。
- 预览文件名使用随机名称（`saveimage_preview_*`）或带时间戳的名称。

---

## 使用示例

- **仅预览**：设置 `save_image = false`、`preview = true`，在画布上查看结果而不落盘。
- **保存带工作流的 PNG**：设置 `format = png`、`save_workflow_as_json = true`、`meta_data_png = true`。
- **按日期归档**：设置 `custom_path = "outputs/%date"`、`filename_prefix = "img_%date"`。

---

> 返回 [Wiki 首页](Home-简中)
