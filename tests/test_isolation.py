import subprocess

from mmdev.config import MMDevConfig
from mmdev.isolation import export_worktree_diff
from mmdev.models.base import CompletionResult
from mmdev.workflow import run_auto
from tests.test_workflow import FakeExecutor, FakePlanner, FakeReviewer


def setup_committed_project(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, text=True, capture_output=True, timeout=10, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, text=True, capture_output=True, timeout=10, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, text=True, capture_output=True, timeout=10, check=True)
    src = tmp_path / "src"
    src.mkdir()
    (src / "todos.py").write_text("old\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, text=True, capture_output=True, timeout=10, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, text=True, capture_output=True, timeout=10, check=True)


def make_config(tmp_path):
    return MMDevConfig(
        workdir=tmp_path,
        openai_planner_model="planner",
        openai_reviewer_model="reviewer",
        deepseek_executor_model="executor",
        command_timeout_seconds=30,
    )


def test_export_worktree_diff_writes_patch_without_applying(tmp_path):
    setup_committed_project(tmp_path)
    config = make_config(tmp_path)
    run_auto("update todo file", config, FakePlanner(), FakeExecutor(), FakeReviewer(), isolation="worktree")

    patch_path = export_worktree_diff(config, "task-001")

    assert patch_path.name == "task-001-approved.patch"
    assert "+new" in patch_path.read_text(encoding="utf-8")
    assert (tmp_path / "src" / "todos.py").read_text(encoding="utf-8") == "old\n"


def test_export_worktree_diff_can_apply_to_main_worktree(tmp_path):
    setup_committed_project(tmp_path)
    config = make_config(tmp_path)
    run_auto("update todo file", config, FakePlanner(), FakeExecutor(), FakeReviewer(), isolation="worktree")

    export_worktree_diff(config, "task-001", apply_to_main=True)

    assert (tmp_path / "src" / "todos.py").read_text(encoding="utf-8") == "new\n"
