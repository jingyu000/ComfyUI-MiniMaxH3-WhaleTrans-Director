from server import PromptServer

# 与 WhaleTransAccumulateSaveVideo 共享的状态字典
# key 为 SaveVideo 节点的 display_id，value 为视频编码器状态
# Loop 节点在第一次迭代 (iteration_offset=0) 时负责清理所有旧状态
_WHALE_LOOP_SAVE_STATES = {}

# 全局 latent 缓存：expand 机制下避免把大张量复制 N 份到展开图里。
# key 格式: f"latent_{save_video_display_id}_{iteration}"
# SaveVideo 每次执行完写入当前迭代的 feedback_latent，
# LoopVariable 按 key 字符串读取，最后一次迭代 finalize 后由 SaveVideo 清理。
_WHALE_LATENT_CACHE = {}


class WhaleTransLoop:
    """循环开始节点：控制循环次数。

    输出顺序与旧版 prs-generic-loops 的 Loop 节点对齐：
    iteration, is_first, is_last, 最后新增 flow_control。

    iteration_offset 为内部隐藏参数，由 SaveVideo 的 expand 机制在每次展开时递增，
    Loop 据此计算当前迭代的 iteration/is_first/is_last，并在节点上显示进度。
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "num_iterations": ("INT", {"default": 1, "min": 0, "max": 100000, "step": 1}),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
                "iteration_offset": "INT",
                "dynprompt": "DYNPROMPT",
            },
        }

    RETURN_TYPES = ("INT", "BOOLEAN", "BOOLEAN", "FLOW_CONTROL")
    RETURN_NAMES = ("iteration", "is_first", "is_last", "flow_control")
    FUNCTION = "execute"
    CATEGORY = "looping"

    def execute(self, num_iterations, unique_id=None, iteration_offset=0, dynprompt=None):
        iteration = int(iteration_offset)
        # 防御性边界检查：中断后 ComfyUI 队列可能残留已展开但未执行的节点，
        # 其 iteration_offset 是上一次运行的值，导致进度显示超过 num_iterations（如 4/3）。
        # 检测到越界时强制钳位到最后一次，并打印警告，阻止 SaveVideo 继续展开。
        if iteration < 0:
            iteration = 0
        if iteration >= num_iterations:
            print(f"[WhaleTransLoop] 警告: iteration_offset={iteration_offset} 超出 num_iterations={num_iterations}，"
                  f"可能是中断后残留展开节点，已钳位到最后一次。建议重启 ComfyUI 清除残留状态。")
            iteration = num_iterations - 1
        is_first = (iteration == 0)
        is_last = (iteration >= num_iterations - 1)

        # 获取 display_id：展开图里副本的 override_display_id=原图节点 id，
        # 所以 display_id 在所有迭代间保持不变，进度能正确显示在原图 Loop 节点上
        display_id = unique_id
        if dynprompt is not None and hasattr(dynprompt, "get_display_node_id"):
            try:
                display_id = str(dynprompt.get_display_node_id(unique_id))
            except Exception:
                pass

        # 第一次迭代时清理所有 SaveVideo 的旧状态（防止上一次运行的残留编码器）
        if is_first:
            for old_key in list(_WHALE_LOOP_SAVE_STATES.keys()):
                old_state = _WHALE_LOOP_SAVE_STATES.pop(old_key)
                try:
                    old_state["output"].close()
                except Exception:
                    pass
            # 同时清理全局 latent 缓存（上一次运行的残留）
            _WHALE_LATENT_CACHE.clear()

        # 在 Loop 节点上显示进度（用 display_id 确保展开图副本的进度也能显示在原图节点上）
        try:
            PromptServer.instance.send_progress_text(
                f"段 {iteration + 1} / {num_iterations}",
                display_id,
            )
        except Exception:
            pass

        return (iteration, is_first, is_last, "stub")


class WhaleTransLoopVariable:
    """循环变量节点：在循环体内传递 latent 变量。

    next_value 为内部隐藏参数，原图不需要连接（避免环），
    由 AccumulateSaveVideo 在展开图内部自动设置为上一次迭代的反馈 latent。
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "iteration": ("INT", {"forceInput": True}),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
                "next_value": "LATENT",
            },
        }

    RETURN_TYPES = ("LATENT",)
    RETURN_NAMES = ("current_value",)
    FUNCTION = "execute"
    CATEGORY = "looping"

    def execute(self, iteration, unique_id=None, next_value=None):
        # next_value 有三种形态：
        # 1. None：第一次迭代（原图未连接），循环续段靠 is_first=True 忽略 previous_latent
        # 2. 字符串 key（格式 "latent_{save_video_id}_{iteration}"）：展开图里由 SaveVideo 设置，
        #    从全局缓存读取对应 latent，避免把大张量复制 N 份到展开图
        # 3. 实际 latent 张量：兼容旧行为
        if isinstance(next_value, str) and next_value.startswith("latent_"):
            cached = _WHALE_LATENT_CACHE.get(next_value)
            if cached is None:
                raise ValueError(
                    f"WhaleTransLoopVariable 缓存未找到: {next_value}。"
                    "这通常是因为上一次运行被中断后残留了展开节点，或者 SaveVideo 没有正确写入 feedback_latent。"
                    "请重新运行工作流（不要从中断点继续）。"
                )
            return (cached,)
        return (next_value,)


NODE_CLASS_MAPPINGS = {
    "WhaleTransLoop": WhaleTransLoop,
    "WhaleTransLoopVariable": WhaleTransLoopVariable,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "WhaleTransLoop": "WhaleTrans Loop",
    "WhaleTransLoopVariable": "WhaleTrans Loop Variable",
}
