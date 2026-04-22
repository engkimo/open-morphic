"""ToolSchema — JSON Schema definitions for LLM tool calling."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ParameterProperty:
    """A single parameter in a tool's JSON schema."""

    type: str
    description: str = ""
    enum: list[str] | None = None
    default: Any = None
    items: dict[str, Any] | None = None


@dataclass(frozen=True)
class ToolSchema:
    """Schema for a single tool, convertible to OpenAI tool format."""

    name: str
    description: str
    properties: dict[str, ParameterProperty] = field(default_factory=dict)
    required: list[str] = field(default_factory=list)

    def to_openai_tool(self) -> dict[str, Any]:
        """Convert to OpenAI-compatible tool definition (pure, no I/O)."""
        props: dict[str, Any] = {}
        for param_name, prop in self.properties.items():
            schema: dict[str, Any] = {"type": prop.type, "description": prop.description}
            if prop.enum is not None:
                schema["enum"] = prop.enum
            if prop.default is not None:
                schema["default"] = prop.default
            if prop.items is not None:
                schema["items"] = prop.items
            props[param_name] = schema

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": props,
                    "required": self.required,
                },
            },
        }
