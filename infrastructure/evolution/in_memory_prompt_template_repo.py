"""In-memory PromptTemplateRepository — dict-backed for dev and testing."""

from __future__ import annotations

from domain.entities.prompt_template import PromptTemplate
from domain.ports.prompt_template_repository import PromptTemplateRepository


class InMemoryPromptTemplateRepository(PromptTemplateRepository):
    """Dict-backed PromptTemplateRepository."""

    def __init__(self) -> None:
        self._templates: dict[str, PromptTemplate] = {}  # keyed by id

    async def save(self, template: PromptTemplate) -> None:
        self._templates[template.id] = template

    async def get_latest(self, name: str) -> PromptTemplate | None:
        versions = [t for t in self._templates.values() if t.name == name]
        if not versions:
            return None
        return max(versions, key=lambda t: t.version)

    async def get_by_name_and_version(self, name: str, version: int) -> PromptTemplate | None:
        for t in self._templates.values():
            if t.name == name and t.version == version:
                return t
        return None

    async def list_by_name(self, name: str) -> list[PromptTemplate]:
        versions = [t for t in self._templates.values() if t.name == name]
        return sorted(versions, key=lambda t: t.version, reverse=True)

    async def list_all(self) -> list[PromptTemplate]:
        return sorted(
            self._templates.values(),
            key=lambda t: (t.name, -t.version),
        )
