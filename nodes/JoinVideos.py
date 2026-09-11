"""Join Videos 节点：把多段视频按输入顺序合并为一段。

两组输入都是自增加（Autogrow）输入，做法与 LLM Text Generator 的 ``image`` 一致：
初始不占用槽位，每连上一个就自动再长出一个空槽。

* ``filenames`` —— 每槽一个字符串路径。为兼容 ``easy forLoopEnd`` 之类的循环累加串，
  单个槽里也可以用逗号 / 换行分隔多个路径。
* ``videos``    —— 每槽一个 ComfyUI ``VIDEO``。

合并顺序：先 filenames 组（按槽位序号），再 video 组（按槽位序号）。

输出两项：``filenames``（VHS_FILENAMES，可继续喂给 VHS 节点）与 ``video``（VIDEO），
并在节点上预览合成结果。若所有源与目标封装一致且未要求改动质量，走 ffmpeg concat
无损流拷贝（失败自动降级为重编码）；否则按所选格式重编码。
"""

import importlib.util as _importlib_util
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from io import BytesIO

import folder_paths
from comfy_api.latest import InputImpl, io, ui

# nodes/ 目录不是 Python 包（模块按文件路径在 __init__.py 中加载），因此这里按
# 文件路径加载共享模块并缓存到 sys.modules，保证与其他节点共用同一个实例。
if "zyd232_filename_tokens" not in sys.modules:
    _TOKENS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "filename_tokens.py")
    _tokens_spec = _importlib_util.spec_from_file_location("zyd232_filename_tokens", _TOKENS_PATH)
    _tokens_mod = _importlib_util.module_from_spec(_tokens_spec)
    sys.modules["zyd232_filename_tokens"] = _tokens_mod
    _tokens_spec.loader.exec_module(_tokens_mod)
_filename_tokens = sys.modules["zyd232_filename_tokens"]

_ENCODE_ARGS = ("utf-8", "replace")
_MAX_SLOTS = 32  # 与 LLM Text Generator 的自增加上限保持一致

# ---------------------------------------------------------------------------
# 输出格式表
#   crf=None      -> 该格式不使用 crf（如 ProRes）
#   vf            -> 重编码时附加的 -vf（统一到 bt709，避免色彩漂移）
#   acodec=None   -> 无音轨输出
#   movflags=True -> mp4/mov 容器，需要 movflags / 支持元数据标签
#   meta=False    -> 容器不支持写入元数据（如 gif）
# ---------------------------------------------------------------------------
_FORMATS = {
    "video/h264-mp4": {
        "ext": "mp4",
        "vcodec": ["-c:v", "libx264"],
        "pix_fmt": "yuv420p",
        "crf": 19,
        "crf_max": 51,
        "extra": ["-preset", "medium"],
        "vf": "scale=out_color_matrix=bt709",
        "acodec": ["-c:a", "aac", "-b:a", "192k"],
        "movflags": True,
    },
    "video/h265-mp4": {
        "ext": "mp4",
        "vcodec": ["-c:v", "libx265"],
        "pix_fmt": "yuv420p",
        "crf": 22,
        "crf_max": 51,
        "extra": ["-preset", "medium", "-vtag", "hvc1", "-x265-params", "log-level=quiet"],
        "vf": "scale=out_color_matrix=bt709",
        "acodec": ["-c:a", "aac", "-b:a", "192k"],
        "movflags": True,
    },
    "video/h264-mkv": {
        "ext": "mkv",
        "vcodec": ["-c:v", "libx264"],
        "pix_fmt": "yuv420p",
        "crf": 19,
        "crf_max": 51,
        "extra": ["-preset", "medium"],
        "vf": "scale=out_color_matrix=bt709",
        "acodec": ["-c:a", "aac", "-b:a", "192k"],
    },
    "video/webm": {
        "ext": "webm",
        "vcodec": ["-c:v", "libvpx-vp9"],
        "pix_fmt": "yuv420p",
        "crf": 30,
        "crf_max": 63,
        "extra": ["-b:v", "0"],
        "vf": "scale=out_color_matrix=bt709",
        "acodec": ["-c:a", "libopus"],
    },
    "video/av1-webm": {
        "ext": "webm",
        "vcodec": ["-c:v", "libsvtav1"],
        "pix_fmt": "yuv420p",
        "crf": 23,
        "crf_max": 63,
        "extra": [],
        "vf": "scale=out_color_matrix=bt709",
        "acodec": ["-c:a", "libopus"],
        "env": {"SVT_LOG": "1"},
    },
    "video/prores-mov": {
        "ext": "mov",
        "vcodec": ["-c:v", "prores_ks", "-profile:v", "hq"],
        "pix_fmt": "yuv422p10le",
        "crf": None,
        "extra": [],
        "vf": None,
        "acodec": ["-c:a", "pcm_s16le"],
        "movflags": True,
    },
    "image/gif": {
        "ext": "gif",
        "gif": True,
        "acodec": None,
        "meta": False,
    },
}

_DEFAULT_FORMAT = "video/h264-mp4"


def _find_ffmpeg() -> str:
    """定位 ffmpeg 可执行文件。"""
    try:
        from imageio_ffmpeg import get_ffmpeg_exe

        path = get_ffmpeg_exe()
        if path and os.path.isfile(path):
            return path
    except Exception:
        pass
    found = shutil.which("ffmpeg")
    if found:
        return found
    raise RuntimeError(
        "Join Videos: ffmpeg was not found. Install imageio-ffmpeg or put ffmpeg on your PATH."
    )


def _run(args, env=None):
    proc = subprocess.run(args, capture_output=True, env=env)
    if proc.returncode != 0:
        raise RuntimeError(
            "ffmpeg failed (exit %s):\n%s\ncommand: %s"
            % (proc.returncode, proc.stderr.decode(*_ENCODE_ARGS), " ".join(args))
        )
    return proc


def _parse_slot_index(key) -> int:
    """取 autogrow 槽名 ``filename_3`` 末尾的序号。"""
    match = re.search(r"_(\d+)\s*$", str(key))
    return int(match.group(1)) if match else -1


def _write_concat_list(files, list_path):
    with open(list_path, "w", encoding="utf-8") as handle:
        for path in files:
            handle.write("file '%s'\n" % path.replace("'", "'\\''"))


def _resolve_path(raw, search_dirs):
    if os.path.isabs(raw):
        if os.path.isfile(raw):
            return raw
    else:
        for folder in search_dirs:
            candidate = os.path.join(folder, raw)
            if os.path.isfile(candidate):
                return candidate
    raise FileNotFoundError(
        "Join Videos: video file not found: %s (searched: %s)"
        % (raw, ", ".join(search_dirs))
    )


def _fmt_rate(frame_rate):
    rate = float(frame_rate or 24.0)
    return "%d" % round(rate) if abs(rate - round(rate)) < 1e-6 else "%.6g" % rate


def _pick_crf(spec, crf):
    """把 crf 解析成实际使用的值：-1 / None 表示用该格式的默认值。"""
    default = spec.get("crf")
    if default is None:
        return None
    if crf is None or int(crf) < 0:
        return default
    return max(0, min(int(crf), spec.get("crf_max", 63)))


def _encode_args(spec, crf, frame_rate, lead_video_filter=None, lead_audio_filter=None):
    """构造重编码参数。GIF 走 filter_complex 调色板；lead_* 用于 pingpong 的倒放。"""
    if spec.get("gif"):
        lead = (lead_video_filter + ",") if lead_video_filter else ""
        return [
            "-filter_complex",
            "[0:v] %sfps=%s, split [a][b]; [a] palettegen=reserve_transparent=0 [p]; "
            "[b][p] paletteuse=dither=sierra2_4a" % (lead, _fmt_rate(frame_rate)),
            "-an",
        ]

    args = list(spec["vcodec"])
    if spec.get("pix_fmt"):
        args += ["-pix_fmt", spec["pix_fmt"]]
    picked = _pick_crf(spec, crf)
    if picked is not None:
        args += ["-crf", str(picked)]
    args += list(spec.get("extra", []))
    filters = [part for part in (lead_video_filter, spec.get("vf")) if part]
    if filters:
        args += ["-vf", ",".join(filters)]
    if spec.get("acodec"):
        args += list(spec["acodec"])
        if lead_audio_filter:
            args += ["-af", lead_audio_filter]
    else:
        args += ["-an"]
    args += ["-r", _fmt_rate(frame_rate)]
    return args


def _escape_metadata(key, value):
    """按 FFMETADATA1 规范转义 key/value（与 Video Helper Suite 同一套规则）。"""
    text = str(value)
    for char in ("\\", ";", "#", "="):
        text = text.replace(char, "\\" + char)
    text = text.replace("\n", "\\\n")
    return "%s=%s" % (key, text)


def _write_metadata_file(path, hidden, save_metadata):
    """把 prompt / workflow 写成 FFMETADATA1 文件，返回其路径（未启用则 None）。

    必须走文件、不能走 ``-metadata key=value`` 命令行参数：完整工作流 JSON 动辄
    上百 KB，而 Windows 的 CreateProcess 命令行上限是 32767 字符，直接作为参数
    传入会抛 ``FileNotFoundError: [WinError 206] 文件名或扩展名太长``。
    """
    if not save_metadata or hidden is None:
        return None
    entries = []
    prompt = getattr(hidden, "prompt", None)
    if prompt is not None:
        entries.append(_escape_metadata("prompt", json.dumps(prompt)))
    for key, value in (getattr(hidden, "extra_pnginfo", None) or {}).items():
        entries.append(_escape_metadata(key, json.dumps(value)))
    if not entries:
        return None
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(";FFMETADATA1\n")
        handle.write("\n".join(entries) + "\n")
    return path


def _can_stream_copy(files, spec, crf, ignore_crf=False):
    """能否直接 -c copy：所有源与目标封装一致，且未要求改动质量。"""
    if spec.get("gif"):
        return False
    if not ignore_crf and crf is not None and int(crf) >= 0:
        return False
    target = "." + spec["ext"]
    return all(os.path.splitext(path)[1].lower() == target for path in files)


def _concat(ffmpeg, files, out_path, list_path, spec, crf, frame_rate,
            loop_count, metadata_path, copy, reverse=False):
    """用 concat demuxer 把 files 写成 out_path。"""
    _write_concat_list(files, list_path)
    args = [ffmpeg, "-v", "error", "-y", "-f", "concat", "-safe", "0"]
    loops = max(0, int(loop_count or 0))
    if loops:
        args += ["-stream_loop", str(loops)]
    args += ["-i", list_path]
    if metadata_path:
        # 元数据作为第二个输入传入并用 -map_metadata 选中，命令行长度与 JSON 体积无关。
        args += ["-i", metadata_path, "-map_metadata", "1"]
    if copy:
        args += ["-c", "copy"]
    else:
        args += _encode_args(
            spec, crf, frame_rate,
            lead_video_filter="reverse" if reverse else None,
            lead_audio_filter="areverse" if reverse else None,
        )
    if spec.get("movflags"):
        args += ["-movflags", "+faststart+use_metadata_tags" if metadata_path else "+faststart"]
    args += [out_path]
    env = os.environ.copy()
    env.update(spec.get("env", {}))
    _run(args, env=env)


def _merge(ffmpeg, files, out_path, list_path, spec, crf, frame_rate,
           loop_count, metadata_path, copy_pref):
    """先试无损流拷贝，失败则打印告警并降级为重编码。"""
    if copy_pref:
        try:
            _concat(ffmpeg, files, out_path, list_path, spec, crf, frame_rate,
                    loop_count, metadata_path, True)
            return
        except RuntimeError as exc:
            print("[zyd232 JoinVideos] stream copy failed, falling back to re-encode.\n%s" % exc)
    _concat(ffmpeg, files, out_path, list_path, spec, crf, frame_rate,
            loop_count, metadata_path, False)


class zyd232_JoinVideos(io.ComfyNode):
    """Join Videos 节点：按输入顺序合并多段视频。

    两组输入都可自增加：``filenames`` 收字符串路径，``videos`` 收 VIDEO 对象。
    合并顺序为先 filenames 组、再 video 组，各自按槽位序号。
    """

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="zyd232_JoinVideos",
            display_name="Join Videos",
            category="zyd232 Nodes",
            description=(
                "Join multiple videos into one, in input order. Both input groups autogrow: "
                "'filenames' takes file paths (one per slot, or several separated by commas/newlines) "
                "and 'videos' takes VIDEO inputs; filenames are merged first, then videos. "
                "When every source already matches the target container and the quality is left "
                "untouched (crf = -1), the segments are joined with a lossless ffmpeg stream copy "
                "(falling back to a re-encode if the copy fails); otherwise the result is re-encoded "
                "with the selected format."
            ),
            search_aliases=["join videos", "merge videos", "concat videos", "combine videos",
                            "join saved videos", "MMH3 Join Saved Videos"],
            is_output_node=True,
            inputs=[
                io.Autogrow.Input("filenames", optional=True,
                    display_name="Filenames",
                    tooltip="Video file paths to merge. A slot may also hold several paths separated by commas or newlines.",
                    template=io.Autogrow.TemplatePrefix(
                        input=io.String.Input("filename", display_name="Filename",
                            tooltip="A video file path (absolute, or relative to the output/temp directory)"),
                        prefix="filename_", min=0, max=_MAX_SLOTS)),
                io.Autogrow.Input("videos", optional=True,
                    display_name="Videos",
                    tooltip="VIDEO inputs to merge, appended after the filenames group.",
                    template=io.Autogrow.TemplatePrefix(
                        input=io.Video.Input("video", display_name="Video",
                            tooltip="A ComfyUI VIDEO to merge"),
                        prefix="video_", min=0, max=_MAX_SLOTS)),
                io.String.Input("filename_prefix", default="zyd232_merged",
                    display_name="Filename Prefix",
                    tooltip="Output filename prefix. Supports date placeholders: the core style %date:yyyy-MM-dd%, or the shorthand %date / %time."),
                io.Float.Input("frame_rate", default=24.0, min=1.0, max=240.0, step=0.1,
                    display_name="Frame Rate",
                    tooltip="Frame rate used when re-encoding and reported in the preview. "
                            "A lossless stream copy keeps each source's own timing."),
                io.Combo.Input("format", options=list(_FORMATS.keys()), default=_DEFAULT_FORMAT,
                    display_name="Format", tooltip="Output container / codec"),
                io.Int.Input("crf", default=-1, min=-1, max=63, step=1,
                    display_name="Quality (CRF)",
                    tooltip="Lower is better quality and a bigger file. -1 keeps the quality untouched, "
                            "which enables the lossless stream-copy path. The usable range and the default "
                            "value depend on the selected format (0-51 for H.264/H.265, 0-63 for VP9/AV1; "
                            "ProRes ignores CRF)."),
                io.Boolean.Input("save_metadata", default=True,
                    display_name="Save Metadata", label_on="Yes", label_off="No",
                    tooltip="Embed the prompt / workflow metadata into the output container"),
                io.Boolean.Input("pingpong", default=False,
                    display_name="Pingpong", label_on="Yes", label_off="No",
                    tooltip="Append a reversed copy of the merged video (play forward, then backward). "
                            "The reversed half is re-encoded."),
                io.Int.Input("loop_count", default=0, min=0, max=100, step=1,
                    display_name="Loop Count",
                    tooltip="How many extra times to repeat the merged video (0 = play once)"),
                io.Boolean.Input("save_output", default=True,
                    display_name="Save Output", label_on="Yes", label_off="No",
                    tooltip="Save into the output directory. When off, the result goes to the temp directory."),
            ],
            outputs=[
                io.Custom("VHS_FILENAMES").Output("filenames", display_name="filenames"),
                io.Video.Output("video", display_name="video"),
            ],
        )

    @classmethod
    def execute(cls, filenames=None, videos=None, filename_prefix="zyd232_merged",
                frame_rate=24.0, format=_DEFAULT_FORMAT, crf=-1,
                save_metadata=True, pingpong=False, loop_count=0,
                save_output=True) -> io.NodeOutput:
        spec = _FORMATS.get(format) or _FORMATS[_DEFAULT_FORMAT]
        output_dir = folder_paths.get_output_directory()
        temp_dir = folder_paths.get_temp_directory()

        work_dir = os.path.join(temp_dir, "zyd232_joinvideos_" + uuid.uuid4().hex[:8])
        os.makedirs(work_dir, exist_ok=True)
        try:
            sources = cls._collect_sources(filenames, videos, [output_dir, temp_dir], work_dir)
            if not sources:
                raise ValueError("Join Videos: no input videos were provided.")

            ffmpeg = _find_ffmpeg()
            list_path = os.path.join(work_dir, "concat_list.txt")
            metadata_path = None
            if spec.get("meta", True):
                metadata_path = _write_metadata_file(
                    os.path.join(work_dir, "metadata.txt"), cls.hidden, save_metadata)

            final_dir = output_dir if save_output else temp_dir
            prefix = _filename_tokens.prepare_path_prefix(
                filename_prefix, default="zyd232_merged")
            full_folder, name, counter, subfolder, _ = folder_paths.get_save_image_path(
                prefix, final_dir)
            out_path = os.path.join(full_folder, "%s_%05d.%s" % (name, counter, spec["ext"]))

            if pingpong:
                # 先把所有源并成一段（同封装则无损），再接上它的倒放版本。
                merged = os.path.join(work_dir, "merged.%s" % spec["ext"])
                _merge(ffmpeg, sources, merged, list_path, spec, crf, frame_rate, 0, None,
                       _can_stream_copy(sources, spec, crf, ignore_crf=True))
                reversed_path = os.path.join(work_dir, "reversed.%s" % spec["ext"])
                _concat(ffmpeg, [merged], reversed_path, list_path, spec, crf, frame_rate,
                        0, None, False, reverse=True)
                # 两段同封装，最终拼接可无损；loop 与元数据在这一步生效。
                _merge(ffmpeg, [merged, reversed_path], out_path, list_path, spec, crf,
                       frame_rate, loop_count, metadata_path, True)
            else:
                _merge(ffmpeg, sources, out_path, list_path, spec, crf, frame_rate,
                       loop_count, metadata_path, _can_stream_copy(sources, spec, crf))
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

        folder_type = io.FolderType.output if save_output else io.FolderType.temp
        return io.NodeOutput(
            (save_output, [out_path]),
            InputImpl.VideoFromFile(out_path),
            ui=ui.PreviewVideo([ui.SavedResult(os.path.basename(out_path), subfolder, folder_type)]),
        )

    @classmethod
    def _collect_sources(cls, filenames, videos, search_dirs, work_dir):
        """把两组 autogrow 输入按顺序摊平成一组本地文件路径。"""
        sources = []

        slots = sorted((filenames or {}).items(), key=lambda item: _parse_slot_index(item[0]))
        for _key, value in slots:
            if value is None:
                continue
            for raw in str(value).replace("\n", ",").replace("\r", ",").split(","):
                raw = raw.strip()
                if raw:
                    sources.append(_resolve_path(raw, search_dirs))

        slots = sorted((videos or {}).items(), key=lambda item: _parse_slot_index(item[0]))
        for _key, video in slots:
            if video is not None:
                sources.append(cls._video_to_path(video, work_dir))

        return sources

    @staticmethod
    def _video_to_path(video, work_dir):
        """VIDEO -> 本地文件路径；内存中的视频先落到工作目录。"""
        source = video.get_stream_source() if hasattr(video, "get_stream_source") else video
        if isinstance(source, str):
            if not os.path.isfile(source):
                raise FileNotFoundError("Join Videos: video file not found: %s" % source)
            return source
        if isinstance(source, (bytes, bytearray)):
            source = BytesIO(source)
        if hasattr(source, "read"):
            # 容器格式交给 ffmpeg 按内容探测，扩展名仅作占位。
            dump = os.path.join(work_dir, "input_%s.mp4" % uuid.uuid4().hex[:8])
            with open(dump, "wb") as handle:
                handle.write(source.read())
            return dump
        raise TypeError("Join Videos: unsupported video source: %r" % type(video))
