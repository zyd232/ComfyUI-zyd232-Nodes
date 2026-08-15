<div align="center">

# Mask Batch Blend

[![简体中文](https://img.shields.io/badge/简体中文-文档-blue)](zh-CN/Mask-Batch-Blend)

</div>

> Back to [Wiki Home](Home)

## Overview

The **Mask Batch Blend** node blends multiple masks together using different operations (add, max, average). It can handle masks with different dimensions and batch sizes.

- **Class name**: `zyd232 MaskBatchBlend`
- **Category**: `zyd232 Nodes`
- **Output**: `MASK`

---

## Inputs

| Input | Type | Description |
|-------|------|-------------|
| **masks** | `MASK` | Masks to blend (supports batches) |
| **operation** | `["add", "max", "average"]` | Blend operation |

---

## Output

| Output | Type | Description |
|--------|------|-------------|
| **MASK** | `MASK` | The blended single mask |

---

## How It Works

The node automatically handles the input tensor dimensions:

- **2D tensor** `(height, width)` — a batch dimension is added automatically.
- **4D tensor** `(batch, 1, height, width)` — the channel dimension is removed automatically.
- Other shapes raise an error.

### Blend operations

| Operation | Description |
|-----------|-------------|
| **add** | Sums all masks together (overlay effect) |
| **max** | Takes the maximum value at each pixel across all masks |
| **average** | Computes the average of all masks |

### Edge cases

- **Batch size 0** (no masks) — returns an all-zero mask.
- **Batch size 1** (only one mask) — returns that mask directly without blending.

---

## Usage Examples

- **Overlay multiple selections**: use `add` to stack multiple masks into a brighter combined selection.
- **Union**: use `max` to keep any region covered by at least one mask.
- **Smooth transition**: use `average` to get the average intensity of multiple masks.

---

> Back to [Wiki Home](Home)
