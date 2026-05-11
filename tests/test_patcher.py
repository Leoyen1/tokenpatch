import pytest

from mmdev.patcher import PatchSafetyError, assert_patch_within_allowed_files, changed_files_from_patch


PATCH = """diff --git a/src/todos.py b/src/todos.py
--- a/src/todos.py
+++ b/src/todos.py
@@ -1 +1 @@
-old
+new
"""


def test_changed_files_from_patch():
    assert changed_files_from_patch(PATCH) == ["src/todos.py"]


def test_assert_patch_within_allowed_files_accepts_allowed_file():
    assert assert_patch_within_allowed_files(PATCH, ["src/todos.py"]) == ["src/todos.py"]


def test_assert_patch_within_allowed_files_rejects_disallowed_file():
    with pytest.raises(PatchSafetyError):
        assert_patch_within_allowed_files(PATCH, ["src/other.py"])

