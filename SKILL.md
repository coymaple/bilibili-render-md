---
name: bilibili-render-md
description: Turn a Bilibili lecture, tutorial, or technical video into structured Chinese Markdown notes with verified key frames, code, formulas, timestamps, and self-contained local assets. Use when the user provides a Bilibili URL or BV number and wants Markdown or 图文讲义; do not use when the required final deliverable is LaTeX/PDF.
---

本技能单点维护于 `.opencode/skills/bilibili-render-md`。修改 SKILL.md、scripts/、references/ 或 agents/ 下任何文件后，变更即生效。

# Bilibili Render Markdown

Create accurate, readable Chinese Markdown notes from the requested Bilibili video or selected parts. Preserve teaching value without producing a chronological transcript dump.

## Workspace and output invariant

Resolve the workspace at runtime:

- Default to the current working directory.
- If the user names another project directory, use that directory only after resolving it.
- Never hard-code a prior workspace, user profile, drive letter, or output path.
- Keep every task under `<workspace>/output/<job-id>/`.

Initialize the task with `scripts/init_job.py`. Use `<BVID>_P<n>` for one part and `<BVID>_FULL` only when the user explicitly requests the full video.

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

### 1. Inspect before downloading

Inspect compact metadata first: title, BVID, part list, duration, cover, subtitle tracks, and usable formats. Do not print full platform JSON into the conversation; save it under `source/metadata/` and return only the needed fields.

For a multi-part video, list the parts and ask which range to process before downloading media. Do not infer full-series authorization from one URL.

Prefer the highest usable public format. Request browser-cookie access only when public quality is inadequate for readable teaching figures or the user explicitly requests login-gated quality. Never export or persist browser cookies.

### 2. Acquire text with bounded fallback

Use this order:

1. Platform CC subtitles, preserving timestamps.
2. Local Whisper transcription.
3. Visual-only analysis when audio is unusable.

If Whisper is needed, read [references/whisper.md](references/whisper.md) before installing, downloading, or transcribing. Check local packages and local model paths before any network action. Stop repeated model-download attempts after one official endpoint and at most one user-approved fallback; use an already available model when possible. On this workspace, load `scripts/setup.ps1` to prepare the Python 3.13 environment, the shared packages path, and the CUDA runtime DLL path before running a transcription.

#### 模型选择指南

| 内容类型 | 推荐模型 | 原因 |
|---------|---------|------|
| 纯英文 | small.en | 质量更好，速度适中 |
| 中英混合 | small | 支持多语言 |
| CPU-only | base/int8 | 速度优先 |
| GPU可用 | small/float16 | 质量优先 |

#### CPU-only模式

当GPU不可用时：
1. 使用`--device cpu`参数
2. 使用`--compute-type int8`提高速度
3. 预期处理时间：每10分钟视频约需2-3分钟
4. 质量略有下降，但足够用于笔记生成

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

### 4. Handle long videos efficiently

When duration exceeds 20 minutes or subtitles exceed 300 entries, read [references/long-video.md](references/long-video.md). Split by real teaching boundaries, not arbitrary equal chunks when chapters are visible.

When subagents are available, give them minimal context: paths, exact time range, task rubric, and a strict return schema. Do not fork the full thread history. The main agent owns the unified outline, deduplication, factual reconciliation, and final prose.

### 5. Locate and verify figures

Use subtitle timestamps to identify high-value windows. First create coarse chapter coverage, then densely sample only short concept windows. Avoid exhaustive high-resolution inspection of every candidate.

This step assumes a vision-capable model; otherwise apply the fallback in the "Detect vision capability" section above.

Use contact sheets for recall, then directly inspect several nearby original frames before selecting one. Reject frames that are incomplete, transitional, unreadable, redundant, error-filled, or expose secrets or private data. Do not use OCR as a substitute for visual understanding.

Name raw frames by timestamp. Assign a semantic filename only after the image has been visually confirmed. Copy selected figures to `deliverables/assets/figures/` and record the source time or subtitle-aligned interval in the Markdown caption.

### 6. Write the notes

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

Use the exact path the lecturer presents (project-relative when possible). Terminal commands and other code blocks not tied to a file need no path annotation.

When the lecturer modifies a file that was already shown earlier in the video, do not silently dump the whole file again. Instead:

- Add the same path comment on the block.
- If the file is small or the whole file is on screen, show it once with the path comment.
- If only part of the file is relevant or the file is large, retain its structure while omitting unchanged regions: keep the surrounding unchanged lines for context and replace the omitted span with an ellipsis, for example `  // …` inside code or a short note such as `（原文件其余部分未改动，已省略）`.
- Always make the newly changed lines visually explicit, by preferring a short leading marker in a comment line such as `// [改动]`, `# [改动]`, or `/* [改动] */`. Mark only what changed in this part of the video, not the whole file.
- Keep anything a previously-shown block already established; do not repeat unchanged content verbatim.

Do not invent changes beyond what the lecturer actually did; if only one line changes, show that single change with context and state that the rest was untouched.

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
- `<BVID>`: the video's unchanged BV number (for example `BV1HoN6eREQ2`).
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

### 8. Validate before delivery

Run `scripts/validate_delivery.py --job-root <job-root> --markdown <final-md>`.

Confirm that:

- every local Markdown link resolves;
- every relative local link stays inside `deliverables/`;
- final Markdown is under `deliverables/docs/`;
- selected figures match the surrounding explanation;
- no secrets, tokens, cookie values, email addresses, private endpoints, or personal identifiers appear;
- the notes do not exceed the user-approved part range;
- original and intermediate files remain outside `deliverables/`.

Deliver the final Markdown link first, followed by optional attachment and job-directory links. Do not generate PDF or LaTeX unless the user changes the requested deliverable and invokes an appropriate workflow.

## 常见错误处理

### 转录失败
- 检查视频文件是否完整
- 确认模型文件存在
- 尝试使用更小的模型（base而非small）

### 笔记不完整
- 读取更多转录块
- 检查是否覆盖了所有主要教学点
- 验证代码示例是否完整

### 链接验证失败
- 检查文件路径是否正确
- 确认所有引用的文件都在deliverables目录中
- 更新Markdown中的相对路径

## Stage handoff notes

A conversion job may span multiple sessions, models, or capabilities. Before switching context — changing model, closing a session, losing vision, or pausing for user input — persist a compact handoff file at `<work>/logs/handoff.md` (this file is a standard per-stage intermediate artifact, not a deliverable). It must contain:

- task goal and video identity: URL, BVID, part, duration, transcription provenance;
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
