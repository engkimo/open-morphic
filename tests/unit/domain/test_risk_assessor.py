"""TDD: RiskAssessor tests — written FIRST, then implement domain service."""

from domain.entities.execution import Action
from domain.services.risk_assessor import RiskAssessor
from domain.value_objects import RiskLevel


class TestRiskAssessor:
    """Test risk assessment for LAEE actions."""

    def setup_method(self):
        self.assessor = RiskAssessor()

    # ── SAFE operations ──
    def test_fs_read_is_safe(self):
        action = Action(tool="fs_read", args={"path": "/tmp/test.txt"})
        assert self.assessor.assess(action) == RiskLevel.SAFE

    def test_fs_glob_is_safe(self):
        action = Action(tool="fs_glob", args={"pattern": "*.py"})
        assert self.assessor.assess(action) == RiskLevel.SAFE

    def test_fs_tree_is_safe(self):
        action = Action(tool="fs_tree", args={"path": "."})
        assert self.assessor.assess(action) == RiskLevel.SAFE

    def test_system_process_list_is_safe(self):
        action = Action(tool="system_process_list")
        assert self.assessor.assess(action) == RiskLevel.SAFE

    def test_system_screenshot_is_safe(self):
        action = Action(tool="system_screenshot")
        assert self.assessor.assess(action) == RiskLevel.SAFE

    # ── LOW operations ──
    def test_shell_background_is_low(self):
        action = Action(tool="shell_background", args={"cmd": "sleep 10"})
        assert self.assessor.assess(action) == RiskLevel.LOW

    def test_system_notify_is_low(self):
        action = Action(tool="system_notify", args={"message": "hello"})
        assert self.assessor.assess(action) == RiskLevel.LOW

    # ── MEDIUM operations ──
    def test_fs_write_is_medium(self):
        action = Action(tool="fs_write", args={"path": "/tmp/new.txt", "content": "hi"})
        assert self.assessor.assess(action) == RiskLevel.MEDIUM

    def test_shell_exec_is_medium(self):
        action = Action(tool="shell_exec", args={"cmd": "echo hello"})
        assert self.assessor.assess(action) == RiskLevel.MEDIUM

    def test_dev_git_is_medium(self):
        action = Action(tool="dev_git", args={"cmd": "git add ."})
        assert self.assessor.assess(action) == RiskLevel.MEDIUM

    def test_dev_pkg_install_is_medium(self):
        action = Action(tool="dev_pkg_install", args={"pkg": "requests"})
        assert self.assessor.assess(action) == RiskLevel.MEDIUM

    # ── HIGH operations ──
    def test_fs_delete_is_high(self):
        action = Action(tool="fs_delete", args={"path": "/tmp/test.txt"})
        assert self.assessor.assess(action) == RiskLevel.HIGH

    def test_system_process_kill_is_high(self):
        action = Action(tool="system_process_kill", args={"pid": 1234})
        assert self.assessor.assess(action) == RiskLevel.HIGH

    # ── CRITICAL operations ──
    def test_fs_delete_recursive_is_critical(self):
        action = Action(tool="fs_delete", args={"path": "/tmp/folder", "recursive": True})
        assert self.assessor.assess(action) == RiskLevel.CRITICAL

    def test_shell_exec_sudo_is_critical(self):
        action = Action(tool="shell_exec", args={"cmd": "sudo rm -rf /tmp/test"})
        assert self.assessor.assess(action) == RiskLevel.CRITICAL

    def test_shell_exec_rm_rf_is_critical(self):
        action = Action(tool="shell_exec", args={"cmd": "rm -rf /home/user"})
        assert self.assessor.assess(action) == RiskLevel.CRITICAL

    def test_credential_path_is_critical(self):
        action = Action(tool="fs_read", args={"path": "/home/user/.ssh/id_rsa"})
        assert self.assessor.assess(action) == RiskLevel.CRITICAL

    def test_env_file_is_critical(self):
        action = Action(tool="fs_read", args={"path": "/project/.env"})
        assert self.assessor.assess(action) == RiskLevel.CRITICAL

    def test_aws_credentials_is_critical(self):
        action = Action(tool="fs_read", args={"path": "/home/user/.aws/credentials"})
        assert self.assessor.assess(action) == RiskLevel.CRITICAL
