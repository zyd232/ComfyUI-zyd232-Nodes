import re

from comfy_api.latest import io


class zyd232_MergeLoraStacks(io.ComfyNode):
    """Merge LoRA Stacks 节点：将多个 lora_stack 输入合并为一个 lora_stack 输出。

    左侧的 lora_stack 输入为动态输入（node API V3 的 Autogrow），可动态增加。
    合并时按槽位顺序拼接各输入中的 LoRA 条目，并过滤掉 strength_model == 0 的条目。
    """

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="zyd232 MergeLoraStacks",
            display_name="Merge LoRA Stacks",
            category="zyd232 Nodes",
            description=(
                "Merge multiple lora_stack inputs into a single lora_stack output. "
                "The left-side lora_stack inputs are dynamic (Autogrow) and can be "
                "added/removed freely. Entries with strength_model == 0 are filtered out."
            ),
            inputs=[
                io.Autogrow.Input("lora_stacks", optional=True,
                    template=io.Autogrow.TemplatePrefix(
                        input=io.Custom("LORA_STACK").Input(
                            "lora_stack",
                            display_name="LoRA Stack",
                            tooltip="A lora_stack to merge into the output (list of (lora_name, strength_model, strength_clip) tuples)"),
                        prefix="lora_stack_", min=0, max=100)),
            ],
            outputs=[
                io.Custom("LORA_STACK").Output(display_name="lora_stack"),
            ],
        )

    @staticmethod
    def _parse_index(key):
        """Extract the trailing integer from an autogrow key like 'lora_stack_3'."""
        m = re.search(r"_(\d+)\s*$", str(key))
        if m:
            return int(m.group(1))
        return -1

    @staticmethod
    def _entry_strength_model(entry):
        """Return the strength_model of a lora_stack entry.

        Supports both the legacy tuple format ``(lora_name, strength_model, strength_clip)``
        and the dict format ``{"lora_name": ..., "strength_model": ...}``.
        """
        if isinstance(entry, dict):
            return entry.get("strength_model", 1.0)
        if isinstance(entry, (tuple, list)):
            if len(entry) >= 2:
                return entry[1]
            return 1.0
        return 1.0

    @classmethod
    def execute(cls, lora_stacks=None) -> io.NodeOutput:
        """Merge all incoming lora_stacks into a single list of LoRA entries.

        ``lora_stacks`` is a dict keyed by the autogrow slot names
        (lora_stack_0, lora_stack_1, ...). Each value is a lora_stack (a list of
        (lora_name, strength_model, strength_clip) tuples) or None.
        """
        merged = []

        if lora_stacks:
            # Sort slots by their trailing index so lora_stack_0 always comes first.
            slots = sorted(lora_stacks.items(), key=lambda item: cls._parse_index(item[0]))
            for _key, stack in slots:
                if stack is None:
                    continue
                for entry in stack:
                    # Filter out entries with strength_model == 0.
                    if cls._entry_strength_model(entry) == 0:
                        continue
                    merged.append(entry)

        return io.NodeOutput(merged)
