import torch
from comfy_api.latest import io


class zyd232_ImagesPixelsCompare(io.ComfyNode):
    """图片对比节点：比较两张图片是否完全相同"""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="zyd232 ImagesPixelsCompare",
            display_name="Images Pixels Compare",
            category="zyd232 Nodes",
            description="Compare two images at the pixel level to check whether they are exactly the same.",
            inputs=[
                io.Image.Input("image1", display_name="Image 1",
                    tooltip="First image to compare"),
                io.Image.Input("image2", display_name="Image 2",
                    tooltip="Second image to compare"),
                io.Boolean.Input("if_same_output", default=True,
                    display_name="If Same Output", label_on="Yes", label_off="No",
                    tooltip="When true, outputs true if the images are identical; when false, inverts the logic"),
            ],
            outputs=[
                io.Boolean.Output(display_name="Result"),
            ],
        )

    @classmethod
    def execute(cls, image1, image2, if_same_output) -> io.NodeOutput:
        # 确保两张图片尺寸相同
        if image1.shape != image2.shape:
            # 图片尺寸不同时，根据开关状态返回
            return io.NodeOutput(False if if_same_output else True)

        # ComfyUI中的图片格式是 torch.Tensor
        # 直接比较所有像素值是否相同
        is_identical = torch.all(torch.eq(image1, image2)).item()

        # 根据开关状态返回结果
        return io.NodeOutput(is_identical if if_same_output else (not is_identical))
