import torch
from comfy_api.latest import io


class zyd232_MaskBatchBlend(io.ComfyNode):
    """Mask混合节点：将多个Mask合并（叠加效果）为一个Mask"""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="zyd232 MaskBatchBlend",
            display_name="Mask Batch Blend",
            category="zyd232 Nodes",
            description="Blend multiple masks together into a single mask.",
            inputs=[
                io.Mask.Input("masks", display_name="Masks",
                    tooltip="Masks to blend (supports batches)"),
                io.Combo.Input("operation", options=["add", "max", "average"],
                    display_name="Operation",
                    tooltip="Blend operation: add, max, or average"),
            ],
            outputs=[
                io.Mask.Output(display_name="Result"),
            ],
        )

    @classmethod
    def execute(cls, masks, operation) -> io.NodeOutput:
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
            return io.NodeOutput(result)

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

        return io.NodeOutput(result)
