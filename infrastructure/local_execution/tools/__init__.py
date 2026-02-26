"""LAEE Tool Registry — maps tool names to async callables."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from infrastructure.local_execution.tools.browser_tools import (
    browser_click,
    browser_extract,
    browser_navigate,
    browser_pdf,
    browser_screenshot,
    browser_type,
)
from infrastructure.local_execution.tools.cron_tools import (
    cron_cancel,
    cron_list,
    cron_once,
    cron_schedule,
)
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
from infrastructure.local_execution.tools.gui_tools import (
    gui_accessibility,
    gui_applescript,
    gui_open_app,
    gui_screenshot_ocr,
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
    # Shell (4)
    "shell_exec": shell_exec,
    "shell_background": shell_background,
    "shell_stream": shell_stream,
    "shell_pipe": shell_pipe,
    # Filesystem (7)
    "fs_read": fs_read,
    "fs_write": fs_write,
    "fs_edit": fs_edit,
    "fs_delete": fs_delete,
    "fs_move": fs_move,
    "fs_glob": fs_glob,
    "fs_tree": fs_tree,
    # System (7)
    "system_process_list": system_process_list,
    "system_process_kill": system_process_kill,
    "system_resource_info": system_resource_info,
    "system_clipboard_get": system_clipboard_get,
    "system_clipboard_set": system_clipboard_set,
    "system_notify": system_notify,
    "system_screenshot": system_screenshot,
    # Dev (4)
    "dev_git": dev_git,
    "dev_docker": dev_docker,
    "dev_pkg_install": dev_pkg_install,
    "dev_env_setup": dev_env_setup,
    # Browser (6) — v0.4
    "browser_navigate": browser_navigate,
    "browser_click": browser_click,
    "browser_type": browser_type,
    "browser_screenshot": browser_screenshot,
    "browser_extract": browser_extract,
    "browser_pdf": browser_pdf,
    # GUI (4) — v0.4
    "gui_applescript": gui_applescript,
    "gui_open_app": gui_open_app,
    "gui_screenshot_ocr": gui_screenshot_ocr,
    "gui_accessibility": gui_accessibility,
    # Cron (4) — v0.4
    "cron_schedule": cron_schedule,
    "cron_once": cron_once,
    "cron_list": cron_list,
    "cron_cancel": cron_cancel,
}

__all__ = ["TOOL_REGISTRY", "ToolFunc"]
