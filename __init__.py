import importlib.util
import os

from comfy_api.latest import ComfyExtension, io

# 让 ComfyUI 自动加载此插件根目录下的 web 文件夹
WEB_DIRECTORY = "./web"

_NODES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nodes")


def _load_node_module(filename: str):
    """从 nodes/ 目录按文件路径加载节点模块（nodes 目录不是包）。"""
    module_path = os.path.join(_NODES_DIR, filename)
    module_name = "zyd232_nodes_" + os.path.splitext(filename)[0]
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_llm_module = _load_node_module("LLMGeneratorV3.py")
_llm_unload_module = _load_node_module("LLMUnload.py")
_images_module = _load_node_module("ImagesPixelsCompare.py")
_mask_module = _load_node_module("MaskBatchBlend.py")
_save_module = _load_node_module("SavePreviewImages.py")
_merge_lora_module = _load_node_module("MergeLoraStacks.py")

zyd232_LLMGeneratorV3 = _llm_module.zyd232_LLMGeneratorV3
zyd232_LLMUnload = _llm_unload_module.zyd232_LLMUnload
zyd232_ImagesPixelsCompare = _images_module.zyd232_ImagesPixelsCompare
zyd232_MaskBatchBlend = _mask_module.zyd232_MaskBatchBlend
zyd232_SavePreviewImages = _save_module.zyd232_SavePreviewImages
zyd232_MergeLoraStacks = _merge_lora_module.zyd232_MergeLoraStacks


class Zyd232Extension(ComfyExtension):
    """zyd232 Nodes 的 V3 扩展入口，注册所有节点。"""

    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [
            zyd232_LLMGeneratorV3,
            zyd232_LLMUnload,
            zyd232_ImagesPixelsCompare,
            zyd232_MaskBatchBlend,
            zyd232_SavePreviewImages,
            zyd232_MergeLoraStacks,
        ]


async def comfy_entrypoint() -> Zyd232Extension:
    return Zyd232Extension()
