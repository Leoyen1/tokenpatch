import subprocess
from pathlib import Path


def test_fake_demo_script_runs_end_to_end():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        ["python", "examples/todo-app/scripts/run_fake_demo.py"],
        cwd=root,
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "final_status" in result.stdout
    assert "approved" in result.stdout
    assert (root / ".mmdev-demo" / "todo-app" / ".mmdev" / "patches" / "task-001-approved.patch").exists()
    assert (root / ".mmdev-demo" / "todo-app" / ".mmdev" / "reports" / "final-report.md").exists()
