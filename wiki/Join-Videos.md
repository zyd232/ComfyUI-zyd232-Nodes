<div align="center">

# Join Videos

[![简体中文](https://img.shields.io/badge/简体中文-文档-blue)](Join-Videos-简中)

</div>

> Back to [Wiki Home](Home)

## Overview

The **Join Videos** node concatenates multiple videos into one, **in input order**. It accepts two kinds of input, both of which are **dynamic** (based on node API V3's Autogrow) and can be freely added or removed:

- **`filenames`** — video files on disk (each slot holds one path, or several paths separated by commas / newlines)
- **`videos`** — ComfyUI `VIDEO` objects

The `filenames` group is merged first, then the `videos` group. The node outputs both a `VHS_FILENAMES` value (usable by Video Helper Suite nodes) and a `VIDEO` value, and previews the merged result directly on the node itself.

- **Class name**: `zyd232_JoinVideos`
- **Category**: `zyd232 Nodes`
- **Outputs**: `VHS_FILENAMES`, `VIDEO`

---

## Inputs

| Input | Type | Description |
|-------|------|-------------|
| **filenames** | `STRING` (Autogrow) | Video file paths to merge. Each slot holds one path, or several paths separated by commas / newlines. Slots are dynamic — click `+` to add more. |
| **videos** | `VIDEO` (Autogrow) | `VIDEO` inputs to merge. Merged after every `filenames` slot. Slots are dynamic. |
| **filename_prefix** | `STRING` | Output filename prefix (default `zyd232_merged`). |
| **frame_rate** | `FLOAT` | 1–240, default `24`. Frame rate used when re-encoding, and reported in the preview. A lossless stream copy keeps each source's own timing. |
| **format** | `COMBO` | Output container / codec — see [Formats](#formats). Default `video/h264-mp4`. |
| **crf** | `INT` | -1–63, default `-1`. Lower is better quality and a larger file. `-1` leaves the quality untouched, which enables the lossless stream-copy path. |
| **save_metadata** | `BOOLEAN` | Default `Yes`. Embed the prompt / workflow metadata into the output container. |
| **pingpong** | `BOOLEAN` | Default `No`. Append a reversed copy of the merged video (play forward, then backward). |
| **loop_count** | `INT` | 0–100, default `0`. How many extra times to repeat the merged video (`0` = play once). |
| **save_output** | `BOOLEAN` | Default `Yes`. Save into the output directory. When off, the result goes to the temp directory. |

> Both Autogrow groups start with no slot in use. Connect one and a fresh empty slot appears below it.

---

## Outputs

| Output | Type | Description |
|--------|------|-------------|
| **filenames** | `VHS_FILENAMES` | `(save_output, [path])` — the standard Video Helper Suite filenames value, usable by other VHS nodes. |
| **video** | `VIDEO` | The merged video as a ComfyUI `VIDEO`, usable by core video nodes. |

---

## How It Works

### Merge order

1. Every slot of the `filenames` group, in slot order (`filename_0` → `filename_1` → …)
2. Then every slot of the `videos` group, in slot order (`video_0` → `video_1` → …)

Inside a single `filename` slot, paths are read left to right after splitting on commas / newlines. Empty entries are ignored, so a trailing separator — or a loop-accumulator string that begins with a comma — is harmless.

### Lossless copy vs. re-encode

Merging is done with **ffmpeg's concat demuxer**, in one of two modes:

| Mode | Used when | Result |
|------|-----------|--------|
| **Stream copy** (`-c copy`) | `crf = -1`, `pingpong` off, `format` is not `image/gif`, **and** every source already uses the target container's extension | Lossless and fast — nothing is re-encoded |
| **Re-encode** | Anything else | The result is re-encoded with the selected format and `crf` |

If a stream copy is attempted but fails (for example the segments' codecs have drifted apart), the node prints a warning and automatically retries with a re-encode.

### Pingpong

`pingpong` merges the sources, encodes a reversed copy of the result (`reverse` + `areverse`), then appends it, so the output plays forward and then backward. The reversed half is re-encoded; the final join of the two halves is a lossless copy. `loop_count` is applied at that final step.

### Metadata

When `save_metadata` is on, the prompt / workflow is embedded into the container. For `mp4` / `mov` the node also writes `-movflags +faststart+use_metadata_tags`. GIF output carries no metadata, because the container does not support it.

---

## Formats

| `format` | Container | Video codec | Default CRF (range) | Audio |
|----------|-----------|-------------|---------------------|-------|
| `video/h264-mp4` | `.mp4` | `libx264` | 19 (0–51) | AAC 192k |
| `video/h265-mp4` | `.mp4` | `libx265` | 22 (0–51) | AAC 192k |
| `video/h264-mkv` | `.mkv` | `libx264` | 19 (0–51) | AAC 192k |
| `video/webm` | `.webm` | `libvpx-vp9` | 30 (0–63) | libopus |
| `video/av1-webm` | `.webm` | `libsvtav1` | 23 (0–63) | libopus |
| `video/prores-mov` | `.mov` | `prores_ks` (profile `hq`) | — (CRF ignored) | PCM s16le |
| `image/gif` | `.gif` | palettegen / paletteuse | — (CRF ignored) | none |

When a `crf` value is supplied it is clamped to the selected format's range; `crf = -1` uses that format's default value.

---

## Limits

- **Maximum slots per group: 32** — for `filenames` and `videos` alike.
- **No hard limit on the number of videos inside one slot** — a `filename` slot may hold any number of comma / newline separated paths.
- The selected encoder must exist in the ffmpeg build. The node looks for ffmpeg through `imageio-ffmpeg` first, then on `PATH`.

---

## Usage Examples

- **Join the per-segment videos of a loop**: feed the filename string accumulated by a loop's carry (for example the `forLoopEnd` node of ComfyUI-Easy-Use, or `VHS Select Filename` outputs collected by a loop) into the `filenames` group. Every segment is merged in loop order. Segments written by `Video Combine 🎥🅥🅗🅢` share the same container and codec, so the join stays lossless as long as `crf` is left at `-1`.
- **Mixing sources**: use `filenames` for videos that are already on disk and `videos` for videos produced inside the graph. Everything on disk is merged first.
- **Downstream use**: wire `filenames` into other Video Helper Suite nodes (for example `Prune Outputs`), or wire `video` into core video nodes.

---

> Back to [Wiki Home](Home)
