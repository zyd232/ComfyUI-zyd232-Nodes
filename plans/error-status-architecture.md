# Error 状态方案：Streaming Text 面板错误检测与工作流中断

## 1. 背景与目标

当前 LLM 生成失败时（如 llama.cpp 的 Jinja 模板异常），后端在 [`LLMGeneratorV3.py`](nodes/LLMGeneratorV3.py:1344) 的 `except` 分支中**吞掉错误**，输出空值并继续后续工作流。用户无法在 Streaming Text 面板看到错误原因。

**目标**：
1. 在 Streaming Text 面板的 Status 状态中新增 **Error** 状态
2. 在输出文字中明确告知用户错误描述（而非空值）
3. 发生错误时，像 Stop Generation 一样**中断工作流**（`nodes.interrupt_processing()`）

## 2. 现状分析

### 2.1 后端错误处理（[`LLMGeneratorV3.py`](nodes/LLMGeneratorV3.py:1344)）

```python
except Exception as e:
    was_stopped = is_generation_stopped()
    if was_stopped:
        push_stream_event(scope, "", "", done=True, stopped=True)
    else:
        print(f"[zyd232 LLM] Generation failed: {e}")
        final_text = ""   # 错误被吞掉，输出空值
        reasoning = ""
```

错误信息在 [`_stream_async`](nodes/LLMGeneratorV3.py:592) 中被包装为 `HTTPError`，`body[:200]` 含服务器返回的错误描述。

### 2.2 前端状态机制（[`streaming_text.js`](web/streaming_text.js:437)）

状态由 `st.streaming` 和 `st.lastDone` 两个布尔值决定：
- `streaming=true` → "Streaming..."
- `streaming=false && lastDone=true` → "Done"
- `streaming=false && lastDone=false` → "Idle"

事件处理（[`streaming_text.js`](web/streaming_text.js:609)）：`data.done` 时设置 `lastDone`，`data.stopped` 时 `lastDone=false`。

### 2.3 中断工作流机制（[`LLMGeneratorV3.py`](nodes/LLMGeneratorV3.py:444)）

`stop_generation_endpoint` 通过 `nodes.interrupt_processing()` 中断工作流。

## 3. 设计方案

### 3.1 后端事件层（[`streaming_events.py`](nodes/streaming_events.py:72)）

`push_stream_event` 增加 `error` 字段：

```python
def push_stream_event(scope, content="", reasoning_content="",
                      done=False, stopped=False, start=False, error=""):
    ...
    PromptServer.instance.send_sync(STREAM_EVENT, {
        "node_id": scope.get("node_id"),
        "prompt_id": scope.get("prompt_id"),
        "content": content or "",
        "reasoning_content": reasoning_content or "",
        "done": bool(done),
        "stopped": bool(stopped),
        "start": bool(start),
        "error": error or "",   # 新增：错误描述
    })
```

### 3.2 后端错误处理（[`LLMGeneratorV3.py`](nodes/LLMGeneratorV3.py:1344)）

非 Stop 异常时，推送 error 事件 + 中断工作流：

```python
except Exception as e:
    was_stopped = is_generation_stopped()
    if was_stopped:
        push_stream_event(scope, "", "", done=True, stopped=True)
    else:
        # 提取错误描述（HTTPError 的 body 含服务器错误信息）
        error_msg = _extract_error_message(e)
        print(f"[zyd232 LLM] Generation failed: {error_msg}")
        # 推送 error 事件，前端显示 Error 状态 + 错误文字
        push_stream_event(scope, "", "", done=True, error=error_msg)
        # 中断工作流，阻止后续节点执行
        try:
            nodes.interrupt_processing()
        except Exception as ie:
            print(f"[zyd232 LLM] Failed to interrupt workflow on error: {ie}")
        final_text = ""
        reasoning = ""
```

**错误信息提取辅助函数**：

```python
def _extract_error_message(e):
    """从异常中提取可读的错误描述。"""
    if isinstance(e, urllib.error.HTTPError):
        # HTTPError 的 read() 含服务器返回的 JSON 错误体
        try:
            body = e.read().decode('utf-8', errors='replace')
            # 尝试解析 JSON 中的 error.message
            try:
                data = json.loads(body)
                msg = data.get("error", {}).get("message") or data.get("message") or body
                return f"HTTP {e.code}: {msg}"
            except Exception:
                return f"HTTP {e.code}: {body[:300]}"
        except Exception:
            return f"HTTP {e.code}"
    return str(e)
```

### 3.3 前端状态（[`streaming_text.js`](web/streaming_text.js:30)）

状态对象增加 `error` 字段：

```javascript
node.__zyd232Stream = {
    ...
    streaming: false,
    lastDone: false,
    error: "",        // 新增：错误描述
    ...
};
```

**事件处理**（[`streaming_text.js`](web/streaming_text.js:609)）：

```javascript
if (data.done) {
    st.streaming = false;
    st.lastDone = true;
    if (data.stopped) {
        st.lastDone = false;
    }
    if (data.error) {
        st.error = data.error;   // 记录错误
        st.lastDone = false;     // 错误不算完成
    } else {
        st.error = "";           // 正常完成清除错误
    }
    ...
}
```

**状态渲染**（[`streaming_text.js`](web/streaming_text.js:437)）：

```javascript
if (st.statusEl) {
    if (st.error) {
        st.statusEl.textContent = $tSync("status.error");
        st.statusEl.style.color = "#e53935";   // 红色
    } else {
        st.statusEl.textContent = st.streaming
            ? $tSync("status.streaming")
            : (st.lastDone ? $tSync("status.done") : $tSync("status.idle"));
        st.statusEl.style.color = st.streaming ? "#4caf50" : "#888";
    }
}
```

**错误文字显示**：在 `renderText` 中，若 `st.error` 存在，在文本区显示错误描述（红色）。

### 3.4 本地化

`locales/zh/main.json` + `locales/en/main.json` 增加：

```json
"status.error": "● 错误"
```

## 4. 实施步骤

1. [`streaming_events.py`](nodes/streaming_events.py:72)：`push_stream_event` 增加 `error` 参数
2. [`LLMGeneratorV3.py`](nodes/LLMGeneratorV3.py:1344)：错误处理改为推送 error 事件 + 中断工作流；新增 `_extract_error_message`
3. [`streaming_text.js`](web/streaming_text.js:30)：状态对象增加 `error`；事件处理记录错误；状态渲染显示 Error；文本区显示错误
4. 本地化文件增加 `status.error`
5. 验证

## 5. 风险与注意事项

- **错误信息长度**：`HTTPError` 的 body 可能很长，需截断（如 300 字符）
- **中断工作流**：`nodes.interrupt_processing()` 在错误时调用，需确保不干扰正常 Stop 流程
- **`_generation_was_stopped`**：错误时不应标记为 stopped（否则 fingerprint_inputs 会强制重跑），需区分
- **前端 `error` 清除**：新生成开始时（`data.start`）应清除 `st.error`
