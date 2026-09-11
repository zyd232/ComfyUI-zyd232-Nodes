<div align="center">

# LLM Unload

[![English](https://img.shields.io/badge/English-Docs-blue)](LLM-Unload)

</div>

> 返回 [Wiki 首页](Home-简中)

## 概述

**LLM Unload** 节点向 LLM Server 发送 unload 信号，使模型从显存中释放。当工作流先跑 LLM、接着又要跑大型扩散模型时，中间卸载一次可以避免两者争抢显存。

本节点的参数**几乎全部来自 LLM Text Generator 所保存的 config preset**——它自身没有任何服务器配置项。同时它像 reroute 一样：`any_input` 收到什么，`any_output` 就原样输出什么，因此可以插进工作流任意位置而不破坏链路。

- **类名**：`zyd232 LLMUnload`
- **类别**：`zyd232 Nodes/LLM`
- **输出**：`*`

> **使用前请先确认**：LLM Text Generator 节点能够正常跑通 **Unload After Gen**。本节点不负责配置服务器，它复用 preset，因此 preset 里必须已经有一份可用的 `base_url`、`api_key` 与模型名。

---

## 输入

| 字段（英文） | 字段（中文） | 类型 | 说明 |
|------|------|------|------|
| **config_select** | 配置预设 | `COMBO` | 选择已保存的服务器预设。`base_url`、`api_key`、`model`、`server_type`、`unload_endpoint` 均从该预设读取 |
| **model_select** | 模型选择 | `COMBO` | 下拉选择要卸载的模型，选择后会填入下方的 `model` 字段 |
| **model** | 模型 | `STRING` | 要卸载的模型名称（自由输入）。可手动输入或从上方下拉框选择。留空则回退到预设中保存的模型 |
| **unload_timeout** | 卸载超时 | `INT` | 0–60，默认 `1`。等待服务端完成卸载的最大秒数。`0` 表示不等待、立即继续。该控件来自节点自身，**不**从预设读取 |
| **any_input** | 任意输入 | `*`（可选） | 可选的透传值，使该节点可插入工作流任意位置 |

---

## 输出

| 输出 | 类型 | 说明 |
|------|------|------|
| **any_output** | `*` | `any_input` 的值，原样透传 |

---

## 功能说明

1. **读取预设** —— 从 LLM Text Generator 保存的配置文件中读取所选预设。非法的预设名会被自动清洗。
2. **解析 API 密钥** —— `ENV:变量名` 写法会从环境变量读取；掩码值视为空。若最终仍无密钥，则回退到 `Default` 预设的 `api_key`。
3. **确定要卸载的模型** —— 优先使用节点自身的 `model` 字段；为空时使用预设中的 `model`。
4. **发送卸载信号** —— 按 `server_type`（`auto`、`openai`、`vllm`、`llama.cpp`、`ollama`，其他值一律按 `auto` 处理）构建信号，经共享的 server adapter 发送。
5. **确认模型已释放** —— 采用混合策略：先同步发送卸载请求，再轮询 `/v1/models` 确认模型确实已释放，整个过程受 `unload_timeout` 限制。这样可避免服务端尚未卸载完成时下游节点就 OOM。
6. **透传返回** —— 无论结果如何，都会返回 `any_input`。

在 `auto` 模式下，探测失败时会走多端点兜底，确保卸载 / 停止信号仍能送达。

### 什么情况下不会发信号

以下情况会打印提示并**直接透传、不发送任何信号**：

- 预设中没有 `base_url`
- 无法确定模型（`model` 字段与预设中都没有）

若卸载请求本身失败，节点会打印错误，但依然返回 `any_input`——**绝不中断工作流**。

---

## 上限与注意事项

- **失败不会阻塞工作流。** 错误只会输出到 ComfyUI 控制台。
- **`unload_timeout = 0`** 表示发完请求立即继续、不确认释放。不想等待时可用，但下游节点有可能撞上仍在卸载中的服务端。
- 确认步骤依赖服务端实现 `/v1/models`。若服务端未提供该接口，则只会白等掉超时时间。
- config preset 由 LLM Text Generator 节点管理，请在那里编辑，而不是在本节点。

---

## 使用示例

- **在阶段之间释放显存**：LLM Text Generator → LLM Unload → 重量级扩散 / 放大阶段。扩散模型就能拿到 LLM 释放出来的显存。
- **带副作用的 reroute**：借助 `any_input` / `any_output` 的透传，可以把本节点直接插进任意一条既有连线，无需改动其他布线即可增加一次卸载。
- **卸载指定模型**：当服务端同时驻留多个模型时，在 `model_select` 中选定目标（或直接填入 `model`），而不要依赖预设中的模型名。

---

> 返回 [Wiki 首页](Home-简中)
