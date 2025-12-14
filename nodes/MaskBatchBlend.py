import torch

class zyd232_MaskBatchBlend:
    # Mask混合节点：将多个Mask合并（叠加效果）为一个Mask
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "masks": ("MASK",),
                "operation": (["add", "max", "average"],),
            },
        }

    RETURN_TYPES = ("MASK",)
    FUNCTION = "blend_masks"
    CATEGORY = "zyd232 Nodes"
    NAME = "Mask Batch Blend"

    def blend_masks(self, masks, operation):
        
        if masks.dim() == 2:
            # 如果是2D张量，添加batch维度
            masks = masks.unsqueeze(0)
        elif masks.dim() == 4:
            # 如果是4D张量 (batch_size, 1, height, width)，去掉通道维度
            if masks.shape[1] == 1:
                masks = masks.squeeze(1)
            else:
                raise ValueError(f"Unexpected mask shape: {masks.shape}. Expected (batch, height, width) or (batch, 1, height, width)")
        
        batch_size = masks.shape[0]
        
        if batch_size == 0:
            # 如果没有mask，返回全零mask
            height, width = masks.shape[1], masks.shape[2]
            result = torch.zeros((1, height, width), dtype=torch.float32)
            return (result,)
        
        if batch_size == 1:
            # 如果只有一个mask，直接返回
            result = masks
        else:
            # 多个mask进行合并
            if operation == "add":
                # 叠加效果：将所有mask相加
                result = torch.sum(masks, dim=0, keepdim=True)
            elif operation == "max":
                # 取最大值：每个位置取所有mask中的最大值
                result, _ = torch.max(masks, dim=0, keepdim=True)
            elif operation == "average":
                # 平均值：所有mask的平均值
                result = torch.mean(masks, dim=0, keepdim=True)
            else:
                raise ValueError(f"Unknown operation: {operation}")
        
        return (result,)

NODE_CLASS_MAPPINGS = {
    "zyd232 MaskBatchBlend": zyd232_MaskBatchBlend
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "zyd232 MaskBatchBlend": "Mask Batch Blend"
}
