---
name: glasslite
description: Recall what the user saw on screen or heard/said in meetings and calls, from the local glasslite capture (Whisper transcripts, screenshots, saved summaries). Use when the user asks about something that just happened or was discussed earlier ("what did we decide in the meeting", "summarize the last 30 minutes", "what was on my screen", "who said X", "find when we talked about Y", 방금 회의, 아까 화면, 30분 요약), or asks to save a meeting summary.
---

# glasslite: local screen and speech memory

The `glasslite capture` process records the user's screen and speech on this machine. Query it with the `glasslite` CLI. Every command prints plain text, except `shot`, which prints an image file path.

| Need | Command |
|---|---|
| What happened recently (timeline) | `glasslite recent --minutes 30` |
| Find a keyword or phrase (Korean OK, newest first) | `glasslite search "견적서" --limit 20` |
| Look at a screen | `glasslite shot` (latest) or `glasslite shot 123`, then open the printed path with the Read tool |
| Save a summary you wrote so it is searchable later | `glasslite note "<text>"` |

If daily Markdown export is on, the same content is also under `~/.glasslite/notes/YYYY-MM-DD.md` (or `$GLASSLITE_HOME/notes`). Grep and Read work there for long ranges.

## How to answer

- Start with `recent` for "just now" questions and with `search` for a topic. Widen `--minutes` or try synonyms before you conclude something isn't there.
- Timeline lines look like `[time] (audio|screen|summary) text`. Screenshots appear as `[screenshot #ID]`. Open only the ones that matter. Each image costs context.
- Audio lines may start with `[me]` (the user's mic) or `[them]` (system audio, i.e. the other side of a call). Attribute statements to speakers that way.
- Transcripts come from Whisper and contain recognition errors. Read for meaning, and flag uncertain names, numbers, and dates instead of stating them as fact.
- Cite the times of the lines your answer relies on. If the capture doesn't contain the answer, say so.
- After you summarize a meeting, offer to store the summary with `glasslite note`.
- If `glasslite` is not found or prints nothing at all, capture may not be running. Tell the user to run `glasslite capture` (add `--loopback` for call audio).
