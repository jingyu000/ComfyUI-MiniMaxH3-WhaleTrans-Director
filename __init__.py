"""MiniMax H3 Timeline Director for ComfyUI."""
from .minimax_h3_timeline_director import (
    MiniMaxH3TimelineDirector,
    MiniMaxH3TimelineEncoder,
    MiniMaxH3OmniPromptBridge,
    MiniMaxH3TimelinePlanner,
)
from .minimax_h3_finite_segments import (
    MiniMaxH3FiniteLatentContinuation,
    MiniMaxH3FiniteAudioTrimTail,
    MiniMaxH3FiniteOutputTrim,
    MiniMaxH3FiniteSegmentFinalize,
    MiniMaxH3FiniteSegmentSampler,
    MiniMaxH3LockedAudioSlice,
    MiniMaxH3LockAudioLatent,
    MiniMaxH3LockedAudioMaster,
)
from .minimax_h3_loop import (
    MiniMaxH3LoopPromptSelector,
    MiniMaxH3LoopLatentGuide,
    MiniMaxH3LoopSegmentFinalize,
)
from .h3_latent_scale import H3LatentShrink, H3LatentResolution, H3HighRefineGuide
from .whaletrans_loop import WhaleTransLoop, WhaleTransLoopVariable
try:
    from .whaletrans_savevideo import WhaleTransAccumulateSaveVideo
    _HAS_SAVEVIDEO = True
except Exception:
    _HAS_SAVEVIDEO = False

NODE_CLASS_MAPPINGS = {
    "MiniMaxH3TimelineDirector": MiniMaxH3TimelineDirector,
    "MiniMaxH3TimelinePlanner": MiniMaxH3TimelinePlanner,
    "MiniMaxH3TimelineEncoder": MiniMaxH3TimelineEncoder,
    "MiniMaxH3OmniPromptBridge": MiniMaxH3OmniPromptBridge,
    "MiniMaxH3FiniteSegmentSampler": MiniMaxH3FiniteSegmentSampler,
    "MiniMaxH3FiniteAudioTrimTail": MiniMaxH3FiniteAudioTrimTail,
    "MiniMaxH3FiniteOutputTrim": MiniMaxH3FiniteOutputTrim,
    "MiniMaxH3FiniteLatentContinuation": MiniMaxH3FiniteLatentContinuation,
    "MiniMaxH3FiniteSegmentFinalize": MiniMaxH3FiniteSegmentFinalize,
    "MiniMaxH3LockedAudioSlice": MiniMaxH3LockedAudioSlice,
    "MiniMaxH3LockAudioLatent": MiniMaxH3LockAudioLatent,
    "MiniMaxH3LockedAudioMaster": MiniMaxH3LockedAudioMaster,
    "MiniMaxH3LoopPromptSelector": MiniMaxH3LoopPromptSelector,
    "MiniMaxH3LoopLatentGuide": MiniMaxH3LoopLatentGuide,
    "MiniMaxH3LoopSegmentFinalize": MiniMaxH3LoopSegmentFinalize,
    "H3LatentShrink": H3LatentShrink,
    "H3LatentResolution": H3LatentResolution,
    "H3HighRefineGuide": H3HighRefineGuide,
    "WhaleTransLoop": WhaleTransLoop,
    "WhaleTransLoopVariable": WhaleTransLoopVariable,
    # 旧节点名别名：兼容已有工作流，无需删除重连节点
    "Loop": WhaleTransLoop,
    "LoopVariable": WhaleTransLoopVariable,
}
if _HAS_SAVEVIDEO:
    NODE_CLASS_MAPPINGS["WhaleTransAccumulateSaveVideo"] = WhaleTransAccumulateSaveVideo
    NODE_CLASS_MAPPINGS["AccumulateSaveVideo"] = WhaleTransAccumulateSaveVideo
NODE_DISPLAY_NAME_MAPPINGS = {
    "MiniMaxH3TimelineDirector": "MiniMax H3 Timeline Director",
    "MiniMaxH3TimelinePlanner": "MiniMax H3 Material Planner",
    "MiniMaxH3TimelineEncoder": "MiniMax H3 Plan Encoder",
    "MiniMaxH3OmniPromptBridge": "MiniMax H3 Omni Media Prompt Bridge",
    "MiniMaxH3FiniteSegmentSampler": "MiniMax H3 Finite Segment Sampler",
    "MiniMaxH3FiniteAudioTrimTail": "MiniMax H3 Finite Audio Tail Trim (Internal)",
    "MiniMaxH3FiniteOutputTrim": "MiniMax H3 Finite Output Trim (Internal)",
    "MiniMaxH3FiniteLatentContinuation": "MiniMax H3 Finite Latent Continuation (Internal)",
    "MiniMaxH3FiniteSegmentFinalize": "MiniMax H3 Finite Segment Finalize (Internal)",
    "MiniMaxH3LockedAudioSlice": "MiniMax H3 Locked Audio Slice (Internal)",
    "MiniMaxH3LockAudioLatent": "MiniMax H3 Lock Audio Latent (Internal)",
    "MiniMaxH3LockedAudioMaster": "MiniMax H3 Locked Audio Master (Internal)",
    "MiniMaxH3LoopPromptSelector": "MiniMax H3 循环分段提示词",
    "MiniMaxH3LoopLatentGuide": "MiniMax H3 Latent 循环续段",
    "MiniMaxH3LoopSegmentFinalize": "MiniMax H3 循环片段去重",
    "H3LatentShrink": "H3 Latent 空间缩放",
    "H3LatentResolution": "H3 Latent 分辨率",
    "H3HighRefineGuide": "H3 HIGH 二次采样引导",
    "WhaleTransLoop": "WhaleTrans Loop",
    "WhaleTransLoopVariable": "WhaleTrans Loop Variable",
    "Loop": "Loop (WhaleTrans)",
    "LoopVariable": "Loop Variable (WhaleTrans)",
}
if _HAS_SAVEVIDEO:
    NODE_DISPLAY_NAME_MAPPINGS["WhaleTransAccumulateSaveVideo"] = "WhaleTrans Accumulate Save Video"
    NODE_DISPLAY_NAME_MAPPINGS["AccumulateSaveVideo"] = "Accumulate Save Video (WhaleTrans)"
WEB_DIRECTORY = "./js"
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
