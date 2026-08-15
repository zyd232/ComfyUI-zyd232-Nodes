<div align="center">

# Save Preview Images

[![简体中文](https://img.shields.io/badge/简体中文-文档-blue)](Save-Preview-Images-简中)

</div>

> Back to [Wiki Home](Home)

## Overview

The **Save Preview Images** node saves input images with various options including format (PNG/JPG), quality, metadata, and custom paths. It can also save the workflow as JSON and generate preview images. Preview images are controlled by the same options. The save function can be disabled to use the node solely for preview purposes.

- **Class name**: `zyd232_SavePreviewImages`
- **Category**: `zyd232 Nodes`
- **Output node**: `OUTPUT_NODE = True` (no data output, UI preview only)

---

## Inputs

| Input | Type | Description |
|-------|------|-------------|
| **images** | `IMAGE` | Images to save |
| **save_image** | `BOOLEAN` | Whether to perform the save operation (default `true`) |
| **save_workflow_as_json** | `BOOLEAN` | Whether to save the workflow as JSON (default `false`) |
| **preview** | `BOOLEAN` | Whether to generate preview images (default `true`) |
| **format** | `["png", "jpg"]` | Output image format |
| **quality** | `INT` | Image quality (default `85`, range 0–100) |
| **meta_data_png** | `BOOLEAN` | Whether to write metadata into PNG (default `true`) |
| **custom_path** | `STRING` | Custom save path (default empty) |
| **filename_prefix** | `STRING` | Filename prefix (default `ComfyUI_`) |
| **timestamp** | `["second", "millisecond", "None"]` | Filename timestamp mode |

---

## Output

No data output. The node returns a preview image list via UI (`type: "temp"`).

---

## How It Works

### Saving images

- Supports **PNG** and **JPG** formats.
- **quality** controls compression: PNG uses `compress_level` (computed as `(100 - quality) // 10`), JPG uses the `quality` parameter.
- When `save_image = false`, actual saving is skipped; the node is used for preview only.

### Filename & timestamp

- **filename_prefix** supports `%date` (`YYYY-MM-DD`) and `%time` (`HH-MM-SS`) placeholders.
- **timestamp** determines the filename suffix:
  - `second` — appends `YYYY-MM-DD_HH-MM-SS`
  - `millisecond` — appends `YYYY-MM-DD_HH-MM-SS-fff`
  - `None` — uses a counter (`_00001`, etc.)
- If a file already exists, the counter is incremented automatically to avoid overwriting.

### Custom path

- **custom_path** supports `%date` and `%time` placeholders.
- The directory is created automatically if it does not exist.
- Leave empty to save to the ComfyUI default output directory.

### Metadata

- When `meta_data_png = true`, the `prompt` and `extra_pnginfo` (including the workflow) are written into the PNG metadata.

### Workflow JSON

- When `save_workflow_as_json = true`, the workflow is saved as a `.json` file with the same name as the image.
- If no workflow data is found, a message is printed and saving is skipped.

### Preview

- When `preview = true`, a preview image is generated (saved to the temp directory) and shown in the UI.
- Preview filenames use a random name (`saveimage_preview_*`) or a timestamped name.

---

## Usage Examples

- **Preview only**: set `save_image = false`, `preview = true` to view the result on the canvas without writing to disk.
- **Save PNG with workflow**: set `format = png`, `save_workflow_as_json = true`, `meta_data_png = true`.
- **Archive by date**: set `custom_path = "outputs/%date"`, `filename_prefix = "img_%date"`.

---

> Back to [Wiki Home](Home)
