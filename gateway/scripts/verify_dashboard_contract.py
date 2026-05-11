from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify tokenpatch dashboard contract version consistency.")
    parser.add_argument("--repo-root", default="", help="Repository root path; default auto-detected")
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    return parser.parse_args(argv)


def default_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def collect_versions(repo_root: Path) -> dict[str, object]:
    paths = {
        "app": repo_root / "gateway" / "mmdev_gateway" / "app.py",
        "api_contract": repo_root / "docs" / "API_CONTRACT.md",
        "example_json": repo_root / "docs" / "dashboard-overview.example.json",
        "types_ts": repo_root / "docs" / "dashboard-overview.types.ts",
        "openapi": repo_root / "docs" / "dashboard-overview.openapi-fragment.yaml",
    }
    for name, path in paths.items():
        if not path.exists():
            raise FileNotFoundError(f"missing required file: {name} -> {path}")

    app_text = paths["app"].read_text(encoding="utf-8")
    contract_text = paths["api_contract"].read_text(encoding="utf-8")
    example_payload = json.loads(paths["example_json"].read_text(encoding="utf-8"))
    types_text = paths["types_ts"].read_text(encoding="utf-8")
    openapi_text = paths["openapi"].read_text(encoding="utf-8")

    app_version = extract_version_with_regex(app_text, r'DASHBOARD_SCHEMA_VERSION\s*=\s*"([^"]+)"', "app version")
    contract_current = extract_version_with_regex(
        contract_text,
        r"Current dashboard schema version:\s*`([^`]+)`",
        "API contract current version",
    )
    contract_header = extract_version_with_regex(
        contract_text,
        r"X-TokenPatch-Schema-Version:\s*([0-9]{4}-[0-9]{2}-[0-9]{2}\.v[0-9]+)",
        "API contract header version",
    )
    contract_body = extract_version_with_regex(
        contract_text,
        r'schema_version:\s*"([0-9]{4}-[0-9]{2}-[0-9]{2}\.v[0-9]+)"',
        "API contract body version",
    )
    example_version = str(example_payload.get("schema_version", "")).strip()
    if not example_version:
        raise ValueError("dashboard-overview.example.json missing schema_version")

    types_version = extract_version_with_regex(types_text, r'DASHBOARD_SCHEMA_VERSION\s*=\s*"([^"]+)"', "TypeScript version")
    openapi_info_version = extract_openapi_info_version(openapi_text)
    openapi_example_versions = sorted(set(re.findall(r"example:\s*([0-9]{4}-[0-9]{2}-[0-9]{2}\.v[0-9]+)", openapi_text)))

    return {
        "app_version": app_version,
        "api_contract_current": contract_current,
        "api_contract_header": contract_header,
        "api_contract_body": contract_body,
        "example_json_version": example_version,
        "types_ts_version": types_version,
        "openapi_info_version": openapi_info_version,
        "openapi_example_versions": openapi_example_versions,
    }


def validate_versions(collected: dict[str, object]) -> list[str]:
    issues: list[str] = []
    expected = str(collected["app_version"])
    exact_keys = [
        "api_contract_current",
        "api_contract_header",
        "api_contract_body",
        "example_json_version",
        "types_ts_version",
        "openapi_info_version",
    ]
    for key in exact_keys:
        value = str(collected.get(key, ""))
        if value != expected:
            issues.append(f"{key}={value} does not match app_version={expected}")

    openapi_example_versions = collected.get("openapi_example_versions")
    if not isinstance(openapi_example_versions, list) or not openapi_example_versions:
        issues.append("openapi_example_versions missing")
    else:
        mismatched = [v for v in openapi_example_versions if v != expected]
        if mismatched:
            issues.append(
                "openapi_example_versions contain mismatches: "
                + ", ".join(openapi_example_versions)
                + f" (expected {expected})"
            )
    return issues


def extract_version_with_regex(text: str, pattern: str, field_name: str) -> str:
    match = re.search(pattern, text)
    if not match:
        raise ValueError(f"cannot parse {field_name}")
    return match.group(1).strip()


def extract_openapi_info_version(text: str) -> str:
    in_info = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "info:":
            in_info = True
            continue
        if in_info and line and not line.startswith(" "):
            break
        if in_info:
            match = re.match(r"\s*version:\s*(.+)\s*$", line)
            if match:
                return match.group(1).strip().strip('"').strip("'")
    raise ValueError("cannot parse OpenAPI info.version")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve() if args.repo_root else default_repo_root()
    collected = collect_versions(repo_root)
    issues = validate_versions(collected)
    result = {
        "ok": len(issues) == 0,
        "repo_root": str(repo_root),
        "versions": collected,
        "issues": issues,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if issues:
            print("dashboard contract check failed")
            for issue in issues:
                print(f"- {issue}")
        else:
            print(f"dashboard contract check passed: {collected['app_version']}")
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
