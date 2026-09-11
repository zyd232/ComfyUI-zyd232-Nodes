<div align="center">

# Join Videos

[![English](https://img.shields.io/badge/English-Docs-blue)](Join-Videos)

</div>

> 返回 [Wiki 首页](Home-简中)

## 概述

**Join Videos** 节点按**输入顺序**把多段视频拼接为一段。它接受两类输入，两者都是**动态输入**（基于 node API V3 的 Autogrow），可自由增加或减少：

- **`filenames`** —— 磁盘上的视频文件（每槽一个路径，也可用逗号 / 换行分隔多个路径）
- **`videos`** —— ComfyUI 的 `VIDEO` 对象

合并顺序为先 `filenames` 组、再 `videos` 组。节点同时输出 `VHS_FILENAMES`（可供 [Video Helper Suite](https://github.com/kosinkadink/ComfyUI-VideoHelperSuite) 节点使用）与 `VIDEO`，并在节点上直接预览合成结果。

- **类名**：`zyd232_JoinVideos`
- **类别**：`zyd232 Nodes`
- **输出**：`VHS_FILENAMES`、`VIDEO`

---

## 输入

| 字段（英文） | 字段（中文） | 类型 | 说明 |
|------|------|------|------|
| **filenames** | 文件名 | `STRING`（Autogrow） | 待合并的视频文件路径。每槽一个路径，也可用逗号 / 换行分隔多个路径。槽位为动态输入，点击 `+` 增加 |
| **videos** | 视频 | `VIDEO`（Autogrow） | 待合并的 `VIDEO` 输入，排在全部 `filenames` 槽位之后。槽位为动态输入 |
| **filename_prefix** | 文件名前缀 | `STRING` | 输出文件名前缀，默认 `zyd232_merged` |
| **frame_rate** | 帧率 | `FLOAT` | 1–240，默认 `24`。重编码时使用的帧率，同时显示在预览信息中。无损流拷贝会保留各源自身的时长与帧率 |
| **format** | 格式 | `COMBO` | 输出封装 / 编码格式，见下方「输出格式」。默认 `video/h264-mp4` |
| **crf** | 压缩质量 | `INT` | -1–63，默认 `-1`。数值越小画质越好、文件越大。`-1` 表示不改动质量，可走无损流拷贝路径 |
| **save_metadata** | 保存元数据 | `BOOLEAN` | 默认 `Yes`。将提示词 / 工作流元数据写入输出容器 |
| **pingpong** | 乒乓循环 | `BOOLEAN` | 默认 `No`。在合成结果后追加一段倒放版本（正放再接倒放） |
| **loop_count** | 循环次数 | `INT` | 0–100，默认 `0`。合成视频额外重复播放的次数（`0` 表示只播放一次） |
| **save_output** | 保存输出 | `BOOLEAN` | 默认 `Yes`。保存到输出目录；关闭时输出到临时目录 |

> 两组自增加输入初始都不占用槽位。连上一个后会自动在下方再长出一个空槽。

---

## 输出

| 输出 | 类型 | 说明 |
|------|------|------|
| **filenames** | `VHS_FILENAMES` | `(save_output, [路径])`，[Video Helper Suite](https://github.com/kosinkadink/ComfyUI-VideoHelperSuite) 的标准文件名返回值，可供其他 VHS 节点使用 |
| **video** | `VIDEO` | 合成结果（ComfyUI `VIDEO` 类型），可供核心视频节点使用 |

---

## 功能说明

### 合并顺序

1. 先按槽位顺序遍历 `filenames` 组的每个槽位（`filename_0` → `filename_1` → …）
2. 再按槽位顺序遍历 `videos` 组的每个槽位（`video_0` → `video_1` → …）

单个 `filename` 槽位内，路径按逗号 / 换行切分后从左到右读取。空片段会被忽略，因此结尾多一个分隔符——或循环累加串以逗号开头——都不会出问题。

### 无损拷贝与重编码

拼接使用 **ffmpeg 的 concat demuxer**，分两种模式：

| 模式 | 触发条件 | 结果 |
|------|---------|------|
| **流拷贝**（`-c copy`） | `crf = -1`、未开启 `pingpong`、`format` 不是 `image/gif`，**且**所有源文件的扩展名都与目标封装一致 | 无损且快速，完全不重新编码 |
| **重编码** | 其余任何情况 | 按所选格式与 `crf` 重新编码 |

若尝试流拷贝但失败（例如各分段的编码参数已经不一致），节点会打印告警并自动改为重编码重试一次。

### 乒乓循环

`pingpong` 会先合并所有源，再把合成结果倒放编码一份（`reverse` + `areverse`），然后接到后面——因此输出先正放再倒放。倒放那一段会被重新编码，两段最终拼接是无损拷贝。`loop_count` 在这一步统一生效。

### 元数据

`save_metadata` 开启时，提示词 / 工作流会被写入输出容器。`mp4` / `mov` 还会附加 `-movflags +faststart+use_metadata_tags`。GIF 输出不带元数据，因为该容器不支持。

---

## 输出格式

| `format` | 封装 | 视频编码 | 默认 CRF（范围） | 音频 |
|----------|------|---------|------------------|------|
| `video/h264-mp4` | `.mp4` | `libx264` | 19（0–51） | AAC 192k |
| `video/h265-mp4` | `.mp4` | `libx265` | 22（0–51） | AAC 192k |
| `video/h264-mkv` | `.mkv` | `libx264` | 19（0–51） | AAC 192k |
| `video/webm` | `.webm` | `libvpx-vp9` | 30（0–63） | libopus |
| `video/av1-webm` | `.webm` | `libsvtav1` | 23（0–63） | libopus |
| `video/prores-mov` | `.mov` | `prores_ks`（profile `hq`） | —（忽略 CRF） | PCM s16le |
| `image/gif` | `.gif` | palettegen / paletteuse | —（忽略 CRF） | 无 |

手动填入的 `crf` 会被自动钳制到所选格式的范围内；`crf = -1` 时使用该格式的默认值。

---

## 上限说明

- **每组最多 32 个槽位**（`filenames` 与 `videos` 相同）。
- **单个槽位内的视频数量无硬性上限**，可用逗号 / 换行分隔任意多个路径。
- 所选编码器必须存在于 ffmpeg 构建中。节点优先通过 `imageio-ffmpeg` 定位 ffmpeg，其次在 `PATH` 中查找。

---

## 使用示例

- **拼接循环产生的分段视频**：把循环 carry 累加出来的文件名字符串（例如 ComfyUI-Easy-Use 的 `forLoopEnd` 节点，或循环收集的多个 `VHS Select Filename` 输出）接到 `filenames` 组，各分段就会按循环顺序合并。由 `Video Combine 🎥🅥🅗🅢` 写出的分段封装与编码一致，只要 `crf` 保持 `-1`，拼接即为无损。
- **混合来源**：磁盘上已有的视频走 `filenames`，图内刚生成的视频走 `videos`；磁盘上的会先被合并。
- **下游使用**：把 `filenames` 接到其他 [Video Helper Suite](https://github.com/kosinkadink/ComfyUI-VideoHelperSuite) 节点（例如 `Prune Outputs`），或把 `video` 接到核心视频节点。

---

> 返回 [Wiki 首页](Home-简中)
