import os.path
import folder_paths
import datetime
import shutil
import random
import json
import numpy as np
from PIL.PngImagePlugin import Image, PngInfo

def generate_random_name(prefix:str, suffix:str, length:int) -> str:
    name = ''.join(random.choice("abcdefghijklmnopqrstupvxyz1234567890") for x in range(length))
    return prefix + name + suffix


def generate_random_name(prefix:str, suffix:str, length:int) -> str:
    name = ''.join(random.choice("abcdefghijklmnopqrstupvxyz1234567890") for x in range(length))
    return prefix + name + suffix


class zyd232_SavePreviewImages:

    def __init__(self):
        self.output_dir = folder_paths.get_output_directory()
        self.type = "output"
        self.prefix_append = ""
        self.compress_level = 4

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "save_image": ("BOOLEAN", {"default": True}),
                "save_workflow_as_json": ("BOOLEAN", {"default": False}),
                "preview": ("BOOLEAN", {"default": True}),
                "format": (["png", "jpg"],),
                "quality": ("INT", {"default": 85, "min": 0, "max": 100, "step": 1}),
                "meta_data_png": ("BOOLEAN", {"default": True}),
                "custom_path": ("STRING", {"default": "", "label": "Custom Path"}),
                "filename_prefix": ("STRING", {"default": "ComfyUI_", "label": "Filename Prefix"}),
                "timestamp": (["second", "millisecond", "None"],),
            },
            "hidden": {
                "prompt": "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO"
            }
        }

    RETURN_TYPES = ()
    OUTPUT_NODE = True
    FUNCTION = "save_image"
    CATEGORY = "zyd232 Nodes"
    NAME = "Save Preview Images"

    def save_image(self, images, custom_path, filename_prefix,
                        timestamp, format, quality, meta_data_png,
                        save_workflow_as_json, preview, save_image, prompt=None, extra_pnginfo=None):

        now = datetime.datetime.now()
        custom_path = custom_path.replace("%date", now.strftime("%Y-%m-%d"))
        custom_path = custom_path.replace("%time", now.strftime("%H-%M-%S"))
        filename_prefix = filename_prefix.replace("%date", now.strftime("%Y-%m-%d"))
        filename_prefix = filename_prefix.replace("%time", now.strftime("%H-%M-%S"))
        filename_prefix += self.prefix_append
        full_output_folder, filename, counter, subfolder, filename_prefix = folder_paths.get_save_image_path(filename_prefix, self.output_dir, images[0].shape[1], images[0].shape[0])
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

        return { "ui": { "images": results } }


NODE_CLASS_MAPPINGS = {
    "zyd232_SavePreviewImages": zyd232_SavePreviewImages
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "zyd232_SavePreviewImages": "Save Preview Images"
}
