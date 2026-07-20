# Crux

A personal-use pipeline that generates NYT-Friday/Saturday-difficulty crossword
puzzles and packs them into a SQLite file for an offline mobile app to play.

It fills real, published NYT themeless grid patterns with high-quality answers
and clues drawn from decades of published crosswords, then grades and exports
each puzzle. No themes — the goal is hard puzzles with good clues.

## How it works

```
xd corpus (published puzzles)  ─┐
Collaborative Word List (MIT)  ─┼─►  ingest ─►  corpus.sqlite
Spread the Wordlist (CC-BY-NC) ─┘                    │
                                                      ▼
   grid pattern ─► backtracking fill ─► clue assignment ─► score ─► puzzles.sqlite
```

- **Grids** are real NYT Friday/Saturday black-square patterns (themeless, wide open).
- **Answers** come from a word list intersected with the NYT hard-clue bank, so
  every answer has a genuine Friday/Saturday clue available.
- **Clues** are chosen from published NYT hard clues, never revealing their answer.
- **Difficulty** is graded 1–5; in practice puzzles cluster at the hard end, by design.

## Usage

```bash
# 1. Fetch the corpus and wordlists (~174MB download, one time)
python -c "from pathlib import Path; from crossworder.fetch import download_all, extract_zip; \
download_all(Path('data/raw')); extract_zip(Path('data/raw/xd-puzzles.zip'), Path('data/raw/puzzles'))"

# 2. Build the normalized corpus database (a few minutes)
python -c "from pathlib import Path; from crossworder.ingest import build_corpus; \
build_corpus(Path('data/raw/puzzles'), [Path('data/raw/xwordlist.dict'), Path('data/raw/spreadthewordlist.dict')], Path('data/build/corpus.sqlite'))"

# 3. Generate a puzzle pack (slow — roughly one puzzle per 30–45s; resumable)
python -m crossworder.cli generate --count 500 --out data/build/puzzles.sqlite

# validate an existing pack
python -m crossworder.cli validate --pack data/build/puzzles.sqlite
```

Generation is safe to interrupt and resume — reruns against the same pack skip
grid patterns already used. `--max-seconds` caps total wall-clock for an
unattended overnight batch.

## Data licensing — personal use only

This repository contains **only code**. It downloads its data at runtime; none
of that data is committed here, and none of it should be redistributed.

- **xd corpus** (xd.saul.pw) — clue-answer pairs and grids scraped from
  published crosswords (NYT and others). Used here for personal, non-commercial
  purposes only.
- **Spread the Wordlist** — licensed **CC BY-NC-SA 4.0** (non-commercial).
- **Collaborative Word List** — MIT.

Because the clue data derives from published NYT puzzles and one source is
explicitly non-commercial, this project is for personal use and must not be
used commercially or have its generated packs redistributed.

## Tests

```bash
python -m pytest
```
