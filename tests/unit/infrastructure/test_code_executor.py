"""Tests for CodeExecutor — code block extraction and execution."""

from unittest.mock import AsyncMock, patch

from infrastructure.task_graph.code_executor import (
    CodeBlock,
    execute_code_block,
    extract_and_execute,
    extract_code_blocks,
    find_executable_block,
)


class TestExtractCodeBlocks:
    """Extract fenced code blocks from LLM markdown output."""

    def test_single_python_block(self) -> None:
        content = '```python\nprint("hello")\n```'
        blocks = extract_code_blocks(content)

        assert len(blocks) == 1
        assert blocks[0].language == "python"
        assert blocks[0].code == 'print("hello")'

    def test_multiple_blocks(self) -> None:
        content = "Here is the code:\n```python\nx = 1\n```\nAnd bash:\n```bash\necho hi\n```"
        blocks = extract_code_blocks(content)

        assert len(blocks) == 2
        assert blocks[0].language == "python"
        assert blocks[1].language == "bash"

    def test_no_code_blocks(self) -> None:
        content = "This is just plain text with no code."
        blocks = extract_code_blocks(content)

        assert blocks == []

    def test_untagged_block(self) -> None:
        content = "```\nprint('hello')\n```"
        blocks = extract_code_blocks(content)

        assert len(blocks) == 1
        assert blocks[0].language == ""

    def test_empty_block_skipped(self) -> None:
        content = "```python\n\n```"
        blocks = extract_code_blocks(content)

        assert blocks == []

    def test_multiline_code(self) -> None:
        content = (
            "```python\n"
            "def fib(n):\n"
            "    if n <= 1:\n"
            "        return n\n"
            "    return fib(n-1) + fib(n-2)\n"
            "\n"
            "print(fib(10))\n"
            "```"
        )
        blocks = extract_code_blocks(content)

        assert len(blocks) == 1
        assert "def fib(n):" in blocks[0].code
        assert "print(fib(10))" in blocks[0].code

    def test_javascript_block(self) -> None:
        content = '```javascript\nconsole.log("hello")\n```'
        blocks = extract_code_blocks(content)

        assert blocks[0].language == "javascript"

    def test_surrounding_text_preserved(self) -> None:
        content = "Here is how to solve it:\n\n```python\nresult = 42\n```\n\nThis will output 42."
        blocks = extract_code_blocks(content)

        assert len(blocks) == 1
        assert blocks[0].code == "result = 42"


class TestFindExecutableBlock:
    """Find the first executable code block by language priority."""

    def test_python_preferred(self) -> None:
        blocks = [
            CodeBlock(language="bash", code="echo hi"),
            CodeBlock(language="python", code="print('hi')"),
        ]
        result = find_executable_block(blocks)

        # Returns first executable, which is bash (first in list)
        assert result is not None
        assert result.language == "bash"

    def test_python_found(self) -> None:
        blocks = [CodeBlock(language="python", code="print(1)")]
        result = find_executable_block(blocks)

        assert result is not None
        assert result.language == "python"

    def test_unsupported_language_skipped(self) -> None:
        blocks = [
            CodeBlock(language="rust", code="fn main() {}"),
            CodeBlock(language="python", code="print(1)"),
        ]
        result = find_executable_block(blocks)

        assert result is not None
        assert result.language == "python"

    def test_no_executable_blocks(self) -> None:
        blocks = [
            CodeBlock(language="rust", code="fn main() {}"),
            CodeBlock(language="haskell", code="main = putStrLn"),
        ]
        result = find_executable_block(blocks)

        assert result is None

    def test_empty_list(self) -> None:
        assert find_executable_block([]) is None

    def test_untagged_python_detected(self) -> None:
        blocks = [CodeBlock(language="", code='print("hello world")')]
        result = find_executable_block(blocks)

        assert result is not None
        assert result.language == "python"

    def test_untagged_non_python_not_detected(self) -> None:
        blocks = [CodeBlock(language="", code="<html><body>hi</body></html>")]
        result = find_executable_block(blocks)

        assert result is None

    def test_supported_languages(self) -> None:
        for lang in ["python", "bash", "sh", "javascript", "js", "ruby"]:
            block = CodeBlock(language=lang, code="x=1")
            result = find_executable_block([block])
            assert result is not None, f"{lang} should be executable"


class TestExecuteCodeBlock:
    """Execute a code block via LAEE shell_exec."""

    async def test_successful_execution(self) -> None:
        block = CodeBlock(language="python", code='print("hello")')

        with patch(
            "infrastructure.task_graph.code_executor.shell_exec",
            new_callable=AsyncMock,
            return_value="hello",
        ):
            result = await execute_code_block(block)

        assert result.success is True
        assert result.output == "hello"
        assert result.code == 'print("hello")'
        assert result.language == "python"
        assert result.error is None

    async def test_timeout_error(self) -> None:
        block = CodeBlock(language="python", code="import time; time.sleep(100)")

        with patch(
            "infrastructure.task_graph.code_executor.shell_exec",
            new_callable=AsyncMock,
            side_effect=TimeoutError("timed out"),
        ):
            result = await execute_code_block(block, timeout=5)

        assert result.success is False
        assert "timed out" in (result.error or "")

    async def test_runtime_error(self) -> None:
        block = CodeBlock(language="python", code="raise Exception('boom')")

        with patch(
            "infrastructure.task_graph.code_executor.shell_exec",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Command failed (exit 1): boom"),
        ):
            result = await execute_code_block(block)

        assert result.success is False
        assert "boom" in (result.error or "")

    async def test_unsupported_language(self) -> None:
        block = CodeBlock(language="rust", code="fn main() {}")

        result = await execute_code_block(block)

        assert result.success is False
        assert "Unsupported language" in (result.error or "")

    async def test_bash_execution(self) -> None:
        block = CodeBlock(language="bash", code="echo hello")

        with patch(
            "infrastructure.task_graph.code_executor.shell_exec",
            new_callable=AsyncMock,
            return_value="hello",
        ) as mock_exec:
            result = await execute_code_block(block)

        assert result.success is True
        assert result.output == "hello"
        # Verify bash -c is used
        call_args = mock_exec.call_args[0][0]
        assert "bash" in call_args["cmd"]

    async def test_custom_timeout(self) -> None:
        block = CodeBlock(language="python", code="print(1)")

        with patch(
            "infrastructure.task_graph.code_executor.shell_exec",
            new_callable=AsyncMock,
            return_value="1",
        ) as mock_exec:
            await execute_code_block(block, timeout=60)

        call_args = mock_exec.call_args[0][0]
        assert call_args["timeout"] == 60

    async def test_custom_cwd(self) -> None:
        block = CodeBlock(language="python", code="print(1)")

        with patch(
            "infrastructure.task_graph.code_executor.shell_exec",
            new_callable=AsyncMock,
            return_value="1",
        ) as mock_exec:
            await execute_code_block(block, cwd="/tmp")

        call_args = mock_exec.call_args[0][0]
        assert call_args["cwd"] == "/tmp"


class TestExtractAndExecute:
    """End-to-end: extract + execute from raw LLM output."""

    async def test_python_code_extracted_and_run(self) -> None:
        content = (
            "Here is FizzBuzz:\n\n"
            "```python\nfor i in range(1, 16):\n    print(i)\n```\n\n"
            "This prints numbers 1 to 15."
        )

        with patch(
            "infrastructure.task_graph.code_executor.shell_exec",
            new_callable=AsyncMock,
            return_value="1\n2\n3",
        ):
            result = await extract_and_execute(content)

        assert result is not None
        assert result.success is True
        assert result.output == "1\n2\n3"
        assert "for i in range" in result.code

    async def test_no_code_blocks_returns_none(self) -> None:
        content = "The Fibonacci sequence starts with 0, 1, 1, 2, 3, 5, 8..."

        result = await extract_and_execute(content)

        assert result is None

    async def test_unsupported_only_returns_none(self) -> None:
        content = '```rust\nfn main() { println!("hi"); }\n```'

        # No untagged blocks to fall back to, and rust is unsupported
        # find_executable_block returns None
        result = await extract_and_execute(content)

        assert result is None

    async def test_execution_failure_returns_error(self) -> None:
        content = '```python\nraise ValueError("oops")\n```'

        with patch(
            "infrastructure.task_graph.code_executor.shell_exec",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Command failed"),
        ):
            result = await extract_and_execute(content)

        assert result is not None
        assert result.success is False

    async def test_timeout_passed_through(self) -> None:
        content = '```python\nprint("hi")\n```'

        with patch(
            "infrastructure.task_graph.code_executor.shell_exec",
            new_callable=AsyncMock,
            return_value="hi",
        ) as mock_exec:
            await extract_and_execute(content, timeout=10)

        call_args = mock_exec.call_args[0][0]
        assert call_args["timeout"] == 10
