# Crossworder — Design Spec

Date: 2026-07-20
Status: Approved sections 1–4 in brainstorming; pending final spec review.

## Overview

A personal-use mobile crossword app (Flutter) with NYT-Friday/Saturday difficulty and clue quality. No themes required. Puzzles are auto-generated offline by a desktop Python pipeline from free crossword databases and shipped to the app as a SQLite pack. Unlimited on-demand play, mostly 15x15 with occasional 21x21.

Working name candidates: Crux (preferred), Gridlock, Saturday, Stumper, Downright, Blacksquare.

Non-goals: publishing to app stores, multiplayer, accounts, network features, themed puzzles.

Licensing posture: personal use only, so scraped published-clue corpora (xd corpus) are acceptable. If the app is ever published, the clue source must be replaced with openly licensed data.

## Data sources (all free)

All source facts below were verified by download and inspection on 2026-07-20.

Primary source — **xd-puzzles.zip** (https://xd.saul.pw/xd-puzzles.zip, 93MB):
the single most important correction to the original plan. The xd website
describes this archive as "over 6000 pre-1965 New York Times crossword puzzles",
but it actually contains **89,662 puzzles across 33 publications**, extracted to
a `gxd/<publication>/<year>/` tree. NYT coverage is **28,337 puzzles spanning
1942–2025**, of which **11,688 are Shortz-era (1994+)**.

Each `.xd` file is plain text containing everything needed in one place: a
`Date:` header, the black-square grid as ASCII rows (`#` = black), and every
clue paired to its answer as `A1. Clue text ~ ANSWER`. This yields grids,
clues, and weekday from a single parse.

Measured Friday/Saturday (hard) inventory, Shortz era:
- 3,339 Fri/Sat puzzles
- **231,063 Fri/Sat clue-answer pairs** over 71,328 distinct answers
- **2,906 distinct real 15x15 Fri/Sat black-square patterns** (themeless, wide open)

Fill wordlists (both format `WORD;score`, score 0–100):
- **Collaborative Word List** — https://raw.githubusercontent.com/Crossword-Nexus/collaborative-word-list/main/xwordlist.dict — 566,665 valid entries, **MIT licensed**.
- **Spread the Wordlist** — https://drive.google.com/uc?export=download&id=1f0XZ0xRJ37UdxbLsmckYqUJUf_R7pQcs (linked from spreadthewordlist.com) — 315,899 valid entries, **CC BY-NC-SA 4.0** (non-commercial; acceptable for personal use, blocks commercial release).

Merged and filtered to score >= 50: **285,536 usable fill entries**, with good
coverage at every length including 17,213 fifteen-letter entries (needed for
themeless spanners).

**Not used, and why:**
- *xd-clues.zip* (8M rows) was the originally specified clue source, but its schema is only `pubid, year, answer, clue` — **no date, no weekday, and no puzzle ID**. Weekday-based difficulty filtering is therefore impossible from this file, and clues cannot be joined back to puzzles. Superseded by parsing `.xd` files directly.
- *xd-metadata.zip* `puzzles.tsv` contains metadata only (xdid, date, size, title, author) — **no grid layouts**. Cannot supply grid patterns.
- *Peter Broda's Wordlist* — the domain `peterbroda.me` is **unreachable as of 2026-07-20** (connection fails, not merely a moved path). Dropped; the two wordlists above cover the need.

Difficulty signal: NYT difficulty ramps Monday→Saturday, so restricting to
Friday/Saturday Shortz-era puzzles yields the hard clue bank. Answer obscurity
(inverse frequency across the full corpus) is a second hardness signal.

Bonus: the app can import `.puz` files, so free indie puzzles are also playable.

## Critical constraint: fill must be clue-aware

Measured overlap between the score>=50 wordlist and the Fri/Sat clue bank is
**56,632 answers** (avg 3.5 hard clues each) — only about 20% of the 285,536
fillable entries have a Friday/Saturday clue available.

This drives a core design decision: **the filler must draw candidates from the
clue-covered set, not from the full wordlist.** A filler that optimises purely
for fill score will produce grids full of answers that have no hard clue, forcing
either weak clues or unclued slots. The candidate pool is therefore
`wordlist(score>=50) ∩ clue_bank`, with the full wordlist used only as a
last-resort fallback for otherwise-unfillable slots (such answers then draw
clues from the wider non-Fri/Sat corpus and are penalised in difficulty scoring).

Overlap is thinnest at lengths 11–14 (2,058 / 516 / 623 / 243 entries) and
notably better at 15 (2,127). Grid patterns whose slot-length profile demands
many 12–14 letter answers should be deprioritised during pattern selection.

## Generation pipeline (Python, desktop)

1. **Ingest** — download `xd-puzzles.zip` and both wordlists once; parse the `gxd/nytimes/**` tree into local SQLite: `clues(answer, clue, weekday, year, is_hard)`, `words(answer, score)`, `grids(pattern, size, source_date)`. Dedupe, uppercase, strip non A–Z answers.
2. **Grid pick** — sample a real black-square pattern from the 2,906 extracted Fri/Sat layouts (15x15 default; 21x21 sourced from Sunday grids). Patterns come from published puzzles so symmetry and connectivity are inherent, but are re-validated on ingest; files with irregular row counts (a small minority) are rejected.
3. **Fill** — backtracking search: most-constrained slot first; candidates from the clue-covered pool described above, indexed by letter pattern; prefer high fill score. Retry with a new grid on dead ends. 21x21 runs as overnight batch.
4. **Clue assignment** — per answer, choose from the clue bank, preferring Fri/Sat-sourced clues and rarer clue-answer pairings; never pick a clue containing its own answer. Note that clues referring to a grid position ("See 17-Across") or to a puzzle theme are meaningless out of context and must be filtered out at ingest.
5. **Difficulty scoring 1–5** — combination of share of clues sourced from Fri/Sat, average answer obscurity (inverse corpus frequency), share of long answers, grid openness, and a penalty for fallback answers clued from outside the hard bank.
6. **Export** — `puzzles.sqlite` with grid, solution, clues, difficulty, size; batches of 500+. Also emit `.puz`-compatible JSON.
7. **Curation (optional)** — CLI preview to reject bad fills before export.

The pipeline can be rerun anytime to produce a fresh pack; the app imports the new file.

## Flutter app

Screens:

1. **Home / puzzle list** — two tabs.
   - *In Progress*: every started puzzle with size, difficulty, completion % (filled cells / total fillable cells), time spent, last played. Tap to resume exact state. Autosave on every letter; leaving a puzzle mid-solve is a first-class flow.
   - *Library*: unplayed puzzles, filterable by difficulty (1–5) and size; "random hard" quick-start.
2. **Solve screen**
   - Grid rendered with `CustomPaint`; pinch-zoom (needed for 21x21); current-cell and current-word highlight; tapping the active cell toggles across/down.
   - Clue bar above keyboard with prev/next clue navigation.
   - Custom in-app keyboard (no system keyboard, no autocorrect).
   - Tools: timer (pausing hides the grid), pencil mode, check letter/word/puzzle, reveal letter/word/puzzle, and a hard-mode toggle that disables check/reveal.
   - Back always returns to the list with state saved.
3. **Stats** — solve counts, average time per difficulty, streak, completion history.
4. **Settings** — theme, import new puzzle pack, import `.puz`, error-check behavior.

State and storage: `drift` (SQLite). Read-only pack tables plus a `progress` table (puzzle_id, per-cell entries, elapsed time, pencil flags, completed_at) kept in a separate DB file so pack swaps never touch progress. Riverpod for state management. Fully offline.

## Data flow, error handling, testing

Data flow: pipeline emits `puzzles.sqlite` → bundled as asset or imported via file picker → copied to app documents dir on first run → drift reads pack, writes progress to its own DB file.

Error handling:
- Pipeline: unfillable grid → retry up to 50 restarts then skip pattern and log; answers lacking clues are excluded during fill, never after.
- App: corrupt or missing pack → import prompt, no crash; progress writes are transactional; malformed `.puz` imports rejected with a message.

Testing:
- Pipeline (pytest): every exported puzzle validated — solution matches grid, all slots clued, symmetry, connectivity, no duplicate answers within a puzzle.
- App: unit tests for grid navigation (next cell, word jump, wrap) and completion % calculation; widget test for solve-screen basics.
