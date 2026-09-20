"""WhaleTrans Latent Resolution：从 latent 中提取分辨率，兼容 H3 的 NestedTensor（视频+音频打包）和普通 4D/5D latent。"""

import torch
from comfy.nested_tensor import NestedTensor


class WhaleTransLatentResolution:
    """从 latent 提取 width/height，支持 H3 NestedTensor 视频 latent。"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "latent": ("LATENT",),
            }
        }

    RETURN_TYPES = ("INT", "INT")
    RETURN_NAMES = ("width", "height")
    FUNCTION = "execute"
    CATEGORY = "WhaleTrans"

    def execute(self, latent):
        samples = latent.get("samples")
        if samples is None:
            raise ValueError("latent 中没有 samples 字段")

        # H3 视频 latent：NestedTensor((video, audio))，video 是 5D (B,C,T,H,W)
        if isinstance(samples, NestedTensor):
            parts = samples.decompose()
            video = parts[0]
            height = int(video.shape[-2])
            width = int(video.shape[-1])
        elif isinstance(samples, torch.Tensor):
            # 普通 latent：4D (B,C,H,W) 或 5D (B,C,T,H,W)
            height = int(samples.shape[-2])
            width = int(samples.shape[-1])
        else:
            raise ValueError(f"不支持的 latent 类型: {type(samples)}")

        print(f"[WhaleTrans Latent Resolution] {width}x{height}")
        return (width, height)
