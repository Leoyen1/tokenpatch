import subprocess

import pytest

from mmdev.checkpoint import CheckpointError, checkpoint_diff, create_checkpoint, list_checkpoints, restore_checkpoint
from mmdev.config import MMDevConfig, init_state_dir


def run(args, cwd):
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True, timeout=10, check=False)
    assert result.returncode == 0, result.stderr or result.stdout
    return result


def setup_repo(tmp_path):
    run(["git", "init"], tmp_path)
    run(["git", "config", "user.email", "test@example.com"], tmp_path)
    run(["git", "config", "user.name", "Test User"], tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text("base\n", encoding="utf-8")
    run(["git", "add", "."], tmp_path)
    run(["git", "commit", "-m", "initial"], tmp_path)
    init_state_dir(tmp_path)
    return MMDevConfig(workdir=tmp_path)


def test_checkpoint_create_list_and_diff_records_tracked_and_untracked(tmp_path):
    config = setup_repo(tmp_path)
    (tmp_path / "src" / "app.py").write_text("changed\n", encoding="utf-8")
    (tmp_path / "scratch.txt").write_text("do not restore\n", encoding="utf-8")

    record = create_checkpoint(config, "before refactor")

    assert record.base_head
    assert "scratch.txt" in record.untracked_files
    assert "src/app.py" in checkpoint_diff(config.mmdev_dir, record.id)
    assert list_checkpoints(config.mmdev_dir)[0].id == record.id


def test_checkpoint_restore_is_dry_run_by_default_and_yes_restores_tracked_only(tmp_path):
    config = setup_repo(tmp_path)
    (tmp_path / "src" / "app.py").write_text("good\n", encoding="utf-8")
    record = create_checkpoint(config, "good state")

    (tmp_path / "src" / "app.py").write_text("bad\n", encoding="utf-8")
    (tmp_path / "new-local.txt").write_text("keep me\n", encoding="utf-8")

    dry = restore_checkpoint(config, record.id)
    assert dry["dry_run"] is True
    assert (tmp_path / "src" / "app.py").read_text(encoding="utf-8") == "bad\n"

    restored = restore_checkpoint(config, record.id, yes=True)
    assert restored["dry_run"] is False
    assert (tmp_path / "src" / "app.py").read_text(encoding="utf-8") == "good\n"
    assert (tmp_path / "new-local.txt").exists()
    assert any(item.source == "pre-restore" for item in list_checkpoints(config.mmdev_dir))


def test_checkpoint_restore_rejects_head_mismatch_by_default(tmp_path):
    config = setup_repo(tmp_path)
    record = create_checkpoint(config, "base")
    (tmp_path / "src" / "other.py").write_text("other\n", encoding="utf-8")
    run(["git", "add", "."], tmp_path)
    run(["git", "commit", "-m", "second"], tmp_path)

    with pytest.raises(CheckpointError, match="HEAD differs"):
        restore_checkpoint(config, record.id, yes=True)
