# Crossworder — Design Spec

Date: 2026-07-20
Status: Approved sections 1–4 in brainstorming; pending final spec review.

## Overview

A personal-use mobile crossword app (Flutter) with NYT-Friday/Saturday difficulty and clue quality. No themes required. Puzzles are auto-generated offline by a desktop Python pipeline from free crossword databases and shipped to the app as a SQLite pack. Unlimited on-demand play, mostly 15x15 with occasional 21x21.

Working name candidates: Crux (preferred), Gridlock, Saturday, Stumper, Downright, Blacksquare.

Non-goals: publishing to app stores, multiplayer, accounts, network features, themed puzzles.

Licensing posture: personal use only, so scraped published-clue corpora (xd corpus) are acceptable. If the app is ever published, the clue source must be replaced with openly licensed data.

## Data sources (all free)

Clues and answers:

1. **xd corpus** (xd.saul.pw) — ~7M clue-answer pairs from decades of published puzzles (NYT, LA Times, WSJ, Universal, and more), TSV download. Each row carries publication and date. Primary clue bank.
2. **Peter Broda's Wordlist** — ~400k answers scored 0–100 for fill quality. Primary fill wordlist.
3. **Spread the Wordlist** (Husic/Henestroza) — ~120k curated scored entries, modern vocabulary. Merged with Broda.
4. **Collaborative Word List** (Crossword Nexus, GitHub) — additional open scoring signal.

Grid designs:

5. Black-square layouts extracted from xd corpus puzzles — thousands of real, proven, symmetric 15x15 and 21x21 patterns. No grid invention needed.

Difficulty signal:

6. NYT clues in the xd corpus carry a date, hence a weekday; NYT difficulty ramps Monday→Saturday. Filtering to Friday/Saturday clues yields a hard-clue bank. Clue-answer pairing rarity across the corpus is a second hardness signal.

Bonus: the app can import `.puz` files, so free indie puzzles (e.g., Crosshare) are also playable.

## Generation pipeline (Python, desktop)

1. **Ingest** — one-time download of xd corpus + wordlists into local SQLite: `clues(answer, clue, source, date, weekday)`, `words(answer, score)`. Dedupe, uppercase, strip non A–Z answers.
2. **Grid pick** — sample a real black-square pattern from extracted xd layouts (15x15 default, 21x21 sometimes). Enforce symmetry, connectivity, minimum 3-letter words.
3. **Fill** — backtracking search: most-constrained slot first; candidates come from the merged wordlist indexed by letter pattern; prefer high fill score and answers present in the clue bank. Retry with a new grid on dead ends. 21x21 runs as overnight batch.
4. **Clue assignment** — per answer, choose from the clue bank. Hard mode prefers Fri/Sat-sourced clues and rare clue-answer pairings; never pick a clue containing its answer.
5. **Difficulty scoring 1–5** — combination of average weekday of chosen clues, average answer obscurity (inverse corpus frequency), share of long answers, grid openness.
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
