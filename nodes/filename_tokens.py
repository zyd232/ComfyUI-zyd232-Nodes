"""filename_prefix / custom_path 的占位符展开与文件名清洗（多节点共用）。

为什么放在后端
--------------
ComfyUI 把 ``%date:...%`` 这类 token 的展开放在**前端**（控件的 serializeValue →
``app.applyTextReplacements``），只有在界面点运行时才执行；通过 API（comfy-cli /
MCP 等）提交的 prompt 不经过前端，token 会原样进后端，变成含 ``:`` 的非法文件名，
让保存阶段报 ``Error opening output ... Invalid argument``。这里在后端完成展开与
清洗，界面 / API / MCP 三种提交途径的行为就一致了。

支持两种写法
------------
* **核心写法**：``%date:yyyy-MM-dd%`` / ``%time:HHmmss%``
  格式串语义与前端 ``formatUtil`` 的实现完全一致：d/dd 日、M/MM 月、h/hh 时
  （24 小时制）、m/mm 分、s/ss 秒、yy/yyyy 年，位数不足左侧补零。
* **简写**：``%date`` / ``%time``（闭合的 ``%`` 可写可不写，``%date%`` 也接受）
  等价于 ``%date:yyyy-MM-dd%`` / ``%time:HH-mm-ss%``。

老式转义符（``%year% %month% %day% %hour% %minute% %second% %width% %height%``）由
``folder_paths.get_save_image_path()`` 负责，本模块不处理，也不会报成"未展开"。
"""

import datetime
import re

__all__ = [
    "format_date",
    "expand_placeholders",
    "sanitize_filename",
    "prepare_path_prefix",
    "unresolved_tokens",
]

# 带格式串的核心写法：%date:yyyy-MM-dd%
_PLACEHOLDER = re.compile(r"%([^%]+)%")
# 简写形式。后面的负向断言避免误伤 %timeout% 这类普通词，同时允许 %date_foo。
_SHORT_DATE = re.compile(r"%date(?![A-Za-z0-9])%?")
_SHORT_TIME = re.compile(r"%time(?![A-Za-z0-9])%?")
# 前端 formatDate 支持的日期占位符（顺序与前端正则一致）。
_DATE_PLACEHOLDER = re.compile(r"dd?|MM?|hh?|mm?|ss?|yyy?y?")
# Windows 文件名非法字符；'/' 与 '\' 不在此列，它们表示子目录分隔。
_ILLEGAL_CHARS = re.compile(r'[<>:"|?*\x00-\x1f]')

SHORT_DATE_FORMAT = "%Y-%m-%d"
SHORT_TIME_FORMAT = "%H-%M-%S"

# get_save_image_path() 自己能展开的老式 token，别误报为"未展开"。
LEGACY_TOKENS = frozenset({
    "%width%", "%height%", "%year%", "%month%", "%day%",
    "%hour%", "%minute%", "%second%",
})


def format_date(fmt, now):
    """按前端 formatDate 的语义展开一个日期格式串。

    ``fmt`` 只含日期占位符与字面量，例如 ``yyyy-MM-dd`` / ``hhmmss``。
    """
    values = {"d": now.day, "M": now.month, "h": now.hour,
              "m": now.minute, "s": now.second}

    def repl(match):
        token = match.group(0)
        if token == "yyyy":
            return "%04d" % now.year
        if token == "yy":
            return ("%04d" % now.year)[2:]
        head = token[0]
        if head in values and len(token) in (1, 2):
            return str(values[head]).zfill(len(token))
        return token

    return _DATE_PLACEHOLDER.sub(repl, fmt)


def expand_placeholders(value, now=None):
    """展开核心写法与简写两种占位符。"""
    if not value or "%" not in value:
        return value
    now = now or datetime.datetime.now()

    def repl(match):
        body = match.group(1)
        lowered = body.lower()
        for head in ("date:", "time:"):
            if lowered.startswith(head):
                inner = body[len(head):]
                if inner:
                    return format_date(inner, now)
        return match.group(0)

    # 顺序不能颠倒：先展开带格式串的核心写法，再处理简写；否则 %date:yyyy%
    # 会被简写规则从中间截断，留下一个 ':'。
    text = _PLACEHOLDER.sub(repl, value)
    text = _SHORT_DATE.sub(now.strftime(SHORT_DATE_FORMAT), text)
    text = _SHORT_TIME.sub(now.strftime(SHORT_TIME_FORMAT), text)
    return text


def unresolved_tokens(value):
    """返回既非本模块可展开、也非 get_save_image_path 负责的占位符。"""
    return sorted({m.group(0) for m in _PLACEHOLDER.finditer(value)} - LEGACY_TOKENS)


def sanitize_filename(value):
    """把 Windows 文件名非法字符换成 '_'，保留 '/' 作为子目录分隔符。

    兜底：无论还剩哪些没能展开的占位符（例如 %节点标题.字段%），都不会再生成
    非法文件名让保存 / ffmpeg 阶段失败。
    """
    text = str(value).replace("\\", "/")
    text = _ILLEGAL_CHARS.sub("_", text)
    parts = [part.strip(" .") for part in text.split("/")]
    parts = [part for part in parts if part]
    return "/".join(parts)


def prepare_path_prefix(value, now=None, default="ComfyUI", label="filename_prefix"):
    """展开占位符 → 清洗非法字符，返回可直接交给 get_save_image_path 的前缀。

    只用于**相对的**名称前缀（如 filename_prefix）。绝对路径（如自定义输出目录）
    请改用 :func:`expand_placeholders`，否则盘符里的 ``:`` 会被当成非法字符替换掉。
    """
    expanded = expand_placeholders(value, now)
    left = unresolved_tokens(expanded)
    if left:
        # 用字符串拼接而不是 %-格式化：文案里本来就有大量 % 号。
        print("[zyd232] " + label + " 含后端无法展开的占位符 " + ", ".join(left)
              + "，将按字面量使用。%date:...% / %time:...% 以及简写 %date / %time "
              + "可由后端展开；%节点标题.字段% 依赖前端，经 API 提交时不会展开。")
    return sanitize_filename(expanded) or default
