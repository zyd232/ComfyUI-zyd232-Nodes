<div align="center">

# Images Pixels Compare

[![简体中文](https://img.shields.io/badge/简体中文-文档-blue)](zh-CN/Images-Pixels-Compare)

</div>

> Back to [Wiki Home](Home)

## Overview

The **Images Pixels Compare** node compares two input images at the **pixel level** to check whether they are exactly the same, and outputs a boolean value.

- **Class name**: `zyd232 ImagesPixelsCompare`
- **Category**: `zyd232 Nodes`
- **Output**: `BOOLEAN`

---

## Inputs

| Input | Type | Description |
|-------|------|-------------|
| **image1** | `IMAGE` | First image to compare |
| **image2** | `IMAGE` | Second image to compare |
| **if_same_output** | `BOOLEAN` | Output logic switch (default `true`) |

---

## Output

| Output | Type | Description |
|--------|------|-------------|
| **BOOLEAN** | `BOOLEAN` | Comparison result |

---

## How It Works

The node compares **all pixel values** of the two images to check if they are identical:

- When `if_same_output = true`, it outputs `true` if the two images are **identical**, `false` if they differ.
- When `if_same_output = false`, the output logic is **inverted**: it outputs `true` if the two images **differ**, `false` if they are identical.

### Different sizes

If the two images have **different shapes (sizes)**, the node cannot compare pixel by pixel. In that case it returns based on the switch:

- `if_same_output = true` → returns `false` (treated as different)
- `if_same_output = false` → returns `true` (treated as different)

---

## Usage Example

Useful for workflow control, for example:

- Determine whether the output image of a step has changed, to decide whether to continue downstream processing.
- Combine with the `if_same_output` switch to implement "if same, do A; if different, do B" branching logic.

---

> Back to [Wiki Home](Home)
