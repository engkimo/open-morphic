"""InstallToolUseCase — search + score + install coordination."""

from __future__ import annotations

from dataclasses import dataclass

from domain.entities.tool_candidate import ToolCandidate
from domain.ports.tool_installer import InstallResult, ToolInstallerPort
from domain.ports.tool_registry import ToolRegistryPort, ToolSearchResult


@dataclass
class InstallByNameResult:
    """Result of a search-then-install flow."""

    search_result: ToolSearchResult
    install_result: InstallResult | None = None


class InstallToolUseCase:
    """Orchestrate: search registry → pick best → install."""

    def __init__(
        self,
        registry: ToolRegistryPort,
        installer: ToolInstallerPort,
    ) -> None:
        self._registry = registry
        self._installer = installer

    async def search(self, query: str, limit: int = 10) -> ToolSearchResult:
        """Search the registry for tools."""
        return await self._registry.search(query, limit=limit)

    async def install(self, candidate: ToolCandidate) -> InstallResult:
        """Install a specific tool candidate."""
        return await self._installer.install(candidate)

    async def install_by_name(self, name: str) -> InstallByNameResult:
        """Search for a tool by name and install the best match."""
        search_result = await self._registry.search(name, limit=5)
        if not search_result.candidates:
            return InstallByNameResult(
                search_result=search_result,
            )

        best = search_result.candidates[0]
        install_result = await self._installer.install(best)
        return InstallByNameResult(
            search_result=search_result,
            install_result=install_result,
        )

    async def uninstall(self, tool_name: str) -> InstallResult:
        """Uninstall a tool."""
        return await self._installer.uninstall(tool_name)

    def list_installed(self) -> list[ToolCandidate]:
        """List all installed tools."""
        return self._installer.list_installed()
