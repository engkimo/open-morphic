"""ToolState — whether a tool is enabled or masked for the current execution."""

from enum import Enum


class ToolState(str, Enum):
    ENABLED = "enabled"
    MASKED = "masked"
