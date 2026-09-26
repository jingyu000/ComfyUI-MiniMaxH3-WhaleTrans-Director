# -*- coding: utf-8 -*-
"""MiniMax H3 专用 latent 空间缩放节点，支持 NestedTensor（视频+音频打包）。"""
import torch
import torch.nn.functional as F
import node_helpers
from comfy.nested_tensor import NestedTensor
from .experimental_latent_guide import _build_direct_latent_keyframe

VAE_DOWNSAMPLE = 16
UPSCALE_METHODS = ["nearest-exact", "bilinear", "area", "bicubic", "bislerp"]


def _resize_video_5d(video, target_h, target_w, method):
    B, C, T, H, W = video.shape
    video_bt = video.permute(0, 2, 1, 3, 4).reshape(B * T, C, H, W)
    if method == "nearest-exact":
        up = F.interpolate(video_bt, size=(target_h, target_w), mode="nearest-exact")
    elif method == "area":
        up = F.interpolate(video_bt, size=(target_h, target_w), mode="area")
    elif method == "bicubic":
        up = F.interpolate(video_bt, size=(target_h, target_w), mode="bicubic", align_corners=False)
    else:
        up = F.interpolate(video_bt, size=(target_h, target_w), mode="bilinear", align_corners=False)
    up = up.reshape(B, T, C, target_h, target_w).permute(0, 2, 1, 3, 4).contiguous()
    return up


def _center_crop(video, target_h, target_w):
    B, C, T, H, W = video.shape
    old_aspect = W / H
    new_aspect = target_w / target_h
    if old_aspect > new_aspect:
        new_W = int(round(H * new_aspect))
        x_start = (W - new_W) // 2
        return video[:, :, :, :, x_start:x_start + new_W]
    elif old_aspect < new_aspect:
        new_H = int(round(W / new_aspect))
        y_start = (H - new_H) // 2
        return video[:, :, :, y_start:y_start + new_H, :]
    return video


class H3LatentShrink:
    """MiniMax H3 专用 latent 空间缩放节点，支持 ComfyUI NestedTensor（视频+音频打包）"""
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "samples": ("LATENT",),
                "width": ("INT", {"default": 960, "min": 64, "max": 8192, "step": 8}),
                "height": ("INT", {"default": 544, "min": 64, "max": 8192, "step": 8}),
                "upscale_method": (UPSCALE_METHODS, {"default": "bilinear"}),
                "crop": (["disabled", "center"], {"default": "disabled"}),
            }
        }
    RETURN_TYPES = ("LATENT",)
    FUNCTION = "upscale"
    CATEGORY = "MiniMax H3"

    def upscale(self, samples, width, height, upscale_method, crop):
        s = dict(samples)
        latent = s["samples"]
        target_h = height // VAE_DOWNSAMPLE
        target_w = width // VAE_DOWNSAMPLE
        if isinstance(latent, NestedTensor):
            parts = latent.unbind()
            video = parts[0]
            audio = parts[1] if len(parts) > 1 else None
            if crop == "center":
                video = _center_crop(video, target_h, target_w)
            orig_dtype = video.dtype
            video = _resize_video_5d(video.float(), target_h, target_w, upscale_method).to(orig_dtype)
            if audio is not None:
                s["samples"] = NestedTensor([video, audio])
            else:
                s["samples"] = video
            print(f"[H3 Scale] NestedTensor 视频 {parts[0].shape[-1]}x{parts[0].shape[-2]}"
                  f" -> {target_w}x{target_h} | 音频保留 | {upscale_method}")
        else:
            orig_dtype = latent.dtype
            was_4d = (latent.ndim == 4)
            if was_4d:
                latent = latent.unsqueeze(2)
            if crop == "center":
                latent = _center_crop(latent, target_h, target_w)
            latent = _resize_video_5d(latent.float(), target_h, target_w, upscale_method).to(orig_dtype)
            if was_4d:
                latent = latent.squeeze(2)
            s["samples"] = latent
            print(f"[H3 Scale] 普通latent -> {target_w}x{target_h} | {upscale_method}")
        return (s,)


class H3LatentResolution:
    """从 H3 latent（NestedTensor 或普通 tensor）中读取分辨率，输出像素尺寸。兼容 4D/5D latent。"""
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "samples": ("LATENT",),
            }
        }
    RETURN_TYPES = ("INT", "INT")
    RETURN_NAMES = ("width", "height")
    FUNCTION = "get_resolution"
    CATEGORY = "MiniMax H3"

    def get_resolution(self, samples):
        latent = samples["samples"]
        if isinstance(latent, NestedTensor):
            parts = latent.unbind()
            video = parts[0]
            latent_h = video.shape[-2]
            latent_w = video.shape[-1]
        else:
            latent_h = latent.shape[-2]
            latent_w = latent.shape[-1]
        width = latent_w * VAE_DOWNSAMPLE
        height = latent_h * VAE_DOWNSAMPLE
        return (width, height)


class H3HighRefineGuide:
    """H3 二段式采样专用引导节点：把 3D 放大后的 latent 作为 direct latent guide 注入条件，
    同时输出同尺寸空 AV latent 作为二次采样初值。解决放大后 latent 与条件尺寸不匹配的问题。"""
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "source_latent": ("LATENT",),
                "positive": ("CONDITIONING",),
                "guide_frames": ("INT", {"default": 22, "min": 1, "max": 362, "step": 1}),
            }
        }
    RETURN_TYPES = ("CONDITIONING", "LATENT")
    RETURN_NAMES = ("positive", "latent")
    FUNCTION = "build_guide"
    CATEGORY = "MiniMax H3"

    def build_guide(self, source_latent, positive, guide_frames):
        src = source_latent["samples"]
        if isinstance(src, NestedTensor):
            parts = src.unbind()
            video = parts[0]
            # target_latent 直接用 source_latent（尺寸一致，保留一次采样数据，不创建空latent）
            target_latent = source_latent
            # 构建 direct latent guide（target=source本身, source=放大后的latent）
            keyframe, details = _build_direct_latent_keyframe(
                target_latent, source_latent, guide_frames, frame_idx=0, include_audio=False
            )
            keyframes = list(positive[0][1].get("minimax_keyframes", []))
            keyframes.append(keyframe)
            conditioned = node_helpers.conditioning_set_values(
                positive, {"minimax_keyframes": keyframes}
            )
            print(f"[H3 HighRefineGuide] latent尺寸 {video.shape[-1]}x{video.shape[-2]} "
                  f"(latent) | 引导 {details['frames']}帧/{details['video_tokens']}tokens "
                  f"| 起始帧 {details['frame_idx']} | 透传一次采样数据")
            # latent 输出直接透传 source_latent，保留一次采样的全部数据
            return (conditioned, source_latent)
        else:
            # 普通 latent 降级处理：直接透传，不注入引导
            print(f"[H3 HighRefineGuide] 普通latent（非NestedTensor），直接透传，未注入引导")
            return (positive, source_latent)
