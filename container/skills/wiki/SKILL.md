---
name: wiki
description: Maintain the persistent personal wiki (Karpathy LLM Wiki pattern). Use when the user shares a source (URL, PDF, Office doc, image, voice note, pasted text or transcript) to ingest, asks a question the wiki might answer, or asks for a wiki health check (lint).
---

# Wiki maintainer

You own a persistent, interlinked markdown wiki in `/workspace/agent/wiki/`. Raw material lives in `/workspace/agent/sources/` and is **immutable** — read it, never edit it. Knowledge is compiled into the wiki once and kept current, not re-derived per question.

Domain: personal / general (goals, health, self-improvement, things the user reads and learns).

## Layout

- `sources/` — raw files exactly as received. Name: `YYYY-MM-DD-short-slug.<ext>`.
- `wiki/index.md` — catalog of every page: link + one-line summary, grouped by category. Read it first when answering.
- `wiki/log.md` — append-only. Entries start `## [YYYY-MM-DD] ingest|query|lint | Title`.
- `wiki/sources/<slug>.md` — one summary page per source (what it is, key claims, link to the raw file).
- `wiki/entities/` — people, places, orgs, products. `wiki/concepts/` — ideas, topics. `wiki/syntheses/` — comparisons, analyses, filed-back answers.
- Pages are markdown with YAML frontmatter (`title`, `type`, `updated`, `sources: []`) and `[[wikilinks]]`-style relative links so they work in Obsidian.

Create folders as needed. Keep conventions simple; adapt if the user asks.

## Ingest

Process **one source at a time**, fully, before starting the next. If given several files or a folder, loop: never batch-read everything and then summarise together — that yields shallow pages.

For each source:
1. Get the full content into `sources/` (see Getting content). Read it in full.
2. Tell the user the key takeaways in a few lines; ask only if direction is genuinely unclear.
3. Write `wiki/sources/<slug>.md`.
4. Create or update every relevant entity and concept page — revise summaries, add cross-references both ways, and **flag contradictions** with earlier pages explicitly (cite both sources). A single source commonly touches 5–15 pages.
5. Update `wiki/index.md`.
6. Append to `wiki/log.md`.
7. Only then move on.

### Getting content
- **URLs:** WebFetch returns a summary, not the document. Download the full text instead: `curl -sLo /workspace/agent/sources/<name> "<url>"` for files/PDFs; for web pages use `agent-browser` to open the page and extract the full text, saving it as markdown in `sources/`.
- **PDFs / Office docs:** attachments arrive in `/workspace/inbox/<id>/`; copy to `sources/`, then extract text (e.g. `pdftotext`, or an installed doc-conversion tool). If you cannot read a format, say so rather than guessing.
- **Images:** copy to `sources/`, view them directly, and write a description into the source page.
- **Voice notes:** copy to `sources/`; if no transcription capability is available, tell the user instead of inventing a transcript.
- **Pasted text / transcripts:** save verbatim to `sources/` as `.md` first.

## Query

1. Read `wiki/index.md`, then the relevant pages. Search with `grep -ri` if the index isn't enough.
2. Answer with citations to wiki pages (and through them, sources).
3. If the answer is a useful synthesis, offer to file it as `wiki/syntheses/<slug>.md` (update index + log) so the exploration compounds.
4. Log meaningful queries.
5. Say plainly when the wiki lacks the answer; don't fill gaps from memory without labelling it.

## Lint

Periodic health check. Look for: contradictions between pages, claims superseded by newer sources, orphan pages with no inbound links, important concepts mentioned but lacking a page, missing cross-references, pages missing from the index, data gaps. Fix mechanical issues directly; report judgment calls and suggest sources or questions to investigate. Log a `lint` entry with a short summary.

## Rules

- Never modify files in `sources/`.
- Every page change is reflected in `index.md` and `log.md`.
- Keep replies to the user short: outcome first (pages created/updated, contradictions found).
