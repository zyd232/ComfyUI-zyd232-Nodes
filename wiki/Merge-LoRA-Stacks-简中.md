<div align="center">

# Merge LoRA Stacks

[![English](https://img.shields.io/badge/English-Docs-blue)](Merge-LoRA-Stacks)

</div>

> 返回 [Wiki 首页](Home-简中)

## 概述

**Merge LoRA Stacks** 节点用于将多个 `lora_stack` 输入合并为一个 `lora_stack` 输出。左侧的 `lora_stack` 输入为**动态输入**（基于 node API V3 的 Autogrow），可自由增加或减少输入数量。

- **类名**：`zyd232 MergeLoraStacks`
- **类别**：`zyd232 Nodes`
- **输出**：`LORA_STACK`

---

## 输入

| 字段（英文） | 字段（中文） | 类型 | 说明 |
|------|------|------|------|
| **lora_stack_0** | LoRA 栈 0 | `LORA_STACK` | 待合并的 lora_stack（可动态增加） |
| **lora_stack_1** | LoRA 栈 1 | `LORA_STACK` | 待合并的 lora_stack |
| **...** | ... | `LORA_STACK` | 更多输入，可动态添加 |

> 左侧输入为动态输入（Autogrow），点击节点上的 `+` 即可增加输入槽位。

---

## 输出

| 输出 | 类型 | 说明 |
|------|------|------|
| **lora_stack** | `LORA_STACK` | 合并后的单个 lora_stack |

---

## 功能说明

- **合并顺序**：按输入槽位顺序（`lora_stack_0` → `lora_stack_1` → ...）依次拼接各输入中的 LoRA 条目。
- **过滤规则**：自动过滤掉 `strength_model == 0` 的条目（兼容元组 `(lora_name, strength_model, strength_clip)` 与字典两种格式）。
- **空输入处理**：`None` 或空列表的输入会被跳过，不影响合并结果。

### 数据格式

`lora_stack` 是一个 LoRA 条目列表，每个条目为三元组：

```
(lora_name, strength_model, strength_clip)
```

例如：

```
[("lora_a.safetensors", 1.0, 1.0), ("lora_b.safetensors", 0.5, 0.5)]
```

---

## 上限说明

- **左侧 lora_stack 输入数量上限：100 个**（由 ComfyUI V3 API 的 `Autogrow._MaxNames = 100` 硬性限制）。
- **合并后 lora 总数上限：无硬性上限**，仅受内存限制（`lora_stack` 是 Python 列表拼接）。

---

## 使用示例

- **合并多个 LoRA 栈**：将多个 LoRA Stacker 节点的输出连接到本节点的多个输入，合并为一个栈后统一传给下游的 LoRA 应用节点。
- **与旧节点兼容**：本节点输出的 `LORA_STACK` 类型与旧 V1 节点的 `LORA_STACK` 类型标识一致，可直接与 comfyui-easy-use、comfyui-lora-optimizer 等旧节点的输入/输出连线。

---

> 返回 [Wiki 首页](Home-简中)
