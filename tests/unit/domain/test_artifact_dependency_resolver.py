"""Tests for ArtifactDependencyResolver — TD-097."""

from __future__ import annotations

from domain.entities.task import SubTask
from domain.services.artifact_dependency_resolver import ArtifactDependencyResolver


class TestResolveFromArtifacts:
    """Dependencies inferred from producer→consumer artifact relationships."""

    def test_simple_chain(self) -> None:
        """A produces X, B consumes X → B depends on A."""
        a = SubTask(description="step A", output_artifacts={"report": ""})
        b = SubTask(description="step B", input_artifacts={"report": ""})
        ArtifactDependencyResolver.resolve([a, b])
        assert a.id in b.dependencies
        assert a.dependencies == []

    def test_diamond_dependency(self) -> None:
        """A→B, A→C, B+C→D (diamond pattern)."""
        a = SubTask(description="gather", output_artifacts={"data": ""})
        b = SubTask(
            description="analyze",
            input_artifacts={"data": ""},
            output_artifacts={"analysis": ""},
        )
        c = SubTask(
            description="summarize",
            input_artifacts={"data": ""},
            output_artifacts={"summary": ""},
        )
        d = SubTask(description="combine", input_artifacts={"analysis": "", "summary": ""})
        ArtifactDependencyResolver.resolve([a, b, c, d])
        assert a.id in b.dependencies
        assert a.id in c.dependencies
        assert b.id in d.dependencies
        assert c.id in d.dependencies
        assert a.dependencies == []

    def test_no_duplicate_deps(self) -> None:
        """If dependency already exists, don't add duplicate."""
        a = SubTask(description="step A", output_artifacts={"x": ""})
        b = SubTask(description="step B", input_artifacts={"x": ""})
        b.dependencies.append(a.id)  # Pre-existing dep
        ArtifactDependencyResolver.resolve([a, b])
        assert b.dependencies.count(a.id) == 1

    def test_self_reference_ignored(self) -> None:
        """Subtask producing and consuming same artifact doesn't self-depend."""
        a = SubTask(
            description="self",
            output_artifacts={"x": ""},
            input_artifacts={"x": ""},
        )
        ArtifactDependencyResolver.resolve([a])
        assert a.dependencies == []

    def test_multi_producer(self) -> None:
        """Last producer of an artifact wins (index-based overwrite)."""
        a = SubTask(description="first", output_artifacts={"data": ""})
        b = SubTask(description="second", output_artifacts={"data": ""})
        c = SubTask(description="consumer", input_artifacts={"data": ""})
        ArtifactDependencyResolver.resolve([a, b, c])
        # b is the last producer of "data"
        assert b.id in c.dependencies


class TestResolveLinearChain:
    """Fallback: no artifacts → linear chain inference."""

    def test_two_subtasks(self) -> None:
        a = SubTask(description="step 1")
        b = SubTask(description="step 2")
        ArtifactDependencyResolver.resolve([a, b])
        assert a.dependencies == []
        assert a.id in b.dependencies

    def test_three_subtasks(self) -> None:
        a = SubTask(description="step 1")
        b = SubTask(description="step 2")
        c = SubTask(description="step 3")
        ArtifactDependencyResolver.resolve([a, b, c])
        assert a.id in b.dependencies
        assert b.id in c.dependencies
        assert a.id not in c.dependencies  # Only direct predecessor

    def test_single_subtask_no_deps(self) -> None:
        a = SubTask(description="only one")
        ArtifactDependencyResolver.resolve([a])
        assert a.dependencies == []

    def test_empty_list(self) -> None:
        ArtifactDependencyResolver.resolve([])  # No error

    def test_no_duplicate_chain_deps(self) -> None:
        a = SubTask(description="step 1")
        b = SubTask(description="step 2")
        b.dependencies.append(a.id)  # Pre-existing
        ArtifactDependencyResolver.resolve([a, b])
        assert b.dependencies.count(a.id) == 1


class TestApprovePlanIntegration:
    """Simulate the approve_plan flow: new SubTasks with artifacts but no deps."""

    def test_plan_approval_reinfers_deps(self) -> None:
        """TD-097: SubTasks created from PlanSteps get dependencies re-inferred."""
        # Simulate what approve_plan does: create new SubTasks with artifacts
        subtasks = [
            SubTask(
                description="search for data",
                output_artifacts={"search_results": ""},
            ),
            SubTask(
                description="analyze results",
                input_artifacts={"search_results": ""},
                output_artifacts={"analysis": ""},
            ),
            SubTask(
                description="write report",
                input_artifacts={"analysis": ""},
            ),
        ]
        # These are NEW subtasks — no dependencies set yet
        assert all(st.dependencies == [] for st in subtasks)

        ArtifactDependencyResolver.resolve(subtasks)

        # Now dependencies should be correctly inferred
        assert subtasks[0].dependencies == []
        assert subtasks[0].id in subtasks[1].dependencies
        assert subtasks[1].id in subtasks[2].dependencies

    def test_plan_approval_no_artifacts_gets_chain(self) -> None:
        """TD-097: PlanSteps with no artifacts get linear chain."""
        subtasks = [
            SubTask(description="step 1"),
            SubTask(description="step 2"),
            SubTask(description="step 3"),
        ]
        ArtifactDependencyResolver.resolve(subtasks)
        assert subtasks[0].id in subtasks[1].dependencies
        assert subtasks[1].id in subtasks[2].dependencies
