"""MCPToolInstaller — Install MCP server packages via npm/pip subprocess.

Safety gate: refuses SafetyTier.UNSAFE tools.
In-memory tracking of installed tools.
"""

from __future__ import annotations

import asyncio
import logging
import shlex

from domain.entities.tool_candidate import ToolCandidate
from domain.ports.tool_installer import InstallResult, ToolInstallerPort
from domain.value_objects.tool_safety import SafetyTier

logger = logging.getLogger(__name__)

# Safety gate: minimum tier to allow installation
_MIN_INSTALL_TIER = SafetyTier.EXPERIMENTAL


class MCPToolInstaller(ToolInstallerPort):
    """Install MCP tools via subprocess (npm/pip).

    Refuses UNSAFE tools. Tracks installed tools in memory.
    """

    def __init__(self, safety_threshold: SafetyTier = _MIN_INSTALL_TIER) -> None:
        self._threshold = safety_threshold
        self._installed: dict[str, ToolCandidate] = {}

    async def install(self, candidate: ToolCandidate) -> InstallResult:
        """Install tool if it passes safety gate."""
        # Safety gate
        if candidate.safety_tier < self._threshold:
            return InstallResult(
                tool_name=candidate.name,
                success=False,
                error=f"Blocked: safety tier {candidate.safety_tier.name} "
                f"below threshold {self._threshold.name}",
            )

        if self.is_installed(candidate.name):
            return InstallResult(
                tool_name=candidate.name,
                success=True,
                message="Already installed",
            )

        if not candidate.install_command:
            return InstallResult(
                tool_name=candidate.name,
                success=False,
                error="No install command available",
            )

        # Run install command
        result = await self._run_install(candidate)
        if result.success:
            self._installed[candidate.name] = candidate

        return result

    async def uninstall(self, tool_name: str) -> InstallResult:
        """Remove tool from installed tracking."""
        if tool_name not in self._installed:
            return InstallResult(
                tool_name=tool_name,
                success=False,
                error="Tool not installed",
            )

        candidate = self._installed.pop(tool_name)
        return InstallResult(
            tool_name=tool_name,
            success=True,
            message=f"Uninstalled {candidate.name}",
        )

    def list_installed(self) -> list[ToolCandidate]:
        """Return all installed tools."""
        return list(self._installed.values())

    def is_installed(self, tool_name: str) -> bool:
        """Check if tool is installed."""
        return tool_name in self._installed

    async def _run_install(self, candidate: ToolCandidate) -> InstallResult:
        """Execute install command as subprocess."""
        cmd = candidate.install_command
        logger.info("Installing %s: %s", candidate.name, cmd)

        try:
            parts = shlex.split(cmd)
            proc = await asyncio.create_subprocess_exec(
                *parts,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=120.0,
            )

            if proc.returncode == 0:
                return InstallResult(
                    tool_name=candidate.name,
                    success=True,
                    message=stdout_bytes.decode(errors="replace")[:500],
                    install_command=cmd,
                )
            return InstallResult(
                tool_name=candidate.name,
                success=False,
                install_command=cmd,
                error=stderr_bytes.decode(errors="replace")[:500],
            )

        except TimeoutError:
            return InstallResult(
                tool_name=candidate.name,
                success=False,
                install_command=cmd,
                error="Install timed out after 120s",
            )
        except FileNotFoundError as exc:
            return InstallResult(
                tool_name=candidate.name,
                success=False,
                install_command=cmd,
                error=f"Command not found: {exc}",
            )
        except Exception as exc:
            return InstallResult(
                tool_name=candidate.name,
                success=False,
                install_command=cmd,
                error=str(exc),
            )
