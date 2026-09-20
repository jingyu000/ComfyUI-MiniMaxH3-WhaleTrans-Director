# ComfyUI MiniMax H3 WhaleTrans Director

基于 [Songssx/ComfyUI-MiniMaxH3-TimelineDirector](https://github.com/Songssx/ComfyUI-MiniMaxH3-TimelineDirector) 开发的 UI 增强版开源插件。核心是自定义 3 节点循环系统，使用 ComfyUI 官方 **expand 递归展开机制**实现多段循环 latent 传输 + 视频累积拼接，无需替换核心文件（projection），开箱即用。

## ✨ 功能特性

- **3 节点循环系统**：Loop / LoopVariable / AccumulateSaveVideo，替代原作者的 Set/Get 全局字典通信方案
- **官方 expand 机制**：使用 ComfyUI 原生递归展开，不侵入核心文件，兼容性好
- **内存优化**：全局 latent 缓存 + key 字符串引用，避免 N 次迭代复制 N 份大张量导致显存爆炸
- **运行隔离**：每次点击"运行"自动检测新运行，清理上一次中断残留状态，从第 1 段重新开始
- **H3 HIGH 二次采样引导**：解决导演台条件下 3D 潜空间放大后二次采样尺寸不匹配的问题
- **H3 Latent 分辨率**：从 H3 NestedTensor（视频+音频打包）读取像素宽高，兼容普通 latent
- **H3 Latent 空间缩放**：H3 专用 latent 空间尺寸缩放，支持 NestedTensor
- **导演台 UI 增强**：分段时间轴自适应、帧率输入框、绿色高亮、双击改编号、素材持久化、分组三列+音频/音乐两列、全局开关、时长联动、双击改名等

## 🖼️ 界面预览

![导演台 UI 界面](docs/images/director-ui-overview.png)

## 📦 安装

### 方法一：Releases 下载（推荐）
1. 前往 [Releases](https://github.com/jingyu000/ComfyUI-MiniMaxH3-WhaleTrans-Director/releases) 页面下载最新版 zip
2. 解压到 ComfyUI 的 `custom_nodes` 目录
3. 重启 ComfyUI

### 方法二：git clone
```bash
cd ComfyUI/custom_nodes
git clone https://github.com/jingyu000/ComfyUI-MiniMaxH3-WhaleTrans-Director.git
```

### 依赖
- ComfyUI 0.35.1+
- MiniMax H3 模型（视频生成模型）
- 3D 潜空间放大模型：`minimax_h3_latent_upscaler_3d_fp16.safetensors`

## 🧩 节点说明

### 核心循环节点

![Loop 循环节点特写](docs/images/loop-node-closeup.png)

| 节点名 | 显示名 | 说明 |
|--------|--------|------|
| `WhaleTransLoop` | WhaleTrans Loop | 循环开始节点，控制循环次数，输出 iteration / is_first / is_last / flow_control |
| `WhaleTransLoopVariable` | WhaleTrans Loop Variable | 循环变量节点，在循环体内传递 latent 变量（上一段反馈 latent） |
| `WhaleTransAccumulateSaveVideo` | WhaleTrans Accumulate Save Video | 累积保存视频，每次迭代追加帧，最后一次完成编码；同时作为 expand 循环的触发节点 |

### 工具节点

| 节点名 | 显示名 | 说明 |
|--------|--------|------|
| `H3HighRefineGuide` | H3 HIGH 二次采样引导 | 把 3D 放大后的 latent 作为 direct latent guide 注入条件，同时透传 latent，解决导演台二次采样尺寸冲突 |
| `H3LatentResolution` | H3 Latent 分辨率 | 从 H3 NestedTensor 或普通 latent 读取像素宽高（自动乘 16 倍 VAE 下采样） |
| `H3LatentShrink` | H3 Latent 空间缩放 | H3 专用 latent 空间尺寸缩放，支持 NestedTensor（视频+音频打包），用于回传时缩回原始尺寸 |

## 📁 示例工作流

插件 `example_workflows/` 目录包含以下示例：

| 文件 | 说明 |
|------|------|
| `MiniMax循环长视频基础版示例工作流.json` | **推荐入门**：多段循环 + 二段式采样（LOW→3D放大→HIGH引导→二次采样→去重→累积保存），可直接运行 |
| `MiniMaxH3全功能合一完全体导演台工作流.json` | 原作者全功能版工作流（参考用） |
| `MiniMax_H3时间规划+Prompt提示词生成.json` | 时间规划 + 提示词生成工作流（参考用） |

**使用方法：** ComfyUI 菜单 → `Load` → 选择对应 JSON 文件导入。

## 🎬 基础版工作流结构（多段循环 + 二段式采样）

![基础版工作流整体图](docs/images/workflow-basic-overview.png)

基础版工作流结构：

```
导演台（规划编码器）→ 循环续段 → 基本引导器1 → 一次采样器（LOW）
                                                          ↓
                                              3D 潜空间放大（1.5x）
                                                          ↓
                                              H3 HIGH 二次采样引导 → 基本引导器2 → 二次采样器（HIGH）
                                                          ↓
                                              循环片段去重 → 累积保存视频
                                                          ↓
                                                    （循环回传）
```

**关键连线：**
- 一次采样器 Latent 口：原始尺寸空 AV latent
- 一次采样器引导口：循环续段后的 positive（包含上一段 latent 引导，保证段间连续性）
- 3D 放大输入：一次采样器输出
- H3 HIGH 二次采样引导 source_latent：3D 放大输出
- H3 HIGH 二次采样引导 positive：导演台直接输出的**干净 positive**（不经过循环续段）
- 二次采样器 Latent 口：H3 HIGH 二次采样引导输出的 latent（透传 3D 放大结果）
- 二次采样器引导口：H3 HIGH 二次采样引导输出的 positive → 基本引导器2
- 去重输入：二次采样器输出
- 累积保存视频输入：去重输出 + Loop is_last
- 循环回传：累积保存视频 feedback_latent → LoopVariable → 循环续段 previous_latent

## ⚙️ 技术实现

### 循环机制
使用 ComfyUI 官方 `expand` 递归展开机制，AccumulateSaveVideo 节点在每次迭代执行后，动态展开下一次迭代的所有循环体节点副本。Loop 副本的 `iteration_offset` 递增，据此计算当前迭代序号。

### 内存优化
展开图中 LoopVariable 副本的 `next_value` 不存储实际 latent 张量，而是存储全局缓存的 key 字符串（格式 `latent_{save_video_id}_{iteration}`），执行时按 key 从 `_WHALE_LATENT_CACHE` 字典读取。避免 N 次迭代复制 N 份大张量导致显存爆炸。

### 运行隔离
使用 `dynprompt` 对象 ID 区分不同次运行。每次点击"运行" ComfyUI 创建新的 DynamicPrompt 对象，SaveVideo 执行时检测到 ID 变化，自动清理上一次中断残留的视频编码器和 latent 缓存，`current_iteration` 归零，确保从第 1 段重新开始。

### HIGH 二次采样引导
导演台（规划编码器）生成的条件基于原始 latent 尺寸（如 38x22），3D 放大后 latent 尺寸变化（如 56x32），直接接入二次采样器会因条件与 latent 尺寸不匹配报错。H3HighRefineGuide 节点把放大后的 latent 作为 `direct latent guide` 注入条件的 `minimax_keyframes`，同时透传放大后的 latent 作为二次采样初值，解决尺寸冲突。

## ❓ 常见问题

**Q: 中断后再运行，循环从中间开始而不是第 1 段？**
A: 已修复。v1.0+ 版本使用运行隔离机制，每次新运行自动清理残留状态。如果仍有问题，重启 ComfyUI 可彻底清除。

**Q: 二次采样报 `shape mismatch` 错误？**
A: 检查二次采样的条件是否接了循环续段后的 positive（包含 previous_latent 引导）。应使用 H3 HIGH 二次采样引导节点，positive 接导演台直接输出的干净 positive。

**Q: 多段循环时显存爆炸？**
A: 已修复。使用全局 latent 缓存 + key 引用，不会复制多份大张量。建议在循环体内使用 VRAM Debug 节点释放中间模型显存。

**Q: `ImageGenResolutionFromLatent` 报 `too many values to unpack (expected 4)`？**
A: 普通节点不支持 H3 的 5D NestedTensor。使用插件自带的 `H3 Latent 分辨率` 节点替代。

## 📄 许可证

GPL v3 - 详见 [LICENSE](LICENSE) 文件。

## 🙏 致谢

- 原作者 [Songssx](https://github.com/Songssx) 的 [ComfyUI-MiniMaxH3-TimelineDirector](https://github.com/Songssx/ComfyUI-MiniMaxH3-TimelineDirector)
- ComfyUI 官方 expand 机制
