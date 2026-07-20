"""The candidate pool the filler draws from.

Only answers that have at least one hard (Fri/Sat) clue are offered as primary
candidates. Filling from the raw wordlist produces grids full of answers with
no usable clue, which is the failure mode this class exists to prevent.
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from pathlib import Path


class CandidatePool:
    def __init__(
        self,
        scores: dict[str, int],
        hard_answers: set[str],
    ) -> None:
        self._scores = scores
        self._hard = hard_answers
        self._covered_by_length: dict[int, list[str]] = defaultdict(list)
        self._all_by_length: dict[int, list[str]] = defaultdict(list)

        for answer, score in sorted(scores.items(), key=lambda kv: -kv[1]):
            self._all_by_length[len(answer)].append(answer)
            if answer in hard_answers:
                self._covered_by_length[len(answer)].append(answer)

        self._build_index()

    @classmethod
    def load(cls, db_path: Path, min_score: int = 50) -> "CandidatePool":
        con = sqlite3.connect(db_path)
        scores = {
            answer: score
            for answer, score in con.execute(
                "SELECT answer, score FROM words WHERE score >= ?", (min_score,)
            )
        }
        hard = {
            row[0]
            for row in con.execute(
                "SELECT DISTINCT answer FROM clues WHERE is_hard = 1"
            )
        }
        con.close()
        return cls(scores, hard)

    def by_length(self, length: int) -> list[str]:
        return self._covered_by_length.get(length, [])

    def score(self, answer: str) -> int:
        return self._scores.get(answer, 0)

    def has_hard_clue(self, answer: str) -> bool:
        return answer in self._hard

    def _build_index(self) -> None:
        """Index (length, position, letter) -> set of word offsets.

        A linear scan per lookup was measured at ~4ms; the filler performs one
        lookup per unfilled slot per search node (~70 per node), which is far
        too slow to fill a 15x15. This index makes lookups set intersections.
        """
        self._index: dict[int, dict[tuple[int, str], set[int]]] = {}
        for length, words in self._covered_by_length.items():
            table: dict[tuple[int, str], set[int]] = {}
            for offset, word in enumerate(words):
                for position, letter in enumerate(word):
                    table.setdefault((position, letter), set()).add(offset)
            self._index[length] = table

    def matching(self, pattern: str) -> list[str]:
        length = len(pattern)
        words = self._covered_by_length.get(length, [])
        if not words:
            return []
        known = [(p, c) for p, c in enumerate(pattern) if c != "?"]
        if not known:
            return words
        table = self._index.get(length, {})
        sets = sorted((table.get(k, set()) for k in known), key=len)
        result = set(sets[0])
        for other in sets[1:]:
            result &= other
            if not result:
                return []
        return [words[i] for i in result]

    @staticmethod
    def _matches(answer: str, pattern: str) -> bool:
        return all(p == "?" or p == a for p, a in zip(pattern, answer))

    def fallback_matching(self, pattern: str) -> list[str]:
        return [
            a
            for a in self._all_by_length.get(len(pattern), [])
            if self._matches(a, pattern)
        ]
