"""Command line entry point."""
from __future__ import annotations

import argparse
from pathlib import Path

from crossworder.export import generate, validate_pack


def main() -> None:
    parser = argparse.ArgumentParser(prog="crossworder")
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="generate puzzles into a pack")
    gen.add_argument("--corpus", type=Path, default=Path("data/build/corpus.sqlite"))
    gen.add_argument("--out", type=Path, default=Path("data/build/puzzles.sqlite"))
    gen.add_argument("--count", type=int, default=50)
    gen.add_argument("--size", type=int, default=15)
    gen.add_argument("--seed", type=int, default=0)
    gen.add_argument(
        "--max-seconds", type=float, default=None,
        help="overall wall-clock budget for the run; stop and return "
             "whatever was written once exceeded (default: no cap)",
    )
    gen.add_argument(
        "--pattern-time-budget", type=float, default=6.0,
        help="per-pattern fill time budget in seconds, split across "
             "max_restarts=4 attempts (default: 6.0)",
    )

    val = sub.add_parser("validate", help="validate an existing pack")
    val.add_argument("--pack", type=Path, default=Path("data/build/puzzles.sqlite"))

    args = parser.parse_args()
    if args.command == "generate":
        written = generate(
            args.corpus, args.out, args.count, args.size, args.seed,
            max_seconds=args.max_seconds,
            pattern_time_budget_s=args.pattern_time_budget,
        )
        print(f"wrote {written} puzzles to {args.out}")
        problems = validate_pack(args.out)
        print("validation:", "clean" if not problems else f"{len(problems)} problems")
        for problem in problems[:20]:
            print(" -", problem)
    else:
        problems = validate_pack(args.pack)
        print("validation:", "clean" if not problems else f"{len(problems)} problems")
        for problem in problems[:20]:
            print(" -", problem)


if __name__ == "__main__":
    main()
