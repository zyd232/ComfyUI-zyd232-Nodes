<div align="center">

# Mask Batch Blend

[![English](https://img.shields.io/badge/English-Docs-blue)](Mask-Batch-Blend)

</div>

> 返回 [Wiki 首页](Home-简中)

## 概述

**Mask Batch Blend** 节点用于将多个 Mask 通过不同的操作（add、max、average）合并为一个 Mask。它可以处理不同尺寸和批次大小的 Mask。

- **类名**：`zyd232 MaskBatchBlend`
- **类别**：`zyd232 Nodes`
- **输出**：`MASK`

---

## 输入

| 输入 | 类型 | 说明 |
|------|------|------|
| **masks** | `MASK` | 待合并的 Mask（支持批次） |
| **operation** | `["add", "max", "average"]` | 合并操作方式 |

---

## 输出

| 输出 | 类型 | 说明 |
|------|------|------|
| **MASK** | `MASK` | 合并后的单个 Mask |

---

## 功能说明

节点自动处理输入张量的维度：

- **2D 张量** `(height, width)` — 自动添加批次维度。
- **4D 张量** `(batch, 1, height, width)` — 自动移除通道维度。
- 其他形状会抛出错误。

### 合并操作

| 操作 | 说明 |
|------|------|
| **add** | 将所有 Mask 相加（叠加效果） |
| **max** | 在每个像素位置取所有 Mask 的最大值 |
| **average** | 计算所有 Mask 的平均值 |

### 边界情况

- **批次大小为 0**（无 Mask）— 返回全零 Mask。
- **批次大小为 1**（只有一个 Mask）— 直接返回该 Mask，不进行合并。

---

## 使用示例

- **叠加多个选区**：使用 `add` 将多个 Mask 叠加，形成更亮的合并选区。
- **取并集**：使用 `max` 保留所有 Mask 中任意一个覆盖的区域。
- **平滑过渡**：使用 `average` 得到多个 Mask 的平均强度。

---

> 返回 [Wiki 首页](Home-简中)
