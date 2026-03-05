"""ToolInstallerPort — abstract interface for installing tools.

Domain defines WHAT it needs. Infrastructure provides HOW.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from domain.entities.tool_candidate import ToolCandidate


@dataclass
class InstallResult:
    """Result from a tool installation attempt."""

    tool_name: str
    success: bool
    message: str = ""
    install_command: str = ""
    error: str | None = None


class ToolInstallerPort(ABC):
    """Port for installing and managing marketplace tools."""

    @abstractmethod
    async def install(self, candidate: ToolCandidate) -> InstallResult:
        """Install a tool from a candidate.

        Args:
            candidate: The tool to install (must pass safety gate).

        Returns:
            InstallResult indicating success or failure.
        """
        ...

    @abstractmethod
    async def uninstall(self, tool_name: str) -> InstallResult:
        """Uninstall a previously installed tool.

        Args:
            tool_name: Name of the tool to remove.

        Returns:
            InstallResult indicating success or failure.
        """
        ...

    @abstractmethod
    def list_installed(self) -> list[ToolCandidate]:
        """Return all currently installed tools."""
        ...

    @abstractmethod
    def is_installed(self, tool_name: str) -> bool:
        """Check if a tool is already installed."""
        ...
