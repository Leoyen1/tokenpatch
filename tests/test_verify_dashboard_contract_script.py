import json
from pathlib import Path

from gateway.scripts import verify_dashboard_contract


def write_contract_files(root: Path, version: str, *, mismatch_types: bool = False) -> None:
    (root / "gateway" / "mmdev_gateway").mkdir(parents=True, exist_ok=True)
    (root / "docs").mkdir(parents=True, exist_ok=True)

    (root / "gateway" / "mmdev_gateway" / "app.py").write_text(
        f'DASHBOARD_SCHEMA_VERSION = "{version}"\n',
        encoding="utf-8",
    )
    (root / "docs" / "API_CONTRACT.md").write_text(
        "\n".join(
            [
                f"Current dashboard schema version: `{version}`",
                f"`X-TokenPatch-Schema-Version: {version}`",
                f'`schema_version: "{version}"`',
            ]
        ),
        encoding="utf-8",
    )
    (root / "docs" / "dashboard-overview.example.json").write_text(
        json.dumps({"schema_version": version}, ensure_ascii=False),
        encoding="utf-8",
    )
    types_version = "2099-01-01.v9" if mismatch_types else version
    (root / "docs" / "dashboard-overview.types.ts").write_text(
        f'export const DASHBOARD_SCHEMA_VERSION = "{types_version}" as const;\n',
        encoding="utf-8",
    )
    (root / "docs" / "dashboard-overview.openapi-fragment.yaml").write_text(
        "\n".join(
            [
                "openapi: 3.1.0",
                "info:",
                f"  version: {version}",
                "paths: {}",
                "components:",
                "  schemas:",
                "    X:",
                f"      example: {version}",
            ]
        ),
        encoding="utf-8",
    )


def test_collect_and_validate_versions_ok(tmp_path):
    version = "2026-05-11.v1"
    write_contract_files(tmp_path, version)
    collected = verify_dashboard_contract.collect_versions(tmp_path)
    assert collected["app_version"] == version
    assert verify_dashboard_contract.validate_versions(collected) == []


def test_validate_versions_reports_mismatch(tmp_path):
    version = "2026-05-11.v1"
    write_contract_files(tmp_path, version, mismatch_types=True)
    collected = verify_dashboard_contract.collect_versions(tmp_path)
    issues = verify_dashboard_contract.validate_versions(collected)
    assert any("types_ts_version" in issue for issue in issues)


def test_main_json_mode_outputs_ok_for_repo():
    rc = verify_dashboard_contract.main(["--json"])
    assert rc == 0
