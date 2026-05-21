from mmdev.cursor_install import cursor_rule_text, default_cursor_rule_path, install_cursor_rules


def test_default_cursor_rule_path(tmp_path):
    assert default_cursor_rule_path(tmp_path) == tmp_path / ".cursor" / "rules" / "tokenpatch.mdc"


def test_cursor_rule_text_contains_cli_fallback():
    text = cursor_rule_text(python_command="C:\\Python314\\python.exe")

    assert "alwaysApply: true" in text
    assert "Do not directly edit source files before trying tokenpatch." in text
    assert "tp:" in text
    assert "C:\\Python314\\python.exe -m mmdev.cli do" in text
    assert "metrics --workdir ." in text
    assert "report --workdir ." in text
    assert "Savings ratio" in text
    assert "Users may ask in any language" in text
    assert "Equivalent requests in other languages are also valid" in text


def test_install_cursor_rules_dry_run_does_not_write(tmp_path):
    result = install_cursor_rules(workdir=tmp_path, dry_run=True, python_command="python")

    assert result.changed is True
    assert result.backup_path is None
    assert not result.rules_path.exists()


def test_install_cursor_rules_writes_and_is_idempotent(tmp_path):
    result = install_cursor_rules(workdir=tmp_path, python_command="python")

    assert result.changed is True
    assert result.rules_path.exists()
    assert "Use tokenpatch" in result.rules_path.read_text(encoding="utf-8")

    again = install_cursor_rules(workdir=tmp_path, python_command="python")
    assert again.changed is False
    assert again.backup_path is None


def test_install_cursor_rules_backs_up_existing_rule(tmp_path):
    rules_path = default_cursor_rule_path(tmp_path)
    rules_path.parent.mkdir(parents=True)
    rules_path.write_text("old rule", encoding="utf-8")

    result = install_cursor_rules(workdir=tmp_path, python_command="python")

    assert result.changed is True
    assert result.backup_path is not None
    assert result.backup_path.exists()
    assert result.backup_path.read_text(encoding="utf-8") == "old rule"
