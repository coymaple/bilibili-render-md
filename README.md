# bilibili-render-md

把 Bilibili 技术教程、讲座类视频，转成**结构化中文 Markdown 图文讲义**的 opencode 技能（Agent Skill）。

产出不是逐句转录，而是一份**可脱离视频独立阅读**的图文教程：重建讲解顺序，保留关键代码、命令、公式与**经核对的视频关键帧截图**，并标出每张图的画面时间。

---

## 这是什么

一个 Agent Skill：目录由 `SKILL.md` 定义，被 opencode（以及兼容 Claude 的 `.claude/skills/` 目录）按需加载。

- 触发场景：用户给出 Bilibili 链接或 BV 号，要求生成 Markdown / 图文讲义。
- 不适用：最终交付物是 LaTeX / PDF 的场景（那是另一套流程）。

## 主要特性

- **有界降级**：字幕优先用平台 CC，其次本地 Whisper 转写，最后才纯视觉分析。
- **覆盖契约**：写文档前先做逐块内容盘点（inventory），保证不遗漏术语、命令、代码。
- **关键帧核对**：先用缩略图筛，再逐张看原图，只保留能讲清知识点的图。
- **可校验**：交付前跑结构 + 质量校验（链接、路径注释、依赖命令、自包含性等）。
- **交接友好**：支持跨会话/跨模型续跑，用 `work/logs/handoff.md` 保存进度。
- **目录分离**：原始素材、可再生中间产物、最终交付物严格分层。

## 目录结构

```text
bilibili-render-md/
├─ SKILL.md                    技能定义（工作流与规则）
├─ README.md                   本文件
├─ requirements.txt            运行依赖声明
├─ agents/openai.yaml          Agent 配置
├─ references/
│  ├─ whisper.md               转写、模型与本地环境指引
│  └─ long-video.md            长视频处理策略
└─ scripts/
   ├─ init_job.py              初始化任务、识别来源、建立目录
   ├─ transcribe_faster.py     faster-whisper 转写
   ├─ slice_transcript.py      转录切块与索引
   ├─ build_inventory.py       逐块内容盘点
   ├─ check_inventory_coverage.py  盘点与文档的覆盖核对
   ├─ validate_delivery.py     交付前结构与质量校验
   └─ setup.ps1                可选：本机转写环境准备（Windows）
```

## 获取与安装

### 作为项目 submodule

```bash
git submodule add <本仓库地址> .opencode/skills/bilibili-render-md
```

> 目录名必须与技能名一致（`bilibili-render-md`）。

### 作为全局技能

```bash
git clone <本仓库地址> ~/.config/opencode/skills/bilibili-render-md
```

## 依赖

```bash
pip install -r requirements.txt
```

- 脚本直接依赖：`faster-whisper`、`torch`。
- 下载步骤需要 `yt-dlp`。
- `ctranslate2`、`tokenizers`、`huggingface-hub` 等由 `faster-whisper` 自动带入。
- **Whisper 模型权重不入库**：放在 `<workspace>/output/_models/faster-whisper-<model>`，或用环境变量 `FASTER_WHISPER_MODEL_ROOT` 指向其父目录。
- 共享包目录（`pip --target` 安装）可用环境变量 `BILIBILI_RENDER_MD_PYTHONPATH` 指定，`transcribe_faster.py` 也会自动发现 `<workspace>/output/_shared/python-packages/`。

> GPU 转写需要与本机 CUDA 匹配的 torch 轮子，详见 `references/whisper.md`。Windows 下可用 `scripts/setup.ps1` 检查环境（其 `Python` / `TorchLib` 参数可按机器覆盖）。

## 使用方式

正常工作流由 Agent 通过 `skill` 工具自动加载 `SKILL.md` 后执行；用户只需给出视频来源与交付诉求（例如「转成 MD 图文讲义」）。

手动跑脚本的典型流程：

```bash
# 1) 初始化任务（B 站链接）
python scripts/init_job.py --bvid BVxxxxxxxxxx --part 1
#    或本地视频
python scripts/init_job.py --video-path "C:\videos\demo.mp4" --title "Demo"

# 2) 转写（用已装好 faster-whisper 的解释器）
<python> scripts/transcribe_faster.py "source/media/....mp4" \
    --workspace . --output-dir work/transcript --model medium --device cpu --language zh

# 3) 切块 + 盘点
python scripts/slice_transcript.py --job-root output/<job-id>
python scripts/build_inventory.py --job-root output/<job-id>

# 4) 覆盖核对 + 交付校验
python scripts/check_inventory_coverage.py --job-root output/<job-id> --markdown <final-md>
python scripts/validate_delivery.py --job-root output/<job-id> --markdown <final-md> --strict
```

## 工作流概览

| 步骤 | 内容 |
|---|---|
| 0 | 判断视频来源（已在本地则跳过下载） |
| 1 | 初始化任务、读取元信息、确认分 P 范围 |
| 2 | 取文本：CC 字幕 → 本地 Whisper → 纯视觉（有界降级） |
| 3 | 转录切块，建立逐块内容盘点（写前必做） |
| 4 | 长视频按真实章节切分，必要时用最小上下文子代理 |
| 5 | 用时间戳定位并**肉眼核对**关键帧 |
| 6 | 按盘点撰写讲义（中文、教学顺序、代码带路径注释） |
| 7 | 统一 Markdown 格式与命名规范 |
| 8 | 交付前校验（结构 + 质量），失败则定点重写 |

## 输出约定

所有任务产物位于 `<workspace>/output/<job-id>/`，三层分离：

```text
output/<job-id>/
├─ source/           原始平台素材（元数据、媒体）
├─ work/             可再生中间产物（转录、抽帧、盘点、日志）
└─ deliverables/     最终自包含交付（docs/、assets/、attachments/）
```

- 最终 Markdown 只写入 `deliverables/docs/`，且不得链接到 `source/` 或 `work/`。
- 最终文件名形如 `<课程简称>_<BVID>_P<n>_图文讲义.md`（整片为 `_FULL`）。

## 常见问题

- **转写报「未安装 faster-whisper」**：当前 `python` 可能是个空 `.venv`，改用已装该包的解释器，不要为每个任务单独安装。
- **中文错字多**：中文/中英混合必须显式 `--language zh`，并优先 `medium`/`large-v3`；绝不用 `.en` 模型。
- **笔记不完整**：用 `check_inventory_coverage.py` 对照 `work/transcript/inventory.json`，补齐未覆盖的术语/命令/代码。
- **质量校验失败**：按 `validate_delivery.py --strict` 指出的类别定点重写（缺路径注释、缺安装命令、文档引用了视频等）。

## 维护说明

本仓库是该技能的唯一来源。修改 `SKILL.md`、`scripts/`、`references/` 或 `agents/` 下任何文件后，变更即生效。建议按功能提交，并在提交信息中说明动机与影响。
