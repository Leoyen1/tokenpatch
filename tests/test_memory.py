import json
import subprocess

from mmdev.config import MMDevConfig, init_state_dir
from mmdev.memory import load_memory, memory_prompt_block, refresh_memory, render_memory_markdown


def run(args, cwd):
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True, timeout=10, check=False)
    assert result.returncode == 0, result.stderr or result.stdout
    return result


def setup_repo(tmp_path):
    run(["git", "init"], tmp_path)
    run(["git", "config", "user.email", "test@example.com"], tmp_path)
    run(["git", "config", "user.name", "Test User"], tmp_path)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_demo.py").write_text("def test_demo():\n    assert True\n", encoding="utf-8")
    run(["git", "add", "."], tmp_path)
    run(["git", "commit", "-m", "initial"], tmp_path)
    mmdev_dir = init_state_dir(tmp_path)
    (mmdev_dir / "tasks.json").write_text(
        json.dumps(
            {
                "project_summary": "Demo project.",
                "assumptions": [],
                "risks": [],
                "tasks": [
                    {
                        "task_id": "task-001",
                        "title": "Update demo",
                        "goal": "Update demo",
                        "context": "",
                        "allowed_files": ["tests/test_demo.py"],
                        "forbidden_changes": [],
                        "acceptance_criteria": ["tests pass"],
                        "validation_commands": ["python -m pytest"],
                        "complexity": "low",
                        "recommended_executor": "cheap",
                        "max_attempts": 2,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return MMDevConfig(workdir=tmp_path)


def test_memory_refresh_writes_deterministic_project_memory_without_model(tmp_path):
    config = setup_repo(tmp_path)

    memory = refresh_memory(config)

    assert memory.project_summary == "Demo project."
    assert "python -m pytest" in memory.known_commands
    assert "tests/test_demo.py" in memory.key_files
    assert load_memory(config.mmdev_dir) is not None
    markdown = render_memory_markdown(memory)
    assert "Project Memory Pack" in markdown
    assert "tests/test_demo.py" in markdown


def test_memory_prompt_block_respects_character_limit(tmp_path):
    config = setup_repo(tmp_path)
    refresh_memory(config)

    block = memory_prompt_block(config.mmdev_dir, max_chars=80)

    assert block.startswith("## tokenpatch Project Memory Pack")
    assert "Memory truncated" in block
