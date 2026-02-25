"""LAEE Tool Registry — maps tool names to async callables."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from infrastructure.local_execution.tools.dev_tools import (
    dev_docker,
    dev_env_setup,
    dev_git,
    dev_pkg_install,
)
from infrastructure.local_execution.tools.fs_tools import (
    fs_delete,
    fs_edit,
    fs_glob,
    fs_move,
    fs_read,
    fs_tree,
    fs_write,
)
from infrastructure.local_execution.tools.shell_tools import (
    shell_background,
    shell_exec,
    shell_pipe,
    shell_stream,
)
from infrastructure.local_execution.tools.system_tools import (
    system_clipboard_get,
    system_clipboard_set,
    system_notify,
    system_process_kill,
    system_process_list,
    system_resource_info,
    system_screenshot,
)

ToolFunc = Callable[[dict[str, Any]], Coroutine[Any, Any, str]]

TOOL_REGISTRY: dict[str, ToolFunc] = {
    # Shell
    "shell_exec": shell_exec,
    "shell_background": shell_background,
    "shell_stream": shell_stream,
    "shell_pipe": shell_pipe,
    # Filesystem
    "fs_read": fs_read,
    "fs_write": fs_write,
    "fs_edit": fs_edit,
    "fs_delete": fs_delete,
    "fs_move": fs_move,
    "fs_glob": fs_glob,
    "fs_tree": fs_tree,
    # System
    "system_process_list": system_process_list,
    "system_process_kill": system_process_kill,
    "system_resource_info": system_resource_info,
    "system_clipboard_get": system_clipboard_get,
    "system_clipboard_set": system_clipboard_set,
    "system_notify": system_notify,
    "system_screenshot": system_screenshot,
    # Dev
    "dev_git": dev_git,
    "dev_docker": dev_docker,
    "dev_pkg_install": dev_pkg_install,
    "dev_env_setup": dev_env_setup,
}

__all__ = ["TOOL_REGISTRY", "ToolFunc"]
