"""Tool JSON schemas — OpenAI-compatible definitions for all LAEE tools.

Hand-written schemas so LLMs can correctly select and parameterize tools.
"""

from __future__ import annotations

from domain.entities.tool_schema import ParameterProperty, ToolSchema

TOOL_SCHEMAS: dict[str, ToolSchema] = {
    # ── Web tools (NEW) ──
    "web_search": ToolSchema(
        name="web_search",
        description=(
            "Search the web for real-time information."
            " Use this to find current data, prices, news, etc."
        ),
        properties={
            "query": ParameterProperty(type="string", description="The search query"),
            "max_results": ParameterProperty(
                type="integer", description="Maximum number of results (default 5)", default=5
            ),
        },
        required=["query"],
    ),
    "web_fetch": ToolSchema(
        name="web_fetch",
        description=(
            "Fetch the full text content of a URL. Use after web_search to read a specific page."
        ),
        properties={
            "url": ParameterProperty(type="string", description="The URL to fetch"),
            "max_length": ParameterProperty(
                type="integer",
                description="Maximum characters to return (default 20000)",
                default=20000,
            ),
        },
        required=["url"],
    ),
    # ── Shell tools ──
    "shell_exec": ToolSchema(
        name="shell_exec",
        description=(
            "Execute a shell command and return stdout. Use for running scripts, calculations, etc."
        ),
        properties={
            "cmd": ParameterProperty(type="string", description="Shell command to execute"),
            "timeout": ParameterProperty(
                type="integer", description="Timeout in seconds (default 30)", default=30
            ),
            "cwd": ParameterProperty(type="string", description="Working directory (optional)"),
        },
        required=["cmd"],
    ),
    "shell_background": ToolSchema(
        name="shell_background",
        description="Start a command in the background, return its PID.",
        properties={
            "cmd": ParameterProperty(type="string", description="Shell command to run"),
            "cwd": ParameterProperty(type="string", description="Working directory (optional)"),
        },
        required=["cmd"],
    ),
    "shell_stream": ToolSchema(
        name="shell_stream",
        description="Execute command with merged stdout+stderr output.",
        properties={
            "cmd": ParameterProperty(type="string", description="Shell command"),
            "timeout": ParameterProperty(
                type="integer", description="Timeout in seconds", default=30
            ),
            "cwd": ParameterProperty(type="string", description="Working directory (optional)"),
        },
        required=["cmd"],
    ),
    "shell_pipe": ToolSchema(
        name="shell_pipe",
        description="Execute a pipeline of piped shell commands.",
        properties={
            "cmds": ParameterProperty(
                type="array",
                description="List of commands to pipe together",
                items={"type": "string"},
            ),
            "timeout": ParameterProperty(
                type="integer", description="Timeout in seconds", default=30
            ),
        },
        required=["cmds"],
    ),
    # ── Filesystem tools ──
    "fs_read": ToolSchema(
        name="fs_read",
        description="Read the contents of a file.",
        properties={
            "path": ParameterProperty(type="string", description="File path to read"),
            "encoding": ParameterProperty(
                type="string", description="Encoding (default utf-8)", default="utf-8"
            ),
        },
        required=["path"],
    ),
    "fs_write": ToolSchema(
        name="fs_write",
        description="Write content to a file (creates or overwrites).",
        properties={
            "path": ParameterProperty(type="string", description="File path"),
            "content": ParameterProperty(type="string", description="Content to write"),
        },
        required=["path", "content"],
    ),
    "fs_edit": ToolSchema(
        name="fs_edit",
        description="Replace text in a file (sed-like).",
        properties={
            "path": ParameterProperty(type="string", description="File path"),
            "old": ParameterProperty(type="string", description="Text to find"),
            "new": ParameterProperty(type="string", description="Replacement text"),
        },
        required=["path", "old", "new"],
    ),
    "fs_delete": ToolSchema(
        name="fs_delete",
        description="Delete a file or directory.",
        properties={
            "path": ParameterProperty(type="string", description="Path to delete"),
        },
        required=["path"],
    ),
    "fs_move": ToolSchema(
        name="fs_move",
        description="Move or rename a file/directory.",
        properties={
            "src": ParameterProperty(type="string", description="Source path"),
            "dst": ParameterProperty(type="string", description="Destination path"),
        },
        required=["src", "dst"],
    ),
    "fs_glob": ToolSchema(
        name="fs_glob",
        description="Find files matching a glob pattern.",
        properties={
            "pattern": ParameterProperty(
                type="string", description="Glob pattern (e.g. '**/*.py')"
            ),
            "root": ParameterProperty(type="string", description="Root directory (default '.')"),
        },
        required=["pattern"],
    ),
    "fs_tree": ToolSchema(
        name="fs_tree",
        description="Display directory tree structure.",
        properties={
            "path": ParameterProperty(type="string", description="Directory path"),
            "max_depth": ParameterProperty(
                type="integer", description="Max depth (default 3)", default=3
            ),
        },
        required=["path"],
    ),
    # ── System tools ──
    "system_process_list": ToolSchema(
        name="system_process_list",
        description="List running processes.",
        properties={},
    ),
    "system_process_kill": ToolSchema(
        name="system_process_kill",
        description="Kill a process by PID.",
        properties={
            "pid": ParameterProperty(type="integer", description="Process ID to kill"),
        },
        required=["pid"],
    ),
    "system_resource_info": ToolSchema(
        name="system_resource_info",
        description="Get CPU, memory, and disk usage info.",
        properties={},
    ),
    "system_clipboard_get": ToolSchema(
        name="system_clipboard_get",
        description="Read clipboard contents.",
        properties={},
    ),
    "system_clipboard_set": ToolSchema(
        name="system_clipboard_set",
        description="Set clipboard contents.",
        properties={
            "content": ParameterProperty(type="string", description="Content for clipboard"),
        },
        required=["content"],
    ),
    "system_notify": ToolSchema(
        name="system_notify",
        description="Send a desktop notification.",
        properties={
            "title": ParameterProperty(type="string", description="Notification title"),
            "message": ParameterProperty(type="string", description="Notification message"),
        },
        required=["message"],
    ),
    "system_screenshot": ToolSchema(
        name="system_screenshot",
        description="Take a screenshot of the entire screen.",
        properties={
            "output_path": ParameterProperty(type="string", description="Output file path"),
        },
        required=["output_path"],
    ),
    # ── Dev tools ──
    "dev_git": ToolSchema(
        name="dev_git",
        description="Execute a git command.",
        properties={
            "subcmd": ParameterProperty(
                type="string", description="Git subcommand (e.g. 'status', 'log')"
            ),
            "args": ParameterProperty(type="string", description="Additional arguments"),
            "cwd": ParameterProperty(type="string", description="Working directory"),
        },
        required=["subcmd"],
    ),
    "dev_docker": ToolSchema(
        name="dev_docker",
        description="Execute a docker command.",
        properties={
            "subcmd": ParameterProperty(type="string", description="Docker subcommand"),
            "args": ParameterProperty(type="string", description="Additional arguments"),
        },
        required=["subcmd"],
    ),
    "dev_pkg_install": ToolSchema(
        name="dev_pkg_install",
        description="Install a package (pip, npm, or brew).",
        properties={
            "manager": ParameterProperty(
                type="string",
                description="Package manager",
                enum=["pip", "npm", "brew"],
            ),
            "package": ParameterProperty(type="string", description="Package name"),
        },
        required=["manager", "package"],
    ),
    "dev_env_setup": ToolSchema(
        name="dev_env_setup",
        description="Set up development environment from project config.",
        properties={
            "path": ParameterProperty(type="string", description="Project root directory"),
        },
        required=["path"],
    ),
    # ── Browser tools ──
    "browser_navigate": ToolSchema(
        name="browser_navigate",
        description="Navigate browser to a URL.",
        properties={
            "url": ParameterProperty(type="string", description="URL to navigate to"),
        },
        required=["url"],
    ),
    "browser_click": ToolSchema(
        name="browser_click",
        description="Click an element on the page.",
        properties={
            "selector": ParameterProperty(type="string", description="CSS selector"),
        },
        required=["selector"],
    ),
    "browser_type": ToolSchema(
        name="browser_type",
        description="Type text into an input element.",
        properties={
            "selector": ParameterProperty(type="string", description="CSS selector"),
            "text": ParameterProperty(type="string", description="Text to type"),
        },
        required=["selector", "text"],
    ),
    "browser_screenshot": ToolSchema(
        name="browser_screenshot",
        description="Take a screenshot of the current page.",
        properties={
            "output_path": ParameterProperty(type="string", description="Output file path"),
        },
        required=["output_path"],
    ),
    "browser_extract": ToolSchema(
        name="browser_extract",
        description="Extract text content from the current page.",
        properties={
            "selector": ParameterProperty(type="string", description="CSS selector (optional)"),
        },
    ),
    "browser_pdf": ToolSchema(
        name="browser_pdf",
        description="Save current page as PDF.",
        properties={
            "output_path": ParameterProperty(type="string", description="Output PDF path"),
        },
        required=["output_path"],
    ),
    # ── GUI tools ──
    "gui_applescript": ToolSchema(
        name="gui_applescript",
        description="Execute an AppleScript command (macOS only).",
        properties={
            "script": ParameterProperty(type="string", description="AppleScript code"),
        },
        required=["script"],
    ),
    "gui_open_app": ToolSchema(
        name="gui_open_app",
        description="Open an application by name.",
        properties={
            "app_name": ParameterProperty(type="string", description="Application name"),
        },
        required=["app_name"],
    ),
    "gui_screenshot_ocr": ToolSchema(
        name="gui_screenshot_ocr",
        description="Take a screenshot and extract text via OCR.",
        properties={
            "region": ParameterProperty(type="string", description="Screen region (optional)"),
        },
    ),
    "gui_accessibility": ToolSchema(
        name="gui_accessibility",
        description="Interact with UI elements via Accessibility API.",
        properties={
            "action": ParameterProperty(type="string", description="Action to perform"),
            "target": ParameterProperty(type="string", description="Target element description"),
        },
        required=["action", "target"],
    ),
    # ── Cron tools ──
    "cron_schedule": ToolSchema(
        name="cron_schedule",
        description="Schedule a recurring task.",
        properties={
            "cron_expr": ParameterProperty(type="string", description="Cron expression"),
            "cmd": ParameterProperty(type="string", description="Command to run"),
        },
        required=["cron_expr", "cmd"],
    ),
    "cron_once": ToolSchema(
        name="cron_once",
        description="Schedule a one-shot task.",
        properties={
            "delay_seconds": ParameterProperty(type="integer", description="Delay in seconds"),
            "cmd": ParameterProperty(type="string", description="Command to run"),
        },
        required=["delay_seconds", "cmd"],
    ),
    "cron_list": ToolSchema(
        name="cron_list",
        description="List all scheduled jobs.",
        properties={},
    ),
    "cron_cancel": ToolSchema(
        name="cron_cancel",
        description="Cancel a scheduled job by ID.",
        properties={
            "job_id": ParameterProperty(type="string", description="Job ID to cancel"),
        },
        required=["job_id"],
    ),
}


def get_openai_tools(tool_names: list[str] | None = None) -> list[dict]:
    """Return OpenAI-compatible tool definitions.

    Args:
        tool_names: If provided, only include these tools. Otherwise include all.
    """
    if tool_names is None:
        return [schema.to_openai_tool() for schema in TOOL_SCHEMAS.values()]
    return [TOOL_SCHEMAS[name].to_openai_tool() for name in tool_names if name in TOOL_SCHEMAS]
