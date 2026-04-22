"""Tests for MemoryClassifier domain service."""

from __future__ import annotations

import pytest

from domain.services.memory_classifier import MemoryClassifier
from domain.value_objects.cognitive import CognitiveMemoryType

# Short aliases for readability
_c = MemoryClassifier.classify
_P = CognitiveMemoryType.PROCEDURAL
_S = CognitiveMemoryType.SEMANTIC
_W = CognitiveMemoryType.WORKING
_E = CognitiveMemoryType.EPISODIC


class TestClassify:
    """MemoryClassifier.classify — first-match priority."""

    def test_procedural_how_to(self) -> None:
        assert _c("how to deploy the app") == _P

    def test_procedural_steps(self) -> None:
        assert _c("steps to reproduce the bug") == _P

    def test_procedural_strategy(self) -> None:
        assert _c("our strategy is to scale horizontally") == _P

    def test_procedural_best_practice(self) -> None:
        assert _c("best practice is to use connection pooling") == _P

    def test_procedural_always(self) -> None:
        assert _c("always run tests before pushing") == _P

    def test_procedural_never(self) -> None:
        assert _c("never commit secrets to the repo") == _P

    def test_procedural_avoid(self) -> None:
        assert _c("avoid using global state") == _P

    def test_procedural_prefer(self) -> None:
        assert _c("prefer composition over inheritance") == _P

    def test_semantic_uses(self) -> None:
        assert _c("the project uses PostgreSQL") == _S

    def test_semantic_requires(self) -> None:
        assert _c("this module requires Python 3.12") == _S

    def test_semantic_depends_on(self) -> None:
        assert _c("auth service depends on Redis") == _S

    def test_semantic_version(self) -> None:
        assert _c("version 2.3.1 added async support") == _S

    def test_working_currently(self) -> None:
        assert _c("currently refactoring the router") == _W

    def test_working_in_progress(self) -> None:
        assert _c("database migration is in progress") == _W

    def test_working_blocked(self) -> None:
        assert _c("deployment is blocked by CI failure") == _W

    def test_episodic_decided(self) -> None:
        assert _c("we decided to use FastAPI") == _E

    def test_episodic_failed(self) -> None:
        assert _c("the migration failed at step 3") == _E

    def test_episodic_completed(self) -> None:
        assert _c("task completed successfully") == _E

    def test_default_is_episodic(self) -> None:
        assert _c("some random text") == _E

    def test_empty_string(self) -> None:
        assert _c("") == _E

    def test_priority_procedural_over_semantic(self) -> None:
        """When both procedural and semantic match, procedural wins."""
        text = "how to configure the module that uses Redis"
        assert _c(text) == _P

    def test_priority_procedural_over_working(self) -> None:
        text = "best practice when currently blocked"
        assert _c(text) == _P

    def test_priority_semantic_over_episodic(self) -> None:
        text = "the service uses Python and was created yesterday"
        assert _c(text) == _S

    def test_case_insensitive(self) -> None:
        assert _c("HOW TO debug") == _P


class TestClassifyWithConfidence:
    """MemoryClassifier.classify_with_confidence — hit-count confidence."""

    def test_no_match_returns_episodic_030(self) -> None:
        mt, conf = MemoryClassifier.classify_with_confidence("xyz")
        assert mt == _E
        assert conf == pytest.approx(0.3)

    def test_single_hit_050(self) -> None:
        mt, conf = MemoryClassifier.classify_with_confidence("uses PostgreSQL")
        assert mt == _S
        assert conf == pytest.approx(0.5)

    def test_two_hits_070(self) -> None:
        mt, conf = MemoryClassifier.classify_with_confidence("uses PostgreSQL and requires Python")
        assert mt == _S
        assert conf == pytest.approx(0.7)

    def test_three_hits_capped_090(self) -> None:
        text = "how to avoid errors and always prefer immutability"
        mt, conf = MemoryClassifier.classify_with_confidence(text)
        assert mt == _P
        assert conf == pytest.approx(0.9)

    def test_many_hits_capped_at_090(self) -> None:
        text = "always prefer to avoid issues; never skip; strategy first; best practice"
        mt, conf = MemoryClassifier.classify_with_confidence(text)
        assert mt == _P
        assert conf == pytest.approx(0.9)

    def test_best_category_by_hit_count(self) -> None:
        """Category with most hits wins, regardless of priority."""
        text = "uses Redis, requires Python, depends on Docker, strategy once"
        mt, conf = MemoryClassifier.classify_with_confidence(text)
        assert mt == _S
        # 3 semantic hits -> 0.3 + 3*0.2 = 0.9
        assert conf == pytest.approx(0.9)
