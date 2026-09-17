# Whisper fallback

Read this reference only when the requested video has no usable CC subtitles or the user asks for a fresh transcription.

## Model choice

- English-only audio: prefer an `.en` model such as `small.en`.
- Chinese or Chinese-English technical content: use multilingual `medium` or `large-v3`; never use an `.en` model. Multilingual `small` runs on Chinese but produces too many character errors for a lecture handout — treat it as a last resort and flag the quality risk in the handoff.
- CPU-first default: `small`/`small.en` with `faster-whisper` `compute_type="int8"`. For Chinese on CPU, `medium int8` is roughly 3-4x slower than `small`; budget for it or use a GPU.
- Prefer `medium` or `large-v3` only when the quality benefit justifies the extra compute and a suitable local model is available.

Set `language="zh"` or `language="en"` explicitly when the primary language is known. Do not rely on auto-detection for Chinese: short clips or clips that open with music are frequently mis-detected as English. For mixed technical content, provide a short initial prompt containing names and domain terms that actually occur in the video (this noticeably reduces proper-noun errors).

## Availability checks

Before network access, use this lookup order:

1. An explicit `--model-path`.
2. `output/_models/manifest.json` — inspect locally available models (run `scripts/transcribe_faster.py --list-models`).
3. `FASTER_WHISPER_MODEL_ROOT/faster-whisper-<model>` when the environment variable is set for cross-project reuse.
4. `<workspace>/output/_models/faster-whisper-<model>`.
5. A standard Whisper model already present in its cache.

Also check the active project Python environment for `faster_whisper`. Use the fastest available local path rather than installing duplicate packages per job.

Verify the interpreter before transcribing: run `<python> -c "import faster_whisper"`. A shell may resolve `python` to an empty virtualenv (on this workspace `.venv` is empty), which fails with "faster-whisper is not installed". Switch to the interpreter that already has the package instead of installing it into every job.

For project-shared packages installed with `pip --target`, use `<workspace>/output/_shared/python-packages/`. `scripts/transcribe_faster.py` discovers this directory automatically. For a shared package directory outside the project, set `BILIBILI_RENDER_MD_PYTHONPATH`.

Recommended shared layout:

```text
output/_models/
├─ faster-whisper-small.en/
├─ faster-whisper-small/
└─ faster-whisper-medium/
```

When a model was downloaded as an ordinary directory, load its resolved local path instead of its Hugging Face model ID:

```python
model = WhisperModel(
    str(model_path),
    device="cpu",
    compute_type="int8",
)
```

Do not assume an arbitrary local folder has Hugging Face cache layout.

Use `scripts/transcribe_faster.py` for the normal local-model path. It checks `<workspace>/output/_models/faster-whisper-<model>` first and refuses an implicit network download unless `--allow-download` is explicitly supplied.

For a model stored outside the current project, either pass `--model-path` or set `FASTER_WHISPER_MODEL_ROOT` to its parent directory. This keeps the skill portable without embedding a machine-specific absolute path.

## Output rules

Write raw ASR products to `work/transcript/`. Preserve timestamps in SRT or VTT. A plain TXT copy is optional; do not create multiple redundant formats unless a later deterministic tool needs them.

If an SRT is part of the delivery, copy the reviewed version to `deliverables/attachments/`; do not make the final Markdown link to `work/transcript/`.

Whisper is local compute and does not consume Codex tokens. Transcript text consumes Codex tokens only when loaded into model context, so chunk it before analysis.
