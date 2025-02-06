import torch

class zyd232_ImagesPixelsCompare:
    # 图片对比节点：比较两张图片是否完全相同
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image1": ("IMAGE",),
                "image2": ("IMAGE",),
                "if_same_output": ("BOOLEAN", {
                    "default": True,
                    "name": "If same output:",
                }),
            },
        }

    RETURN_TYPES = ("BOOLEAN",)
    FUNCTION = "process"
    CATEGORY = "zyd232 Nodes"
    NAME = "Images Pixels Compare"

    def process(self, image1, image2, if_same_output):
        # 确保两张图片尺寸相同
        if image1.shape != image2.shape:
            # 图片尺寸不同时，根据开关状态返回
            return (False if if_same_output else True,)
        
        # ComfyUI中的图片格式是 torch.Tensor
        # 直接比较所有像素值是否相同
        is_identical = torch.all(torch.eq(image1, image2)).item()
        
        # 根据开关状态返回结果
        return (is_identical,) if if_same_output else (not is_identical,)

NODE_CLASS_MAPPINGS = {
    "zyd232 ImagesPixelsCompare": zyd232_ImagesPixelsCompare
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "zyd232 ImagesPixelsCompare": "Images Pixels Compare"
}