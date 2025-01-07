import torch
import numpy as np

class ImageCompareNode:
    """图片对比节点：比较两张图片是否完全相同"""
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image1": ("IMAGE",),  # ComfyUI的图片格式
                "image2": ("IMAGE",),
            },
        }

    RETURN_TYPES = ("BOOLEAN",)
    FUNCTION = "process"
    CATEGORY = "zyd232-Nodes"

    def process(self, image1, image2):
        # 确保两张图片尺寸相同
        if image1.shape != image2.shape:
            return (False,)
        
        # ComfyUI中的图片格式是 torch.Tensor，
        # 格式为 (batch, height, width, channels)
        # 直接比较所有像素值是否相同
        is_identical = torch.all(torch.eq(image1, image2))
        
        return (bool(is_identical),)

# 注册节点
NODE_CLASS_MAPPINGS = {
    "ImageCompareNode": ImageCompareNode
}

# 显示名称映射
NODE_DISPLAY_NAME_MAPPINGS = {
    "ImageCompareNode": "Image Pixels Compare"
} 