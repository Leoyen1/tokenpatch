import subprocess

from mmdev.config import MMDevConfig, init_state_dir
from mmdev.doctor import format_doctor, run_doctor
from mmdev.models.base import CompletionResult


class FakeAPIClient:
    def __init__(self, text='{"ok": true}', fail=False):
        self.text = text
        self.fail = fail
        self.calls = 0

    def complete(self, *, prompt, model, timeout_seconds):
        self.calls += 1
        if self.fail:
            raise RuntimeError("boom")
        return CompletionResult(text=self.text)


def test_doctor_reports_missing_git_and_uninitialized_state(tmp_path):
    result = run_doctor(MMDevConfig(workdir=tmp_path))
    by_name = {check.name: check for check in result.checks}
    assert by_name["workdir"].status == "pass"
    assert by_name["local-state"].status == "warn"
    assert by_name["git"].status == "fail"
    assert result.ok is False
    assert "[FAIL] git" in format_doctor(result)


def test_doctor_passes_git_head_and_worktree_after_init_and_commit(tmp_path):
    init_state_dir(tmp_path)
    subprocess.run(["git", "init"], cwd=tmp_path, text=True, capture_output=True, timeout=10, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, text=True, capture_output=True, timeout=10, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, text=True, capture_output=True, timeout=10, check=True)
    (tmp_path / "README.md").write_text("sample\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, text=True, capture_output=True, timeout=10, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, text=True, capture_output=True, timeout=10, check=True)

    result = run_doctor(
        MMDevConfig(
            workdir=tmp_path,
            openai_api_key="x",
            openai_planner_model="planner",
            openai_reviewer_model="reviewer",
            deepseek_api_key="x",
            deepseek_base_url="https://example.test",
            deepseek_executor_model="executor",
        )
    )
    by_name = {check.name: check for check in result.checks}
    assert by_name["local-state"].status == "pass"
    assert by_name["git"].status == "pass"
    assert by_name["git-head"].status == "pass"
    assert by_name["worktree-support"].status == "pass"
    assert by_name["strong-model-config"].status == "pass"
    assert by_name["executor-config"].status == "pass"


def test_doctor_api_checks_are_opt_in(tmp_path):
    client = FakeAPIClient()
    run_doctor(
        MMDevConfig(
            workdir=tmp_path,
            openai_api_key="x",
            openai_planner_model="planner",
            deepseek_api_key="x",
            deepseek_base_url="https://example.test",
            deepseek_executor_model="executor",
        ),
        openai_client=client,
        deepseek_client=client,
    )
    assert client.calls == 0


def test_doctor_api_checks_use_injected_clients(tmp_path):
    openai = FakeAPIClient()
    deepseek = FakeAPIClient()
    result = run_doctor(
        MMDevConfig(
            workdir=tmp_path,
            openai_api_key="x",
            openai_planner_model="planner",
            deepseek_api_key="x",
            deepseek_base_url="https://example.test",
            deepseek_executor_model="executor",
        ),
        check_api=True,
        openai_client=openai,
        deepseek_client=deepseek,
    )
    by_name = {check.name: check for check in result.checks}
    assert by_name["strong-model-api"].status == "pass"
    assert by_name["executor-api"].status == "pass"
    assert openai.calls == 1
    assert deepseek.calls == 1


def test_doctor_api_check_reports_failure(tmp_path):
    result = run_doctor(
        MMDevConfig(workdir=tmp_path, openai_api_key="x", openai_planner_model="planner"),
        check_api=True,
        openai_client=FakeAPIClient(fail=True),
    )
    by_name = {check.name: check for check in result.checks}
    assert by_name["strong-model-api"].status == "fail"
    assert by_name["executor-api"].status == "warn"


def test_doctor_gateway_executor_config_and_api(tmp_path):
    gateway = FakeAPIClient()
    result = run_doctor(
        MMDevConfig(
            workdir=tmp_path,
            executor_provider="mmdev_gateway",
            mmdev_gateway_url="https://gateway.example.test",
            mmdev_gateway_token="token",
            openai_api_key="x",
            openai_planner_model="planner",
        ),
        check_api=True,
        openai_client=FakeAPIClient(),
        deepseek_client=gateway,
    )
    by_name = {check.name: check for check in result.checks}
    assert by_name["executor-config"].status == "pass"
    assert by_name["executor-api"].status == "pass"
    assert gateway.calls == 1


def test_doctor_reports_executor_provider_reason_and_ignored_config(tmp_path):
    result = run_doctor(
        MMDevConfig(
            workdir=tmp_path,
            executor_provider="mmdev_gateway",
            executor_provider_reason="explicit environment executor_provider=mmdev_gateway",
            mmdev_gateway_url="https://gateway.example.test",
            mmdev_gateway_token="token",
            deepseek_api_key="deepseek-key",
        )
    )

    message = {check.name: check for check in result.checks}["executor-config"].message
    assert "explicit environment executor_provider=mmdev_gateway" in message
    assert "DeepSeek BYOK key is also configured but ignored" in message


def test_doctor_supports_claude_strong_model_config_and_api(tmp_path):
    strong = FakeAPIClient()
    result = run_doctor(
        MMDevConfig(
            workdir=tmp_path,
            strong_model_provider="claude",
            claude_api_key="x",
            claude_planner_model="claude-planner",
            claude_reviewer_model="claude-reviewer",
            deepseek_api_key="x",
            deepseek_base_url="https://example.test",
            deepseek_executor_model="executor",
        ),
        check_api=True,
        openai_client=strong,
        deepseek_client=FakeAPIClient(),
    )
    by_name = {check.name: check for check in result.checks}
    assert by_name["strong-model-config"].status == "pass"
    assert by_name["strong-model-api"].status == "pass"
    assert strong.calls == 1
