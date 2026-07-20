"""Choose clues for filled answers and grade the resulting puzzle."""
from __future__ import annotations

import random
import sqlite3
from collections import defaultdict
from pathlib import Path

from crossworder.grid import Slot


class ClueBank:
    def __init__(
        self,
        hard: dict[str, list[str]],
        easy: dict[str, list[str]],
        frequency: dict[str, int],
    ) -> None:
        self._hard = hard
        self._easy = easy
        self._frequency = frequency

    @classmethod
    def load(cls, db_path: Path) -> "ClueBank":
        con = sqlite3.connect(db_path)
        hard: dict[str, list[str]] = defaultdict(list)
        easy: dict[str, list[str]] = defaultdict(list)
        frequency: dict[str, int] = defaultdict(int)
        for answer, clue, is_hard in con.execute(
            "SELECT answer, clue, is_hard FROM clues"
        ):
            frequency[answer] += 1
            (hard if is_hard else easy)[answer].append(clue)
        con.close()
        return cls(dict(hard), dict(easy), dict(frequency))

    def frequency(self, answer: str) -> int:
        return self._frequency.get(answer, 0)

    def pick(self, answer: str, rng: random.Random) -> tuple[str, bool] | None:
        """Prefer a hard clue; never return one that gives away its answer."""
        for pool, from_hard in ((self._hard.get(answer, []), True),
                                (self._easy.get(answer, []), False)):
            usable = [c for c in pool if answer not in c.upper()]
            if usable:
                return rng.choice(usable), from_hard
        return None


def score_difficulty(
    answers: dict[int, str],
    hard_flags: dict[int, bool],
    bank: ClueBank,
    slots: list[Slot],
) -> int:
    """Grade 1 (easiest) to 5 (hardest)."""
    if not answers:
        return 1

    hard_share = sum(1 for v in hard_flags.values() if v) / len(hard_flags)

    # Rarer answers across the corpus are harder.
    freqs = [bank.frequency(a) for a in answers.values()]
    rare_share = sum(1 for f in freqs if f <= 5) / len(freqs)

    lengths = [len(a) for a in answers.values()]
    long_share = sum(1 for n in lengths if n >= 8) / len(lengths)

    raw = 0.5 * hard_share + 0.3 * rare_share + 0.2 * long_share
    return max(1, min(5, 1 + round(raw * 4)))
