import subprocess

from mmdev.git_utils import apply_patch


def run(args, cwd):
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True, timeout=10, check=False)
    assert result.returncode == 0, result.stderr or result.stdout
    return result


def setup_repo(tmp_path):
    run(["git", "init"], tmp_path)
    run(["git", "config", "user.email", "test@example.com"], tmp_path)
    run(["git", "config", "user.name", "Test User"], tmp_path)
    (tmp_path / "index.html").write_text(
        "\n".join(
            [
                "<!doctype html>",
                "<html>",
                "<head>",
                '  <meta charset="utf-8">',
                "  <title>TokenPatch Test</title>",
                "</head>",
                "<body>",
                "  <h1>TokenPatch Test</h1>",
                "</body>",
                "</html>",
                "",
            ]
        ),
        encoding="utf-8",
    )
    run(["git", "add", "index.html"], tmp_path)
    run(["git", "commit", "-m", "initial"], tmp_path)


def test_apply_patch_falls_back_to_context_search_when_hunk_line_is_offset(tmp_path):
    setup_repo(tmp_path)
    patch_path = tmp_path / "offset.patch"
    patch_path.write_text(
        """--- a/index.html
+++ b/index.html
@@ -3,7 +3,7 @@
 <html>
 <head>
   <meta charset="utf-8">
-  <title>TokenPatch Test</title>
+  <title>TokenPatch CLI Fallback</title>
 </head>
 <body>
   <h1>TokenPatch Test</h1>
""",
        encoding="utf-8",
    )

    apply_patch(tmp_path, patch_path, 10)

    assert "<title>TokenPatch CLI Fallback</title>" in (tmp_path / "index.html").read_text(encoding="utf-8")
