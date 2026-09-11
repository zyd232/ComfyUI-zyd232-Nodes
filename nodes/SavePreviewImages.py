import os.path
import folder_paths
import datetime
import importlib.util as _importlib_util
import random
import json
import sys
import numpy as np
from PIL.PngImagePlugin import Image, PngInfo
from comfy_api.latest import io

# nodes/ 目录不是 Python 包（模块按文件路径在 __init__.py 中加载），因此这里按
# 文件路径加载共享模块并缓存到 sys.modules，保证与其他节点共用同一个实例。
if "zyd232_filename_tokens" not in sys.modules:
    _TOKENS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "filename_tokens.py")
    _tokens_spec = _importlib_util.spec_from_file_location("zyd232_filename_tokens", _TOKENS_PATH)
    _tokens_mod = _importlib_util.module_from_spec(_tokens_spec)
    sys.modules["zyd232_filename_tokens"] = _tokens_mod
    _tokens_spec.loader.exec_module(_tokens_mod)
_filename_tokens = sys.modules["zyd232_filename_tokens"]


def generate_random_name(prefix: str, suffix: str, length: int) -> str:
    name = ''.join(random.choice("abcdefghijklmnopqrstupvxyz1234567890") for x in range(length))
    return prefix + name + suffix


class zyd232_SavePreviewImages(io.ComfyNode):
    """保存预览图片节点"""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="zyd232_SavePreviewImages",
            display_name="Save Preview Images",
            category="zyd232 Nodes",
            description="Save images to the output directory, optionally generating previews and workflow JSON.",
            is_output_node=True,
            inputs=[
                io.Image.Input("images", display_name="Images",
                    tooltip="Images to save"),
                io.Boolean.Input("save_image", default=True,
                    display_name="Save Image", label_on="Yes", label_off="No",
                    tooltip="Whether to save the images to disk"),
                io.Boolean.Input("save_workflow_as_json", default=False,
                    display_name="Save Workflow as JSON", label_on="Yes", label_off="No",
                    tooltip="Whether to save the workflow as a JSON file"),
                io.Boolean.Input("preview", default=True,
                    display_name="Preview", label_on="Yes", label_off="No",
                    tooltip="Whether to generate preview images"),
                io.Combo.Input("format", options=["png", "jpg"],
                    display_name="Format", tooltip="Output image format"),
                io.Int.Input("quality", default=85, min=0, max=100, step=1,
                    display_name="Quality", tooltip="Image quality (jpg only)"),
                io.Boolean.Input("meta_data_png", default=True,
                    display_name="Write PNG Metadata", label_on="Yes", label_off="No",
                    tooltip="Whether to write prompt info into PNG metadata"),
                io.String.Input("custom_path", default="",
                    display_name="Custom Path",
                    tooltip="Custom save path. Supports date placeholders: the core style %date:yyyy-MM-dd%, or the shorthand %date / %time."),
                io.String.Input("filename_prefix", default="ComfyUI_",
                    display_name="Filename Prefix",
                    tooltip="Filename prefix. Supports date placeholders: the core style %date:yyyy-MM-dd%, or the shorthand %date / %time."),
                io.Combo.Input("timestamp", options=["second", "millisecond", "None"],
                    display_name="Timestamp", tooltip="Filename timestamp mode"),
            ],
        )

    @classmethod
    def execute(cls, images, custom_path, filename_prefix,
                timestamp, format, quality, meta_data_png,
                save_workflow_as_json, preview, save_image) -> io.NodeOutput:
        # V3 API: prompt/extra_pnginfo 通过 cls.hidden 注入，而非 execute 参数
        prompt = getattr(cls.hidden, "prompt", None)
        extra_pnginfo = getattr(cls.hidden, "extra_pnginfo", None)
        output_dir = folder_paths.get_output_directory()
        now = datetime.datetime.now()
        # 占位符展开与文件名清洗统一交给共享模块（与 Join Videos 同一实现）：
        # 既支持核心写法 %date:yyyy-MM-dd%，也支持本插件的简写 %date / %time，
        # 全部在后端完成，因此界面 / API / MCP 三种提交途径行为一致。
        # custom_path 可能是绝对路径（盘符含 ':'），所以只展开占位符、不做清洗。
        custom_path = _filename_tokens.expand_placeholders(custom_path, now=now)
        filename_prefix = _filename_tokens.prepare_path_prefix(
            filename_prefix, now=now, default="ComfyUI", label="filename_prefix")
        full_output_folder, filename, counter, subfolder, filename_prefix = folder_paths.get_save_image_path(filename_prefix, output_dir, images[0].shape[1], images[0].shape[0])
        results = list()
        temp_dir = folder_paths.get_temp_directory()

        for image in images:
            i = 255. * image.cpu().numpy()
            img = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8))

            metadata = None
            if meta_data_png:
                metadata = PngInfo()
                if prompt is not None:
                    metadata.add_text("prompt", json.dumps(prompt))
                if extra_pnginfo is not None:
                    for x in extra_pnginfo:
                        metadata.add_text(x, json.dumps(extra_pnginfo[x]))

            if timestamp == "millisecond":
                file = f'{filename}_{now.strftime("%Y-%m-%d_%H-%M-%S-%f")[:-3]}'
            elif timestamp == "second":
                file = f'{filename}_{now.strftime("%Y-%m-%d_%H-%M-%S")}'
            else:
                file = f'{filename}_{counter:05}'

            if preview:
                if not os.path.isdir(temp_dir):
                    try:
                        os.makedirs(temp_dir)
                    except Exception as e:
                        print(e)
                if timestamp == "millisecond":
                    preview_filename = f'{filename}_preview_{now.strftime("%Y-%m-%d_%H-%M-%S-%f")[:-3]}_{counter:05}.{format}'
                elif timestamp == "second":
                    preview_filename = f'{filename}_preview_{now.strftime("%Y-%m-%d_%H-%M-%S")}_{counter:05}.{format}'
                else:
                    preview_filename = generate_random_name('saveimage_preview_', f'_temp_{counter:05}', 16) + f'.{format}'
                try:
                    if meta_data_png:
                        img.save(os.path.join(temp_dir, preview_filename), pnginfo=metadata)
                    else:
                        img.save(os.path.join(temp_dir, preview_filename))
                except Exception as e:
                    print(e)

            if custom_path != "":
                # 将 filename_prefix 中的子目录拼接到 custom_path 后面
                if subfolder:
                    custom_path = os.path.join(custom_path, subfolder)
                if not os.path.exists(custom_path):
                    try:
                        os.makedirs(custom_path)
                    except Exception as e:
                        print(f"Error: unable to create temporary folder. {e}")
                        raise FileNotFoundError(f"cannot create custom_path {custom_path}, {e}")

                full_output_folder = os.path.normpath(custom_path)

            while os.path.isfile(os.path.join(full_output_folder, f"{file}.{format}")):
                counter += 1
                if timestamp == "millisecond":
                    file = f'{filename}_{now.strftime("%Y-%m-%d_%H-%M-%S-%f")[:-3]}_{counter:05}'
                elif timestamp == "second":
                    file = f'{filename}_{now.strftime("%Y-%m-%d_%H-%M-%S")}_{counter:05}'
                else:
                    file = f"{filename}_{counter:05}"

            image_file_name = os.path.join(full_output_folder, f"{file}.{format}")
            json_file_name = os.path.join(full_output_folder, f"{file}.json")

            if save_image:  # 只在保存开关开启时执行保存操作
                if format == "png":
                    img.save(image_file_name, pnginfo=metadata, compress_level=(100 - quality) // 10)
                else:
                    if img.mode == "RGBA":
                        img = img.convert("RGB")
                    img.save(image_file_name, quality=quality)

            if save_workflow_as_json:  # 独立检查JSON保存选项
                try:
                    workflow = (extra_pnginfo or {}).get('workflow')
                    if workflow is None:
                        print('No workflow found, skipping saving of JSON')
                    else:
                        with open(f'{json_file_name}', 'w', encoding='utf-8') as workflow_file:
                            json.dump(workflow, workflow_file, ensure_ascii=False, indent=4)
                except Exception as e:
                    print(f'Failed to save workflow as json due to: {e}')

            if preview:
                results.append({
                    "filename": preview_filename,
                    "subfolder": "",
                    "type": "temp"
                })

            counter += 1

        return io.NodeOutput(ui={"images": results})
