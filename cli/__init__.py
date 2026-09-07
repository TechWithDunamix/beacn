"""The `beacn` console.

Built on `sillo.console`. Command names are one to three space-separated tokens
(`beacn key create`, `beacn events publish`); `BeacnConsole` joins the leading
tokens into the registered name and hands everything else back to the framework.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sillo.console import Command, Console  # noqa: E402

from cli.commands import COMMANDS  # noqa: E402

__all__ = ["BeacnConsole", "build_console", "main"]


class BeacnConsole(Console):
    @property
    def _max_name_tokens(self) -> int:
        return max((len(name.split()) for name in self.commands), default=1)

    def _join_leading_tokens(self, tokens: list[str]) -> list[str]:
        for size in range(min(self._max_name_tokens, len(tokens)), 0, -1):
            candidate = " ".join(tokens[:size])
            if self.resolve(candidate) is not None:
                return [candidate, *tokens[size:]]
        return tokens

    def _prepare(self, argv: Sequence[str] | None) -> int | tuple[type[Command], object]:
        tokens = list(sys.argv[1:] if argv is None else argv)
        if tokens and tokens[0] not in ("-h", "--help", "help", "-V", "--version"):
            tokens = self._join_leading_tokens(tokens)
        return super()._prepare(tokens)


def build_console() -> Console:
    console = BeacnConsole(prog="beacn")
    for command in COMMANDS:
        console.add(command)
    return console


def main(argv: list[str] | None = None) -> int:
    return build_console().main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
