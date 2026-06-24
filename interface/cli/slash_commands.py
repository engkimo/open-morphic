"""Slash command parsing for Morphic Chat CLI."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SlashCommand:
    name: str
    args: str = ""


def parse_slash_command(text: str) -> SlashCommand:
    stripped = text.strip()
    if not stripped.startswith("/"):
        raise ValueError("slash command must start with '/'")
    body = stripped[1:]
    if not body:
        raise ValueError("slash command name must not be empty")
    name, _, args = body.partition(" ")
    return SlashCommand(name=name, args=args.strip())
