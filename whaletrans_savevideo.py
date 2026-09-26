import os
import torch
import folder_paths
import json
import math
import numpy as np
from fractions import Fraction
from comfy.cli_args import args
from comfy_execution.graph_utils import GraphBuilder, is_link

# 与 WhaleTransLoop 共享的状态字典（Loop 节点负责第一次迭代时清理）
from .whaletrans_loop import _WHALE_LOOP_SAVE_STATES as ACCUMULATE_SAVE_VIDEO_STATES
from .whaletrans_loop import _WHALE_LATENT_CACHE


class WhaleTransAccumulateSaveVideo:
    """累积保存视频：每次迭代追加帧，最后一次完成编码。同时作为 expand 循环的触发节点。

    与原作者 prs-generic-loops 的 AccumulateSaveVideo 行为对齐：
    - 输入 VIDEO（CreateVideo 输出的 VideoFromComponents 对象），每次迭代追加帧
    - last=True 时完成编码并输出视频预览
    - 不同点：原作者用 projection 机制（替换核心文件），本实现用官方 expand 机制（独立插件）
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("*",),
                "filename_prefix": ("STRING", {"default": "video/ComfyUI"}),
                "format": ("STRING", {"default": "auto"}),
                "codec": ("STRING", {"default": "auto"}),
                "last": ("BOOLEAN", {"forceInput": True}),
            },
            "optional": {
                "flow_control": ("FLOW_CONTROL", {"rawLink": True}),
                "feedback_latent": ("LATENT",),
                "complete_audio": ("AUDIO",),
            },
            "hidden": {
                "dynprompt": "DYNPROMPT",
                "unique_id": "UNIQUE_ID",
                "prompt": "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO",
            },
        }

    RETURN_TYPES = ()
    OUTPUT_NODE = True
    FUNCTION = "execute"
    CATEGORY = "video"

    def _explore_dependencies(self, node_id, dynprompt, visited=None):
        """从 node_id 向上游递归探索所有依赖节点，返回 visited 集合（包含 node_id 自身）。
        只基于 link 关系收集，与 Set/Get 等任何靠全局字典通信的第三方节点无关。"""
        if visited is None:
            visited = set()
        if node_id in visited:
            return visited
        visited.add(node_id)
        node_info = dynprompt.get_node(node_id)
        if "inputs" not in node_info:
            return visited
        for v in node_info["inputs"].values():
            if is_link(v):
                self._explore_dependencies(v[0], dynprompt, visited)
        return visited

    def _get_state_key(self, dynprompt, unique_id):
        """用节点的 display_id 作为 state_key，确保所有迭代共享同一个视频编码器。
        展开图里副本的 override_display_id=原图节点 id，所以 display_id 在所有迭代间保持不变。"""
        if dynprompt is not None and hasattr(dynprompt, "get_display_node_id"):
            try:
                return str(dynprompt.get_display_node_id(unique_id))
            except Exception:
                pass
        return str(unique_id) if unique_id else "default"

    def _extract_components(self, video):
        """统一从各种视频类型中提取 images, audio, frame_rate。
        支持: VideoFromComponents(新版API, CreateVideo 输出), dict(旧版VIDEO), torch.Tensor(IMAGE), list。
        返回 (images, audio, frame_rate)"""
        # 新版 API: VideoFromComponents 有 get_components() 方法
        if hasattr(video, "get_components") and callable(video.get_components):
            components = video.get_components()
            images = components.images
            audio = components.audio
            frame_rate = float(components.frame_rate) if components.frame_rate else 24.0
            return images, audio, frame_rate
        # 旧版: dict 格式
        if isinstance(video, dict):
            return video.get("images"), video.get("audio"), video.get("frame_rate", 24.0)
        # IMAGE 张量或列表
        if isinstance(video, (torch.Tensor, list)):
            return video, None, 24.0
        return None, None, 24.0

    def _append_frames(self, state, video):
        """把当前迭代的视频帧追加到编码器。支持 VIDEO(dict)、VideoFromComponents(新版API)、IMAGE(tensor/list)。"""
        import av
        images, audio, _ = self._extract_components(video)
        if images is None:
            return

        if isinstance(images, torch.Tensor):
            if images.dim() == 4:
                images = [images[i] for i in range(images.shape[0])]
            else:
                images = [images]

        for image in images:
            if state["is_10bit"]:
                image = (image.float() * 65535).clamp(0, 65535).cpu().numpy().astype(np.uint16)
                frame = av.VideoFrame.from_ndarray(image, format="rgb48le")
            else:
                image = (image * 255).clamp(0, 255).byte().cpu().numpy()
                frame = av.VideoFrame.from_ndarray(image, format="rgb24")
            frame = frame.reformat(format=state["pix_fmt"])
            for packet in state["video_stream"].encode(frame):
                state["output"].mux(packet)
            state["frame_count"] += 1

        # 累积每段视频自带的音轨（如果没有指定 complete_audio）
        if audio is not None and state["complete_audio"] is None:
            state["audio_chunks"].append(audio["waveform"][0])

    def _finalize_video(self, state):
        """完成视频编码，返回 ui 预览（格式与官方 PreviewVideo.as_dict() 一致）。"""
        import av
        for packet in state["video_stream"].encode(None):
            state["output"].mux(packet)

        audio = state["complete_audio"]
        if audio is None and state["audio_chunks"]:
            audio = {
                "sample_rate": state["audio_sample_rate"],
                "waveform": torch.cat(state["audio_chunks"], dim=1).unsqueeze(0),
            }
        if state["audio_stream"] and audio is not None:
            waveform = audio["waveform"][0, :, :math.ceil((state["audio_sample_rate"] / state["frame_rate"]) * state["frame_count"])]
            layout = {1: "mono", 2: "stereo", 6: "5.1"}.get(waveform.shape[0], "stereo")
            frame = av.AudioFrame.from_ndarray(waveform.float().cpu().contiguous().numpy(), format="fltp", layout=layout)
            frame.sample_rate = state["audio_sample_rate"]
            frame.pts = 0
            for packet in state["audio_stream"].encode(frame):
                state["output"].mux(packet)
            for packet in state["audio_stream"].encode(None):
                state["output"].mux(packet)

        state["output"].close()
        return {"ui": {"images": [{"filename": state["file"], "subfolder": state["subfolder"], "type": "output"}], "animated": (True,)}}

    def _clear_latent_cache(self, state_key):
        """清理这个 SaveVideo 对应的所有全局 latent 缓存。"""
        prefix = f"latent_{state_key}_"
        for k in list(_WHALE_LATENT_CACHE.keys()):
            if k.startswith(prefix):
                del _WHALE_LATENT_CACHE[k]

    def execute(self, video, filename_prefix, format, codec, last,
                flow_control=None, feedback_latent=None, complete_audio=None,
                dynprompt=None, unique_id=None, prompt=None, extra_pnginfo=None):
        import av

        state_key = self._get_state_key(dynprompt, unique_id)
        state = ACCUMULATE_SAVE_VIDEO_STATES.get(state_key)

        # 运行隔离：用 dynprompt 对象 ID 区分不同次运行。
        # 每次点击"运行" ComfyUI 会创建新的 DynamicPrompt 对象，id 不同。
        # 中断后残留的 state 属于上一次运行（dynprompt_id 不同），自动清理并从零开始，
        # 确保每次运行都从第 1 段开始，不会继承上一次中断的位置。
        current_run_id = id(dynprompt) if dynprompt is not None else None
        if state is not None and state.get("run_id") != current_run_id:
            print(f"[WhaleTransSaveVideo] 检测到新运行（run_id={current_run_id}），"
                  f"清理上一次残留状态（旧 run_id={state.get('run_id')}），从第 1 段开始")
            try:
                state["output"].close()
            except Exception:
                pass
            ACCUMULATE_SAVE_VIDEO_STATES.pop(state_key, None)
            self._clear_latent_cache(state_key)
            state = None

        # 容错：旧工作流可能把 filename_prefix 的值映射到 format/codec（旧版节点没有这两个参数）
        # 传入非法值时自动 fallback 到 auto，避免节点被跳过
        if format not in ("auto", "mp4", "webm", "gif"):
            format = "auto"
        if codec not in ("auto", "h264", "h265", "vp9", "av1", "prores", "gif"):
            codec = "auto"
        # 第一次迭代：创建视频编码器
        if state is None:
            if format not in ("auto", "mp4"):
                raise ValueError("Only MP4 format is supported for now")
            if codec not in ("auto", "h264"):
                raise ValueError("Only H264 codec is supported for now")

            images, audio, frame_rate_val = self._extract_components(video)

            # 计算视频尺寸
            if images is None or (isinstance(images, torch.Tensor) and images.numel() == 0):
                width, height = 512, 512
            elif isinstance(images, torch.Tensor) and images.dim() == 4:
                _, height, width, _ = images.shape
            elif isinstance(images, list) and len(images) > 0:
                height, width = images[0].shape[:2]
            else:
                width, height = 512, 512

            full_output_folder, filename, counter, subfolder, _ = folder_paths.get_save_image_path(
                filename_prefix, folder_paths.get_output_directory(), width, height
            )
            ext = "mp4"
            file = f"{filename}_{counter:05}_.{ext}"
            path = os.path.join(full_output_folder, file)

            # 元数据
            metadata = None
            if not args.disable_metadata:
                metadata = {}
                if extra_pnginfo is not None:
                    metadata.update(extra_pnginfo)
                if prompt is not None:
                    metadata["prompt"] = prompt
                if not metadata:
                    metadata = None

            extra_kwargs = {"format": "mp4"} if format != "auto" else {}
            output = av.open(path, mode="w", options={"movflags": "use_metadata_tags"}, **extra_kwargs)
            if metadata is not None:
                for key, value in metadata.items():
                    output.metadata[key] = json.dumps(value)

            frame_rate = Fraction(round(frame_rate_val * 1000), 1000)

            # 位深检测
            is_10bit = False
            if images is not None and isinstance(images, torch.Tensor) and images.numel() > 0:
                is_10bit = images.dtype in (torch.int16, torch.float64) or (images.max() > 1.0)
            pix_fmt = "yuv420p10le" if is_10bit else "yuv420p"

            video_stream = output.add_stream("h264", rate=frame_rate)
            video_stream.width = width
            video_stream.height = height
            video_stream.pix_fmt = pix_fmt

            # 音频流（优先使用 complete_audio，否则使用每段累积的音频）
            audio_stream = None
            audio_sample_rate = 1
            active_audio = complete_audio or audio
            if active_audio is not None:
                audio_sample_rate = int(active_audio["sample_rate"])
                channels = active_audio["waveform"].shape[1]
                layout = {1: "mono", 2: "stereo", 6: "5.1"}.get(channels, "stereo")
                audio_stream = output.add_stream("aac", rate=audio_sample_rate, layout=layout)

            state = ACCUMULATE_SAVE_VIDEO_STATES[state_key] = {
                "path": path,
                "file": file,
                "subfolder": subfolder,
                "output": output,
                "video_stream": video_stream,
                "audio_stream": audio_stream,
                "audio_sample_rate": audio_sample_rate,
                "frame_rate": frame_rate,
                "frame_count": 0,
                "is_10bit": is_10bit,
                "pix_fmt": pix_fmt,
                "complete_audio": complete_audio,
                "audio_chunks": [],
                "current_iteration": 0,
                "run_id": current_run_id,
            }

        # 追加当前迭代的帧
        try:
            self._append_frames(state, video)
        except Exception:
            state["output"].close()
            ACCUMULATE_SAVE_VIDEO_STATES.pop(state_key, None)
            self._clear_latent_cache(state_key)
            if os.path.exists(state["path"]):
                os.remove(state["path"])
            raise

        state["current_iteration"] += 1

        # 把当前迭代的 feedback_latent 缓存到全局字典，供下一次迭代的 LoopVariable 读取。
        # 关键：展开图里 LoopVariable 副本的 next_value 只存 key 字符串，不存实际张量，
        # 避免 N 次迭代复制 N 份大 latent 导致内存爆炸。
        if feedback_latent is not None:
            completed_iteration = state["current_iteration"] - 1
            cache_key = f"latent_{state_key}_{completed_iteration}"
            _WHALE_LATENT_CACHE[cache_key] = feedback_latent

        # 最后一次迭代：完成编码并输出
        if last:
            try:
                result = self._finalize_video(state)
                ACCUMULATE_SAVE_VIDEO_STATES.pop(state_key, None)
                self._clear_latent_cache(state_key)
                return result
            except Exception:
                state["output"].close()
                ACCUMULATE_SAVE_VIDEO_STATES.pop(state_key, None)
                self._clear_latent_cache(state_key)
                if os.path.exists(state["path"]):
                    os.remove(state["path"])
                raise

        # 还有迭代：用 expand 递归展开循环体
        # flow_control 是 rawLink 格式 [loop_node_id, socket]（rawLink=True 不解析输出值）
        if flow_control is None or not isinstance(flow_control, (list, tuple)) or len(flow_control) < 1:
            raise ValueError(
                "WhaleTransAccumulateSaveVideo 必须连接 flow_control 输入。"
                "请从 WhaleTrans Loop 节点的 flow_control 输出端连一条线到本节点的 flow_control 输入端。"
            )
        open_node = flow_control[0]

        # 从 SaveVideo 向上游收集所有依赖节点（只基于 link 关系）
        visited = self._explore_dependencies(unique_id, dynprompt)
        contained = {nid: True for nid in visited}

        next_iteration = state["current_iteration"]
        graph = GraphBuilder()

        # 复制循环体内的所有节点
        for node_id in contained:
            original_node = dynprompt.get_node(node_id)
            name = "Recurse" if node_id == unique_id else node_id
            node = graph.node(original_node["class_type"], name)
            node.set_override_display_id(node_id)

        # 重新连接节点输入（所有 link 统一重连到副本，包括 flow_control）
        for node_id in contained:
            original_node = dynprompt.get_node(node_id)
            name = "Recurse" if node_id == unique_id else node_id
            node = graph.lookup_node(name)
            for k, v in original_node["inputs"].items():
                if is_link(v) and v[0] in contained:
                    parent_name = "Recurse" if v[0] == unique_id else v[0]
                    parent = graph.lookup_node(parent_name)
                    node.set_input(k, parent.out(v[1]))
                else:
                    node.set_input(k, v)

        # 关键：直接把 Loop 副本的输出连到需要迭代值的节点，绕过 Set/Get 全局字典通信
        # 原因：展开图里 Loop 副本的输出只连 Set 副本，Set 副本输出没连任何节点（Get/Set 靠全局字典通信无 link），
        # 导致 Loop 副本不在 SaveVideo 副本的依赖链里，ComfyUI 跳过它不执行，
        # Get 副本永远拿到原图第一次迭代的旧值 → 两段内容一样。
        # Loop 副本输出 socket: 0=iteration, 1=is_first, 2=is_last, 3=flow_control
        loop_clone = graph.lookup_node(open_node)
        loop_clone.set_input("iteration_offset", next_iteration)

        for node_id in contained:
            original_node = dynprompt.get_node(node_id)
            cls_type = original_node["class_type"]
            name = "Recurse" if node_id == unique_id else node_id
            node = graph.lookup_node(name)

            # 循环续段节点：直接连 Loop 副本的 iteration 和 is_first
            if cls_type == "MiniMaxH3LoopLatentGuide":
                node.set_input("iteration", loop_clone.out(0))
                node.set_input("is_first", loop_clone.out(1))

            # LoopVariable：直接连 Loop 副本的 iteration，
            # next_value 不设置为实际 latent 张量（否则 N 次迭代复制 N 份大张量导致内存爆炸），
            # 而是设置为全局缓存的 key 字符串，LoopVariable 执行时按 key 从 _WHALE_LATENT_CACHE 读取。
            if cls_type in ("WhaleTransLoopVariable", "LoopVariable"):
                node.set_input("iteration", loop_clone.out(0))
                completed_iteration = state["current_iteration"] - 1
                cache_key = f"latent_{state_key}_{completed_iteration}"
                node.set_input("next_value", cache_key)

        # SaveVideo 副本：直接连 Loop 副本的 is_last（flow_control 已在上面统一重连到 Loop 副本）
        my_clone = graph.lookup_node("Recurse")
        my_clone.set_input("last", loop_clone.out(2))

        return {"result": (), "expand": graph.finalize()}


NODE_CLASS_MAPPINGS = {
    "WhaleTransAccumulateSaveVideo": WhaleTransAccumulateSaveVideo,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "WhaleTransAccumulateSaveVideo": "WhaleTrans Accumulate Save Video",
}
