<div align="center">

# Images Pixels Compare

[![English](https://img.shields.io/badge/English-Docs-blue)](Images-Pixels-Compare)

</div>

> 返回 [Wiki 首页](Home-简中)

## 概述

**Images Pixels Compare** 节点用于**像素级比较**两张输入图片是否完全相同，并输出一个布尔值。

- **类名**：`zyd232 ImagesPixelsCompare`
- **类别**：`zyd232 Nodes`
- **输出**：`BOOLEAN`

---

## 输入

| 字段（英文） | 字段（中文） | 类型 | 说明 |
|------|------|------|------|
| **image1** | 图片 1 | `IMAGE` | 第一张待比较图片 |
| **image2** | 图片 2 | `IMAGE` | 第二张待比较图片 |
| **if_same_output** | 相同则输出 | `BOOLEAN` | 输出逻辑开关（默认 `true`） |

---

## 输出

| 输出 | 类型 | 说明 |
|------|------|------|
| **BOOLEAN** | `BOOLEAN` | 比较结果 |

---

## 功能说明

节点会比较两张图片的**所有像素值**是否完全相同：

- 当 `if_same_output = true` 时，输出 `true` 表示两张图片**完全相同**，`false` 表示不同。
- 当 `if_same_output = false` 时，输出逻辑**反转**：输出 `true` 表示两张图片**不同**，`false` 表示相同。

### 尺寸不同的情况

如果两张图片的**尺寸（shape）不同**，节点无法进行逐像素比较，此时会根据开关状态返回：

- `if_same_output = true` → 返回 `false`（视为不同）
- `if_same_output = false` → 返回 `true`（视为不同）

---

## 使用示例

常用于流程控制，例如：

- 判断某一步骤的输出图片是否发生变化，从而决定是否继续后续处理。
- 结合 `if_same_output` 开关，实现「相同则执行 A，不同则执行 B」的分支逻辑。

---

> 返回 [Wiki 首页](Home-简中)
