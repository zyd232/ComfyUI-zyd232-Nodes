<div align="center">

# Merge LoRA Stacks

[![简体中文](https://img.shields.io/badge/简体中文-文档-blue)](Merge-LoRA-Stacks-简中)

</div>

> Back to [Wiki Home](Home)

## Overview

The **Merge LoRA Stacks** node merges multiple `lora_stack` inputs into a single `lora_stack` output. The left-side `lora_stack` inputs are **dynamic** (based on node API V3's Autogrow) and can be freely added or removed.

- **Class name**: `zyd232 MergeLoraStacks`
- **Category**: `zyd232 Nodes`
- **Output**: `LORA_STACK`

---

## Inputs

| Input | Type | Description |
|-------|------|-------------|
| **lora_stack_0** | `LORA_STACK` | A lora_stack to merge (can be added dynamically) |
| **lora_stack_1** | `LORA_STACK` | A lora_stack to merge |
| **...** | `LORA_STACK` | More inputs, can be added dynamically |

> The left-side inputs are dynamic (Autogrow). Click the `+` on the node to add more input slots.

---

## Output

| Output | Type | Description |
|--------|------|-------------|
| **lora_stack** | `LORA_STACK` | The merged single lora_stack |

---

## How It Works

- **Merge order**: Entries are concatenated in slot order (`lora_stack_0` → `lora_stack_1` → ...).
- **Filtering**: Entries with `strength_model == 0` are automatically filtered out (supports both tuple `(lora_name, strength_model, strength_clip)` and dict formats).
- **Empty inputs**: `None` or empty lists are skipped and do not affect the result.

### Data format

A `lora_stack` is a list of LoRA entries, each a 3-tuple:

```
(lora_name, strength_model, strength_clip)
```

For example:

```
[("lora_a.safetensors", 1.0, 1.0), ("lora_b.safetensors", 0.5, 0.5)]
```

---

## Limits

- **Maximum number of left-side lora_stack inputs: 100** (hard limit from ComfyUI V3 API's `Autogrow._MaxNames = 100`).
- **Maximum total number of LoRAs after merging: no hard limit** — limited only by memory (a `lora_stack` is a Python list concatenation).

---

## Usage Examples

- **Merge multiple LoRA stacks**: connect the outputs of several LoRA Stacker nodes to this node's multiple inputs, then pass the merged stack to a downstream LoRA application node.
- **Compatibility with legacy nodes**: this node's `LORA_STACK` output uses the same type identifier as legacy V1 nodes' `LORA_STACK`, so it can be wired directly to/from nodes in comfyui-easy-use, comfyui-lora-optimizer, and others.

---

> Back to [Wiki Home](Home)
