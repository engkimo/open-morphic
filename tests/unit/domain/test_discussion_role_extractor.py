"""Tests for DiscussionRoleExtractor — role extraction from goal text."""

from domain.services.discussion_role_extractor import DiscussionRoleExtractor


class TestExplicitLabel:
    """Pattern 1: 'role: X, Y' / 'roles: X, Y' / '役割: X, Y'."""

    def test_role_colon_english(self) -> None:
        goal = "discuss with Claude and GPT, role: optimist, pessimist"
        roles = DiscussionRoleExtractor.extract(goal)
        assert roles is not None
        assert roles == ["optimist", "pessimist"]

    def test_roles_colon_english(self) -> None:
        roles = DiscussionRoleExtractor.extract("analyze, roles: researcher, critic, reporter")
        assert roles is not None
        assert len(roles) == 3
        assert "researcher" in roles
        assert "critic" in roles
        assert "reporter" in roles

    def test_role_colon_japanese(self) -> None:
        roles = DiscussionRoleExtractor.extract("claudeとgeminiで議論して、role: 賛成派, 反対派")
        assert roles is not None
        assert roles == ["賛成派", "反対派"]

    def test_yakuwari_colon_japanese(self) -> None:
        roles = DiscussionRoleExtractor.extract("役割: データ分析、リスク評価、最終判断")
        assert roles is not None
        assert len(roles) == 3
        assert "データ分析" in roles
        assert "リスク評価" in roles

    def test_yakuwari_ha_japanese(self) -> None:
        roles = DiscussionRoleExtractor.extract("役割は賛成派と反対派")
        assert roles is not None
        assert "賛成派" in roles
        assert "反対派" in roles

    def test_fullwidth_colon(self) -> None:
        roles = DiscussionRoleExtractor.extract("役割：技術評価、ビジネス分析")
        assert roles is not None
        assert len(roles) == 2

    def test_case_insensitive(self) -> None:
        roles = DiscussionRoleExtractor.extract("Role: analyst, reviewer")
        assert roles is not None
        assert roles == ["analyst", "reviewer"]

    def test_role_with_period(self) -> None:
        roles = DiscussionRoleExtractor.extract("role: supporter, critic. Discuss the topic.")
        assert roles is not None
        assert roles == ["supporter", "critic"]


class TestToshitePattern:
    """Pattern 2: 'Xとして、Yとして'."""

    def test_two_roles(self) -> None:
        roles = DiscussionRoleExtractor.extract("賛成派として、反対派として議論して")
        assert roles is not None
        assert roles == ["賛成派", "反対派"]

    def test_three_roles(self) -> None:
        roles = DiscussionRoleExtractor.extract("分析者として、批評家として、報告者として検討")
        assert roles is not None
        assert len(roles) == 3

    def test_filters_model_names(self) -> None:
        """Model names like 'claude' should not be treated as roles."""
        roles = DiscussionRoleExtractor.extract("claudeとして賛成派として議論")
        # 'claude' filtered out, only 1 role left → returns None (need >=2)
        assert roles is None

    def test_single_toshite_returns_none(self) -> None:
        """Need at least 2 roles for として pattern."""
        roles = DiscussionRoleExtractor.extract("リーダーとして行動して")
        assert roles is None


class TestPerspectivePattern:
    """Pattern 3: 'Xの立場で' / 'Xの視点で' / 'Xの観点で'."""

    def test_tachiba(self) -> None:
        roles = DiscussionRoleExtractor.extract("消費者の立場で、生産者の立場で分析")
        assert roles is not None
        assert roles == ["消費者", "生産者"]

    def test_shiten(self) -> None:
        roles = DiscussionRoleExtractor.extract("技術の視点で、ビジネスの視点で検討")
        assert roles is not None
        assert roles == ["技術", "ビジネス"]

    def test_kanten(self) -> None:
        roles = DiscussionRoleExtractor.extract("法律の観点で、倫理の観点で議論")
        assert roles is not None
        assert roles == ["法律", "倫理"]

    def test_single_perspective_returns_none(self) -> None:
        roles = DiscussionRoleExtractor.extract("技術の視点で分析して")
        assert roles is None


class TestAsRolePattern:
    """Pattern 4: English 'as a [role]' pattern."""

    def test_two_as_roles(self) -> None:
        roles = DiscussionRoleExtractor.extract(
            "Claude as a financial analyst, Gemini as a risk assessor"
        )
        assert roles is not None
        assert len(roles) == 2
        assert "financial analyst" in roles
        assert "risk assessor" in roles

    def test_as_an_role(self) -> None:
        roles = DiscussionRoleExtractor.extract("analyze as an optimist, as a pessimist")
        assert roles is not None
        assert len(roles) == 2

    def test_single_as_returns_none(self) -> None:
        roles = DiscussionRoleExtractor.extract("act as a leader")
        assert roles is None


class TestNoRoles:
    """When no role pattern is detected."""

    def test_plain_task(self) -> None:
        roles = DiscussionRoleExtractor.extract("FizzBuzzを書いて")
        assert roles is None

    def test_multi_model_no_roles(self) -> None:
        roles = DiscussionRoleExtractor.extract("claudeとgeminiで分析して")
        assert roles is None

    def test_empty_string(self) -> None:
        roles = DiscussionRoleExtractor.extract("")
        assert roles is None


class TestPriority:
    """Explicit label takes priority over implicit patterns."""

    def test_label_over_toshite(self) -> None:
        roles = DiscussionRoleExtractor.extract("賛成派として、role: 分析者, 批評家")
        assert roles is not None
        # Label pattern wins
        assert roles == ["分析者", "批評家"]


class TestRoleGenerationPrompt:
    """build_role_generation_prompt returns a valid prompt string."""

    def test_contains_goal(self) -> None:
        prompt = DiscussionRoleExtractor.build_role_generation_prompt(goal="市場分析", count=3)
        assert "市場分析" in prompt
        assert "3" in prompt
        assert "JSON" in prompt

    def test_contains_count(self) -> None:
        prompt = DiscussionRoleExtractor.build_role_generation_prompt(goal="test", count=2)
        assert "exactly 2" in prompt
