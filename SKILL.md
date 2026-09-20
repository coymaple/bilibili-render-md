---
name: bilibili-render-md
description: Turn a Bilibili lecture, tutorial, or technical video into structured Chinese Markdown notes with verified key frames, code, formulas, timestamps, and self-contained local assets. Use when the user provides a Bilibili URL or BV number and wants Markdown or 图文讲义; do not use when the required final deliverable is LaTeX/PDF.
---

本技能维护于独立仓库 `bilibili-render-md`，以 submodule 挂载在项目路径 `.opencode/skills/bilibili-render-md`（全局安装时位于 `~/.config/opencode/skills/`）。修改 SKILL.md、scripts/、references/ 或 agents/ 下任何文件后，变更即生效。

# Bilibili Render Markdown

Create accurate, readable Chinese Markdown notes from the requested Bilibili video or selected parts. Preserve teaching value without producing a chronological transcript dump.

## Workspace and output invariant

Resolve the workspace at runtime:

- Default to the current working directory.
- If the user names another project directory, use that directory only after resolving it.
- Never hard-code a prior workspace, user profile, drive letter, or output path.
- Keep every task under `<workspace>/output/<job-id>/`.

Initialize the task with `scripts/init_job.py`. Use `<BVID>_P<n>` for one part and `<BVID>_FULL` only when the user explicitly requests the full video. When the source has no BV number, use its aid (`Av<id>`) in place of `<BVID>`.

The following separation is mandatory:

```text
output/<job-id>/
├─ source/                         Original platform artifacts
│  ├─ metadata/
│  └─ media/
├─ work/                           Regenerable intermediate artifacts
│  ├─ transcript/
│  ├─ frames/{coarse,targeted}/
│  ├─ contact-sheets/
│  ├─ logs/
│  └─ temp/
└─ deliverables/                   Final, self-contained delivery only
   ├─ docs/
   ├─ assets/{cover,figures}/
   └─ attachments/
```

Do not place final Markdown beside original video, audio, platform JSON, raw subtitles, candidate frames, scripts, dependencies, or logs. Write the final Markdown directly into `deliverables/docs/`. Copy only the selected cover and figures into `deliverables/assets/`; copy a cleaned or final SRT into `deliverables/attachments/` when it is part of the delivery. Final Markdown must not link into `source/` or `work/`.

Do not install Python packages or model weights inside a per-video job. Reuse a project environment such as `<workspace>/.venv` and shared model storage such as `<workspace>/output/_models/` when available.

## Detect vision capability

Before any figure work (step 5), probe whether the current model can actually read images. Ask it to describe a small existing frame or state its vision capability explicitly. Do not discover a missing vision ability halfway through.

When the model cannot see images, do not stop the job. Use one of these fallbacks:

- **Contact-sheet confirmation**: extract a coarse contact sheet, give the user the single image path, and let the user pick the good frames. Proceed with the chosen timestamps.
- **Timestamp-only auto-selection**: select frames from the timestamp map without a human pass. Label each such figure in the document as "按字幕时间戳截取，未经人工核对".
- **Text-and-code only**: if figures do not materially add teaching value, deliver the notes without screenshots and state that in the metadata blockquote.

Record the chosen fallback in the final document header and in the handoff notes (next section) so a later visual model can re-verify figures if needed.

## Workflow

### 0. Detect video source

Before any other step, determine where the video comes from:

| 情况 | 动作 |
|------|------|
| 用户提供 BVID/URL 且 `source/media/` 下已有该视频文件 | 跳过下载 |
| 用户提供 BVID/URL 且 `source/media/` 下无视频 | 下载到 `source/media/` |
| 用户提供本地视频文件路径 | 复制到 `source/media/` |
| 用户直接指定 `--video-path` 给 `scripts/init_job.py` | 由 init_job 复制到 `source/media/` |

Local material is often staged under `<workspace>/input/<course>/`, with the video and an optional same-stem audio file (`.mp3`, `.m4a`, `.wav`, …) side by side. The input layout is not fixed; always resolve the path the user names. When a same-stem sibling audio file exists, prefer it as the transcription source: copy it to `source/media/` and send it to Whisper directly instead of extracting an audio track from the video. `scripts/init_job.py` discovers sibling audio automatically; use `--audio-path` only to override.

### 1. Inspect and initialize

Initialize the job with `scripts/init_job.py`:
- Bilibili URL → `scripts/init_job.py --bvid <BVID> --part <N>`
- Local video → `scripts/init_job.py --video-path <path> --title "<title>"`

When a local filename encodes the Bilibili identity as `(Av<id>,P<n>)` or `(BV<id>,P<n>)` (for example `6.part1_05(Av113985311540118,P6).mp4`), `init_job.py` parses the id and part from the name automatically, so the job id and the final filename stay in the `<id>_P<n>` form. Never let the raw, long title become the job id.

After initialization, inspect compact metadata (title, duration, subtitle tracks, usable formats). Do not print full platform JSON into the conversation; save it under `source/metadata/` and return only the needed fields.

For a multi-part video, list the parts and ask which range to process. Do not infer full-series authorization from one URL.

Prefer the highest usable public format. Request browser-cookie access only when public quality is inadequate for readable teaching figures or the user explicitly requests login-gated quality. Never export or persist browser cookies.

### 2. Acquire text with bounded fallback

Use this order:

1. Platform CC subtitles, preserving timestamps.
2. Local Whisper transcription.
3. Visual-only analysis when audio is unusable.

If a local audio file is available (see step 0), pass it directly to `scripts/transcribe_faster.py`; faster-whisper reads `.mp3`/`.m4a`/`.wav` without a separate ffmpeg extraction step.

If Whisper is needed, read [references/whisper.md](references/whisper.md) before installing, downloading, or transcribing. Check local packages and local model paths before any network action. Stop repeated model-download attempts after one official endpoint and at most one user-approved fallback; use an already available model when possible. `scripts/transcribe_faster.py` automatically discovers shared packages and CUDA runtime DLLs. The optional `scripts/setup.ps1` script remains available for manual environment inspection.

Run the script with an interpreter that already has `faster-whisper` — verify with `<python> -c "import faster_whisper"` before transcribing. The active `python` may be an empty `.venv`; do not install the package per job, switch to the interpreter that already has it (see [references/whisper.md](references/whisper.md)).

#### Check available models first

Before choosing a model, inspect `output/_models/manifest.json` (if it exists) to see which models are already downloaded locally. Run this check at the start of any Whisper-dependent job:

```
- python -c "import json; print(json.dumps(json.load(open('output/_models/manifest.json')), ensure_ascii=False))"
```

Prefer a locally available model over downloading. If no model exists, use the model appropriate to the content type from the table below and add it to the manifest after download.

#### 模型选择指南

| 内容类型 | 推荐模型 | 原因 |
|---------|---------|------|
| 纯英文 | small.en | 质量更好，速度适中 |
| 纯中文 | medium / large-v3（多语言） | 多语言 `small` 中文错字明显，不足以支撑讲义 |
| 中英混合 | medium（多语言），急用可 `small` | 需要多语言模型；`small` 术语易错 |
| CPU-only | small / base（int8） | 速度优先 |
| GPU 可用 | medium / large-v3（float16） | 质量优先 |

中文或中英混合音频必须显式传 `--language zh`，不要依赖自动检测：短音频或开头有音乐时会被误判成英文。同时用 `--prompt` 传入视频里真实出现的技术名词（例如 `Next.js tRPC React Agent`）可明显减少专有名词错字。中文绝不能使用 `.en` 结尾的模型。

#### CPU-only模式

当GPU不可用时：
1. 使用`--device cpu`参数
2. 使用`--compute-type int8`提高速度
3. 预期处理时间：`small` 每10分钟视频约需2-3分钟；`medium` 约为其 3-4 倍，长视频优先用 `small` 出初稿或改用 GPU
4. 质量略有下降；中文内容不要为了速度退回 `small` 而不说明质量风险

#### 处理时间估算

| 视频长度 | 转录时间(base/CPU) | 笔记生成 | 总时间 |
|---------|-------------------|---------|-------|
| 10分钟 | 2-3分钟 | 1-2分钟 | 3-5分钟 |
| 30分钟 | 6-8分钟 | 2-3分钟 | 8-11分钟 |
| 50分钟 | 10-12分钟 | 3-5分钟 | 13-17分钟 |

### 3. Keep transcript context small

Use `scripts/slice_transcript.py` to create timestamped chunks and an index. Read only the chunks relevant to the current section. Persist each section's compact notes before moving to the next section.

Never send the full SRT, TXT, TSV, and JSON versions of the same transcript into model context. Prefer one timestamped source plus a compact index.

#### 转录块读取策略

对于50分钟以上的视频：
- 至少读取50%的转录块（约5-6个块）
- 优先读取开头、中间和结尾的块
- 确保覆盖所有主要教学点
- 对于关键代码示例，读取包含该代码的完整块

#### Build the content inventory（盘点，写文档前必做）

Before writing any prose, build a per-chunk content inventory so nothing in the transcript is skipped. This replaces post-hoc content checking with a before-you-write checklist.

1. Run `scripts/build_inventory.py --job-root <job-root>` to mechanically extract, per chunk: density, code terms, commands, code-shaped lines, visual cues, and transition cues. It writes `work/transcript/inventory.json`.
2. Read the inventory once, then read **every chunk** and enrich each entry's `points` array with compact teaching points: concepts, code details, pitfalls, and anything the lecturer implies is on screen (frame-dependent content). Persist these points into `inventory.json`.
   - This is the one pass that guarantees all transcript content is seen at least once, even when chunks were never read later.
   - A chunk flagged `"density": "sparse"` means speech carries little information; extract points with the video frames in mind and note the on-screen artifact in `points`.
   - A chunk whose `visual_cues` list is non-empty describes on-screen content; record what must be captured in prose even if no figure is selected.
3. **Label the real chapter boundaries.** Platform parts are arbitrary cuts: a course chapter can start or end mid-part. While reading chunks, use `transition_cues` (spoken cues like "接下来进入", "now let's move to", "chapter 4") plus on-screen signals (whiteboard, slides, file/route changes) to identify the lecturer's actual chapter switches. Set each chunk's `chapter` field to the course chapter number (and optionally name) it belongs to; chunks on a boundary get `chapter_boundary: true`. Persist these labels into `inventory.json`.
4. The outline in step 6 must be derived from this inventory, so it already reflects every chunk.

### 4. Handle long videos efficiently

When duration exceeds 20 minutes or subtitles exceed 300 entries, read [references/long-video.md](references/long-video.md). Split by real teaching boundaries, not arbitrary equal chunks when chapters are visible.

When subagents are available, give them minimal context: paths, exact time range, task rubric, and a strict return schema. Do not fork the full thread history. The main agent owns the unified outline, deduplication, factual reconciliation, and final prose.

### 5. Locate and verify figures

Use subtitle timestamps to identify high-value windows. First create coarse chapter coverage, then densely sample only short concept windows. Avoid exhaustive high-resolution inspection of every candidate.

This step assumes a vision-capable model; otherwise apply the fallback in the "Detect vision capability" section above.

Use contact sheets for recall, then directly inspect several nearby original frames before selecting one. Reject frames that are incomplete, transitional, unreadable, redundant, error-filled, or expose secrets or private data. Do not use OCR as a substitute for visual understanding.

Name raw frames by timestamp. Assign a semantic filename only after the image has been visually confirmed. Copy selected figures to `deliverables/assets/figures/` and record the source time or subtitle-aligned interval in the Markdown caption.

### 6. Write the notes

Write against the inventory from step 3: before each chapter, read the relevant chunk's `inventory.json` entry plus its transcript chunk, and make sure every term, command, code line, and recorded point from that entry is addressed in the prose or a code block. Do not close a chapter while its chunk's points are unaddressed. Reuse the chunk texts only where a teaching point needs more context; the inventory alone carries the coverage contract.

Write in Chinese unless the user requests another language. Reconstruct a teaching sequence rather than following subtitles line by line. Each major section should establish motivation, mechanism, example or evidence, common failure modes, and takeaway when applicable.

Preserve important code, formulas, commands, examples, and speaker-stated limitations. Explain code before or after the listing. For formulas, explain the purpose and every symbol. Do not invent formulas, code, results, citations, or material from later parts.

Every code block must carry a comment as its first line that states the file path being shown, in a form appropriate to the language:

```tsx
// src/modules/home/ui/views/home-view.tsx
```

```python
# scripts/transcribe.py
```

For languages with no comment syntax (for example bare JSON or a directory tree), put a short italic note before the block stating the path instead.

Use the exact path the lecturer presents (project-relative when possible). Terminal commands and other code blocks not tied to a file need no path annotation. Code blocks written purely to test, demo, or illustrate (not part of the lecturer's project files) also need no path annotation; only blocks that show one of the lecturer's actual files carry the path comment.

The document must be a step-by-step builder's manual: each action is a numbered step with the command or file change first, followed by the exact expected result (what the user sees or the terminal prints). An expected result is written only when it appears in the video — in the subtitles or on screen at a concrete timestamp; never invent an expected result from memory. If the video does not show a verifiable outcome for a step, omit the expected result instead of guessing.

When the lecturer modifies a file that was already shown earlier in the video, do not silently dump the whole file again. Instead:

- Add the same path comment on the block.
- If the file is small or the whole file is on screen, show it once with the path comment.
- If only part of the file is relevant or the file is large, retain its structure while omitting unchanged regions: keep the surrounding unchanged lines for context and replace the omitted span with an ellipsis, for example `  // …` inside code or a short note such as `（原文件其余部分未改动，已省略）`.
- Always make the newly changed lines visually explicit, by preferring a short leading marker in a comment line such as `// [改动]`, `# [改动]`, or `/* [改动] */`. Mark only what changed in this part of the video, not the whole file.
- Keep anything a previously-shown block already established; do not repeat unchanged content verbatim.

Do not invent changes beyond what the lecturer actually did; if only one line changes, show that single change with context and state that the rest was untouched.

Every code block that imports a package or uses a library must be accompanied by the installation command nearby (e.g. `pip install faster-whisper`, `npm install express`). The document must be self-contained: a reader should be able to follow every step without watching the video.

The document should normally include:

- title, source URL, exact part scope, duration, and transcription provenance;
- concise learning map or timeline;
- structured teaching sections;
- verified key figures with concrete source times;
- code, formulas, and commands that materially support the lesson;
- troubleshooting or common mistakes when present;
- final synthesis and explicit boundary with later parts;
- links only to self-contained files within `deliverables/`.

Avoid decorative screenshots, repeated near-identical frames, transcript dumps, greetings, sponsorship, routine sign-off, and unrelated platform content.

### 7. Markdown format

Produce a consistent, scannable Chinese Markdown document. Follow this structure and these style rules:

**Document shell**

- `#` title as the first line, followed immediately by the cover image on the next line.
- A blockquote right after the cover carrying the source metadata (source URL / BVID / part, exact part scope, duration, and transcription provenance). Keep it a short blockquote, not paragraphs.
- A concise `## 这一讲完成什么` overview naming the topics covered and, when relevant, what this part does not finish.
- A `## 学习路线` table with columns `时间 | 内容 | 最终产物`, one row per segment. Keep the table narrow and aligned.
- Numbered top-level teaching sections (`## 一、`, `## 二、`, …) with logical `### …` subheads. Do not mirror the subtitle stream as the outline.

**标题规范 (headings)**

- Level 1 (`# H1`) appears exactly once, as the document title only: `<课程> <P数> 图文讲义`. No other `#` headings anywhere.
- Level 2 (`## H2`) has exactly two kinds of use:
  - the fixed overview headings `## 这一讲完成什么` and `## 学习路线` (use these exact titles, in this order, right after the metadata blockquote);
  - the numbered teaching chapters `## 一、…`, `## 二、…`, … in order, one per teaching unit.
- A platform part is an arbitrary cut, not a course chapter. When this part begins or ends inside a course chapter (that is, the inventory labels a `chapter_boundary` chunk inside this part), mark the switch with a highlighted blockquote immediately above the teaching heading where the new course chapter starts:

  `> ⚠️ 章节边界：视频在此从第 N 讲（名称）进入第 N+1 讲（名称），时间 `MM:SS` 附近。`

  Use one such marker per switch. Without a boundary, do not add the marker. If this part begins mid-chapter and no previous part's notes are in scope, note in the metadata blockquote that the part opens in the middle of course chapter N.
- Level 3 (`### H3`) is for subheads inside a chapter. Pick one consistent numbering scheme for the whole document and do not mix:
  - `### 2.1 描述`, `### 2.2 描述`, … (chapter.subsection), or
  - `### 1. 描述`, `### 2. 描述`, … (sequential restart within each chapter).
- A small, consistent set of unnumbered `### H3` shortcuts is allowed only for recurring named blocks (for example `### 常见错误`, `### 本讲边界`). Use them sparingly and keep their names identical each time.
- Do not use `#### H4` (or deeper) for ordinary prose; fold such nuance into `###` text or body paragraphs.
- Every teaching heading must be descriptive Chinese and summarize the section's result or purpose, not quote a transcript line.
- Keep all heading punctuation and numbering style uniform: no trailing punctuation on headings, `、` only after the chapter numerals, and a space after the number in `### n. ` subheads.

**文件名规范 (filename)**

The final Markdown file name must follow one fixed pattern and match the job's video identity:

- Pattern: `<course-slug>_<BVID>_P<n>_图文讲义.md` for a single part, or `<course-slug>_<BVID>_FULL_图文讲义.md` for the whole video.
- `<course-slug>`: a short readable identifier of the course from the video title, keeping letters and digits (for example `Nextjs15_React19_YouTube 克隆` → `Nextjs15_React19_YouTube`). Drop spaces; do not keep an article, a version suffix that duplicates the BVID, or the words `图文讲义` themselves.
- `<BVID>`: the video's unchanged BV number (for example `BV1HoN6eREQ2`). If the source provides only an aid and no BV number, write `Av<id>` here and in the job id (for example `Av113985311540118` in `Nextjs15_React19_YouTube_Av113985311540118_P6_图文讲义.md`).
- `<P<n>>`: the processed part number; `_FULL` replaces it only when the whole video is delivered.
- Use ASCII underscore `_` as the only separator. The full file name must remain filesystem- and link-safe: no spaces, no `/ \ : * ? " < > |`, and no Chinese punctuation in the name itself.
- Write the file into `deliverables/docs/`. Keep its name identical to the `#` document title's content minus `图文讲义`, so a reader can find the file from the heading.

**Section and paragraph style**

- Write each section as a teaching sequence (motivation → mechanism → example/evidence → failure modes → takeaway), not a transcript.
- Keep headings concise; prefer descriptive Chinese without trailing punctuation.
- Use `---` horizontal rules sparingly, only to separate large parts when the text would otherwise run together.

**Code and diagram blocks**

- Add the `// <path>` file-path comment as the first line (see the code rule above); terminal commands need no annotation.
- Prefer syntax-hinted fenced blocks (```` ```tsx ````, ```` ```python ````, etc.).
- Use `text`-fenced ASCII trees/flow diagrams for directory structures and data flows; align with box-drawing characters, and keep them narrow and tidy.
- Do not wrap code in extra `> ` blockquotes or inline styling that breaks copy-paste.

**Figures and captions**

- Insert each figure inline right after the paragraph or code that references it, using a relative path into `deliverables/assets/figures/`.
- Give every figure an italic caption line directly below, of the form `*图 N：<说明>，画面时间 <mm:ss>。*`, numbering figures across the whole document.

**Lists and emphasis**

- Use `-` bullet lists and `1.` ordered lists consistently; keep each list to one idea per item.
- Mark key terms, file paths, and inline code with backticks.
- Prefer short Chinese prose and code-first explanations (explain before or after each listing).

**Consistency and validation**

- Keep the same heading depth, list marker, and caption numbering from top to bottom.
- Before delivery the document must pass the layout, link, and separation checks in the validation step below.

#### Inventory cross-check（写完后清单核对）

After drafting and before `validate_delivery.py`, mechanically verify the written document still addresses the inventory:

```
python scripts/check_inventory_coverage.py --job-root <job-root> --markdown <final-md>
```

This is a checklist, not a quality review: it reports each chunk's terms, commands, and code lines that do not appear anywhere in the document. `--skip` skips the cross-check after printing a one-line log.

When the report is not `ok`:
1. Read the gap report's `uncovered` lists for the failing chunks.
2. Re-read those chunk texts and their inventory `points`.
3. Patch the affected sections of the document to cover the named imports, commands, and terms.
4. Re-run the cross-check. Fix in at most two iterations; if still failing, leave the report JSON in `work/logs/` and record the recipe in `work/logs/handoff.md`.

### 8. Validate before delivery

Run `scripts/validate_delivery.py --job-root <job-root> --markdown <final-md> --strict`.

Confirm that structural checks pass:

- every local Markdown link resolves;
- every relative local link stays inside `deliverables/`;
- final Markdown is under `deliverables/docs/`;
- selected figures match the surrounding explanation;
- no secrets, tokens, cookie values, email addresses, private endpoints, or personal identifiers appear;
- the notes do not exceed the user-approved part range;
- original and intermediate files remain outside `deliverables/`.

Confirm that quality checks pass (the `--strict` flag enables these; code-block path-comment findings remain warnings even with `--strict` because shell and test/demo blocks legitimately carry no path):

- every fenced **project-file** code block has a file path comment as its first line (`// <path>` or `# <path>`); shell, terminal, text/tree, and test/demo code blocks are exempt;
- code blocks containing imports have a dependency installation command somewhere in the document (e.g. `pip install`, `npm install`, `bun add`, `cargo install`, `conda install`, etc.);
- the document contains no references to the video (e.g. "as shown in the video", "如视频所示") — it must be self-contained;
- all required sections are present (`#`, `## 这一讲完成什么`, `## 学习路线`, `## 一、…`);
- every figure reference has a matching caption with the `图 N：…，画面时间 …` pattern.

The dependency check is a coverage check — it verifies the document mentions an installation command at least once, not that each code block has one inline. This accommodates projects using multiple package managers or languages.

#### Writing quality self-check (before validation)

Before running `validate_delivery.py`, verify these properties in the draft:

1. **Self-contained**: Can a reader follow every step without watching the video? Every command, every import, every configuration is stated explicitly.
2. **Code completeness**: Does every code block represent a complete, runnable snippet? Truncated or partial code is a quality failure.
3. **No video dependency**: No phrases like "as I showed" or "like the video" — everything is written as if the reader has never seen the video.
4. **Multi-language support**: The document may use Python, TypeScript, shell, JSON, etc. — installation commands must match the language of the code block.
5. **Path accuracy**: Every `// <path>` comment uses the exact path the lecturer showed, not an invented one.
6. **Expected results are borrowed, not invented**: Every expected result / acceptance line (what the user sees or the terminal prints after a step) comes from the video — the subtitles or the frame at that timestamp. If the video never shows a verifiable outcome for a step, write the step without an expected result instead of guessing.

#### Re-generation on quality failure

If any quality check fails (warnings or errors), do not deliver. Instead:

1. Read the failed categories from the validation output.
2. Read the corresponding transcript chunks via `scripts/slice_transcript.py`.
3. Re-read [references/whisper.md](references/whisper.md) for model and transcription guidance.
4. Re-write the affected sections, following the Writing quality self-check rules above.
5. Re-run validation with `--strict` before delivering again.
6. If re-generation is needed more than once, update `work/logs/handoff.md` with the specific failure categories so a later context can resume without re-examining the video.

Deliver the final Markdown link first, followed by optional attachment and job-directory links. Do not generate PDF or LaTeX unless the user changes the requested deliverable and invokes an appropriate workflow.

## 常见错误处理

### 转录失败
- 检查视频文件是否完整
- 确认模型文件存在
- 尝试使用更小的模型（base而非small）

### 笔记不完整
- 运行 `scripts/check_inventory_coverage.py` 对照 `work/transcript/inventory.json`，定位哪些 chunk 的术语/命令/代码未进文档
- 重读对应 chunk 文本和其 inventory `points`，补充到受影响章节
- 字幕密度为 sparse 的 chunk：确认文档借助视频帧/界面描述补足了屏幕上的信息
- 验证是否所有 chunk 的 inventory 项都已被文档承接

### 质量检查失败（依赖命令缺失、引用视频、代码块无路径注释）
- 根据 `validate_delivery.py --strict` 的输出定位失败类别
- 重新读取对应转录块和 [references/whisper.md](references/whisper.md)
- 重写受影响章节：确保每个代码块有路径注释、依赖安装命令完整、文档自包含
- 更新 `work/logs/handoff.md` 记录失败类别
- 重新运行 `--strict` 验证通过后交付

### 链接验证失败
- 检查文件路径是否正确
- 确认所有引用的文件都在deliverables目录中
- 更新Markdown中的相对路径

## Stage handoff notes

A conversion job may span multiple sessions, models, or capabilities. Before switching context — changing model, closing a session, losing vision, or pausing for user input — persist a compact handoff file at `<work>/logs/handoff.md` (this file is a standard per-stage intermediate artifact, not a deliverable). It must contain:

- task goal and video identity: URL, BVID (or aid), part, duration, transcription provenance;
- completed steps with exact artifact paths under `<job-root>`;
- pending steps and their order;
- key decisions and environment traps: verified commands, the `scripts/setup.ps1` usage, dependency levels, GPU DLL workaround;
- the coarse frame → timestamp map and the proposed figure embedding points;
- the draft outline (chapter list) so a later context can continue writing without re-reading the whole transcript.

Keep the file to a single screen of prose plus tables; the aim is that a fresh model resumes the job without reading long chat history.

## Token discipline

- Keep command output narrow; save verbose logs to `work/logs/`.
- Exclude `.venv`, dependencies, models, and `work/temp` from recursive searches.
- Extract specific metadata fields instead of dumping JSON.
- Load transcript chunks once and write section summaries to disk.
- Use contact sheets for broad screening and original images only for finalists.
- Use minimal-context subagents with concise structured returns.
- Fix the outline and figure list before drafting; write once, then perform bounded validation.
- Do not create heartbeat automations for an ordinary one-run conversion.
