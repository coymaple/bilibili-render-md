# Long-video strategy

Read this reference when the selected material exceeds 20 minutes or contains more than 300 subtitle entries.

## Segment once

Prefer visible chapter boundaries, topic transitions, slide-title changes, or coherent subtitle windows. Add only the overlap needed to preserve an explanation that crosses a boundary.

Create a compact index with `scripts/slice_transcript.py`. Each segment should carry:

- start and end time;
- teaching goal;
- keywords;
- subtitle file or chunk path;
- candidate figure windows.

Do not repeatedly scan the full transcript after boundaries have been fixed.

## Minimal subagent contract

When subagents are available, pass only:

- the selected segment time range;
- the timestamped transcript chunk path;
- candidate-frame or contact-sheet paths;
- the user's requested output and scope;
- this return schema:

```text
teaching_goal
core_mechanisms
important_code_or_formulas
common_failures
figure_candidates: path + visible content + exact time + keep/reject reason
ambiguities
```

Use no full-history fork when a minimal task prompt is sufficient. Cap the response to the information needed for integration; do not ask for polished final prose from every segment.

The main agent must inspect final image candidates directly, reconcile overlaps, enforce the approved part boundary, and write one coherent document.

## Figure budget

Start with recall but bound the expensive stage:

1. Coarse sample for chapter orientation.
2. Identify high-value subtitle windows.
3. Generate roughly 10–15 candidates per concept window.
4. Use a contact sheet to retain 2–3 finalists.
5. Directly inspect nearby originals and keep the best complete frame.

The number of final figures is driven by teaching necessity, not a fixed quota. Avoid inspecting every frame at original detail.

