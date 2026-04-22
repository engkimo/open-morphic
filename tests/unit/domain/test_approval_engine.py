"""TDD: ApprovalEngine tests — written FIRST, then implement domain service."""

from domain.services.approval_engine import ApprovalEngine
from domain.value_objects import ApprovalMode, RiskLevel


class TestApprovalEngine:
    """Test the approval matrix: mode × risk → needs_approval?"""

    def setup_method(self):
        self.engine = ApprovalEngine()

    # ── full-auto: nothing needs approval ──
    def test_full_auto_safe(self):
        assert self.engine.needs_approval(ApprovalMode.FULL_AUTO, RiskLevel.SAFE) is False

    def test_full_auto_critical(self):
        assert self.engine.needs_approval(ApprovalMode.FULL_AUTO, RiskLevel.CRITICAL) is False

    # ── confirm-destructive: HIGH and CRITICAL need approval ──
    def test_confirm_destructive_safe(self):
        assert self.engine.needs_approval(ApprovalMode.CONFIRM_DESTRUCTIVE, RiskLevel.SAFE) is False

    def test_confirm_destructive_low(self):
        assert self.engine.needs_approval(ApprovalMode.CONFIRM_DESTRUCTIVE, RiskLevel.LOW) is False

    def test_confirm_destructive_medium(self):
        assert (
            self.engine.needs_approval(ApprovalMode.CONFIRM_DESTRUCTIVE, RiskLevel.MEDIUM) is False
        )

    def test_confirm_destructive_high(self):
        assert self.engine.needs_approval(ApprovalMode.CONFIRM_DESTRUCTIVE, RiskLevel.HIGH) is True

    def test_confirm_destructive_critical(self):
        assert (
            self.engine.needs_approval(ApprovalMode.CONFIRM_DESTRUCTIVE, RiskLevel.CRITICAL) is True
        )

    # ── confirm-all: everything except SAFE needs approval ──
    def test_confirm_all_safe(self):
        assert self.engine.needs_approval(ApprovalMode.CONFIRM_ALL, RiskLevel.SAFE) is False

    def test_confirm_all_low(self):
        assert self.engine.needs_approval(ApprovalMode.CONFIRM_ALL, RiskLevel.LOW) is True

    def test_confirm_all_medium(self):
        assert self.engine.needs_approval(ApprovalMode.CONFIRM_ALL, RiskLevel.MEDIUM) is True

    def test_confirm_all_critical(self):
        assert self.engine.needs_approval(ApprovalMode.CONFIRM_ALL, RiskLevel.CRITICAL) is True
