"""L1-L4 Integration Test — end-to-end memory hierarchy with all 5 compression strategies.

Exercises: MemoryHierarchy, ContextZipper, ForgettingCurve, DeltaEncoder,
HierarchicalSummarizer, ContextBridge, and MCP Server together.

Uses InMemoryMemoryRepository (no Docker required).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from domain.entities.memory import MemoryEntry
from domain.value_objects.status import MemoryType
from infrastructure.memory.context_bridge import ContextBridge
from infrastructure.memory.context_zipper import ContextZipper
from infrastructure.memory.delta_encoder import DeltaEncoderManager
from infrastructure.memory.forgetting_curve import ForgettingCurveManager
from infrastructure.memory.hierarchical_summarizer import HierarchicalSummaryManager
from infrastructure.memory.memory_hierarchy import MemoryHierarchy
from infrastructure.persistence.in_memory import InMemoryMemoryRepository

# ── Scenario 1: Full Lifecycle ──


class TestFullLifecycle:
    """Add memories, record deltas, summarize, compact, retrieve, export."""

    @pytest.mark.asyncio
    async def test_add_memories_and_retrieve(self) -> None:
        repo = InMemoryMemoryRepository()
        hierarchy = MemoryHierarchy(memory_repo=repo)

        # Add 20 memories
        for i in range(20):
            await hierarchy.add(f"Memory entry number {i} about topic {i % 5}")

        # Retrieve should find relevant entries
        result = await hierarchy.retrieve("topic 3", max_tokens=200)
        assert len(result) > 0
        assert "topic 3" in result

    @pytest.mark.asyncio
    async def test_deltas_and_state_reconstruction(self) -> None:
        repo = InMemoryMemoryRepository()
        hierarchy = MemoryHierarchy(memory_repo=repo)

        # Record 5 deltas on a topic
        await hierarchy.record_delta("project", "init", {"name": "Morphic", "version": "0.1"})
        await hierarchy.record_delta("project", "bump version", {"version": "0.2"})
        await hierarchy.record_delta("project", "add feature", {"feature": "MCP"})
        await hierarchy.record_delta("project", "set budget", {"budget": 50000})
        await hierarchy.record_delta("project", "approve", {"status": "approved"})

        state = await hierarchy.get_state("project")
        assert state["name"] == "Morphic"
        assert state["version"] == "0.2"
        assert state["feature"] == "MCP"
        assert state["budget"] == 50000
        assert state["status"] == "approved"

    @pytest.mark.asyncio
    async def test_summarize_and_retrieve_at_depth(self) -> None:
        repo = InMemoryMemoryRepository()
        summarizer = HierarchicalSummaryManager(memory_repo=repo)

        # Add entries with enough content for meaningful summarization
        # Use words without trailing punctuation for keyword search compatibility
        sentences = [f"The architecture design includes component {i}" for i in range(20)]
        content = ". ".join(sentences) + "."
        entry = MemoryEntry(
            content=content,
            memory_type=MemoryType.L2_SEMANTIC,
            metadata={"role": "user"},
        )
        await repo.add(entry)

        # Summarize
        result = await summarizer.summarize(entry.id)
        assert result is not None
        assert result.levels_built == 4
        assert result.original_tokens > result.compressed_tokens

        # Retrieve at depth uses search() which does keyword matching
        text = await summarizer.retrieve_at_depth("architecture", max_tokens=500)
        assert len(text) > 0

    @pytest.mark.asyncio
    async def test_forgetting_curve_promotes_to_l3(self) -> None:
        repo = InMemoryMemoryRepository()

        # Create old entries with low access count → should be expired
        old_entry = MemoryEntry(
            content="old stale memory",
            memory_type=MemoryType.L2_SEMANTIC,
            metadata={"role": "user"},
            access_count=1,
            importance_score=0.0,
            created_at=datetime.now() - timedelta(days=30),
            last_accessed=datetime.now() - timedelta(days=30),
        )
        await repo.add(old_entry)

        # Create fresh entry → should survive
        fresh_entry = MemoryEntry(
            content="fresh recent memory",
            memory_type=MemoryType.L2_SEMANTIC,
            metadata={"role": "user"},
            access_count=5,
            importance_score=0.9,
        )
        await repo.add(fresh_entry)

        mgr = ForgettingCurveManager(memory_repo=repo, knowledge_graph=None, threshold=0.3)
        result = await mgr.compact()

        assert result.scanned >= 1
        assert result.deleted >= 1  # Old entry deleted

        # Fresh entry should survive
        remaining = await repo.get_by_id(fresh_entry.id)
        assert remaining is not None

    @pytest.mark.asyncio
    async def test_full_pipeline_export(self) -> None:
        repo = InMemoryMemoryRepository()
        hierarchy = MemoryHierarchy(memory_repo=repo)
        zipper = ContextZipper(memory_repo=repo)
        delta = DeltaEncoderManager(memory_repo=repo)
        bridge = ContextBridge(
            memory=hierarchy,
            context_zipper=zipper,
            delta_encoder=delta,
        )

        # Add memories
        await hierarchy.add("Project uses Python 3.12 with FastAPI")
        await hierarchy.add("Database is PostgreSQL with pgvector")

        # Record deltas
        await delta.record("config", "init", {"db": "postgres", "api": "fastapi"})

        # Export to all platforms
        results = await bridge.export_all(query="project stack")
        assert len(results) == 4
        for r in results:
            assert r.token_estimate >= 1


# ── Scenario 2: Compression Strategy Interplay ──


class TestCompressionInterplay:
    """Verify different compression strategies work together correctly."""

    @pytest.mark.asyncio
    async def test_zipper_finds_semantic_matches(self) -> None:
        repo = InMemoryMemoryRepository()
        zipper = ContextZipper(memory_repo=repo)

        # Ingest content to L2
        await zipper.ingest("Python is great for data science")
        await zipper.ingest("TypeScript is popular for web development")
        await zipper.ingest("Rust provides memory safety guarantees")

        # Compress should find relevant memories
        result = await zipper.compress(
            history=["What language should I use?"],
            query="data science programming",
            max_tokens=200,
        )
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_hierarchy_levels_depth_selection(self) -> None:
        repo = InMemoryMemoryRepository()
        summarizer = HierarchicalSummaryManager(memory_repo=repo)

        # Add a long entry
        long_content = "Detailed technical specification for the API. " * 30
        entry = MemoryEntry(
            content=long_content,
            memory_type=MemoryType.L2_SEMANTIC,
            metadata={},
        )
        await repo.add(entry)
        await summarizer.summarize(entry.id)

        # Small budget → should pick higher (more compressed) level
        small_result = await summarizer.retrieve_at_depth("API", max_tokens=50)
        # Large budget → should pick lower (more detailed) level
        large_result = await summarizer.retrieve_at_depth("API", max_tokens=5000)

        # Large budget result should be longer or equal
        assert len(large_result) >= len(small_result)

    @pytest.mark.asyncio
    async def test_delta_state_reconstruction_full_chain(self) -> None:
        repo = InMemoryMemoryRepository()
        delta = DeltaEncoderManager(memory_repo=repo)

        # Build a chain of 10 deltas
        await delta.record("deploy", "init", {"env": "dev", "version": "0.1"})
        for i in range(1, 10):
            await delta.record("deploy", f"update {i}", {f"feature_{i}": True})

        state = await delta.get_state("deploy")
        assert state["env"] == "dev"
        assert state["version"] == "0.1"
        # All features should be present
        for i in range(1, 10):
            assert state[f"feature_{i}"] is True

    @pytest.mark.asyncio
    async def test_delta_topics_across_multiple_topics(self) -> None:
        repo = InMemoryMemoryRepository()
        delta = DeltaEncoderManager(memory_repo=repo)

        await delta.record("frontend", "init", {"framework": "React"})
        await delta.record("backend", "init", {"framework": "FastAPI"})
        await delta.record("infra", "init", {"cloud": "AWS"})

        topics = await delta.list_topics()
        assert set(topics) == {"frontend", "backend", "infra"}

        # Each topic's state is independent
        assert (await delta.get_state("frontend")) == {"framework": "React"}
        assert (await delta.get_state("backend")) == {"framework": "FastAPI"}
        assert (await delta.get_state("infra")) == {"cloud": "AWS"}


# ── Scenario 3: Edge Cases ──


class TestEdgeCases:
    """Verify operations on empty memory, single entry, and large content."""

    @pytest.mark.asyncio
    async def test_all_operations_on_empty_memory(self) -> None:
        repo = InMemoryMemoryRepository()
        hierarchy = MemoryHierarchy(memory_repo=repo)
        zipper = ContextZipper(memory_repo=repo)
        delta = DeltaEncoderManager(memory_repo=repo)
        summarizer = HierarchicalSummaryManager(memory_repo=repo)
        bridge = ContextBridge(
            memory=hierarchy,
            context_zipper=zipper,
            delta_encoder=delta,
        )

        # All operations should succeed without crashing
        assert await hierarchy.retrieve("anything") == ""
        assert await zipper.compress([], "query", 100) == ""
        assert await delta.get_state("nonexistent") == {}
        assert await delta.list_topics() == []
        assert await summarizer.retrieve_at_depth("query", 100) == ""

        # Context bridge export should produce minimal content
        result = await bridge.export("claude_code", query="test")
        assert isinstance(result.content, str)

    @pytest.mark.asyncio
    async def test_single_entry_pipeline(self) -> None:
        repo = InMemoryMemoryRepository()
        hierarchy = MemoryHierarchy(memory_repo=repo)
        bridge = ContextBridge(memory=hierarchy)

        # Single memory entry
        await hierarchy.add("The only memory in the system")

        # Retrieve
        result = await hierarchy.retrieve("only memory")
        assert "only memory" in result

        # Export
        export = await bridge.export("chatgpt", query="memory")
        assert isinstance(export.content, str)

    @pytest.mark.asyncio
    async def test_large_content_handling(self) -> None:
        repo = InMemoryMemoryRepository()
        summarizer = HierarchicalSummaryManager(memory_repo=repo)

        # Create large content with proper sentences for summarizer + keyword-friendly words
        # Each sentence ends with period, but "architecture" and "design" appear without punctuation
        large_content = " ".join(
            f"The architecture design for component {i} is documented here." for i in range(500)
        )
        entry = MemoryEntry(
            content=large_content,
            memory_type=MemoryType.L2_SEMANTIC,
            metadata={},
        )
        await repo.add(entry)

        # Summarize should produce valid hierarchy
        result = await summarizer.summarize(entry.id)
        assert result is not None
        assert result.levels_built == 4
        assert result.compressed_tokens < result.original_tokens

        # Retrieve with budget should find the entry via keyword search
        text = await summarizer.retrieve_at_depth("architecture", max_tokens=5000)
        assert len(text) > 0
        assert len(text) <= len(large_content)


# ── Scenario 4: Cross-Component Consistency ──


class TestCrossComponentConsistency:
    """Verify same data is accessible via different components consistently."""

    @pytest.mark.asyncio
    async def test_memory_accessible_via_hierarchy_and_zipper(self) -> None:
        repo = InMemoryMemoryRepository()
        hierarchy = MemoryHierarchy(memory_repo=repo)
        zipper = ContextZipper(memory_repo=repo)

        # Add via hierarchy
        await hierarchy.add("Shared data between components")

        # Retrieve via hierarchy
        h_result = await hierarchy.retrieve("Shared data", max_tokens=500)
        assert "Shared data" in h_result

        # Retrieve via zipper
        z_result = await zipper.compress([], "Shared data", max_tokens=500)
        assert "Shared" in z_result

    @pytest.mark.asyncio
    async def test_delta_state_accessible_via_bridge(self) -> None:
        repo = InMemoryMemoryRepository()
        delta = DeltaEncoderManager(memory_repo=repo)
        bridge = ContextBridge(delta_encoder=delta)

        await delta.record("config", "init", {"db": "postgres"})

        # Direct access
        state = await delta.get_state("config")
        assert state["db"] == "postgres"

        # Via bridge export
        result = await bridge.export("gemini")
        assert "postgres" in result.content

    @pytest.mark.asyncio
    async def test_mcp_server_accesses_same_data(self) -> None:
        """MCP server tools see the same data as direct API calls."""
        from infrastructure.mcp.server import create_mcp_server

        # Build container-like setup
        repo = InMemoryMemoryRepository()
        hierarchy = MemoryHierarchy(memory_repo=repo)
        zipper = ContextZipper(memory_repo=repo)
        delta = DeltaEncoderManager(memory_repo=repo)
        bridge = ContextBridge(
            memory=hierarchy,
            context_zipper=zipper,
            delta_encoder=delta,
        )

        # Use a simple mock container
        class _Container:
            pass

        container = _Container()
        container.memory = hierarchy
        container.context_zipper = zipper
        container.delta_encoder = delta
        container.context_bridge = bridge

        # Add data directly
        await hierarchy.add("MCP integration test data")
        await delta.record("mcp_test", "init", {"status": "testing"})

        # Create MCP server with the same underlying data
        mcp = create_mcp_server(container)

        # Verify MCP tools see the same data
        search_tool = mcp._tool_manager._tools.get("memory_search")
        assert search_tool is not None
        result = await search_tool.fn(query="integration test", max_tokens=500)
        assert "integration test data" in str(result)

        # Verify delta state via MCP
        delta_tool = mcp._tool_manager._tools.get("delta_get_state")
        assert delta_tool is not None
        state_json = await delta_tool.fn(topic="mcp_test")
        state = json.loads(state_json)
        assert state["status"] == "testing"

    @pytest.mark.asyncio
    async def test_export_all_platforms_consistent(self) -> None:
        repo = InMemoryMemoryRepository()
        hierarchy = MemoryHierarchy(memory_repo=repo)
        delta = DeltaEncoderManager(memory_repo=repo)
        bridge = ContextBridge(memory=hierarchy, delta_encoder=delta)

        await hierarchy.add("Consistent data across platforms")
        await delta.record("shared", "init", {"key": "value"})

        results = await bridge.export_all(query="data")

        # All platforms should contain the core data
        for result in results:
            assert "value" in result.content or "Consistent" in result.content
