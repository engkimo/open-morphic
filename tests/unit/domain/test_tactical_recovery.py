"""Tests for TacticalRecovery domain service."""

from __future__ import annotations

from domain.entities.execution import Action
from domain.entities.strategy import RecoveryRule
from domain.services.tactical_recovery import TacticalRecovery
from domain.value_objects.risk_level import RiskLevel


def _rule(
    pattern: str = "timeout",
    failed_tool: str = "",
    alt_tool: str = "shell_exec",
    success: int = 1,
    total: int = 1,
    alt_args: dict | None = None,
) -> RecoveryRule:
    return RecoveryRule(
        error_pattern=pattern,
        failed_tool=failed_tool,
        alternative_tool=alt_tool,
        alternative_args=alt_args or {},
        success_count=success,
        total_attempts=total,
    )


def _action(tool: str = "browser_navigate", **kwargs) -> Action:  # type: ignore[no-untyped-def]
    return Action(tool=tool, **kwargs)


class TestFindAlternative:
    def test_basic_match(self) -> None:
        rules = [_rule(pattern="timeout", alt_tool="web_fetch")]
        result = TacticalRecovery.find_alternative(_action(), "Connection timeout after 30s", rules)
        assert result is not None
        assert result.tool == "web_fetch"

    def test_no_match_returns_none(self) -> None:
        rules = [_rule(pattern="timeout", alt_tool="web_fetch")]
        result = TacticalRecovery.find_alternative(
            _action(), "FileNotFoundError: config.yaml", rules
        )
        assert result is None

    def test_empty_rules_returns_none(self) -> None:
        result = TacticalRecovery.find_alternative(_action(), "some error", [])
        assert result is None

    def test_tool_filter_match(self) -> None:
        rules = [
            _rule(pattern="timeout", failed_tool="browser_navigate", alt_tool="web_fetch"),
        ]
        result = TacticalRecovery.find_alternative(_action("browser_navigate"), "timeout", rules)
        assert result is not None
        assert result.tool == "web_fetch"

    def test_tool_filter_mismatch(self) -> None:
        rules = [
            _rule(pattern="timeout", failed_tool="shell_exec", alt_tool="web_fetch"),
        ]
        result = TacticalRecovery.find_alternative(_action("browser_navigate"), "timeout", rules)
        assert result is None

    def test_empty_failed_tool_matches_any(self) -> None:
        rules = [_rule(pattern="timeout", failed_tool="", alt_tool="retry_tool")]
        result = TacticalRecovery.find_alternative(_action("any_tool"), "timeout occurred", rules)
        assert result is not None
        assert result.tool == "retry_tool"

    def test_selects_highest_success_rate(self) -> None:
        rules = [
            _rule(pattern="error", alt_tool="low_rate", success=1, total=10),
            _rule(pattern="error", alt_tool="high_rate", success=9, total=10),
        ]
        result = TacticalRecovery.find_alternative(_action(), "error happened", rules)
        assert result is not None
        assert result.tool == "high_rate"

    def test_regex_pattern_match(self) -> None:
        rules = [_rule(pattern=r"connection.*refused", alt_tool="retry_tool")]
        result = TacticalRecovery.find_alternative(
            _action(), "connection was refused by server", rules
        )
        assert result is not None
        assert result.tool == "retry_tool"

    def test_case_insensitive_match(self) -> None:
        rules = [_rule(pattern="TIMEOUT", alt_tool="alt")]
        result = TacticalRecovery.find_alternative(_action(), "request timeout", rules)
        assert result is not None

    def test_invalid_regex_falls_back_to_substring(self) -> None:
        rules = [_rule(pattern="[invalid regex", alt_tool="alt")]
        result = TacticalRecovery.find_alternative(
            _action(), "contains [invalid regex in message", rules
        )
        assert result is not None

    def test_preserves_risk_level(self) -> None:
        rules = [_rule(pattern="err", alt_tool="alt")]
        action = _action(risk=RiskLevel.HIGH)
        result = TacticalRecovery.find_alternative(action, "err", rules)
        assert result is not None
        assert result.risk == RiskLevel.HIGH

    def test_includes_alternative_args(self) -> None:
        rules = [_rule(pattern="err", alt_tool="alt", alt_args={"timeout": 60})]
        result = TacticalRecovery.find_alternative(_action(), "err", rules)
        assert result is not None
        assert result.args == {"timeout": 60}

    def test_description_set(self) -> None:
        rules = [_rule(pattern="timeout", alt_tool="web_fetch")]
        result = TacticalRecovery.find_alternative(_action(), "timeout", rules)
        assert result is not None
        assert "Recovery" in result.description


class TestCreateRuleFromRecovery:
    def test_basic_rule_creation(self) -> None:
        failed = _action("browser_navigate")
        successful = _action("web_fetch", args={"url": "http://example.com"})
        rule = TacticalRecovery.create_rule_from_recovery(failed, "Connection timeout", successful)
        assert rule.failed_tool == "browser_navigate"
        assert rule.alternative_tool == "web_fetch"
        assert rule.alternative_args == {"url": "http://example.com"}
        assert rule.success_count == 1
        assert rule.total_attempts == 1

    def test_error_pattern_extracted(self) -> None:
        rule = TacticalRecovery.create_rule_from_recovery(
            _action(), "FileNotFoundError: /home/user/config.yaml", _action("alt")
        )
        assert rule.error_pattern  # non-empty
        assert "<path>" in rule.error_pattern  # path replaced

    def test_long_error_truncated(self) -> None:
        long_err = "Error: " + "x" * 200
        rule = TacticalRecovery.create_rule_from_recovery(_action(), long_err, _action("alt"))
        assert len(rule.error_pattern) <= 120

    def test_empty_error_message(self) -> None:
        rule = TacticalRecovery.create_rule_from_recovery(_action(), "", _action("alt"))
        assert rule.error_pattern == "unknown_error"

    def test_multiline_error_uses_first_line(self) -> None:
        error = "TimeoutError: connection timed out\n  at line 42\n  in module foo"
        rule = TacticalRecovery.create_rule_from_recovery(_action(), error, _action("alt"))
        assert "line" not in rule.error_pattern
        assert "TimeoutError" in rule.error_pattern


class TestRankRules:
    def test_rank_by_success_rate(self) -> None:
        rules = [
            _rule(pattern="a", alt_tool="low", success=1, total=10),
            _rule(pattern="b", alt_tool="high", success=9, total=10),
            _rule(pattern="c", alt_tool="mid", success=5, total=10),
        ]
        ranked = TacticalRecovery.rank_rules(rules)
        assert ranked[0].alternative_tool == "high"
        assert ranked[1].alternative_tool == "mid"
        assert ranked[2].alternative_tool == "low"

    def test_tiebreak_by_sample_size(self) -> None:
        rules = [
            _rule(pattern="a", alt_tool="small", success=1, total=2),
            _rule(pattern="b", alt_tool="large", success=5, total=10),
        ]
        ranked = TacticalRecovery.rank_rules(rules)
        # Both have 50% success rate, but "large" has more attempts
        assert ranked[0].alternative_tool == "large"

    def test_empty_list(self) -> None:
        assert TacticalRecovery.rank_rules([]) == []

    def test_single_rule(self) -> None:
        rules = [_rule()]
        assert TacticalRecovery.rank_rules(rules) == rules
