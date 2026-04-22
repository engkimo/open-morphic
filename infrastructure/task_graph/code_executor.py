"""CodeExecutor — Extract code blocks from LLM responses and execute them.

Sprint 9.2: LAEE Code Execution Integration.
  - Extract fenced code blocks (```python, ```bash, etc.) from LLM output
  - Execute via LAEE shell_exec with timeout and safety checks
  - Return structured result with code + output
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from infrastructure.local_execution.tools.shell_tools import shell_exec

logger = logging.getLogger(__name__)

# Languages that map to direct shell execution
_LANGUAGE_COMMANDS: dict[str, list[str]] = {
    "python": ["python3", "-c"],
    "bash": ["bash", "-c"],
    "sh": ["sh", "-c"],
    "javascript": ["node", "-e"],
    "js": ["node", "-e"],
    "ruby": ["ruby", "-e"],
}

# Default timeout for code execution (seconds)
DEFAULT_TIMEOUT = 30


@dataclass
class CodeBlock:
    """A single extracted code block."""

    language: str
    code: str


@dataclass
class ExecutionResult:
    """Result of code execution."""

    code: str
    language: str
    output: str
    success: bool
    error: str | None = None


def extract_code_blocks(content: str) -> list[CodeBlock]:
    """Extract fenced code blocks from LLM markdown output.

    Supports ```language ... ``` format.
    Returns blocks in order of appearance.
    """
    pattern = r"```(\w+)?\s*\n(.*?)```"
    matches = re.findall(pattern, content, re.DOTALL)

    blocks: list[CodeBlock] = []
    for lang, code in matches:
        lang = (lang or "").strip().lower()
        code = code.strip()
        if code:
            blocks.append(CodeBlock(language=lang, code=code))
    logger.debug("Extracted %d code block(s) from LLM output", len(blocks))
    return blocks


def find_executable_block(blocks: list[CodeBlock]) -> CodeBlock | None:
    """Find the first executable code block (supported language).

    Priority: python > bash/sh > javascript > ruby.
    """
    # First pass: find blocks with known executable languages
    for block in blocks:
        if block.language in _LANGUAGE_COMMANDS:
            return block

    # Second pass: untagged blocks — try to detect Python
    for block in blocks:
        if not block.language and _looks_like_python(block.code):
            return CodeBlock(language="python", code=block.code)

    return None


def _looks_like_python(code: str) -> bool:
    """Heuristic: does the code look like Python?"""
    python_indicators = [
        "def ",
        "import ",
        "print(",
        "for ",
        "if __name__",
        "class ",
        "return ",
    ]
    return any(indicator in code for indicator in python_indicators)


async def execute_code_block(
    block: CodeBlock,
    timeout: int = DEFAULT_TIMEOUT,
    cwd: str | None = None,
) -> ExecutionResult:
    """Execute a code block via LAEE shell_exec.

    Builds appropriate command for the language and runs it.
    """
    cmd_parts = _LANGUAGE_COMMANDS.get(block.language)
    if not cmd_parts:
        return ExecutionResult(
            code=block.code,
            language=block.language,
            output="",
            success=False,
            error=f"Unsupported language: {block.language}",
        )

    # Build shell command: python3 -c 'code'
    # Use shell_exec which handles timeout and error capture
    escaped_code = block.code.replace("'", "'\"'\"'")
    cmd = f"{cmd_parts[0]} {cmd_parts[1]} '{escaped_code}'"

    logger.info(
        "Executing %s code block (%d chars), timeout=%ds",
        block.language,
        len(block.code),
        timeout,
    )
    try:
        output = await shell_exec({"cmd": cmd, "timeout": timeout, "cwd": cwd})
        logger.info("Code execution succeeded — output %d chars", len(output))
        return ExecutionResult(
            code=block.code,
            language=block.language,
            output=output,
            success=True,
        )
    except TimeoutError:
        logger.warning("Code execution timed out after %ds", timeout)
        return ExecutionResult(
            code=block.code,
            language=block.language,
            output="",
            success=False,
            error=f"Execution timed out after {timeout}s",
        )
    except RuntimeError as e:
        logger.warning("Code execution failed: %s", e)
        return ExecutionResult(
            code=block.code,
            language=block.language,
            output="",
            success=False,
            error=str(e),
        )


async def extract_and_execute(
    content: str,
    timeout: int = DEFAULT_TIMEOUT,
    cwd: str | None = None,
) -> ExecutionResult | None:
    """Extract the first executable code block from LLM output and run it.

    Returns None if no executable code block is found.
    """
    blocks = extract_code_blocks(content)
    block = find_executable_block(blocks)
    if block is None:
        return None
    return await execute_code_block(block, timeout=timeout, cwd=cwd)
