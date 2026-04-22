"""PromptTemplateRepository port — storage for versioned prompt templates."""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.entities.prompt_template import PromptTemplate


class PromptTemplateRepository(ABC):
    """Port for storing and querying prompt templates."""

    @abstractmethod
    async def save(self, template: PromptTemplate) -> None:
        """Persist a prompt template (create or update metrics)."""
        ...

    @abstractmethod
    async def get_latest(self, name: str) -> PromptTemplate | None:
        """Get the latest version of a template by name."""
        ...

    @abstractmethod
    async def get_by_name_and_version(self, name: str, version: int) -> PromptTemplate | None:
        """Get a specific version of a template."""
        ...

    @abstractmethod
    async def list_by_name(self, name: str) -> list[PromptTemplate]:
        """List all versions of a template, newest first."""
        ...

    @abstractmethod
    async def list_all(self) -> list[PromptTemplate]:
        """List all templates across all names, newest first."""
        ...
