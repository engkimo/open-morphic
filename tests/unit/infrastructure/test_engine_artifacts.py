"""TDD: Engine artifact injection, extraction, and chaining — Sprint 13.4a/b."""

from domain.entities.task import SubTask, TaskEntity
from domain.value_objects.status import SubTaskStatus
from infrastructure.task_graph.engine import LangGraphTaskEngine


class _FakeLLM:
    """Minimal LLMGateway stub."""

    async def complete(self, messages, **kwargs):
        class R:
            content = "result text"
            model = "ollama/qwen3:8b"
            cost_usd = 0.0

        return R()

    async def complete_with_tools(self, *a, **kw):
        raise NotImplementedError

    async def is_available(self, model=None):
        return True


class _FakeAnalyzer:
    async def decompose(self, goal):
        return [SubTask(description=goal)]


class _FakeKVCache:
    stable_prefix = "test"

    def build_system_prompt(self, ctx):
        return "system"


# ── Artifact context building ──


class TestBuildArtifactContext:
    def test_empty_artifacts(self):
        result = LangGraphTaskEngine._build_artifact_context({})
        assert result == ""

    def test_empty_values_skipped(self):
        result = LangGraphTaskEngine._build_artifact_context({"key": ""})
        assert result == ""

    def test_single_artifact(self):
        result = LangGraphTaskEngine._build_artifact_context({"search_results": "Found 3 theaters"})
        assert "Artifacts from previous steps:" in result
        assert "### search_results" in result
        assert "Found 3 theaters" in result

    def test_multiple_artifacts(self):
        result = LangGraphTaskEngine._build_artifact_context({"code": "print(1)", "output": "1"})
        assert "### code" in result
        assert "### output" in result
        assert "print(1)" in result

    def test_long_artifact_truncated(self):
        long_text = "x" * 5000
        result = LangGraphTaskEngine._build_artifact_context({"data": long_text})
        assert "..." in result
        assert len(result) < 5000


# ── Output artifact extraction ──


class TestExtractOutputArtifacts:
    def test_no_output_artifacts_defined(self):
        st = SubTask(description="step", result="done")
        LangGraphTaskEngine._extract_output_artifacts(st)
        assert st.output_artifacts == {}

    def test_single_key_filled_from_result(self):
        st = SubTask(
            description="search",
            result="Found data",
            output_artifacts={"search_results": ""},
        )
        LangGraphTaskEngine._extract_output_artifacts(st)
        assert st.output_artifacts["search_results"] == "Found data"

    def test_multiple_keys_from_result_code_output(self):
        st = SubTask(
            description="execute",
            result="Analysis complete",
            code="import pandas",
            execution_output="OK",
            output_artifacts={"analysis": "", "source_code": "", "exec_out": ""},
        )
        LangGraphTaskEngine._extract_output_artifacts(st)
        assert st.output_artifacts["analysis"] == "Analysis complete"
        assert st.output_artifacts["source_code"] == "import pandas"
        assert st.output_artifacts["exec_out"] == "OK"

    def test_fewer_values_than_keys(self):
        st = SubTask(
            description="step",
            result="Result only",
            output_artifacts={"key1": "", "key2": ""},
        )
        LangGraphTaskEngine._extract_output_artifacts(st)
        assert st.output_artifacts["key1"] == "Result only"
        assert st.output_artifacts["key2"] == "Result only"

    def test_no_result_no_fill(self):
        st = SubTask(
            description="step",
            output_artifacts={"key": ""},
        )
        LangGraphTaskEngine._extract_output_artifacts(st)
        assert st.output_artifacts["key"] == ""


# ── Sprint 13.4b: Smart extraction from engine output ──


class TestSmartArtifactExtraction:
    """Sprint 13.4b: ArtifactExtractor-powered extraction from rich text."""

    def test_code_key_extracts_code_block_from_result(self):
        """Engine output with fenced code → code key gets the code."""
        st = SubTask(
            description="implement",
            result="Here:\n```python\ndef solve(): return 42\n```\nDone.",
            output_artifacts={"source_code": ""},
        )
        LangGraphTaskEngine._extract_output_artifacts(st)
        assert "def solve" in st.output_artifacts["source_code"]
        # Should NOT include fences in extracted content
        assert "```" not in st.output_artifacts["source_code"]

    def test_url_key_extracts_urls_from_result(self):
        """Engine output with URLs → url key gets the URLs."""
        st = SubTask(
            description="search",
            result="Found: https://a.com/1 and https://b.com/2",
            output_artifacts={"found_urls": ""},
        )
        LangGraphTaskEngine._extract_output_artifacts(st)
        assert "https://a.com/1" in st.output_artifacts["found_urls"]
        assert "https://b.com/2" in st.output_artifacts["found_urls"]

    def test_data_key_extracts_json_from_result(self):
        """Engine output with JSON block → data key gets the JSON."""
        st = SubTask(
            description="parse",
            result='Parsed:\n```json\n{"items": [1, 2]}\n```',
            output_artifacts={"parsed_json": ""},
        )
        LangGraphTaskEngine._extract_output_artifacts(st)
        assert '"items"' in st.output_artifacts["parsed_json"]

    def test_mixed_keys_smart_routing(self):
        """Multiple keys with different types matched from single result."""
        st = SubTask(
            description="research",
            result=(
                "Results:\n"
                "https://example.com/r1\n\n"
                "```python\nprint('hi')\n```\n\n"
                "Summary of findings."
            ),
            output_artifacts={
                "impl_code": "",
                "reference_links": "",
                "overview": "",
            },
        )
        LangGraphTaskEngine._extract_output_artifacts(st)
        assert "print('hi')" in st.output_artifacts["impl_code"]
        assert "example.com" in st.output_artifacts["reference_links"]
        # "overview" has no keyword match → falls back to result text
        assert "Results:" in st.output_artifacts["overview"]

    def test_no_code_blocks_code_key_falls_to_positional(self):
        """Code key but no code blocks in result → positional fallback."""
        st = SubTask(
            description="step",
            result="No code here, just text.",
            output_artifacts={"source_code": ""},
        )
        LangGraphTaskEngine._extract_output_artifacts(st)
        assert st.output_artifacts["source_code"] == "No code here, just text."


# ── Artifact injection ──


class TestInjectArtifacts:
    def _make_engine(self):
        llm = _FakeLLM()
        analyzer = _FakeAnalyzer()
        engine = LangGraphTaskEngine(llm, analyzer, kv_cache=_FakeKVCache())
        return engine

    def test_inject_from_completed_dependency(self):
        engine = self._make_engine()
        st_a = SubTask(
            id="a",
            description="search",
            status=SubTaskStatus.SUCCESS,
            result="data",
            output_artifacts={"search_results": "Found 5 items"},
        )
        st_b = SubTask(
            id="b",
            description="analyze",
            dependencies=["a"],
            input_artifacts={"search_results": ""},
        )
        task = TaskEntity(goal="test", subtasks=[st_a, st_b])
        engine._task = task

        engine._inject_artifacts(st_b)
        assert st_b.input_artifacts["search_results"] == "Found 5 items"

    def test_inject_no_matching_artifact(self):
        engine = self._make_engine()
        st_a = SubTask(
            id="a",
            description="search",
            status=SubTaskStatus.SUCCESS,
            output_artifacts={"other_key": "value"},
        )
        st_b = SubTask(
            id="b",
            description="analyze",
            dependencies=["a"],
            input_artifacts={"search_results": ""},
        )
        task = TaskEntity(goal="test", subtasks=[st_a, st_b])
        engine._task = task

        engine._inject_artifacts(st_b)
        assert st_b.input_artifacts["search_results"] == ""

    def test_inject_empty_input_artifacts_noop(self):
        engine = self._make_engine()
        st = SubTask(id="a", description="step")
        task = TaskEntity(goal="test", subtasks=[st])
        engine._task = task

        engine._inject_artifacts(st)  # should not raise
        assert st.input_artifacts == {}

    def test_inject_from_multiple_sources(self):
        engine = self._make_engine()
        st_a = SubTask(
            id="a",
            description="search",
            status=SubTaskStatus.SUCCESS,
            output_artifacts={"search_data": "results A"},
        )
        st_b = SubTask(
            id="b",
            description="code",
            status=SubTaskStatus.SUCCESS,
            output_artifacts={"code_output": "print(1)"},
        )
        st_c = SubTask(
            id="c",
            description="combine",
            dependencies=["a", "b"],
            input_artifacts={"search_data": "", "code_output": ""},
        )
        task = TaskEntity(goal="test", subtasks=[st_a, st_b, st_c])
        engine._task = task

        engine._inject_artifacts(st_c)
        assert st_c.input_artifacts["search_data"] == "results A"
        assert st_c.input_artifacts["code_output"] == "print(1)"

    def test_inject_skips_non_completed_subtasks(self):
        engine = self._make_engine()
        st_a = SubTask(
            id="a",
            description="search",
            status=SubTaskStatus.RUNNING,  # not completed
            output_artifacts={"data": "should not be injected"},
        )
        st_b = SubTask(
            id="b",
            description="use",
            input_artifacts={"data": ""},
        )
        task = TaskEntity(goal="test", subtasks=[st_a, st_b])
        engine._task = task

        engine._inject_artifacts(st_b)
        assert st_b.input_artifacts["data"] == ""
